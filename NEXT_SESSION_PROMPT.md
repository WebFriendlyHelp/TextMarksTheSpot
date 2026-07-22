# Next session prompt (paste into a fresh session)

We're picking up Text Marks the Spot on branch `scope-hardening`. `main` is
still v1.0.13 and that is what the store serves, so nothing on this branch has
reached users. All three branches ARE pushed to GitHub now.

Read `CLAUDE.md`, `DEBUGGING.md`, and the TOP entry of `implementation-notes.md`
first. 313 tests: `python -B -m pytest tests/` from the repo root (the `-B`
matters — see the harness traps in `tests/sabotage_check.py`).

## State as of 2026-07-19 (end of day)

The merge blocker is CLOSED and Task 2 SHIPPED. Three commits today:

- `c7ec17b` — deleted the `chrome-none` scope (it admitted every chunk with no
  chrome check whenever the landmark enumeration came back empty, and NVDA makes
  a FAILED search indistinguishable from a landmark-free page), and added
  landmark ancestry from the control field stack for the WALK.
- `ac35e89` — fixes from two independent implementation reviews, which BOTH
  found the same two deletions that left all 307 tests green.
- `e8eaa8c` — recorded that the depleted-scope net has never fired, and shelved
  its planned refinement.

**Measured in production, both engines.** stevequayle: `walk_total=84ms`,
`parent_derefs=0`, `identity=0`, `field=113` of 113, `field_backend=y`. Firefox
(`Dynamic_DocumentMozillaIAccessible`) and Chromium
(`IAccessible.chromium.Document`) both report `field_backend=y`, so the
class-based backend gate covers both.

Casey is SOAKING this build as his daily driver. The field_stack probe add-on
has been uninstalled, so the logs are clean.

## What to do next

1. **Ask Casey how the soak went, and read the log before theorising.** The
   persistent log (`%APPDATA%\nvda\TextMarksTheSpot-perf.log`) survives
   restarts; the decision trace lives only in `nvda.log` and is gone two NVDA
   restarts later. You can always reproduce by re-loading the page.
2. **Still unobserved in production: `field_drops` doing real work.** Everything
   measured so far was landmark-free or simple-nav. Pages in Casey's history
   with no `<main>` but marked chrome: thurrott.com (9 loads), bleepingcomputer,
   disabilityscoop, breitbart (6 chrome ranges), vovsoft (15 loads).
3. **THE COUNTS** are now the dominant cost — 646-666 ms of ~730 ms, with
   `counts_trunc=True` every time. This is measured, not guessed. PROBE FIRST:
   collapse to the item start and expand ONE CHARACTER, record MAX call time
   (not average), plus `backendName`, the TextInfo class, and the NVDA version.
   Budget math before committing: 6 types x 300-item cap x ~1 ms is ~1.8 s
   against a 0.6 s budget.

## Open, none of them blockers

- `_count_in_scope` (`tree_summary.py:1712`) DROPS an item whose `obj is None`
  without setting `truncated_out` — a TRUSTED undercount, poison for NOTICE and
  KEY_RESULT which fire on SMALL counts. Its sibling `_count_in_range` biases
  the OPPOSITE way on the same evidence.
- Objectless chunks still fail open on the plain-chrome and range-error identity
  branches (`chrome-pos` correctly refuses them). Pre-existing; both reviewers
  say CLAUDE.md mis-files this as an accepted limitation.
- `classifier.py:448` bumps LIST confidence at `article_count >= 5` while
  `_ARTICLE_LIMIT = 4` caps it. Dead branch.
- The depleted-scope net is UNVERIFIED (never fired in 245 loads). Do not refine
  it; watch the persistent log for `unscoped-depleted` and delete it if it stays
  absent. Its shelved refinement, and a live Codex/Fable disagreement about
  whether `_SCOPE_RANGE_DROP` may be treated as trusted, are recorded in
  `_scope_looks_depleted`'s docstring.
- `main-id` via `controlIdentifier_docHandle`/`_ID`, behind its own probe.
- Whether `_LANDED_SUPPRESS_SEC` should be TI-aware rather than URL-only.
- The branch version is still 1.0.13, same as the release, so the installed copy
  is not self-identifying. Deliberate: the bump happens at release time.

## How to work on this branch

- **Two reviewers in parallel, every round: Codex AND a Fable subagent.** They
  have killed several designs, they disagree with each other usefully, and today
  they independently found the same two green-suite holes. This is the
  highest-value habit here. Codex invocation traps are in the global CLAUDE.md.
- **Sabotage-check every new test**: `python -B tests/sabotage_check.py` reverts
  each fix in several disguises and confirms the suite goes red. 15 entries, all
  caught. It found a genuine hole in today's own tests.
- **Before improving a mechanism, confirm it has ever fired.** See DEBUGGING.md
  step 0. This is what stopped a full day of work on the depleted net.
- Verify NVDA behavior from source or the INSTALLED bytecode, never recall.
- Commit and push freely (standing authorization). A TAG push is a release and
  still needs Casey's explicit go-ahead, as does store submission.
