## Summary

Describe what this pull request changes.

## Why This Change

Explain the problem, user need, or issue this PR addresses.

## Testing

- [ ] `python -m pytest tests/ -q`
- [ ] `scons` builds the add-on cleanly
- [ ] Manual NVDA testing (Firefox and Chrome) where relevant
- [ ] Tested across NVDA speech modes (talk, beeps, off, on-demand) where relevant
- [ ] AI-assisted output, if used, was reviewed for correctness and third-party code concerns

Describe the testing you performed:

## Accessibility Check

- [ ] Keyboard-only interaction still works; NVDA's built-in keys not rebound
- [ ] NVDA's speech mode is honored (content via `speech.speak*`, status tones via `tones.beep`)
- [ ] No emoji or Unicode box-drawing in any spoken or logged string
- [ ] User-facing text reviewed for clarity
- [ ] Images or graphics added in this PR have appropriate alt text

Describe any accessibility impact:

## User-Facing Changes

- [ ] `changelog.md` updated if user-visible behavior changed
- [ ] `readme.md` updated if usage or settings changed

## Notes

Add anything reviewers should pay attention to.
