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

1. **Position only by default — no auto-read.** When detection succeeds, the add-on moves the browse-mode caret to the content start. NVDA's normal cursor-move announcement speaks whatever element the caret lands on (the heading, the first body paragraph, etc.) — that announcement IS the user's confirmation. The user then drives reading themselves with the standard NVDA keys (Down Arrow, NVDA+Down for sayAll-from-caret, etc.). Rationale: respects guardrail #5 (the user is always in charge), avoids conflicting with NVDA's existing `config.conf["virtualBuffers"]["autoSayAllOnPageLoad"]` preference, eliminates the risk of accidentally talking over video or other unwanted content, and the user keeps full agency over when speech starts. An opt-in "auto-read after positioning" toggle can live in settings later if real users ask for it — but it's not the default.
2. **Manual re-trigger hotkey: `Z`.** Confirmed unused by NVDA browse-mode quick navigation. Pressed in browse mode to re-run detection if the auto pick was wrong.
3. **Per-site / per-app disable list** in the settings panel. Users can opt out for specific domains or apps.
4. **Form-as-primary-goal detection.** Only treat as a form page when:
   - Readability scoring finds NO strong article candidate, AND
   - A form with multiple fields occupies the main content area, AND
   - Optional URL/title signals (`/register`, `/signup`, `/apply`, `/intake`, `/contact`) reinforce
   - NOT triggered by a newsletter widget sitting inside an article page
   - Honors guardrail #2: if any of the above is uncertain, the add-on does nothing and the user uses `f` to find form fields normally. We do not "best guess" form pages.
5. **No audio feedback during detection** (in the default position-only flow). Detection is <50ms — well under the human "instant" threshold. NVDA's natural cursor-move announcement on the landed element gives the user confirmation that something happened; a tone on top would be noise. If real-world detection ever crosses ~150ms on common pages (which would mean a perf regression worth fixing), we revisit and reintroduce the start / progress-pulse / success tones using NVDA's built-in `tones.beep`. For now: silent on success, silent on failure.
6. **Visual highlight at the detected spot.** Low-vision users and sighted observers (demo viewers, family/colleagues working alongside the blind user) benefit from seeing where the cursor landed.
   - **Phase 1 (MVP) — free, no code:** Rely on NVDA's built-in vision highlight system. When we move the browse cursor to the detected position, NVDA's existing browse-mode caret highlight (if enabled in `Preferences → Settings → Vision`) shows a box around it automatically. User-facing docs tell users to enable it. Zero implementation cost.
   - **Phase 2 — custom flash effect:** Add a `visionEnhancementProviders/` module to the add-on. Brief colored overlay around the detected element for ~500 ms on detection success, then fades. Doesn't clutter the screen long-term. High demo/marketing value. NVDA Vision Enhancement Provider API was added in 2020.4 — within our compatibility floor. Settings toggle for the flash, default ON.
   - **Phase 3 — skip unless requested:** persistent custom highlight with user-configurable color. NVDA's built-in highlight already covers the persistent case.
7. **Intent-first architecture (the load-bearing decision).** The add-on classifies every page or message by what its purpose is to the user, then dispatches to a per-intent strategy. This replaces the earlier "one universal heuristic" framing. The user-model: match what a sighted person automatically does on each page type — sighted users don't apply one rule everywhere either, they read articles, scan lists, fill forms, and ignore dashboards according to what the page is for.

   Intents and behaviors:

   - **Article** (news article, blog post, Wikipedia entry, docs page, single long-form piece). Goal: jump past headline / dek / byline / date / social-share / image-figures / related-articles rail to the **first substantial body paragraph**. Auto-read ON.
   - **List of articles** (news index home, search results page, YouTube home / channel, Google results, blog index, forum thread index). Goal: jump to the **first content heading of the largest same-level heading cluster inside `<main>`** — the first story / result / video / thread title. Auto-read OFF. User scans with NVDA's `H` key, picks one, clicks.
   - **Form** (signup, login, contact, intake, medical intake). Goal: jump to the **first form field**. Auto-read OFF. (Existing locked decision #4 is the form-detection rule; it becomes a branch of this architecture.)
   - **Status / dashboard** (account home, portal, monitoring widget, settings page). Too varied for a useful default. **Silent.** No jump, no tone. User uses NVDA's normal keys.
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

8. **Z is a smart "next likely thing" sequence, not just re-trigger.** Each press of Z moves to the next contextually likely position for the current page intent. After every Z press, NVDA announces what it did ("Jumped to first error: Email is required") so the user knows what happened.

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
   - If the page type is unidentified (no confident article / form / email / search / app match), Z falls back to "re-run detection from current position." Same as Phase 1 MVP behavior. Never invent a sequence on an ambiguous page.
   - At the end of a sequence (no more steps), Z announces "No more next-likely actions on this page" rather than wrapping around or guessing.
   - Z never rebinds or interferes with NVDA's built-in quick-nav keys. Tab, h, f, t, k, b, etc. continue to work exactly as NVDA defines them.

   **Phasing — MVP stays small:**
   - **Phase 1 (MVP):** Z = re-trigger detection only (single behavior, no sequence state)
   - **Phase 1.5:** Press counter + article-context sequence (step 1: next major section)
   - **Phase 2:** Form-context sequence (errors, next empty, submit) — high user value
   - **Phase 3:** Email and search-results sequences

   Resist the urge to ship the full sequence in v0.1.0. Each phase is its own marketing event and gets its own user feedback loop.

## Approach

- **Pure heuristic, zero AI, zero network.** No API keys, no privacy concerns, no per-use cost. Snappy. Free forever.
- **Architecture is intent-first** (see locked decision #8). The add-on classifies the page or message by purpose, then dispatches to a per-intent strategy. The detection modules below are the strategies, not standalone heuristics.
- **Web detection (article intent):** Walk NVDA's already-parsed browse-mode virtual buffer to find the first substantial body paragraph inside `<article>` or the main content region, skipping byline / date / social-share / figure / related-rail chrome (see decision #8 chrome list). Paragraph-cluster filter: candidate must be ≥ 100 chars AND a sibling of 3+ similar-length paragraphs. No re-parse of HTML.
- **Web detection (list intent):** Walk NVDA's heading tree, find the largest cluster of same-level headings inside `<main>` (or not inside `<header>` / `<nav>` / `<aside>`), jump to the first heading in that cluster.
- **Email detection:** Same intent classifier as web (personal/work, marketing, transactional, system). For plain-text email: regex-based quoted-reply strip (`On <date>, <name> wrote:`, `>`-prefixed lines, "From: ... Sent: ..." blocks) + signature strip (trailing K lines after valediction or org-keyword pattern, or `-- ` delimiter). For HTML email: apply the article-intent strategy plus an email-specific chrome list (preheader hidden text, masthead/logo block, signature blocks in `<blockquote>` or `<table class="signature">`, footer/unsubscribe rail). Same detection function applies regardless of email client — the trigger fires on whatever message-body area gains focus.
- **Auto-trigger mechanism:** Override `event_gainFocus` on the `GlobalPlugin` and bookkeep `obj.treeInterceptor` — fire detection only when the treeInterceptor object identity changes from the last one we saw. Optionally also override `event_documentLoadComplete` for fresh-page-load coverage. The intuition in earlier drafts was correct (we want "treeInterceptor changed"), but the mechanism was wrong: `event_treeInterceptor_gainFocus` is invoked directly as a method on the treeInterceptor by `doPreGainFocus` in NVDA's `eventHandler.py` and is NOT in the GlobalPlugin event dispatch chain. Verified against NVDA source 2026.1.1 — the `_EventExecuter.gen()` chain dispatches global plugins → app modules → tree interceptor → NVDAObject for normal events, but `event_treeInterceptor_gainFocus` short-circuits that. NVDA's own debounce (`obj.treeInterceptor is not oldTreeInterceptor`) means in-document focus shifts don't trigger — we replicate that check in our own `event_gainFocus` override.
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
│       ├── trigger.py                     event_gainFocus hook + TI bookkeeping
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
- **Last tested NVDA:** 2026.1.1 (Python 3.13, 64-bit)
- **Pure Python, no C extensions** — works in both 32-bit and 64-bit NVDA without rebuild
- License: GPL v2 (NV Access store convention)
- Versioning: major.minor.patch

## Phase 0 — must do BEFORE writing code in the new session

1. **Investigate "Content priority reading"** (NVDA store, v0.3, publisher "lamb"). Fetch its actual repo / detail page and confirm what it does. If it overlaps with this add-on, decide: pivot, differentiate, or proceed with awareness. Store page only listed it in the index — the detail page or its GitHub repo will have the real description.
2. **Confirm `Z` is also unused by JAWS quick-nav** in case we port later. Casey is JAWS Certified — a future JAWS script pack would want consistent keys.
3. **Pick a final add-on ID slug** for the manifest. Current proposal: `TextMarksTheSpot`. The store uses this as the addon ID URL slug.

## Phase 1 — what shipped in 0.1.0

Status: working build, end-to-end, in Firefox and Chrome browse mode against a varied corpus of real sites.

**Implemented:**
- Intent-first classifier (`classifier.py`) — 23 hand-coded fixtures, 100% pass. Pure Python, no NVDA imports — runnable on any workstation.
- NVDA-binding layer (`tree_summary.py`) — walks the browse-mode tree and produces a TreeSummary the classifier can consume. Three-tier walk fallback: (1) scoped to `<main>`, (2) chrome-filtered when main scoping yields nothing, (3) unscoped last-resort for pages whose theme wraps body in `role="complementary"` etc.
- Article landing strategy (`detection/web.py`) — `find_article_landing` (cluster or hero pattern) and `find_list_landing` (first heading in dominant cluster). 13/14 landing fixtures pass.
- Trigger (`__init__.py`) — hooks `event_gainFocus` and `event_documentLoadComplete`. TI-changed bookkeeping (mirrors NVDA's own `doPreGainFocus` debounce). Synchronous detection at event time — empirically more reliable on JS-heavy sites than delayed/queued detection.
- Action: on ARTICLE → move caret to first body paragraph; on LIST → move caret to first headline in dominant heading cluster. `speech.cancelSpeech()` immediately at handler start (gated on TI change) plus before our own speakTextInfo, then `speech.speakTextInfo` so the user hears the landing text.
- `Z` key — re-runs detection. Gated on `BrowseModeDocumentTreeInterceptor` + `passThrough=False`; passes through to host app outside browse mode (so users can type `z` in terminals/edit fields).
- Single-call cache for `_in_scope` parent-chain lookups — 3-10x speedup over uncached.
- Build: `scons` from the project root produces the `.nvda-addon` using NV Access's official addon template (buildVars.py, sconstruct, site_scons/). `probes/build_probe.py` is still used for the small probe add-ons.

**Deferred to later phases:**
- Settings panel and per-site disable list — not yet wired.
- Email detection (Phase 2) — plain-text + HTML email body extraction.
- Form / video per-intent actions — silent today, planned per-intent later.
- Z key sequence state machine (next-likely-thing per page type) — Phase 1.5.
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

- Should auto-read be on by default for the FIRST run after install, or default to "position only, no auto-read" until the user opts in? (Currently locked to: auto-read on. Revisit if early testers complain about surprise speech.)
- Should the form-detection branch try to focus the first form field, or just announce "this looks like a registration form" and let the user navigate? (Defer until form detection is implemented.)
- Should the per-site disable list be exact-match domains or support patterns? (Defer to settings panel implementation.)

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

- `event_treeInterceptor_gainFocus` override — does it fire when a page loads / an email opens? Does it also fire on minor in-document focus shifts (debounce target)?
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
- NVDA 2026.1 Developer Guide: https://download.nvaccess.org/documentation/developerGuide.html
- Mozilla Readability.js: https://github.com/mozilla/readability
- Mailgun Talon (email quote/sig parsing): https://github.com/mailgun/talon
- NVDA Add-on Store: https://addons.nvda-project.org/
- Add-on submission form: https://github.com/nvaccess/addon-datastore
