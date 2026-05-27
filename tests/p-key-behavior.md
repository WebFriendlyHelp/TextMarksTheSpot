# How NVDA's `P` (paragraph quick-nav) actually works

Pulled from the NVDA source on github.com/nvaccess/nvda. This is the basis for deciding whether a "press `P` once, then check what we got" strategy is enough on its own, or whether we still need Readability-style scoring on top.

## TL;DR — important correction

**On NVDA 2024.2 and later, `p` / `Shift+P` does NOT run plain paragraph quick-nav.** It runs TextNav, which was merged from Tony Malykh's `nvda-text-nav` add-on into NVDA core in 2024.2 and assigned to `p` by default. TextNav's rule: "find the next paragraph that contains one or more sentences separated by periods." Designed specifically to skip menus, ads, and non-textual content.

This explains the makeuseof.com miss perfectly: the figure caption "ChatGPT Web Search interface on an iPad screen." ends with a period. TextNav saw a sentence, treated it as a text paragraph, accepted it. So `p` IS already doing a smart heuristic — the bar is just low enough that single-sentence captions and pull quotes pass it.

On NVDA 2024.1 and earlier (or if the user has rebound `p`), the behavior reverts to raw paragraph quick-nav, described below.

## Raw paragraph quick-nav (the fallback / pre-2024.2 behavior)

Walks the page using NVDA's `textInfos.UNIT_PARAGRAPH` unit. What counts as a "paragraph" depends on:

1. The user's **Paragraph Style** setting (NVDA → Preferences → Settings → Document Navigation → Paragraph Style). Three choices:
   - **Handled by application** (default) — let the underlying text model decide.
   - **Single line break** — any line break = paragraph boundary. Almost everything becomes a paragraph.
   - **Multi line break** — blank line required for a paragraph boundary.
2. Which text model NVDA is using for that page:
   - **Firefox / Chromium (non-UIA)** — NVDA's virtual buffer (`source/virtualBuffers/`). Paragraphs come from block-level boundaries the VBuf already produces from the rendered DOM.
   - **Edge / Chromium UIA mode** — NVDA asks the UIA text provider for `TextUnit_Paragraph` (`source/UIAHandler/browseMode.py`, `source/NVDAObjects/UIA/web.py`). The browser decides what counts.

Practical consequence: with the default "Handled by application" setting on a Chromium-engine browser, `P` stops on anything the browser's accessibility tree labels as a paragraph-like block — which **includes figure captions, pull quotes, `<aside>` blocks, list items in some markup, and short standalone text nodes**. That matches what we saw on makeuseof.com (P landed on an image caption).

## Source pointers

- Enum: `source/config/featureFlagEnums.py` → `ParagraphNavigationFlag` (`APPLICATION`, `SINGLE_LINE_BREAK`, `MULTI_LINE_BREAK`).
- Config key: `source/config/configSpec.py` → `[documentNavigation] paragraphStyle = featureFlag(... behaviorOfDefault="application")`.
- Cycle script: `source/globalCommands.py` → `script_cycleParagraphStyle` (no gesture by default; user can assign one).
- Move logic: `source/cursorManager.py` and `source/editableText.py` → `_handleParagraphNavigation()` branches on the flag.
- Unit constant: `source/textInfos/__init__.py` → `UNIT_PARAGRAPH = "paragraph"`.
- Virtual buffer paragraph chunking: `source/virtualBuffers/__init__.py` → "get text in block (paragraph) chunks ... `UNIT_PARAGRAPH`".
- UIA paragraph iteration: `source/UIAHandler/browseMode.py` → `iterUIARangeByUnit(... UIAHandler.TextUnit_Paragraph ...)`.
- User guide: `userGuide.md` → "Paragraph Style" section under Document Navigation.

## What this means for "P-first" as our strategy

The Phase 1 idea was: hit `P` once from page load, see where it lands, and use scoring only as a tiebreaker. Three things now clearer:

1. **P does NOT define "paragraph" the way a human would.** It uses whatever block boundary the browser advertises. That's why an image caption is a valid stop — the browser reports the figure caption as a block. P has no concept of "real article body vs. peripheral text."
2. **Behavior varies across users.** Anyone who's switched their Paragraph Style to "Single line break" will get a very different stop position than the default. Anything we build on top of P must read `config.conf["documentNavigation"]["paragraphStyle"]` and reason about which model the user is on, OR override by walking `UNIT_PARAGRAPH` ourselves with our own definition.
3. **Behavior varies across browsers.** Edge (UIA) and Chrome (non-UIA VBuf) will give different paragraph boundaries on the same page. Test on both.

## Open questions to resolve before deciding the Phase 1 strategy

- Does NVDA's browse-mode **quick-nav** `P` honor `paragraphStyle`, or does it always use the underlying app's `UNIT_PARAGRAPH` regardless? `_handleParagraphNavigation` lives in `cursorManager.py` (and `editableText.py`) — confirm whether browse-mode `P` goes through that code path or through a separate QuickNavItem in `browseMode.py`.
- On the makeuseof.com miss, was the figure caption inside a `<figure>` element? If yes, we can write a one-line filter: "if P landed inside an `<aside>` / `<figure>` / `<figcaption>` / `[role='complementary']`, don't accept it as the article start, fall through to scoring."
- On the steve quayle hit (top headline), the page is a link list, not an article. Should the add-on classify aggregator/index pages as "no clear article" and stay silent (guardrail #3), or treat first-headline as a valid stop? Likely silent.

## Fixture data so far (from the field probe)

- **stevequayle.com** — P landed on top headline link. News aggregator home page. Borderline — first headline is arguably the right answer, but the page isn't really an article. Likely belongs in the "silent" category once we add page-type classification.
- **makeuseof.com article** (writing-habits-that-make-you-sound-like-chatgpt) — P landed on a figure caption ("ChatGPT Web Search interface on an iPad screen"). **Miss.** Desired target: article body opener or author bio.
- **groups.io** — P landed on hero marketing blurb ("Groups.io is the ultimate group email service..."). Product landing page. Reasonable hit for that page type.

More fixtures needed before we commit to a strategy. Target categories: news articles (NYT, WaPo, BBC), blog posts (Substack, Medium, WordPress), reference (Wikipedia, MDN, GitHub README), forum threads (Reddit, HN, Discourse), docs (Stripe, Django, Python docs).

## Prior art worth studying (Tony Malykh's add-ons)

Both are GPL, both still useful even though TextNav merged into core.

- **BrowserNav** — github.com/mltony/nvda-browser-nav. Active. Hugely featureful. The relevant piece for us is `addon/globalPlugins/browserNav/paragraph.py` — a working `Paragraph` class that wraps NVDA's `textInfo` and exposes `.next` / `.previous`, `.text`, `.attributes`, `.roles`, `.headingLevel`, `.home` / `.end`, `.find(text)`, `.findRegexp()`, `.findQuickNav(itemType)`, `.previousHeading` / `.nextHeading2` / ... / `.previousLink` / `.nextEdit` / `.previousArticle` / etc., and `.document`. This is the abstraction we'd be writing anyway. We should borrow the API shape (and possibly the file outright, since GPL-to-GPL is fine), not reinvent it. Note also: BrowserNav already has a "SkipClutter" concept (default skips empty paragraphs; user-configurable to skip other clutter via bookmarks) — that's adjacent to our problem space.
- **TextNav** — github.com/mltony/nvda-text-nav. Discontinued but instructive. Source reveals the exact "one or more periods = sentence-paragraph" heuristic, which is the rule now in NVDA core for `p`. If we want to raise the bar (e.g., require N sentences, or minimum paragraph length, or weighted sentence detection), that's where the lineage starts.

For the SPEC, the practical move is:
- Phase 1 trigger: call TextNav (i.e. just press `p` programmatically, or call NVDA's underlying `textParagraph` quick-nav iterator) from the start of the document, then apply our own filters before accepting the position.
- Filters to consider: reject if landing element role is `figure` / `figcaption` / `aside` / `complementary`; reject if text length below threshold; reject if inside a class/id pattern from `patterns.py` blacklist; reject if NVDA reports the parent is in a `nav` / `banner` / `contentinfo` landmark.

That's a much smaller MVP than reimplementing Readability scoring. It also stays composable with `Z` (re-trigger), guardrail #6 (honor focused control), and the per-site disable list.

## Implication for the SPEC

If P-first turns out to land correctly on 70%+ of real article pages once we filter out `<figure>` / `<aside>` parents, the Phase 1 MVP shrinks dramatically: trigger fires → press P internally → check parent element role/class → accept or fall back to scoring. That's a much smaller MVP than implementing Readability-style scoring from scratch.

If P-first stays in the 50% range even with the figure/aside filter, we keep the scoring approach as primary and treat P as an upper-bound sanity check.

Either way: we need more probe data on real pages before locking the approach.
