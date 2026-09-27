# Changelog

Each release raises `version` in `.claude-plugin/plugin.json` and is tagged `vX.Y.Z`.

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
