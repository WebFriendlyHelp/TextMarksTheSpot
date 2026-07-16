# Changelog

## 1.0.12

Login and signup pages land you in the form, and Shift+Z can now summon a landing anywhere.

- **Login pages are recognized.** A login form is just two fields, email and password, and the add-on's bar for "this page is a form" needed three, so login pages got no landing at all, just the two low not-found beeps. When the page's address plainly says it is a sign-in page (/login, /signin, /register and the like), two fields are now enough: the page title is announced and your focus lands in the email field. An article that merely mentions login in its address, like a "login-security-tips" post, is left alone.
- **Signup pages that open with a line of welcome text land in the form now too.** One short line like "You can join an existing organization or create one later." was enough to make the add-on read the whole page as an article, and the cursor landed on the password hint sitting in the middle of the form. Pages whose address says signup or register now keep their form treatment even with that intro line present.
- **Shift+Z now works on pages the add-on never saw load.** Switching back to a tab that was already open never triggers an automatic landing, and some web apps swap in a whole new page without a real page load, so the add-on has no way to know you arrived. Shift+Z used to answer "No saved landing on this page" and leave you there. Now it runs the detection on the spot and takes you to the result. The rule of thumb: if the page didn't speak and you want a landing, press Shift+Z.

Known gaps: sign-in pages that ask only for your email and save the password for a second page still get no landing (the two low beeps); Shift+Z works there like everywhere else. Recipe sites can still land on a marketing line or a reader's review, and script-drawn result widgets like the fast.com speed test are still not detected.

## 1.0.11

Stuck pages can no longer freeze NVDA.

- **A page that hangs while loading no longer locks NVDA up.** One news site froze NVDA for over ten seconds while the add-on tried to size the page up. Every step of that inspection now runs on a strict clock, so even a completely stuck page costs about a second, and the same page lands correctly once it finishes loading. Normal pages are unaffected.
- **Busy, link-heavy pages come up faster.** Counting the controls on a Stack Overflow topic listing took two extra seconds before the cursor moved. The count now stops as soon as it has learned enough, and the same landing arrives about a second and a half sooner.
- **When the clock does cut an inspection short, the add-on stops guessing.** A half-inspected page can look smaller and simpler than it really is. Before, that could make a busy page read as a small notice page, or in the worst case treat an article as a form and move your keyboard focus into a field. Now, when the add-on could not finish looking, it declines those judgment calls, stays quiet, and takes its usual second look a moment later.

Known gaps, unchanged from 1.0.10: recipe sites can still land on a marketing line or a reader's review, and pages that draw a single result widget by script, like the fast.com speed test, are not detected at all. The two low beeps there are the add-on saying it found nothing, not an error.

## 1.0.10

The add-on was quietly ignoring most page loads. It isn't anymore.

- **The add-on now actually runs when you open a page.** It was skipping roughly two out of every three page loads and doing nothing at all — no tone, no landing, no sign it had tried. This is why pages so often needed a refresh, or a press of Z, before anything happened. The cause was a wrong assumption about how NVDA tracks documents: the add-on decided "this is the same page as last time" by looking at an internal NVDA object, but NVDA reuses that object across navigations and simply changes the page address underneath it. The address is now what tells one page from another. This affects Firefox, Chrome and Edge alike.
- **The add-on no longer reads out a different paragraph than the one it moved you to.** On pages that are still loading themselves in, the page could shift under the add-on between choosing a paragraph and reading it, so it would move your cursor to the right place and then read something else entirely — a sports headline on a health story, a photo credit, a "we're loading your content" placeholder. It now checks that the paragraph is still there before speaking, and finds it again by its text if the page moved.
- **Long pages no longer freeze NVDA.** A long Bible chapter or a big newsletter could lock NVDA up for five to twelve seconds. Reading now stops at a time limit and lands with what it has, which on every page tested was the same paragraph it would have picked anyway.
- **Movie pages and news home pages no longer steal your keyboard focus.** IMDb film pages and TV station front pages were being treated as forms, so the add-on announced the title and then dropped your cursor into the site's search box. They are now recognised as content: an IMDb page lands on the plot summary.
- **Sign-in and account-creation pages are treated as forms again**, so you land in the first field instead of on the help text beside it.
- **The cursor skips more of the text that isn't the story.** Affiliate and referral disclosures ("this post contains affiliate links"), syndication notes ("republished with permission from our news partner"), marketing-consent blurbs ("by signing up, you agree to receive text messages"), photo credits, ad banners, and other stories' headlines all sat exactly where a story begins and were being read as if they were the article. They are now recognised and passed over.
- **Landings prefer real prose.** A landing spot should read like a sentence. Headlines, credits and labels that merely look substantial no longer win. Sites that are nothing but headlines, like link aggregators, still land on the first item.

Known gaps in this release: recipe sites can still land on a site's own marketing line ("all our recipes are tested in our test kitchen") or a newsletter promo, which is one Down-arrow away from the recipe; and a recipe page can land on a reader's review instead of the recipe itself.

## 1.0.9

The cursor no longer lands on copyright and legal text.

- On pages that draw their content in after the page first loads (Zoom webinar registration pages were the trigger), the only text present at first is the site's footer. The add-on would land on the copyright line and read it as if it were the page. Copyright lines and legal footer links are now recognized and never used as a landing spot; instead the add-on waits its usual moment and looks again once the real content has arrived.
- The same recognition applies everywhere: the Z key skips past copyright text too, and a footer line can no longer keep a registration form from being treated as a form.
- Registration pages that open with a real description, like a Zoom webinar signup, now land on the page title so you can arrow through the description and into the form. Previously the add-on jumped keyboard focus straight to the first field, skipping everything above it. Plain forms with no description still put you right on the first field.
- Going back to a page no longer yanks you to the top. When you press Back to return to search results or a list you were working through, your browser restores your place, and the add-on now respects it: on a page you have already visited, if your cursor is anywhere past the top, it stays quiet. First visits still land as usual, even on the occasional page where the cursor starts a little below the top. Links that point into a specific section of a page are respected too.
- Paragraphs that follow images or link-heavy blocks are no longer invisible. A stepping quirk in how the add-on read through the page could silently skip the paragraph right after a picture, a logo heading, or an author block, so that paragraph could never be landed on or found with Z. This was behind several "landed one paragraph too far" reports, including a welcome message that landed on the second paragraph instead of the first.
- News articles no longer land on "READ MORE" promo boxes or bylines. On sites like the Daily Mail, a related-story promo line and the all-caps byline sat right where the story begins and looked enough like article text to win the landing. Both shapes are now recognized as page furniture and skipped, so the cursor reaches the story's real opening paragraph. "Written by..." and "Posted by..." style bylines, like Phoronix uses, are skipped too.
- Pages whose address says they're content (news, blog, podcast, article) are no longer treated as forms just because they carry a comment box, login, search, and newsletter widgets. A podcast episode page with ten scattered form fields landed on the page title instead of the episode description; the address is now trusted as the tiebreaker. Pages whose address says form (register, signup, contact) keep the form treatment.
- Blog posts with newsletter signup widgets land on the article again. A post whose site offers no structural hints and carries a several-field subscribe widget could be mistaken for a form page, landing you on the title instead of the opening paragraph. Two long body paragraphs in a row now count as proof the page is an article. Real registration pages are unaffected.
- Posts on X (Twitter) now land on the post text. A tweet reaches NVDA as several short lines rather than one paragraph, and each line was too short to qualify as a landing, so the cursor settled on the generic "Post" heading. Runs of short lines that read like sentences are now recognized as real content, and the cursor lands on the first line. Menus and form labels, which are also runs of short lines but don't read like sentences, are unaffected.
- On short pages like confirmations, the Z key now reaches the message too. Z looks for meaty paragraphs, and on a page whose longest line is under its usual bar it used to say "Nothing else to land on" with the message sitting right there. When a page has no long paragraphs at all, Z now accepts shorter lines.
- Confirmation pages land properly again. Pages like "You have successfully registered" were being passed over (with the two-beep not-found sound) whenever they carried a stray control like an Add to Calendar button, because status pages were required to have no form controls at all. A status page with a clear confirmation message now tolerates a couple of controls, and the cursor lands on the message.
- Much faster page detection. The slowest part of every detection pass was the control-counting step, which could add a second or more of sluggishness per page (and much worse on some blogs). It now uses a far cheaper position-based check on most pages, which also fixes form detection: pages like Zoom's registration form previously counted as having zero form fields, so they were never treated as forms at all.
- When a form page hides its description inside collapsed sections (Zoom does this once you're signed in), the only readable text left may be a single question partway down the form, and the add-on landed there. It now lands on the page's heading instead, so you start at the top of the form with the collapsed Description section one arrow above you.
- One page visit, one landing. Some web apps quietly rebuild their page seconds after it loads (Zoom's registration page does this when it fills in your signed-in profile), and each rebuild used to trigger a fresh detection that yanked the cursor away from a good landing, sometimes to a worse spot. Now, once the add-on has landed on a page, later rebuilds of that same page leave your cursor alone. Press Z any time you want a fresh detection; going to a new page starts fresh automatically.

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
