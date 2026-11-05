---
paths:
  - "tests/**"
  - "tests/test_classifier.py"
  - "tests/test_landing.py"
  - "tests/sabotage_check.py"
  - ".github/workflows/tests.yml"
  - "probes/**"
---

# tests: full notes (from CLAUDE.md: Tests)

Full text behind the one-line summaries in the root CLAUDE.md, moved here verbatim on 5 November 2026 to keep the always-loaded instructions small. Claude Code loads this file automatically when it reads or edits one of the paths above; other agents should read it before changing that code. Keep it accurate when the behavior changes, and keep the CLAUDE.md summary in step.

Pure-Python unit-test suite at `tests/` covering the classifier (`tests/test_classifier.py`) and landing finders (`tests/test_landing.py`). Run with `python -B -m pytest tests/` from the project root. Requires `pip install pytest` once (no NVDA needed — the classifier and landing finders are deliberately pure-function for exactly this reason). **Use `-B`, not bare `python`.** CPython validates a `.pyc` against the source's mtime and SIZE, so a source file edited and re-run within the same second can execute the PREVIOUS bytecode and report a pass about code that was never loaded. That is the trap `tests/sabotage_check.py` documents, and it is not specific to sabotage runs; it bites any edit-then-immediately-rerun loop.

**Lint and format are BOTH gated, and ruff is PINNED to the version in `.github/workflows/tests.yml`.** The pin is not fussiness: an unpinned install put ruff 0.16.7 against a tree that 0.14.5 called clean and drew 218 errors, so without it some unrelated future push fails on code its author never touched. Bumping the pin is a deliberate act that comes with its own diff to clean up. The tree was reformatted in one commit on 2026-09-10, listed in `.git-blame-ignore-revs` so it does not sit on top of the reasoning history that lives in this codebase's comments; run `git config blame.ignoreRevsFile .git-blame-ignore-revs` once on a fresh clone to get the same locally (GitHub honors the file on its own). Two things about the ruff config are worth knowing before touching it. `probes` is excluded, because those are frozen throwaway add-ons still calling the pre-2026-09-06 snake_case API. And `format.line-ending` is `auto` rather than `lf`, because `.gitattributes` sets `* text=auto` so git already stores LF regardless of the working tree, and pinning ruff to `lf` on a CRLF Windows checkout made `ruff format --check` report every file in the repository.
