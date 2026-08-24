# Text Marks the Spot — Design Spec

NVDA add-on that automatically jumps to the real start of content (and starts reading) when a web page or email opens. Skips ads, cookie banners, navigation chrome, quoted reply chains, and signatures.

This file is the load-bearing handoff for any new session that starts in this folder. Read it first.

## The problem

Screen reader users waste real time hunting for where the actual content starts. Pages bury articles under ads/cookie banners/nav. Emails bury new content under quoted replies, headers, and signatures. NVDA's `p` (paragraph) and `h` (heading) quick-nav help but require pressing keys repeatedly. Reader-mode browser extensions exist but are manual and don't help in email clients.

This add-on does the work automatically with zero keypresses on page/message open.

## Guardrails (apply to every decision below)

These are the principles the add-on must satisfy. They override any feature that conflicts with them.

1. **Never supplant natural NVDA navigation.** Tab, `h` (headings), `f` (form fields), `t` (tables), `k` (links), `b` (buttons), and every other built-in NVDA key continues to do exactly what it has always done. Users have muscle memory; we do not break it. The add-on binds only `Z` — nothing else.
2. **Act only when the page's purpose is unambiguous.** If detection isn't confident about what kind of page this is (article, form, email, search, app), the add-on does nothing — no jump, no tone, no fallback "best guess." Silent. The user proceeds with normal NVDA keys.
3. **When in doubt, do nothing.** A wrong auto-jump is worse than no auto-jump. Wrong jumps train users to distrust the add-on; silence on an ambiguous page is fine because the user still has all their normal navigation.
4. **Confidence threshold gates every action.** Every detector returns a position AND a confidence score. Below the threshold, the result is treated as no-result and the add-on stays silent. Threshold is configurable in code so we can tune as we test against real fixtures.
5. **The user is always in charge.** Per-site disable list, settings panel toggles, and the natural NVDA keys all give the user a clean way to opt out or override. The add-on is opinionated about *defaults*, not about *taking control*.
6. **Honor website-placed focus on form controls.** If the page (or email client) auto-focuses a real form control on load — search box, login field, compose body, any `<input>`/`<textarea>`/`<select>`/contenteditable — the add-on does nothing. No cursor move, no auto-read, no tone. The site has already told the user where to start; stealing that focus would force them to Tab back. This check runs before any detection branch fires. The manual `Z` key still works if the user wants to override.

## Design decisions (locked)

1. **Auto-read on successful landings is the shipped default.** This supersedes the early "position only, no auto-read" draft. For ARTICLE / LIST / NOTICE / KEY_RESULT, the add-on moves the browse-mode caret, cancels speech only at the moment it has a landing, expands to the paragraph, and calls `speech.speakTextInfo` so the user hears exactly where they landed. FORM uses a different path: `ui.message` announces the form title, then focus moves to the first form field so NVDA's own focus speech announces the control. Video, app, unknown, and focus-honored pages stay silent.
2. **Manual content hotkey: `Z`.** Confirmed unused by NVDA browse-mode quick navigation. In the current implementation, `Z` scans forward from the current browse cursor to the next substantial content paragraph, skipping headings and known chrome. On an excluded site, double-press `Z` runs one-time detection without changing the exclusion list.
3. **Per-site disable list via `NVDA+Z`.** Users can opt out for specific domains without a settings panel. `NVDA+Z` toggles the current hostname after confirmation. A per-app list and settings panel remain future work.
4. **Form-as-primary-goal detection.** Only treat as a form page when:
   - Readability scoring finds NO strong article candidate, AND
   - A form with multiple fields occupies the main content area, AND
   - Optional URL/title signals (`/register`, `/signup`, `/apply`, `/intake`, `/contact`) reinforce
   - NOT triggered by a newsletter widget sitting inside an article page
   - Honors guardrail #2: if any of the above is uncertain, the add-on does nothing and the user uses `f` to find form fields normally. We do not "best guess" form pages.
5. **Audio feedback is intentionally present.** This supersedes the early "no audio feedback" draft. Real-world detection can be slow, so the shipped flow plays a short working tone when detection starts, a soft repeating pulse while the tree walk runs, and two low beeps only after the retry attempt finds nothing. There is no success tone; the spoken landing text is the success signal. Focus-honored pages remain completely silent.
6. **Visual highlight at the detected spot.** Low-vision users and sighted observers (demo viewers, family/colleagues working alongside the blind user) benefit from seeing where the cursor landed.
   - **Phase 1 (MVP) — free, no code:** Rely on NVDA's built-in vision highlight system. When we move the browse cursor to the detected position, NVDA's existing browse-mode caret highlight (if enabled in `Preferences → Settings → Vision`) shows a box around it automatically. User-facing docs tell users to enable it. Zero implementation cost.
   - **Phase 2 — custom flash effect:** Add a `visionEnhancementProviders/` module to the add-on. Brief colored overlay around the detected element for ~500 ms on detection success, then fades. Doesn't clutter the screen long-term. High demo/marketing value. NVDA Vision Enhancement Provider API was added in 2020.4 — within our compatibility floor. Settings toggle for the flash, default ON.
   - **Phase 3 — skip unless requested:** persistent custom highlight with user-configurable color. NVDA's built-in highlight already covers the persistent case.
7. **Intent-first architecture (the load-bearing decision).** The add-on classifies every page or message by what its purpose is to the user, then dispatches to a per-intent strategy. This replaces the earlier "one universal heuristic" framing. The user-model: match what a sighted person automatically does on each page type — sighted users don't apply one rule everywhere either, they read articles, scan lists, fill forms, and ignore dashboards according to what the page is for.

   Intents and behaviors:

   - **Article** (news article, blog post, Wikipedia entry, docs page, single long-form piece). Goal: jump past headline / dek / byline / date / social-share / image-figures / related-articles rail to the **first substantial body paragraph**. Auto-read ON.
   - **List of articles** (news index home, search results page, YouTube home / channel, Google results, blog index, forum thread index). Goal: jump to the **first content heading of the largest same-level heading cluster inside `<main>`** — the first story / result / video / thread title. Auto-read OFF. User scans with NVDA's `H` key, picks one, clicks.
   - **Form** (signup, login, contact, intake, medical intake). Goal: jump to the **first form field**. Auto-read OFF. (Existing locked decision #4 is the form-detection rule; it becomes a branch of this architecture.)
   - **Notice / status page** (closed form, thank-you page, 404, maintenance, access-denied, short confirmation). Goal: land on the first meaningful status sentence.
   - **Key-result widget** (speed test, weather, stock quote, battery level, currency conversion). Goal: land on the label so the user can arrow forward to hear the value and unit.
   - **Dashboard** (account home, portal, monitoring widget, settings page). Too varied for a useful default. **Silent.** No jump, no tone. User uses NVDA's normal keys.
   - **Video / media-consumption page** (YouTube watch page, Spotify web, podcast page, video-first article). Don't compete with the audio. **Silent.** User uses NVDA's normal keys.
   - **App** (webmail compose, web IDE, calculator, drawing tool, anything that's a control surface). **Silent.**
   - **Unknown** (below confidence on any intent). **Silent.** Guardrail #3.

   Chrome to skip inside an article (the "first substantial body paragraph" filter):
   - Byline / author elements: `<address>`, `[rel="author"]`, `[itemprop="author"]`, `class*="byline"`, `class*="author"`, `class*="credit"`
   - Date / timestamp wrappers: `<time>`, `class*="date"`, `class*="published"`
   - Social share clusters: `[aria-label*="share"]`, `class*="share"`, `class*="social"`, runs of social-media icon links
   - Figure / image caption blocks: `<figure>`, `<figcaption>`, `[role="img"]`, `[role="figure"]`
   - Comments / discussion sections (unless the user has explicitly navigated there)
   - Related-articles / recommended rails (often a sibling cluster of short H2/H3/H5 elements after the article body)
   - Newsletter signup widgets embedded mid-article
   - The body paragraph we accept must be ≥ ~100 chars AND a sibling of a paragraph cluster (3+ similar-length siblings). Single-sentence pull quotes don't qualify.

   Email intents (HTML or plain text — same classifier, different chrome list):

   - **Personal / work message** — jump past headers, quoted-reply chain, and signature to the **first paragraph of new content**. Existing regex strip (Decision #5's text rules) is the implementation. HTML email adds: skip the per-client wrapper, the preheader hidden text, and signature blocks marked with `<blockquote>` or `<table class="signature">`.
   - **Marketing / newsletter** — skip preheader, masthead/logo block, hero image-only rows, footer/unsubscribe rail. Jump to the **first headline or body paragraph** of the actual content. Same paragraph-cluster filter as article mode.
   - **Transactional / notification** (order confirmation, password reset, account alert) — the gist is usually a single sentence near the top. Jump to the first `<p>` after the header block.
   - **Calendar invite / system-generated** — different layout per client. **Silent** for now.

   Classifier signals (order matters — first confident match wins). Important constraint: the classifier only uses signals visible in NVDA's accessibility tree. **It does not read `<meta>` tags, `<head>` content, or `og:`/`schema.org` properties** — those aren't in the virtual buffer, and fetching the HTML separately would violate the no-network / privacy guardrail and blow the speed budget. The signals below are all walk-the-tree only.

   1. **Focused control check (guardrail #6)** — if `api.getFocusObject()` is an editable form control (`Role.EDITABLETEXT`, `Role.COMBOBOX`, `Role.LISTBOX`, `Role.CHECKBOX`, `Role.RADIOBUTTON`, or has `STATE_EDITABLE`), silent regardless of intent.
   2. **Form intent** — count visible interactive inputs inside the `<main>` landmark (or the root tree interceptor if no `<main>`). Threshold: ≥ 3 inputs, AND those inputs span ≥ 50% of the heading-to-heading body content. A newsletter signup widget with 1-2 inputs inside an article does NOT trigger form intent. URL patterns like `/signup`, `/register`, `/contact`, `/apply`, `/intake` are tiebreaker positive signals.
   3. **Article intent** — `<article>` element present (`Role.ARTICLE`) OR `<main>` contains a paragraph cluster of ≥ 3 paragraphs of ≥ 100 chars each, with the cluster's combined text length ≥ ~500 chars. URL patterns like `/article/`, `/news/`, `/blog/`, `/post/`, `/story/` are tiebreaker positives. Multiple sibling `<article>` elements demote this to list intent (see #5).
   4. **Video / media intent** — `Role.VIDEO` or video-player widget in the primary main-content position (not as a sidebar embed). URL patterns like `/watch`, `/video/`, `/v/`, `/embed/` are tiebreaker positives. We don't try to detect whether autoplay is actually playing (too brittle); presence of a primary video element is enough to go silent.
   5. **List intent** — multiple `<article>` siblings (`Role.ARTICLE` count ≥ 3) OR a same-level heading cluster of ≥ 5 inside `<main>` where the cluster headings have < 200 chars of body text between consecutive members. URL patterns like `/search`, `/results`, `/category/`, `/tag/`, `/feed`, or a root path on a known-aggregator host shape are tiebreakers.
   6. **App intent** — `<main>` is dominated by interactive controls (buttons / inputs / custom widgets) with no paragraph cluster ≥ 3 substantial paragraphs and no dominant heading cluster. Webmail compose, web IDE, calculator, drawing tool fit here. URL patterns like `/app/`, `/compose`, `/dashboard`, `/admin/` are tiebreakers — but #2 (form) takes priority if input count is high.
   7. **Unknown** — no signal above its threshold → silent. Guardrail #3.

   Confidence handling: each signal returns (intent_or_none, confidence_0_to_1). The classifier picks the highest-confidence intent above the threshold (initially 0.6, tunable). If two intents tie above threshold, pick the higher-priority intent in the list above. If nothing clears the threshold, unknown.

   The classifier is the load-bearing piece. Every per-intent strategy is small (10-30 lines). The classifier is what determines whether the add-on does the right thing or the wrong thing.

8. **Z is a content-forward scan today; richer sequences are deferred.** The current shipped `Z` behavior starts from the user's current browse cursor and moves to the next substantial content paragraph below it. It deliberately skips headings because NVDA's `H` key already handles headings. The broader "next likely thing" sequences below remain a future design direction, not current behavior.

   Page-type taxonomy and Z sequences (each step is one Z press; the auto-trigger fires step 0 on page load):

   - **Article / blog / news:**
     0. Auto: article start
     1. Z: next major section (next h2/h3 boundary)
     2. Z: next major section
     3. Z: comments section if present
     4. Z: announce "no more sections"

   - **Form-centric page:**
     0. Auto: first form field
     1. Z: first error message if any (ARIA alert, aria-invalid, class containing "error" / "invalid")
     2. Z: next empty required field
     3. Z: submit / next button
     4. Z: terms / privacy link if present

   - **Email:**
     0. Auto: new message body (past quote/headers/signature)
     1. Z: first important sentence (heuristic — contains "?", "please", "need", "by [date]")
     2. Z: first link (often the call to action)
     3. Z: quoted reply chain start (if user wants history)
     4. Z: signature

   - **Search results:**
     0. Auto: first result (if detected)
     1. Z: next result
     2. Z: next result (repeats until end)

   - **Web app / dashboard:**
     0. Auto: usually nothing (no clear content)
     1. Z: primary CTA / first interactive element

   Sequence state resets when the document changes (URL change, new email opened, navigation event). Each press announces "Jumped to X" via `ui.message` so the user knows the result.

   **Guardrail enforcement on Z:**
   - Current behavior: Z never invents an intent-specific sequence. It only scans forward to the next substantial content paragraph from the user's actual cursor position.
   - If there is no eligible paragraph below the cursor, it announces "Nothing else to land on" and does not wrap.
   - Z never rebinds or interferes with NVDA's built-in quick-nav keys. Tab, h, f, t, k, b, etc. continue to work exactly as NVDA defines them.

   **Current and deferred behavior:**
   - **Current:** Z scans forward to next content paragraph; Shift+Z returns to the saved automatic landing, or runs one-time detection when none is saved for the page (stale-tab rescue; exclusion still honored); NVDA+Z toggles the site exclusion list.
   - **Deferred:** article section sequence, form-context sequence (errors, next empty, submit), email sequence, and search-result sequence.

   Resist the urge to ship the full sequence until the simpler content-forward scan has more real-world feedback. Each larger sequence should get its own user feedback loop.

## Approach

- **Pure heuristic, zero AI, zero network.** No API keys, no privacy concerns, no per-use cost. Snappy. Free forever.
- **Architecture is intent-first** (see locked decision #8). The add-on classifies the page or message by purpose, then dispatches to a per-intent strategy. The detection modules below are the strategies, not standalone heuristics.
- **Web detection (article intent):** Walk NVDA's already-parsed browse-mode virtual buffer to find the first substantial body paragraph inside `<article>` or the main content region, skipping byline / date / social-share / figure / related-rail chrome (see decision #8 chrome list). Paragraph-cluster filter: candidate must be ≥ 100 chars AND a sibling of 3+ similar-length paragraphs. No re-parse of HTML.
- **Web detection (list intent):** Walk NVDA's heading tree, find the largest cluster of same-level headings inside `<main>` (or not inside `<header>` / `<nav>` / `<aside>`), jump to the first heading in that cluster.
- **Email detection:** Same intent classifier as web (personal/work, marketing, transactional, system). For plain-text email: regex-based quoted-reply strip (`On <date>, <name> wrote:`, `>`-prefixed lines, "From: ... Sent: ..." blocks) + signature strip (trailing K lines after valediction or org-keyword pattern, or `-- ` delimiter). For HTML email: apply the article-intent strategy plus an email-specific chrome list (preheader hidden text, masthead/logo block, signature blocks in `<blockquote>` or `<table class="signature">`, footer/unsubscribe rail). Same detection function applies regardless of email client — the trigger fires on whatever message-body area gains focus.
- **Auto-trigger mechanism:** The `GlobalPlugin` hooks `event_documentLoadComplete` ONLY, not broad `event_gainFocus`. **Correction (2026-07-14, verified in NVDA source):** this spec previously named `event_treeInterceptor_gainFocus` as a second hook. It CANNOT fire in a GlobalPlugin, on any NVDA version — it is a plain method core calls directly on the TreeInterceptor object (`eventHandler.py:425`), never dispatched through the global-plugin event chain (`eventHandler.py:141-167`). It fired 0 times in 31 page loads. The handler has been deleted; do not re-add it. `documentLoadComplete` is the only trigger and always was. `event_gainFocus` fires on routine focus changes and alt-tab restores, so it is too noisy for this add-on. Detection is gated by TreeInterceptor identity, URL cooldown, site exclusion, and the focus-editable guard before any tone or tree walk runs. Manual `Z` bypasses the identity and URL cooldown gates because the user explicitly requested a scan.
- **Speed budget:** Under ~50ms per detection. Pre-compiled regex at module load. Walk-only, no re-parse. Cache last-detected position keyed by document URL / message identity.

## Privacy stance

Everything runs locally. No data leaves the user's machine. No telemetry. No optional AI path (rejected — adds privacy concern and friction). If we ever add AI later, it would be opt-in with user-supplied API key and clearly marked.

## File layout

```
Text Marks the Spot/
├── README.md                              project overview
├── SPEC.md                                this file
├── manifest.ini                           NVDA add-on metadata
├── buildVars.py                           SCons build config
├── .gitignore
├── addon/
│   ├── doc/en/readme.md                   user-facing docs (shown in store)
│   └── globalPlugins/TextMarksTheSpot/
│       ├── __init__.py                    GlobalPlugin entry, event hooks
│       ├── classifier.py                  pure-logic intent classifier
│       ├── tree_summary.py                NVDA-binding: tree → TreeSummary
│       ├── detection/
│       │   ├── __init__.py                per-intent strategy dispatcher
│       │   ├── web.py                     article landing strategy
│       │   ├── email.py                   email landing strategy (Phase 2)
│       │   └── form.py                    form landing strategy (Phase 2)
│       ├── patterns.py                    regex + class/id chrome blacklists
│       ├── context.py                     browser vs webmail vs app detection
│       ├── trigger.py                     stub; trigger logic currently lives in __init__.py
│       ├── sequence.py                    Z key per-intent sequence state
│       └── config.py                      settings storage (confspec) — backs the site-exclusion list
└── tests/
    ├── README.md                          how to test detection against fixtures
    └── fixtures/
        ├── web/                           saved HTML snippets
        └── email/                         saved message bodies
```

## Compatibility

- **Minimum NVDA:** 2024.1 (Python 3.11)
- **Last tested NVDA:** 2026.2.0 (Python 3.13, 64-bit)
- **Re-verified against NVDA 2026.2 rc1 (2026-08-24, running build):** no code changes required, and none were made. 2026.1 was the API-breaking release, not 2026.2; 2026.2's "changes for developers" declares no break, and its only deprecations are in `speechDictHandler` (`ENTRY_TYPE_*`, `SpeechDictEntry`/`SpeechDict` moved to `speechDictHandler.types`), which this add-on does not import. Every NVDA symbol the add-on touches was checked against BOTH releases' removal lists and all survive: `speech.speakTextInfo`, `speech.cancelSpeech`, `ui.message`, `api.getFocusObject`, `browseMode.BrowseModeDocumentTreeInterceptor`, `controlTypes.OutputReason`/`.State`, the `textInfos` constants, `gui.mainFrame`. Nothing here uses `versionInfo.version_*` (the change that broke ~15 store add-ons), `IDT_TONE_DURATION`, MathPlayer, or the moved screen-curtain modules. **Two 2026.1 fixes touch the UNIT_PARAGRAPH walk and are benign here:** `TextInfo.collapse()` no longer advances to the next paragraph in some cases, and `OffsetTextInfo.move()` now reaches document end. The walk's forward-progress guard already tolerates either, since it expands at the collapsed end and forces a move only when `compareEndPoints` shows no advance, so the collapse fix merely makes the guard fire less often and the move fix costs at most one extra terminating iteration. 2026.2's default `NVDA+x` does not collide with `Z` / `Shift+Z` / `NVDA+Z`. Confirmed loading on the running 2026.2rc1 (NVDA log: "Requires API: (2024, 1, 0). Last-tested API: (2026, 2, 0)") with 143 detections logged that day, so `addon_lastTestedNVDAVersion` stays `2026.2.0` in `buildVars.py`. NOTE: the earlier version of this bullet said "we hook `event_treeInterceptor_gainFocus` rather than subclassing". That was already false when written and is corrected at the Auto-trigger bullet: the hook cannot fire in a GlobalPlugin and has been deleted.
- **Pure Python, no C extensions** — works without rebuild on the 32-bit NVDA builds up to 2025.3 and the 64-bit builds from 2026.1 on (2026.1 dropped 32-bit Windows and moved to Python 3.13, 64-bit)
- License: GPL v2 (NV Access store convention)
- Versioning: major.minor.patch

## Phase 0 — must do BEFORE writing code in the new session

1. **Investigate "Content priority reading"** (NVDA store, v0.3, publisher "lamb"). Fetch its actual repo / detail page and confirm what it does. If it overlaps with this add-on, decide: pivot, differentiate, or proceed with awareness. Store page only listed it in the index — the detail page or its GitHub repo will have the real description.
2. **Confirm `Z` is also unused by JAWS quick-nav** in case we port later. Casey is JAWS Certified — a future JAWS script pack would want consistent keys.
3. **Pick a final add-on ID slug** for the manifest. Current proposal: `TextMarksTheSpot`. The store uses this as the addon ID URL slug.

## Current shipped behavior

Status: working public add-on, version 1.0.8 in `buildVars.py`, end-to-end in Firefox and Chrome browse mode against a varied corpus of real sites.

**Implemented:**
- Intent-first classifier (`classifier.py`) over `TreeSummary`. Current intents include `SILENT_FOCUS_HONORED`, `FORM`, `ARTICLE`, `LIST`, `APP`, `NOTICE`, `KEY_RESULT`, and `UNKNOWN`.
- NVDA-binding layer (`tree_summary.py`) walks browse-mode text by `UNIT_PARAGRAPH`, captures parallel textInfo positions, computes notice-keyword and caption flags from full chunk text, and logs `[TMTS perf]` timing data.
- Tree-summary fallback is now main-scoped walk to unscoped walk. The older intermediate chrome-filtered fallback was removed for performance because it used the same unreliable parent-chain mechanism as the main-scoped walk.
- Positional article scoping is implemented for the no-`<main>` / exactly-one-`<article>` case. This excludes nav before the article and comments/footer/sidebar after it, then marks `TreeSummary.positionally_scoped=True`.
- Landing strategies (`detection/web.py`) cover ARTICLE, LIST, FORM, NOTICE, KEY_RESULT, and Z forward scan. Article landing skips tag lists, share-link payloads, accessibility instructions, figure captions/photo credits, and protects short news dateline ledes.
- Trigger (`__init__.py`) hooks `event_documentLoadComplete` only (see the correction above — the `treeInterceptor_gainFocus` hook never fired and is gone). It debounces by **TreeInterceptor identity AND URL together** (a TI is bound to an accessibility-tree ROOT, not a document: NVDA reuses it across navigations while the URL changes in place underneath it, so identity alone was swallowing two thirds of real page loads) plus a same-URL cooldown, honors the site exclusion list, pre-checks editable focus before any feedback tone, and schedules one retry after 1500 ms when the first attempt produces no action.
- Action: ARTICLE / LIST / NOTICE / KEY_RESULT move the browse-mode caret, cancel speech only immediately before the add-on speaks, expand to the paragraph, and call `speech.speakTextInfo`. FORM announces the form title with `ui.message` and moves keyboard focus to the first form input.
- Gestures: `Z` scans forward from the current cursor to the next substantial content paragraph; `Shift+Z` returns to the saved automatic landing, or runs one-time detection when none is saved for the page (tab switches fire no documentLoadComplete, so a revisited tab has nothing saved; exclusion still honored); `NVDA+Z` toggles the current site in the exclusion list. Outside browse mode, `Z` and `Shift+Z` pass through.
- Audio feedback: short working tone at detection start, pulse while detection runs, two low beeps after retry finds nothing, no success tone.
- Unit-test suite currently covers classifier, landing logic, hostname handling, and tree-summary node filtering.
- Build: `scons` from the project root produces the `.nvda-addon` using NV Access's official addon template (buildVars.py, sconstruct, site_scons/). `probes/build_probe.py` is still used for the small probe add-ons.

**Deferred to later phases:**
- Settings panel and per-app disable list. Per-site exclusion is already wired via `NVDA+Z`.
- Email detection (Phase 2) — plain-text + HTML email body extraction.
- Video-specific behavior remains silent. FORM is already implemented.
- Z key sequence state machine for richer next-likely actions. Current Z is a content-forward scan, not a per-intent sequence.
- Translation infrastructure — English only.
- **Visual saliency detection (designed, deferred).** Some sites (fast.com, hand-coded blogs, older WordPress themes) style what is logically a heading as a styled `<div>` instead of an `<h1>` — so NVDA's role-based heading detection misses it. The principled fix is a saliency walker that records `(text, role, x, y, w, h)` per chunk from `obj.location`, computes the page's median chunk height and typical vertical rhythm, and flags chunks that are significantly taller than median, surrounded by larger-than-typical whitespace, or horizontally centered. Those get treated as synthetic headings in `main_nodes`. The principle is "what sighted readers notice" — visual difference from neighbors — not "matches a heading formatting pattern." Estimated 200–300 lines + a tuning loop against real pages. **Does NOT fix fast.com** by itself; fast.com's separate problem is that NVDA's `UNIT_PARAGRAPH` walk produces only 4 nodes total on that page (heavy styled-div DOM), so the speed widget isn't in our walk at all and saliency can't see it. Fast.com would need both saliency + a richer walk strategy.

**Known issues / limitations:**
- Speed budget (<50ms target) currently missed. Real-world detection is 0.5–10s depending on page complexity. Caching helped 3-10x but the underlying NVDA tree walk on large pages is intrinsically slow.
- "Speech leak" window — when navigating between pages, the prior page's speech can play for ~1s before our `cancelSpeech` fires. Cancellation runs at TI-changed gate (closest signal we get); the gap is the latency from user click to our event handler firing.
- Some pages produce zero in-scope nodes despite `<main>` being detected. The three-tier walk fallback handles this on most sites but a few remain stubborn (likely shadow DOM, iframe boundaries, or unusual ancestor wrapping). When the unscoped walk also yields zero, we stay silent.
- Landing on summary callouts vs the actual body narrative — if a page has a TL;DR summary cluster before the chronological narrative, we land on the summary (it's the first cluster). Acceptable in practice; the user is still on body content and can arrow-down to read.
- LIST landing on the first heading cluster sometimes lands on a sidebar / related-stories rail when those have more headings than the main story list. Not yet differentiated.
- `nodes=0` on certain modern news sites (intermittent — same site, different sessions) suggests NVDA accessibility-tree state can affect what surfaces. Restarting NVDA and Firefox clears it.

## Phase 1.5 — first follow-up after MVP

- Z press counter and sequence state machine
- Article-context Z sequence (next major section)
- `ui.message` announce-after-Z so the user knows what just happened

## Phase 2 — after Phase 1.5 lands

- Email content detection (Outlook desktop, Outlook web, Gmail web, Thunderbird — single detection function, multiple trigger surfaces)
- Form-context Z sequence (error → next empty field → submit) — high user value
- Custom Vision Enhancement Provider for the brief flash effect (see decision #6)
- Per-app disable list (in addition to per-site)
- Statistics / debug log toggle for users reporting bad detections

## Phase 3 — later

- Email and search-results Z sequences
- Web app / dashboard primary-CTA detection

## Out of scope (don't build, don't suggest)

- AI / LLM integration (privacy, latency, cost)
- Reader-mode style rewriting of the page (we move the cursor, not the DOM)
- Reaper or audio editor integration (covered by OSARA)
- EPUB handling (covered by Paperback)
- General content summarization (not the same problem)

## Open questions (decide as we go)

- Should the site exclusion list stay exact-match by hostname, or grow pattern support later?
- Should audio feedback get a user-facing setting, or stay always on until there is real user demand?
- What is the right scope for the first email-detection release: webmail only, desktop mail clients only, or one shared heuristic with separate trigger surfaces?

## Build / test workflow — chosen: edit in the project folder, rebuild with SCons

Project uses NV Access's official addon template. SCons handles the build. The project folder is the source of truth — edit Python files in `addon/globalPlugins/TextMarksTheSpot/`, rebuild the `.nvda-addon`, reinstall in NVDA.

### Required tools (one-time setup)

- Python 3.13 (or 3.11+).
- `python -m pip install --user scons markdown`
- gettext on PATH: `winget install --id mlocati.GetText`
- `pip install pytest` for the unit-test suite.

### Build

From the project root (PowerShell):

```
scons
```

Produces `TextMarksTheSpot-<version>.nvda-addon` at the project root. Version comes from `buildVars.py:addon_info["addon_version"]`.

Clean build artifacts (the generated `addon/manifest.ini`, `addon/doc/<lang>/readme.{md,html}`, `addon/doc/style.css`, and the `.nvda-addon` itself):

```
scons -c
```

The archive layout is correct by construction — `manifest.ini` + `globalPlugins/` + `doc/` at the zip root, no `addon/` wrapper. The template's archive-building tool guarantees this; we don't have to.

### Where things live

- `buildVars.py` — addon metadata (name, version, summary, description, changelog, author, URLs, min/lastTested NVDA versions, license). Bump version here.
- `sconstruct` — SCons build script. Don't edit.
- `site_scons/` — SCons helpers (NVDATool, gettexttool).
- `manifest.ini.tpl` + `manifest-translated.ini.tpl` — SCons fills these in from buildVars.py to produce `addon/manifest.ini` at build time.
- `changelog.md` — user-visible changelog. Update for each release.
- `readme.md` (project root) — user-facing add-on documentation. SCons auto-copies this to `addon/doc/<baseLanguage>/readme.md` at build time, then renders it to `readme.html` for the Add-on Store page. Do NOT maintain `addon/doc/en/readme.md` directly — it gets overwritten every build.

### Install / iterate

NVDA → Tools → Manage add-ons → Install → pick the `.nvda-addon`. Acknowledge the trust warning. Restart NVDA on first install; later updates only need `NVDA+Ctrl+F3` to reload.

Daily loop:

1. Edit Python files in `addon/globalPlugins/TextMarksTheSpot/`.
2. `scons` to rebuild.
3. Reinstall the `.nvda-addon` in NVDA (or just restart NVDA — it'll pick up the new version).
4. Test, observe in `NVDA+F1` log viewer.

Iteration is a few seconds per cycle. No staging or syncing dance needed — the project folder IS the source.

### API probes BEFORE committing real code

For each NVDA API this add-on uses that we haven't worked with before, write a tiny standalone test add-on that probes the API in isolation. Install it, observe in NVDA log viewer (`NVDA+F1`), uninstall. Probes needed:

- ~~`event_treeInterceptor_gainFocus` override~~ — **ANSWERED 2026-07-14, no probe needed: it never fires in a GlobalPlugin, on any NVDA version.** It is a TreeInterceptor method core calls directly, not a dispatched event. Do not spend a probe on this.
- `sayAll` / `SayAllHandler.readText` from a specific position — does speech start exactly where the cursor moved?
- Settings panel registration — does `gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(...)` reliably show our panel? Does `terminate()` cleanly remove it?
- `tones.beep` from inside the focus event — does it play without blocking the event handler?

Each probe is 5–20 lines, packaged as a minimal `.nvda-addon` of its own. Install, observe, uninstall, move on.

### Future upgrades to this workflow (deferred)

Park these for later — only switch when the current loop becomes the bottleneck:

- **Developer Scratchpad** — built-in NVDA mechanism, basically the same idea as in-place editing but in a dedicated folder. Cleaner separation, no risk of NVDA "pending update" interfering.
- **SCons build** — `pip install scons markdown`, install GNU Gettext, run `scons` from the project root. Needed eventually for translations and markdown-rendered docs.

## Store submission checklist (Joseph Lee guide, summarized)

- GPL-compatible license (we'll use GPL v2)
- Python 3.x (we target 3.11+)
- Compatible with current base API release
- All user-facing strings wrapped in `_()` Gettext + `# Translators:` comments
- Version scheme: major.minor.patch
- Minimum NVDA version >= 2019.1
- Add-on package on GitHub (or comparable), submission via NV Access addon-datastore issue form
- First submission requires manual NV Access approval

## References

- Joseph Lee's NVDA Add-on Development Guide: https://github.com/nvdaaddons/DevGuide/wiki/NVDA-Add-on-Development-Guide
- NVDA Developer Guide (current): https://download.nvaccess.org/documentation/developerGuide.html — reviewed at 2026.2 beta 1, see Compatibility section above
- Mozilla Readability.js: https://github.com/mozilla/readability
- Mailgun Talon (email quote/sig parsing): https://github.com/mailgun/talon
- NVDA Add-on Store: https://addons.nvda-project.org/
- Add-on submission form: https://github.com/nvaccess/addon-datastore
