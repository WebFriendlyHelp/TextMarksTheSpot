---
paths:
  - "tests/test_chrome_scope.py"
  - "tests/sabotage_check.py"
---

# test-chrome-scope: full notes (from CLAUDE.md: Known limitations (deferred fixes))

Full text behind the one-line summaries in the root CLAUDE.md, moved here verbatim on 5 November 2026 to keep the always-loaded instructions small. Claude Code loads this file automatically when it reads or edits one of the paths above; other agents should read it before changing that code. Keep it accurate when the behavior changes, and keep the CLAUDE.md summary in step.

**Test the CHAIN, not the pieces.** `_chromePosVerdict` and `_selectScope` are pure and unit-tested, and that was not enough: both reviewers showed that deleting the `otherRanges` append left the whole suite green, because every test hand-built its own untrusted list. `tests/test_chrome_scope.py` now drives scan to select to verdict end to end with no hand-built lists. Assume the next safety input is deletable without a test noticing unless the chain itself is tested.

**A `chrome-none` scope existed briefly and was REMOVED 2026-07-19 as a merge blocker. Do not rebuild it, under any name.** It skipped chrome checking entirely on a page whose landmark enumeration yielded nothing, gated on `seen == 0 and exhausted and interactive_count > 0`. `exhausted` was doing the safety work and cannot: by the swallow above, a natively FAILED search arrives as `seen=0, exhausted=True`, byte-for-byte the shape of a genuinely landmark-free page. The interactive count does not corroborate either, since every quick-nav type runs through the same swallowing iterator. There is NO signal at the `LandmarkScan` layer that separates the two zero-seen cases; the per-chunk field stack is the only positive witness available. The cost of removal is real and accepted: on a landmark-free page with many chunks the walk returns to a roughly 14-dereference COM chain per chunk and may produce NO LANDING inside the 2 s budget. That is a silence, not a wrong landing, which is the direction guardrail 3 specifies. `tests/test_chrome_scope.py` pins the native-swallow shape and `tests/sabotage_check.py` fails when the shortcut returns, including under a new name and disguised as an empty exclusion list. One note on how it got in: the hazard had been looked at directly that same day and mis-filed as a pre-existing accepted risk. Noticing a hazard is not disposing of it.
