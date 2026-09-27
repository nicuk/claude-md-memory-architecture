![Cairn](assets/cairn-logo.png)

![CLAUDE.md and agent memory that stays true. Three stones stack into a cairn.](assets/hero.svg)

[![Claude Code plugin](https://img.shields.io/badge/Claude_Code-plugin-E9A23B?style=flat-square)](#install)
[![Self-test](https://img.shields.io/github/actions/workflow/status/nicuk/claude-md-memory-architecture/self-test.yml?branch=main&label=self-test&style=flat-square)](.github/workflows/self-test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-8CC084?style=flat-square)](LICENSE)
[![Privacy: nothing collected](https://img.shields.io/badge/privacy-nothing_collected-C9B79C?style=flat-square)](PRIVACY.md)

**[Install](#install)** · **[What you get](#what-you-get)** · **[The audit script](#the-audit-script)** · **[Privacy](#privacy)**

**Claude forgets everything between sessions, so it re-reads, re-researches and re-decides.
Cairn Memory gives every fact one right place and keeps it from going stale.**

A cairn is a stack of stones left to guide whoever comes next. This is the same idea for
your next Claude Code session.

Most memory setups fail in one of two ways:

- **Too expensive.** Everything goes into `CLAUDE.md` or the memory index, and it loads
  in every session whether it's needed or not. One real memory index was costing about
  2,500 tokens per session before the first message was typed.
- **Quietly false.** A note that was true in June says "next: build X" in September,
  after X was built. Four memories each claim to be "the current direction". Claude
  picks one and confidently redoes work that is already closed.

Cairn Memory is a skill for Claude Code. It fixes both problems and gives you a script
that proves the fix holds:

![The audit script's self-test passes all 22 checks, then an audit of a memory folder finds an orphaned memory, a duplicate index entry and two files each claiming to be the current direction.](assets/audit-demo.svg)

*Real output, from a small made-up memory folder.*

## Built your app with AI agents?

If you built your product with Claude Code, Cursor, Codex, or several of them over a few
months, you have probably seen these problems:

- It undoes a fix you made last week.
- It re-proposes an idea you already rejected.
- Each tool follows different rules, because each one reads a different file.
- Every session starts by re-reading everything, and your usage limit goes faster than the
  work.

None of this means the AI is getting worse. It means your project's memory is scattered,
stale or in the wrong place. Cairn Memory gives every agent **one shared memory**:
`AGENTS.md` is read by Claude Code, Cursor and Codex. It also records what has already
been decided, so settled questions stay settled.

You don't need to know where any of these files live. Ask in plain words:

- *"Why does Claude keep redoing things we already decided?"*
- *"Set up memory for this project so every AI tool follows the same rules."*
- *"Check my project's memory and score it 0–10."*

## What you get

![Where each fact belongs. Loads every session: the global CLAUDE.md, the project CLAUDE.md or AGENTS.md, and the MEMORY.md index. Loads on demand: path-scoped rules, folder CLAUDE.md files, memory topic files, and repo docs and registries. Never read, but enforced: deny rules, hooks and CI checks.](assets/layers.svg)

| | |
|---|---|
| **Fewer tokens per session** | Budgets for everything that loads every session, and what to move out. It covers the load cap on `MEMORY.md`: only the first 200 lines or 25KB are read, and the rest is invisible. |
| **Claude stops redoing research** | Registries for evidence you've already gathered, one-line "read this first" pointers, and a closed-questions ledger, so settled questions stay settled. |
| **Memory that doesn't mislead** | Every file path an agent is told to follow must exist, no memory hides outside the index, and there is exactly one current direction. Each rule comes from a real incident. |
| **A clear answer to "where does this go?"** | A routing table for 11 layers: global and project `CLAUDE.md`, `AGENTS.md`, `CLAUDE.local.md`, folder files, path-scoped `.claude/rules`, auto memory, repo docs, generated status files, recall tools, and deny rules, hooks and CI. |
| **Rules that can't be skipped** | Which rules to write down, which to enforce with a permission deny rule, hook or CI step, and why a folder `CLAUDE.md` alone won't stop Claude creating a new file in a frozen folder. |
| **A score you can defend** | A 0–10 rubric where every point cites evidence, and things it couldn't see are marked N/A rather than scored 0. |

## How it compares with `claude-md-management`

Anthropic's official
[`claude-md-management`](https://claude.com/plugins/claude-md-management) plugin makes
your `CLAUDE.md` files better written. It checks commands, architecture notes and
gotchas, and captures what you learned in a session.

Cairn Memory works a level above that: it decides **where** each fact should live
across the whole memory system, moves out what doesn't belong, and catches memory
that has gone stale. They work well together.

## Install

```
/plugin marketplace add nicuk/claude-md-memory-architecture
/plugin install cairn-memory@cairn-memory
```

Then ask in plain words: *"audit my Claude memory and score it 0–10"*, *"where should
this rule live?"*, *"set up CLAUDE.md for this new repo"*, or *"Claude keeps redoing the
same research"*.

## The audit script

`skills/memory-architecture/scripts/audit_memory.py` runs 22 checks that give the same
answer every time. Examples: an index past its load cap, memories missing from the
index, one file indexed twice, several files each claiming to be the current direction,
backticked paths that don't exist, `.claude/rules` globs that match nothing, and
project-specific lines in your global file.

```
python skills/memory-architecture/scripts/audit_memory.py --self-test
python skills/memory-architecture/scripts/audit_memory.py --repo . \
  --memory-dir ~/.claude/projects/<project>/memory --global-file ~/.claude/CLAUDE.md
```

`--self-test` plants one defect for each check in a temporary folder and confirms every
check fires. A check that has never failed has never been tested. The self-test badge at
the top runs it on every push, along with a check that the script imports nothing that
can reach the network.

## What it runs, and what it doesn't

- It only reads files. The script reads the paths you pass it, and runs `git ls-files`
  in `--repo` to see what is tracked.
- It writes nothing to your project, except that `--self-test` writes a temporary folder
  and deletes it.
- It makes no network calls, and there's no server or API key. Nothing leaves your
  machine.
- Everything else is instructions for Claude in `SKILL.md` and `references/`.

## Evidence

The rules come from about fifteen repositories worked with coding agents between June
and September 2026. Every rule has an incident behind it, recorded in
`skills/memory-architecture/references/incidents.md`.

In a small test (two realistic prompts, one run each with and without the skill), answers
with the skill passed 93% of the checks against 71% without. Treat that as indicative,
not conclusive. The checks target Claude Code's file layout. The `AGENTS.md` rules also
apply to other agents that read `AGENTS.md`.

## Privacy

Nothing is collected. See [PRIVACY.md](PRIVACY.md).

## Who made this

Built by [Nic Chin](https://nicchin.com/?ref=cairn-memory), who reviews apps built with AI
coding tools. If this audit showed that your agents have been working from stale or
conflicting instructions, the code they wrote may deserve the same check. That's what the
[AI-Built App Audit](https://nicchin.com/vibe-coded-app-audit?ref=cairn-memory) is for.
The plugin is free and complete either way. Nothing in it is held back.

## License

MIT
