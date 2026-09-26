#!/usr/bin/env python3
"""
audit_memory.py — deterministic checks for an agent memory system.

Checks only things a script can decide. Judgement calls (is this fact in the
right layer? is it still true?) stay with the agent reading the report.

Usage:
  python audit_memory.py --repo PATH [--memory-dir PATH] [--global-file PATH] [--json]

Every check prints FAIL (a breach), WARN (worth a look) or nothing. Exit code
is 1 if any FAIL, else 0. A check that has never failed has never been tested:
run with --self-test to watch each one fire against a synthetic tree.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# Budgets. Each is a tradeoff, not a law — change them, but change them on purpose.
INDEX_MAX_BYTES = 3000          # an index loaded every session; ~750 tokens
INDEX_HARD_LINES = 200          # Claude Code loads only the first 200 lines ...
INDEX_HARD_BYTES = 25_000       # ... or 25KB of MEMORY.md; the rest is invisible
INDEX_LINE_MAX_CHARS = 200      # a hook, not the finding
GLOBAL_MAX_LINES = 60           # loaded into every session in every repo
ROOT_CLAUDE_MAX_LINES = 300     # past this, it gets skimmed
FOLDER_CLAUDE_MAX_LINES = 60    # a folder file carries local invariants only
MEMORY_FILE_MAX_BYTES = 4000    # one fact; longer means several facts

SKIP_DIRS = {"node_modules", ".git", ".next", "dist", "build", ".venv", "venv",
             "__pycache__", ".turbo", "coverage", ".claude"}

BACKTICK_PATH = re.compile(r"`([A-Za-z0-9_./\-]+/[A-Za-z0-9_.\-]+\.[A-Za-z0-9]{1,6})`")
INDEX_LINK = re.compile(r"\]\(([^)]+\.md)\)")
# Lowercase only, and not possessive: "Today's Signal" is a feature name, "decided today" is rot.
DATE_WORDS = re.compile(r"\b(today|yesterday|tomorrow|last week|next week|this week)\b(?!'s)")
CURRENT_CLAIM = re.compile(r"\b(ACTIVE DIRECTION|NORTH STAR|CURRENT DIRECTION|SOURCE OF TRUTH|LEAD CANDIDATE|ACTIVE)\b")
PROJECT_SMELLS =re.compile(r"(npm run |pnpm |yarn |/src/|src/|app/api|supabase|prisma|manage\.py|\.tsx?\b|migrations/)", re.I)


@dataclass
class Report:
    findings: list[dict] = field(default_factory=list)

    def add(self, level: str, check: str, where: str, msg: str) -> None:
        self.findings.append({"level": level, "check": check, "where": where, "msg": msg})

    @property
    def failed(self) -> bool:
        return any(f["level"] == "FAIL" for f in self.findings)


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out: dict[str, str] = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^\s*([A-Za-z_]+)\s*:\s*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"')
    return out


def rule_paths(text: str) -> list[str]:
    """The `paths:` globs of a .claude/rules file, inline or as a YAML list."""
    if not text.startswith("---"):
        return []
    block = text[3:text.find("\n---", 3)] if text.find("\n---", 3) != -1 else ""
    out: list[str] = []
    in_paths = False
    for line in block.splitlines():
        m = re.match(r"^paths\s*:\s*(.*)$", line)
        if m:
            in_paths = True
            inline = m.group(1).strip().strip("[]")
            out += [g.strip().strip("\"'") for g in inline.split(",") if g.strip()]
            continue
        if in_paths:
            item = re.match(r"^\s+-\s*(.+)$", line)
            if item:
                out.append(item.group(1).strip().strip("\"'"))
            elif line.strip():
                in_paths = False
    return out


# ---------------------------------------------------------------- auto-memory

def check_memory_dir(mem: Path, r: Report) -> None:
    index = mem / "MEMORY.md"
    files = sorted(p for p in mem.glob("*.md") if p.name != "MEMORY.md")
    if not index.exists():
        if files:
            r.add("FAIL", "index-missing", str(mem), f"{len(files)} memory files but no MEMORY.md index — none of them will be found")
        return

    text = read(index)
    size = len(text.encode("utf-8"))
    nlines = len(text.splitlines())
    if nlines > INDEX_HARD_LINES or size > INDEX_HARD_BYTES:
        r.add("FAIL", "index-truncated", str(index),
              f"{nlines} lines / {size} bytes — past {INDEX_HARD_LINES} lines or {INDEX_HARD_BYTES} bytes the harness stops reading; later entries are never seen")
    if size > INDEX_MAX_BYTES:
        r.add("WARN", "index-budget", str(index),
              f"{size} bytes (~{size // 4} tokens) loaded every session; budget {INDEX_MAX_BYTES}. Shorten hooks or consolidate")
    for i, line in enumerate(text.splitlines(), 1):
        if len(line) > INDEX_LINE_MAX_CHARS:
            r.add("WARN", "index-line-length", f"{index}:{i}",
                  f"{len(line)} chars — the finding belongs in the file, the index carries only a hook")

    targets = [Path(t).name for t in INDEX_LINK.findall(text)]
    for name in sorted({t for t in targets if targets.count(t) > 1}):
        r.add("WARN", "index-duplicate", str(index), f"{name} is indexed {targets.count(name)} times — the hooks will drift apart")
    linked = set(targets)
    for name in sorted(linked):
        if not (mem / name).exists():
            r.add("FAIL", "index-dead-link", str(index), f"points at {name}, which does not exist")
    for f in files:
        if f.name not in linked:
            r.add("FAIL", "memory-orphan", str(f), "not linked from MEMORY.md — invisible to every future session")

    names: dict[str, str] = {}
    for f in files:
        body = read(f)
        fm = frontmatter(body)
        for key in ("name", "description"):
            if not fm.get(key):
                r.add("FAIL", "memory-frontmatter", str(f), f"missing `{key}` in frontmatter")
        mtype = fm.get("type") or ""
        if not mtype:
            m = re.search(r"^\s+type:\s*(\w+)", body, re.M)
            mtype = m.group(1) if m else ""
        if mtype not in {"user", "feedback", "project", "reference"}:
            r.add("WARN", "memory-type", str(f), f"type is '{mtype or 'missing'}' — expected user|feedback|project|reference")
        # Feedback only: a project memory that records a measured result carries its own
        # evidence, and demanding a Why there flagged most of a healthy store (tested 2026-09-26).
        if mtype == "feedback" and not re.search(r"\*\*Why", body):
            r.add("WARN", "memory-why", str(f), "feedback memory with no **Why:** — the rule can't be applied to an edge case")
        if len(body.encode("utf-8")) > MEMORY_FILE_MAX_BYTES:
            r.add("WARN", "memory-size", str(f), f"{len(body.encode('utf-8'))} bytes — probably several facts; split or move to a repo doc")
        if DATE_WORDS.search(body):
            r.add("WARN", "memory-relative-date", str(f), f"relative date '{DATE_WORDS.search(body).group(0)}' — rot on read; use an absolute date")
        n = fm.get("name")
        if n:
            if n in names:
                r.add("FAIL", "memory-duplicate-name", str(f), f"name '{n}' also used by {names[n]}")
            names[n] = f.name

    # Several files each claiming to be the live direction is the commonest cause of
    # re-work: each session picks a different one. Uppercase markers only, to stay quiet
    # on prose that merely uses the words.
    # Read the index too: in practice the claim usually lives in the hook, not the file.
    claimants = {f.name for f in files if CURRENT_CLAIM.search(read(f))}
    for line in text.splitlines():
        link = INDEX_LINK.search(line)
        if link and CURRENT_CLAIM.search(line):
            claimants.add(Path(link.group(1)).name)
    claimants = sorted(claimants)
    if len(claimants) > 1:
        r.add("WARN", "competing-current", str(mem),
              f"{len(claimants)} files claim to be the current direction ({', '.join(claimants[:6])}) — keep one, demote the rest to dated history")

    all_names = set(names) | {f.stem for f in files}
    for f in files:
        for target in re.findall(r"\[\[([^\]]+)\]\]", read(f)):
            if target not in all_names:
                r.add("WARN", "memory-dangling-link", str(f), f"[[{target}]] has no memory yet (fine if intended as a to-write marker)")


# ---------------------------------------------------------------- global file

def check_global(path: Path, r: Report) -> None:
    if not path.exists():
        return
    text = read(path)
    lines = text.splitlines()
    if len(lines) > GLOBAL_MAX_LINES:
        r.add("WARN", "global-budget", str(path), f"{len(lines)} lines loaded into every session in every repo; budget {GLOBAL_MAX_LINES}")
    for i, line in enumerate(lines, 1):
        if PROJECT_SMELLS.search(line) and not line.lstrip().startswith(">"):
            r.add("WARN", "global-project-leak", f"{path}:{i}",
                  "looks project-specific — it will leak into unrelated repos: " + line.strip()[:90])
    for m in re.finditer(r"\b(move|migrate|todo|pending)\b.{0,80}", text, re.I):
        r.add("WARN", "global-stale-action", str(path),
              f"an instruction to do something once is sitting in a file read forever: '{m.group(0)[:80]}'")


# ---------------------------------------------------------------- repo files

def walk_md(repo: Path):
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in files:
            if f.endswith(".md"):
                yield Path(root) / f


def git_tracked(repo: Path) -> set[str] | None:
    try:
        out = subprocess.run(["git", "-C", str(repo), "ls-files"], capture_output=True, text=True, check=True).stdout
        return {line.strip() for line in out.splitlines()}
    except Exception as e:  # not a repo, or git missing — say so rather than guess
        print(f"note: git ls-files unavailable ({e.__class__.__name__}); tracking checks skipped", file=sys.stderr)
        return None


def check_repo(repo: Path, r: Report) -> None:
    root_files = [repo / n for n in ("CLAUDE.md", "AGENTS.md") if (repo / n).exists()]
    if not root_files:
        r.add("WARN", "root-missing", str(repo), "no CLAUDE.md or AGENTS.md — a memoryless agent starts from nothing")

    rules = repo / ".claude" / "rules"
    if rules.is_dir():
        for f in rules.rglob("*.md"):
            fm_text = read(f)
            globs = rule_paths(fm_text)
            if not globs:
                r.add("WARN", "rule-unscoped", f.relative_to(repo).as_posix(),
                      "no `paths:` — loads at startup in every session; scope it or move it to CLAUDE.md on purpose")
            for g in globs:
                if not list(repo.glob(g.strip())):
                    r.add("FAIL", "rule-dead-scope", f.relative_to(repo).as_posix(),
                          f"paths glob '{g.strip()}' matches no file — this rule can never load")

    tracked = git_tracked(repo)
    for md in walk_md(repo):
        rel = md.relative_to(repo).as_posix()
        text = read(md)
        is_agent_file = md.name in {"CLAUDE.md", "AGENTS.md"}
        if is_agent_file:
            n = len(text.splitlines())
            limit = ROOT_CLAUDE_MAX_LINES if md.parent == repo else FOLDER_CLAUDE_MAX_LINES
            if n > limit:
                r.add("WARN", "agent-file-size", rel, f"{n} lines; budget {limit}. Move how-to and history out; keep rules that change a decision")
            if tracked is not None and rel not in tracked:
                r.add("WARN", "agent-file-untracked", rel, "not tracked in git — teammates and clean clones never see it")

        # The walk test: every backticked path in an agent-facing file must resolve.
        if is_agent_file or md.name in {"CONTEXT.md", "README.md"}:
            fm = frontmatter(text)
            strict = fm.get("status", "live") != "historical"
            for target in set(BACKTICK_PATH.findall(text)):
                if any(ch in target for ch in "*<>{}"):
                    continue
                candidates = [md.parent / target, repo / target]
                if not any(c.exists() for c in candidates):
                    level = "FAIL" if strict and md.name != "README.md" else "WARN"
                    r.add(level, "walk-test", rel,
                          f"`{target}` does not resolve (backticks mean 'follow this'; write it bare if it is a name, not a pointer)")


# ---------------------------------------------------------------- self-test

def self_test() -> int:
    """Build a tree with one planted defect per check, and confirm each fires."""
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        repo, mem = t / "repo", t / "mem"
        (repo / "sub").mkdir(parents=True)
        mem.mkdir()
        (repo / "CLAUDE.md").write_text("Start at `src/missing.ts`.\n", encoding="utf-8")
        (repo / "sub" / "CLAUDE.md").write_text("\n".join(["rule"] * (FOLDER_CLAUDE_MAX_LINES + 5)), encoding="utf-8")
        (mem / "MEMORY.md").write_text("- [A](a.md) — " + "x" * 250 + "\n- [Gone](gone.md) — hook\n- [A again](a.md) — hook\n", encoding="utf-8")
        (mem / "a.md").write_text("---\nname: a\ndescription: d\nmetadata:\n  type: feedback\n---\nNORTH STAR: do X, decided today. [[nope]]\n", encoding="utf-8")
        (mem / "b.md").write_text("---\nname: b\ndescription: d\nmetadata:\n  type: project\n---\nACTIVE DIRECTION: do Y.\n", encoding="utf-8")
        (mem / "orphan.md").write_text("---\nname: a\n---\nbody\n", encoding="utf-8")
        (repo / ".claude" / "rules").mkdir(parents=True)
        (repo / ".claude" / "rules" / "api.md").write_text('---\npaths:\n  - "nowhere/**/*.ts"\n---\nrule\n', encoding="utf-8")
        (repo / ".claude" / "rules" / "all.md").write_text("rule with no scope\n", encoding="utf-8")
        big = t / "big"
        big.mkdir()
        (big / "MEMORY.md").write_text("\n".join("- [x](x.md) — h" for _ in range(205)), encoding="utf-8")
        noindex = t / "noindex"
        noindex.mkdir()
        (noindex / "lost.md").write_text("---\nname: lost\n---\n" + "y" * (MEMORY_FILE_MAX_BYTES + 1), encoding="utf-8")
        bare = t / "bare"
        bare.mkdir()
        g = t / "GLOBAL.md"
        g.write_text("Run `npm run dev` in src/app.\nTODO: move this file.\n", encoding="utf-8")

        r = Report()
        check_memory_dir(mem, r)
        check_memory_dir(big, r)
        check_memory_dir(noindex, r)
        (noindex / "MEMORY.md").write_text("- [Lost](lost.md) — h\n", encoding="utf-8")
        check_memory_dir(noindex, r)
        check_global(g, r)
        check_repo(repo, r)
        check_repo(bare, r)
        fired = {f["check"] for f in r.findings}
        expected = {"index-line-length", "index-dead-link", "memory-orphan", "memory-frontmatter",
                    "memory-why", "memory-relative-date", "memory-duplicate-name", "memory-dangling-link",
                    "global-project-leak", "global-stale-action", "agent-file-size", "walk-test",
                    "index-truncated", "rule-dead-scope", "rule-unscoped", "index-budget",
                    "memory-type", "index-missing", "memory-size", "root-missing",
                    "index-duplicate", "competing-current"}
        missing = expected - fired
        for c in sorted(expected):
            print(f"{'ok  ' if c in fired else 'MISS'} {c}")
        if missing:
            print(f"\nself-test FAILED: {len(missing)} check(s) never fired", file=sys.stderr)
            return 1
        print(f"\nself-test passed: all {len(expected)} planted defects detected")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", type=Path)
    ap.add_argument("--memory-dir", type=Path)
    ap.add_argument("--global-file", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if a.self_test:
        return self_test()
    if not (a.repo or a.memory_dir or a.global_file):
        ap.error("give at least one of --repo, --memory-dir, --global-file")

    r = Report()
    if a.global_file:
        check_global(a.global_file.expanduser(), r)
    if a.memory_dir:
        check_memory_dir(a.memory_dir.expanduser(), r)
    if a.repo:
        check_repo(a.repo.expanduser().resolve(), r)

    if a.json:
        print(json.dumps(r.findings, indent=2))
    else:
        for level in ("FAIL", "WARN"):
            rows = [f for f in r.findings if f["level"] == level]
            if rows:
                print(f"\n{level} ({len(rows)})")
                for f in rows:
                    print(f"  [{f['check']}] {f['where']}\n      {f['msg']}")
        fails = sum(f["level"] == "FAIL" for f in r.findings)
        warns = sum(f["level"] == "WARN" for f in r.findings)
        print(f"\n{fails} FAIL, {warns} WARN")
    return 1 if r.failed else 0


if __name__ == "__main__":
    sys.exit(main())
