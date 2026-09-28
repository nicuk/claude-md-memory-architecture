# Changelog

Each release raises `version` in `.claude-plugin/plugin.json` and is tagged `vX.Y.Z`.

## 1.4.0 (2026-09-28)

**Added**
- `--project .` audits the repo, the memory folder Claude Code keeps for it, and the global
  `CLAUDE.md`, finding each one itself. Until now the README asked for
  `~/.claude/projects/<project>/memory` without saying how to find `<project>`. From a
  subfolder it uses the repo's memory, and from a worktree the main checkout's, which all
  worktrees share (read from git's own `commondir`). It uses an exact folder name only:
  when there's none, it says what it looked for and lists similar names without using them,
  because `my-app` and `myapp` can be different projects, and `--draft-index` would write
  into the wrong one. It respects `$CLAUDE_CONFIG_DIR`. `--draft-index --project .` works too.
  Eight planted cases run the whole command, each broken once on purpose.

## 1.3.0 (2026-09-27)

An audit of this repo against its own principle, "a claim with an enforcer stays true", found
claims with no enforcer. Two checks had no planted defect, and the README said 22 checks when
the script had 24. The privacy grep missed three ways to import a network module. Dead links
inside the skill's own folder went unchecked.

**Added**
- `rule-unenforced`: in a `binding` doc, a rule under a Rules heading (`## Rules`, `## Hard
  rules`; not a title that mentions rules) that doesn't say "Enforced by" and name its check, or
  say it isn't enforced, is a warning.
- A skill's markdown links must resolve, because its folder ships as it is. Its backticked
  paths are skipped: on Claude Code's own plugin-dev skills they were examples, not links, 27
  times out of 27. So are `@` names (a CLAUDE.md feature; in a skill, `@john.doe` is a person)
  and placeholder links. The skill's own two references are now links, so they're checked.
  Tested on the public `anthropics/skills` and `anthropics/claude-code` repos: no FAILs from any
  of it, and 47 false warnings on `anthropics/skills` are gone (README files inside a skill name
  paths relative to the skill's folder, which is where the agent reads them).
- Agents, commands, skills and output styles under `.claude/` are walked. A dead link in a skill
  there fails like any skill's; other dead pointers there are warnings, and `@name` there is a
  person, not an import. `.claude/worktrees/` and nested repositories are skipped: they are copies.
- A skill link to a file that exists locally but isn't tracked fails: installers never get it.
  A `SKILL.md` at the repo root covers only itself, not the whole repo.
- `--census` lists every markdown file and how the walk test covers it.
- `--strict` exits 1 on warnings too, for CI.
- CI reads the script's code to prove it's read-only and offline (`check_privacy.py`), and
  checks the numbers and release facts the docs state against their source (`check_claims.py`).
  Each has its own planted-case self-test. The privacy check also refuses renamed imports
  (`import subprocess as sp`), a process started outside the `git()` helper, and writes
  through `io.open`, `codecs.open` or `os.open`.

**Changed**
- The self-test reads the check names from the script's syntax tree, and reporting a check
  under any other name raises, so a check without a planted defect fails the self-test.
  `global-budget` and `agent-file-untracked` now have one: 25 checks, all planted.
- The demo's check count comes from the script.
- `AGENTS.md`: each rule names its enforcer or says it has none, and the repo's own audit
  runs with `--strict`.
- The skill: `.claude/rules` and folder `CLAUDE.md` reach Claude Code only, so a costly
  invariant also gets a line in `AGENTS.md` and a check that stops every agent.
- The eval assertion `billing-local` allowed no root-file line, which contradicted the skill.
  It now allows a one-line pointer; `evals/README.md` explains why the published grades stand.

## 1.2.0 (2026-09-27)

Measured on four public repositories, where the 1.1.0 audit crashed on one and most of its
findings on the others were false alarms.

**Fixed**
- A brace glob in `.claude/rules` (`{website/src/**,README.md}`) crashed the audit. Braces are
  expanded and each alternative is checked on its own; a glob it can't read is a warning.
- `rule-dead-scope` fails only when every alternative of every glob matches nothing. A dead
  alternative next to live ones, or a glob that matches only gitignored or untracked files,
  is a warning.
- The walk test no longer fails on `...` abbreviations, placeholders like `OUT_DIR/`, a
  leading `/`, gitignored build output, or a file the sentence says to create. A path that
  only resolves as the tail of a longer tracked path is a warning naming the full path.

**Added**
- `.claude/CLAUDE.md` counts as a root file and is walk-tested; so are `.claude/rules` bodies.
- The walk test follows `@path` imports and relative markdown links in agent files.
- `paths: "**"` is reported as unscoped.

**Changed**
- The folder `CLAUDE.md` budget is 100 lines, up from 60 (the evidence is at the constant).

## 1.1.0 (2026-09-27)

**Added**
- `--draft-index`: writes a trimmed `MEMORY.draft.md` for review, with one short hook per
  memory, orphans appended, and duplicate or dead entries dropped. It never writes
  `MEMORY.md`, and won't overwrite a draft without `--force`. On a real 47-memory index it
  cut 10,078 bytes to 6,934 with every memory still linked.
- `evals/`: a rebuildable, synthetic fixture with its answer key, so the with-and-without
  comparison can be re-run.
- `AGENTS.md`, and a CI step where this repo passes its own memory audit.
- A case study, linked from the Evidence section.

**Changed**
- The trigger description covers narrow questions too (which CLAUDE.md files load, whether
  an agent file's paths still exist, why an agent broke a rule it was given). On fresh
  prompts it now triggers 5 of 5, with no false triggers.

**Fixed**
- The skill description contained `: `, which a strict YAML parser rejects. `claude plugin
  validate` passed it, but the skill loader fell back to the heading. CI now parses the
  frontmatter strictly.

## 1.0.0 to 1.0.6 (2026-09-26 to 2026-09-27)

First release, then the shared Cairn README layout and family section, the icon as
`.claude-plugin/icon.svg`, and a link to the public principles and evidence.
