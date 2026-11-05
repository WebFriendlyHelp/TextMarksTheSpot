---
paths:
  - "site_scons/site_tools/NVDATool/addon.py"
---

# addon: full notes (from CLAUDE.md: Releasing (CI publishes — do NOT create the release by hand))

Full text behind the one-line summaries in the root CLAUDE.md, moved here verbatim on 5 November 2026 to keep the always-loaded instructions small. Claude Code loads this file automatically when it reads or edits one of the paths above; other agents should read it before changing that code. Keep it accurate when the behavior changes, and keep the CLAUDE.md summary in step.

**A side-loaded add-on will NOT show "What's new" even when the changelog is correct.** NVDA's store reads it from the installed manifest fine (`addonStore/models/addon.py:230-232`), but the menu item is gated on the add-on having come from the store (`gui/addonStoreGui/viewModels/store.py:289-291`). So the absence of "What's new" on a local install is expected and is NOT evidence of a packaging bug. Don't go chasing it.
