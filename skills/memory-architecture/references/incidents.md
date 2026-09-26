# Incidents behind the rules

Each rule in SKILL.md is here because it failed without it. The incidents come from one
developer's portfolio of about fifteen repositories, all worked with coding agents,
between June and September 2026. The numbers are as measured at the time.

A principle without its incident is easy to agree with and hard to apply. Use these to
explain a rule, and to recognise the failure when it starts again.

## Contents
- Index lines that carried the finding
- Four files, each "the current direction"
- The research that was done twice
- The walk test that nothing ran
- Two binding rules and no precedence
- The generated file that was red on every commit
- The folder restructure that fixed nothing
- The memory tool that was dead for three months
- The one-time instruction in the global file
- The private plans that got pushed
- The number typed into prose
- The index entry that pointed at nothing
- The comment that was true when written

---

### Index lines that carried the finding
Two projects' `MEMORY.md` indexes reached about 10KB each, roughly 2,500 tokens loaded
into every session. Individual lines ran to 400+ characters because each one restated
its memory's conclusion, with numbers and caveats. A third project's index covered 29
memories in 4.6KB with one-clause hooks and lost nothing. The detail was one click away
in the topic file either way.
**Rule:** the index is a budget; lines are hooks.

### Four files, each "the current direction"
A trading-research store of 31 memories had four separate entries marked "NORTH STAR",
"ACTIVE DIRECTION", "LEAD CANDIDATE" and "ACTIVE highest-EV branch". Nothing said which
won, and six further research entries post-dated the "pivot" that was meant to end
research. Index hooks also contradicted their own files: "next task = build X" where the
file recorded X as built, and "gate the 15m signal" where the file recorded the lead as
falsified. The most-recent "ACTIVE" file wasn't in the index at all. Any session could
pick up any of these and redo work that another had closed.
**Rule:** one current direction; demote the rest in the same edit; change file and index
line together; keep closed questions in one ledger.

### The research that was done twice
A game project re-ran a full market and competitor research pass for an investor deck,
though an earlier report had already covered it. The owner caught it. The same failure
happened earlier with art assets. The fix was a registry doc
(`docs/reference/market-evidence.md`: every outside number with a source, a date and a
confidence grade, plus a list of what had *not* been researched) and a one-line memory:
"read the registry before any market research".
**Rule:** repeated work gets a registry and a router memory.

### The walk test that nothing ran
A marketplace repo declared the walk test and wrote a checker whose header said it "exits
non-zero so it can gate a deploy". Nothing called it: no CI job, no hook, no build step.
The next day it was measured. The checker covered 14 of 48 tracked markdown files, and
the other 34 held 26 dead pointers. Two of those pointed at renamed files, sending an
agent into a directory that had since been frozen. Wiring the check into CI took twelve
lines of YAML.
**Rule:** a rule with no gate is a preference. Plus the census: every document is
covered or excluded with a reason.

### Two binding rules and no precedence
The same repo held two binding rules: "ADRs are immutable" and "every pointer must
resolve". They collided in `plans/`, where ADRs legitimately cite files that were later
renamed. Neither document knew about the other, so nobody could say which one won.
**Rule:** the fix was `authority` + `status` frontmatter. A dead pointer in a
`historical` document is a warning and in a `live` one is a failure. It also needed an
explicit carve-out saying that frontmatter and dated annotations are not edits to an ADR.

### The generated file that was red on every commit
A RAG SaaS generated per-directory `STATUS.md` files: verdict, live callers, last change.
A test failed whenever the committed copy differed byte-for-byte from a fresh render. The
files held volatile data: last-change dates, caller lists that shifted whenever any file
anywhere imported a covered one (26 routes imported one component), a citation count,
and a "tracked in git" column describing the file itself. On a Windows checkout, CRLF
turned HEAD red on every clone.
**Rule:** gitignore the views. Enforce invariants that only change when status really
changes ("no file becomes unreachable unless listed with a reason; a listed file that
revives fails").

### The folder restructure that fixed nothing
The published ICM methodology (arXiv 2603.16021) has two halves: numbered stage folders,
and declarative documents that a memoryless agent can walk. An audit mapped five root
causes of documentation drift. The folder half addressed none of them, and it would have
broken every path citation in code comments and agent files. The declarative half,
adopted without moving a file, addressed four. A CI wire-up covered the fifth.
**Rule:** don't restructure for tidiness.

### The memory tool that was dead for three months
A recall plugin saved zero observations for three months across every project, while its
hooks kept firing and its health endpoint kept reporting "ok". The cause was a missing
CLI on the path plus an unauthenticated CLI. Separately, the plugin's first setup cost
about $6 a day with no visible benefit, until the model and context settings were cut,
which brought it to about $0.07 a day.
**Rule:** measure memory tooling by its output and its cost per day, not its health check.

### The one-time instruction in the global file
The global `CLAUDE.md` once held one project's full conventions (its framework, its
commands, its domain rules), which leaked into every unrelated repo. That content was moved out, but the
move left behind an instruction: "move that file into the project repo". It was loaded
into every session for months, and the move never happened.
**Rule:** the global file holds standing preferences, never tasks.

### The private plans that got pushed
A repo gitignored `_internal/` for private plans. A planning skill wrote its specs to
its own default path under `docs/`, which was not ignored, and they were pushed. In a
different repo, the decision records were *under* the ignored folder, so the ledger
recording rejected experiments existed on one machine with no history.
**Rule:** `_internal/*` then `!_internal/docs/`. Check the exact file with
`git check-ignore -v` before the first commit, and never chain the check and the push in
one command.

### The number typed into prose
A collectibles site had figures like "3.7×" and "$3,700" in thesis text on about 30
cards. Each price update made them wrong and needed a manual copy edit on every card.
**Rule:** derive numbers where they are displayed; keep prose qualitative.

### The index entry that pointed at nothing
The first audit run found a memory file present on disk but absent from its index. Since
agents find memories through the index, that memory had been invisible to every session
since it was written.
**Rule:** orphans are a FAIL, not a WARN.

### The comment that was true when written
In one session in one codebase, the following were all found: five metadata fields
described as carrying data that nothing wrote; a function documented as "one predicate,
two callers" that had zero callers; and a comment made false by someone else's later
fix, with nothing to notice. Every one was a written claim, and every one was false.
**Rule:** enforce, or don't assert. Delete the word "always", "called by" or "verified",
or add the assertion that makes it true.
