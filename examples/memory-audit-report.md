# Example: a memory audit, start to finish

This is the complete answer from one run of the skill. Nothing was edited or picked from several runs.

- **Asked:** the `audit-bloated-store` prompt in [evals/evals.json](../evals/evals.json), word for word: *My claude memory folder for my forecasting project feels bloated and every session seems to burn tokens re-reading it, and claude still redoes stuff. it's at &lt;fixture&gt;/forecast-memory . check it from 0 to 10 and tell me exactly what to fix. also should i add a CLAUDE.md in every folder of the repo to help?*
- **On:** the made-up memory folder that `python evals/build_fixture.py <folder>` builds, for a demand forecaster at a small chain of bakeries. Every name, number and date in it is invented.
- **Run:** 2026-09-28 with Cairn Memory 1.4.0, in a session that could not see the answer key.

---

## Score: 2/10 (1.7, rounded up)

This score covers only the memory folder, because that's all I was given. I scored the three criteria the folder can show: the index, the memory files, and whether there's one current direction plus a list of closed questions. Those came to 0.5 out of 3, which rescales to 1.7/10. I marked the other seven criteria N/A, not 0. They need the repo, your global `CLAUDE.md` or your CI, and scoring what I can't see would measure my access, not your memory.

I ran the audit script on the folder and got 1 FAIL and 38 WARN. The script's self-test passed, meaning all 25 of its planted defects were detected, so its checks do fire. I didn't change anything in your folder.

**Your two complaints have separate causes:**

- **Token cost:** one experiment log has been pasted into 8 files, and the index holds the findings instead of short pointers.
- **Redone work:** four files each claim to be the current plan, there's no list of closed questions, and the same experiments were run again.

## What's wrong

**1. The index loads 9.6 KB, about 2,400 tokens, into every session.**
- That's 3.2 times the 3,000-byte budget.
- 29 of its 33 entries run 214 to 446 characters. They're meant to be one short hook of about 150 characters, pointing to a file.
- For many memories, the index is the only copy of the finding. The file behind it is one sentence:
  - `category-drivers.md` says only "Each category has its own driver."
  - The rain +11% and weekend +23% figures exist only in the index.
  - The same is true of `ensemble-ab-v3.md`: its actual verdict (+0.3 pts, 5x compute, don't retry) is only in the index.
- `model-search-status.md` has two index entries, and they say different things.

**2. One experiment log has been copied into 8 files: about 70 KB of the folder's 87 KB.**
- Runs `fc-2601` onward appear with the same numbers in 8 files: `input-ideas-backlog`, `ensemble-ab-v3`, `bake-quantity-decision`, `public-data-inputs-done`, `model-search-status`, `explainer-product-direction`, `calendar-model-v6` and `shared-model-growth-loop`.
- Each file uses a different prefix (IN-, EN-, RP-, PD-, RW-, OPT-, V6-, ST-).
- Every copy already says the raw numbers are in "the run log", so the memory copies aren't needed.
- The copies also don't match what the files are supposed to be about:
  - The ensemble file's "Member results" are single-input tests, not ensemble members.
  - The bake-quantity "Replay log" has no replay results in it.
  - Its 13 "open questions" are one sentence template repeated with shop and input names swapped in.
- Descriptions don't match contents:
  - `input-ideas-backlog` says "18 candidates, top three tested, 15 untested", but the file holds 56 runs.
  - `public-data-inputs-done` says 41 groups were tried, but it lists 14.
- Opening `input-ideas-backlog.md` alone costs about 6,600 tokens.

**3. Four files claim to be the current direction (the script's `competing-current` check).**
- `explainer-product-direction` says "ACTIVE DIRECTION" (2026-04-09).
- `bake-quantity-decision` says "LEAD CANDIDATE" (2026-04-11).
- `shared-model-growth-loop` says "NORTH STAR" and has no date.
- `pooled-shops-next-step` says "ACTIVE: the branch to work on next is one pooled model".
  - That last one is the FAIL: nothing in the index links to it, so no session will ever see it.
  - It's also out of date: `pooled-test-failed.md` records that the pooled model was tested and didn't help.
- The "NORTH STAR" (one shared model for all shops) contradicts that same failed pooled test, where the small shops got worse. Yet it tells every session to "build nothing that does not feed it".

Each session picks one of these directions, so work that another session already closed gets opened again.

**4. There's no list of closed questions, and the log shows work being redone.**
- Rejected work is spread across about 10 files: v5, the ensemble, pooling, shelf photos, the hourly demand claim, public inputs and the input backlog.
- The input log alone runs the rain flag three times (IN-01, IN-21, IN-41) on different shops, and does the same for most other inputs. That's the redone work you're noticing, recorded in memory itself.

**5. The status memories are stale, and 26 of 31 files have no date in the file itself.**
- Everything is from April 2026; today is 2026-09-28.
- `pilot-shops-status`: "the two waiting shops keep their slots until the end of May".
- `cloud-bill-spike`: "switched to every 20 minutes last week". Was the move to 04:00 ever made?
- The till import, backup, demo video and prompt v2 memories:
  - none of them says when it was last checked ("as of" a date);
  - none gives a command to re-check it.

**6. Some numbers contradict each other. Check them against the run log before anything relies on them.**
- Some verdicts don't match their own numbers:
  - footfall: 12.8% vs a baseline of 13.2%, labelled "worse";
  - promo calendar: 11.8% vs 12.3%, labelled "no effect";
  - delivery cut-off: 14.0% vs 13.7%, labelled "small gain".
- `holiday-flags-hf1` says the school-term flag adds 0.4 pts on its own, but the log calls it "within noise" (13.6% vs 13.4%).
- v6 includes payday week, but the log calls payday week "not robust".
- Shop-week counts are impossible for March:
  - one shop alone has 44 "shop-weeks", and March is about 4.4 weeks;
  - six shops can give about 26 at most.
  - `imported-rows-cluster` says 1,212 of the 1,500 imported rows fall on 2026-03-24 to 2026-03-27.

If the sales history really is days deep, the March holdout results need re-checking. That matters more than anything else in this list.

## Scorecard

| # | Criterion | Score | Evidence |
|---|---|---|---|
| 1-3 | Global file, root file, folder rules | N/A | not given |
| 4 | Index under budget, short entries, nothing unlinked or duplicated | 0 | 9,589 bytes vs 3,000; 29 entries too long; 1 duplicate; 1 unlinked file (FAIL) |
| 5 | One fact per file, type, Why, absolute dates | 0.5 | Every file has a type, and the three feedback memories have Why and How to apply. But 7 of 31 files (22%) trigger warnings, 26 have no date in the file, and 8 carry the copied log |
| 6 | Registry plus pointer, one current direction, closed-questions list | 0 | 4 competing directions; no list; the same inputs re-run |
| 7-10 | Pointers checked by a gate, precedence, generated views, private/tracked split | N/A | repo not given |

## Exactly what to fix, in order

**1. Choose one current direction (about 15 minutes; this does the most for the redone work).**
- Write `current-direction.md` saying what is active now and what is paused.
- My guess is the explainer and the bake quantity fit together: the bake quantity would be the suggestion the explanation justifies. That's your call, though.
- In the same edit:
  - rewrite the other three as dated history ("superseded on <date> by current-direction");
  - delete `pooled-shops-next-step.md`, since `pooled-test-failed.md` answers it;
  - add a date to `pooled-test-failed.md`.
- Keep "NORTH STAR" only if you can say why it survives the failed pooled test.

**2. Replace the 8 log copies with one list of closed questions and one pointer (about 1 hour).**
- Create `closed-questions.md`, one line per question: what was tried, the verdict, the date, and the run id where the evidence lives. Put these in it:
  - v5 closed;
  - the ensemble rejected;
  - the pooled model failed;
  - shelf photos (retry only at 1,000+ labelled photos);
  - the hourly demand claim;
  - one line per input with its run ids.
- Put that list in the repo next to the run log if anyone else works on this, or in memory if it's only you.
- Delete every `### XX-nn` block from the 8 files. The run log already holds them.
- Merge `input-ideas-backlog`, `public-data-inputs-done`, `model-search-status`, `v5-forward-test-result` and `ensemble-ab-v3` into that list.
- Result: about 70 KB gone, and a session checks one file before re-running an experiment.

**3. Move the findings out of the index, then rebuild the index (about 30 minutes).**
- First, copy each long index line's detail into its file body, with an absolute date. The files that need it most:
  - `category-drivers`, `ensemble-ab-v3`, `order-cutoff-timing`, `saturday-uplift-check`;
  - `replay-one-order-limit`, `imported-rows-cluster`, `store-pricing-plan`, `explanation-prompt-v2`.
- Then run `audit_memory.py --memory-dir <folder> --draft-index`. Review the draft before it replaces `MEMORY.md`.
- Don't run it before those steps. On a scratch copy it would:
  - drop the findings that exist only in the index;
  - re-add the stale "ACTIVE: pooled" line at the bottom.

  It also came out at 3,576 bytes, still over budget with 31 memories. The merges in fix 2 are what bring it under.
- Aim for about 15 entries: current direction, closed questions, the three feedback memories, v6 / HF1 / WP2, category drivers, bake economics, and the status memories that survive fix 4.

**4. Re-check or delete the status memories (about 20 minutes).**
- Covers pilot shops, till import, backup, demo video, prompt v2 and the cloud bill.
- For each one, either check it now and add "as of 2026-09-28; re-check with: <command or page>", or delete it.
- `backup-script-status`, `demo-video-status` and `shop-onboarding-checklist` only name repo paths. Either keep them as one-line pointers or drop them.
- Change "last week" in `cloud-bill-spike` to a real date.

**5. Settle the data question before building on any number (cost depends on the run log).**
- Check `imported-rows-cluster` and the shop-week counts against the actual till export.
- If the history really is four days, mark every March-holdout result as not yet valid, with a correction at the top rather than silent deletion.

The first three are the highest value. Together they should take the index from about 2,400 to about 400 tokens per session, and the folder from 87 KB to around 15 KB. After them I'd expect the folder to score about 8 to 9 on the parts I could check.

## Should you add a CLAUDE.md in every folder?

No, because it wouldn't fix either problem:

- **They don't help planning.** A folder `CLAUDE.md` loads only when Claude reads a file in that folder. That doesn't happen during planning or when creating new files, which is exactly when redone work starts.
- **They go stale.** A file per folder usually ends up describing what each file does, and that's out of date by the next commit. It's more text to maintain without stopping any repeat.
- **They don't fix the cause.** Your redone work comes from the competing directions and the missing closed-questions list, not from missing folder notes.

What to do instead:

- **One short root `CLAUDE.md`** (under about 150 lines) with:
  - a pointer to the current direction and to the closed-questions list;
  - the rule "check closed questions before running any experiment";
  - the rule "every null result names its inputs, shops and weeks".
- **A folder `CLAUDE.md` only where a local rule exists that the code can't show.** For example, a model folder whose `CLAUDE.md` says "v6/HF1/WP2 are frozen: no new input without a pass/fail rule written before the run". Most folders need none.
- **If breaking that rule would be costly, enforce it** with a deny rule in `.claude/settings.json`, a hook or CI. Written rules are advice; enforcement is what actually stops it.
- **If Cursor or Codex also work in the repo,** repeat that one rule as a line in `AGENTS.md`.

If you'd like, point me at the repo and I'll score the other seven items and check whether the run log and `docs/onboarding.md` actually exist.
