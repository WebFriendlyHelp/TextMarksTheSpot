---
paths:
  - "tests/test_regex_linear.py"
---

# test-regex-linear: full notes (from CLAUDE.md: Tests)

Full text behind the one-line summaries in the root CLAUDE.md, moved here verbatim on 5 November 2026 to keep the always-loaded instructions small. Claude Code loads this file automatically when it reads or edits one of the paths above; other agents should read it before changing that code. Keep it accurate when the behavior changes, and keep the CLAUDE.md summary in step.

**Every detector that runs on a chunk's FULL text must be linear time** (security
audit, 2026-09-24). Those run on NVDA's main thread inside one regex call the walk
deadline cannot interrupt, and a web page controls the text: two quadratic patterns
let a 40,000-space paragraph freeze NVDA for five seconds, reproduced on the VM.
When adding one, avoid adjacent unbounded runs that can split the same characters
(`\s*x?\s*`) and scans that restart from every candidate (`\(...[^)]*\)$`), and add
it to `test_regex_linear.py` with a timing test and an equivalence test.
