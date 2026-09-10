# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read this first

**SPEC.md at the project root is the load-bearing handoff.** Read it before touching code. It contains the locked guardrails, locked design decisions, current gesture behavior, deferred per-page-type Z sequences, the phasing plan, the build/test workflow, and the store submission checklist. CLAUDE.md is a pointer into SPEC.md, not a replacement for it.

**The rest of the doc map, so nothing gets re-derived:** `implementation-notes.md` is the running decision log, newest entry at the TOP, and it holds the long-form reasoning behind most of the "do not rebuild this" notes summarized here. `NEXT_SESSION_PROMPT.md` is a DATED snapshot of where things stood, not a live document; when it disagrees with the source or with this file, it is stale and the source wins. `AGENTS.md` is the short brief for non-Claude agents and restates a subset of these rules, so a rule change here needs checking there. `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, and `AI_CODE_GENERATION_POLICY.md` are the public-facing repository policies.

**DEBUGGING.md at the project root is the incident playbook.** When Casey reports "this URL landed wrong," follow it step by step: logs before theories, verify the page independently (Chrome extension / Wayback), fixture-first general fix, stale-build check before re-diagnosing. It was written from the 2026-07-06 soak-test day and encodes the workflow that found four real bugs; it also works for less capable models running routine checks.

## What this project is

NVDA screen-reader add-on (`TextMarksTheSpot`) that auto-jumps the browse cursor to where real content starts on web pages and email messages, then speaks that single paragraph so the user knows where they landed — no keypress needed, and no `sayAll`. From there the user reads on with normal NVDA navigation (Down Arrow, `h`, etc.). Pure heuristic, no AI, no network. Targets NVDA 2024.1+ (Python 3.11+), pure Python so it runs in both 32-bit and 64-bit NVDA. GPL v2.

The only key the add-on binds is `Z` (browse mode). Every other NVDA key keeps its built-in behavior — this is guardrail #1 and overrides any feature idea that would conflict.

## Guardrails that override everything else

These come from SPEC.md and bind every change:

- Never supplant natural NVDA navigation. The add-on owns `Z` and nothing else.
- Act only when the page's purpose is unambiguous. Below the confidence threshold → silent.
- When in doubt, do nothing. A wrong auto-jump is worse than no jump.
- Honor website-placed focus on form controls. If the page auto-focused a real `<input>`/`<textarea>`/`<select>`/contenteditable (search box, login, compose body, etc.) before our trigger fires, do nothing — no cursor move, no auto-read, no tone. The site already told the user where to start. `Z` still lets the user override manually.
- Do not pre-cancel speech on page load. Don't call `speech.cancelSpeech()` (or equivalent) when the trigger fires — that's what was eating the add-on's own output. Detection runs silently while NVDA does its normal page-load chatter (title, URL, focus). The single moment of interruption is the add-on's own `speakObject` / `speakText` call when a paragraph is found — speaking the paragraph naturally cuts off whatever NVDA was saying. If detection finds nothing, no interrupt happens and NVDA's page-load speech finishes normally. Failure mode to avoid: gating the speak call on "speech queue idle" — during rapid navigation the queue may never go idle and the add-on stays silent.
- The user is in charge. Per-site disable list, settings toggles, and NVDA's normal keys are the escape hatches.

If a proposed change weakens any of these, push back instead of implementing.

## Naming convention (NVDA house style, adopted 2026-09-06)

The codebase follows NVDA's own coding standards, not generic PEP 8, because add-on
store reviewers read core style as the community style and flag divergence. Tabs for
indentation. Functions, variables, properties and attributes are `camelCase` starting
lower case. Classes are `CapWords`. Constants stay `UPPER_SNAKE_CASE`. Booleans start
with a question word (`isX`, `hasX`, `shouldX`).

Three prefixes are kept literally and camelCased only after the underscore, which is
how NVDA itself writes them: `script_returnToLanding`, `event_documentLoadComplete`,
and `test_definitionalLedeBeatsAPrerequisiteNoteAboveIt` in the test suite. Do not "fix" those to `scriptX` /
`eventX` / `testX` — NVDA's script and event dispatch keys on the prefix, and
`pytest.ini` sets `python_functions = test_*`.

Two deliberate exceptions, both because the name is a lookup key rather than an
identifier:

1. **Capture-log JSON keys stay snake_case.** `"positionally_scoped"`, `"has_main"`,
   `"counts_trunc"` in `_appendCapture` and in `tests/replay_captures.py` are a wire
   format shared with capture files already on disk. Renaming a key does not fail, it
   makes `rec.get(...)` quietly return the default for every existing record, so an
   old corpus would replay as though every page were unscoped. The `Intent.KEY_RESULT`
   enum *value* `"key_result"` is data for the same reason.
2. **`tmp_path` and other pytest fixtures stay snake_case.** Fixtures are injected by
   parameter name, so renaming the parameter simply stops the fixture from being found.

## Architecture

The add-on is one NVDA `GlobalPlugin` at `addon/globalPlugins/TextMarksTheSpot/`. The SPEC describes more files than currently carry weight — the load-bearing modules right now are `__init__.py`, `classifier.py`, `treeSummary.py`, `detection/web.py`, and `feedback.py`. The other files exist as stubs or scaffolds for future phases.

Load-bearing modules:

- `__init__.py` — `GlobalPlugin` class, all trigger logic, and the `Z` script (browse-mode binding). Hooks **`event_documentLoadComplete` ONLY** — explicitly NOT `event_gainFocus`, because that fires on every alt-tab and in-document focus change.

  **Read this before touching the trigger (2026-07-14, verified in NVDA source by two independent reviews).** Two things this file used to claim are FALSE, and believing them cost the add-on two thirds of its page loads:

  1. **`event_treeInterceptor_gainFocus` CANNOT fire in a GlobalPlugin.** Not "doesn't on this NVDA build" — cannot, on any version, by construction. Global plugins only receive events dispatched through `eventHandler.executeEvent` → `_EventExecuter.gen` (`eventHandler.py:141-167`); `treeInterceptor_gainFocus` is never dispatched that way. It is a plain **method** core calls directly on the TreeInterceptor object (`eventHandler.py:425`, `virtualBuffers/__init__.py:611` and `:620`). The old handler fired 0 times in 31 page loads, which is exactly what the source predicts. It has been deleted. `documentLoadComplete` is the ONLY trigger and always was; the "backstop" never existed. Do not re-add it.
  2. **A TreeInterceptor is NOT a document identity.** NVDA binds a TI to an **accessibility-tree root**, not to a URL or a navigation. `treeInterceptorHandler.update()` returns the EXISTING interceptor whenever the object already has one (`treeInterceptorHandler.py:48-78`), and Gecko keeps it alive while the root accessible is not defunct (`gecko_ia2.py:309-329`). So on same-tab navigation the browser commonly keeps the root, **NVDA reuses the TI, and the URL changes in place underneath it** — NVDA documents exactly that for SPAs (`browseMode.py:2387-2396`), and on Gecko `documentConstantIdentifier` is a live COM call, not a cached value (`gecko_ia2.py:610-614`). The old "same TI → skip" gate therefore swallowed **17 of 31 real page loads**. The URL is the document's identity; the TI is just the container. Chrome/Edge are affected identically — `ChromeVBuf` inherits from the Gecko buffer and overrides neither `_get_isAlive` nor `_get_documentConstantIdentifier`.

  Debounce gates, in order: (a) **same TI AND same URL** → skip (this is the document-identity gate; an iframe/ad load fires its own `documentLoadComplete` but resolves through containment to the MAIN page's TI and URL, so it lands here correctly, as do duplicate double-fires. Known gap, accepted: a genuine re-navigation to the IDENTICAL url on a reused TI — F5, a form POST returning the same URL — is skipped; `Z` covers it, and distinguishing it needs a document-generation signal NVDA does not expose); (b) same URL within `_REFIRE_COOLDOWN_SEC` (2.0 s) → skip (catches SPA-ish sites like DDG/Gmail that emit duplicate document-load events for one logical page load); (c) **post-landing suppression** — same URL as the last SUCCESSFUL landing within `_LANDED_SUPPRESS_SEC` (120 s) → skip (SPA re-renders fire fresh documentLoadComplete events with new TIs well past the 2 s cooldown — Zoom webinar registration re-rendered at +9 s and +34 s when it swapped in the signed-in profile, and the re-rendered tree was WORSE: description collapsed into accordions, so re-detection yanked the user off a good landing into mid-form. One page visit, one landing; `_recordLanding` stamps the URL on both success paths); (d) focus is on an editable control → skip silently per guardrail #6; (e) **restored-position gate** (`_caretIsMidPage` + `_seenUrls`) — browse cursor is past the first character AND (the URL was already visited this session OR the URL carries a real anchor fragment, not a `#/` SPA route) → skip. Both signals are required: caret-mid-page alone misfires on first visits to pages that initialize the caret below the top (halturnerradioshow articles start at node 1 — the 2026-07-06 soak-test miss), while Back navigation by definition returns to a seen URL. `_seenUrls` is a session-scoped url-to-timestamp dict, membership checked BEFORE recording at PROCEEDING time, pruned to the newest 250 at 500 entries. The 1500 ms retry uses a different check — it captures the caret position at scheduling time and abandons only if the caret MOVED during the wait (comparing against document-top would permanently break retries on those same below-top-caret pages). The `Z` script bypasses (a), (b), (c), and the URL/timestamp gates, and double-Z on an excluded site bypasses (e) too (explicit user request). Trade-offs accepted: an F5 refresh of the same URL within 120 s of a landing gets no auto-landing (Z covers it), and alt-tab / tab-switch NEVER auto-triggers — alt-tab produces no `documentLoadComplete` at all (it is a browser *load* event, mapped from `IA2_EVENT_DOCUMENT_LOAD_COMPLETE`), so quiet tab switches are structurally safe and do not depend on any gate. Casey confirmed 2026-07-06 that this is the DESIRED behavior, so do not "fix" it by hooking `event_gainFocus`. **Readiness poll:** `documentLoadComplete` means "the DOM finished loading", which is NOT when NVDA finishes building the virtual buffer, and NVDA only builds a TI in its pre-step when the loaded object is the focus or a focus ancestor (`eventHandler.py:431-432`) — so the TI can arrive unready OR as `None`. Both are polled (250 ms × 12). The None case is gated by a **URL-scheme allowlist** (http/https/file), which is the same trick NVDA itself uses to tell web documents from email (`browseMode.py:2406-2413`); mail clients expose `imap:`/`mailbox:`/`news:` URLs, so this keeps us out of Thunderbird message previews without hard-coding an app name. **Beware:** on a REUSED TI, `isReady` stays True throughout the buffer's re-render, so the poll never engages and detection can walk a buffer still holding the PREVIOUS page — the stale-position guard in `_handleResult` (below) is what catches that. Calls `feedback.working()` then `feedback.progress_start()`, runs detection in `_runDetection`, dispatches by intent in `_handleResult`, calls `feedback.progress_stop()` in a finally. **Speech path differs by intent:** ARTICLE / LIST / NOTICE / KEY_RESULT land via `speech.speakTextInfo` on a captured textInfo (with `speech.cancelSpeech` immediately before — the only sanctioned cancel point). **FORM splits by page shape**: a bare form (no substantial preamble) gets `ui.message` announcing the form title (mode-agnostic so it survives NVDA's auto-switch into focus mode when the page auto-focuses an input), then `setFocusOnFirstFormInput` moves keyboard focus to the first form field so NVDA's own focus speech announces it — without this, Google-Forms-style pages would swallow our browse-mode `speakTextInfo` silently. But a **rich-preamble form** (`web.formWantsBrowseLanding`: any non-chrome paragraph ≥200 chars) gets a normal browse-mode landing on the form title instead — focusing the first input on a Zoom-webinar-registration-style page (81-char H1 + ~2000-char description + 7 inputs) skipped the user past all the context. **Retry mechanism:** if a detection attempt returns False (no landing acted on), schedules another attempt via `wx.CallLater`, bounded by `_MAX_DETECTION_ATTEMPTS` (3 including the first). The delay depends on WHY the attempt failed. A tree that yielded real nodes and still found no landing has genuinely answered, so it gets exactly ONE more look at +`_RETRY_DELAY_MS` (1500 ms) and no third; re-walking such a page costs seconds on exactly the heavy pages that can least afford it. An UNBUILT (empty) tree is nearly free to re-walk (the two IMDb misses took 2 ms and 4 ms, there being nothing to walk), so it earns a third attempt at +`_EMPTY_RETRY_DELAY_MS` (1250 ms) each, giving three looks at 0 / 1.25 / 2.5 s inside the budget for how long a user will wait to be told nothing was found. The retry is silent (no second working tone), verifies URL hasn't changed, and either lands+speaks (if content has now hydrated) or plays the two-beep `notFound` tone. New events (real navigation, Z press, refresh, alt-tab to new TI) cancel any pending retry. This is the principled fix for SPA hydration delays — no per-site code, just "wait, look again." `notFound` only plays on the retry's no-result outcome, not the first attempt; that way the first attempt's silence covers the wait gap cleanly. **Stale-position guard (load-bearing, do not remove):** we capture a TextInfo per node during the walk and speak it afterwards, but the walk takes 1.5–2 s and on a hydrating page NVDA rebuilds the virtual buffer DURING that window, so positions captured early are already stale by the time the walk ends. The add-on was *speaking a different paragraph than the one it landed on* — 7 of 42 landings in an 83-page soak, and the classifier's choice was often CORRECT (chose the right WFAA lede, spoke a Cincinnati Reds sports headline; chose a recipe lede, spoke "We're loading your content, stay tuned!"). It also explains silent landings: a stale position that expands to an empty range makes `speakTextInfo` neither raise nor speak. So before moving the caret or speaking, `_handleResult` re-expands the captured position and checks it still holds the paragraph the classifier chose (`web.landingTextMatches`); on drift it **re-anchors by TEXT** via `tsMod.findLandingByText` → NVDA's `TextInfo.find` (returns bool, repositions to the match start). A retry is NOT a substitute — the buffer drifts *during* the walk, so a re-walk races the same way; text is the stable anchor, the offset is not. If the re-find also fails, we stay silent: reading the WRONG paragraph is worse than reading none.
- `classifier.py` — pure-Python intent classifier over a `TreeSummary`. Intents: `SILENT_FOCUS_HONORED`, `FORM`, `ARTICLE`, `VIDEO`, `LIST`, `APP`, `NOTICE`, `KEY_RESULT`, `UNKNOWN`. Order matters — high-confidence NOTICE (keyword + small shape) fires early, ARTICLE-cluster before KEY_RESULT before ARTICLE-hero before APP before NOTICE-fallback. Key thresholds: `PARAGRAPH_MIN_CHARS=100` (cluster substantial bar), `HERO_PARAGRAPH_MIN_CHARS=50` (decoupled from cluster bar — landing-page intros commonly run 50–99 chars), `NOTICE_MAX_TOTAL_CHARS=1500`, `NOTICE_MAX_HEADINGS=3`, `NOTICE_MAX_INTERACTIVES=6`. `noticeKeywordMatch` boosts NOTICE confidence 0.65 → 0.85 when status-keyword regex hit. **FORM blocks**: `<article>` present, strong body cluster (3+ paragraphs ≥100 each, ≥500 total), hero without strong form signal, or a **massive duo** (`_hasMassiveParagraphDuo`: two ADJACENT non-caption/non-boilerplate paragraphs ≥`MASSIVE_DUO_MIN_CHARS_EACH=200` each — armstrongeconomics blog posts have two 600-char body paragraphs but no `<article>` and a 6-input newsletter widget, so nothing else blocked FORM); the `<article>` and massive-duo blocks are both bypassed when the URL matches FORM hints (/register, /signup, ...) so Zoom-style registration pages stay FORM. An **editorial URL** (matches ARTICLE hints — /news/, /blog/, /podcast, /article/, /story/, ... — and does NOT match FORM hints) also blocks FORM outright: thurrott.com podcast pages carry 10 scattered inputs (comment box, login, search, newsletter), expose no `<article>`, and have neither a massive duo nor a strong cluster, so the URL is the only reliable content signal (2026-07-06 soak). `KEY_RESULT` matches "label (10–40 chars) + value (1–8 chars, mostly digits) + unit (explicit or implicit `%$°` in value)" at lead position (before any 100+ char body paragraph) — catches fast.com-style speed widgets, weather, stock single-quotes, battery indicators.
- `treeSummary.py` — NVDA binding layer. Walks the browse-mode tree by UNIT_PARAGRAPH, builds a `TreeSummary` for the classifier, captures parallel textInfo positions for `getLandingTextinfo`. Also runs four detectors against the FULL chunk text during the walk (the `textPreview` it stores is truncated to 60 chars, so end-of-text signals must be computed here): the NOTICE status-keyword regex (`_NOTICE_RE`) → `summary.noticeKeywordMatch`, the photo-credit detector (`web._looksLikeImageCaption`) → per-paragraph `MainNode.isCaption` (a trailing "(Getty Images)"-style credit usually sits past the 60-char cutoff), the sentence-end detector (`web.endsLikeSentence`) → per-paragraph `MainNode.endsSentence` (backs the prose-run landing gate), and the legal-boilerplate detector (`web._looksLikeLegalBoilerplate`) → per-paragraph `MainNode.isBoilerplate` (the "All rights reserved" tail likewise sits past the cutoff; the classifier's `_heroParagraphChars` skips flagged nodes so a not-yet-hydrated SPA shell whose only substantial text is the footer copyright can't classify as ARTICLE — it produces no landing, handing the page to the 1500 ms retry — and a footer line can't block FORM on a weak-signal form page). Exposes `isFocusEditable()` publicly so the trigger can pre-check before any tone, and `setFocusOnFirstFormInput(ti)` for the FORM intent. **Walk iteration gotcha (fixed 2026-07-06)**: the walk previously did `collapse(end=True)` + `move(UNIT_PARAGRAPH, 1)` after every chunk — when a chunk's end offset lands exactly on the next paragraph's start boundary (common after link/image-heavy blocks), that pair advances TWO paragraphs and silently skips one (pattysworlds' "Watch your step" paragraph after the logo-bearing welcome heading; same signature as the missing main-tweet text on X). The loop now expands directly at the collapsed end and only forces a move when `compareEndPoints` shows no forward progress. A `[TMTS walk-drops]` debug line logs up to 10 chunk previews dropped by the scope filter after the scoped region started — mid-region drops are anomalies, and the line distinguishes "scope ate it" from "NVDA never yielded it". **Two-stage fallback**: main-scoped walk → unscoped walk. The previous intermediate chrome-filtered walk was removed for performance — it uses the same parent-chain mechanism as the scoped walk and almost always failed the same way when the scoped walk failed, doubling detection time on hard pages (webaim 413-node walk dropped from ~9 s → ~5 s after removal). **Known limitation**: the parent-chain landmark check (`_inScope`) is unreliable on some sites — NVDA returns different object instances for the same logical landmark across accesses, so `cur is mainObj` and `cur is <chrome landmark>` both fail, defaulting chunks into the wrong scope. Net effect: on sites like bestmidi.com/bg/ the unscoped fallback runs and `mainNodes` ends up containing nav + footer too. The landing finders compensate (lowered hero threshold + doc-order-first NOTICE landing + tag-list filter + seen-heading gate) but a real fix would be to filter by textInfo position range instead of by parent-walk identity.
- `detection/web.py` — landing finders.

  **Two passes over the cascade (2026-07-14).** `findArticleLanding` runs the whole cascade once over a SENTENCE-STRICT view (paragraphs that don't end like a sentence are treated as chrome), then, if that yields nothing trustworthy, over the original cascade unchanged. Rationale: in an 83-page soak, all 9 good landings were prose ending in terminal punctuation and all 4 bad ones weren't (a photo credit ending "…/Getty", an ad banner ending "…Founded By Veterans", a self-promo ending "…Preferred Source", another story's headline). One signal separated every good landing from every bad one. **TWO GUARDS, both load-bearing, both pinned by tests:** (1) the fallback to the unrestricted cascade — on a link-aggregator front page (stevequayle.com) NOTHING ends like a sentence and landing on the first bullet is CORRECT; without the fallback the page lands nowhere. (2) Only TRUST the strict pass when it lands on sentence-ending prose — without this it BROKE the X/Twitter status page, because a tweet is a run of short lines that individually lack terminal punctuation, so flagging them as chrome shattered the run the prose-run gate needs and the page landed on the generic "Post" heading.

  **`_findLeadSectionLanding`** runs BEFORE the size/cluster gates: in the span between the FIRST heading and the NEXT one, exactly ONE non-chrome sentence-ending paragraph ≥100 chars with no substantial neighbour IS the page's lead. This is IMDb's plot summary — a 166-char standalone paragraph that fails every other gate (VERY_SUBSTANTIAL wants 200; the cluster gate wants an adjacent substantial paragraph, but IMDb follows it with short director/cast lines; the hero gate wants a heading within 4 nodes, but IMDb's next heading is 31 away). The cascade walked past it and landed on one of four adjacent "Clip…" video titles. Note the titles END IN QUESTION MARKS, so `endsLikeSentence` is genuinely True for them and the strict pass is right to keep them — suppressing the clip rail alone would NOT fix it, the cascade would run on to a 200+ char user review. The synopsis needs POSITIVE evidence. **"Exactly one" is the load-bearing part**: a normal article's lead section holds MANY substantial paragraphs, so the gate declines and the ordinary cascade runs — that is what keeps it off every news page and off deks.

  **`_looksLikeEditorialDisclosure`** (in `_isChromeParagraph`) catches BOILERPLATE THAT READS LIKE PROSE — the blind spot on the far side of the sentence rule, which separates prose from fragments and cannot see grammatical sentences. Three families, all with near-mandated vocabulary: affiliate/referral disclosures ("this post contains referral links"), syndication notes ("written by WTOP's news partner… republished with permission"), and marketing-consent blurbs ("by signing up, you agree to receive text messages"). Matched on CONJUNCTIONS, not loose keywords: publishing language ("originally appeared") only counts when the paragraph refers to ITSELF ("this article"), because "She originally appeared on the show in 1998" is ordinary prose. **NOT included, deliberately:** signup promos ("Keep your favorites in MyRecipes for free") and masthead marketing ("rigorously tested in our Nashville Test Kitchen"). Open vocabulary; a rule loose enough to catch them would eat real ledes. KNOWN GAP — the cost is landing one paragraph early, one Down arrow. **Rejected approach, do not revisit without new evidence:** tracking paragraph text across a site's pages ("boilerplate is what repeats"). Two independent source reviews killed it — it is stateful, makes the same URL land differently on visit 1 and visit 4, destroys fixture-based debugging, and does nothing on a FIRST visit, which is the common case. And for a blind user, predictable-and-slightly-wrong beats adaptive-and-sometimes-right: you can learn "this site lands one paragraph early, press Down"; you cannot learn a moving target.

  **Known structural fault (named independently by both reviews, NOT fixed):** the cascade awards the landing on rule ORDER rather than EVIDENCE STRENGTH — a weak two-paragraph cluster of 50-char fragments returns immediately and beats a stronger candidate sitting earlier in the document. The lead-section gate patches one instance; the disease remains. It is why food.com lands on a reader's review instead of the recipe.

  **`_findHeadlineListLanding` runs FIRST**, ahead of the sentence-strict pass and the whole cascade, so whatever it decides is final. It fires on a run of `_HEADLINE_RUN_MIN`=6 headline-ish paragraphs with no article body. **`_repeatsPreviousMember` is what keeps a MEDIA RAIL from faking that wall**: a rail commonly emits each item twice, a bare title and then the title with its source appended ("How to Mod Minecraft for Beginners!" then the same "by <channel> on YouTube"), so three videos present as six members. A repeat is transparent, neither a member nor a gap, compared against the previous MEMBER rather than the previous node because the two emissions are separated by the source and date lines the gap tolerance already steps over. Two guards, both forced by the 60-char `textPreview`: the repeat must be at least as long as what it repeats (two distinct long titles can share a 60-char opening), and the prefix must survive normalization at `_HEADLINE_MIN_CHARS`. Not Google-specific — the Guardian emits its pre-main teasers the same way.

  **`findArticleLanding` cascade** (in order, first match wins): (1) skip paragraphs below `LANDING_MIN_PARAGRAPH_CHARS=50`; (2) skip chrome-shaped paragraphs via the shared `_isChromeParagraph` helper — **tag lists** (`_looksLikeTagList`: no-space commas like "CoPilot,Microsoft 365,Microsoft Excel" — real prose uses commas WITH spaces), **share-link payloads**, **screen-reader instruction text**, **promo teasers** (`_looksLikePromoTeaser`: ALL-CAPS "READ MORE:"/"RELATED:"/"SEE ALSO:"/"DON'T MISS:" labels with optional leading bullet — case-SENSITIVE so prose "Read more about..." survives; "EXCLUSIVE:" deliberately excluded because sites open real ledes with it; Daily Mail's "• READ MORE:" box + byline formed a fake cluster and won the landing), **bylines** (`_looksLikeByline`, two forms: all-caps "By ..." — starts with exactly "By " AND ≥70% of following letters uppercase, the ratio keeps "By NASA's estimate..." prose safe, mixed-case "By John Smith" is a known deliberate gap; and participle bylines "Written/Posted/Published/... by Name" — mixed case allowed, Phoronix's "Written by Michael Larabel..." was landing via the scoped fast path, guarded by requiring a capitalized name after "by" and a 120-char cap on the FULL paragraph length passed via `fullLength` since the 60-char preview can't enforce it), **figure captions / photo credits** (`_nodeIsCaption`: walk-time `MainNode.isCaption` flag, preview fallback), and **cookie consent** (`_looksLikeCookieConsent`: a first-person subject, a placing verb and the cookie or device-storage object inside ONE sentence, so an article about cookie law survives; bensound.com was landing on its banner instead of the track description), **machine-serialized data** (`_looksLikeSerializedData`: anchored at the start AND requiring a quoted key, because a Google Apps Script page served a 115,605-char JSON document as a single paragraph, which clears `VERY_SUBSTANTIAL_PARAGRAPH_CHARS` by three orders of magnitude and wins outright — length is not evidence of prose), **legal footer boilerplate** (`_nodeIsBoilerplate`: walk-time `MainNode.isBoilerplate` flag, preview fallback; matches "all rights reserved", copyright+year, and the CCPA "Do Not Sell My Personal Information" row — the Zoom-webinar-shell regression where the pre-hydration page's only substantial paragraph was the footer copyright); these skip filters apply at every gate and also in `findNoticeLanding`, `findFormLanding`'s paragraph fallback, and the Z forward scan; (3) **very substantial** paragraphs ≥`VERY_SUBSTANTIAL_PARAGRAPH_CHARS=200` win immediately on their own; (4) **cluster** (next paragraph also ≥50 chars) wins — but a short candidate (<100 chars) followed by a much longer paragraph (≥150 and >2×) yields to the longer one (**teaser-skip**, for CNET-style TLDR teasers), *unless* the short candidate is an AP-style **news dateline lede** (`_looksLikeNewsDateline`, e.g. "DENVER (KDVR) —"), which is the real opening line and wins; (5) **hero shortcut** (≥`HERO_PATTERN_MIN_CHARS=100` + heading in lookahead) wins, but **only if we've already seen a heading in mainNodes** — pre-H1 substantial paragraphs are nearly always chrome (publisher disclaimers, deks, bylines); (5.5) **prose-run gate** (`_findProseRunLanding`) — a run of ≥2 consecutive non-chrome paragraphs each ≥15 chars totaling ≥100 chars lands on its FIRST line, but only when ≥2 lines AND ≥half the run end like sentences (`MainNode.endsSentence`, computed at walk time via `web.endsLikeSentence` because the terminal '.' of a 61+ char line sits past the 60-char preview cutoff; preview fallback for ≤60-char lines) and the run starts AFTER a heading (pre-heading sentence runs are cookie banners). This is the X/Twitter single-status fix: a tweet arrives as line-per-paragraph chunks (19+34+61 chars on the MarioNawfal page), each under the 50-char bar, and the old cascade fell through to the directory redirect and landed on the generic "Post" heading. Sentence-end density is what rejects the two length-based impostors: nav/directory link runs (Montgomery: six Title Case rows, zero sentence ends) and form-label runs (signed-in Zoom: sixteen labels + one "?" question = 1/17); (6) **largest-paragraph fallback** picks the longest non-chrome paragraph ≥50 chars, with a **directory-page redirect**: on pages ≤`_DIRECTORY_REDIRECT_MAX_NODES=40` nodes where the ONLY substantial paragraph sits ≥5 nodes past the first heading, land on the heading instead (Montgomery probate forms was the original case at ≤30; widened to 40 for the signed-in Zoom registration shell — 36 nodes, description in closed accordions, lone 52-char question label mid-form). Each gate has a regression test in `tests/test_landing.py`. `findListLanding` (first heading in largest same-level cluster). `findNoticeLanding` (first paragraph ≥ `_NOTICE_LANDING_MIN_CHARS=30` in document order — deliberately NOT gated on "first heading first" because useful content often precedes any detected heading on small pages). `findKeyResultLanding` (delegates to `classifier.findKeyResultPatternIndex` to land on the LABEL so the user arrows forward to hear the value). `findFormLanding` (first heading — the form title — or first substantive paragraph as fallback; the caller in `__init__.py` then either announces this via `ui.message` + `setFocusOnFirstFormInput` for bare forms, or lands the browse cursor on it when `formWantsBrowseLanding` says the page has a rich preamble).
- `feedback.py` — three audio cues via `tones.beep`. `working()` = 500 Hz / 30 ms at detection start. `progressStart()` / `progressStop()` = 400 Hz / 20 ms pulse every 500 ms while detection runs, on a `threading.Timer` background thread so beeps still play while the main NVDA thread is busy walking the tree. `notFound()` = **two** 220 Hz / 60 ms beeps with an 80 ms gap, played on a background thread so the sequence doesn't block NVDA — the two-tone rhythm is distinctive from working() (single short blip) and the progress pulse (single beep, repeated). Distinct pitches (500 / 400 / 220) so they're easy to tell apart by ear. No success tone — the spoken landing paragraph IS the success signal. **Override of original SPEC**: the SPEC said "failure is silent"; we play `notFound()` for genuine no-result outcomes after the retry attempt (the user asked for this), but still stay silent for SILENT_FOCUS_HONORED per guardrail #6.

Stubs / scaffolds (described in SPEC, not yet load-bearing):

- `trigger.py`, `context.py`, `detection/__init__.py`, `detection/email.py`, `detection/form.py`, `patterns.py`, `sequence.py` — stub files. When promoting any of these to real code, lift the relevant logic out of `__init__.py` and keep this list updated.
- `config.py` is load-bearing — backs the per-site exclusion list via NVDA's config system. Not a stub.
- No `settingsPanel.py`. The NVDA+Z gesture handles site exclusion directly; a settings panel would be redundant for v0.1.0. If genuinely useful settings emerge later (audio-feedback toggle is the most likely candidate), add it as a fresh `settingsPanel.py` then — `gui.SettingsPanel` is the right base class, and registration is `gui.NVDASettingsDialog.categoryClasses.append(...)` in `__init__` paired with a `.remove(...)` in `terminate()`.

`addon/doc/en/readme.md` is the user-facing doc shown in the NVDA Add-on Store. `manifest.ini` and `buildVars.py` are the add-on metadata and SCons build config.

## Diagnostic logs

Every call to `buildTreeSummary` emits a `[TMTS perf]` line with per-phase timing and shape data. Format:

```
[TMTS perf] total=2052ms find_main=36ms counts=15ms walk=2002ms fallback=0ms (ran=False) truncated=True counts_trunc=False raw_seen=443 all_nodes=363 main_nodes=341 has_main=True scope=main-pos chrome_ranges=2 lm_ordered=True article=1 forms=10 interactive=11 url='...'
```

`find_main` is the `<main>` landmark lookup (now also captures the landmark's positional range). `counts` covers the `_iterNodesByType` enumerations (article, form inputs, link, button, edit, comboBox, checkBox, radioButton). **Form inputs are counted as `edit` / `comboBox` / `checkBox` / `radioButton` — deliberately NOT NVDA's `formField` quick-nav type, because in NVDA's definition a BUTTON is a form field.** Counting `formField` meant a control-dense CONTENT page maxed the counter: an IMDb title page (rate / watchlist / share / trailer) and a TV station front page both reported `forms=10`, classified as FORM, and the bare-form branch MOVED THE USER'S KEYBOARD FOCUS into the site's search box. Honest counts are much smaller, so `STRONG_FORM_INPUT_COUNT` came down 5 → 4 to match (the bar was calibrated against button-inflated numbers; "5" never meant five inputs). The whole counts phase (article + form inputs + interactive) shares ONE 0.6 s wall-clock budget, checked PER ITEM inside every enumeration — not just between enumerations, because on a page stuck mid-load a single `_iterNodesByType` call hangs on COM and a between-enumerations check can't stop it (krdo.com spent 10.5 s frozen that way, 2026-07-14: unbudgeted article count + always-run `edit` + six interactive enumerations). `_countInScope` also honors the 300-item scan cap (`_COUNT_SCAN_LIMIT`) — without it, when the identity check is failing (its known failure mode) nothing counts as in-scope, the in-scope `limit` never triggers, and the loop pays a parent-chain walk for every link on the page (Stack Overflow's tag page: 2038 ms). `_findMainLandmark` and `_singleArticleScopeRange` carry their own caps (0.5 s / 50 landmarks; shared counts deadline respectively) for the same reason. `edit` still runs first because it carries most of the FORM signal. When any budget or scan cap fires, the perf line shows `counts_trunc=True` and `TreeSummary.countsTruncated` is set — truncated counts are UNDERCOUNTS, fail-safe for FORM/APP (fire on large counts) but poison for NOTICE's shape-only path and KEY_RESULT (fire on small counts), so the classifier declines those two when the flag is set and leaves the page to the 1500 ms retry. The keyword NOTICE path (real text evidence) still fires. One truncation is NOT fail-safe and gets its own flag: a zeroed ARTICLE count drops the hasEditorialContent FORM block, and FORM moves keyboard focus — `TreeSummary.articleCountTruncated` makes the classifier treat editorial content as unknown and block FORM (form-URL escape hatch still applies). Contract details all three loops share (pinned by `tests/test_count_budgets.py`, which drives the helpers with fake iterators — they're importable outside NVDA): an expired deadline starts NO new enumeration; per-item checks sit at the loop BOTTOM so the budget guards fetching the NEXT item (the fetch is the hanging COM call — never discard the item already paid for, and never fetch past the scan cap); and an iterator exception preserves the partial count AND sets the truncated flag, because an exception must never read as a trustworthy zero. Classifier gates pinned in `tests/test_classifier.py`. Historically the biggest cost driver (~1 s on Zoom, 12.4 s on judysdogblog) because each item triggered a parent-chain `_inScope` walk; since the 2026-07-06 perf rework, pages with a usable scope range (`scope=main-pos` or `article`) count POSITIONALLY via `_countInRange` (start-inside-range compareEndPoints, capped at `_COUNT_SCAN_LIMIT=300` items scanned per type) — no parent chains. Identity-based `_countInScope` only remains for `main-id` (main present but no usable range) and `chrome` (no main, no single article) pages. `scope=` values: `main-pos` (positional main range — counts AND walk), `main-id` (identity fallback), `article` (positional single-article), `chrome` (identity chrome filter), `unscoped` (walk fell back), `unscoped-recount` (walk fell back AND the scoped counts were all zero, so counts were recomputed document-wide for consistency — the Zoom forms=0-on-a-7-input-form fix), `chrome-pos` (positional chrome exclusion, see the scope-hardening notes below), and `unscoped-depleted` / `unscoped-depleted-recount` (the depleted net widened a scoped walk that had kept too little to classify). `positionallyScoped` stays True only for `article` scope — deliberately NOT `main-pos`, so the defensive hero/cluster landing gates keep guarding main-scoped trees (pre-H1 deks/disclaimers live inside `<main>` on many sites). `walk` is the UNIT_PARAGRAPH walk. `fallback` is the unscoped re-walk, with `ran=` showing whether it actually executed. `raw_seen` is the raw chunk count for the walk (the older `[TMTS walk-empty]` line still fires for empty walks but only carries raw_seen — the perf line subsumes it). On judysdogblog.wordpress.com the perf line revealed a 12.4s blocking freeze inside `counts+video` despite a 327ms walk on 72 paragraphs — instrumentation added 2026-05-26 to drive the next perf decision.

`truncated=` says the walk stopped on a LIMIT rather than reaching the end of the document — and the `[TMTS walk-truncated]` line names WHICH limit (the 2.0 s `WALK_TIME_BUDGET_SEC` or the 1000-node `WALK_NODE_LIMIT`). That distinction is load-bearing: a briefly-lowered node cap silently starved GitHub's chrome-heavy tree and made the page land on a commit message, and the page got *faster* while doing it. Without the log naming the limit, that ships broken. The node cap is a BACKSTOP ONLY — the clock must be the thing that truncates.

`all_nodes=` is every node the walk produced regardless of scope. The unscoped fallback no longer re-walks the document (it used to, doubling the cost on exactly the slowest pages); it reuses this list, so `fallback=` is now a few ms rather than a second walk. The old `fb_raw_seen=` field is gone.

The perf line goes to two places:

- **NVDA's session log** (`%TEMP%\nvda.log`, viewable live via `NVDA+F1`). Rotates to `nvda-old.log` on NVDA restart, lost on the next restart after that.
- **Persistent perf log** (`%APPDATA%\nvda\TextMarksTheSpot-perf.log`) — append-only, ISO-timestamped, survives NVDA and Windows restarts. Self-rotates at 1 MB to `TextMarksTheSpot-perf.log.old` (one generation of history kept). Use this when collecting data across multiple sessions or asking a fresh AI session to analyze patterns. Write errors are swallowed silently so a locked or unwritable file can never break detection.

**BOTH PERSISTENT LOGS ARE OPT-IN (2026-07-22) AND THAT IS A PRIVACY GATE, NOT A TIDINESS ONE.** The perf log and the capture log (below) each record the FULL url of every page detected, query string and all, and the perf log outlives NVDA restarts, so it accrues for months. One real day of them banked an invoice link, OAuth authorization codes, and an app path carrying a `client_secret`. Both were gated on NVDA's DEBUG log level, which is NOT consent: people raise the log level for unrelated reasons and would never guess a screen-reader add-on had started recording where they go. They now write only when `%APPDATA%\nvda\TextMarksTheSpot-diagnostics-enabled` exists, checked once per session by `treeSummary._diagnostics_enabled()` so it cannot flip on under a user mid-browse; an unreadable `APPDATA` reads as OFF. Pinned by `tests/test_diagnostic_optin.py` and four separate entries in `tests/sabotage_check.py` (each writer sabotaged independently — a suite watching only one would not notice the other reverting to DEBUG). **The session-log copy was ALSO gated on 2026-08-18, and this reverses the earlier decision recorded here.** It used to stay ungated on the reasoning that NVDA's own log is one the user asked for, is wiped on the second restart, and is what makes a live `NVDA+F1` diagnosis possible. That reasoning was sound as far as it went, and two measurements settled it the other way. First, NVDA's own default log level is `INFO` and it logs spoken text via `log.io` at the IO level (verified in `config/configSpec.pyc` and `speech/speech.pyc`), so nothing of ours was ever written at the default anyway — the ungated copy only ever appeared for someone who had raised the level, which is precisely the "a debug log level is not consent" case. Second, at that level NVDA is already logging every phrase it speaks, so we were never the dominant source of page content in such a log — but we were much the tidiest, one clean greppable `url=` per page load, and THAT is the shape a browsing record actually takes. Volume was never the risk; structure and persistence are.

So **every `log.debug` in the add-on now goes through `treeSummary.dlog`** (`_GatedDebugLog`), which checks the same marker. Not just the lines with a url in them: "gate the sensitive ones" needs correct judgement at every future call site and one miss puts a stranger's browsing in a file, whereas "no bare `log.debug` anywhere" is auditable, and `tests/test_diagnostic_optin.py` audits it. Deliberately still ungated: the three `log.info` lifecycle lines and the fifteen `log.exception` calls, all static strings with no interpolation — they say nothing about where anyone has been and they are what makes a crash report from someone who never opted in worth having. Consequence: a live `NVDA+F1` diagnosis now needs the marker too, so the "create the marker, restart, reproduce" request covers all three logs rather than two. Consequence to plan around: asking a user for a perf log is now a two-step request (create the marker, restart, reproduce), and they deserve to be told what the file holds and how to delete it. On a fresh dev machine, create the marker or your own data silently stops arriving — that looks exactly like broken logging.

- **Capture log** (`%APPDATA%\nvda\TextMarksTheSpot-captures.jsonl`) — one JSON record per detection carrying every field the classifier and landing finders read, so `tests/replay_captures.py` reproduces a real decision offline with no NVDA. Same marker gate, self-rotates at 2 MB. **Its corpus is deliberately NOT in the repository**: `tests/fixtures/local/` is gitignored, `tests/test_replay_corpus.py` skips when the file is absent so a fresh clone runs green, and `tests/test_no_capture_corpus_committed.py` fails if a capture-shaped record is ever tracked again. Add corpus cases BY HAND from public pages worth pinning. Never paste the raw log into an issue or bulk-copy it into the repo; it is a record of someone's browsing, and a data file shaped like one invites the next person (or the next AI session) to add a real one.

`[TMTS walk-preamble-drops]` lists what the scope filter dropped BEFORE the scoped region started, capped at `_PREAMBLE_DROP_LOG_LIMIT`=40 with the true total reported separately, session log only. The post-start `[TMTS walk-drops]` line deliberately ignores that region because on a normal page it is just nav and banner — which made content placed above `<main>` invisible in the logs, indistinguishable from never having been in the buffer. That is exactly where Google puts its AI Overview. The capture record carries the same region as `pre_main_nodes` (`TreeSummary.preMainNodes`, bounded by `_PREAMBLE_NODE_LIMIT`=60) so a rule about it can be replayed offline; the classifier and landing finders never read it. **Before proposing any rule that admits content from above `<main>`, read DEBUGGING.md section G** — it was measured across 40 swept sites and the answer is that the pre-main region is chrome essentially always (cookie banners, headline teasers, subscription marketing), Google is 1 of 36, and neither "has a heading before it" nor "is a multi-paragraph block" separates the outlier.

A second line, `[TMTS walk-phase]`, breaks the walk's wall clock down by CALL SITE — `expand`, `text`, `obj` (`NVDAObjectAtStart`), `fields` (the control-field stack), `scope` (`_inScope`) — plus `chunks`, `parent_derefs`, cache hits/misses, and the per-chunk verdict tally `positional` / `pos_drops` / `identity` / `field` / `field_drops`. `field_backend=y|n` says whether this document's backend populates `field['landmark']` at all (`_fieldsCarryLandmarks`); an `n` here means the fast field path never engaged and the walk silently fell back to parent chains, which is correct but slow, so it is the first thing to read on an unexplained slow walk. The aggregate `walk=` number cannot name the expensive call, and that ambiguity is what stalled the store.payproglobal.com checkout investigation (2026-07-17): every phase slowed together on the bad loads, so "the parent chains are the cost" stayed a guess. Two independent reviews both declined to approve a fix without this measurement. It goes to the session log always, but to the PERSISTENT log only when the walk truncated or took ≥ 1.0 s, so routine pages don't halve the rotation history. It is written from inside the walk, so it lands immediately BEFORE the `[TMTS perf]` line for the same detection — that adjacency is what ties it to a URL. Note what the breakdown will NOT explain: `copy`, `collapse`, and `compareEndPoints` on a virtual-buffer TextInfo are offset arithmetic, not browser COM calls, so they are deliberately untimed.

## Build and packaging

The project uses NV Access's official addon template structure. Build is done by **SCons**. The Python code under `addon/globalPlugins/TextMarksTheSpot/` is the source of truth; edit there, rebuild the `.nvda-addon`, reinstall in NVDA.

**Archive layout (still important even with SCons):** the `.nvda-addon` zip must have `manifest.ini` at the root AND the *contents* of `addon/` at the root — NOT the `addon/` folder itself. So the zip looks like:

```
manifest.ini
globalPlugins/TextMarksTheSpot/__init__.py
doc/en/readme.md
```

If `globalPlugins/` is not a direct child of the archive root, NVDA registers the addon (the manifest is found) but loads **zero plugins** and logs **no error**. SCons produces the right layout automatically; this note exists in case anyone builds by hand.

### Where things live

- `buildVars.py` (project root) — addon metadata (name, version, summary, description, changelog, author, URLs, min/lastTested NVDA versions, license). Bump version here, not in the manifest.
- `sconstruct` (project root) — SCons build script. Don't edit unless you know what you're doing.
- `site_scons/` — SCons helper tools (NVDATool, gettexttool).
- `manifest.ini.tpl` + `manifest-translated.ini.tpl` — SCons fills these in from `buildVars.py` to produce `addon/manifest.ini` at build time.
- `changelog.md` (project root) — user-visible changelog. Update for each release.
- `readme.md` (project root) — user-facing add-on documentation. **SCons auto-copies this to `addon/doc/<baseLanguage>/readme.md` at build time**, then renders it to `readme.html` for the Add-on Store. Don't maintain `addon/doc/en/readme.md` directly — it gets overwritten on every build.
- `style.css` (project root) — CSS for the rendered HTML doc.
- `pyproject.toml` — linting / formatting config.
- `COPYING.txt` — GPL v2 license text.

### Required tools

Install once on a fresh dev machine:

- Python 3.13 (matches NVDA 2026.1+ but older NVDAs work too with their bundled Python).
- `python -m pip install --user scons markdown`
- gettext (msgfmt + xgettext) on PATH. Install via `winget install --id mlocati.GetText`.

### Build commands

From the project root (PowerShell):

```powershell
# Build locally. THIS is the local build command, not bare `scons`.
.\build.ps1

# Build and launch it so NVDA installs it
.\build.ps1 -Install

# Clean build artifacts (addon/manifest.ini, addon/doc/en/readme.{md,html}, addon/doc/style.css, the .nvda-addon)
scons -c

# Update the .pot translation template (when source strings changed)
scons pot
```

`build.ps1` runs SCons and then MOVES the output onto the single unversioned
name, sweeping any versioned leftovers, so the project root holds **exactly one**
`TextMarksTheSpot.nvda-addon` and it is always the newest build. Two files side
by side is how a stale build gets installed by mistake, and the installed copy
was always the unversioned one anyway.

Bare `scons` still works and still emits `TextMarksTheSpot-<version>.nvda-addon`,
named from `buildVars.py:addon_info["addon_version"]`. Do not rename that SCons
target: `.github/workflows/release.yml` verifies the versioned filename against
the pushed tag, and CI runs plain `scons`. Use bare `scons` locally only when you
specifically want to inspect the versioned artifact, and delete it afterwards.

**Note**: scons might fail to install in your default Python; if so, the `scons.exe` from `python -m pip install --user scons` lives in `C:\Users\<you>\AppData\Roaming\Python\Python313\Scripts\`. Make sure that directory is on PATH or call it by full path.

Running `scons` by hand is for **local smoke-testing only**, not for publishing — see "Releasing" below.

### Committing and pushing: standing authorization (granted 2026-07-19)

Casey has delegated the *timing* of commits and pushes on this project. Use your
judgement: commit at meaningful checkpoints, push so work is not stranded on one
machine, and do not stop to ask each time.

(No `.claude/settings.json` for this — one was written and removed the same day
at Casey's request. A settings file only suppresses harness permission prompts,
which he is not seeing; the policy is what matters and it lives here. Revisit
only if prompts actually start interrupting him.)

This covers `git add` / `commit` / `push` of code, tests, and docs on a branch.
It does NOT extend to anything that reaches users, and the boundary is not
subtle: **a tag push is a release.** `.github/workflows/release.yml` fires on
`v*.*.*` and publishes to GitHub Releases, which is what the Add-on Store entry
downloads. So `git tag`, pushing a `v*` ref, `gh release`, and any store
submission still need Casey to say go — they are in the `ask` list for exactly
that reason. Same for force-pushes and hard resets, which destroy work rather
than publish it.

The reason to keep pushing freely: this branch sat 20 commits deep and entirely
unpushed for days. That is a single-drive failure away from losing a week of
reasoning that lives mostly in commit messages and implementation-notes.md.

### Releasing (CI publishes — do NOT create the release by hand)

Releases are published automatically by `.github/workflows/release.yml`. Pushing a tag matching `v*.*.*` triggers a windows-latest job that runs the tests, builds with SCons, and creates the GitHub release with two assets: `TextMarksTheSpot-<version>.nvda-addon` (versioned/archival) and `TextMarksTheSpot.nvda-addon` (unversioned — backs the stable "Latest" download URL).

The release flow is:

1. Bump `addon_version` in `buildVars.py`.
2. **Write the changelog. In BOTH places. This is not optional for a real release.**
3. Commit.
4. `git tag vX.Y.Z` — must match `addon_version` (CI verifies the built filename against the tag and fails the run if they differ).
5. `git push origin main`, then `git push origin vX.Y.Z`.
6. Stop. CI builds and publishes. Watch it with `gh run watch <run-id> --exit-status`.

#### The changelog is a release deliverable, not paperwork

Every real release — anything tagged, anything that reaches GitHub Releases or the NV Access store, anything we've decided is a keeper — ships with a written, user-facing "What's new". During test iterations (rebuild, reinstall, try again), don't bother; nobody reads a changelog for a build that exists for ten minutes. The moment a version is real, the changelog is part of it.

**It has to go in TWO places, and they are easy to get out of sync (this happened on 1.0.10):**

- `changelog.md` at the repo root — the human-readable history.
- `addon_changelog` in `buildVars.py` — this is what NVDA actually shows the user. SCons writes it into `manifest.ini`. Updating only `changelog.md` ships stale release notes to every user.

**Write it for the person using the add-on, not for a developer.** They do not know what a TreeInterceptor is, they do not care which function changed, and "fixed a bug in the classifier" tells them nothing. Say what they will *notice*:

- Bad: "Fixed TI-identity gate to compare URL." Good: "The add-on now actually runs when you open a page. It was skipping roughly two out of every three page loads and doing nothing at all."
- Lead with the change that matters most to them, not the one that was hardest to fix.
- Name the real-world symptom they'd have hit ("this is why pages so often needed a refresh, or a press of Z").
- **State the known gaps honestly.** If recipe sites still land on a marketing line, say so. Users trust a changelog that admits what's still broken.

**Run it through the `humanizer` skill before shipping**, same as any other prose deliverable, and obey Casey's punctuation rules: no em dashes, straight quotes. Remember this text is read aloud by a screen reader — no emoji, no symbol bullets, no decorative characters.

**A side-loaded add-on will NOT show "What's new" even when the changelog is correct.** NVDA's store reads it from the installed manifest fine (`addonStore/models/addon.py:230-232`), but the menu item is gated on the add-on having come from the store (`gui/addonStoreGui/viewModels/store.py:289-291`). So the absence of "What's new" on a local install is expected and is NOT evidence of a packaging bug. Don't go chasing it.

**Do NOT also run `gh release create` after pushing the tag.** CI already creates the release; a manual one collides (CI fails with "a release with the same tag name already exists") and omits the unversioned asset the Latest URL depends on. If a manual release got created by mistake: `gh release delete vX.Y.Z --yes` (keeps the tag), then `gh run rerun <run-id>` to let CI publish properly.

The manual `scons` + `gh release create` path is the **fallback for when CI is broken** (release.yml says so in its header) — not the normal flow.

### Verify the build

```
Add-Type -AssemblyName System.IO.Compression.FileSystem
$z = [System.IO.Compression.ZipFile]::OpenRead("C:\OneDrive\Downloads\Text Marks the Spot\TextMarksTheSpot-0.1.0.nvda-addon")
$z.Entries | ForEach-Object { $_.FullName } | Sort-Object
$z.Dispose()
```

Top-level entries should be `doc/...`, `globalPlugins/...`, `manifest.ini`. If you see `addon/...` anywhere, the build is broken.

### Other useful shortcuts

- `NVDA+Ctrl+F3` — reload all add-ons in the running NVDA.
- `NVDA+F1` — open the NVDA log viewer (where probes and the add-on log to).
- Installed-copy path (Windows, for reference): `%APPDATA%\nvda\addons\TextMarksTheSpot\`.

### Tests

Pure-Python unit-test suite at `tests/` covering the classifier (`tests/test_classifier.py`) and landing finders (`tests/test_landing.py`). Run with `python -B -m pytest tests/` from the project root. Requires `pip install pytest` once (no NVDA needed — the classifier and landing finders are deliberately pure-function for exactly this reason). **Use `-B`, not bare `python`.** CPython validates a `.pyc` against the source's mtime and SIZE, so a source file edited and re-run within the same second can execute the PREVIOUS bytecode and report a pass about code that was never loaded. That is the trap `tests/sabotage_check.py` documents, and it is not specific to sabotage runs; it bites any edit-then-immediately-rerun loop.

The tests are regression guards: every bug fixed in this session got at least one fixture-based test pinning the correct behavior. When changing classifier thresholds or landing logic, run the tests FIRST. If a test fails after a "tuning" change, ask whether the test is still semantically correct before "fixing" it — most of them encode page-shape patterns that recurred during real debugging (bestmidi BAD walk, Google Forms closed, Calendar Google-Account-vs-appointment, fast.com KEY_RESULT, etc.).

Commands, from the project root:

```powershell
python -B -m pytest tests/                           # whole suite, well under a second
python -B -m pytest tests/test_landing.py -q         # one file
python -B -m pytest tests/test_landing.py::test_definitionalLedeBeatsAPrerequisiteNoteAboveIt  # one test
python -B -m pytest tests/ -k chrome_scope           # one topic across files
python -B tests/sabotage_check.py                    # prove the tests FAIL when their rule is deleted
python -m ruff check . && python -m ruff format --check .   # lint / format (tabs, line length 110)
```

**Nothing runs the tests on push or on a pull request.** `.github/workflows/release.yml` is the only workflow and it triggers on a `v*.*.*` tag, so a broken test surfaces at release time, not at commit time. Run the suite locally before pushing; do not assume a green branch means CI checked anything.

`sabotage_check.py` is not optional ceremony on this project. A green suite has three
times been shown to pass with a safety input deleted, so any change to a scope,
budget, or diagnostics gate gets a sabotage entry, not just a test.

Two REPORTING tools, neither of them pytest, both useful before touching a heuristic:

- `python tests/replay_captures.py [--url substr]` replays real captured pages
  through the live classifier and landing finders offline, printing the intent and
  the landing it would pick. This is the fastest way to see the effect of a threshold
  change across dozens of real pages at once. It reads the capture log under `%APPDATA%\nvda`
  by default, which is the user's own browsing: analyze it in place, never copy it
  into the repo.
- `python tests/run_classifier.py` and `python tests/run_landing.py` run the committed
  fixtures and print a pass/fail report.

Test-file inventory, since the names do not all announce what they guard:
`test_classifier.py` (intent gates), `test_landing.py` (the landing cascade),
`test_treeSummary.py` and `test_walk_wiring.py` (the walk's pure helpers and the
scan-to-select-to-verdict chain), `test_chrome_scope.py` and `test_scope_depleted.py`
(chrome positional scoping and the depleted net), `test_scope_cache.py` (the
`id(obj)` wrong-answer bug), `test_count_budgets.py` (the shared counts deadline),
`test_diagnostic_optin.py` (the privacy marker, including the audit that no bare
`log.debug` exists), `test_find_needle.py`, `test_hostname.py`,
`test_replay_corpus.py` and `test_no_capture_corpus_committed.py` (the corpus stays
out of git).

NVDA-dependent code (treeSummary's walk, speech, tones, event hooks) is NOT unit-testable — that surface stays manual via the log viewer (`NVDA+F1`, search for `[TMTS]`). Each new NVDA API gets a 5–20 line standalone probe add-on before it appears in real code — see "API probes before real code" below and SPEC.md.

## API probes before real code

For each NVDA API the add-on uses for the first time, write a minimal standalone probe add-on, install it, observe in the NVDA log viewer, uninstall. Probes listed in SPEC.md §"API probes BEFORE committing real code": `event_treeInterceptor_gainFocus` firing behavior, `sayAll` / `SayAllHandler.readText` from an arbitrary position, settings-panel `categoryClasses` register/terminate cleanliness, `tones.beep` from inside a focus event. Each probe is 5–20 lines.

Probes live in `probes/<name>/` (each a miniature add-on: `manifest.ini` plus `addon/globalPlugins/...`) and build with the generic wrapper:

```powershell
.\probes\build_probe.ps1 field_stack   # -> probes\field_stack\tmts_probe_field_stack-0.1.0.nvda-addon
```

Three are kept because their findings are load-bearing and re-provable: `focus_event` (which trigger events actually fire in a GlobalPlugin), `field_stack` (whether a backend populates `field['landmark']`, which is what the walk's primary scope answer depends on), and `shadow`. Keep a probe after it answers its question if the answer is one a future session would otherwise take on trust.

## Gesture behavior and phasing

Current shipped behavior:

- `Z` in browse mode scans forward from the user's current browse cursor to the next substantial content paragraph. It skips headings because NVDA's `H` already handles heading navigation, and it skips known chrome paragraphs. If nothing qualifies below the cursor, it says "Nothing else to land on" and does not wrap.
- `Shift+Z` returns to the saved automatic landing on the current page without recalculating. If NO landing is saved for the page (the auto-trigger structurally can't fire on tab switches — no `documentLoadComplete` — so a stale tab has nothing saved), Shift+Z runs full one-time detection instead, resetting the debounce gates like Z does; on an excluded site it keeps the plain "No saved landing" message (double-Z stays the only exclusion override). Added 2026-07-16 after the starttesting.net login tab left the user stranded with no gesture that could summon detection.
- `NVDA+Z` toggles the current hostname in the per-site exclusion list after confirmation. On an excluded site, double-pressing `Z` runs one-time detection without changing the list.
- Outside browse mode or while browse mode is pass-through, `Z` and `Shift+Z` pass through to the host app.

Deferred:

- Article sequence: next major section / comments / no more sections.
- Form sequence: first error / next empty required / submit.
- Email and search-result sequences.
- Web-app / dashboard primary CTA detection.
- Vision Enhancement Provider flash effect.

Never rebind NVDA's built-in quick-nav keys (Tab, `h`, `f`, `t`, `k`, `b`, etc.). Future sequences must not wrap or guess at the end.

## Known limitations (deferred fixes)

These are not bugs — they're real architectural limitations we've reasoned about and chosen to defer. Future work should address them at the architectural level, NOT by adding per-site special cases.

- **In-scope filter is identity-based, not position-based (partially fixed).** `treeSummary._inScope` walks `obj.parent` up looking for `cur is mainObj` or chrome-landmark identity. NVDA returns different `obj.parent` instances across accesses on some sites, so the identity check unreliably fails. On Calendar this manifests as: `raw_seen=51` chunks visited, but only ~8 make it into `mainNodes` because the parent walk can't confirm they're under `<main>`. The addon then lands on chrome text (e.g. "Google Account: Casey Mathews") instead of the appointment. **The positional fix is now implemented for the no-`<main>`/single-`<article>` case** (2026-06-17): when there is no `<main>` landmark but exactly one `<article>`, `buildTreeSummary` scopes the walk positionally to that article via `_singleArticleScopeRange`, and `_walkMainNodes` keeps each chunk only if `info.compareEndPoints(scopeRange, "startToStart") >= 0 and info.compareEndPoints(scopeRange, "endToEnd") <= 0`. This drops nav (before the article) and comments/footer/sidebar (after it) — on steviet3.wordpress.com it cut `mainNodes` from 113 to 30. The walk sets `TreeSummary.positionallyScoped=True` on success (False if it fell back to the unscoped walk), and `findArticleLanding` then lands on the first substantial paragraph instead of applying the noisy-tree hero/cluster gates. The perf line carries `scope=main|article|chrome|unscoped`. **Load-bearing gotcha:** the scope range MUST come from the quick-nav item's own `textInfo` (`item.textInfo`), NOT `obj.makeTextInfo(POSITION_ALL)` — the latter builds a range in a different coordinate space and matched zero chunks (a degenerate range), which is the same "makeTextInfo can be more restrictive than expected" trap noted in `_walkMainNodes`. The `<main>`-present case is ALSO positional (`scope=main-pos`): `_findMainLandmark` returns the landmark's own quick-nav `textInfo` alongside the object, and counts plus walk both use it.

**The `chrome` case is positional now (2026-07-18, `scope=chrome-pos`) — but the reasoning is subtle and two design attempts died first. Read this before touching it.** With no `<main>` there is no range to be INSIDE, so it inverts: `_findMainLandmark` collects the CHROME landmark ranges in the pass it already makes, and the walk drops any chunk whose START falls inside one. Measured first, per DEBUGGING.md: `[TMTS walk-phase]` on the payproglobal checkout showed 1808 ms of a 2035 ms walk in the parent chains (341 dereferences for 33 chunks), against 223 ms for `NVDAObjectAtStart` and 2 ms for expand plus text.

**Attempt 1, shelved on branch `chrome-pos-attempt`: gated on "did the landmark enumeration complete?"** Unimplementable. NVDA's `VirtualBuffer._iterNodesByAttribs` wraps its `VBuf_findNodeByAttributes` call in a handler that DISCARDS the exception and returns, so a native failure is indistinguishable from natural exhaustion — verified by disassembling `virtualBuffers/__init__.pyc` from the installed `library.zip` (`PUSH_EXC_INFO` / `POP_TOP` / `POP_EXCEPT` / `RETURN_CONST None`). A completeness flag can return True holding a partial list.

**Attempt 2: bounded trust.** Never ask whether the scan finished, only how far it got. `trustBoundary` is the START of the last landmark successfully placed; `_startsBefore` compares STRICTLY, and `trustFrozen` is monotone, so if the boundary landmark was placed then every earlier emitted landmark was too. Truncation costs speed, never correctness.

**Why that STILL was not enough, and the trap to never repeat: the probe that "confirmed" the premise was hollow.** A passive probe reported `ordered=True` on 15 of 15 real pages and it was presented as evidence. It was not. NVDA seeds each landmark search with the PREVIOUS MATCH'S START OFFSET and searches forward, so emitted starts are nondecreasing BY CONSTRUCTION — `ordered=False` could never have occurred. The property actually needed is that the emission is COMPLETE, and a landmark starting at the SAME offset as the one just returned may be silently skipped. That is omission mid-stream, which ordering cannot detect and truncation logic cannot catch. `<section aria-label="...">` wrapping a `<nav>` with no text between them is exactly that shape: the section is emitted, the nav may not be, the nav is absent from `chromeRanges`, a later footer advances the boundary past it, and every chunk of that navigation reads as trusted CONTENT. A blind user lands in a menu. **When a probe comes back unanimous, ask whether it could ever have come back the other way.**

**The structural fix, and the C++ that backs it.** VERIFIED in `nvdaHelper/vbufBase/storage.cpp`, because the fix does depend on it: `VBufStorage_fieldNode_t::nextNodeInTree` (FORWARD) goes to `firstChild` when present, else up and to `next` — a PRE-ORDER walk, so an ancestor is emitted before its descendants; and `findNodeByAttributes` reseeds via `locateTextFieldNodeAtOffset`, which returns the TEXT LEAF at that offset, so the next search resumes from inside the just-matched landmark's own subtree. Everything skipped is therefore a DESCENDANT of an emitted landmark. The outer member is always the one emitted, so the dangerous inverse (inner emitted, outer skipped and extending past it) cannot occur. A skipped equal-start landmark is necessarily nested inside the emitted one, so any chunk it could contain also lies inside an emitted landmark's range. So `_chromePosVerdict` answers in three steps: inside an emitted CHROME range → excluded (nested chrome inside chrome excludes the same text, so omission is harmless); inside an emitted NON-CHROME range (`untrustedRanges`) → defer to the identity filter, since that is the only place an omitted nested nav can hide; inside no emitted range → the positional answer is sound. Every tri-state `None` from `_startsInAny` / `_startsBefore` propagates to "ask identity" — there is deliberately no "assume not excluded" branch, because that is how navigation becomes article text. `_chromePosVerdict` and `_selectScope` are pure and unit-tested. **Extracting the decision is NOT the same as covering the wiring** — both reviewers showed that deleting the `otherRanges` append left the whole suite green, because every test hand-built its own untrusted list. `tests/test_chrome_scope.py` now drives scan → select → verdict end to end with no hand-built lists, and that chain was confirmed to fail when the append is removed. Twice this session a safety input was found deletable without a test noticing; assume it will happen again unless the chain is tested, not the pieces.

**Two more things this round fixed, both found in review and both independent of scoping.** (1) `setFocusOnFirstFormInput` filtered candidate fields against `<main>` — and with NO `<main>` that filter returned True for EVERY field, so "first form input in document order" meant the first editable element anywhere, routinely the header search box. This branch MOVES KEYBOARD FOCUS, so it dropped a blind user into site chrome; it is the Zoom-language-picker failure on the branch nobody scoped. It now excludes fields starting inside a chrome landmark when there is no `<main>`. (2) In the `chrome-pos` path a chunk whose `NVDAObjectAtStart` is None no longer defaults to in-scope. Elsewhere that default is harmless, but chrome-pos routes its uncertain chunks to the identity filter AS its safety mechanism, and for an objectless chunk that filter cannot run at all — so the one chunk class the design leans on the fallback for was the one class with no fallback. Those chunks are now out of scope, they still reach `allNodes` so the depleted net can recover them, and the cost of being wrong is a missed paragraph instead of a landing in a menu.

**The depleted net keys on `positionalDrops == 0` (positional EXCLUSIONS), not on the scope name.** Two earlier versions were wrong in opposite directions: excluding `chrome-pos` outright switched the net off on the commonest no-`<main>` shape (a single top-of-page nav puts the trust boundary at offset 0, so nothing is decided positionally and the page is chrome-scoped in all but name), while admitting `chrome-pos` unconditionally let a page whose exclusions WORKED be widened back open by two long chrome paragraphs, re-admitting the nav and cookie text that had been correctly removed. The scope name cannot separate those; the decision count can.

**A `chrome-none` scope existed briefly and was REMOVED 2026-07-19 as a merge blocker. Do not rebuild it.** It promoted a page whose landmark enumeration yielded nothing into a walk that skipped chrome checking ENTIRELY, gated on `seen == 0 and exhausted and interactive_count > 0`. The `exhausted` flag was doing the safety work and could not: NVDA's `_iterNodesByAttribs` CATCHES the native exception from `VBuf_findNodeByAttributes` and RETURNS, so a natively FAILED landmark search arrives as `seen=0, exhausted=True` — byte-for-byte the shape of a genuinely landmark-free page. `exhausted` ruled out only a Python exception ESCAPING the iterator, which is the one shape NVDA does not produce here. This is the SAME indistinguishability that killed `chrome-pos-attempt`, reintroduced in a different function, and it had been looked at directly the same day and mis-filed as "a pre-existing accepted risk" rather than as a bug — noticing a hazard is not disposing of it. The interactive-count corroboration did not close it and was weaker than it read: every quick-nav type runs through the SAME swallowing iterator, so a non-zero link count can itself be a silent partial result, and the counts run AFTER the landmark scan, so a transient mid-load failure can clear before the corroborating sample is taken — and mid-load is exactly when `documentLoadComplete` fires. There is NO signal at the `LandmarkScan` layer that can separate the two zero-seen cases; the per-chunk field stack is the only positive witness available. The cost of removal is real and accepted: on a landmark-free page with many chunks (stevequayle.com) the walk goes back to a ~14-dereference COM chain per chunk and may produce NO LANDING inside the 2 s budget. That is a silence, not a wrong landing, which is the direction guardrail 3 specifies. `tests/test_chrome_scope.py` pins the native-swallow shape, and `tests/sabotage_check.py` confirms those tests fail when the shortcut returns — including under a new name and disguised as an empty exclusion list.

**The control-field stack is the walk's PRIMARY scope answer now, and it is barely
described anywhere but the source.** `_landmarkScopeFromFields` reads the leading
control run of each chunk's own `TextInfo` and returns a tri-state verdict (not
chrome / chrome / unknown) with no parent dereference at all; unknown falls through
to the positional or identity path exactly as before. It is gated by
`_fieldsCarryLandmarks`, which matches the TextInfo's MRO against the Gecko
virtual-buffer class BY NAME AND MODULE, because `field['landmark']` is written by
the backend's `_normalizeControlField`, not by any TextInfo contract: Gecko writes it
and Chromium inherits it, WebKit does not write it at all, and MSHTML is excluded on
purpose for want of probe evidence. Do NOT re-gate this on `backendName` — Chromium
does not declare its own and inherits Gecko's string, so that gate cannot tell the
engines apart. If NV Access ever renames the Gecko class the gate fails silently to
False everywhere and the add-on quietly reverts to parent chains, correct but slow,
which is exactly what `field_backend=y|n` on the `[TMTS walk-phase]` line exists to
make visible in one page load. `probes/field_stack/` is the probe this was built on.

**Still on the identity path, deliberately: the COUNTS** (~620 ms of a 2.7 s page). So on a `chrome-pos` page the counts and the walk can describe slightly different trees, which weakens the "ONE scope for both" invariant in `buildTreeSummary`. FORM is the intent that moves keyboard focus, so watch this if a form page misbehaves.

**Known unfixed, pre-existing on every scope path:** a chunk whose `NVDAObjectAtStart` is None is treated as in-scope with no chrome check (`obj is None or _inScope(...)`). Deliberately not changed under time pressure; it predates this work.

**The `id(obj)` memo inside `_inScope` was a wrong-answer bug, fixed 2026-07-18 — do not "simplify" the fix away.** It stored `{id(obj): bool}`, the bare address. Its ancestors are transient (NVDA caches each parent on its child, and NVDA's own instance registry is a `WeakKeyDictionary`, so the chain dies with the child when the walk rebinds `obj`), and CPython hands freed blocks back LIFO, so the next chunk's objects land on exactly the cached addresses. Measured: 2000 transient objects of one class occupied 2 distinct addresses. A dead entry therefore matched a live, unrelated object and handed it the dead one's verdict. Reproduced against the old code in `tests/test_scope_cache.py`: after 100 nav chunks, all 100 following CONTENT chunks answered out-of-scope. That empties `mainNodes`, which trips the unscoped fallback, which is why the symptom read as "the identity check unreliably fails" and why the recovered tree contains nav and footer — the bestmidi signature. The cache now stores `(obj, verdict)`, pinning the address, and verifies `entry[0] is obj` on hit so a dropped reference degrades to a miss instead of a wrong answer. Keying on the object instead does NOT work: `NVDAObject.__eq__` is logical (`_isEqual`) but `__hash__` is `super().__hash__()`, i.e. address-based, verified in NVDA's own bytecode.
- **Sparse walks on heavily-styled DOMs.** Some sites' DOM/CSS structures (fast.com's styled `<div>` widgets) cause NVDA's `UNIT_PARAGRAPH` walk to produce very few chunks (4 total on fast.com), missing important content entirely. The classifier never sees the speed widget. Adding a richer walk strategy (NVDAObject recursion, `_iterNodesByType("paragraph")`, or saliency-based detection per the SPEC deferred-features note) would help, but adds significant code + tuning. Deferred.
- **Visual saliency detection (designed, not built).** Some sites style what is logically a heading as a styled `<div>` instead of `<h1>` — NVDA's role-based heading detection misses it. The principled fix is a saliency walker recording `(text, role, x, y, w, h)` from `obj.location` per chunk, computing typical chunk height + vertical rhythm, flagging chunks that are taller, isolated, or centered as synthetic headings. Mission-aligned ("help users where developers failed") and would also subsume some KEY_RESULT cases. Deferred per SPEC notes. Does NOT help fast.com (it's the sparse-walk problem above, not a missing-heading problem).

## Out of scope

Do not propose or build: AI/LLM integration, reader-mode DOM rewriting, Reaper/audio-editor integration (OSARA), EPUB handling (Paperback), general summarization.

## Translations and store strings

Every user-facing string is wrapped in `_()` with a `# Translators:` comment above it. Required by NV Access store submission. Translation scaffolding goes in early even though Phase 1 is English-only.

## Accessibility output rules (global)

These come from the user's global CLAUDE.md and apply to anything the add-on speaks or writes to the log/UI:

- Never put emoji in any string spoken aloud — NVDA reads emoji as their Unicode name.
- No Unicode box-drawing characters (`─ ━ ═ │ ┌ ┐ └ ┘ ├ ┤ ┬ ┴ ┼ ╔ ╗ ╚ ╝`) in any console/log output. Plain ASCII (`-`, `|`, `+`) or indented lists.
- Always call explicit `unload()` / `shutdown()` / `terminate()` on close. Never rely on `__del__`.
