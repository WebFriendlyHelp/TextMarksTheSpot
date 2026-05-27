# Text Marks the Spot

An NVDA add-on that jumps the browse cursor to the start of real content when you open a web page. Pure heuristic; nothing runs over the network.

## Download and install

Latest stable build, always current:

https://github.com/WebFriendlyHelp/TextMarksTheSpot/releases/latest/download/TextMarksTheSpot.nvda-addon

Download that file. Open it (double-click in File Explorer, or `Enter` on it from a focused list). NVDA prompts to install — accept and restart NVDA when it asks.

To uninstall later: NVDA → Tools → Manage add-ons → select Text Marks the Spot → Uninstall → restart NVDA.

If you would rather pick a specific version, the [releases page](https://github.com/WebFriendlyHelp/TextMarksTheSpot/releases) lists them all.

The add-on is also being submitted to the NVDA Add-on Store. Once accepted there, NVDA's own auto-update mechanism will keep it current for you.

## What it does

When a web page finishes loading in browse mode, the add-on looks at the structure and picks a place to land. What that means depends on the kind of page.

On an article (Wikipedia, news, blog post, a WordPress homepage with a real body), the cursor moves to the first substantial paragraph and NVDA reads it. You skip the nav, the cookie banner, and the "skip to main content" link without having to press H or P to get there.

On a list or index page (news homepage, search results, a grid of cards), the cursor moves to the first headline so you can start scanning with `H`. No auto-read here. The headlines are short and you would probably skip past them anyway if it tried.

On a form page (signup, login, contact, intake), the form's title is announced and keyboard focus moves to the first field.

On a single-status page (closed form, "thank you for submitting", maintenance, 404), the cursor lands on the status sentence. That is usually the only thing on the page that matters.

On a key-result widget (speed test, weather, single-quote stock price, battery level), the cursor lands on the label so the value reads naturally on the next arrow press.

If the page already put focus on a search box, login field, or compose area, the add-on stays silent. The site already decided where you should start.

On a video player, dashboard, app, or page it cannot make sense of, the add-on is silent and gets out of the way.

## Usage

Open a page. The cursor jumps to the right place and NVDA reads it. That is the whole thing.

Press `Z` in browse mode to re-run detection if the automatic pick was wrong, or to re-trigger after dynamic content loaded. Every other NVDA key (`Tab`, `H`, `F`, arrow keys, everything) behaves exactly as before. The add-on only binds `Z` and `NVDA+Z`.

Outside browse mode (terminals, edit fields, native apps), `Z` types a normal letter.

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
