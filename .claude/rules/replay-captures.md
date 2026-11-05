---
paths:
  - "tests/replay_captures.py"
  - "tests/test_replay_corpus.py"
  - "tests/test_no_capture_corpus_committed.py"
---

# replay-captures: full notes (from CLAUDE.md: Diagnostic logs)

Full text behind the one-line summaries in the root CLAUDE.md, moved here verbatim on 5 November 2026 to keep the always-loaded instructions small. Claude Code loads this file automatically when it reads or edits one of the paths above; other agents should read it before changing that code. Keep it accurate when the behavior changes, and keep the CLAUDE.md summary in step.

A third file, the **capture log** (`%APPDATA%\nvda\TextMarksTheSpot-captures.jsonl`), holds one JSON record per detection that carries every field the classifier and landing finders read, so `tests/replay_captures.py` reproduces a real decision offline with no NVDA. Same marker gate, self-rotates at 2 MB. **Its corpus is deliberately NOT in the repository**: `tests/fixtures/local/` is gitignored, `tests/test_replay_corpus.py` skips when the file is absent so a fresh clone runs green, and `tests/test_no_capture_corpus_committed.py` fails if a capture-shaped record is ever tracked again. Add corpus cases BY HAND from public pages worth pinning. Never paste the raw log into an issue or bulk-copy it into the repo; it is a record of someone's browsing, and a data file shaped like one invites the next person (or the next AI session) to add a real one.
