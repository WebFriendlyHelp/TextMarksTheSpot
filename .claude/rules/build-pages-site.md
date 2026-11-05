---
paths:
  - "tools/build_pages_site.py"
  - ".github/workflows/pages.yml"
---

# build-pages-site: full notes (from CLAUDE.md: Where things live)

Full text behind the one-line summaries in the root CLAUDE.md, moved here verbatim on 5 November 2026 to keep the always-loaded instructions small. Claude Code loads this file automatically when it reads or edits one of the paths above; other agents should read it before changing that code. Keep it accurate when the behavior changes, and keep the CLAUDE.md summary in step.

- `tools/build_pages_site.py` + `.github/workflows/pages.yml` — publish `readme.md` (as index.html) and `changelog.md` (as changelog.html) to the user-facing site, `https://webfriendlyhelp.github.io/TextMarksTheSpot/`, on every push to main that touches either file. It is the repo's website link and the manifest's `addon_url`; point users there, not at `#readme`. A release whose changelog is written is therefore also a site update; there is no separate step.
