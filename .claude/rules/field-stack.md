---
paths:
  - "probes/field_stack/**"
---

# field-stack: full notes (from CLAUDE.md: Known limitations (deferred fixes))

Full text behind the one-line summaries in the root CLAUDE.md, moved here verbatim on 5 November 2026 to keep the always-loaded instructions small. Claude Code loads this file automatically when it reads or edits one of the paths above; other agents should read it before changing that code. Keep it accurate when the behavior changes, and keep the CLAUDE.md summary in step.

**The control-field stack is the walk's PRIMARY scope answer now, and it is barely
described anywhere but the source.** `_landmarkScopeFromFields` reads the leading
control run of each chunk's own `TextInfo` and returns a tri-state verdict (not
chrome / chrome / unknown) with no parent dereference at all; unknown falls through
to the positional or identity path exactly as before. It is gated by
`_fieldsCarryLandmarks`, which matches the TextInfo's MRO against the Gecko
virtual-buffer class BY NAME AND MODULE, because `field['landmark']` is written by
the backend's `_normalizeControlField`, not by any TextInfo contract: Gecko writes it
and Chromium inherits it, WebKit does not write it at all, and MSHTML is excluded on
purpose for want of probe evidence. Do NOT re-gate this on `backendName` — Chromium
does not declare its own and inherits Gecko's string, so that gate cannot tell the
engines apart. If NV Access ever renames the Gecko class the gate fails silently to
False everywhere and the add-on quietly reverts to parent chains, correct but slow,
which is exactly what `field_backend=y|n` on the `[TMTS walk-phase]` line exists to
make visible in one page load. `probes/field_stack/` is the probe this was built on.
