# Changelog

## 0.1.0

First public release. Web only for now. Email handling is on the roadmap.

### What's new

- Automatic content detection. When a page finishes loading, the cursor moves to the first real paragraph and NVDA reads it, skipping nav, banners, and related-stories rails along the way.
- Form-page detection (registration, signup, contact, intake). The form title is announced and keyboard focus moves to the first input.
- Single-status-page detection (closed form, "thank you for submitting", maintenance, 404). The cursor lands on the status sentence.
- Key-result widget detection (speed test, weather, single-quote stock price, battery level). The cursor lands on the label so the value reads on the next arrow press.
- Re-run with `Z` in browse mode. Useful when the automatic pick was wrong, or when JavaScript loads new content without firing a fresh page-load event.
- Per-site exclusion. `NVDA+Z` adds or removes the current site. Press `Z` twice in quick succession on an excluded site for a one-time detection without changing the list.
- Speech mode is respected automatically. Talk, beeps, off, on-demand all behave the way you would expect. Status tones still play across modes so you know detection is running.
- If a site auto-focused a real input before we fire, we stay silent. The site already decided where you should start.

### Audio cues

- Short blip when detection starts.
- Soft pulse every half-second while detection is running so you know not to press a key yet.
- Two low beeps when detection finished but found nothing.
- No success tone. The spoken landing paragraph is the success signal.
