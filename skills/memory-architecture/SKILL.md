---
name: memory-architecture
description: Keeps coding-agent memory cheap and true, so Claude stops forgetting between sessions, re-reading bloated CLAUDE.md files, redoing research it already did, and acting on stale notes. Decides which layer each fact belongs in (global or project CLAUDE.md, AGENTS.md, folder files, path-scoped .claude/rules, MEMORY.md, repo docs, deny rules and hooks) and the gates that stop it rotting. Ships a self-testing audit script and a 0-10 score. Use it before touching any of those files by hand. Use it whenever someone wants to set up, audit, slim down or clean up CLAUDE.md, AGENTS.md or a memory folder; asks which CLAUDE.md files actually load; wants Claude Code, Cursor and Codex to follow the same rules; says an agent keeps breaking a rule it was given, keeps forgetting, redoes work or burns tokens; asks where a rule or fact should live; or is about to save a memory or write an agent-facing doc, even if they never say "memory".
---

# Memory architecture for coding agents

Memory exists for one reason: so the next session does not pay again for what this one
already learned. Two things undo that. Memory that is **expensive** gets loaded every
session whether it is needed or not. Memory that is **false** sends the next session the
wrong way while sounding sure of itself. Everything below guards against one or the other.

Two ideas carry the whole skill:

1. **Put each fact in the cheapest layer that the agent who needs it will still find.**
   Every layer has a load cost (when it enters context) and a rot rate (how fast it goes
   stale). The two usually trade off against each other.
2. **A claim with an enforcer stays true; a claim with only an author rots.** Anything
   that can go stale either gets something that fails when it does, or it gets written as
   dated history rather than as a present-tense fact.

## The layers

Load behaviour below is Claude Code's documented behaviour. Other harnesses differ, so
confirm yours with `/memory` or its docs before relying on a row.

| Layer | Enters context | Holds | Never holds |
|---|---|---|---|
| **Global** `~/.claude/CLAUDE.md` | every session, every repo | preferences true in a repo you haven't created yet | anything naming a stack, a path, a command or a project |
| **Project root** `CLAUDE.md` / `AGENTS.md` | every session in the repo | the constitution: rules that forbid, require or disambiguate a decision, plus pointers to canonical docs | how-to (goes in a commands doc), history (goes in ADRs), descriptions of code (go in the code) |
| `CLAUDE.local.md` | every session, this checkout only | personal, uncommitted project preferences | anything a teammate also needs |
| **Path-scoped rules** `.claude/rules/*.md` with `paths:` | on demand, when a matching file is read | invariants for a glob such as `**/migrations/**` or `src/billing/**` | rules with no `paths:`, which load every session like the root file |
| **Folder** `CLAUDE.md` | on demand, when files in that subtree are read | local invariants the code cannot show: "frozen", "owned by X", "never import from Y", "generated, do not edit" | a list of what each file does, which rots on the next commit |
| **Memory index** `MEMORY.md` | every session, **first 200 lines or 25KB only** | one line per memory: a link and a hook | the finding itself |
| **Memory topic files** | on demand, via the index | one fact each: user, feedback, project or reference | anything the repo already records |
| **Repo docs**: ADRs, plans, postmortems, registries | on demand, via a pointer | decisions with rationale, measured evidence, the numbers a team relies on | volatile state |
| **Generated views**: `STATUS.md`, `CONTEXT.md` | on demand | facts derived from source at generation time | anything a human typed |
| **Code comments** | when the code is read | why this code is shaped this way | claims about who calls it (the call graph already says so) |
| **Recall tools**: session search, observation stores, code graphs | when queried | "did we already try this?" | authority; anything recalled gets verified before it is acted on |
| **Enforcement**: permission deny rules in `.claude/settings.json`, hooks, CI | never read; it blocks the action | invariants whose breach is costly ("never edit an applied migration", "`billing/` is frozen") | preferences; a deny rule that fires on intended work gets deleted |

**Written rules are advice; enforcement is a wall.** When breaking an invariant would be
expensive, state it in the right written layer so the agent plans around it, and also
enforce it with a deny rule, a hook or CI, so that one skipped read can't break it.

**Load timing matters for planning.** A folder `CLAUDE.md` or a path-scoped rule loads
only once a matching file is read. Creating a new file, or planning before reading
anything, never triggers it. So a constraint that shapes the plan ("don't touch
`billing/` until 2026-12-31") needs one line in the root file. The detail can stay local.

A few facts decide most placements. Parent-directory `CLAUDE.md` files load at startup.
All worktrees of one repo share a single auto-memory directory. `@path` imports resolve
relative to the importing file and go at most 4 hops deep. An index entry past line 200
is invisible, and so is the memory it points to.

### Routing a new fact

Ask these in order and stop at the first yes:

1. **Can it be derived from the code or git?** Then don't store it. If deriving it is
   expensive, generate a view (see "Generated views" below).
2. **Would a teammate or a fresh clone need it?** Then it goes in the repo, never in
   personal memory. If it is a decision, write an ADR. If it is a rule, put it in the
   root file or a path-scoped rule. If it is evidence or numbers, put it in a registry doc.
3. **Does it apply only when certain files are touched?** Use a path-scoped rule, or a
   folder `CLAUDE.md` if the scope is exactly one subtree.
4. **Is it true in every repo?** Put it in the global file, in one line.
5. **Is it about this user, their corrections, or project state outside the repo?** Write
   an auto-memory topic file and add one index line for it.

When an auto-memory keeps pointing into the repo ("read `docs/X.md` first"), it is
working as a **router**. That is the best use of personal memory: a line that costs almost
nothing and prevents a whole re-investigation.

## Writing memory

Read `references/templates.md` for copy-ready templates of every file type.

**Save when:**
- the user corrects your approach, or confirms a non-obvious one;
- a decision is made and an alternative is rejected (record the rejected one, or it gets re-proposed);
- work is about to be redone, such as research, a measurement or an audit. Record where the result lives;
- external state is learned that the repo can't show: a dashboard, an account quirk, a service's real behaviour.

**Don't save:** code structure, past fixes, anything git log or the repo already records,
or anything that only matters to the current conversation. If asked to remember one of
these, ask what was non-obvious about it and save that instead.

**Format rules and why they exist:**
- **One fact per file.** A file that grows sections becomes a lab notebook that nobody can
  cite or supersede cleanly. Split it, or move it to a repo doc and leave a router memory.
- **Feedback carries `**Why:**` and `**How to apply:**`.** A rule without its reason can't
  be applied to an edge case, and gets applied rigidly or not at all.
- **Absolute dates only.** "Decided today" is false tomorrow.
- **Status memories carry "as of <date>" and the command that re-checks them.** The
  reader can then verify in one step instead of trusting or re-investigating.
- **Retract visibly.** When a number turns out wrong, strike it through and say why rather
  than deleting it silently, because someone may already have repeated it. Put the
  correction at the top.
- **Update before you create.** Look for an existing memory on the topic first. Two
  memories on one topic will eventually disagree.
- **One current direction.** Exactly one memory or doc says what is active now. When the
  direction changes, demote the old one to dated history in the same edit. A store where
  five files each call themselves "ACTIVE" or "NORTH STAR" is worse than no store at all,
  because each session picks one and redoes work another already closed.
- **Keep a closed-questions ledger.** Record each rejected option, dead hypothesis or
  settled question as one line: what was tried, the verdict, the date, and where the
  evidence lives. It is the single file that most directly prevents re-work. Keep it in
  the repo if the team needs it, in memory if only you do.
- **Change the file and its index line together.** An index hook that still says "next:
  build X" after the file records X as done sends every session to build X again.
- **Index lines are hooks.** Keep them under about 150 characters: what it is and when it
  matters. The detail belongs in the file the index points to.

## Reading memory

This is where most tokens are saved or wasted.

1. **Before investigating anything, check whether it has already been answered.** Scan
   the index, open only the topic files it points at, and follow any router to the repo
   doc. Then check the decision records (ADRs, plans, postmortems) for a closed question.
   Only if both come up empty, search recall tools for "did we already try this".
2. **Treat every memory as a claim about the past.** Before recommending a file, function,
   flag or command that a memory names, confirm it still exists. Memory that disagrees
   with the code loses; fix or delete the memory in the same breath.
3. **Don't re-open what's closed without new evidence.** A decision record with a rejected
   alternative is an answer. Re-litigating it costs a session and usually lands in the same
   place. If there is new evidence, say what it is.
4. **Cite by name, not number.** Section numbers drift; "the Method section of `AGENTS.md`"
   survives edits.

## Keeping it true

These are the rules with a real incident behind each one. `references/incidents.md` has
the stories. Read it when you need to explain a rule to a skeptical owner, or when a rule
seems like overkill.

- **The walk test.** An agent with no memory must be able to orient itself, act and report
  status from the files alone. That only holds if every pointer resolves. **Backticks mean
  "follow this":** a backticked path must resolve, and a bare path is a name (a file under
  discussion, quoted as broken, or known to be absent). Without that rule, no document
  could report a dead pointer without containing one.
- **A rule with no gate is a preference.** Whatever check proves the walk test has to
  actually run: in CI, in `npm test` or in a pre-commit hook. "Can be run" is not "runs".
- **The census.** Every tracked agent-facing document is either covered by the gate or
  excluded from it with a stated reason. No document enters the repo invisibly.
- **Declared precedence.** When two binding documents can disagree, give each an
  `authority` (`binding` > `decision` > `brief` > `reference`) and a `status`
  (`live` | `historical`) in frontmatter. A dead pointer in a `historical` doc is a
  warning; in a `live` doc it is a failure. That split lets immutable ADRs sit next to a
  strict walk test.
- **ADRs are annotated, never rewritten.** The body is the decision. Frontmatter and a
  dated "superseded by" line appended below are metadata, not edits.
- **Derive numbers; don't type them into prose.** A figure written into a sentence is
  stale the moment the source moves. Compute it where it is displayed, or point to where
  it is computed.
- **Private versus tracked.** Keep private docs under a gitignored folder, but track the
  decision records inside it, because an untracked decision log lives on one machine with
  no history. In `.gitignore`, `_internal/*` then `!_internal/docs/` works; a bare
  `_internal/` stops git descending and the negation can't reach inside. Verify with
  `git check-ignore -v <exact file path>`. Watch skills and tools that write plans to
  their own default paths, which may not be ignored.

### Generated views

When a status or context file is worth having, derive it from source and **enforce
invariants, not bytes**. A check that byte-compares a committed generated file against a
fresh render turns red on every unrelated commit (a new caller, a date, CRLF on another
OS), and a check that is always red gets switched off. Instead:

- gitignore the rendered view and stamp it with its generation time;
- enforce only what changes when status genuinely changes. Example: "no file in a covered
  directory becomes unreachable unless it is listed with a reason, and a listed file that
  comes back to life fails until the list is updated";
- keep dates, hashes and counts out of anything a check compares.

### Don't restructure for tidiness

Moving every document into numbered stage folders feels like architecture, but it breaks
every path citation at once and addresses none of the usual root causes. Those causes are
dead pointers, an ungated check, undeclared precedence, unclassified documents and
volatile generated files. Adopt the **declarative** part (frontmatter, census, walk test)
and leave the folders alone unless a measured problem is a folder problem.

### Memory tooling is a claim too

A recall plugin or memory server can die silently while its health endpoint keeps
reporting "ok". Measure it by its output (rows written today, what a fresh session
actually receives) and by its cost per day. Keep it only if recall visibly saves re-work
after a few sessions.

## Workflows

### Set up from zero (new or unstructured repo)

1. Run the audit script (below) to get a baseline.
2. Write a root `CLAUDE.md` or `AGENTS.md` from the template, under about 150 lines to
   start. Give it a pointer table to canonical docs and **a Method section**: how decisions
   get made here, not only the conclusions.
3. Move anything project-specific out of the global file.
4. Add path-scoped rules or folder `CLAUDE.md` files **only where a local invariant
   exists.** Most folders need none. An empty-but-present folder file is noise.
5. Add a registry doc for each kind of work that has already been repeated: market numbers,
   benchmark results, asset sources, vendor quirks. Then add a router memory for each one.
6. Wire the walk-test check into whatever already runs (a test, CI or a hook). Break it
   once on purpose to confirm it fails.
7. Run the audit again and record the score.

### Audit and score (0-10)

Run the deterministic checks first, since they're cheaper and more reliable than reading:

```bash
python <skill-dir>/scripts/audit_memory.py --global-file ~/.claude/CLAUDE.md \
  --memory-dir ~/.claude/projects/<project>/memory --repo .
python <skill-dir>/scripts/audit_memory.py --self-test   # proves every check can fire
```

FAIL means a breach (an orphaned memory, a truncated index, a dead pointer in a live
doc). WARN means worth a look. Budgets live at the top of the script as named constants,
so change them on purpose rather than ignoring the warnings.

When `index-budget`, `index-line-length`, `index-truncated`, `index-duplicate` or
`memory-orphan` fire, fix the index with a draft rather than by hand:

```bash
python <skill-dir>/scripts/audit_memory.py --memory-dir <memory-dir> --draft-index
```

It writes `MEMORY.draft.md` next to the index: one line of at most about 150 characters
per memory file, with the hook taken from the file's `description` (or the old index text),
the index's order kept, orphans appended, duplicates and dead links dropped. It prints
bytes, lines and estimated tokens before and after, and whether the draft fits the budget
and the load cap. It never touches `MEMORY.md` and won't overwrite an earlier draft
without `--force`. **A human reviews the draft before it replaces `MEMORY.md`:** a hook
rebuilt from `description` can lose a word the owner relied on. If the draft is still over
budget, trimming can't fix it; merge memories or move a cluster into a repo doc.

Then score. Each item is worth 1 point, or 0.5 if only partly met. Cite evidence for each
item; don't grade on impression. If you can't see something (for example, you were given
only the memory folder and not the repo), mark those items N/A, rescale over the items in
scope, and say what the score covers. Scoring what you can't see as 0 measures access,
not quality.

| # | Criterion | Evidence |
|---|---|---|
| 1 | Global file is universal only, under about 60 lines, and holds no one-time instructions | script: `global-*` clean |
| 2 | Root `CLAUDE.md`/`AGENTS.md` exists, is tracked, and holds only decision-changing rules plus pointers | read it; `root-missing` and `agent-file-size` clean |
| 3 | Folder or path-scoped files exist only where a local invariant exists, and every scope matches files | `rule-dead-scope` clean; spot-check 3 |
| 4 | Memory index under budget with hook-length lines; nothing truncated or orphaned | `index-*` and `memory-orphan` clean |
| 5 | Memory files hold one fact each, with type, Why (for feedback) and absolute dates | `memory-*` warnings under 10% of files |
| 6 | Repeated work has a registry doc and a router memory, there is exactly one current direction, and closed questions are in a ledger | `competing-current` clean; find the last re-done investigation and check a registry covers it |
| 7 | Every pointer in live agent-facing docs resolves, and a gate **that runs** proves it | `walk-test` clean; show where it runs |
| 8 | Documents declare authority and status, or the repo is small enough not to need it | frontmatter present; census clean |
| 9 | Generated views enforce invariants, not bytes; costly invariants are also enforced by deny rules, hooks or CI | read the check and `.claude/settings.json` |
| 10 | Private/tracked split verified, and decision records have git history | `git check-ignore -v` on one private file and one decision doc |

Report the score with the three highest-value fixes, each with its cost. **The override
rule:** if a fix would add more friction than the failure it prevents, say so and skip it.
A small solo repo can legitimately score 7 with no work left worth doing.

### Maintain

Maintenance happens when you touch memory, not on a schedule:
- Before adding a memory, check for one to update.
- When a memory proves wrong, fix or delete it now.
- When the index nears its budget, merge related memories or move clusters into a repo doc
  with a single router line.
- When index lines have grown into findings, or memories have fallen out of the index, run
  `--draft-index`, show the owner the draft, and replace `MEMORY.md` with it only once they
  approve.
- When the same investigation happens twice, that is the trigger for a registry.

Don't run repo-wide sweeps by default. A full audit is a decision the owner makes.
