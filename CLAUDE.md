# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read this first

**SPEC.md at the project root is the load-bearing handoff.** Read it before touching code. It contains the locked guardrails, locked design decisions, the per-page-type Z sequences, the phasing plan, the build/test workflow, and the store submission checklist. CLAUDE.md is a pointer into SPEC.md, not a replacement for it.

## What this project is

NVDA screen-reader add-on (`textMarksTheSpot`) that auto-jumps the browse cursor to where real content starts on web pages and email messages, then speaks that single paragraph so the user knows where they landed — no keypress needed, and no `sayAll`. From there the user reads on with normal NVDA navigation (Down Arrow, `h`, etc.). Pure heuristic, no AI, no network. Targets NVDA 2024.1+ (Python 3.11+), pure Python so it runs in both 32-bit and 64-bit NVDA. GPL v2.

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

## Architecture

The add-on is one NVDA `GlobalPlugin` at `addon/globalPlugins/textMarksTheSpot/`. The SPEC describes more files than currently carry weight — the load-bearing modules right now are `__init__.py`, `classifier.py`, `tree_summary.py`, `detection/web.py`, and `feedback.py`. The other files exist as stubs or scaffolds for future phases.

Load-bearing modules:

- `__init__.py` — `GlobalPlugin` class, all trigger logic, and the `Z` script (browse-mode binding). Hooks `event_documentLoadComplete` AND `event_treeInterceptor_gainFocus` — explicitly NOT `event_gainFocus`, because that fires on every alt-tab and in-document focus change. `event_treeInterceptor_gainFocus` is the narrow hook that fires when a TreeInterceptor specifically gains focus (refresh, navigation, browse-mode entry) — different TI identity on refresh, same TI on alt-tab, so the TI-identity gate distinguishes them. Debounces along three axes before any tone fires: (a) same TI as last run → skip; (b) same URL within `_REFIRE_COOLDOWN_SEC` (2.0 s) → skip (catches SPA-ish sites like DDG/Gmail that emit duplicate document-load events for one logical page load); (c) focus is on an editable control → skip silently per guardrail #6. The `Z` script bypasses (a), (b), and the URL/timestamp gates (the user is explicitly asking to redo detection). Calls `feedback.working()` then `feedback.progress_start()`, runs detection in `_run_detection`, dispatches by intent in `_handle_result`, calls `feedback.progress_stop()` in a finally. **Speech path differs by intent:** ARTICLE / LIST / NOTICE / KEY_RESULT land via `speech.speakTextInfo` on a captured textInfo (with `speech.cancelSpeech` immediately before — the only sanctioned cancel point). **FORM uses a separate path**: `ui.message` announces the form title (mode-agnostic so it survives NVDA's auto-switch into focus mode when the page auto-focuses an input), then `set_focus_on_first_form_input` moves keyboard focus to the first form field so NVDA's own focus speech announces it. Without this, Google-Forms-style pages would swallow our browse-mode `speakTextInfo` silently. **Retry mechanism:** if the first detection attempt returns False (no landing acted on), schedules a single retry at +`_RETRY_DELAY_MS` (1500 ms) via `wx.CallLater`. The retry is silent (no second working tone), verifies URL hasn't changed, and either lands+speaks (if content has now hydrated) or plays the two-beep `not_found` tone. New events (real navigation, Z press, refresh, alt-tab to new TI) cancel any pending retry. This is the principled fix for SPA hydration delays — no per-site code, just "wait, look again." `not_found` only plays on the retry's no-result outcome, not the first attempt; that way the first attempt's silence covers the wait gap cleanly.
- `classifier.py` — pure-Python intent classifier over a `TreeSummary`. Intents: `SILENT_FOCUS_HONORED`, `FORM`, `ARTICLE`, `VIDEO`, `LIST`, `APP`, `NOTICE`, `KEY_RESULT`, `UNKNOWN`. Order matters — high-confidence NOTICE (keyword + small shape) fires early, ARTICLE-cluster before KEY_RESULT before ARTICLE-hero before APP before NOTICE-fallback. Key thresholds: `PARAGRAPH_MIN_CHARS=100` (cluster substantial bar), `HERO_PARAGRAPH_MIN_CHARS=50` (decoupled from cluster bar — landing-page intros commonly run 50–99 chars), `NOTICE_MAX_TOTAL_CHARS=1500`, `NOTICE_MAX_HEADINGS=3`, `NOTICE_MAX_INTERACTIVES=6`. `notice_keyword_match` boosts NOTICE confidence 0.65 → 0.85 when status-keyword regex hit. `KEY_RESULT` matches "label (10–40 chars) + value (1–8 chars, mostly digits) + unit (explicit or implicit `%$°` in value)" at lead position (before any 100+ char body paragraph) — catches fast.com-style speed widgets, weather, stock single-quotes, battery indicators.
- `tree_summary.py` — NVDA binding layer. Walks the browse-mode tree by UNIT_PARAGRAPH, builds a `TreeSummary` for the classifier, captures parallel textInfo positions for `get_landing_textinfo`. Also runs the NOTICE status-keyword regex (`_NOTICE_RE`) against full chunk text during the walk and sets `summary.notice_keyword_match`. Exposes `is_focus_editable()` publicly so the trigger can pre-check before any tone, and `set_focus_on_first_form_input(ti)` for the FORM intent. **Two-stage fallback**: main-scoped walk → unscoped walk. The previous intermediate chrome-filtered walk was removed for performance — it uses the same parent-chain mechanism as the scoped walk and almost always failed the same way when the scoped walk failed, doubling detection time on hard pages (webaim 413-node walk dropped from ~9 s → ~5 s after removal). **Known limitation**: the parent-chain landmark check (`_in_scope`) is unreliable on some sites — NVDA returns different object instances for the same logical landmark across accesses, so `cur is main_obj` and `cur is <chrome landmark>` both fail, defaulting chunks into the wrong scope. Net effect: on sites like bestmidi.com/bg/ the unscoped fallback runs and `main_nodes` ends up containing nav + footer too. The landing finders compensate (lowered hero threshold + doc-order-first NOTICE landing + tag-list filter + seen-heading gate) but a real fix would be to filter by textInfo position range instead of by parent-walk identity.
- `detection/web.py` — landing finders. **`find_article_landing` cascade** (in order, first match wins): (1) skip paragraphs below `LANDING_MIN_PARAGRAPH_CHARS=50`; (2) skip **tag-list-shaped paragraphs** detected via `_looks_like_tag_list` (no-space commas like "CoPilot,Microsoft 365,Microsoft Excel" — real prose uses commas WITH spaces); (3) **very substantial** paragraphs ≥`VERY_SUBSTANTIAL_PARAGRAPH_CHARS=200` win immediately on their own; (4) **cluster** (next paragraph also ≥50 chars) wins; (5) **hero shortcut** (≥`HERO_PATTERN_MIN_CHARS=100` + heading in lookahead) wins, but **only if we've already seen a heading in main_nodes** — pre-H1 substantial paragraphs are nearly always chrome (publisher disclaimers, deks, bylines); (6) **largest-paragraph fallback** picks the longest non-tag-list paragraph ≥50 chars. Each gate has a regression test in `tests/test_landing.py`. `find_list_landing` (first heading in largest same-level cluster). `find_notice_landing` (first paragraph ≥ `_NOTICE_LANDING_MIN_CHARS=30` in document order — deliberately NOT gated on "first heading first" because useful content often precedes any detected heading on small pages). `find_key_result_landing` (delegates to `classifier.find_key_result_pattern_index` to land on the LABEL so the user arrows forward to hear the value). `find_form_landing` (first heading — the form title — or first substantive paragraph as fallback; the caller in `__init__.py` then announces this via `ui.message` and uses `set_focus_on_first_form_input` to put keyboard focus on the box itself).
- `feedback.py` — three audio cues via `tones.beep`. `working()` = 500 Hz / 30 ms at detection start. `progress_start()` / `progress_stop()` = 400 Hz / 20 ms pulse every 500 ms while detection runs, on a `threading.Timer` background thread so beeps still play while the main NVDA thread is busy walking the tree. `not_found()` = **two** 220 Hz / 60 ms beeps with an 80 ms gap, played on a background thread so the sequence doesn't block NVDA — the two-tone rhythm is distinctive from working() (single short blip) and the progress pulse (single beep, repeated). Distinct pitches (500 / 400 / 220) so they're easy to tell apart by ear. No success tone — the spoken landing paragraph IS the success signal. **Override of original SPEC**: the SPEC said "failure is silent"; we play `not_found()` for genuine no-result outcomes after the retry attempt (the user asked for this), but still stay silent for SILENT_FOCUS_HONORED per guardrail #6.

Stubs / scaffolds (described in SPEC, not yet load-bearing):

- `trigger.py`, `context.py`, `detection/__init__.py`, `detection/email.py`, `detection/form.py`, `patterns.py`, `sequence.py` — stub files. When promoting any of these to real code, lift the relevant logic out of `__init__.py` and keep this list updated.
- `config.py` is load-bearing — backs the per-site exclusion list via NVDA's config system. Not a stub.
- No `settingsPanel.py`. The NVDA+Z gesture handles site exclusion directly; a settings panel would be redundant for v0.1.0. If genuinely useful settings emerge later (audio-feedback toggle is the most likely candidate), add it as a fresh `settingsPanel.py` then — `gui.SettingsPanel` is the right base class, and registration is `gui.NVDASettingsDialog.categoryClasses.append(...)` in `__init__` paired with a `.remove(...)` in `terminate()`.

`addon/doc/en/readme.md` is the user-facing doc shown in the NVDA Add-on Store. `manifest.ini` and `buildVars.py` are the add-on metadata and SCons build config.

## Diagnostic logs

Every call to `build_tree_summary` emits a `[TMTS perf]` line with per-phase timing and shape data. Format:

```
[TMTS perf] total=12787ms find_main=13ms counts+video=12446ms walk=327ms fallback=327ms (ran=False) raw_seen=72 fb_raw_seen=0 main_nodes=67 has_main=True article=68 forms=53 interactive=53 url='...'
```

`find_main` is the `<main>` landmark lookup. `counts+video` covers the seven `_iterNodesByType` enumerations (article, formField, button, link, edit, comboBox, checkBox, radioButton) plus video detection — historically the biggest cost driver on heavy pages because each item triggers a parent-chain `_in_scope` walk and the `id()`-keyed cache is silently useless when `obj.parent` returns fresh wrappers (see Known limitations). `walk` is the UNIT_PARAGRAPH walk. `fallback` is the unscoped re-walk, with `ran=` showing whether it actually executed. `raw_seen` / `fb_raw_seen` are the raw chunk counts for the scoped and fallback walks (the older `[TMTS walk-empty]` line still fires for empty walks but only carries raw_seen — the perf line subsumes it). On judysdogblog.wordpress.com the perf line revealed a 12.4s blocking freeze inside `counts+video` despite a 327ms walk on 72 paragraphs — instrumentation added 2026-05-26 to drive the next perf decision.

The perf line goes to two places:

- **NVDA's session log** (`%TEMP%\nvda.log`, viewable live via `NVDA+F1`). Rotates to `nvda-old.log` on NVDA restart, lost on the next restart after that.
- **Persistent perf log** (`%APPDATA%\nvda\textMarksTheSpot-perf.log`) — append-only, ISO-timestamped, survives NVDA and Windows restarts. Self-rotates at 1 MB to `textMarksTheSpot-perf.log.old` (one generation of history kept). Use this when collecting data across multiple sessions or asking a fresh AI session to analyze patterns. Write errors are swallowed silently so a locked or unwritable file can never break detection.

## Build and packaging

The project uses NV Access's official addon template structure. Build is done by **SCons**. The Python code under `addon/globalPlugins/textMarksTheSpot/` is the source of truth; edit there, rebuild the `.nvda-addon`, reinstall in NVDA.

**Archive layout (still important even with SCons):** the `.nvda-addon` zip must have `manifest.ini` at the root AND the *contents* of `addon/` at the root — NOT the `addon/` folder itself. So the zip looks like:

```
manifest.ini
globalPlugins/textMarksTheSpot/__init__.py
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

```
# Build the .nvda-addon
scons

# Clean build artifacts (addon/manifest.ini, addon/doc/en/readme.{md,html}, addon/doc/style.css, the .nvda-addon)
scons -c

# Update the .pot translation template (when source strings changed)
scons pot
```

Output: `textMarksTheSpot-<version>.nvda-addon` at the project root, named from `buildVars.py:addon_info["addon_version"]`.

**Note**: scons might fail to install in your default Python; if so, the `scons.exe` from `python -m pip install --user scons` lives in `C:\Users\<you>\AppData\Roaming\Python\Python313\Scripts\`. Make sure that directory is on PATH or call it by full path.

### Verify the build

```
Add-Type -AssemblyName System.IO.Compression.FileSystem
$z = [System.IO.Compression.ZipFile]::OpenRead("C:\OneDrive\Downloads\Text Marks the Spot\textMarksTheSpot-0.1.0.nvda-addon")
$z.Entries | ForEach-Object { $_.FullName } | Sort-Object
$z.Dispose()
```

Top-level entries should be `doc/...`, `globalPlugins/...`, `manifest.ini`. If you see `addon/...` anywhere, the build is broken.

### Other useful shortcuts

- `NVDA+Ctrl+F3` — reload all add-ons in the running NVDA.
- `NVDA+F1` — open the NVDA log viewer (where probes and the add-on log to).
- Installed-copy path (Windows, for reference): `%APPDATA%\nvda\addons\textMarksTheSpot\`.

### Tests

Pure-Python unit-test suite at `tests/` covering the classifier (`tests/test_classifier.py`) and landing finders (`tests/test_landing.py`). Run with `python -m pytest tests/` from the project root. Requires `pip install pytest` once (no NVDA needed — the classifier and landing finders are deliberately pure-function for exactly this reason).

The tests are regression guards: every bug fixed in this session got at least one fixture-based test pinning the correct behavior. When changing classifier thresholds or landing logic, run the tests FIRST. If a test fails after a "tuning" change, ask whether the test is still semantically correct before "fixing" it — most of them encode page-shape patterns that recurred during real debugging (bestmidi BAD walk, Google Forms closed, Calendar Google-Account-vs-appointment, fast.com KEY_RESULT, etc.).

NVDA-dependent code (tree_summary's walk, speech, tones, event hooks) is NOT unit-testable — that surface stays manual via the log viewer (`NVDA+F1`, search for `[TMTS]`). Each new NVDA API gets a 5–20 line standalone probe add-on before it appears in real code — see "API probes before real code" below and SPEC.md.

## API probes before real code

For each NVDA API the add-on uses for the first time, write a minimal standalone probe add-on, install it, observe in the NVDA log viewer, uninstall. Probes listed in SPEC.md §"API probes BEFORE committing real code": `event_treeInterceptor_gainFocus` firing behavior, `sayAll` / `SayAllHandler.readText` from an arbitrary position, settings-panel `categoryClasses` register/terminate cleanliness, `tones.beep` from inside a focus event. Each probe is 5–20 lines.

## Z behavior phasing

`Z` ships in stages. Don't implement the full per-page-type sequence in v0.1.0.

- Phase 1 (MVP): `Z` = re-run detection from current position. Single behavior, no sequence state.
- Phase 1.5: press counter + article sequence (next major section), `ui.message` announces what happened.
- Phase 2: form sequence (first error → next empty required → submit), Vision Enhancement Provider flash effect.
- Phase 3: email and search-result sequences, web-app/dashboard CTA detection.

`Z` never rebinds NVDA's built-in quick-nav keys (Tab, `h`, `f`, `t`, `k`, `b`, etc.). At end of a sequence, announce "No more next-likely actions on this page" — never wrap or guess. On an unidentified page, `Z` falls back to "re-run detection."

## Known limitations (deferred fixes)

These are not bugs — they're real architectural limitations we've reasoned about and chosen to defer. Future work should address them at the architectural level, NOT by adding per-site special cases.

- **In-scope filter is identity-based, not position-based.** `tree_summary._in_scope` walks `obj.parent` up looking for `cur is main_obj` or chrome-landmark identity. NVDA returns different `obj.parent` instances across accesses on some sites, so the identity check unreliably fails. On Calendar this manifests as: `raw_seen=51` chunks visited, but only ~8 make it into `main_nodes` because the parent walk can't confirm they're under `<main>`. The addon then lands on chrome text (e.g. "Google Account: Casey Mathews") instead of the appointment. **Real fix is positional:** capture `main_obj.makeTextInfo(POSITION_ALL)` once, compare each chunk's textInfo with `compareEndPoints("startToStart")` and `compareEndPoints("endToEnd")`. Positions are stable across accesses; identities aren't. Deferred because it's a 50–100 line refactor with risk that can't be unit-tested (textInfo APIs aren't available outside NVDA) — requires the build-install-test loop in real NVDA. ~Phase 2.
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
