# Changelog

Each release raises `version` in `.claude-plugin/plugin.json` and is tagged `vX.Y.Z`.

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
