#!/usr/bin/env python3
"""
audit_memory.py — deterministic checks for an agent memory system.

Checks only things a script can decide. Judgement calls (is this fact in the
right layer? is it still true?) stay with the agent reading the report.

Usage:
  python audit_memory.py --project PATH [--json] [--strict]
  python audit_memory.py --repo PATH [--memory-dir PATH] [--global-file PATH] [--json] [--strict]
  python audit_memory.py --repo PATH --census
  python audit_memory.py --memory-dir PATH --draft-index [--force]

--project audits the repo at PATH, its Claude Code memory folder and the global
CLAUDE.md, finding the folders itself (it lists ~/.claude/projects to do so).

Every check prints FAIL (a breach), WARN (worth a look) or nothing. Exit code
is 1 if any FAIL (or, with --strict, any WARN), else 0. A check that has never
failed has never been tested: run with --self-test to watch each one fire
against a synthetic tree. The self-test reads the check names from this file,
so a check without a planted defect fails it.

The audit only reads. The one exception is --draft-index, which writes a
proposed trimmed index to <memory-dir>/MEMORY.draft.md and nothing else: one
hook-length line per memory file, in the index's order, orphans appended,
duplicates and dead links dropped. It never touches MEMORY.md and refuses to
overwrite an existing draft unless --force is given. A human reviews the draft
and replaces MEMORY.md with it by hand.
"""
from __future__ import annotations

import argparse
import ast
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
# A folder file carries local invariants only. This was 60 until 2026-09-27, when an audit of
# four public repositories flagged well-built folder files at 65 to 89 lines (local rules plus
# the commands for that package) and the one clearly bloated folder file was 320 lines. At 60
# the warning was mostly noise; 100 still catches the bloated case.
FOLDER_CLAUDE_MAX_LINES = 100
MEMORY_FILE_MAX_BYTES = 4000    # one fact; longer means several facts
DRAFT_LINE_MAX_CHARS = 150      # --draft-index: a hook is what it is and when it matters
DRAFT_TITLE_MAX_CHARS = 60      # --draft-index: leaves most of the line for the hook
DRAFT_NAME = "MEMORY.draft.md"  # the only file this script ever writes outside --self-test

# What Claude Code reads under .claude/. Not its worktrees: `.claude/worktrees/` holds whole copies of the repo.
DOT_CLAUDE_DIRS = {"rules", "agents", "commands", "skills", "output-styles"}
SKIP_DIRS = {"node_modules", ".git", ".next", "dist", "build", ".venv", "venv",
             "__pycache__", ".turbo", "coverage", ".claude"}

BACKTICK_PATH = re.compile(r"`([A-Za-z0-9_./\-]+/[A-Za-z0-9_.\-]+\.[A-Za-z0-9]{1,6})`")
# Claude Code's `@path` import. Needs a file extension, so an npm scope (`@types/node`) or a
# handle (`@alice`) isn't taken for one; the lookbehind skips e-mail addresses.
AT_IMPORT = re.compile(r"(?<![\w@/.`])@((?:\.{1,2}/)*[A-Za-z0-9_\-][A-Za-z0-9_./\-]*\.[A-Za-z0-9]{1,6})(?![\w/])")
MD_LINK = re.compile(r"!?\[[^\]\n]*\]\(\s*<?([^()\s<>]+)>?(?:\s+[\"'][^\"'\n]*[\"'])?\s*\)")
FENCE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$", re.M | re.S)
CODE_SPAN = re.compile(r"`[^`\n]*`")
# Walk-test targets that aren't pointers into the repo. Each class was a false FAIL on real repos.
PLACEHOLDER_HEAD = re.compile(r"^[A-Z][A-Z0-9_]*[A-Z0-9]$")   # `OUT_DIR/x.rs`: a variable, not a folder
HOME_DIRS = {".local", ".config", ".cache", ".ssh", ".aws", ".kube", ".docker", ".npm", ".cargo", ".gnupg"}
CREATE_WORDS = re.compile(r"\b(?:creat(?:e|es|ed|ing)|generat(?:e|es|ed|ing)|produc(?:e|es|ed|ing)|outputs?|"
                          r"emits?|will write|writes? (?:it |them )?(?:to|into))\b", re.I)
UNSCOPED_GLOBS = {"**", "**/*", "/**", "./**", "**/**"}
GLOB_ALTERNATIVES_MAX = 256     # a brace pattern that expands past this is reported, not evaluated
INDEX_LINK = re.compile(r"\]\(([^)]+\.md)\)")
# Lowercase only, and not possessive: "Today's Signal" is a feature name, "decided today" is rot.
DATE_WORDS = re.compile(r"\b(today|yesterday|tomorrow|last week|next week|this week)\b(?!'s)")
# A rule in a `binding` doc says what enforces it, or says that nothing does.
ENFORCER_MARK = re.compile(r"enforced by|not enforced|\(intent\b", re.I)
# "## Rules", "## Hard rules", "### Git rules": a section of rules, not a title that mentions them.
RULES_HEADING = re.compile(r"^#{2,6}\s+(?:[\w'-]+\s+){0,2}rules?\s*:?\s*$", re.I)
CURRENT_CLAIM = re.compile(r"\b(ACTIVE DIRECTION|NORTH STAR|CURRENT DIRECTION|SOURCE OF TRUTH|LEAD CANDIDATE|ACTIVE)\b")
PROJECT_SMELLS =re.compile(r"(npm run |pnpm |yarn |/src/|src/|app/api|supabase|prisma|manage\.py|\.tsx?\b|migrations/)", re.I)


@dataclass
class Report:
    findings: list[dict] = field(default_factory=list)

    def add(self, level: str, check: str, where: str, msg: str) -> None:
        if check not in check_names():
            raise ValueError(f"check '{check}' isn't a literal name in an .add() call, so the self-test can't count it")
        self.findings.append({"level": level, "check": check, "where": where, "msg": msg})

    @property
    def failed(self) -> bool:
        return any(f["level"] == "FAIL" for f in self.findings)


_CHECK_NAMES: list[str] = []


def check_names() -> list[str]:
    """Every check this script can report: the literal name in each `.add(level, "name", ...)` call,
    read from this file's syntax tree, so the self-test can't miss one. Report.add refuses any other."""
    if not _CHECK_NAMES:
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        _CHECK_NAMES.extend(sorted({n.args[1].value for n in ast.walk(tree)
                                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                                    and n.func.attr == "add" and len(n.args) >= 2
                                    and isinstance(n.args[1], ast.Constant) and isinstance(n.args[1].value, str)}))
    return _CHECK_NAMES


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


def memory_files(mem: Path) -> list[Path]:
    """Memory topic files: every .md in the folder except the index and a pending draft of it."""
    return sorted(p for p in mem.glob("*.md") if p.name not in {"MEMORY.md", DRAFT_NAME})


def split_top(inline: str) -> list[str]:
    """Split an inline YAML list on the commas that separate items, not those inside {a,b} or quotes."""
    items, cur, depth, quote = [], "", 0, ""
    for ch in inline:
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch in "{}":
            depth += 1 if ch == "{" else -1
        elif ch == "," and depth <= 0:
            items.append(cur)
            cur = ""
            continue
        cur += ch
    return items + [cur]


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
            out += [g.strip().strip("\"'") for g in split_top(m.group(1).strip().strip("[]")) if g.strip()]
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
    files = memory_files(mem)
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


# ---------------------------------------------------------------- finding a project's memory

def claude_home() -> Path:
    """Claude Code's config folder: $CLAUDE_CONFIG_DIR if set, else ~/.claude."""
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()


def main_checkout(repo: Path) -> Path:
    """The main checkout a worktree belongs to, read from its `.git` file: all worktrees of one
    repo share one memory folder, keyed to the main checkout. Any other folder is its own."""
    dot_git = repo / ".git"
    if dot_git.is_file():
        m = re.match(r"gitdir:\s*(.+)", read(dot_git).strip())
        if m:
            gitdir = Path(m.group(1).strip())
            gitdir = gitdir if gitdir.is_absolute() else (repo / gitdir).resolve()
            if gitdir.parent.name == "worktrees":        # <main>/.git/worktrees/<name>
                return gitdir.parent.parent.parent
    return repo


def find_memory_dir(repo: Path, projects: Path) -> tuple[Path | None, str]:
    """The auto-memory folder Claude Code keeps for `repo`: projects/<path with every character
    that isn't a letter or digit turned into ->/memory. If the exact name isn't there, a folder
    whose name matches once punctuation is ignored is accepted when it is the only one."""
    root = main_checkout(repo)
    name = re.sub(r"[^A-Za-z0-9]", "-", str(root))
    exact = projects / name / "memory"
    if exact.is_dir():
        return exact, f"{exact}"
    key = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())
    near = [d / "memory" for d in (projects.iterdir() if projects.is_dir() else [])
            if key(d.name) == key(name) and (d / "memory").is_dir()]
    if len(near) == 1:
        return near[0], f"{near[0]} (the closest match to {name})"
    why = f"{len(near)} folders match" if near else "none exists yet: Claude Code creates it the first time it saves a memory"
    return None, f"no memory folder for {root} under {projects} ({why}); pass --memory-dir to name one"


# ---------------------------------------------------------------- draft index

INDEX_ENTRY = re.compile(r"\[([^\]]*)\]\(([^)]+\.md)\)")
ANY_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def shorten(text: str, limit: int) -> str:
    """Collapse whitespace; if still over `limit` chars, cut at a word boundary and add an ellipsis."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:max(limit - 1, 0)]
    space = cut.rfind(" ")
    if space > limit // 2:          # a boundary that still keeps most of the text
        cut = cut[:space]
    return cut.rstrip(" ,;:.-–—(") + "…"


def description_of(body: str) -> str:
    """The `description` frontmatter value, including a YAML folded/literal block (`>` or `|`)."""
    desc = frontmatter(body).get("description", "").strip("'")
    if desc not in {">", "|", ">-", "|-", ">+", "|+"}:
        return desc
    block = body[3:body.find("\n---", 3)].splitlines()
    for i, line in enumerate(block):
        if re.match(r"^\s*description\s*:", line):
            rest = []
            for more in block[i + 1:]:
                if more.strip() and not more[:1].isspace():
                    break
                rest.append(more.strip())
            return " ".join(x for x in rest if x)
    return ""


def draft_line(name: str, title: str, hook: str) -> str:
    title = shorten(title.replace("[", "(").replace("]", ")"), DRAFT_TITLE_MAX_CHARS) or Path(name).stem
    prefix = f"- [{title}]({name})"
    room = DRAFT_LINE_MAX_CHARS - len(prefix) - 3     # 3 = " — "
    hook = shorten(hook, room) if room >= 10 else ""  # a very long file name leaves no room for a hook
    return f"{prefix} — {hook}" if hook else prefix


def build_draft(mem: Path) -> tuple[str, dict]:
    """A trimmed index: the index's headings and order, one hook-length line per memory file,
    duplicates and dead links dropped, orphans appended at the end."""
    index = mem / "MEMORY.md"
    text = read(index) if index.exists() else ""
    files = {p.name: p for p in memory_files(mem)}
    items: list[tuple[str, str]] = []   # ("head", line) or ("entry", file name)
    titles: dict[str, str] = {}
    index_hooks: dict[str, str] = {}
    st = {"on_disk": len(files), "duplicates": 0, "dead": 0}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            items.append(("head", line.strip()))
            continue
        entries = list(INDEX_ENTRY.finditer(line))
        for i, m in enumerate(entries):
            name = Path(m.group(2)).name
            if name not in files:
                st["dead"] += 1
                continue
            if name in titles:
                st["duplicates"] += 1
                continue
            end = entries[i + 1].start() if i + 1 < len(entries) else len(line)
            titles[name] = m.group(1).strip()
            index_hooks[name] = ANY_LINK.sub(r"\1", line[m.end():end]).strip(" \t-:|–—")
            items.append(("entry", name))
    st["indexed"] = len(titles)
    orphans = [n for n in files if n not in titles]
    st["orphans"] = len(orphans)
    indexed_items = len(items)          # headings are judged on indexed entries only, so orphans
    items += [("entry", n) for n in orphans]   # land at the end under no heading of their own

    out: list[str] = []
    for i, (kind, val) in enumerate(items):
        if kind == "head":
            # Keep a heading only if an entry follows before the next heading at its level or above.
            level = len(val) - len(val.lstrip("#"))
            for kind2, val2 in items[i + 1:indexed_items]:
                if kind2 == "entry":
                    out.append(val)
                    break
                if len(val2) - len(val2.lstrip("#")) <= level:
                    break
            continue
        body = read(files[val])
        hook = description_of(body) or index_hooks.get(val, "")
        title = titles.get(val) or frontmatter(body).get("name") or Path(val).stem
        out.append(draft_line(val, title, hook))
    st["linked"] = sum(k == "entry" for k, _ in items)
    return "".join(line + "\n" for line in out), st


def draft_index(mem: Path, force: bool = False, log=print) -> int:
    """Write <mem>/MEMORY.draft.md, the only file this script writes. MEMORY.md is never opened for writing."""
    if not mem.is_dir():
        log(f"--draft-index: {mem} is not a folder")
        return 2
    index, out = mem / "MEMORY.md", mem / DRAFT_NAME
    draft, st = build_draft(mem)
    if not st["on_disk"]:
        log(f"--draft-index: no memory files in {mem}; nothing to index")
        return 2
    try:
        # "x" creates or fails atomically, so a draft someone is reviewing is never clobbered.
        with open(out, "w" if force else "x", encoding="utf-8", newline="\n") as fh:
            fh.write(draft)
    except FileExistsError:
        log(f"refusing: {out} already exists. Review or delete it, or pass --force to overwrite it.")
        return 1

    def size(label: str, b: int, n: int) -> str:
        return f"{label} {b:>7,} bytes, {n:>4} lines, ~{b // 4:,} tokens (~ estimate: bytes/4)"

    before = index.read_bytes() if index.exists() else b""
    after = draft.encode("utf-8")
    nb, na = len(before.decode("utf-8", "replace").splitlines()), len(draft.splitlines())
    log(size("before  MEMORY.md      ", len(before), nb))
    log(size("after   MEMORY.draft.md", len(after), na))
    log(f"memories: {st['on_disk']} on disk, {st['indexed']} linked before, {st['linked']} linked in the draft "
        f"(orphans appended: {st['orphans']}, duplicate entries dropped: {st['duplicates']}, "
        f"dead links dropped: {st['dead']})")
    within = len(after) <= INDEX_MAX_BYTES
    cap = na <= INDEX_HARD_LINES and len(after) <= INDEX_HARD_BYTES
    log(f"draft is {'within' if within else 'OVER'} the {INDEX_MAX_BYTES:,}-byte index budget, and "
        f"{'within' if cap else 'PAST'} the {INDEX_HARD_LINES}-line / {INDEX_HARD_BYTES:,}-byte load cap")
    longest = max((len(line) for line in draft.splitlines()), default=0)
    if longest > DRAFT_LINE_MAX_CHARS:
        log(f"note: longest line is {longest} chars; a long title or file name leaves no room to trim further")
    if not within and st["linked"]:
        log(f"trimming hooks alone can't fit {st['linked']} memories in {INDEX_MAX_BYTES:,} bytes "
            f"(~{INDEX_MAX_BYTES // st['linked']} bytes a line). Merge related memories, or move a cluster "
            f"into a repo doc behind one router line.")
    log(f"wrote {out}\nMEMORY.md was not changed. Review the draft, then replace MEMORY.md with it yourself.")
    return 0


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

def md_files(repo: Path) -> list[Path]:
    """Every markdown file an agent might read: dependency and build folders, nested repositories and
    worktrees are skipped, and so are dot-folders, except the agent-facing parts of `.claude/`."""
    out: list[Path] = []
    dot = repo / ".claude"
    for root, dirs, files in os.walk(repo):
        here = Path(root)
        if here == dot:
            dirs[:] = sorted(d for d in dirs if d in DOT_CLAUDE_DIRS)
        elif dot in here.parents:             # a rule or skill folder may be called build or dist
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and not (here / d / ".git").exists())
        else:
            dirs[:] = sorted(d for d in dirs if ((d == ".claude" and here == repo)
                             or (d not in SKIP_DIRS and not d.startswith("."))) and not (here / d / ".git").exists())
        out += [Path(root) / f for f in sorted(files) if f.endswith(".md")]
    return out


def skill_dirs(docs: list[Path]) -> list[Path]:
    """Folders holding a SKILL.md: a skill, and everything it ships with it. Deepest first."""
    return sorted({d.parent for d in docs if d.name == "SKILL.md"}, key=lambda p: -len(p.parts))


def bundle_of(md: Path, bundles: list[Path], repo: Path) -> Path | None:
    """The skill folder a file ships in. A SKILL.md at the repo root covers only itself: the rest of
    the repo keeps its own rules rather than all becoming one skill."""
    b = next((b for b in bundles if b == md.parent or b in md.parents), None)
    return None if b == repo and md.name != "SKILL.md" else b


def coverage(repo: Path, md: Path, bundles: list[Path]) -> str | None:
    """How the walk test covers one markdown file: 'agent' (every pointer; a dead one FAILs),
    'dot' (an agent, command or skill under `.claude/`; every pointer, a dead one WARNs),
    'backticks' (backticked paths only), 'bundle' (a skill's markdown links; its backticked
    paths usually name files in the repo it is used on) or None (not agent-facing)."""
    parts = md.relative_to(repo).parts
    if md.name in {"CLAUDE.md", "AGENTS.md"} or parts[:2] == (".claude", "rules"):
        return "agent"
    if parts[0] == ".claude":
        return "dot"
    if bundle_of(md, bundles, repo):
        return "bundle"
    if md.name in {"CONTEXT.md", "README.md"}:
        return "backticks"
    return None


CENSUS_LABEL = {"agent": "walked: every pointer; a dead one FAILs",
                "dot": "walked: every pointer; a dead one WARNs",
                "backticks": "walked: backticked paths",
                "bundle": "skill: markdown links must resolve"}


def census(repo: Path) -> list[tuple[str, str]]:
    """Every markdown file under `repo` and how the walk test covers it, so no document is
    covered or skipped without anyone being able to see which."""
    docs = md_files(repo)
    bundles = skill_dirs(docs)
    out = []
    for md in docs:
        mode = coverage(repo, md, bundles)
        label = CENSUS_LABEL[mode] if mode else "not checked"
        if mode == "dot" and bundle_of(md, bundles, repo):
            label = "walked: a dead link FAILs (a skill), other dead pointers WARN"
        if mode and frontmatter(read(md)).get("status") == "historical":
            label += " (historical, so WARN only)"
        out.append((md.relative_to(repo).as_posix(), label))
    return out


def unmarked_rules(text: str) -> list[tuple[int, str]]:
    """(line, rule) for each list item under a Rules heading that neither names its enforcer
    ("Enforced by ...") nor says it has none ("not enforced", "(intent")."""
    out: list[tuple[int, str]] = []
    cur: list | None = None
    in_rules = fence = False

    def flush() -> None:
        nonlocal cur
        if cur and not ENFORCER_MARK.search(cur[1]):
            out.append((cur[0], " ".join(cur[1].split())))
        cur = None
    for i, line in enumerate(text.splitlines(), 1):
        if re.match(r"^\s*(```|~~~)", line):
            flush()
            fence = not fence
            continue
        if fence:
            continue
        if re.match(r"^#{1,6}\s", line):
            flush()
            in_rules = bool(RULES_HEADING.match(line))
        elif in_rules and re.match(r"^(?:[-*+]|\d+[.)])\s+\S", line):
            flush()
            cur = [i, line]
        elif cur is not None and line[:1] in (" ", "\t") and line.strip():
            cur[1] += " " + line.strip()
        else:
            flush()
    flush()
    return out


def git(repo: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    """Run a read-only git command in `repo`. GIT_* variables are dropped: set by a git hook, they
    would point the command at the repository the hook runs in instead of the one named here."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, input=stdin,
                          encoding="utf-8", errors="replace", env=env, timeout=120)


def git_tracked(repo: Path) -> set[str] | None:
    try:
        p = git(repo, "ls-files", "-z")
        if p.returncode:
            raise RuntimeError(p.stderr.strip())
        return {x for x in p.stdout.split("\0") if x}
    except Exception as e:  # not a repo, or git missing — say so rather than guess
        print(f"note: git ls-files unavailable ({e.__class__.__name__}); tracking checks skipped", file=sys.stderr)
        return None


def git_ignored(repo: Path, paths) -> set[str]:
    """Which of these repo-relative paths .gitignore excludes. They needn't exist: a build output
    is ignored before it is built. Empty, with a note, if git can't say."""
    paths = sorted({p for p in paths if p and p != ".." and not p.startswith("../")})
    if not paths:
        return set()
    try:
        p = git(repo, "check-ignore", "-z", "--no-index", "--stdin", stdin="\0".join(paths) + "\0")
        why = "" if p.returncode in (0, 1) else p.stderr.strip()[:100]      # 1 means none is ignored
    except Exception as e:
        why = e.__class__.__name__
    if why:
        print(f"note: git check-ignore unavailable ({why}); gitignored paths are not recognised", file=sys.stderr)
        return set()
    return {x for x in p.stdout.split("\0") if x}


def disk_files(repo: Path) -> list[str]:
    """Every file under `repo`, tracked or not, as repo-relative posix paths."""
    out: list[str] = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules"}]
        base = Path(root).relative_to(repo).as_posix()
        out += [f if base == "." else f"{base}/{f}" for f in files]
    return out


# ------------------------------------------------ path-scoped rules

def expand_braces(glob: str) -> list[str]:
    """The `{a,b}` alternatives of a glob, nested and repeated braces included."""
    m = re.search(r"\{([^{}]*)\}", glob)
    if not m:
        return [glob]
    out: list[str] = []
    for alt in m.group(1).split(","):
        out += expand_braces(glob[:m.start()] + alt + glob[m.end():])
        if len(out) > GLOB_ALTERNATIVES_MAX:
            raise ValueError(f"expands to more than {GLOB_ALTERNATIVES_MAX} alternatives")
    return out


def glob_regex(glob: str) -> re.Pattern:
    """A brace-free `paths:` glob as a regex over repo-relative paths. `**` crosses folders, `*` and
    `?` stay inside one, and a glob with no `/` matches a file name at any depth. Raises ValueError
    (or re.error) on a glob it can't read, so the caller reports it instead of crashing."""
    g = glob.strip()
    g = g[2:] if g.startswith("./") else g
    g = g.lstrip("/")
    if not g or "{" in g or "}" in g:
        raise ValueError("unbalanced brace" if g else "empty glob")
    out, i = [], 0
    while i < len(g):
        if g.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif g.startswith("**", i):
            out.append(".*")
            i += 2
        elif g[i] in "*?":
            out.append("[^/]*" if g[i] == "*" else "[^/]")
            i += 1
        elif g[i] == "[":
            j = g.find("]", i + 2)
            if j == -1:
                raise ValueError("unclosed [")
            body = g[i + 1:j]
            out.append("[" + ("^" + body[1:] if body.startswith("!") else body).replace("\\", "\\\\") + "]")
            i = j + 1
        else:
            out.append(re.escape(g[i]))
            i += 1
    rx = "".join(out)
    if "/" not in g.rstrip("/"):
        rx = "(?:.*/)?" + rx
    if g.endswith("/"):
        rx += ".*"
    return re.compile(rx)


def glob_probe(glob: str) -> str:
    """One concrete path a brace-free glob would match, to ask git whether such paths are ignored."""
    g = glob.strip()
    g = (g[2:] if g.startswith("./") else g).lstrip("/").replace("**/", "").replace("**", "x")
    g = re.sub(r"\[[^\]]*\]", "x", g).replace("*", "x").replace("?", "x")
    return g + "x" if not g or g.endswith("/") else g


def check_rules(repo: Path, tracked: set[str] | None, r: Report) -> None:
    rules = repo / ".claude" / "rules"
    if not rules.is_dir():
        return
    known = sorted(tracked) if tracked is not None else None
    disk: list[str] | None = None
    for f in sorted(rules.rglob("*.md")):
        rel = f.relative_to(repo).as_posix()
        globs = [g.strip() for g in rule_paths(read(f)) if g.strip()]
        if not globs:
            r.add("WARN", "rule-unscoped", rel,
                  "no `paths:` — loads at startup in every session; scope it or move it to CLAUDE.md on purpose")
            continue
        wide = [g for g in globs if g in UNSCOPED_GLOBS]
        if wide:
            r.add("WARN", "rule-unscoped", rel, f"paths '{wide[0]}' matches every file, so this rule loads as soon as "
                  "any file is read, like an unscoped one; scope it or move it to CLAUDE.md on purpose")
            continue
        # Each glob, and each {a,b} alternative in it, is judged on its own. The rule is dead only
        # when every alternative of every glob matches nothing, tracked or on disk.
        status: dict[tuple[str, str], str] = {}
        unreadable = False
        for g in globs:
            try:
                pats = [(a, glob_regex(a)) for a in expand_braces(g)]
            except (ValueError, re.error) as e:
                unreadable = True
                r.add("WARN", "rule-dead-scope", rel, f"paths glob '{g}' can't be read ({e}); check by hand that it matches files")
                continue
            for a, rx in pats:
                if known is not None and any(rx.fullmatch(p) for p in known):
                    status[(g, a)] = "live"
                    continue
                if disk is None:
                    disk = disk_files(repo)
                on_disk = any(rx.fullmatch(p) for p in disk)
                # Without git, files on disk are all there is. With it, a file only on disk is
                # untracked or ignored: a clean clone doesn't have it.
                status[(g, a)] = ("live" if on_disk else "dead") if known is None else ("local" if on_disk else "dead")
        dead = [k for k, s in status.items() if s == "dead"]
        if dead and known is not None:
            # A glob aimed at gitignored files (`**/*.tfvars`) matches nothing in a clean clone but does
            # on a machine that has them. That's a scope to look at, not a rule that can never load.
            ignored = git_ignored(repo, [glob_probe(a) for _, a in dead])
            for k in dead:
                if glob_probe(k[1]) in ignored:
                    status[k] = "ignored"
        live = [k for k, s in status.items() if s == "live"]
        aside = [a for (_, a), s in status.items() if s in ("local", "ignored")]
        if live:
            for g, a in (k for k, s in status.items() if s == "dead"):
                what = f"paths glob '{g}'" if a == g else f"alternative '{a}' of paths glob '{g}'"
                r.add("WARN", "rule-dead-scope", rel,
                      f"{what} matches nothing; the rule still loads through its other paths. Fix it or drop it")
        elif aside:
            r.add("WARN", "rule-dead-scope", rel, f"paths match only untracked or gitignored files ({', '.join(aside[:3])}), "
                  "so this rule never loads in a clean clone")
        elif status and not unreadable:
            r.add("FAIL", "rule-dead-scope", rel,
                  f"no paths glob matches any file ({', '.join(repr(g) for g in globs)}) — this rule can never load")


# ------------------------------------------------ the walk test

def sentence_at(text: str, start: int, end: int) -> str:
    """The sentence (within its line) around text[start:end]."""
    a = text.rfind("\n", 0, start) + 1
    b = text.find("\n", end)
    line = text[a:len(text) if b == -1 else b]
    cut = re.sub(r"\b(e\.g|i\.e|etc|vs|cf)\. ", lambda m: m.group(0)[:-2] + "_ ", line)   # not sentence ends
    s, e = start - a, end - a
    head = max(cut.rfind(p, 0, s) for p in (". ", "! ", "? "))
    tails = [i for i in (cut.find(p, e) for p in (". ", "! ", "? ")) if i != -1]
    return line[0 if head == -1 else head + 2:min(tails) + 1 if tails else len(line)]


def pointers(text: str, agent: bool) -> list[tuple[str, str, str]]:
    """(kind, target, sentence) for each pointer: backticked paths always; in agent files also
    `@path` imports and relative markdown links, outside code blocks and code spans."""
    found = [("backtick", m.group(1), sentence_at(text, m.start(), m.end())) for m in BACKTICK_PATH.finditer(text)]
    if agent:
        blank = lambda m: re.sub(r"[^\n]", " ", m.group(0))      # keeps offsets, so sentences line up
        prose = CODE_SPAN.sub(blank, FENCE.sub(blank, text))
        for kind, rx in (("import", AT_IMPORT), ("link", MD_LINK)):
            found += [(kind, m.group(1), sentence_at(text, m.start(), m.end())) for m in rx.finditer(prose)]
    return found


def walk_target(raw: str, kind: str) -> str | None:
    """The repo path a pointer names, or None when it names something else."""
    t = raw.strip()
    if kind == "link":
        if re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*:", t) or t.startswith(("#", "//")):
            return None                           # a URL, another scheme, or an anchor on this page
        t = re.sub(r"%([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), t.split("#", 1)[0].split("?", 1)[0])
    if not t or "..." in t or "…" in t or any(ch in t for ch in "*<>{}$~"):
        return None                               # `docs/.../x.md` abbreviates; `<id>.md` is a template
    return t if t.startswith("./") else t.lstrip("/")


def walk_candidates(repo: Path, md: Path, t: str) -> list[str]:
    """Where a pointer may lead, as repo-relative paths: from the file's folder, then from the root."""
    out: list[str] = []
    for base in (md.parent, repo):
        rel = os.path.relpath(os.path.normpath(os.path.join(base, t)), repo).replace(os.sep, "/")
        if rel != ".." and not rel.startswith("../") and rel not in out:
            out.append(rel)
    return out


WALK_MSG = {
    "backtick": "`{t}` does not resolve (backticks mean 'follow this'; write it bare if it is a name, not a pointer)",
    "import": "`@{t}` import does not resolve — Claude Code skips a missing import without a word",
    "link": "link to `{t}` does not resolve",
}


def check_repo(repo: Path, r: Report) -> None:
    roots = [repo / "CLAUDE.md", repo / "AGENTS.md", repo / ".claude" / "CLAUDE.md"]
    if not any(p.exists() for p in roots):
        r.add("WARN", "root-missing", str(repo), "no CLAUDE.md, AGENTS.md or .claude/CLAUDE.md — a memoryless agent starts from nothing")

    tracked = git_tracked(repo)
    check_rules(repo, tracked, r)
    tracked_dirs = {f.rsplit("/", i)[0] for f in (tracked or ()) for i in range(1, f.count("/") + 1)}

    docs = md_files(repo)
    bundles = skill_dirs(docs)
    pending: list[tuple[str, str, str, str, list[str], list[str]]] = []
    for md in docs:
        mode = coverage(repo, md, bundles)
        if mode is None:
            continue
        rel = md.relative_to(repo).as_posix()
        text = read(md)
        if md.name in {"CLAUDE.md", "AGENTS.md"}:
            n = len(text.splitlines())
            limit = ROOT_CLAUDE_MAX_LINES if md.parent in (repo, repo / ".claude") else FOLDER_CLAUDE_MAX_LINES
            if n > limit:
                r.add("WARN", "agent-file-size", rel, f"{n} lines; budget {limit}. Move how-to and history out; keep rules that change a decision")
            if tracked is not None and rel not in tracked:
                r.add("WARN", "agent-file-untracked", rel, "not tracked in git — teammates and clean clones never see it")

        fm = frontmatter(text)
        strict = fm.get("status", "live") != "historical"
        if mode in ("agent", "dot") and strict and fm.get("authority") == "binding":
            for line_no, rule in unmarked_rules(text):
                r.add("WARN", "rule-unenforced", f"{rel}:{line_no}",
                      f"binding rule names no enforcer: '{rule[:90]}'. Add 'Enforced by `<check>`', or say '(intent, not enforced)'")

        # The walk test: every pointer in an agent-facing file must resolve.
        level = "WARN" if mode == "dot" or not strict or md.name == "README.md" else "FAIL"
        bundle = bundle_of(md, bundles, repo)
        sentences: dict[tuple[str, str], list[str]] = {}
        for kind, raw, sentence in pointers(text, mode != "backticks"):
            t = walk_target(raw, kind)
            # `@` imports are a CLAUDE.md feature: in an agent or skill, `@jane.smith` is a person.
            if t is not None and not (kind == "import" and mode in ("dot", "bundle")):
                sentences.setdefault((kind, t), []).append(sentence)
        for (kind, t), said in sentences.items():
            head = re.sub(r"^(\.\.?/)+", "", t).split("/", 1)[0]
            placeholder = PLACEHOLDER_HEAD.match(head) and not (repo / head).exists() and not (md.parent / head).exists()
            if bundle and kind == "link" and not placeholder:
                # A skill ships its folder as is: a dead link in it breaks the skill for everyone who installs it.
                found = next((base / t for base in (md.parent, bundle) if (base / t).exists()), None)
                where = f"the skill's folder `{bundle.relative_to(repo).as_posix()}/`"
                blevel = "WARN" if not strict or md.name == "README.md" else "FAIL"
                if found is None and not any(CREATE_WORDS.search(x) for x in said):
                    r.add(blevel, "walk-test", rel, WALK_MSG[kind].format(t=t) + f" from {where}; the skill ships broken")
                elif found is not None and tracked is not None:
                    # Installers get what git tracks, not what is on this machine.
                    target = os.path.relpath(os.path.normpath(found), repo).replace(os.sep, "/")
                    if target not in tracked and target not in tracked_dirs:
                        r.add(blevel, "walk-test", rel, f"link to `{t}` resolves here, but `{target}` isn't tracked "
                              f"in git, so the skill ships without it")
                continue
            if mode == "bundle":
                # Backticked paths in a skill were examples or the user's files, not links: 27 of 27 on
                # Claude Code's own plugin-dev skills (2026-09-27). `@` imports are a CLAUDE.md feature,
                # and `@john.doe` in a skill is a person. Links are checked above.
                continue
            if placeholder or (head in HOME_DIRS and not (repo / head).exists() and not (md.parent / head).exists()):
                continue                          # `~/.config/x` quoted without the ~, or `OUT_DIR/x.rs`
            cands = walk_candidates(repo, md, t)
            if cands and not any((repo / c).exists() or c in (tracked or ()) or c in tracked_dirs for c in cands):
                pending.append((level, rel, kind, t, cands, said))

    # Resolved in one batch: a pointer into a gitignored path names a build output, and a pointer that
    # only a longer tracked path ends with is followable, just not from here.
    ignored = git_ignored(repo, [c for p in pending for c in p[4]]) if pending and tracked is not None else set()
    files = sorted(tracked) if tracked is not None else (disk_files(repo) if pending else [])
    for level, rel, kind, t, cands, said in pending:
        if any(c in ignored for c in cands):
            continue
        lead = re.match(r"^(?:\.\.?/)*", t).group(0)
        tail = t[len(lead):]
        here = Path(rel).parent.as_posix()
        # `./x` and `../x` point from this file's folder, so only a file under that folder can be meant.
        base = os.path.normpath(os.path.join(here, lead)).replace(os.sep, "/") if lead else "."
        under = lambda f, d: d == "." or f.startswith(d + "/")
        # Nearest first, then the one whose folder the sentence names closest to the pointer
        # ("the `website/` page (e.g. `src/pages/index.astro`)").
        def named(f: str) -> float:
            gaps = [abs(m.start() - x.find(t)) for x in said for seg in f[:len(f) - len(tail)].split("/") if seg
                    for m in re.finditer(rf"(?<![\w-]){re.escape(seg)}(?![\w-])", x.replace(t, " " * len(t)))]
            return min(gaps, default=float("inf"))
        hits = sorted((f for f in files if (f == tail or f.endswith("/" + tail)) and under(f, base)),
                      key=lambda f: (not under(f, here), named(f)))
        if hits:
            more = f" (or {len(hits) - 1} more)" if len(hits) > 1 else ""
            r.add("WARN", "walk-test", rel, f"`{'@' if kind == 'import' else ''}{t}` only resolves as `{hits[0]}`{more}; "
                  "write the full path so an agent can follow it")
        elif not any(CREATE_WORDS.search(x) for x in said):
            # Only a path found nowhere can be one the sentence says to create ("create `x/y.ts`").
            r.add(level, "walk-test", rel, WALK_MSG[kind].format(t=t))


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
        g.write_text("Run `npm run dev` in src/app.\nTODO: move this file.\n" + "- a preference\n" * GLOBAL_MAX_LINES, encoding="utf-8")

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
    repo_cases, repo_fired = self_test_repo()
    fired |= repo_fired
    # Read from this file, not typed here: a new check with no planted defect is a MISS.
    expected = set(check_names())
    missing = expected - fired
    for c in sorted(expected):
        print(f"{'ok  ' if c in fired else 'MISS'} {c}")
    broken = []
    for label, cases in (("--draft-index", self_test_draft()), ("--repo", repo_cases), ("--project", self_test_project())):
        print()
        for name, ok, detail in cases:
            print(f"{'ok  ' if ok else 'FAIL'} {name}" + ("" if ok else f": {detail}"))
        broken += [c for c in cases if not c[1]]
        if not any(not c[1] for c in cases):
            print(f"{label}: all {len(cases)} cases held")
    if missing or broken:
        print(f"\nself-test FAILED: {len(missing)} check(s) never fired, {len(broken)} case(s) failed",
              file=sys.stderr)
        return 1
    print()
    print(f"self-test passed: all {len(expected)} planted defects detected")
    return 0


def self_test_repo() -> tuple[list[tuple[str, bool, str]], set[str]]:
    """Plant, in a throwaway git repository, each false-alarm class that real repositories produced,
    next to the real defect it resembles, and check each lands where it should: FAIL, WARN or nothing.
    Also returns the names of the checks that fired, for the self-test's coverage count."""
    def rule(*globs: str, body: str = "rule\n") -> str:
        return "---\npaths:\n" + "".join(f"  - {g}\n" for g in globs) + "---\n" + body
    files = {
        ".gitignore": "*.tfvars\nout/\n",
        "src/app/main.ts": "", "docs/guide.md": "", "infra/main.tf": "", "pkg/client/src/settings/tips.ts": "", "pkg/client/src/log.ts": "",
        "admin/src/pages/index.astro": "", "web/src/pages/index.astro": "", "native/lib/shim.c": "",
        "app/CLAUDE.md": "- The **admin** console is separate; the **web** landing page (e.g. `src/pages/index.astro`) is static.\n",
        ".claude/CLAUDE.md": "Start in `src/app/main.ts`, never in `src/app/gone_root.ts`.\n",   # the only root file
        "sub/CLAUDE.md": "- a local rule\n" * 89,
        ".claude/rules/brace-dead.md": rule('"{mobile/ios/**,mobile/android/**}"'),
        ".claude/rules/brace-partial.md": rule('"{src/**,website/**}"'),
        ".claude/rules/brace-live.md": rule('"{src,docs}/**"', '"pkg/*/src/**"'),
        ".claude/rules/inline.md": '---\npaths: ["{src,docs}/**", "pkg/**"]\n---\nrule\n',
        ".claude/rules/ignored.md": rule('"**/*.tfvars"'),
        ".claude/rules/terraform.md": rule("'**/*.tf'", "'**/*.tfvars'"),
        ".claude/rules/local.md": rule('"scratch/**"'),
        ".claude/rules/unreadable.md": rule('"src/[app/**"'),
        ".claude/rules/everything.md": rule('"**"'),
        ".claude/rules/body.md": rule('"src/**"', body="Edit `src/app/body_gone.ts` with care.\n"),
        "docs/AGENTS.md": "\n".join([
            "- Abbreviated: the page is `docs/.../guide.md`.",
            "- Placeholder: the build reads `OUT_DIR/detected.rs` at compile time.",
            "- Rooted: the entry point is `/src/app/main.ts`; the old one was `/src/app/rooted_gone.ts`.",
            "- Ignored: the bundle is `out/bundle.js` after a build.",
            "- Short: tips live in `settings/tips.ts` for the client.",
            "- Local: the logger is `./log.ts`, next to this file.",
            "- To add a handler, create `src/app/new_module.ts` first.",
            "- The build compiles `lib/shim.c` and emits a binary.",
            "- Dead: the router is `src/app/really_gone.ts`.",
            "- Imports: @docs/guide.md and @docs/missing_import.md, but not `@docs/in_code.md`.",
            "- Links: [guide](docs/guide.md), [top](#top), [site](https://example.com/gone.md), [old](old_notes.md).",
            "- Mail dev@example.com with questions.",
            "```", "@docs/in_fence.md", "```", ""]),
        # A plugin skill: links into its own folder must resolve; its other paths name the user's files.
        ".claude-plugin/plugin.json": "{}\n",
        "skills/demo/SKILL.md": "---\nname: demo\n---\nRead [the guide](references/guide.md), then [the rest](references/lost.md) "
                                "and [my notes](references/local-only.md). "
                                "In your repo, edit `.claude/settings.json` and `docs/X.md`; "
                                "a finance skill would keep `references/finance.md`. See [the docs](URL), or ask @john.doe.\n",
        "skills/demo/references/guide.md": "Run [the tool](../scripts/tool.py), not [this one](../scripts/missing.py).\n",
        "skills/demo/scripts/tool.py": "",
        # Agents, commands and skills under .claude/ describe this repo, so every pointer is walked.
        ".claude/agents/reviewer.md": "Review against `src/app/main.ts` and `src/app/agent_gone.ts`. Ask @jane.smith first.\n",
        ".claude/skills/local/SKILL.md": "Use [tips](notes/tips.md) and [more](notes/missing.md) here, then `src/app/local_gone.ts`.\n",
        ".claude/skills/local/notes/tips.md": "",
        # A worktree Claude Code made: a copy of the repo, not more docs to audit.
        ".claude/worktrees/feature/CLAUDE.md": "Start at `src/app/worktree_gone.ts`.\n",
        # A repository nested inside this one audits itself.
        "vendor/lib/CLAUDE.md": "Start at `src/app/nested_gone.ts`.\n",
        "vendor/lib/.git": "gitdir: elsewhere\n",
        # A binding doc: each rule names its enforcer or says it has none.
        "binding/AGENTS.md": "\n".join([
            "---", "authority: binding", "status: live", "---", "## Rules",
            "- Never edit an applied migration. Enforced by `src/app/main.ts`.",
            "- Keep billing frozen", "  until the audit ends.",
            "- Use uv (intent, not enforced).", "", "## Notes", "- a note, not a rule",
            "# Team rules", "- an intro, not a rule", "## Where the rules live", "- in the rules folder", ""]),
        # Folders called build under .claude/ are rules and skills, not build output.
        ".claude/rules/build/deep.md": '---\npaths:\n  - "src/**"\n---\nSee `src/app/build_rule_gone.ts`.\n',
        ".claude/skills/build/SKILL.md": "Read [the steps](steps_absent.md).\n",
    }
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "repo"
        for name, body in files.items():
            (p / name).parent.mkdir(parents=True, exist_ok=True)
            (p / name).write_text(body, encoding="utf-8")
        (p / "scratch").mkdir()
        (p / "scratch" / "notes.txt").write_text("", encoding="utf-8")    # on disk, never added, not ignored
        (p / "scratch" / "CLAUDE.md").write_text("- local rule\n", encoding="utf-8")   # an agent file never added
        (p / "skills" / "demo" / "references" / "local-only.md").write_text("", encoding="utf-8")   # linked, never added
        try:
            ok = git(p, "init", "-q").returncode == 0
            # --info-only indexes the files without writing git objects: nothing but the index to clean up.
            ok = ok and git(p, "update-index", "--add", "--info-only", "--", *files).returncode == 0
        except OSError:
            ok = False
        if not ok:
            return [("repo-cases-need-git", False, "git init / update-index failed; these cases need git on PATH")], set()
        r = Report()
        try:
            check_repo(p, r)
            crash = ""
        except Exception as e:
            crash = f"{e.__class__.__name__}: {e}"
        cen = dict(census(p))
        # A single-skill repo: SKILL.md at the root covers only itself.
        solo = Path(t) / "solo"
        for name, body in {"SKILL.md": "Read [the guide](gone_root_skill.md).\n",
                           "README.md": "Start in `src/solo_nope.ts`.\n",
                           "docs/history.md": "Old: [notes](removed_history.md).\n"}.items():
            (solo / name).parent.mkdir(parents=True, exist_ok=True)
            (solo / name).write_text(body, encoding="utf-8")
        rs = Report()
        check_repo(solo, rs)
    fs = r.findings

    def at(where: str, check: str = "", level: str = "", text: str = "") -> list[dict]:
        return [f for f in fs if f["where"] == where and (not check or f["check"] == check)
                and (not level or f["level"] == level) and text in f["msg"]]

    def said(text: str) -> list[dict]:
        return [f for f in fs if text in f["msg"]]
    try:
        unknown = "-".join(["no", "such", "check"])        # not a literal, or it would count as a check
        Report().add("WARN", unknown, "x", "a name the self-test can't count")
        refused_unknown = False
    except ValueError:
        refused_unknown = True
    rules = ".claude/rules/"
    only_warn = lambda w: bool(at(rules + w, "rule-dead-scope", "WARN")) and not at(rules + w, level="FAIL")
    return [
        ("glob-never-crashes", not crash, crash),
        ("brace-all-dead-fails", bool(at(rules + "brace-dead.md", "rule-dead-scope", "FAIL", "mobile/ios")), "no FAIL"),
        ("brace-partly-dead-warns", only_warn("brace-partial.md") and bool(at(rules + "brace-partial.md", text="'website/**'")),
         str(at(rules + "brace-partial.md"))),
        ("brace-live-quiet", not at(rules + "brace-live.md"), str(at(rules + "brace-live.md"))),
        ("inline-brace-list-parsed", not at(rules + "inline.md"), str(at(rules + "inline.md"))),
        ("gitignored-glob-warns", only_warn("ignored.md"), str(at(rules + "ignored.md"))),
        ("untracked-match-warns", only_warn("local.md"), str(at(rules + "local.md"))),
        ("gitignored-alternative-quiet", not at(rules + "terraform.md"), str(at(rules + "terraform.md"))),
        ("unreadable-glob-warns", bool(at(rules + "unreadable.md", "rule-dead-scope", "WARN", "can't be read"))
         and not at(rules + "unreadable.md", level="FAIL"), str(at(rules + "unreadable.md"))),
        ("star-star-unscoped", bool(at(rules + "everything.md", "rule-unscoped", "WARN")), "no rule-unscoped"),
        ("walk-skips-abbreviation", not said("docs/.../guide.md"), str(said("docs/.../guide.md"))),
        ("walk-skips-placeholder", not said("OUT_DIR"), str(said("OUT_DIR"))),
        ("walk-leading-slash-is-root", not said("src/app/main.ts")
         and bool(at("docs/AGENTS.md", "walk-test", "FAIL", "src/app/rooted_gone.ts")), str(said("rooted_gone"))),
        ("walk-skips-gitignored", not said("out/bundle.js"), str(said("out/bundle.js"))),
        ("walk-suffix-warns", bool(at("docs/AGENTS.md", "walk-test", "WARN", "only resolves as `pkg/client/src/settings/tips.ts`"))
         and not at("docs/AGENTS.md", level="FAIL", text="settings/tips.ts"), str(said("settings/tips.ts"))),
        ("walk-suffix-prefers-named", bool(at("app/CLAUDE.md", "walk-test", "WARN", "only resolves as `web/src/pages/index.astro`")),
         str(at("app/CLAUDE.md"))),
        ("walk-dot-slash-stays-local", bool(at("docs/AGENTS.md", "walk-test", "FAIL", "`./log.ts` does not resolve")),
         str(said("log.ts"))),
        ("walk-skips-create", not said("new_module.ts"), str(said("new_module.ts"))),
        ("walk-create-word-not-a-pass", bool(at("docs/AGENTS.md", "walk-test", "WARN", "only resolves as `native/lib/shim.c`")),
         str(said("shim.c"))),
        ("walk-dead-still-fails", bool(at("docs/AGENTS.md", "walk-test", "FAIL", "src/app/really_gone.ts")), "no FAIL"),
        ("dot-claude-is-root", not [f for f in fs if f["check"] == "root-missing"], "root-missing fired"),
        ("dot-claude-walked", bool(at(".claude/CLAUDE.md", "walk-test", "FAIL", "src/app/gone_root.ts")), "no FAIL"),
        ("rule-body-walked", bool(at(rules + "body.md", "walk-test", "FAIL", "src/app/body_gone.ts")), "no FAIL"),
        ("at-import-walked", bool(at("docs/AGENTS.md", "walk-test", "FAIL", "@docs/missing_import.md"))
         and not said("in_code.md") and not said("in_fence.md") and not said("example.com"), str(said("@"))),
        ("link-walked", bool(at("docs/AGENTS.md", "walk-test", "FAIL", "old_notes.md"))
         and not said("gone.md") and not said("#top"), str(said("link"))),
        ("folder-budget-100", not at("sub/CLAUDE.md", "agent-file-size"), str(at("sub/CLAUDE.md"))),
        ("skill-bundle-dead-fails", bool(at("skills/demo/SKILL.md", "walk-test", "FAIL", "references/lost.md")), str(said("lost.md"))),
        ("skill-bundle-live-quiet", not said("references/guide.md") and not said("scripts/tool.py"), str(said("guide.md"))),
        ("skill-non-links-quiet", not said(".claude/settings.json") and not said("docs/X.md") and not said("finance.md")
         and not said("URL") and not said("john.doe"), str(said("settings.json") + said("finance.md") + said("URL") + said("john"))),
        ("skill-reference-walked", bool(at("skills/demo/references/guide.md", "walk-test", "FAIL", "scripts/missing.py")),
         str(said("missing.py"))),
        ("dot-claude-agent-walked", bool(at(".claude/agents/reviewer.md", "walk-test", "WARN", "agent_gone"))
         and not at(".claude/agents/reviewer.md", level="FAIL"), str(at(".claude/agents/reviewer.md"))),
        ("project-skill-bundle-fails-once", len(said("notes/missing.md")) == 1
         and bool(at(".claude/skills/local/SKILL.md", "walk-test", "FAIL", "notes/missing.md"))
         and bool(at(".claude/skills/local/SKILL.md", "walk-test", "WARN", "local_gone"))
         and not said("notes/tips.md"), str(at(".claude/skills/local/SKILL.md"))),
        ("rule-unenforced-warns", [f["where"] for f in fs if f["check"] == "rule-unenforced"] == ["binding/AGENTS.md:7"]
         and "until the audit ends" in str(said("Keep billing frozen")), str([f for f in fs if f["check"] == "rule-unenforced"])),
        ("unknown-check-name-refused", refused_unknown, "Report.add accepted a name no .add() call spells out"),
        ("skill-link-untracked-fails", bool(at("skills/demo/SKILL.md", "walk-test", "FAIL", "isn't tracked"))
         and "references/local-only.md" in str(said("isn't tracked")), str(said("local-only"))),
        ("dot-claude-no-at-imports", not said("jane.smith"), str(said("jane"))),
        ("rule-heading-strict", not said("an intro") and not said("in the rules folder"), str(said("intro") + said("rules folder"))),
        ("dot-claude-build-folders-walked", bool(at(".claude/rules/build/deep.md", "walk-test", "FAIL", "build_rule_gone"))
         and bool(at(".claude/skills/build/SKILL.md", "walk-test", "FAIL", "steps_absent")) and ".claude/skills/build/SKILL.md" in cen,
         str(said("build_rule_gone") + said("steps_absent"))),
        ("census-matches-severity", "FAILs" in cen.get(".claude/skills/local/SKILL.md", ""), cen.get(".claude/skills/local/SKILL.md", "")),
        ("root-skill-covers-itself",
         sorted((f["level"], f["where"]) for f in rs.findings if f["check"] == "walk-test") == [("FAIL", "SKILL.md"), ("WARN", "README.md")],
         str(rs.findings)),
        ("worktrees-skipped", not said("worktree_gone") and not [f for f in fs if "worktrees" in f["where"]],
         str([f for f in fs if "worktree" in f["where"] + f["msg"]])),
        ("nested-repo-skipped", not said("nested_gone") and not [f for f in fs if f["where"].startswith("vendor/")],
         str([f for f in fs if "vendor" in f["where"]])),
        ("untracked-agent-file-warns", bool(at("scratch/CLAUDE.md", "agent-file-untracked", "WARN")), str(at("scratch/CLAUDE.md"))),
        ("census-classifies", cen.get("skills/demo/SKILL.md", "").startswith("skill")
         and cen.get(".claude/agents/reviewer.md", "").endswith("WARNs")
         and cen.get("docs/AGENTS.md", "").endswith("FAILs") and cen.get("docs/guide.md") == "not checked",
         str({k: v for k, v in cen.items() if k in ("skills/demo/SKILL.md", ".claude/agents/reviewer.md", "docs/guide.md")})),
    ], {f["check"] for f in fs}


def self_test_project() -> list[tuple[str, bool, str]]:
    """Plant a Claude Code config folder and check --project finds each repo's memory folder."""
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        projects = t / "config" / "projects"
        main, other, fresh = t / "code" / "my.app", t / "code" / "other_repo", t / "code" / "fresh"
        for d in (main, other, fresh):
            d.mkdir(parents=True)
        # The main checkout's memory, under Claude Code's name for it.
        (projects / re.sub(r"[^A-Za-z0-9]", "-", str(main)) / "memory").mkdir(parents=True)
        # A worktree of it: its .git file points into the main checkout's .git/worktrees.
        wt = t / "code" / "my.app-feature"
        wt.mkdir()
        (main / ".git" / "worktrees" / "feature").mkdir(parents=True)
        (wt / ".git").write_text(f"gitdir: {main / '.git' / 'worktrees' / 'feature'}\n", encoding="utf-8")
        # A folder named with underscores kept (an older naming), found as the only close match.
        (projects / re.sub(r"[^A-Za-z0-9_]", "-", str(other)) / "memory").mkdir(parents=True)
        found = {name: find_memory_dir(d, projects) for name, d in
                 (("main", main), ("worktree", wt), ("close", other), ("fresh", fresh))}
    want = projects / re.sub(r"[^A-Za-z0-9]", "-", str(main)) / "memory"
    return [
        ("project-finds-memory", found["main"][0] == want, str(found["main"])),
        ("worktree-shares-main-memory", found["worktree"][0] == want, str(found["worktree"])),
        ("close-name-accepted", found["close"][0] is not None and "closest match" in found["close"][1], str(found["close"])),
        ("missing-memory-said", found["fresh"][0] is None and "none exists yet" in found["fresh"][1], str(found["fresh"])),
    ]


def self_test_draft() -> list[tuple[str, bool, str]]:
    """Plant a bloated index (long lines, a duplicate, a dead link, an orphan) and check the draft."""
    # 9-char stride, so a hard cut at the hook's room lands mid-word; the word-boundary check depends
    # on that (a stride that divides the room evenly let a broken shorten() pass, 2026-09-27).
    words = " ".join(f"token{i:03}" for i in range(50))
    fillers = [f"f{i:02}.md" for i in range(1, 11)]
    with tempfile.TemporaryDirectory() as t:
        mem = Path(t) / "mem"
        mem.mkdir()
        def put(name: str, fm: str) -> None:
            (mem / name).write_text(f"---\n{fm}\nmetadata:\n  type: project\n---\nbody\n", encoding="utf-8")
        put("zeta.md", f"name: zeta\ndescription: {words}")
        put("alpha.md", "name: alpha")                                 # no description: hook falls back to the index
        put("mid.md", "name: mid\ndescription: >\n  a folded\n  description")
        for f in fillers:
            put(f, f"name: {f}")                                       # hook comes from its long index line
        put("aa-orphan.md", "name: orphan\ndescription: on disk, never indexed")
        lines = ["# Memory Index",
                 f"- [Zeta](zeta.md) — {words}",
                 f"- [Alpha](alpha.md) — INDEXHOOK {words}",
                 f"- [Zeta again](zeta.md) — {words}",
                 f"- [Mid](mid.md) — {words}"]
        lines += [f"- [Filler {f}]({f}) — {words}" for f in fillers]
        lines += ["## Old", f"- [Gone](gone.md) — {words}"]      # a section left holding only a dead link
        index = mem / "MEMORY.md"
        index.write_text("\n".join(lines) + "\n", encoding="utf-8")
        before, mtime = index.read_bytes(), index.stat().st_mtime_ns
        draft_path = mem / DRAFT_NAME
        quiet = lambda *_: None

        rc1 = draft_index(mem, log=quiet)
        draft = draft_path.read_text(encoding="utf-8") if draft_path.exists() else ""
        draft_lines = draft.splitlines()
        links = [Path(m.group(2)).name for m in INDEX_ENTRY.finditer(draft)]
        on_disk = sorted(p.name for p in memory_files(mem))
        by_name = {Path(m.group(2)).name: line for line in draft_lines for m in [INDEX_ENTRY.search(line)] if m}

        draft_path.write_text("REVIEWED\n", encoding="utf-8")         # a human is part-way through reviewing
        rc2 = draft_index(mem, log=quiet)
        kept = draft_path.read_text(encoding="utf-8")
        rc3 = draft_index(mem, force=True, log=quiet)
        forced = draft_path.read_text(encoding="utf-8")
        r = Report()
        check_memory_dir(mem, r)

        size = len(draft.encode("utf-8"))
        zeta_hook = by_name.get("zeta.md", "").partition(" — ")[2]
        stem = zeta_hook.rstrip("…")
        order = ["zeta.md", "alpha.md", "mid.md"] + fillers + ["aa-orphan.md"]
        return [
            ("draft-under-budget", rc1 == 0 and len(before) > INDEX_MAX_BYTES and size <= INDEX_MAX_BYTES
             and len(draft_lines) <= INDEX_HARD_LINES, f"rc={rc1}, index {len(before)} bytes -> draft {size} bytes"),
            ("draft-line-length", bool(draft_lines) and all(len(x) <= DRAFT_LINE_MAX_CHARS for x in draft_lines),
             f"longest {max((len(x) for x in draft_lines), default=0)} chars"),
            ("draft-links-each-once", sorted(links) == on_disk, f"links {sorted(links)} vs on disk {on_disk}"),
            ("draft-keeps-order", links == order and "## Old" not in draft and draft_lines[:1] == ["# Memory Index"],
             f"got {links}; headings {[x for x in draft_lines if x.startswith('#')]}"),
            ("draft-hook-source", zeta_hook.endswith("…") and words.startswith(stem) and words[len(stem):len(stem) + 1] == " "
             and "INDEXHOOK" in by_name.get("alpha.md", "") and by_name.get("mid.md", "").endswith("a folded description"),
             f"zeta={zeta_hook[-24:]!r} (want a whole-word cut + ellipsis), alpha has index text="
             f"{'INDEXHOOK' in by_name.get('alpha.md', '')}, mid={by_name.get('mid.md', '')[-24:]!r}"),
            ("draft-memory-untouched", index.read_bytes() == before and index.stat().st_mtime_ns == mtime,
             "MEMORY.md changed"),
            ("draft-refuses-overwrite", rc2 != 0 and kept == "REVIEWED\n" and rc3 == 0 and forced != kept,
             f"without --force rc={rc2}, draft kept={kept == 'REVIEWED' + chr(10)}; with --force rc={rc3}"),
            ("draft-not-self-linked", DRAFT_NAME not in forced and forced == draft
             and not any(DRAFT_NAME in f["where"] for f in r.findings),
             "the draft indexed itself, or the audit counted it as a memory"),
        ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", type=Path, help="audit this repo, its Claude Code memory folder and the global "
                    "CLAUDE.md, found automatically")
    ap.add_argument("--repo", type=Path)
    ap.add_argument("--memory-dir", type=Path)
    ap.add_argument("--global-file", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--draft-index", action="store_true",
                    help=f"write a trimmed index to <memory-dir>/{DRAFT_NAME} for review; never touches MEMORY.md")
    ap.add_argument("--force", action="store_true", help=f"with --draft-index: overwrite an existing {DRAFT_NAME}")
    ap.add_argument("--strict", action="store_true", help="exit 1 on any WARN as well as FAIL (for CI)")
    ap.add_argument("--census", action="store_true", help="with --repo: list every markdown file and how the walk test covers it")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if a.self_test:
        return self_test()
    if a.project:
        if a.repo or a.census:
            ap.error("--project already names the repo; use --repo for --census")
        a.repo = a.project
        if not a.memory_dir:
            a.memory_dir, said = find_memory_dir(a.project.expanduser().resolve(), claude_home() / "projects")
            print(f"memory folder: {said}", file=sys.stderr)
        if not a.global_file and (claude_home() / "CLAUDE.md").exists():
            a.global_file = claude_home() / "CLAUDE.md"
        if a.draft_index:
            a.repo = a.global_file = None               # --draft-index works on the memory folder alone
            if not a.memory_dir:
                return 2
    if a.draft_index:
        if not a.memory_dir or a.repo or a.global_file or a.json:
            ap.error("--draft-index takes --memory-dir only (plus --force)")
        return draft_index(a.memory_dir.expanduser(), force=a.force)
    if a.force:
        ap.error("--force only applies to --draft-index")
    if a.census:
        if not a.repo or a.memory_dir or a.global_file or a.json or a.strict:
            ap.error("--census takes --repo only")
        rows = census(a.repo.expanduser().resolve())
        width = max((len(f) for f, _ in rows), default=0)
        for f, how in rows:
            print(f"{f:<{width}}  {how}")
        return 0
    if not (a.repo or a.memory_dir or a.global_file):
        ap.error("give --project, or at least one of --repo, --memory-dir, --global-file")

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
    return 1 if r.failed or (a.strict and r.findings) else 0


if __name__ == "__main__":
    sys.exit(main())
