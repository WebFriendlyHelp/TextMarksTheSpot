# Accessibility

Text Marks the Spot is an NVDA add-on, so its whole audience is screen reader users. The thing it cares about most is staying out of the way: when it isn't sure where the content starts, it says nothing and leaves your cursor alone.

## Supported environments

- NVDA 2024.1 or later. Last tested on NVDA 2026.2.
- Web pages in browse mode, in the browsers NVDA supports. Email is not supported yet.

## What the add-on does to protect your normal NVDA use

- It binds three gestures and leaves every other NVDA key alone. The readme lists them.
- It respects NVDA's speech mode. In beeps mode NVDA beeps, and in off mode the cursor still moves but nothing is spoken.
- Any site where it gets in the way can be added to the exclusion list with NVDA+Z, and the add-on stays silent there afterward.
- It makes no network calls and collects nothing. See SECURITY.md.

## Known barriers

These are listed in the readme under Known limitations and repeated here so they're easy to find:

- Very sparse pages, like business cards or contact-only pages. The add-on stays silent because there is nothing substantial to land on.
- Slow-loading pages such as Gmail and other single-page apps. Content can appear after the first scan. The add-on retries once, and pressing Z starts a fresh scan.
- Articles that put their intro somewhere the add-on can't see (Apple Support is one). The cursor lands on the next paragraph. Shift+H backs up to the page title.

## Reporting a barrier

If the add-on lands you in the wrong place, talks over something, or conflicts with another add-on's gesture, please open an issue. Include your NVDA version, the browser, the page address if you can share it, and what you expected to hear.

You can also email help@webfriendlyhelp.com if you'd rather not post publicly.

## Contributing

CONTRIBUTING.md covers setup. For accessibility specifically: a change has to stay correct across NVDA's speech modes, must not take over any gesture beyond the three the add-on already binds, and user-facing wording should read naturally when spoken.
