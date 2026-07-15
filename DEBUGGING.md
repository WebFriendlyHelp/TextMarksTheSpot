# Debugging playbook — Text Marks the Spot

How to diagnose and fix a "landed wrong / didn't land" report. Written after
the 2026-07-06 soak-test day (four confirmed bugs, four general fixes) so any
AI session or human contributor can follow the same workflow. CLAUDE.md
covers the architecture; this file covers the PROCESS.

## The shape of every incident

Casey reports: "this URL should have landed on X, but did Y." The job is to
answer three questions IN ORDER:

1. What did the add-on actually see? (logs)
2. What is actually on the page? (independent verification)
3. Which rule produced the wrong pick, and what GENERAL rule fixes it?
   (fixture-first fix)

Do not skip to step 3. Two incidents today looked like landing-rule bugs and
were actually a walk bug — the paragraph the user wanted was never in the
add-on's data at all.

## Before you assume it's a landing bug: three failures that MASQUERADE as one

Added after 2026-07-14. All three look exactly like "the cascade picked the wrong
paragraph", and none of them are. Rule these out FIRST — each has a one-line check.

### A. It landed correctly and SPOKE something else (stale position)

The add-on captures a TextInfo per node during the walk and speaks it afterwards.
The walk takes 1.5-2 s, and a hydrating page rebuilds NVDA's buffer DURING that
window, so the captured offset now points somewhere else. **The classifier's choice
can be perfectly correct and the user still hears a sports headline, a photo credit,
or "We're loading your content, stay tuned!".** 7 of 42 landings in one soak.

It also causes SILENT landings: a stale position that expands to an empty range makes
`speakTextInfo` neither raise nor speak.

CHECK: `grep "TMTS stale-" nvda.log`. `stale-recovered` = drifted and re-anchored by
text (fine). `stale-landing` = drifted and could not recover (stayed quiet, correctly).

DO NOT "fix" this with the retry. The buffer drifts DURING the walk, so a re-walk
races the same way and lands stale again. Text is the stable anchor; the offset is not.

### B. The add-on never ran at all

Silence is not a landing bug. Historically the add-on ran on **9 of 31 page loads**
and did nothing on the rest — no tone, no landing, no sign it tried. Anything Casey
describes as "I had to refresh" or "Z worked but the page didn't" is this until proven
otherwise.

CHECK: count the trigger outcomes.

```powershell
Select-String "_maybe_fire_ti:" $env:TEMP
vda.log | Group-Object { $_.Line -replace '.*_maybe_fire_ti: ([a-zA-Z ]+).*','$1' } | Sort-Object Count -Descending
```

`PROCEEDING` = detection ran. Everything else is a skip, and a large skip count on
DIFFERENT urls is a trigger bug, not a landing bug.

### C. Your test harness broke, not the add-on

Two CDP-driven Chrome runs produced garbage and nearly bought a phantom "Chrome is
broken" diagnosis. Chrome focuses the ADDRESS BAR on a blank tab, so focus never
entered the document, NVDA never built a virtual buffer, and every page timed out the
readiness poll. Casey caught it BY EAR — he heard the omnibox being read aloud.

CHECK: if the NVDA log shows the address bar being spoken ("...selected",
"N suggestions available") instead of page content, focus is not in the document and
the run is worthless.

**Only real browsing is trustworthy for trigger measurements.** Automated navigation
(SendKeys, CDP) does not reliably reproduce real focus and document lifecycle. Ask
Casey to browse normally for two minutes; it is faster and it cannot lie.

### D. Automated sweeps (Start-Process per URL): what they can and cannot prove

The 2026-07-15 perf-hardening day ran sweeps by launching URLs with
`Start-Process firefox <url>` in a loop. Three rounds were silently void before the
rules below were learned. A sweep CAN validate detection timing, classification, and
landing choice on pages that fire. It CANNOT validate the trigger gates.

1. **The browser must be FOCUSED for the whole sweep.** NVDA only builds a browse
   buffer for the focused document. If Casey's focus is on the terminal reading
   output (the common case — the sweep is chatty), pages load, zero
   `documentLoadComplete` events reach the add-on, and the readiness poll gives up
   on any late unfocused one. The silence is indistinguishable from "add-on broken".
   Tell Casey to switch to the browser BEFORE starting, and verify the sweep worked
   by counting new perf-log lines, never by absence of errors.
2. **Play a heartbeat.** Casey asked for a beep every ~3 seconds so he knows the
   sweep is alive: `[console]::beep(750,120)` inside the wait loops, a few 600 Hz
   lead-in beeps before the first navigation, `[console]::beep(900,300)` at the end.
   Those pitches are deliberately distinct from the add-on's own tones (500/400/220).
3. **Give slow pages 30+ seconds each.** BibleGateway multi-chapter passages, the
   Hearthstone deckbuilder, and NLS BARD all need longer than 30 s to reach DOM
   load; navigate away sooner and their load event simply never fires — another
   false "did not run".
4. **A URL-list sweep never exercises the TI-reuse gates.** Cross-site navigation
   tears down the document and gets a fresh TreeInterceptor even in the same tab
   (`ti_changed=True` on every PROCEEDING line of the 2026-07-15 sweeps). The
   same-TI/URL-swap paths — where the 1.0.10 bug class lived — only run on
   same-SITE navigation and SPA route changes. For those, only Casey's real
   browsing counts (see the rule above this section).

## Step 1: Logs before theories

Two logs, different lifetimes:

- Persistent perf log: `%APPDATA%\nvda\TextMarksTheSpot-perf.log`.
  Append-only, ISO-timestamped, survives restarts, self-rotates at 1 MB.
  One line per detection: timing phases, `raw_seen` (chunks NVDA yielded),
  `main_nodes` (chunks kept), `scope=` (which scoping strategy ran),
  `article=/forms=/interactive=` counts, URL. Only written when NVDA's log
  level is DEBUG (Casey's normally is, during soak periods).
- Session log: `%TEMP%\nvda.log` (live view: NVDA+F1). Rotates to
  `nvda-old.log` on NVDA restart; one generation survives. This holds the
  DECISION TRAIL — read it soon after an incident or it's gone.

Search the session log for `TMTS` + the hostname. The lines that matter:

- `_maybe_fire_ti: PROCEEDING url=...` — detection ran. If instead you see
  a gate line (`same TI`, `cooldown`, `already landed ... suppressing`,
  `focus editable`, `caret mid-page on revisited/anchored url`), detection
  was deliberately skipped; decide whether the GATE is the bug (that was
  round 11: the mid-page gate misfired on a fresh load).
- `moved caret to idx=N kind=... intent=...(confidence)` — the landing,
  plus the evidence: `first_8` (first eight nodes), `substantial` (every
  paragraph >= 50 chars with index/length/preview), `headings` (all
  headings with index/level). This is usually enough to replay the landing
  cascade by hand.
- `[TMTS walk-drops] ...` — chunks the scope filter dropped after the
  scoped region started. Mid-region drops are anomalies. If a paragraph
  the user expected is absent from `first_8`/`substantial` AND absent
  here, NVDA's walk never yielded it (walk bug or exposure gap), not a
  filter bug.
- `Z scan-from-caret to idx=...` — what Z picked and from where.

Replaying the cascade by hand: with `substantial` + `headings` you can walk
`find_article_landing`'s gates (very-substantial >= 200 wins; cluster of two
>= 50s wins; hero >= 100 + heading in lookahead, only after a heading was
seen; prose-run; largest fallback + directory redirect). The landed idx tells
you which gate fired. If the landed idx makes no sense for ARTICLE, check the
intent — a heading landing usually means FORM (form-title path) or the
directory redirect (round 13: Armstrong was FORM off a newsletter widget).

## Step 2: Verify the page independently

NVDA's tree is not the page. Before designing a fix, establish what a
sighted user sees and in what order:

- Chrome extension (Casey's note: launch Chrome FIRST with
  `Start-Process chrome.exe`, then the browser tools connect). Inspect the
  DOM around the expected landing text: is it a real `<p>`? What precedes
  it (images, link blocks)? Is it inside `<main>`/`<article>`?
- Site down or blocking? Wayback Machine
  (`https://web.archive.org/web/2026/<url>`) — that's how pattysworlds was
  diagnosed while the live site refused connections.
- The walk data is ground truth for what the ADD-ON can act on. Text the
  user "heard" may have come from the window title (the X page headline),
  not from any walkable paragraph. If the expected text is not in the
  buffer, no landing rule can reach it — the fix (if any) is at the walk
  layer, or it's an exposure limitation to document honestly.

## Step 3: Fixture-first general fix

- No per-site code, ever. Casey's standing rule. Every fix must be a
  general shape: "runs of short sentence-ending lines are prose" (X),
  "ALL-CAPS READ MORE labels are promos" (Daily Mail), "two adjacent
  200-char paragraphs prove an article" (Armstrong).
- Before changing code, turn the log's node list into a fixture test in
  `tests/test_landing.py` / `tests/test_classifier.py` that reproduces the
  BAD landing (they're pure-Python; `python -m pytest tests/`). The log's
  `first_8`/`substantial`/`headings` fields give you lengths and previews
  verbatim.
- Then design the rule against the standing hazard fixtures. Every
  candidate heuristic today was nearly defeated by an existing page shape:
  the prose-run rule by Montgomery's nav rows and Zoom's form labels, the
  massive-duo rule by Zoom's rich description (saved by the /register URL
  escape hatch). Run the FULL suite; if an old test fails, assume the old
  test is right until proven otherwise.
- Prefer discriminators that separate content from furniture by how
  LANGUAGE behaves, not by length alone: sentence-ending punctuation
  density, ALL-CAPS labels, uppercase ratio after "By", commas without
  spaces. Length-only rules get defeated by nav menus and label runs.
- 60-char preview trap: any signal at the END of a line (terminal
  punctuation, trailing photo credits, "All rights reserved") must be
  computed at walk time over the full text and stored as a MainNode flag
  (`is_caption`, `is_boilerplate`, `ends_sentence`). Preview-only checks
  silently fail on lines over 60 chars.
- Locked decisions are not up for renegotiation while fixing: the add-on
  binds Z and nothing else; alt-tab/tab-switch stays quiet (do NOT hook
  event_gainFocus); register/signup URLs keep FORM behavior; wrong
  auto-jump is worse than no jump (when in doubt, return None and let the
  1500 ms retry or the not-found tone handle it).

## Step 4: Build, install, verify it's really installed

```
& "$env:APPDATA\Python\Python313\Scripts\scons.exe"
Move-Item -Force TextMarksTheSpot-<ver>.nvda-addon TextMarksTheSpot.nvda-addon
Start-Process .\TextMarksTheSpot.nvda-addon   # opens NVDA's install prompt
```

- Keep ONE unversioned `TextMarksTheSpot.nvda-addon` locally; delete
  versioned copies.
- The install only takes effect after NVDA restarts (Casey usually
  restarts himself; `& "C:\Program Files\NVDA\nvda.exe" -r` restarts it on
  request).
- STALE BUILD CHECK before diagnosing a "fix didn't work": grep the
  installed copy (`%APPDATA%\nvda\addons\TextMarksTheSpot\`) for a marker
  string from the new code, and check for a `pendingInstall` directory.
  Two diagnoses were nearly wasted on builds sitting unaccepted in the
  prompt.
- NVDA-dependent code (the walk, events, speech) is not unit-testable.
  A walk-layer change ships as a hypothesis: say so plainly, name the
  page that will confirm or refute it, and make sure a diagnostic log
  line will disambiguate if the hypothesis is wrong (round 14's
  walk-drops line).

## Release discipline

During a soak: every fix stays LOCAL and UNCOMMITTED on the same version
number. No commits, no tags, no version bumps per fix. Update
`changelog.md` AND `buildVars.py:addon_changelog` (the store "What's new")
as you go — they drift apart otherwise. When Casey declares the soak done:
commit everything, tag `vX.Y.Z` matching `addon_version`, push main then
the tag, and let CI publish. NEVER run `gh release create` (it collides
with CI). Store submissions: the stable channel rejects `lastTested` ahead
of NVDA's stable GA.

## Communication (Casey)

- Casey is blind and uses NVDA full-time. Never suggest "test it with a
  screen reader." State WHAT to check: "pattysworlds.com should now land
  on the Watch-your-step paragraph."
- No Markdown tables, no emoji, no box-drawing glyphs, no em dashes in
  chat prose, numbered lists for sequences.
- Lead with what happened and whether it's fixed; keep the mechanism
  explanation short and in plain sentences.
- Be honest about limits: if the expected text is not in NVDA's buffer,
  say the desired landing is unreachable and name the best achievable one.
- Open things for him (install prompts, pages) with `Start-Process`
  instead of telling him to.
