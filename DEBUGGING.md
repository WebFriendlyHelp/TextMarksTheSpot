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

**Step 0, before improving any mechanism: has it ever fired?** (added
2026-07-19.) A refinement to the depleted-scope net was designed, reviewed by
two independent reviewers, and nearly built — before anyone asked how often the
net had run. The answer was ZERO times in 245 page loads, and on the page it was
built for it could not fire at all. Both reviewers missed it because both were
reasoning inside the premise they were handed; that is what reviewers do.

The count is usually one command against the persistent log:

```powershell
$p = "$env:APPDATA\nvda\TextMarksTheSpot-perf.log"
(Get-Content $p | Where-Object { $_ -match 'unscoped-depleted' }).Count
```

A safety net that has never fired is indistinguishable from one that cannot.
This is the same discipline as "when a check comes back unanimous, ask whether
it could ever have come back the other way", aimed at a mechanism instead of a
probe. And check the WIRING has a test, not just the predicate: on this branch,
five separate times, a rule was unit-tested while the code feeding it could be
deleted with the suite still green.

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
Select-String "_maybeFireTi:" $env:TEMP
vda.log | Group-Object { $_.Line -replace '.*_maybeFireTi: ([a-zA-Z ]+).*','$1' } | Sort-Object Count -Descending
```

`PROCEEDING` = detection ran. Everything else is a skip, and a large skip count on
DIFFERENT urls is a trigger bug, not a landing bug.

### B2. A second browser on the SAME URL is suppressed, and looks broken

Added 2026-07-19 after Edge appeared to fail while Firefox and Chrome worked.

`_LANDED_SUPPRESS_SEC` is 120 seconds and is keyed on the **URL alone**, not on
URL-plus-browser. So a landing in one browser suppresses the identical URL in
the next one. Testing the same page across browsers inside two minutes is VOID,
and the only thing that says so is the decision trace:

```
[TMTS] _maybeFireTi: already landed on url='...' 22.4s ago — suppressing re-detection
```

Vary the URL per browser, or wait two minutes. And note the two OTHER ways a
browser can silently do nothing, which look identical from outside:

- `readiness poll: still not ready after 12 attempts — giving up` (the buffer
  never built inside 3 s; Edge did this on a cold load)
- `readiness poll: not a web document (scheme) — abandon`

Three different causes, one symptom. Read the trace before concluding anything
about a browser.

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
5. **PROGRAMMATIC focus is NOT focus. An unattended sweep cannot work at all.**
   This is stronger than rule 1 and was learned the hard way on 2026-07-18: two
   more sweeps (38 URLs, then 32) were run while Casey was away, the second one
   explicitly forcing the window forward with `AppActivate` +
   `SetForegroundWindow` + `SW_RESTORE`, asserting the foreground window title
   really was "Mozilla Firefox" before dwelling, and re-asserting it mid-dwell.
   Every check passed (`focus=True` on all 32) and **every single page was still
   void — fired=0, void=32.** The session log shows why, identically on every
   page: `[TMTS event] documentLoadComplete` arrives, then
   `ti not ready — readiness poll attempt 1..12/12`, then `giving up`. NVDA
   never built the browse buffer.
   Raising a window with the Win32 foreground APIs is not the same thing as
   NVDA's focus object moving into the document. NVDA only builds a
   TreeInterceptor in its pre-step when the loaded object is the focus or a
   focus ancestor (`eventHandler.py:431-432`), and that requires a real focus
   event, not a window that merely sits in front.
   **Do not try to fix this with more focus trickery, and do not send synthetic
   keystrokes at an unattended machine.** The conclusion is simply that a
   scripted sweep is only valid with Casey present and actually at the browser.
   And usually it is not needed: any PASSIVE diagnostic (a perf field, a probe
   line) collects itself from his ordinary browsing, which is better evidence
   anyway — real pages, real timing, real TI reuse. Prefer "ship the diagnostic
   and wait a day" over "script 30 loads and wait 20 minutes for nothing."
   **Verify by counting, always.** The v2 sweep logged an `OK`/`VOID` delta of
   perf-log lines per page and so reported its own failure on page 1. The v1
   sweep did not, and looked fine for 21 minutes while producing nothing. Any
   future sweep must count new perf-log lines per page and stop early when the
   first few come back void.

### E. A DIRECT `Start-Process <url>` sweep DOES work — the hidden child was the bug (2026-07-21)

The rule above (D5: "an unattended sweep cannot work") is now qualified, not
overturned. What actually fails is a sweep run from a HIDDEN BACKGROUND process
or via Win32 window-forcing — Windows won't let a background process take the
foreground, so the browser never really comes forward and NVDA never builds the
buffer. But opening a URL DIRECTLY from the main automation context —
`Start-Process "<url>"` (the shell-open form, NOT `Start-Process firefox <url>`
from a `-WindowStyle Hidden` child) — brings Firefox forward with a genuine
focus change, and the add-on fires. Confirmed 2026-07-21: three sweeps from a
hidden `pwsh` child were 0/N void; the SAME URLs opened directly, one
`Start-Process` per page, fired 10 of 12, then 4 of the remaining 6 on a retry.

The conditions that make it reliable:
1. **Open directly, not from a hidden child.** `Start-Process "<url>"` from the
   tool call itself. A hidden background launcher cannot set foreground.
2. **Use the shell-open form `Start-Process "<url>"`**, which hands the URL to
   the default browser, exactly like opening a link for Casey. `Start-Process
   firefox <url>` behaved differently in testing.
3. **Casey's Firefox is single-tab** (every link loads in the one tab in place),
   so focus stays in that document across navigations. And opening a link
   switches focus INTO Firefox even from the terminal (Casey confirmed).
4. **Casey must not touch the machine during the run** — typing in the terminal
   pulls focus back and voids the rest. Him being away (e.g. on his phone) is the
   cleanest condition of all.
5. **Adaptive dwell, not fixed.** Poll the perf-log line count every ~2 s and
   advance the instant it increments; give a slow page up to ~40 s. A fixed 20 s
   dwell voided pages that actually fire in 2 s once Firefox is foreground — the
   next `Start-Process` was interrupting a still-settling page.
6. **Still verify by counting** (D5) and expect ~revisit-suppressed pages to
   read void (a page landed earlier this session won't re-fire — that's the gate,
   not a failure).

Pair this with the capture log + `tests/replay_captures.py`: a direct sweep banks
faithful `captures.jsonl` records, and the replay reproduces every landing
offline. That is how the 2026-07-21 corpus was built, and how the XDA author-bio
mislanding was found without touching NVDA.

### F. A shell-open sweep drops every OTHER launch. Relaunch at 12 s (2026-09-10)

Running the section E sweep across 40 URLs produced a perfect OK/VOID
alternation, twice, 26 pages in a row. The void pages were not a focus problem
and not a counting problem: the session log carried NO `documentLoadComplete`
for them at all, so Firefox never navigated. A launch appears to take only when
Firefox has been idle for a while, and the successful launches were exactly the
ones following a 30 s void slot. A post-fire settle of 8 s did NOT help, which
rules out "the previous page was still being spoken".

The fix costs nothing, because the wasted slot was already being spent waiting:
launch, poll, and if nothing has fired by 12 s, `Start-Process` the SAME url a
second time. That took the next 27 pages to 27 OK and 0 void, including all 13
that had been voided earlier.

So: **judge a sweep by its OK count, never by the URL count, and never conclude
"the add-on ignored that page" from a void without checking the session log for
a `documentLoadComplete` first.** Half a sweep silently failing at the browser
looks identical to half a sweep being suppressed by the add-on's own gates.

### G. What is actually above `<main>` on real sites (2026-09-10)

Measured, because a rule was proposed on the strength of ONE page. 40 URLs
swept, 35 usable captures, recording the nodes the walk built and then dropped
for sitting above the main landmark.

Substantial sentence-ending prose above `<main>`: 3 of 35 pages, and all three
are cookie consent (arstechnica, gov.uk, elpais). Widening to any substantial
paragraph: 6 of 35, adding Guardian and Spiegel headline teasers, a W3C skip-link
and tagline block, and Tom's Hardware subscription marketing. Real content above
`<main>`: zero of 35.

So the pre-main region is chrome, essentially always, and the scoping that drops
it is right. Google's AI Overview is a genuine outlier at 1 of 36. **Any rule
permissive enough to admit it also lands on a cookie banner or a headline rail**,
and the obvious safeguards do not save it: gov.uk's consent text is preceded by
a heading, and the Guardian has FOUR substantial paragraphs and five headings up
there, so neither "has a heading before it" nor "is a multi-paragraph block"
separates the outlier from the chrome. Do not reopen this without new evidence,
and if it is reopened, the bar is a rule that fires on Google and on none of the
six pages named above.

### H. The gensix nav landing: investigated, no shippable rule (2026-09-10)

gensix.com/access-message lands on an H1 reading "MAIN NAVIGATION". The cause is
plain: the page carries six H1 headings in its footer sitemap (MAIN NAVIGATION,
SQ PRIVATE BRIEFINGS, PREVIOUS CONFERENCES, GENSIX FILMS, OTHER LINKS, MY
ACCOUNT), that run is the largest same-level heading cluster on the page,
`_largestHeadingCluster` classifies it LIST, and `findListLanding` lands on the
cluster's first member. The right landing is the H2 "LOOKING FOR ACCESS?" at
node 10, with its 111-character explanation at node 11.

Three candidate rules were measured against 385 unique captured pages and all
three failed:

1. **Distrust a level-1 heading run.** Level-1 clusters of 5 or more occur on
   exactly ONE site in the corpus, gensix itself. N=1 on the positive side is
   tailoring, by the same standard applied in section G.
2. **Require substantial text inside the cluster span.** The clusters with NO
   substantial paragraph between members include the Guardian's 10-headline
   rail and RTE's 5-headline rail, which are real content. The rule would
   silence two front pages to fix one login page.
3. **Prefer the earliest cluster over the largest.** Only 10 LIST landings
   exist in the whole corpus, so there is not enough evidence to re-order the
   rule without guessing.

The upstream problem is arguably that this page is not a list at all; it is a
login notice that happens to have a footer sitemap. Left alone deliberately.
Anyone reopening this needs a rule that fixes gensix AND leaves the Guardian and
RTE rails landing where they do now.

**BOTH persistent logs are OFF unless you turn them on, and neither leaves the
machine it was written on.** The capture log records the FULL url of every page
detected, query string and all, plus previews of the page text. The perf log
carries that same url on every line and outlives NVDA restarts, so it accrues
for months. One real day of them collected an invoice link, OAuth authorization
codes, and an app path carrying a client secret. Both write only when this
marker file exists, and the check is cached at startup:

```powershell
New-Item -ItemType File "$env:APPDATA\nvda\TextMarksTheSpot-diagnostics-enabled"
# restart NVDA, then browse
```

Delete the marker and restart NVDA to stop. They were previously gated on NVDA's
DEBUG log level, which was wrong: people run DEBUG for unrelated reasons and
would never guess a screen-reader add-on had started recording where they go.

Consequence to plan around: **asking a user for a perf log is now a two-step
request** (create the marker, restart, reproduce). Say so up front, and tell them
what the file contains and how to delete it, rather than having them discover a
month-long list of their own browsing afterwards. The `[TMTS perf]` line still
goes to NVDA's own session log unconditionally, which is enough for a live
NVDA+F1 diagnosis and is wiped on the second restart.

The corpus that `tests/test_replay_corpus.py` replays lives at
`tests/fixtures/local/capture_corpus.jsonl` and is **gitignored on purpose**. Do
not commit it, do not paste the raw log into an issue, and do not bulk-copy it
into the repo. Add cases by hand from public pages worth pinning. Without the
file the test skips, so a fresh clone still runs green.

## Step 1: Logs before theories

Two logs, different lifetimes:

- Persistent perf log: `%APPDATA%\nvda\TextMarksTheSpot-perf.log`.
  Append-only, ISO-timestamped, survives restarts, self-rotates at 1 MB.
  One line per detection: timing phases, `rawSeen` (chunks NVDA yielded),
  `mainNodes` (chunks kept), `scope=` (which scoping strategy ran),
  `article=/forms=/interactive=` counts, URL. Only written when NVDA's log
  level is DEBUG (Casey's normally is, during soak periods).
- Session log: `%TEMP%\nvda.log` (live view: NVDA+F1). Rotates to
  `nvda-old.log` on NVDA restart; one generation survives. This holds the
  DECISION TRAIL — read it soon after an incident or it's gone.

Search the session log for `TMTS` + the hostname. The lines that matter:

- `_maybeFireTi: PROCEEDING url=...` — detection ran. If instead you see
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
`findArticleLanding`'s gates (very-substantial >= 200 wins; cluster of two
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
  (`isCaption`, `isBoilerplate`, `endsSentence`). Preview-only checks
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
