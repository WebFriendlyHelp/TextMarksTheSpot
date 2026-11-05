---
paths:
  - "addon/globalPlugins/TextMarksTheSpot/feedback.py"
---

# feedback: full notes (from CLAUDE.md: Architecture)

Full text behind the one-line summaries in the root CLAUDE.md, moved here verbatim on 5 November 2026 to keep the always-loaded instructions small. Claude Code loads this file automatically when it reads or edits one of the paths above; other agents should read it before changing that code. Keep it accurate when the behavior changes, and keep the CLAUDE.md summary in step.

- `feedback.py` — three audio cues via `tones.beep`. `working()` = 500 Hz / 30 ms at detection start. `progressStart()` / `progressStop()` = 400 Hz / 20 ms pulse every 500 ms while detection runs, on a `threading.Timer` background thread so beeps still play while the main NVDA thread is busy walking the tree. `notFound()` = **two** 220 Hz / 60 ms beeps with an 80 ms gap, played on a background thread so the sequence doesn't block NVDA — the two-tone rhythm is distinctive from working() (single short blip) and the progress pulse (single beep, repeated). Distinct pitches (500 / 400 / 220) so they're easy to tell apart by ear. No success tone — the spoken landing paragraph IS the success signal. **Override of original SPEC**: the SPEC said "failure is silent"; we play `notFound()` for genuine no-result outcomes after the retry attempt (the user asked for this), but still stay silent for SILENT_FOCUS_HONORED per guardrail #6.
