---
authority: binding
status: live
---

# Cairn Memory: rules for agents working here

This repo is a Claude Code plugin: `skills/memory-architecture/SKILL.md` is the skill,
`skills/memory-architecture/scripts/audit_memory.py` its script. It's public, and one of three Cairn plugins
whose shared principles and evidence are in `nicuk/cairn-principles`.

Each rule names what enforces it, or says that nothing does. The audit warns on a rule here
that does neither. Everything in `.github/workflows/self-test.yml` runs on every push.

## Rules

- **Every check the script gains gets a planted defect in `--self-test`.** The self-test reads
  the check names from the script itself, so a check without one fails it. Enforced by
  `skills/memory-architecture/scripts/audit_memory.py`.
- **The script stays read-only and can't reach the network.** Enforced by
  `.github/scripts/check_privacy.py`, which reads the code: no networking import in any form, no
  program but read-only git, file writes only in `--draft-index` and the self-test. That
  `PRIVACY.md` still describes this is not enforced: re-read it whenever either changes.
- **The skill's frontmatter must parse as strict YAML.** Never put `: ` inside the description.
  Enforced by `.github/scripts/check_frontmatter.py`, because `claude plugin validate` doesn't.
- **Numbers the docs state about the repo come from their source.** Enforced by
  `.github/scripts/check_claims.py`: the check count in the README, the plugin description and
  the demo, the eval results, and the fixture's expected output.
- **README `## ` sections are shared across the family:** don't add, rename or reorder one here
  alone. Enforced by the daily drift check in `nicuk/cairn-principles`, and before a push by
  `.githooks/run_ci_locally.py` when that repo is cloned alongside this one.
- **Every release raises `version` in `.claude-plugin/plugin.json`, with an entry in
  `CHANGELOG.md` and a git tag.** Version and changelog are enforced by
  `.github/scripts/check_claims.py`. The tag is not enforced: tag `vX.Y.Z` when the release merges.
- **Nothing private goes in this repo:** no client or product names, no private codebases, no
  absolute paths from anyone's machine. Absolute paths are enforced by
  `.github/scripts/check_claims.py`. Names and private code are not enforced: check before committing.
- **Hooks and agents for working on this repo go in `.claude/`, never in a root `hooks/` or
  `agents/` folder.** The plugin ships from the repo root, so those folders would run in every
  installer's sessions. Enforced by `.github/scripts/check_claims.py`.
