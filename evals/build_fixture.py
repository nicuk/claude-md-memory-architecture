#!/usr/bin/env python3
"""
build_fixture.py - rebuild the synthetic memory folder used by the "audit-bloated-store" eval.

Usage:
  python build_fixture.py OUT_DIR

Creates OUT_DIR/forecast-memory/, an auto-memory folder (MEMORY.md index plus one file per
memory) for a made-up project: a demand forecaster for a small chain of bakeries. Every
name, number, date and finding in it is invented. It is built to carry the same pathologies
as the real memory folder the eval was first run on, which is private and is not published:

  - an index of about 10 KB whose hook lines carry the findings instead of pointing at them
  - one memory file on disk that the index never links (pooled-shops-next-step.md), and that
    calls itself the ACTIVE branch
  - four files each claiming to be the current direction (ACTIVE DIRECTION, NORTH STAR,
    LEAD CANDIDATE, and the orphan's ACTIVE)
  - one file indexed twice with different hooks (model-search-status.md)
  - oversized files that hold many facts each (the largest is about 26 KB)
  - a relative date ("last week") that rots on read

Deterministic and stdlib only: the same OUT_DIR contents every time, byte for byte.
The answer key is evals.json next to this script; it is never copied into OUT_DIR.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

FIXTURE_NAME = "forecast-memory"
SESSION_NS = uuid.UUID("6f1c2a52-0000-4000-8000-00000000f1c5")  # made-up namespace


def session_id(stem: str) -> str:
    return str(uuid.uuid5(SESSION_NS, stem))


# ------------------------------------------------------------------ bulk generators
# Oversized files are oversized because they log many separate results in one place.
# The generators below write that log from fixed tables, so the output never changes.

TOPICS = [
    "temperature lag", "rain flag", "school-term flag", "payday week", "local events feed",
    "footfall counter", "price change", "promo calendar", "opening hours", "delivery cut-off",
    "shelf-life window", "day-before sell-out", "wind speed", "humidity", "pollen count",
    "sports fixtures", "roadworks nearby", "tourist season", "university term", "market day",
]
SHOPS = ["high street", "station", "harbour", "airport", "market square", "riverside"]
VERDICTS = ["no effect", "no effect", "within noise", "small gain, not robust", "no effect",
            "worse on the holdout"]


def entry(prefix: str, i: int, width: int) -> str:
    topic = TOPICS[i % len(TOPICS)]
    base = 12.0 + (i * 7 % 23) / 10
    got = base - ((i * 5) % 9 - 3) / 10
    shops = ", ".join(SHOPS[(i + k) % len(SHOPS)] for k in range(1 + i % 4))
    verdict = VERDICTS[i % len(VERDICTS)]
    lines = [
        f"### {prefix}{i:02d}: {topic}",
        f"- Setup: add {topic} to the calendar model, refit weekly, shops: {shops}.",
        f"- Result: mean abs error {got:.1f}% vs baseline {base:.1f}% on the March holdout "
        f"({(i * 13) % 40 + 20} shop-weeks).",
        f"- Control: shuffled-label run moved error by {((i * 3) % 5) / 10:.1f} pts.",
        f"- Verdict: {verdict}.",
    ]
    if width > 1:
        lines.append(f"- Notes: tried {2 + i % 3} lag lengths and {1 + i % 2} encodings; none changed the "
                     f"verdict. Raw numbers in the run log, run id fc-{2600 + i}.")
    if width > 2:
        again = "drop it" if verdict in ("no effect", "worse on the holdout") else "retest on April data"
        lines.append(f"- Next: {again}; no rerun without a new data source.")
    return "\n".join(lines) + "\n"


def log(prefix: str, n: int, width: int = 3) -> str:
    return "\n".join(entry(prefix, i, width) for i in range(1, n + 1))


def question_list(n: int) -> str:
    return "\n".join(
        f"{i}. Does the leftover-to-sell-out cost ratio hold at the {SHOPS[i % len(SHOPS)]} shop when "
        f"{TOPICS[i % len(TOPICS)]} changes? (needs {2 + i % 3} weeks of data)" for i in range(1, n + 1)) + "\n"


# ------------------------------------------------------------------ the memories
# hook: what the index line says after the dash. The pathology is that the hook carries the
# finding. body: the file's own text after the frontmatter.

M: list[dict] = []


def mem(stem, title, mtype, description, hook, body, indexed=True):
    M.append(dict(stem=stem, title=title, type=mtype, description=description,
                  hook=hook, body=body, indexed=indexed))


mem("cloud-bill-spike", "Cloud bill spike", "project",
    "April compute bill is the re-forecast job for the demo shops, not customer traffic",
    "2026-04-21: compute bill up 2.1x in April; the cause is the re-forecast job for the demo shops, not "
    "customer traffic; the job runs every 20 minutes so the database never idles; 640 of 700 compute-hours on "
    "the provider's usage page are that job; moving it to once a day at 04:00 should bring the bill to about "
    "$30/month; nothing is misconfigured, the job is just too frequent",
    "The compute bill rose 2.1x in April. The re-forecast job was switched to every 20 minutes last week, "
    "so the database never gets to idle.\n\n"
    "- 640 of 700 compute-hours on the usage page are that job.\n"
    "- Customer traffic is flat; there are no paying shops yet.\n"
    "- Nothing is misconfigured: the job is simply too frequent for the demo shops ([[pilot-shops-status]]).\n\n"
    "**How to apply:** run the job once a day at 04:00 before onboarding more shops.\n")

mem("calendar-model-v6", "Calendar model v6", "project",
    "v6 uses calendar inputs only and beats the baseline on five of six shops",
    "2026-04-19: v6 uses only calendar inputs (weekday, bank holiday, school term, payday). On the March "
    "holdout it beats the naive baseline on five of six shops, 11.8% vs 13.1% mean abs error; the airport shop "
    "is the exception because flights drive it, not the calendar (0.9 pts worse); refit weekly, daily refits "
    "overfit (12.6%); freeze v6 before adding anything",
    "Calendar inputs only: weekday, bank holiday, school term, payday week.\n\n"
    "- March holdout: 11.8% error vs 13.1% baseline, five of six shops better.\n"
    "- Airport shop worse: flights drive it.\n"
    "- Weekly refit; daily refit overfits.\n\n"
    "**How to apply:** freeze v6 before adding any input. The weather inputs are in [[weather-pack-wp2]].\n"
    + log("V6-", 4, 2))

mem("weather-pack-wp2", "Weather pack WP2", "project",
    "Temperature lag and a morning rain flag help loaves on four shops",
    "2026-04-19: weather pack WP2 = two-day temperature lag plus a morning rain flag; error down 1.4 pts on "
    "four shops, unchanged on two; a shuffled-label control moved it only 0.1 pts, so it is not an artefact; "
    "only loaves respond, pastries don't; the rain flag on its own gives 0.8 of the 1.4; one-day and three-day "
    "lags are both worse than two",
    "Two-day temperature lag and a morning rain flag.\n\n"
    "- Error down 1.4 pts on four shops, unchanged on two.\n"
    "- Shuffled-label control: 0.1 pts.\n"
    "- Loaves only ([[category-drivers]]).\n")

mem("shelf-photos-no-signal", "Shelf photos: no signal", "project",
    "Vision models guessing sell-out from shelf photos do no better than chance",
    "2026-04-17: asked three vision models to guess end-of-day sell-out from 10:00 shelf photos; 51% "
    "agreement with what happened over 250 photos, no better than chance; the models agreed with each other "
    "48% of the time; photos from a fixed angle in six shops over two weeks; spent $38 on model calls; parked "
    "until there are 1,000+ labelled photos",
    "Three vision models, 250 shelf photos taken at 10:00, six shops, two weeks.\n\n"
    "- Agreement with actual sell-out: 51%. Between models: 48%.\n\n"
    "**How to apply:** don't retry without at least 1,000 labelled photos.\n")

mem("holiday-flags-hf1", "Holiday flags HF1", "project",
    "Bank-holiday and school-term flags improve every shop on the holdout",
    "2026-04-16: bank-holiday and school-term flags cut error 2.1 pts on the March holdout and every shop "
    "improved; the test was written down before it was run; frozen as HF1; bank holidays account for about "
    "70% of the gain, the school-term flag adds 0.4 on its own; the gain is the same with or without WP2",
    "Bank-holiday and school-term flags, test registered before the run.\n\n"
    "- Error down 2.1 pts on the March holdout, all six shops.\n"
    "- Bank holidays give about 70% of it.\n"
    "- Frozen as HF1.\n")

mem("say-what-was-tested", "Say what was tested", "feedback",
    "A null result names the inputs, shops and weeks it covered",
    "FEEDBACK (2026-04-12): a null result must say which inputs, shops and weeks it covered; never write "
    "\"nothing helps\"; list the inputs that were not tried so a later session does not treat them as ruled "
    "out; the pooling idea was nearly dropped because of a vague null",
    "Every null result names its scope.\n\n"
    "**Why:** a vague \"nothing helps\" nearly got the pooling idea dropped before anyone tried it.\n\n"
    "**How to apply:** write the inputs, shops and weeks next to every null.\n")

mem("v5-forward-test-result", "v5 forward test result", "project",
    "Frozen v5 loses its gain when run forward, so the v5 line is closed",
    "2026-04-14: v5 was frozen on 2026-03-16 and run forward for four weeks with no changes; 14.9% error "
    "going forward vs 11.2% in the fitting window, so its gain was overfit; every v5 variant fell away the same "
    "way, so it is not one bad shop; the in-sample t of 3.1 came after 60 attempts; all v5 variants are closed",
    "v5 frozen on 2026-03-16, run forward four weeks unchanged.\n\n"
    "- Forward error 14.9% vs 11.2% in the fitting window.\n"
    "- Every variant fell away the same way.\n\n"
    "**How to apply:** the v5 line is closed. See [[model-search-status]].\n")

mem("pitch-plain-claim-first", "Pitch: plain claim first", "feedback",
    "The pitch opens with one claim an owner can check; statistics at the back",
    "FEEDBACK (2026-04-10): the pitch opens with one claim a shop owner can check themselves (\"bake 12% "
    "less and still sell out\"); confidence intervals go at the back; two drafts were sent back for opening with "
    "statistics; the owner must be able to check the claim in a week without us",
    "Open with one claim the owner can check.\n\n"
    "**Why:** two drafts were sent back for leading with confidence intervals.\n\n"
    "**How to apply:** statistics go in an appendix, never the opening paragraph.\n")

mem("explainer-product-direction", "Explainer product direction", "project",
    "ACTIVE DIRECTION: the product is the explanation, not a better forecast",
    "ACTIVE DIRECTION (2026-04-09): the product is now the explanation, not a better forecast: every number "
    "shows what drove it in one sentence; start with 3 pilot shops; price stays the same; this replaces the "
    "accuracy roadmap; the success measure is how often owners bake what we suggest; accuracy work is paused, "
    "not deleted",
    "ACTIVE DIRECTION. The search for accuracy is done ([[public-data-inputs-done]]). What we sell is the "
    "explanation: each forecast shows the input that moved it most and one sentence an owner can check.\n\n"
    "## Plan\n"
    "1. Explanation line on every forecast.\n2. Three pilot shops.\n3. Measure how often owners follow the "
    "suggestion.\n\n"
    "## Options considered and dropped\n" + log("OPT-", 10, 3))

mem("bake-quantity-decision", "Bake quantity decision", "project",
    "LEAD CANDIDATE: optimise how much to bake, not forecast error",
    "LEAD CANDIDATE (2026-04-11): optimise how much to bake, not forecast error: with leftovers costed at 1x "
    "and a sell-out at 3x, the cost-aware quantity earns 9% more margin in replay; it holds on 12 of 14 "
    "shop-months; the 3x is a guess from two owner conversations and needs measuring; needs each shop's real "
    "costs; 13 questions still open; can sit on top of v6 without changing it",
    "LEAD CANDIDATE. Stop minimising forecast error; choose the bake quantity that makes the most money.\n\n"
    "- Leftovers cost 1x, a sell-out costs about 3x (the lost sale and the annoyed regular).\n"
    "- In replay the cost-aware quantity earns 9% more margin.\n\n"
    "## Replay log\n" + log("RP-", 20) + "\n## Open questions\n" + question_list(13))

mem("shared-model-growth-loop", "Shared model growth loop", "project",
    "NORTH STAR: one shared model that every shop's sales keep retraining",
    "NORTH STAR: one shared model that every shop's sales keep retraining, so each new shop makes every "
    "other shop's forecast better; build nothing that does not feed it; one-off analysis is wasted effort; a "
    "shop that leaves still improves the model for 90 days; the public league table ranks shops by leftovers "
    "saved, which owners understand better than error rates; it launches at 10 shops",
    "NORTH STAR. Every shop's sales retrain one shared model.\n\n"
    "- Build nothing that does not feed the shared model.\n- One-off analysis is wasted effort.\n"
    "- The public league table ranks shops by leftovers saved.\n\n"
    "## Stages\n" + log("ST-", 3, 1))

mem("pilot-shops-status", "Pilot shops status", "project",
    "Three pilot shops live on the demo login",
    "high street, station and market square went live 2026-04-02 on the demo login; the airport shop failed "
    "onboarding twice (missing till data); the harbour shop is waiting on its owner; each pilot gets its "
    "forecast by 05:30 and retrains overnight; the two waiting shops keep their slots until the end of May",
    "Live since 2026-04-02: high street, station, market square.\n")

mem("ensemble-ab-v3", "Ensemble A/B v3", "project",
    "A five-model ensemble is no better than v6 alone",
    "five-model ensemble vs v6 alone: +0.3 pts, which is inside run-to-run noise, for 5x the compute; three "
    "of the five members contribute nothing; the promotions member makes two shops worse; the blending weights "
    "moved a lot between folds (calendar weight anywhere from 0.31 to 0.74); the result is the same with or "
    "without the airport shop; keep v6 and don't retry with more members",
    "Five-model ensemble against v6 alone.\n\n"
    "## Member results\n" + log("EN-", 25))

mem("explanation-prompt-v2", "Explanation prompt v2", "project",
    "Shorter explanation prompts are written but switched off",
    "shorter explanation prompts are in the codebase (90 words down to 35) but not switched on for any shop; "
    "switching needs a per-shop flag; owners in the pilot said v1 was too long to read before opening",
    "Prompt v2 written 2026-04-06; all shops still on v1.\n")

mem("saturday-uplift-check", "Saturday uplift check", "project",
    "v6 catches the Saturday rise; Sundays are where it misses",
    "Saturday sales are 23% higher and v6 captures 19 points of that; Sundays and bank-holiday Mondays are "
    "where it misses; the worst single week was 18% off; bank-holiday Mondays alone account for half of the Sunday-Monday miss",
    "Saturday uplift 23%, v6 catches 19 points of it.\n")

mem("input-ideas-backlog", "Input ideas backlog", "project",
    "18 candidate inputs ranked; the top three tested and none helped",
    "18 candidate inputs ranked by value times effort; the top three (payday week, local events, footfall) "
    "were tested and none helped; the other 15 are untested; price changes and promotions need data the shops "
    "don't send yet; the ranked list lives in the planning doc, this memory records what was run",
    "Eighteen candidate inputs, ranked by value times effort.\n\n"
    "## Runs\n" + log("IN-", 56))

mem("model-search-status", "Model search status", "project",
    "Where the model search stands: v5 closed, calendar inputs carry the gain",
    "v5 search closed: its best variants looked good in the fitting window (t 3.1) and went flat going "
    "forward; 60 variants were tried, so a t of 3.1 is what picking the best of 60 gives by chance",
    "v5 failed going forward. Taking it apart shows where the gain was: the calendar inputs, not the weather "
    "or the promotions.\n\n"
    "## Rolling-window log\n" + log("RW-", 10))

mem("reusable-pipeline", "Reusable pipeline", "feedback",
    "No throwaway scripts; every experiment feeds the next",
    "FEEDBACK: no throwaway scripts; each experiment writes its result to the run log so the next one "
    "starts from it; build for twenty shops, not three",
    "Every experiment goes through the pipeline and writes to the run log.\n\n"
    "**Why:** the user wants the process to grow with the number of shops.\n\n"
    "**How to apply:** no one-off scripts; add reusable steps to the pipeline.\n")

mem("store-pricing-plan", "Shop pricing plan", "project",
    "Forecast free, explanations and bake quantities paid",
    "shops get the forecast free and pay $49/month for explanations and bake quantities; the free forecast is "
    "never made worse to push upgrades; nobody pays yet, so getting proof matters more than the price",
    "Forecast free; explanations and bake quantities $49/month per shop.\n")

mem("till-import-status", "Till import status", "project",
    "Till import runs every 5 minutes; two shops send late timestamps",
    "till import runs every 5 minutes since 2026-04-02; two shops send timestamps hours late because of old "
    "till firmware; retries are capped at 3; a late batch is re-imported, never dropped, and the gap shows on the status page",
    "Till import every 5 minutes. Two shops on old firmware send late timestamps.\n")

mem("order-cutoff-timing", "Order cut-off timing", "project",
    "Order flour at 14:00, not at closing time",
    "placing the flour order at closing time misses the evening sell-outs, which are 58% of the savings; "
    "ordering at 14:00 captures 91% of them in replay; the supplier's cut-off is 15:00",
    "Order at 14:00; closing time is too late to react to the evening.\n")

mem("hourly-demand-claim", "Hourly demand claim", "project",
    "A supplier's hour-of-day demand pattern does not hold up",
    "a supplier's chart said demand follows the hour of day; on new weeks the pattern disappears; their chart "
    "used 9 days from one shop in December; do not rebuild the hourly model on the strength of it",
    "The supplier's hourly pattern came from 9 days in one shop and does not repeat.\n")

mem("public-data-inputs-done", "Public data inputs done", "project",
    "41 groups of public inputs tried; stop looking for new ones",
    "41 groups of public inputs tried (weather, holidays, footfall, events); nothing beyond HF1 and WP2 "
    "helps; the last 12 were all within 0.2 pts of baseline; stop looking for new public inputs",
    "41 groups of public inputs, all tried.\n\n## Groups\n" + log("PD-", 14, 2))

mem("pooled-test-failed", "Pooled test failed", "project",
    "One pooled model across six shops did not help",
    "registered test of one pooled model across all six shops: no improvement (t 0.4); the spread between "
    "shops got wider on four of them; the two big shops carried the pooled fit and the small ones got worse",
    "Pooled model, registered in advance: t 0.4, no improvement.\n")

mem("category-drivers", "Category drivers", "project",
    "Loaves follow the weather, pastries the calendar, cakes the pre-orders",
    "loaves follow the weather (rain +11%), pastries follow the calendar (weekends +23%), celebration cakes "
    "follow pre-orders; a model per category, not per shop, is the next structure to try; bread flour orders should follow the loaf forecast only",
    "Each category has its own driver.\n")

mem("replay-one-order-limit", "Replay one-order limit", "project",
    "The replay allowed one order a day, which hides the midday top-up",
    "the replay allowed one order a day, which hides the value of a midday top-up (+6% margin on three "
    "shops); it needs two orders a day; the supplier confirmed a second delivery slot costs $6",
    "The replay needs a second daily order to show the top-up.\n")

mem("imported-rows-cluster", "Imported rows cluster", "project",
    "Most imported sales rows fall on four days",
    "of 1,500 imported sales rows, 1,212 fall on 2026-03-24 to 2026-03-27, so the history is days, not "
    "weeks; not enough to see a seasonal pattern; the older exports were never requested from the till provider",
    "The import history is four days deep, not several weeks.\n")

mem("demo-video-status", "Demo video status", "project",
    "Demo video built; narration not recorded",
    "94-second demo video built from code in demo-video/; narration not yet recorded; script is in the "
    "planning doc",
    "Demo video built from code in demo-video/.\n")

mem("backup-script-status", "Backup script status", "reference",
    "Nightly sales database backup; restore tested once",
    "nightly backup of the sales database to cold storage, 1.2 GB; restore tested once on 2026-04-05 and "
    "took 11 minutes; script at scripts/backup.sh",
    "Nightly backup, restore tested 2026-04-05. Script: scripts/backup.sh.\n")

mem("shop-onboarding-checklist", "Shop onboarding checklist", "reference",
    "What a new shop needs before its first forecast",
    "a new shop needs till export access, 8 weeks of sales, opening hours and its supplier cut-off before "
    "the first forecast; checklist in docs/onboarding.md",
    "Checklist: docs/onboarding.md.\n")

# The orphan: on disk, never linked from MEMORY.md, and it says it is the live branch.
# It is also stale: pooled-test-failed.md records that the pooled test was run and failed.
mem("pooled-shops-next-step", "Pooled shops next step", "project",
    "ACTIVE: the branch to work on next is one pooled model across all six shops, with the pass/fail "
    "rule written before the run",
    None,
    "Written 2026-04-08. Single-shop inputs look exhausted, but they were only ever tried one shop at a "
    "time. Small shops have too little history on their own; a model pooled across all six should lend them "
    "the calendar pattern from the big ones.\n\n"
    "## Pass/fail rule (written before the run)\n"
    "- Pass: pooled error at least 1.5 pts below single-shop on four of six shops.\n"
    "- Fail: anything else. No adding inputs after seeing the result.\n\n"
    "## Status\nPipeline checked on made-up data. Real run not started.\n",
    indexed=False)

# Index layout: newest first, in two groups, with model-search-status.md indexed twice.
INDEX_ORDER = [
    ["cloud-bill-spike", "calendar-model-v6", "weather-pack-wp2", "shelf-photos-no-signal",
     "holiday-flags-hf1", "v5-forward-test-result", "say-what-was-tested", "bake-quantity-decision",
     "pitch-plain-claim-first", "explainer-product-direction", "shared-model-growth-loop"],
    ["pilot-shops-status", "ensemble-ab-v3", "explanation-prompt-v2", "saturday-uplift-check",
     "input-ideas-backlog", "model-search-status", "reusable-pipeline", "store-pricing-plan",
     "till-import-status", "order-cutoff-timing", "model-search-status#2", "hourly-demand-claim",
     "public-data-inputs-done", "pooled-test-failed", "category-drivers", "replay-one-order-limit",
     "imported-rows-cluster", "demo-video-status", "backup-script-status", "shop-onboarding-checklist"],
]
SECOND_HOOK = {
    "model-search-status": (
        "Model search: where the gain is",
        "splitting v5 apart shows the calendar inputs carry nearly all of the gain; weather helps on four "
        "shops; promotions add nothing; the obvious next step was pooling all six shops (see the pass/fail "
        "rule); holdout is 2026-03-01 to 2026-03-31"),
}


def render_memory(m: dict) -> str:
    fm = (
        "---\n"
        f"name: {m['stem']}\n"
        f"description: \"{m['description']}\"\n"
        "metadata:\n"
        "  node_type: memory\n"
        f"  type: {m['type']}\n"
        f"  originSessionId: {session_id(m['stem'])}\n"
        "---\n\n"
    )
    return fm + m["body"]


def render_index() -> str:
    by_stem = {m["stem"]: m for m in M}
    out = ["# Memory Index", ""]
    for group in INDEX_ORDER:
        for key in group:
            if key.endswith("#2"):
                stem = key[:-2]
                title, hook = SECOND_HOOK[stem]
            else:
                stem = key
                title, hook = by_stem[stem]["title"], by_stem[stem]["hook"]
            out.append(f"- [{title}]({stem}.md) — {hook}")
        out.append("")
    return "\n".join(out)


def build(out_dir: Path) -> Path:
    target = out_dir / FIXTURE_NAME
    if target.exists():
        raise SystemExit(f"{target} already exists; pick an empty OUT_DIR so no run reuses an old copy")
    target.mkdir(parents=True)
    for m in M:
        (target / f"{m['stem']}.md").write_bytes(render_memory(m).encode("utf-8"))
    (target / "MEMORY.md").write_bytes(render_index().encode("utf-8"))
    return target


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    target = build(Path(sys.argv[1]))
    files = sorted(target.glob("*.md"))
    index = target / "MEMORY.md"
    print(f"fixture at {target}")
    print(f"  {len(files)} files, MEMORY.md {index.stat().st_size} bytes, "
          f"largest {max(f.stat().st_size for f in files)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
