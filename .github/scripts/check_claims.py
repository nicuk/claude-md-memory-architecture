"""
check_claims.py — the facts this repo states about itself, checked against their sources, so a
number typed into prose can't drift from what it describes:

  - every "N checks" in README.md, plugin.json and the demo equals the checks the script reports;
  - the README's with/without-skill percentages equal the published results in evals/evals.json;
  - the fixture's expected audit output in evals/README.md is what the audit prints on a fresh build;
  - plugin.json's version heads CHANGELOG.md;
  - no tracked file holds an absolute path from someone's machine;
  - no root `hooks/` or `agents/` folder exists: the plugin ships from the root, so they would run
    in every installer's sessions. Shipping one is a product decision: change this check with it.

Run with --self-test to watch each matcher fire on a planted case.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "memory-architecture" / "scripts" / "audit_memory.py"
COUNT_CLAIM = re.compile(r"\b(\d+)\s+(?:self-tested\s+|planted\s+)?(?:checks|planted defects)\b")
SHARE_CLAIM = re.compile(r"passed (\d+)% of the checks against (\d+)%")
FIXTURE_CLAIM = re.compile(r"\((\d+) FAIL, (\d+) WARN\)")
SHIPPED_TO_USERS = ("hooks", "agents")
HOME_PATH = re.compile(r"(?:/Users/[A-Za-z]|/home/[a-z][\w.-]*/|\b[A-Za-z]:\\Users\\)")


def count_mismatches(text: str, n: int) -> list[str]:
    return [m.group(0) for m in COUNT_CLAIM.finditer(text) if int(m.group(1)) != n]


def home_paths(text: str) -> list[str]:
    return [m.group(0) for m in HOME_PATH.finditer(text)]


def check_names() -> list[str]:
    sys.path.insert(0, str(SCRIPT.parent))
    import audit_memory
    return audit_memory.check_names()


def main() -> int:
    bad: list[str] = []
    n = len(check_names())
    for rel in ("README.md", ".claude-plugin/plugin.json", "assets/audit-demo.svg"):
        for claim in count_mismatches((ROOT / rel).read_text(encoding="utf-8"), n):
            bad.append(f"{rel}: says '{claim}', but the script reports {n} checks")

    overall = json.loads((ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))["published_results"]["overall"]
    pub = tuple(re.search(r"\((\d+)%\)", overall[k]).group(1) for k in ("with_skill", "without_skill"))
    for m in SHARE_CLAIM.finditer((ROOT / "README.md").read_text(encoding="utf-8")):
        if m.groups() != pub:
            bad.append(f"README.md: says {m.group(1)}% vs {m.group(2)}%, evals.json publishes {pub[0]}% vs {pub[1]}%")

    claim = FIXTURE_CLAIM.search((ROOT / "evals" / "README.md").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as t:
        subprocess.run([sys.executable, str(ROOT / "evals" / "build_fixture.py"), t], check=True, capture_output=True)
        out = subprocess.run([sys.executable, str(SCRIPT), "--memory-dir", str(Path(t) / "forecast-memory")],
                             capture_output=True, text=True).stdout
    got = re.search(r"(\d+) FAIL, (\d+) WARN\s*$", out)
    if not claim or not got or claim.groups() != got.groups():
        bad.append(f"evals/README.md: says {claim.group(0) if claim else 'nothing'}, a fresh fixture gives "
                   f"{got.group(0) if got else 'no summary'}")

    version = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    head = next((ln for ln in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").splitlines() if ln.startswith("## ")), "")
    if not head.startswith(f"## {version} "):
        bad.append(f"CHANGELOG.md: newest entry is '{head}', plugin.json says {version}")

    tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, text=True, check=True).stdout
    for rel in filter(None, tracked.split("\0")):
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue                                   # binary, a submodule or folder link, or deleted
        for hit in home_paths(text):
            bad.append(f"{rel}: holds an absolute path from someone's machine ('{hit}...')")

    for folder in SHIPPED_TO_USERS:
        if (ROOT / folder).exists():
            bad.append(f"{folder}/ exists at the root, so it ships to everyone who installs the plugin; "
                       "put this repo's own hooks and agents in .claude/")

    for b in bad:
        print("FAIL " + b)
    if not bad:
        print(f"ok   {n} checks as stated, eval results and fixture output match, "
              f"version {version} heads the changelog, no personal paths, nothing shipped by accident")
    return 1 if bad else 0


def self_test() -> int:
    cases = [
        ("count-drift-caught", count_mismatches("runs 22 checks; all 22 planted defects; 22 self-tested checks", 25) != []),
        ("count-match-quiet", count_mismatches("runs 25 checks; all 25 planted defects detected", 25) == []),
        ("unrelated-numbers-quiet", count_mismatches("a 0-10 score, 26 cases, 200 lines", 25) == []),
        # Assembled from pieces, so this file holds no path the check itself would flag.
        ("mac-path-caught", bool(home_paths("see /" + "Users/alice/repo/x.md"))),
        ("linux-path-caught", bool(home_paths("cloned to /" + "home/bob/work"))),
        ("windows-path-caught", bool(home_paths("C:" + "\\Users\\carol\\repo"))),
        ("generic-paths-quiet", not home_paths("~/.claude/CLAUDE.md, /tmp/memory-fixture, src/app/main.ts, /home/")),
        ("share-matched", SHARE_CLAIM.search("answers with the skill passed 93% of the checks against 71% without") is not None),
        ("fixture-claim-matched", FIXTURE_CLAIM.search("lines (1 FAIL, 38 WARN).") is not None),
    ]
    for name, ok in cases:
        print(f"{'ok  ' if ok else 'FAIL'} {name}")
    failed = [c for c, ok in cases if not ok]
    if failed:
        print(f"\ncheck_claims self-test FAILED: {len(failed)} case(s)", file=sys.stderr)
        return 1
    print(f"\ncheck_claims self-test passed: all {len(cases)} cases held")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv[1:] else main())
