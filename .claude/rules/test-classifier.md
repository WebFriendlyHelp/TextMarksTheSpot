---
paths:
  - "tests/test_classifier.py"
  - "tests/test_landing.py"
  - "tests/test_treeSummary.py"
  - "tests/test_walk_wiring.py"
  - "tests/test_chrome_scope.py"
  - "tests/test_scope_depleted.py"
  - "tests/test_scope_cache.py"
  - "tests/test_count_budgets.py"
  - "tests/test_diagnostic_optin.py"
  - "tests/test_find_needle.py"
  - "tests/test_hostname.py"
  - "tests/test_replay_corpus.py"
  - "tests/test_no_capture_corpus_committed.py"
  - "tests/test_regex_linear.py"
  - "tests/test_config_hosts.py"
  - "tests/test_plugin_guards.py"
  - "tests/nvda_stubs.py"
---

# test-classifier: full notes (from CLAUDE.md: Tests)

Full text behind the one-line summaries in the root CLAUDE.md, moved here verbatim on 5 November 2026 to keep the always-loaded instructions small. Claude Code loads this file automatically when it reads or edits one of the paths above; other agents should read it before changing that code. Keep it accurate when the behavior changes, and keep the CLAUDE.md summary in step.

Test-file inventory, since the names do not all announce what they guard:
`test_classifier.py` (intent gates), `test_landing.py` (the landing cascade),
`test_treeSummary.py` and `test_walk_wiring.py` (the walk's pure helpers and the
scan-to-select-to-verdict chain), `test_chrome_scope.py` and `test_scope_depleted.py`
(chrome positional scoping and the depleted net), `test_scope_cache.py` (the
`id(obj)` wrong-answer bug), `test_count_budgets.py` (the shared counts deadline),
`test_diagnostic_optin.py` (the privacy marker, including the audit that no bare
`log.debug` exists), `test_find_needle.py`, `test_hostname.py`,
`test_replay_corpus.py` and `test_no_capture_corpus_committed.py` (the corpus stays
out of git), `test_regex_linear.py` (the full-text detectors stay linear on hostile
text AND agree with the old patterns), `test_config_hosts.py` (canonical hostname
matching), and `test_plugin_guards.py`, which drives the GlobalPlugin itself through
the fakes in `tests/nvda_stubs.py`. That harness is the only unit-level coverage
`__init__.py` has; it proves decisions, not real NVDA behaviour, which stays with
the VM.
