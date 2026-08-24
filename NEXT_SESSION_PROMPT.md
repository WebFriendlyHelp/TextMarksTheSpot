# Next session prompt (paste into a fresh session)

We're picking up Text Marks the Spot on `main`. Everything below is current as
of **2026-08-24**.

Read `CLAUDE.md`, `DEBUGGING.md`, and the TOP entry of `implementation-notes.md`
first. 381 tests plus 1 xfail: `python -B -m pytest tests/` from the repo root
(the `-B` matters, see the harness traps in `tests/sabotage_check.py`).

Build locally with `.\build.ps1`, never bare `scons`. It leaves exactly ONE file
at the repo root, `TextMarksTheSpot.nvda-addon`, always the newest build. Bare
`scons` still emits the versioned name and CI depends on that, so do not rename
the SCons target.

## State as of 2026-08-24

`scope-hardening` is MERGED into `main` and the branch is history. `main` is at
**v1.0.15**, released 2026-08-24, and the NV Access store has it: PR 11069 in
`nvaccess/addon-datastore` merged at 13:33 UTC, which closed a gap where the
store had been serving 1.0.6 since June. Store users had missed eight releases,
including the 1.0.10 fix for the add-on skipping roughly two of every three page
loads, so a bug report older than that date is almost certainly that bug.

`chrome-pos-attempt` still preserves a dead first design. Read its commit
message before rebuilding anything like it, because the interlock it depends on
is unimplementable.

**NVDA 2026.2 rc1 is the running build on Casey's machine and the add-on is
compatible with no code changes.** That was verified rather than assumed, on
2026-08-24: 2026.1 was the API-breaking release and 2026.2 declares no break;
every NVDA symbol the add-on touches survives both; and 2026.1's fixes to
`TextInfo.collapse()` and `OffsetTextInfo.move()` are absorbed by the walk's
existing forward-progress guard. The detail is in SPEC.md's Compatibility
section. `addon_lastTestedNVDAVersion` is `2026.2.0` and that is correct.

Casey has been SOAKING this code as his daily driver since roughly 2026-08-18.
It was running under a 1.0.14 label until the 1.0.15 release, so "1.0.14" means
two different things depending on whether you mean the July GitHub release or
his local build. v1.0.15 ends that ambiguity.

## What to do next

1. **Ask Casey how the soak went, and read the log before theorising.** The
   persistent log (`%APPDATA%\nvda\TextMarksTheSpot-perf.log`) survives
   restarts; the decision trace lives only in `nvda.log` and is gone two NVDA
   restarts later. You can always reproduce by re-loading the page.
   **BOTH now require the opt-in marker**
   (`%APPDATA%\nvda\TextMarksTheSpot-diagnostics-enabled`, then restart NVDA).
   On a fresh dev machine, forget it and your own data silently stops arriving,
   which looks exactly like broken logging. Asking a USER for a log is a
   two-step request, and they deserve to be told what the file holds.
2. **Still unobserved in production: `field_drops` doing real work.** Everything
   measured so far was landmark-free or simple-nav. Pages in Casey's history
   with no `<main>` but marked chrome: thurrott.com, bleepingcomputer,
   disabilityscoop, breitbart (6 chrome ranges), vovsoft.
3. **THE COUNTS** are the dominant cost, 646-666 ms of ~730 ms, with
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
- Both concrete code items in this list were re-verified on 2026-08-24 and still
  hold (`_ARTICLE_LIMIT = 4` against `classifier.py:457`'s `>= 5`, and
  `unscoped-depleted` has still never appeared in the perf log). The rest of the
  list is as-of 2026-07-19; confirm against the source before acting on it.

## How to work on this project

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
