# Changelog

## 1.0.8

Better landings on news articles that lead with a photo.

- When a story opens with a large photo, the cursor sometimes landed on the photo's caption or credit line instead of the story. Captions and photo credits are now recognized and skipped, so the cursor goes to the article itself.
- On stories that begin with a city dateline, like "DENVER -", the short opening line was sometimes passed over and the cursor dropped onto a longer paragraph further down. That opening line is now treated as the real start of the story, so the cursor lands there.

## 1.0.7

Declares NVDA 2026.2 as a tested version. No code changes from 1.0.6 — the same article-page landing improvements, now with 2026.2 marked as tested after a real run on the beta.

## 1.0.6

Better landings on blog posts and articles that don't mark where their main content begins.

- A lot of blogs and news sites never tell NVDA where the article starts. There's no "main" region for the add-on to aim at. On those pages it used to wade through the site menu, the comment thread, and the footer right along with the post, and the cursor often came down partway through instead of at the top. Now, when a page has exactly one article and no main region, the add-on reads just that article, with the menu, comments, and footer left out, and lands on the article's real opening line.
- On those same pages the cursor used to skip a short opening line and land further down, on the first item of a list or a later section. Now it stops on the opening line where the post actually begins.
- Checked against the NVDA 2026.2 beta. Nothing needed to change; it runs fine there.

## 1.0.5

Documentation pass. No code changes from 1.0.4.

- Readme rewritten to be friendlier to readers who do not work in tech. "Nav" became "menu", "JavaScript-heavy single-page apps" became "slow-loading pages", and the "structural header block above the main landmark" got replaced with "an unusual place where the add-on cannot see".
- Raw URLs replaced with markdown links carrying descriptive text. Email addresses are now `mailto:` links so they open in the user's mail client.
- The "What it does" list and "Known limitations" list dropped the bolded-prefix style for plain bullets.
- New section: Hear it in action, with a short audio clip of the add-on flipping through three web pages.
- The add-on store description and "What's new" text were rewritten to avoid internal jargon ("teaser-skip", "chrome", "content-section heading matcher").

## 1.0.4

Detection-quality improvements and a usability overhaul of the Z key.

### Landing quality

- Better landings on news articles. When the first paragraph after the headline is a short teaser and the next paragraph is much longer, the cursor lands on the longer one. Catches the CNET-style "X is a huge time saver, once you commit them to memory" then real article opening pattern.
- Better landings on small directory pages. A short page with one heading and only chrome paragraphs (PDF-viewer disclaimers, share buttons) below now lands on the title heading instead of a footer paragraph. Caught on the Montgomery County Probate Court forms page.
- News articles no longer get treated as forms. CNET-style pages with a sidebar newsletter signup and a comment box dispatch as articles, not forms.
- The content-section heading matcher (which looks for "Description", "Features", "Overview" type labels) no longer fires on long sentence-style headings that happen to contain those words. Caught on Thurrott.
- Share-and-bookmark widget text and PDF-viewer disclaimer paragraphs are now filtered out as chrome.

### Z key reshape

- Z scans forward from the cursor for the next substantial content paragraph. Previously it advanced to the next heading. NVDA's H already handles next-heading; Z is meant to add value built-in keys do not.
- The scan skips chrome paragraphs (tag lists, share-link URLs, screen-reader instructions, PDF-viewer disclaimers) so Z lands on content.
- When nothing eligible is below the cursor, the add-on says "Nothing else to land on" and the cursor stays put.
- Z always plays the short blip when pressed, including on the second and later presses.

### New gesture

- Shift+Z returns the cursor to the add-on's last automatic landing on this page. No recalculation, just a quick jump back.

### Documentation

- Hear it in action: a short audio clip of the add-on flipping through three web pages.
- New sections: How it works, Tips and tricks, Known limitations, Reporting bugs and getting help.
- Rewritten add-on description focused on the user experience rather than the internals.

## 1.0.3

The initial landing on a news article was sometimes a social-share button's URL parameter — text like `share-offsite url=https%3A%2F%2F...` that accessibility tooling exposes as a paragraph. Long enough to clear the "substantial paragraph" bar, but not real prose. Now filtered out alongside the existing tag-list and accessibility-instruction filters.

Caught on Fox21 News article pages where LinkedIn share buttons sit near the top of `<main>`.

## 1.0.2

Fixes for the Z-sequence behavior introduced in 1.0.0.

- Z now always plays the short blip when pressed, including on sequence advance. Before, only the first Z press on a page made a sound; subsequent presses ran silently and felt like nothing happened.
- The Z-sequence stops when the next heading is more than 30 nodes away from the last landing. On a short news article with no internal headings, the next heading in NVDA's tree is often a sidebar widget far down the page. Walking the Z-sequence into that widget was wrong. Now Z says "No more sections on this page" and resets when it would otherwise jump into chrome.

Internal: addon name is `TextMarksTheSpot` in PascalCase (the install path under `%APPDATA%\nvda\addons\`). 1.0.0 used the lowercase form. Users upgrading from 1.0.0 need to uninstall the old `textMarksTheSpot` entry from NVDA's add-on manager before installing 1.0.2.

## 1.0.0

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
