"""
check_privacy.py — proves what PRIVACY.md says about the audit script by reading its code:

  - it imports nothing that can reach the network, in any form (`import json, socket`,
    `from urllib import ...`, `__import__`, importlib);
  - it runs no program but git, and only git's read-only commands (`init` and `update-index`
    are allowed in the self-test, which builds a throwaway repository);
  - it writes files only in --draft-index and in the self-test.

A grep for `import socket` missed the first three forms above; this reads the syntax tree.
Run with --self-test to watch each rule fire on a planted snippet.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "skills" / "memory-architecture" / "scripts" / "audit_memory.py"

NETWORK = {"socket", "ssl", "urllib", "urllib3", "http", "requests", "httpx", "aiohttp", "ftplib", "smtplib",
           "poplib", "imaplib", "telnetlib", "xmlrpc", "asyncio", "webbrowser", "importlib", "ctypes",
           "multiprocessing", "socketserver", "selectors"}
GIT_READ = {"ls-files", "check-ignore"}
GIT_SELF_TEST = {"init", "update-index"}
WRITERS = {"write_text", "write_bytes", "mkdir", "unlink", "rmdir", "rename", "touch", "symlink_to", "hardlink_to"}
OS_WRITERS = {"remove", "unlink", "rmdir", "removedirs", "rename", "renames", "replace", "makedirs", "mkdir",
              "system", "popen", "truncate", "symlink", "link", "chmod", "chown"}
BANNED_CALLS = {"__import__", "eval", "exec", "compile"}


def allowed_to_write(stack: list[str]) -> bool:
    return any(f == "draft_index" or f.startswith("self_test") for f in stack)


def in_self_test(stack: list[str]) -> bool:
    return any(f.startswith("self_test") for f in stack)


def write_mode(call: ast.Call, index: int) -> bool:
    """True unless the call's mode is a constant with no w, a, x or +."""
    mode = call.args[index] if len(call.args) > index else next((k.value for k in call.keywords if k.arg == "mode"), None)
    if mode is None:
        return False
    return not (isinstance(mode, ast.Constant) and isinstance(mode.value, str) and not set(mode.value) & set("wax+"))


class Guard(ast.NodeVisitor):
    def __init__(self) -> None:
        self.stack: list[str] = []
        self.problems: list[str] = []

    def bad(self, node: ast.AST, msg: str) -> None:
        self.problems.append(f"line {getattr(node, 'lineno', '?')}: {msg}")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Import(self, node: ast.Import) -> None:
        for a in node.names:
            if a.name.split(".")[0] in NETWORK:
                self.bad(node, f"imports {a.name}, which can reach the network")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = (node.module or "").split(".")[0]
        if mod in NETWORK:
            self.bad(node, f"imports from {node.module}, which can reach the network")
        elif mod in {"subprocess", "os", "shutil"}:
            self.bad(node, f"imports names from {mod}; call {mod}.<name> so this check can see it")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        f = node.func
        name = f.id if isinstance(f, ast.Name) else None
        owner = f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else None
        attr = f.attr if isinstance(f, ast.Attribute) else None
        if name in BANNED_CALLS:
            self.bad(node, f"calls {name}(), which can run or import anything")
        if owner == "importlib":
            self.bad(node, "imports a module by name at run time")
        if owner == "subprocess":
            first = node.args[0] if node.args else None
            if not (isinstance(first, ast.List) and first.elts and isinstance(first.elts[0], ast.Constant)
                    and first.elts[0].value == "git"):
                self.bad(node, f"subprocess.{attr} runs something that isn't visibly git")
        if name == "git":
            sub = node.args[1] if len(node.args) > 1 else None
            cmd = sub.value if isinstance(sub, ast.Constant) and isinstance(sub.value, str) else None
            if cmd in GIT_SELF_TEST and in_self_test(self.stack):
                pass
            elif cmd not in GIT_READ:
                self.bad(node, f"runs `git {cmd or '<computed>'}`; only {', '.join(sorted(GIT_READ))} are read-only here")
        writes = ((name == "open" and write_mode(node, 1))
                  or (attr == "open" and write_mode(node, 0))
                  or attr in WRITERS
                  or (owner == "os" and attr in OS_WRITERS)
                  or owner in {"shutil", "tempfile"})
        if writes and not (owner == "os" and attr in {"system", "popen"}) and not allowed_to_write(self.stack):
            self.bad(node, f"writes to disk ({ast.unparse(node.func)}) outside --draft-index and the self-test")
        if owner == "os" and attr in {"system", "popen"}:
            self.bad(node, f"os.{attr} runs a shell command")
        self.generic_visit(node)


def problems(source: str) -> list[str]:
    g = Guard()
    g.visit(ast.parse(source))
    return g.problems


def self_test() -> int:
    planted = {
        "import-in-a-list": "import json, socket\n",
        "from-import": "from urllib.request import urlopen\n",
        "dunder-import": "x = __import__('socket')\n",
        "importlib": "import importlib\n",
        "subprocess-curl": "import subprocess\nsubprocess.run(['curl', 'https://example.com'])\n",
        "subprocess-computed": "import subprocess\ncmd = ['git']\nsubprocess.run(cmd)\n",
        "from-subprocess": "from subprocess import run\n",
        "git-push": "def check(r):\n    git(r, 'push')\n",
        "git-computed": "def check(r, c):\n    git(r, c)\n",
        "git-init-outside-self-test": "def check(r):\n    git(r, 'init')\n",
        "os-system": "import os\nos.system('ls')\n",
        "open-for-write": "def check(p):\n    open(p, 'w')\n",
        "open-computed-mode": "def check(p, m):\n    open(p, m)\n",
        "path-write-text": "def check(p):\n    p.write_text('x')\n",
        "tempdir-outside-self-test": "import tempfile\ndef check():\n    tempfile.mkdtemp()\n",
        "module-level-write": "open('x', 'a')\n",
    }
    clean = ("import os, re, subprocess, tempfile\n"
             "def git(repo, *a):\n    return subprocess.run(['git', '-C', str(repo), *a])\n"
             "def check(r):\n    git(r, 'ls-files', '-z')\n    git(r, 'check-ignore')\n    open(r)\n    open(r, 'r', encoding='utf-8')\n"
             "    'a'.replace('a', 'b')\n    os.walk(r)\n"
             "def draft_index(p, force):\n    open(p, 'w' if force else 'x')\n"
             "def self_test():\n    git(r, 'init')\n    p.write_text('x')\n    tempfile.TemporaryDirectory()\n"
             "    (lambda: p.mkdir())()\n")
    failed = 0
    for label, src in planted.items():
        hit = bool(problems(src))
        print(f"{'ok  ' if hit else 'MISS'} {label}")
        failed += not hit
    quiet = problems(clean)
    print(f"{'ok  ' if not quiet else 'FAIL'} allowed-patterns-quiet" + (f": {quiet}" if quiet else ""))
    failed += bool(quiet)
    if failed:
        print(f"\ncheck_privacy self-test FAILED: {failed} case(s)", file=sys.stderr)
        return 1
    print(f"\ncheck_privacy self-test passed: {len(planted)} planted breaches caught, allowed patterns quiet")
    return 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return self_test()
    found = problems(SCRIPT.read_text(encoding="utf-8"))
    for p in found:
        print(f"FAIL {SCRIPT.name} {p}")
    if found:
        print("\nPRIVACY.md says the script is read-only and offline; the code above says otherwise.", file=sys.stderr)
        return 1
    print(f"ok   {SCRIPT.name}: no network imports, only read-only git, writes only in --draft-index and the self-test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
