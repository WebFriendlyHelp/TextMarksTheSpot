# Text Marks the Spot

Sighted readers can glance at a web page and find where the article actually starts in a second or two. They tune out the nav, the cookie banner, the related-stories rail without thinking about it. Screen reader users have always had to walk past all of that one item at a time.

Text Marks the Spot does that walking for you. When a page loads, the cursor goes to where the content starts and NVDA reads it. No keypress required. From there your usual NVDA keys take over and you read on the way you always have.

Everything runs locally. No network calls, no AI, no telemetry.

## Hear it in action

A short audio clip of the add-on flipping through three web pages:

[Flipping web pages (mp3)](https://github.com/WebFriendlyHelp/TextMarksTheSpot/raw/main/flipping-webpages.mp3)

## Download and install

Latest stable build, always current:

https://github.com/WebFriendlyHelp/TextMarksTheSpot/releases/latest/download/TextMarksTheSpot.nvda-addon

Download that file. Open it (double-click in File Explorer, or `Enter` on it from a focused list). NVDA prompts to install — accept and restart NVDA when it asks.

To uninstall later: NVDA → Tools → Manage add-ons → select Text Marks the Spot → Uninstall → restart NVDA.

If you would rather pick a specific version, the [releases page](https://github.com/WebFriendlyHelp/TextMarksTheSpot/releases) lists them all.

The add-on is also being submitted to the NVDA Add-on Store. Once accepted there, NVDA's own auto-update mechanism will keep it current for you.

## How it works

When a page finishes loading in browse mode, the add-on inspects the structure NVDA already exposes (headings, paragraphs, landmarks, form fields) and decides what kind of page it is. An article gets a different landing than a list of stories or a form or a single-status page.

That decision is made from the page's accessibility tree alone. No HTML parsing, no network calls. If the add-on isn't confident about what the page is for, it stays silent and your normal NVDA keys behave the way they always have. A wrong guess is worse than no guess.

## What it does

When a web page finishes loading in browse mode, the add-on looks at the structure and picks a place to land. What that means depends on the kind of page.

On an article (Wikipedia, news, blog post, a WordPress homepage with a real body), the cursor moves to the first substantial paragraph and NVDA reads it. You skip the nav, the cookie banner, and the "skip to main content" link without having to press H or P to get there.

On a list or index page (news homepage, search results, a grid of cards), the cursor moves to the first headline so you can start scanning with `H`. No auto-read here. The headlines are short and you would probably skip past them anyway if it tried.

On a form page (signup, login, contact, intake), the form's title is announced and keyboard focus moves to the first field.

On a single-status page (closed form, "thank you for submitting", maintenance, 404), the cursor lands on the status sentence. That is usually the only thing on the page that matters.

On a key-result widget (speed test, weather, single-quote stock price, battery level), the cursor lands on the label so the value reads naturally on the next arrow press.

If the page already put focus on a search box, login field, or compose area, the add-on stays silent. The site already decided where you should start.

On a video player, dashboard, app, or page it cannot make sense of, the add-on is silent and gets out of the way.

## Keyboard commands

The add-on binds three gestures. Every other NVDA key behaves the way it always has.

- `Z` in browse mode: scan forward from the cursor for the next substantial content paragraph. Useful when the automatic pick was off, or when you want to skim past chrome between sections. The add-on skips headings (use NVDA's `H` for those) and skips chrome paragraphs like share-button widgets and PDF-viewer disclaimers.
- `Shift+Z` in browse mode: return to the add-on's last automatic landing. Snaps you back to where the add-on first placed you on this page. No recalculation, just a quick jump back.
- `NVDA+Z` in browse mode: add or remove the current site from the exclusion list. NVDA asks before changing the list. On an excluded site, press `Z` twice in quick succession for a one-time detection that does not change the list.

Outside browse mode (terminals, edit fields, native apps), `Z` types a normal letter and `NVDA+Z` passes through to the host application.

## Tips and tricks

A few ways to get more out of the add-on:

- The cursor lands on the first content paragraph automatically. If that pick is off, use NVDA's `H` to find the heading of the section you want, then press `Z` to drop onto the first content paragraph after it.
- Press `Shift+Z` at any time to return to where the add-on first placed you on this page. Handy after wandering with arrow keys or quick-nav letters when you want to start over.
- On JavaScript-heavy sites (Gmail, some news pages, single-page apps), the page sometimes finishes loading after the add-on's first scan. The add-on retries once automatically about a second and a half later. You can also press `Z` yourself to trigger a fresh scan from where you are.
- `NVDA+S` cycles speech mode. The add-on respects it. In beeps mode NVDA replaces the spoken landing paragraph with a beep. In off mode the cursor still moves but nothing is read. The short status tones from the add-on play in every mode so you know it is working.
- On an excluded site, press `Z` twice in quick succession to run detection once without removing the site from the exclusion list. Useful when you have blocked a domain but landed on an unusual page where you want the add-on to work this one time.

## Disabling on a site you do not want it on

Press `NVDA+Z` in browse mode on the site you want to exclude. NVDA asks whether to add the current site to the exclusion list. Press Y to confirm. The add-on stays silent on that site after that.

To re-enable a site, press `NVDA+Z` again on it. Same prompt, this time to remove it from the list.

If a site is on the exclusion list but you want detection once (you landed on an unusual page and just want it to work this one time), press `Z` twice in quick succession. The add-on runs detection once without changing your exclusion list.

## How it works with NVDA's speech mode

NVDA has four speech modes you cycle through with `NVDA+S`: talk (normal speech), beeps (one beep per line instead of speech), off (silent), and on-demand (only speak when asked).

You do not need to configure anything. The add-on routes spoken text through NVDA's normal speech path, so whatever mode you have set is what you get. In talk mode the landing paragraph is read. In beeps mode NVDA beeps and you arrow forward. In off mode the cursor still moves but nothing is spoken. In on-demand mode NVDA decides.

The short status tones (a brief blip when detection starts, a soft pulse while it works) play in every mode. Those are not speech, they are "the add-on is busy" signals, the same way NVDA's own progress beeps work. They let you know to wait a moment before pressing another key.

## See where the cursor landed visually

If you have some vision, NVDA can draw a colored box around the cursor position. Open `Preferences -> Settings -> Vision` and turn on "Highlight focus" or "Highlight browse mode caret". Useful for low-vision users and for showing the add-on working to sighted colleagues, family, or clients.

## Known limitations

A few cases where the add-on either stays silent or picks a less-than-ideal landing. Worth knowing before you file a bug.

- **Email is not supported yet.** Web only for now. Email handling is on the roadmap.
- **Very sparse pages.** Business-card sites, contact-only landing pages, link directories. The add-on stays silent because there is no substantial paragraph to land on. NVDA's normal navigation works the way it always has.
- **JavaScript-heavy single-page apps.** Sites like Gmail, Square Dashboard, or Crowdcast sometimes finish loading content after the page-load event fires. The add-on's first scan can miss late-arriving content. It retries once automatically about a second and a half later, or you can press Z yourself to trigger a fresh scan.
- **Articles where the lede sits above the main landmark.** Some sites (Apple Support is one) place the introductory paragraph in a structural header block above `<main>`. The add-on lands on the first paragraph inside main, which can mean skipping the lede. Use Shift+H to back up to the page title and arrow down to read the lede manually.

## Reporting bugs and getting help

If something does not work the way you expect, the best place to file it is GitHub:

https://github.com/WebFriendlyHelp/TextMarksTheSpot/issues

A bug report is most useful when it includes:

- The add-on version (visible in NVDA's add-on manager)
- Your NVDA version
- The URL where the issue happened, if it is not private
- A short description of what you heard versus what you expected

If you would rather not file publicly, email help@webfriendlyhelp.com instead. Either way I will get back to you.

For general discussion, questions, or feature ideas, use the Discussions tab in the same repository:

https://github.com/WebFriendlyHelp/TextMarksTheSpot/discussions

## Privacy

Everything runs locally. No network calls, no telemetry, no data collection.

## Compatibility

NVDA 2024.1 or newer. Last tested with NVDA 2026.1.1. Pure Python, no native libraries. Works in 32-bit and 64-bit NVDA.

## License

GPL v2.

## Author

Casey Mathews. Web Friendly Help LLC. help@webfriendlyhelp.com.

NVDA Certified Expert (2017, 2019, 2022, 2025).

## For developers

See `SPEC.md` and `CLAUDE.md` in the project repository for the design document, build instructions, and contributor notes.
