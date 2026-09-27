# Evals: Cairn Memory (memory-architecture)

Everything needed to re-run the with-skill / without-skill comparison behind the numbers in
the main README: the prompts, a script that rebuilds the test fixture from scratch, and the
answer key the runs were graded against.

| File | What it is |
|---|---|
| `build_fixture.py` | Rebuilds the synthetic memory folder used by the audit eval. Stdlib only, deterministic. |
| `evals.json` | The two prompts, expected outputs, the assertions (the answer key), what was planted, and the published results. |

## The two evals

1. **audit-bloated-store**: "my memory folder feels bloated... score it 0-10, tell me what to fix, should I
   add a CLAUDE.md in every folder?" Runs against the fixture.
2. **route-new-repo**: five facts about a new FastAPI repo (uv, append-only migrations, terse answers,
   competitor research, a frozen billing folder). Where should each live? No fixture needed.

## Rebuild the fixture

```
python evals/build_fixture.py /tmp/memory-fixture
```

This writes `/tmp/memory-fixture/forecast-memory/`: a `MEMORY.md` index and 31 memory files for a
made-up project (a demand forecaster for a small chain of bakeries). Every name, number, date and
finding is invented. It refuses to write into a folder that already has a fixture, so no run reuses an
old one.

What is planted (the full list is under `planted` in `evals.json`):

- an index of about 10 KB (~2,400 tokens, loaded every session) whose hook lines carry the findings
- one file on disk the index never links, `pooled-shops-next-step.md`, which calls itself the ACTIVE
  branch (and is stale: another memory records that the pooled test already failed)
- four files each claiming to be the current direction
- one file indexed twice with different hooks
- six oversized files, each holding many facts
- a relative date ("last week")

Check the rebuild with the plugin's own script:

```
python skills/memory-architecture/scripts/audit_memory.py --memory-dir /tmp/memory-fixture/forecast-memory
```

It should report the orphan (FAIL), the index budget, the duplicate index entry, the four competing
"current direction" files, six oversized files, the relative date, and 28 over-long index lines
(1 FAIL, 38 WARN).

## Run the comparison

For each prompt in `evals.json`:

1. Build a **fresh** fixture for every run (or copy one built once). Never let two runs share a folder:
   one run's edits would leak into the next.
2. Put the fixture somewhere the run cannot reach `evals/`. The answer key sits in `evals.json` in plain
   sight; a run that can read it is not a test. Copy the fixture out of the repo, and start the run in
   that copy, not in this repository.
3. Replace `<fixture>` in the prompt with the path to that copy.
4. Run the prompt once **with** the skill installed and once **without** it. Same model, same settings,
   nothing else different.
5. Save each run's final answer, and hash the fixture before and after (for `fixture-untouched`).

## How it was graded

Each run's final answer was read against the assertions in `evals.json`: pass or fail per assertion,
with a line of evidence. `fixture-untouched` was checked by hashing the fixture before and after the run.
The score is assertions passed over assertions total.

## Results published so far

Run on 2026-09-26, one run per configuration per prompt.

| Eval | With skill | Without skill |
|---|---|---|
| audit-bloated-store | 6/7 (missed: load cap) | 5/7 (missed: load cap, registry fix) |
| route-new-repo | 7/7 | 5/7 (put the migrations rule and the billing freeze in the root file) |
| **Total** | **13/14 (93%)** | **10/14 (71%)** |

With the skill the runs took longer: about 296 s against 191 s on average, and about 158k tokens
against 133k.

**The audit eval was first run on a copy of a real memory folder, which is private and is not published.**
The fixture here is a synthetic stand-in built to carry the same pathologies, with invented content. The
published 6/7 and 5/7 were measured on the private folder, not on this fixture, and the fixture has not
yet been through the comparison itself. Re-running on it tests the same things, but it is a new
measurement, and the numbers may differ.

## Known limits

- **Small n.** Two prompts, one run each per configuration. A single run can swing a whole assertion,
  so the 93% vs 71% gap is a signal, not a settled effect size.
- **Made-up data.** The fixture is synthetic, and the published audit result came from a different
  (private) folder with the same shape.
- **Author-built.** The same author wrote the skill, the prompts, the assertions and the fixture, and
  graded the runs. The assertions check what the author thinks matters.
- **One assertion no run passed.** `knows-load-cap` (only the first 200 lines / 25 KB of MEMORY.md load)
  failed in both configurations: the index was 36 lines, so the cap never bound and neither run raised it.
  The synthetic index is 34 lines, so the same is likely.
