---
paths:
  - "tests/nvda_stubs.py"
---

# nvda-stubs: full notes (from CLAUDE.md: Tests)

Full text behind the one-line summaries in the root CLAUDE.md, moved here verbatim on 5 November 2026 to keep the always-loaded instructions small. Claude Code loads this file automatically when it reads or edits one of the paths above; other agents should read it before changing that code. Keep it accurate when the behavior changes, and keep the CLAUDE.md summary in step.

NVDA-dependent BEHAVIOUR (what the walk really yields, what NVDA really speaks, which events really fire) is NOT unit-testable. The GlobalPlugin's DECISIONS are, through the fakes in `tests/nvda_stubs.py` (2026-09-24), and real behaviour is testable on the throwaway VM with real NVDA and Edge (`~/.claude/sr-web-harness/nvda-addon/`); otherwise the surface stays manual via the log viewer (`NVDA+F1`, search for `[TMTS]`). Each new NVDA API gets a 5–20 line standalone probe add-on before it appears in real code — see "API probes before real code" below and SPEC.md.
