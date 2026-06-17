# Text Marks the Spot

Sighted readers can glance at a web page and find where the article actually starts in a second or two. They tune out the menu, the cookie banner, the related-stories list without thinking about it. Screen reader users have always had to walk past all of that one item at a time.

Text Marks the Spot does that walking for you. When a page loads, the cursor goes to where the content starts and NVDA reads it. No keypress needed. From there your usual NVDA keys take over.

Everything runs locally. No network calls, no AI, no telemetry.

## Hear it in action

[A short audio clip of the add-on flipping through three web pages](https://github.com/WebFriendlyHelp/TextMarksTheSpot/raw/main/flipping-webpages.mp3) (mp3).

## Download and install

[Get Text Marks the Spot](https://github.com/WebFriendlyHelp/TextMarksTheSpot/releases/latest/download/TextMarksTheSpot.nvda-addon).

Open the downloaded file. NVDA prompts to install. Accept and restart NVDA when it asks.

To uninstall later: NVDA → Tools → Manage add-ons → select Text Marks the Spot → Uninstall → restart NVDA.

If you would rather pick a specific version, [the releases page](https://github.com/WebFriendlyHelp/TextMarksTheSpot/releases) lists them all.

The add-on is also being submitted to the NVDA Add-on Store. Once accepted there, NVDA will keep it current for you automatically.

## How it works

When a page finishes loading in browse mode, the add-on looks at the page's structure and decides what kind of page it is. An article gets a different landing than a list of stories, a form, or a "thank you" page.

If the add-on isn't confident about what the page is for, it stays silent and your normal NVDA keys behave the way they always have. A wrong guess is worse than no guess.

## What it does

The landing depends on the kind of page:

- Article (Wikipedia, news story, blog post): the cursor moves to the first real paragraph and NVDA reads it. You skip the menu, the cookie banner, and the "skip to main content" link without pressing H or P.
- List or index page (news homepage, search results, a grid of cards): the cursor moves to the first headline so you can start scanning with `H`. No auto-read.
- Form page (signup, login, contact): the form's title is announced and focus moves to the first field.
- Status page (closed form, "thank you for submitting", maintenance, 404): the cursor lands on the status sentence.
- Result widget (speed test, weather, single-quote stock price, battery level): the cursor lands on the label so the value reads on the next arrow press.
- Search box already focused: silent. The site already decided where you should start.
- Video player, dashboard, app, or anything unrecognized: silent.

## Keyboard commands

The add-on binds three gestures. Every other NVDA key behaves the way it always has.

- `Z` in browse mode: scan forward from the cursor to the next real paragraph. The add-on skips headings (use NVDA's `H` for those) and skips ads, menus, and share buttons.
- `Shift+Z` in browse mode: return to where the add-on first placed you on this page. A quick jump back.
- `NVDA+Z` in browse mode: add or remove the current site from the exclusion list. NVDA asks before changing it. On an excluded site, press `Z` twice quickly for a one-time detection that does not change the list.

Outside browse mode (terminals, edit fields, native apps), `Z` types a normal letter.

## Tips and tricks

- The cursor lands on the first real paragraph automatically. If that pick is off, press NVDA's `H` to find the heading of the section you want, then press `Z` to drop onto the first paragraph below it.
- `Shift+Z` at any time returns you to where the add-on first placed you. Handy after wandering with arrow keys when you want to start over.
- On slow-loading sites (Gmail, some news pages), the content sometimes shows up after the add-on's first scan. The add-on retries once automatically about a second and a half later. You can also press `Z` to trigger a fresh scan from where you are.
- `NVDA+S` cycles NVDA's speech mode and the add-on respects it. In beeps mode NVDA beeps for each line. In off mode the cursor still moves but nothing is spoken.

## Disabling on a site you do not want it on

Press `NVDA+Z` in browse mode. NVDA asks whether to add the current site to the exclusion list. Press Y to confirm. The add-on stays silent on that site afterward.

To re-enable a site, press `NVDA+Z` again on it.

For a one-time detection on an excluded site, press `Z` twice in quick succession. The add-on runs once without changing your exclusion list.

## See where the cursor landed visually

If you have some vision, NVDA can draw a colored box around the cursor. Open `Preferences -> Settings -> Vision` and turn on "Highlight focus" or "Highlight browse mode caret". Useful for low-vision users and for showing the add-on working to sighted colleagues, family, or clients.

## Known limitations

- Email is not supported yet. Web only for now. Email handling is on the roadmap.
- Very sparse pages (business cards, contact-only pages). The add-on stays silent because there is nothing substantial to land on. Your normal NVDA keys work the way they always have.
- Slow-loading pages (Gmail, single-page apps). Content sometimes shows up after the add-on's first scan. It retries once automatically. You can also press `Z` to trigger a fresh scan.
- Articles with the intro in an unusual place. Some sites (Apple Support is one) put the article's intro somewhere the add-on cannot see. The cursor lands on the next paragraph instead. Use `Shift+H` to back up to the page title and arrow down to read the intro.

## Reporting bugs and getting help

[Open an issue on GitHub](https://github.com/WebFriendlyHelp/TextMarksTheSpot/issues) if something does not work the way you expect.

A bug report is most useful when it includes:

- The add-on version (visible in NVDA's add-on manager)
- Your NVDA version
- The URL where the issue happened, if it is not private
- A short description of what you heard versus what you expected

If you would rather not file publicly, email [help@webfriendlyhelp.com](mailto:help@webfriendlyhelp.com) instead. Either way I will get back to you.

For questions, ideas, or general feedback, use [the Discussions tab](https://github.com/WebFriendlyHelp/TextMarksTheSpot/discussions) in the same repository.

## Privacy

Everything runs locally. No network calls, no telemetry, no data collection.

## Compatibility

NVDA 2024.1 or newer. Last tested with NVDA 2026.1.1. Pure Python, no native libraries. Works in 32-bit and 64-bit NVDA.

## License

GPL v2.

## Author

Casey Mathews. Web Friendly Help LLC. [help@webfriendlyhelp.com](mailto:help@webfriendlyhelp.com).

NVDA Certified Expert (2017, 2019, 2022, 2025).

## For developers

See `SPEC.md` and `CLAUDE.md` in the project repository for the design document, build instructions, and contributor notes.
