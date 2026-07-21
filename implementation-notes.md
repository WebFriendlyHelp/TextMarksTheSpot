# Implementation notes

Newest entries at the top.

## 2026-07-21 - newsletter-signup CTA filter (verified via the full NVDA loop)

342 tests + 1 xfail. Casey's rule: a newsletter box is never what you came to
read. Added an explicit newsletter-signup family to the disclosure detector
(`_NEWSLETTER_PROMO`: "to your inbox", "sign up for our newsletter", etc. -
near-mandated phrasing, NOT the bare word "newsletter"). Computed at walk time
via the existing `is_disclosure` flag because the giveaway ("to your inbox")
sits past the 60-char preview.

**First fix verified end-to-end with the autonomous NVDA loop** (Casey authorized
restart, 2026-07-21): edit source -> full suite green -> copy web.py into the
installed add-on (`%APPDATA%\nvda\addons\...`, back up first) -> `nvda.exe -r`
-> confirm the add-on loaded (`Z binding registered`, no import error) -> open
the real page -> read the fresh capture. Confirmed: Tom's Hardware's "Get Tom's
Hardware's best news and in-depth reviews, straight to your inbox" (idx 46, the
"to your inbox" past the preview) now carries `is_disclosure=True`. RedState
still lands on its lede (no regression). This loop is the way to verify any
walk-time flag without waiting for a manual install.

**Tom's Hardware itself is NOT fixed and that's the right call.** It is a
HOMEPAGE stacked with grammatical chrome; skipping the newsletter just exposed
the next chrome line ("Tom's Hardware is part of Future US Inc..."), and below
that sit team-bio taglines. Whack-a-mole. The real fix is homepage/LIST
handling: a page whose content is a wall of non-sentence headlines should land
on the first headline (the unrestricted cascade already does this - idx 9 - it's
the sentence-strict pass "trusting" grammatical chrome that overrides it). That
is a deferred design item, tracked with the other replay findings below.

## 2026-07-21 - direct-Start-Process sweep works; capture/replay corpus; XDA bio found + deferred

341 tests + 1 xfail. `main` still v1.0.13.

### The scripted sweep works after all (see DEBUGGING.md E)

Every prior sweep attempt voided because it ran from a HIDDEN background pwsh
(can't take foreground) or used Win32 window-forcing (not a real focus event).
Opening a URL DIRECTLY from the tool call - `Start-Process "<url>"`, the
shell-open form - brings Firefox forward with a genuine focus change and the
add-on fires. Three hidden-child sweeps were 0/N; the same URLs opened directly
fired 10/12 then 4/6 on retry. Keys: direct open (not hidden child), the
`Start-Process "<url>"` shell form (not `Start-Process firefox <url>`), Casey's
single-tab Firefox, Casey away from the machine (phone), and ADAPTIVE dwell
(advance when the perf-log count ticks, up to ~40 s) - a fixed 20 s dwell voided
pages that actually fire in 2 s because the next open interrupted a settling
page. Revisit-suppressed pages correctly read void.

### Capture + replay corpus (the durable payoff)

`_append_capture` (added earlier today) banks one faithful JSON record per
detection. A direct sweep fills it fast; `tests/replay_captures.py` reproduces
every landing offline; `tests/test_replay_corpus.py` +
`tests/fixtures/capture_corpus.jsonl` freeze 10 real pages as a regression guard
(9 verified-correct landings locked, XDA xfail). This is the "automated tests
from real sites" Casey asked for, and it needs NO NVDA driving (which per
DEBUGGING.md D5 is impossible headlessly regardless).

### Bugs the replay surfaced

- **XDA author-bio (xfail'd, fix DEFERRED).** reboot-your-router landed idx 5 on
  "After a 7-year corporate stint, Tanveer found his love for writing..." (337
  chars) - it wins the very-substantial (>=200) gate before the real body at idx
  9. Not fixed autonomously: the giveaway ("writing"/"writer") sits past the
  60-char preview (needs a walk-time flag), and the tempting byline-name-echo
  detector ("bio repeats the author's name") risks common-word names ("By Mark
  Smith" + a lede "Mark my words..."). Needs a curated bio-phrase vocabulary and
  NVDA verification against a broad page set. The xfail flips to a failure the
  day it lands right, which is the reminder to drop it.
- **Homepage / promo landings (noted, not bugs per se).** Tom's Hardware landed
  on a newsletter-signup blurb (idx 57); lite.cnn (idx 54) and text.npr (idx 19)
  landed deep on news homepages. These are the open-vocabulary promo and the
  "where should a homepage even land" questions the disclosure detector already
  declines to touch. Deferred as a design question (homepages arguably want LIST
  intent / first-headline), not a quick fix.

## 2026-07-21 - positional chrome-pos counting: SHELVED after two reviews; auto-capture + replay harness added

332 tests. `main` still v1.0.13. Net add-on change today: an auto-capture debug
log + a replay harness. The counts optimization was written, reviewed, and
REVERTED. Shelved patch: scratch `counts_positional_SHELVED.patch`.

### The counts burn, and why the fix was shelved

The `[TMTS counts-phase]` instrumentation (shipped earlier today) showed the
~600 ms no-`<main>` counts burn is per-ITEM parent-chain COM cost, not scan
volume: e.g. abc7ny 8 links / 677 ms (~85 ms each), DuckDuckGo 4 articles /
424 ms. On no-`<main>` pages the counts use identity `_count_in_scope`, which
walks each item's parent chain to the document root.

The fix attempted: `_count_chrome_pos`, reusing `_chrome_pos_verdict` (the same
positional verdict the walk and `_form_field_in_scope` already use) so the common
case is offset arithmetic, falling back to identity only on a None verdict. It
was pitched as "same result, just faster." TWO independent reviews (Sol/Codex
read-only on the diff; Fable reading the full repo) each found a real,
FORM-flipping OVER-count, in the guardrail-violating direction, and Fable found
the framing itself was wrong. Do NOT rebuild it without addressing all of this:

1. **Shared-cache divergence (Sol).** Old `_count_in_scope` calls `_in_scope`
   for EVERY item, and each parent walk POPULATES the shared cache with its
   ancestors' verdicts, so later controls sharing a nav ancestor short-circuit
   to chrome. The positional path decides items WITHOUT walking, so it never
   primes that cache. A deep control that then falls to identity exhausts the
   30-parent depth limit before reaching the nav ancestor and — because
   `_in_scope` fails OPEN (undecided -> True on a no-`<main>` page) — is counted
   as content. Reproduced in memory: old form count 0, new 3 -> UNKNOWN flips to
   FORM. Preserving the old result requires priming the cache, i.e. the walk,
   i.e. the cost we were removing.

2. **Objectless-item over-count (Fable).** On the decided (True/False) path
   `_count_chrome_pos` never consults `obj`; old code skipped every `obj is
   None` item. `VirtualBufferQuickNavItem.obj` is a COM resolution that FAILS
   mid-hydration — which is exactly when `documentLoadComplete` fires — while
   `textInfo` is offset arithmetic and nearly always present. So a hydrating SPA
   with 4 obj=None edits (valid textInfo, verdict True) counts 4 -> FORM, where
   old counted 0. My docstring even claimed "fails OPEN, objectless item
   counted" while the None+obj=None branch does the opposite: doc and code
   disagreed on the highest-stakes counter, untested.

3. **It is NOT a perf no-op (Fable, the reframe).** The whole reason identity is
   slow on these pages is that it walks to root and fails OPEN, counting nav and
   banner controls as content. The positional verdict correctly EXCLUDES them —
   so counts genuinely DROP on the burn pages, with NO truncated flag, so the
   small-count-intent protections (NOTICE/KEY_RESULT) do not engage. That may be
   MORE correct (it closes the "counts still identity while walk is positional"
   divergence CLAUDE.md flags), but it is a deliberate BEHAVIOR change needing
   its own soak and truncation-flag handling, not a quiet optimization.

4. Under-tested: deleting the `_count_form_inputs` chrome-pos branch left the
   suite green (no test, no `sabotage_check.py` entry) — the exact hazard this
   branch has hit repeatedly.

Decision (Casey's "integrate if safe"): NOT safe -> reverted. The burn is a
documented, accepted, NON-user-facing cost; the fix's failure mode is a FORM
misfire (focus move / false form-title announcement), which the guardrails
rank worse. If revisited, treat it as an intentional accuracy change: fail
CLOSED on undecidable items with per-count-type truncation flags (article-count
0 is NOT fail-safe), pin the objectless and shared-cache cases, and soak it.

### Auto-capture + replay harness (kept)

To build a faithful, NVDA-free regression corpus from real browsing: `_append_capture`
writes one JSON record per detection to `%APPDATA%\nvda\TextMarksTheSpot-captures.jsonl`
(DEBUG-gated, 2 MB self-rotation, errors swallowed — same discipline as the perf
log). It records every field the classifier and landing finders READ (kind,
level, length, 60-char preview, the four walk-time flags). Those finders never
see more than that, so `tests/replay_captures.py` reconstructs the MainNode list
and reproduces the add-on's intent + landing EXACTLY, offline. This is why
driving NVDA headlessly is unnecessary here (and per DEBUGGING.md D5, impossible
anyway — NVDA only builds a buffer for the truly-focused document). Casey browses
normally; the corpus fills itself; verified rows become assertions.

## 2026-07-21 - Gateway Pundit landed on a dated byline

332 tests. `main` still v1.0.13. One more chrome shape, not a per-CMS branch.

thegatewaypundit.com landed idx 1 on "By Jenn Baker Jul. 20, 2026 7:40 pm"
(with the article slug concatenated onto the end), the first substantial
paragraph; the real lede ("The Orange traffic barrel on the side of Arizona
State Route 60...") sat at idx 9. This is the mixed-case "By Name" byline the
all-caps rule deliberately skips (indistinguishable from "By Tuesday, the storm
had..." on its own).

The publication DATE is the extra signal that makes it safe. Added a dated-byline
form to `_looks_like_byline`: "By " + capitalized non-weekday name + a full
Month-DD-YYYY date, capped at 120 chars. Three guards keep it off real "By"
ledes, each pinned by a test: a bare year with no day ("By January 2026, sales
rose") lacks the date; a weekday opener ("By Monday, June 5, 2026, the crews...")
is temporal prose; "By NASA's estimate..." carries no date. Preview-based (the
date sits in the first ~27 chars, well inside the 60-char preview).

CMS note (Casey asked): we deliberately do NOT detect WordPress/Drupal/etc. The
add-on sees NVDA's accessibility tree, not HTML source, so the generator tag /
wp-content paths / script URLs that identify a CMS are invisible to it - and the
platform wouldn't tell us where the lede is anyway (RedState, Gateway Pundit,
armstrong are all probably WordPress with different layouts). The right lever is
the recurring STRUCTURAL furniture those CMSes render - byline blocks, share
rows, disclaimers, breadcrumbs, promo teasers - keyed on the rendered shape,
which is CMS-agnostic and also catches hand-built sites. The chrome-shape library
IS the "common CMS elements" approach; this dated byline is one more entry.

## 2026-07-20 - RedState landed on the publisher opinion-disclaimer

330 tests. `main` still v1.0.13. One-line general fix to the disclosure detector.

Three RedState articles (F-16s, State Dept, Iran), all `article(0.90)`, all
landed idx 3 on "The opinions expressed by contributors are their own and do
not necessarily represent the views of RedState.com." (112 chars). The real
lede sits at idx 6 (233 / 356 / 218 chars, all very-substantial >=200). Page
shape: H1, author slug, byline, THIS disclaimer, a `?subject=...` share-link
payload, a photo credit, then the lede.

It is the documented `_looks_like_editorial_disclosure` blind spot - boilerplate
that reads as a grammatical sentence, so the sentence-strict pass cannot see it
and it clustered with the share payload to win idx 3. The existing detector
covered affiliate / syndication / marketing-consent families but not the
publisher opinion-disclaimer, which is just as standardized on opinion/news
sites.

Added a `_DISCLOSURE_OPINION` x `_DISCLOSURE_NOT_NECESSARILY` conjunction (an
"opinions/views expressed" phrase AND a "not necessarily reflect/represent/those
of" phrase). Same discipline as the publishing family: neither half is safe
alone ("the opinions expressed at the meeting were heated" is prose; "these
results do not necessarily represent the population" is prose), but together
they essentially only occur in this disclaimer. The "not necessarily..." half
sits past the 60-char preview (char ~62 here), so it relies on the walk-time
`is_disclosure` flag over full text, which is already how tree_summary computes
it. Once flagged chrome, the cascade reaches the very-substantial lede at idx 6.

Sabotage-checked: rule off -> chrome=False -> lands idx 3 (the bug); rule on ->
idx 6. Landing test passes the FULL disclaimer as the preview so it exercises
the detector, not a hardcoded flag, and fails before the rule exists.

## 2026-07-20 - counts-phase instrumentation (measure before touching the burn)

328 tests. `main` still v1.0.13. Passive measurement only, no behavior change.

Today's soak log showed every no-`<main>` page (stevequayle, armstrong,
alexjones, kyivpost, thurrott, two Square invoice pages, three glidance.webflow
pages) spending ~600-730 ms in the COUNTS phase and coming back
`counts_trunc=True`. That is the documented identity-counting cost, now the
dominant remaining cost on that page shape since the field-stack walk rework
dropped walks to ~100 ms. Before anyone designs or reviews a fix, the counts
phase needs the same per-call-site measurement the walk already has
(`[TMTS walk-phase]`) - the `counts=Nms` field is a single number and cannot say
WHICH enumeration or WHY. Reviewing a fix without it would repeat the
payproglobal mistake (two reviewers declined to approve until the walk-phase
line existed) and the hollow-probe mistake.

New `[TMTS counts-phase]` line: per-call-site wall-clock and items-scanned for
`article`, `single_article`, `forms`, and each interactive type
(`iv:link` ... `iv:radioButton`). Wall-clock localizes the burn to one
enumeration; items-scanned times the already-known mode (`scope=` on the perf
line says identity vs positional) separates "300 items each paying a
parent-chain walk" from "the COM iterator itself is slow". Persistent log when
the phase is slow (>= 0.3 s, below the walk's 1.0 s on purpose - the burn is
~0.6 s) or truncated; session log always; emitted adjacent to the `[TMTS perf]`
line, same as walk-phase.

Mechanics: added an optional `scanned_out` list to `_count_in_scope` /
`_count_in_range` (live-incremented so every early return reports true scanned)
and threaded it through `_count_form_inputs`. Zero behavioral change - the leaf
count loops and their check-placement contract (`tests/test_count_budgets.py`)
are untouched; five new tests pin that `scanned_out` reports correctly on every
exit path (full scan, limit short-circuit, scan cap, multi-type accumulation)
and never alters the count or the truncated flag. The primary counts phase is
instrumented; the rare/cheap fallback recount (t3->t4) is deliberately not
folded in so attribution stays clean.

This is a "ship the diagnostic and wait a day" step (DEBUGGING.md): the fix
itself - positional counting on chrome/no-`<main>` pages - waits on the data,
and a Sol/Fable review is worth its cost only once there are real per-call-site
numbers to attack.

## 2026-07-20 - the WebAIM survey: a form that read as an article, and a thank-you that read as nav

323 tests. `main` still v1.0.13. Two independent fixes from one soak report,
both general, both fixture-pinned and sabotage-checked.

Casey ran the WebAIM Screen Reader User Survey #11 end to end and hit two
mislandings on consecutive pages. Both traced cleanly from the logs; neither was
a walk bug or a stale position (the moved-caret lines carried the full node
lists, and the classifier inputs were exactly what the perf lines reported).

### 1. The questions page landed mid-form (Q13) instead of at the top

`/screenreadersurvey11/survey`: `article=1`, `forms=10`. Classified
`article(0.75)` and `find_article_landing`'s largest-paragraph fallback picked
idx 42, "13. Do you see free or low-cost desktop screen readers..." (166 chars)
- the LONGEST single question label on the page. Every question is separated by
its short answer options ("Yes", "No Response", 3-11 chars), so no cluster and
no hero gate ever fires on the questions; the cascade falls straight through to
"pick the longest paragraph", and Q13 happened to be longest.

Root cause is classification, not landing: WebAIM wraps the survey body in a
single `<article>`. `has_editorial_content = article_count >= 1` tripped, and
with no form-URL hint the `(has_editorial_content and not form_url_hint)` clause
blocked FORM. So a 10-input survey classified as an article.

Fix: a survey / questionnaire URL is a form URL, exactly like /register and
/contact already are. Added `/survey`, `/questionnaire` to `URL_HINTS[FORM]`.
That flips the existing escape hatch, FORM fires at 0.99, and the bare-form path
announces the title and moves focus to Q1. Deliberately did NOT touch the
`<article>` FORM block or let `strong_form_signal` bypass it - that block is a
documented deliberate decision protecting news articles with comment forms, and
those articles are also caught by `has_body_cluster_strong` (no URL hatch), so a
real "/surveying-services" article with a body cluster still blocks FORM. Pinned
that collision with `test_surveying_article_with_body_cluster_stays_editorial`.
`/poll` was NOT added: plain substring matching would eat "/pollution".

### 2. The thank-you page landed on the breadcrumb, then would have landed on a share prompt

`/survey_confirm`: classified `notice(0.85)` correctly, but landed idx 2, the
breadcrumb "Home > WebAIM Projects > Screen Reader User Survey" - the first 30+
char paragraph in document order. The page's actual status is in its headings
(H1 "Screen Reader User Survey Completed", H2 "Thank you for completing our
screen reader user survey"); the paragraphs below are follow-up prompts ("share
this with others", "check out our services").

Two things were wrong, both needed:

  a. The breadcrumb is nav chrome and was not filtered. Added
     `_looks_like_breadcrumb` to the shared `_is_chrome_paragraph`: a "You are
     here" preamble, or >= 2 spaced chevrons (>, ›, ») forming a 3+ segment
     chain. Two separators (not one) keeps prose with a lone " > " safe; " / "
     is excluded because "and / or" is real prose. General win - breadcrumbs are
     never a landing on any page type.

  b. Even chrome-skipped, `find_notice_landing` was paragraph-first with headings
     as a pure fallback, so it would then land on idx 4 (the share prompt), never
     the heading that IS the message. Rewrote it: a heading owns the status
     UNLESS a status paragraph follows it before the next heading. The lookahead
     is what preserves the closed-form shape (title H1 + "no longer accepting
     responses" paragraph still lands on the sentence) - pinned by
     `test_notice_landing_title_heading_still_yields_to_status_sentence`. Result:
     the thank-you page lands on the H1.

Sabotage-checked both: breadcrumb OFF -> idx 2 (the reported bug); heading rule
OFF -> idx 4 (share prompt); both on -> idx 0.

### Watch during the soak

The notice-landing change touches a core intent's landing behavior, so it will
affect other NOTICE pages Casey hits. The residual risk is a NOTICE page whose
first heading in `main_nodes` is a poor label with no paragraph under it before
the next heading (e.g. a leaked nav "Menu" heading) - it would now land on that
heading instead of a later status paragraph. Judged unlikely on small scoped
NOTICE pages and it degrades to "announces what page this is" (the old
fallback), but the moved-caret line will show it if it happens.

## 2026-07-20 - an embedded video cut the lede off from the body (MacRumors)

318 tests. `main` still v1.0.13. New gate: `_find_title_lede_landing`.

### What Casey reported

macrumors.com "Apple Just Increased Prices" landed on "Subscribe to the
MacRumors YouTube channel for more videos." instead of the lede, "Apple today
dramatically increased device prices across multiple product lines."

### It was not a walk bug and not a stale position

Worth saying, because two of the three masquerading failures in DEBUGGING.md were
live possibilities. The lede WAS in the buffer (idx 2 of 82, `substantial` field
of the moved-caret line) and the speech path was honest: `stale-recovered` shows
the offset drifted and re-anchored BY TEXT onto the paragraph the classifier had
actually chosen. The add-on said what it meant. It meant the wrong thing.

Also worth recording as a non-event: `walk=102ms` on 181 chunks, against
1712-1850 ms on the same site on 2026-07-18. The field-stack backend is doing
what the scope-hardening branch hoped. No page in the 37 loads today truncated.

### The shape, and why every gate declined

    idx 0  H1        "Apple Just Increased Prices on MacBooks, ..."
    idx 1  paragraph  byline / timestamp                                (54)
    idx 2  paragraph  the lede                                          (79)
    idx 3-8           YouTube embed chrome: player name, video title,
                      channel, "648K subscribers", "Watch later", "Share"
    idx 9  paragraph "Subscribe to the MacRumors YouTube channel ..."   (59)
    idx 10 paragraph  body resumes                                     (149)

idx 2 loses on LENGTH alone: 79 is under VERY_SUBSTANTIAL (200) and under
HERO_PATTERN_MIN_CHARS (100), and the embed means its neighbour is a 20-char
player label rather than a substantial paragraph, so the cluster gate declines.
The cascade walked on to idx 9, which clusters with idx 10 and won.

Two near-misses that made this land wrong rather than merely oddly. idx 9 is 59
chars and idx 10 is 149, so teaser-skip needs 150 and misses by one character.
And idx 9 genuinely ends like a sentence, so the sentence-strict pass keeps it.
Neither is a bug; they just both failed to save us.

This is the structural fault CLAUDE.md already names: **the cascade awards the
landing on rule ORDER rather than evidence strength.** Same disease as IMDb, and
`_find_lead_section_landing` did not cover it -- that gate wants exactly ONE
candidate of 100+ chars in the section, and MacRumors' lead section holds four.

### The rule

Sentence-ending prose sitting directly under the page's own H1 is the lede.
POSITION plus GRAMMAR, not length. Nothing else on a news page occupies that slot.

Five guards, all five sabotage-checked (see below):

1. **Level-1 heading only.** A nav or widget heading is an H2/H3; requiring the
   H1 is what makes the slot mean "the page's title" and keeps the gate off
   cookie banners under a sidebar heading in an unscoped tree.
2. **Only fires where the cascade currently walks PAST the candidate** -- the
   next node must not be a substantial paragraph. When it is, the cluster gate
   already owns the page, teaser-skip included. This is what keeps the gate off
   the CNET teaser shape and off Wikipedia-style ledes; it makes the gate purely
   additive rather than a re-ordering of the cascade.
3. **Lookahead of 4 from the H1.** The lede sits under the title, past a byline
   at most. Eight nodes down it is a caption or a promo and we would be guessing.
4. **Stop at an intervening heading.** Once a second heading appears the slot is
   closed. hellomagazine.com is the live case: its H1 is immediately followed by
   an H2 dek, and without this the gate would have reached into the newsletter
   blurb below it.
5. **Sentence-ending required.** Bylines and timestamps share the slot and are
   skipped rather than being disqualifying, so the scan continues past them.

### Sabotage-check found two guards that no test enforced

Per the standing rule, each guard was deleted in turn to confirm a test fails.
Guard 1 and guard 3 came back NOT CAUGHT on the first pass, and guard 4 on the
second -- the suite stayed green with the safety removed. That is the fifth,
sixth and seventh time on this branch a rule has been unit-testable while the
thing enforcing it was deletable. Tests added for all three.

**One of those repair attempts was itself hollow, and that is the transferable
part.** The first guard-3 fixture passed with the lookahead deleted, not because
the guard was unnecessary but because `_find_lead_section_landing` claimed the
same index first and masked it. A fixture that exercises a gate has to be shaped
so the gates ABOVE it decline; otherwise it pins nothing and looks like it does.
Adding a second body paragraph made the lead-section gate decline ("exactly one"
is its load-bearing condition) and the fixture started biting.

### Verified against real trees, not just fixtures

Reconstructed all 82 MacRumors nodes from the log rather than trusting the
11-node fixture, because gates ABOVE the new one (content-section, lead-section)
only get their real chance on the full tree: 2, as wanted. ZDNET Prime Day stays
on 5 and hellomagazine stays on 18, both from their full logged trails.

### Still open, from the same log sweep

ewtnnews.com classified as `form(0.68)` on what reads like a news page
(`forms=4`) and landed on a 78-char headline-ish line. Not chased -- no node
trail was captured for it. Worth a look if Casey hits it again.

## 2026-07-19 (night) - the depleted-scope net has never fired, and its premise no longer holds

313 tests. `main` still v1.0.13. NO CODE CHANGE in this entry - it records why a
planned change was NOT made, which is the useful part.

### The plan that was abandoned, and what stopped it

Codex's last review proposed refining the depleted-scope net: stop widening to
`all_nodes`, widen instead to a RECOVERABLE set (everything except nodes dropped
by a TRUSTED mechanism, `_SCOPE_CHROME_DROP` / `_SCOPE_FIELD_DROP`), and then
delete the `positional_drops == 0` gate, since its only purpose was preventing
re-admission of correctly-removed chrome. The argument was clean and I believed
it. Both reviewers were briefed and were reasoning inside the same premise.

Then a cheap question: **how often has this net actually fired?**

    perf lines since the net shipped (2026-07-18):  245
      of those scope=chrome:                         63
      of those scope=chrome-pos:                     35
      times the net fired (`unscoped-depleted`):      0

Zero. And nothing in `tests/` references `unscoped-depleted` - the PREDICATE has
19 tests, the WIRING that consumes it has none, which is this branch's signature
gap for the fifth time.

### What the motivating page actually shows

The net was built for deadsimpletech.com/blog/midwinter, recorded as "the
identity chrome filter kept 3 of 16 walked nodes, all chrome, and discarded the
entire article INCLUDING a 1439-character paragraph". Loaded it. Three
observations, all from the decision trace:

**1. The net does not fire there, and has not been able to since before this
session.** The page is `chrome-pos` with `pos_drops=15`, so the
`positional_drops == 0` gate blocks it. That gate predates today for chrome-pos;
today only extended it to plain `chrome`.

**2. The first attempt reproduces the recorded symptom exactly** -
`main_nodes=3`, all chrome, `no-action: unknown(0.00)`, first node "Get new
articles delivered to your inbox". But `all_nodes=16` and `raw_seen=21`: the
1439-char paragraph is not in `all_nodes` EITHER. The scope filter never saw it.
**It had not hydrated yet.**

**3. On the hydrated page the filter is CORRECT.** Retry at +1500 ms:
`raw_seen=67 all_nodes=59 main_nodes=46`, landed on the 618-char article lede at
idx=6, `intent=article(0.85)`. A later Z press on the warm page: identical, 46 of
59 kept. The 15 drops are the logo, "WELLINGTON · AOTEAROA · EST. 2024", Home,
About Us, Pricing, Coaching, Contact, Blog, Quizzes, and the copyright line -
every one of them genuine chrome, 11 of them field-stack drops.

### The conclusion, and why the refinement is dead

**Stated carefully, because the first draft of this entry overclaimed.** It
called the original observation a misdiagnosis. That is TOO STRONG: the
docstring quotes six real paragraph lengths (618, 563, 699, 1002, 460, 1439),
so those paragraphs were genuinely observed in `all_nodes` on 2026-07-18.

What today's load supports:

  - Attempt 1 reproduces the symptom, and `raw_seen` went 21 -> 67 before the
    retry, so the page was HYDRATING. The retry landed correctly.
  - LIMIT: attempt 1 had 13 drops and the `[TMTS walk-drops]` line caps at 10.
    The 10 logged are all chrome; up to 3 are unaccounted for - FEWER than the
    6 body paragraphs recorded originally. So hydration explains THIS load
    well, and says nothing definitive about the original one.

The likeliest account, which is better than "misdiagnosis": the original
failure was the IDENTITY filter, the mechanism this net exists to distrust.
**Task 2 took identity off the routine path** - this page now walks with
`identity=0` and 11 field drops, keeping 46 of 59. The thing the net
compensated for is largely gone on supported backends, which fits it never
having fired.

Worse for the design: **had the net fired on the cold load it would have caused
harm.** Widening to `all_nodes` there means widening to 16 nodes containing no
article, and the most likely landing is "Get new articles delivered to your
inbox" - a WRONG landing, which guardrail 3 rates worse than the silence that
actually occurred. Refining WHICH nodes it widens to does not help; on that page
the recoverable set is just as empty of article text.

So: do not build the recoverable-set refinement. Codex's reasoning was sound
GIVEN the premise; the premise did not survive one page load.

### Not ripped out either, and why

One page load is not grounds for deleting a safety net, in the same way it was
not grounds for building on one. The net is now recorded as UNVERIFIED with its
motivating case explained away. The next step is EVIDENCE, not code: if
`unscoped-depleted` is still absent after another few hundred loads, it is dead
weight and should go, along with the `positional_drops` gate and possibly
`positional_drops` itself. Watch the persistent perf log for the tag.

### The lesson, which is the same one in new clothes

I was one review cycle from carefully refining a mechanism that has never
worked, because the refinement was argued well. Neither reviewer caught it -
both were reasoning inside the premise I handed them, which is what reviewers
do. What caught it was asking how many times the thing had fired.

The file already says "when a check comes back unanimous, ask whether it could
ever have come back the other way." This is the same question aimed at a
mechanism instead of a probe: **before improving something, confirm it has ever
done its job.** A safety net that has never fired is indistinguishable from one
that cannot.

### Open, unchanged

1. THE COUNTS, now clearly dominant (646-666 ms of ~730 ms on these loads,
   `counts_trunc=True` every time). Probe first: one-character expand at the
   item start, MAX call time not average, plus backend and NVDA version.
2. `_count_in_scope` drops an `obj is None` item without setting
   `truncated_out` - a TRUSTED undercount.
3. Objectless chunks still fail open on the plain-chrome and range-error
   identity branches.
4. `classifier.py:448` LIST branch is dead (`>= 5` against `_ARTICLE_LIMIT = 4`).
5. `main-id` via `controlIdentifier_docHandle`/`_ID`, behind its own probe.
6. The field_stack probe add-on is still installed; uninstall before a clean
   soak.
7. Whether `_LANDED_SUPPRESS_SEC` should be TI-aware rather than URL-only (see
   the cross-browser testing trap in the entry below).

## 2026-07-19 (evening) - Task 2 shipped, and review found two holes the suite could not see

313 tests, 15 sabotages all caught. `main` still v1.0.13.

**Read this entry, not the one below it.** The entry beneath describes the state
BEFORE Task 2 and was committed unchanged inside c7ec17b, so it says Task 2 is
"still open" in the very commit that ships it, and quotes 300 tests and three
sabotages. Both reviewers flagged it as a handoff that would mislead the next
session. It is kept for its reasoning, superseded on status.

### What Task 2 is, now that it exists

Landmark ancestry read from the LEADING CONTROL RUN of `getTextWithFields()`,
replacing the COM parent chain on chrome-scoped pages. The walk already fetched
that run for the ROLE, so the scope question costs dictionary lookups.

Tri-state: definitive chrome, definitive NOT_IN_CHROME, UNKNOWN. Gated on the
TextInfo CLASS **and its MODULE**. `main-id` deliberately keeps the identity
filter (identity question, unprobed). Counts untouched, held behind a probe.

### MEASURED ON REAL PAGES, both engines

stevequayle.com, the page that motivated all of this:

    walk_total=84ms  obj=0ms  fields=64ms  chunks=113
    parent_derefs=0  identity=0  field=113  field_backend=y

Zero COM parent chains, against 1808 ms of a 2035 ms walk before and 6+ seconds
uncached. 84 ms is exactly what `chrome-none` achieved, now earned by positive
per-chunk evidence instead of an unsound inference. Landed correctly at idx=11.

**Firefox AND Chromium both report `field_backend=y`** (Gecko via
`Dynamic_DocumentMozillaIAccessible`, Chromium via `IAccessible.chromium.Document`).
Chromium inherits Gecko's TextInfo, so one gate covers both. Cross-engine
question closed. Edge confirmed working across several sites.

Counts are now the dominant cost (655 of 740 ms, `counts_trunc=True`). That is
the next target and it is measured, not guessed.

### A TESTING TRAP worth more than the fix: the same URL across browsers

Edge appeared broken. It was not. The trace said:

    already landed on url='https://www.stevequayle.com/' 22.4s ago
      -- suppressing re-detection

`_LANDED_SUPPRESS_SEC` (120 s) is keyed on **URL alone**, not URL+browser. Chrome
had landed on that URL 22 s earlier, so Edge was suppressed by Chrome's landing.
**Testing the same URL across browsers inside two minutes is VOID**, and only the
decision trace says why. Same family as the focused-browser rule. Whether the
gate should be TI-aware is a real open question, deliberately not answered while
reviews were in flight.

### The two holes review found, and what they say about the method

Codex and Fable, run in parallel, INDEPENDENTLY found the same two deletions
that left all 307 tests green:

1. **The chrome-pos field consultation was wired but entirely untested.** Every
   `exclude_ranges` test used the plain `FakeTI`, where the backend gate forces
   the verdict to None; every supported-backend test omitted `exclude_ranges`.
   The two were never exercised together, so the whole branch deleted green.
   Not cosmetic: inside an untrusted range the field stack is the ONLY mechanism
   that can see a nested nav the enumeration may have omitted.
2. **Innermost-wins was untested in both directions.** The `lm()` helper emitted
   one landmark per chunk, so no nested stack existed anywhere in the suite;
   both inverting `reversed(seen)` and deleting the `main` early return passed
   green.

That is the FOURTH instance of this branch's signature failure, and the first
time the sabotage harness was pointed at new work and still missed it -- because
the harness only tests the sabotages someone thought to list. Two independent
reviewers converging on the same two gaps is the actual control here.

### Also fixed from review

- **Malformed landmark VALUES could fail open.** `str(lm).lower()` coerced any
  truthy object into a name: `landmark=123` became `"123"`, matched nothing, and
  fell through to the POSITIVE verdict. Now non-strings return UNKNOWN and
  values are stripped (`" navigation "` was slipping through too).
  Sabotage-checking this taught something worth keeping: deleting the
  `isinstance` guard alone changes NOTHING, because `.strip()` raises and the
  handler returns None regardless. The load-bearing part is the absence of
  coercion, not the guard. Recorded at the line.
- **Backend gate now matches the MODULE as well as the class name**, so a
  third-party backend defining `Gecko_ia2_TextInfo` cannot be falsely trusted.
- **Two documentation claims were overstated and are corrected in place**, not
  quietly deleted, because overstated citations are how this file has been wrong
  before: `getTextInRange` does NOT emit its tag "unconditionally" (a
  zero-length node returns first, storage.cpp:275-278; harmless, since such a
  node cannot enclose a non-degenerate range), and Gecko is NOT the only
  normalizer writing `field["landmark"]` -- MSHTML does too, and is excluded
  deliberately for lack of probe evidence, not by accident.
- **The parity that actually makes the True verdict safe**, found by
  disassembly: Gecko's `_normalizeControlField` DISCARDS a landmark when the
  mapped role is not `Role.LANDMARK` and it is not the first xml-role. So an
  absent key does not prove no ARIA landmark. What rescues it is that
  `ia2Web._get_landmark` applies the byte-identical rule, so the parent chain we
  replace is blind in exactly the same cases. The question answered is "would
  the identity filter have called this chrome", and to THAT it is sound.
- **The scope-kinds comment was actively lying** after the commit (still named
  the deleted FREE kind, omitted the FIELD kinds, and claimed only CHROME_* feed
  `positional_drops` and only chrome-pos consumes them -- false twice). Rewritten,
  including the rationale nobody had written down: identity drops are
  deliberately NOT counted, because identity is the mechanism the net exists to
  distrust. Counting them would switch the net off on the pages it rescues.
- **`[TMTS walk-phase]` now reports `field=`, `field_drops=` and
  `field_backend=`** separately from `positional=`. An aggregate that cannot name
  the mechanism is what stalled the payproglobal investigation for a session.

### Open, in the order I would take them

1. **The depleted net is too coarse (Codex).** On a mixed-evidence page -- one
   definitive field drop on a header nav, body chunks UNKNOWN and wrongly
   discarded by the identity chain -- `positional_drops > 0` disables recovery
   for the WHOLE page, and the result is silence. Fail-closed, but it disables
   the net exactly where it is needed. The durable fix is a recoverable-node
   list that keeps identity-uncertain drops while permanently excluding
   `_SCOPE_CHROME_DROP` and `_SCOPE_FIELD_DROP`, and widening to THAT rather
   than to raw `all_nodes`. Do not revert plain `chrome` to unconditional
   widening; that knowingly re-admits proven chrome.
2. THE COUNTS, now measurably dominant. Probe first: one-character expand at the
   item start, MAX call time not average, plus backend and NVDA version.
3. `_count_in_scope` drops an `obj is None` item without setting
   `truncated_out` -- a TRUSTED undercount, poison for NOTICE and KEY_RESULT.
   Its sibling `_count_in_range` biases the OPPOSITE way on the same evidence.
4. Objectless chunks still fail open on the plain-chrome and range-error
   identity branches. Pre-existing; both reviewers say CLAUDE.md mis-files it as
   an accepted limitation.
5. `classifier.py:448` bumps LIST confidence at `article_count >= 5` while
   `_ARTICLE_LIMIT = 4` caps it. Dead branch.
6. `main-id` via `controlIdentifier_docHandle`/`_ID`, behind its own probe.

### The habit, restated because it keeps paying

Two reviewers in parallel, every round. They disagreed on the chrome-none
remedy (and the losing argument still corrected a false claim in my brief), and
here they CONVERGED on two holes I had no way to see from inside. Neither the
test suite nor the sabotage harness could find these, because both only check
what someone already thought to check.

## 2026-07-19 (later) - the chrome-none blocker is CLOSED by deletion

300 tests (was 301: the removal deleted more test surface than it added).
`main` still v1.0.13. Uncommitted on `scope-hardening`.

### Decision: option 1, delete it. Both reviewers ran; they split on sequencing.

Codex and a Fable subagent reviewed in parallel. Both independently confirmed
the bug FROM THE INSTALLED BYTECODE (`virtualBuffers/__init__.pyc` in NVDA's
`library.zip`: the handler around the `VBuf_findNodeByAttributes` call is
PUSH_EXC_INFO / POP_TOP / POP_EXCEPT / RETURN_CONST None with NO
CHECK_EXC_MATCH, so it discards everything and ends the generator normally).
Both agreed on the test requirement, on the WebKit fallback being acceptable,
and on the three adjacent bugs below.

They DISAGREED on the remedy, and the disagreement was the useful part:

- **Codex: delete now**, then Task 2 separately. "A partial Task 2 used only to
  rescue chrome-none is not a useful third design."
- **Fable: land a field-stack tripwire inside chrome-none FIRST**, then Task 2,
  then delete. Its argument had a genuinely attractive asymmetry: used purely
  as a REFUSAL check the tripwire needs no backend gate to be safe, because on
  an unsupported backend it finds nothing and you are exactly where you are
  today, never worse.

**Resolved for delete-now on this ground: the tripwire NARROWS the blocker but
does not CLOSE it.** On WebKit (the module contains no "landmark" string at
all) and on malformed field stacks it stays silent, so the fail-open path
survives. A merge blocker has to be closed, not narrowed.

The interim cost is a SILENCE on landmark-free many-chunk pages, which is the
direction guardrail 3 specifies ("when in doubt, do nothing"). Task 2 restores
the speed properly.

### Fable was RIGHT and I was WRONG about the blast radius

The brief claimed the regression was not user-facing because the branch is
unmerged. False, and checkable: the installed add-on under the NVDA addons
directory contains `chrome-none` (installed 2026-07-18 20:06). The branch build
is Casey's daily driver, so the fail-open was LIVE, and the soak - the
project's main evidence instrument - was running on it. That strengthens
delete-now rather than weakening it.

### Both reviewers corrected the "unbuilt, unprobed" framing of Task 2

`_walk_main_nodes` ALREADY calls `getTextWithFields()` for every chunk
(`tree_summary.py:2264-2274`) to feed `_role_level_from_fields`. Reading
`field.get("landmark")` off that already-parsed leading run is dictionary
lookups. The fetch and the parser are shipped; Task 2 is smaller than the
previous entry implies, and its walk cost should be slightly BETTER than
chrome-none rather than merely comparable.

### A trap for the backend gate, found by Codex and worth not re-deriving

**Do not gate on `backendName`.** Chromium does not declare its own - it
inherits Gecko's "gecko_ia2" - so the string cannot distinguish the engines and
a gate written against it is gating on the wrong thing. Gate on the TextInfo
CLASS (isinstance against the Gecko TextInfo, which Chromium passes by
inheritance). The probe now logs `backend`, `ti_class`, `ti_type` and the NVDA
version on its START line; the previous run logged none of these, which is why
its results could not be attributed to an engine after the fact.

### What shipped

- `_document_has_no_landmarks` and the `chrome-none` scope deleted, along with
  the `no_landmarks` parameter threaded through `_walk_main_nodes` and
  `_chunk_scope`, and the `_SCOPE_FREE` verdict.
- `LandmarkScan.exhausted` KEPT but demoted to diagnostic, with the
  disassembly recorded at the field itself - that is where the next person
  reaches for it.
- A block comment where the function used to be, stating why it cannot be
  rebuilt.
- `tests/test_chrome_scope.py`: the fast-path block replaced. The old test
  `..._with_working_enumeration_takes_the_fast_path` drove `FakeTI([])`, which
  IS the native-swallow shape, and asserted the shortcut engaged - it PINNED
  THE BUG. The old `exhausted`-separates-the-two-cases test asserted something
  false and is gone. The new tests assert at the SCOPE-SELECTION level, so a
  shortcut reintroduced under any name still trips them.
- `tests/sabotage_check.py` (NEW, reusable). Confirms tests fail when the fix
  is reverted, in three disguises: verbatim, renamed, and smuggled in as an
  empty exclusion list. All three caught. It captures the original bytes ONCE,
  restores in a `finally`, asserts the restore is byte-identical, and re-runs
  the full suite rather than trusting it - and runs every subprocess with `-B`
  plus `PYTHONDONTWRITEBYTECODE`, because .pyc validation keys on source mtime
  and SIZE and has previously made a sabotage run report on code never loaded.

### Still open, in the order I would take them

1. Task 2, the guarded walk path, with the tri-state and the CLASS-based
   backend gate. Restores the speed this removal cost.
2. `_count_in_scope` silently DROPS an item whose `obj is None` without setting
   `truncated_out` (`tree_summary.py:1712`), producing a TRUSTED undercount -
   poison for NOTICE and KEY_RESULT, which fire on SMALL counts. Note its
   sibling `_count_in_range` biases the OPPOSITE way on the same class of
   missing evidence (`:1743`), so the two counting paths disagree about what
   "no evidence" means.
3. Objectless chunks still fail open on the ordinary identity branch and the
   range-error branch of `_chunk_scope`, while `chrome-pos` correctly refuses
   that shape. Both reviewers said CLAUDE.md mis-files this as an accepted
   limitation; it is the same fail-open family with a ready-made fix pattern.
   Pre-existing, so not a blocker.
4. `classifier.py:448` bumps LIST confidence at `article_count >= 5` while
   `_ARTICLE_LIMIT = 4` caps the count at 4. Dead branch, confirmed.
5. Codex adds: the depleted/empty fallback (`tree_summary.py:461-465`) can
   reopen a correctly filtered document and re-admit cookie/nav/subscription
   text. Records as a latent correctness bug, not an accepted limitation.
   Task 2 should make the rescue unnecessary on supported backends.

### The habit that paid here

Running BOTH reviewers in parallel produced a disagreement neither would have
surfaced alone, and the losing argument still corrected a false claim in my own
brief. Keep doing this before believing any design on this branch.

## 2026-07-19 - MERGE BLOCKER in chrome-none, and the field-stack design survives review with conditions

301 tests. `main` still v1.0.13, so NOTHING here is exposed to users.

### MERGE BLOCKER: `_document_has_no_landmarks` trusts a flag that cannot mean what it claims

**RESOLVED 2026-07-19 by deletion — see the entry above.** The analysis below
stands and is kept because it is the reasoning that must not be re-derived; only
the "not decided" disposition at the end is superseded.

Found by Codex, confirmed empirically against the real code:

    scan = _find_main_landmark(FakeTI([]))   # yields nothing, returns normally
    scan.seen        == 0
    scan.exhausted   == True
    _document_has_no_landmarks(scan, 5) == True   # -> chrome-none

`exhausted` is set when OUR loop completes. NVDA's `_iterNodesByAttribs`
CATCHES the native exception from `VBuf_findNodeByAttributes` and RETURNS, so a
natively failed landmark search is an ordinary, empty, completed generator.
`exhausted=True` therefore rules out a Python exception escaping the iterator
and NOTHING ELSE - while the docstring claims "the scan already knows which
event happened (it caught the exception itself)". It knows about one of the two
events.

Consequence: on a page whose landmark search failed natively but whose link
enumeration worked, `chrome-none` activates, the walk skips chrome checking
ENTIRELY, and navigation and footer text are admitted as content. A blind user
lands in a menu. That is the release-blocker failure class.

`tests/test_chrome_scope.py:621` gives false confidence: it drives the iterator
with `raise_after=0`, which makes the exception ESCAPE. That is the shape
`exhausted` genuinely catches. The shape NVDA actually produces - swallowed,
empty, normal return - is untested, and passes.

This is the SAME indistinguishability that killed `chrome-pos-attempt`,
reintroduced in a different function. And it was looked at directly earlier the
same day, in the Change A analysis, and written down as "a pre-existing accepted
risk in the walk" instead of as a bug. Noticing a hazard and mis-filing it is
its own failure mode; the Change A reasoning depended on that same fact and
correctly rejected the change, so the observation was RIGHT and the disposition
was wrong.

Two candidate fixes, NOT decided:
1. Delete `chrome-none`, falling back to the identity chrome filter (the
   pre-2026-07-18 behaviour). Sound, simple, costs the measured speed on
   landmark-free pages (stevequayle's walk was 84 ms with it).
2. Gate it on field-stack landmark evidence, which does not consult the
   enumeration at all - but that is the unbuilt design below, so this couples a
   blocker fix to new work.

### The field-stack design: question 1 is answered, in its favour

Both reviewers verified from `nvdaHelper/vbufBase/storage.cpp` READ DIRECTLY
(downloaded, not summarized) that `VBufStorage_fieldNode_t::getTextInRange`
emits its own opening tag unconditionally and recurses into every child whose
span overlaps the range, starting at `rootNode`, with the filter argument
defaulted to NULL. Every positive-length field ancestor of the range start is
therefore emitted, and presentation filtering happens LATER, in
`getEnclosingContainerRange`. The installed bytecode confirms
`_getFieldsInRange` drops no commands.

**So the leading control run is the complete virtual-buffer ancestor chain.**
The fail-open the brief feared does not exist on the proven backend.

### Four conditions the reviews attached, all of which change the design

1. **"No landmark in the stack" is NOT "content".** Name it `NOT_IN_CHROME`.
   It proves only "no marked chrome landmark ancestor at this offset in the
   vbuf" - not that the document has no landmarks, not that the site marked its
   chrome correctly. Three states are required: definitive-chrome,
   definitive-not-in-chrome, and UNKNOWN (failed call, `''`/`['']`, no leading
   controlStart, malformed field, unsupported backend). The walk already models
   exactly this with `had_field` in `_role_level_from_fields`.
2. **Backend gate, or it is fail-open.** `field["landmark"]` is BACKEND
   normalization, not a `TextInfo` contract. Gecko/Chromium populate it;
   **WebKit's normalizer does not**. On an unsupported backend every chunk
   would read "no landmark" and all chrome would be admitted. The probe does
   not log `backendName`, so it establishes nothing cross-backend.
3. **The two mechanisms are independent in TRAVERSAL ONLY.** The previous
   entry's "second independent source" claim is too strong and is corrected
   here. `_normalizeControlField` and `Ia2Web._get_landmark` compute the same
   `next()` over the same `aria.landmarkRoles` set and null it under the same
   condition, so if a browser misreports `xml-roles` BOTH go blind. The field
   stack IS independent of the landmark ENUMERATION, which is what the Change A
   objection was about - that part stands, narrowly.
4. **`main-id` is not answerable this way.** "Is this inside THE `<main>` we
   found" is identity (`cur is main_obj`); `landmark == "main"` matches ANY
   main. Unprobed. Either keep identity there or match
   `controlIdentifier_docHandle`/`_ID`, which needs its own probe.

### Combination rule, and why "chrome if EITHER says chrome" is wrong

It keeps a COM chain for every clean CONTENT item, which is the majority, so it
forfeits nearly the whole win - and for the COUNTS it is not even conservative:
a false chrome verdict REMOVES items without setting `counts_truncated`, and
smaller counts manufacture NOTICE and KEY_RESULT. Agreed rule instead: field
says chrome -> exclude; field definitively not-in-chrome -> accept, no COM;
unknown -> `_in_scope_verdict`; parent unknown -> keep (walk/counts) or refuse
(focus). `_in_scope` is retired as the ROUTINE authority, kept as the fallback.

The focus gate gets a stricter rule than either: the field stack is a buffer
SNAPSHOT while `setFocus()` acts on the LIVE object, and a dynamic page can
reparent the control in between (unmeasured race). So require definitive field
permission AND a live `_in_scope_verdict(...) is True` immediately before
`setFocus()`. That is one COM chain per FORM page, not per chunk.

### Counts: do NOT extrapolate the 0.7-1.1 ms figure

That is a PARAGRAPH number. A quick-nav item's range can be a whole article, and
`getTextWithFields` serializes and parses everything inside it. Collapse to the
item start and expand ONE CHARACTER instead - the leading run there still
carries full ancestry. Budget math before committing: 6 types x 300-item scan
cap x ~1 ms is ~1.8 s against a 0.6 s counts budget, so `counts_truncated`
stays load-bearing and "cheap against COM" is not "fits the budget".

Also found, unrelated and real: `_count_in_scope` silently DROPS an item whose
`obj is None` without setting `truncated_out`, producing a TRUSTED undercount.

### Agreed plan

1. Resolve the `chrome-none` blocker (decision needed).
2. Build the guarded WALK path only, on Gecko/Chromium, with the tri-state and
   the backend gate, pinned by deletion-confirmed end-to-end tests.
3. Probe before the COUNTS: one-character call cost distribution (MAX, not
   average), backend name, NVDA version.
4. Probe before touching `main-id`.
5. Do NOT delete `trust_boundary` / `untrusted_ranges` / `_chrome_pos_verdict`
   in the same change that adds the field path. Two steps, each pinned.
6. One Firefox rerun of the probe before calling the mechanism cross-engine.

## 2026-07-18 (night) - the counts fix died in review, and the safety net it would have leaned on was fail-open

301 tests. Uncommitted on `scope-hardening`. `main` still v1.0.13.

### What was planned, and why none of it shipped

The target was the counts phase, which the lazy-fetch work promoted into the
dominant cost (646-691 ms on chrome-scoped pages; 691 of stevequayle's 777 ms,
`counts_trunc=True` every time). Two changes were designed and sent to two
independent reviewers. Both reviewers rejected the main one, for the same
reason, arrived at separately.

**Change A - count document-wide on `chrome-none` - is dead. Do not rebuild
it.** The argument was that on a page whose landmark scan emitted nothing, the
parent chains "can only ever conclude in scope", so paying for them is waste.
That is true only when the enumeration told the truth. NVDA swallows the native
failure inside `_iterNodesByAttribs`, so a silently failed scan is
indistinguishable from a landmark-free page - and on that page the parent chain
is the ONLY independent evidence the scan lied. The 691 ms is not computing a
foregone conclusion; it is the second opinion.

Worse, it is circular. `interactive_count` is itself one of the counts, and
`_document_has_no_landmarks` consumes it as the corroboration that decides
whether the WALK drops its filter. Counting document-wide would have produced
the number that then proved no chrome exists - a corroborator downstream of the
assumption it exists to check. After the change, `interactive_count > 0` could
fail only on a page with no controls at all: hollow evidence, the exact pattern
this file already records twice.

And a second path neither of us had spotted: `tree_summary.py:366` promotes
scope to positional `article` when the article count is exactly 1, BEFORE
`chrome-none` is decided. A document-wide article count could therefore scope
the entire walk to a single `<article>` sitting inside chrome.

**Change B - bounded-trust positional counts on `chrome-pos` - survived, but
shrank.** It helps vovsoft (88 of 109 chunks were decided positionally there)
and does nothing for thurrott, whose only landmark is a top nav, putting the
trust boundary at offset 0. Both reviewers also caught a factual error in the
brief: it claimed the counts are "inclusive on a missing textInfo" and proposed
preserving that. That is `_count_in_range`'s behaviour, on main-pos/article
pages. The path Change B touches uses `_count_in_scope`, which requires an
object (`tree_summary.py:1631`), so "preserve the bias" would have flipped
no-evidence items from excluded to COUNTED, in the direction of FORM. Shelved
rather than shipped, on Casey's call, because the real fix below subsumes it.

### What DID ship: the identity filter could not say "I do not know"

Review found a wrong-answer bug, pre-existing and independent of the perf work.
`_in_scope` ended with `result = main_obj is None` for every way of leaving the
parent walk without an answer - a dereference that raised, or a chain deeper
than the 30-ancestor cap. On a page with no `<main>` that expression is True.
So **"we could not prove this is chrome" was returned as "this is proven
content"**, and the verdict was then cached against every ancestor visited on
the way, handing one COM failure's unearned answer to every sibling under that
chain.

It lands hardest where the design leans on it hardest. `chrome-pos` routes its
undecidable chunks to the identity filter AS its safety mechanism, and
`_form_field_in_scope` - the path that calls `setFocus()` - documented itself
as "Fails CLOSED throughout" while delegating there. It did not fail closed.
One failed dereference could put a blind user's caret in a header search box.

`_in_scope_verdict` is now tri-state; `_in_scope` is a thin wrapper keeping the
OLD default for the walk and counts, whose documented policy really is "keep
what you cannot classify". The focus path takes the tri-state and accepts only
True. Both of its identity fallbacks were fixed: the second one matters because
`article` scope is positional with NO `<main>`, so `main_obj is None` there too
and the old default read as content.

An undecided walk now caches NOTHING. That is a deliberate perf tradeoff on the
failure path (a truly unreachable chain is re-walked per item), and it is the
half of the bug that made a single failure contagious.

### Trap I walked into, caught by an existing test

Restructuring the loop, I set `decided = True` on clean root termination but
never computed the answer, so the ordinary case returned None. Caught by
`test_focus_move_skips_a_field_inside_chrome`. Worth recording because it is
the failure mode of tri-state refactors generally: the "ran out of ancestors"
exit is the ONE place the old blanket default was correct, and it is easy to
delete along with the three places it was not.

### Known divergence, deliberate, NOT resolved

A form control the focus gate would refuse for lack of evidence can still
contribute to `form_input_count`. So the counts can call a page FORM and the
focus gate can then decline every field that made it one. Codex proposed
tightening the counts to match. Not done: it changes classification on pages we
have no measurement for. The probe now reports how often the undecided path is
reached at all - decide it on that number.

### The real answer to BOTH perf problems, and it needs the probe first

Both reviewers independently landed on the same direction, and it is better
than anything in the original brief because it fixes the counts AND the walk's
parent chains on identity-bound pages (thurrott: `scope=1805ms`, 141
dereferences, truncated at 26 chunks and 5 nodes).

**Read landmark ancestry off the leading control field stack.** Verified in the
INSTALLED `virtualBuffers/__init__.pyc`: NVDA's own `getEnclosingContainerRange`
pops control fields and tests `field.get("landmark")`. The leading run is the
ancestor stack at the range start (established last session against the same
function). So the ancestry `_in_scope` buys at 13-18 ms per COM dereference may
already be in data the walk fetches in-process for well under a millisecond -
and unlike every positional design tried here, it does NOT depend on the
landmark enumeration being complete, which is the constraint that killed
attempts 1 and 2.

Also verified this round, from source downloaded and read directly (not a
summary): `storage.cpp:207-220` `locateTextFieldNodeAtOffset` accumulates
`tempOffset += child->length` with `nhAssert(firstChild != NULL || length ==
0)`, so children exactly partition their parent's span and any two vbuf nodes
NEST OR ARE DISJOINT - partial overlap is impossible. That confirms a proposal
to advance `trust_boundary` from the last landmark's START to its END is sound.
It is also small: it makes chunks INSIDE the top nav decidable, while thurrott's
content sits after the nav and stays on the identity path. Both reviewers said
so independently. Sound, cheap, not the win.

### PROBE RESULTS, 4 pages, 153 chunks (run 2026-07-19)

thurrott.com front, deadline.com article, stevequayle.com front, vovsoft
product page. Casey installed and triggered each himself.

**1. Role equivalence is now MEASURED, not argued.** `disagree_role_exact=0`
across all 153 chunks, with `trailing_control_chunks` totalling 26 - so the
inline-control shape that broke the first implementation was richly sampled
(14 on stevequayle alone) rather than absent. This is the honesty gap the
previous entry opened; it is closed. The 219-chunk claim it replaces was
worthless for the reason recorded there.

**2. Landmark ancestry: the field stack never missed a landmark the parent
chain found.** 48 chunks carried a landmark on the object side, across three
pages, and in that direction there were zero disagreements. That direction is
the dangerous one - a missed landmark serves navigation as article text.

**3. It found three the parent chain MISSED, and it was right about all
three.** On deadline: `banner` on "Got A Tip?" and "Deadline", and
`banner`+`navigation` on "BOX OFFICE". The object chain reported
`outcome=root` on each, i.e. it walked to the top and concluded there was no
landmark at all. Note the dereference counts: 3, 2, 3. A header link's real
ancestry is far deeper than three nodes, so those chains are terminating
early. That is independent corroboration, from a new direction, of the
"identity check silently fails" limitation CLAUDE.md has carried since the
Calendar and bestmidi cases.

Pre-registered criterion was `lm_disagree > 0` kills it UNTIL THE CAUSE IS
UNDERSTOOD. The cause is understood and it favours the substitution. Recording
that explicitly so nobody later reads it as a threshold quietly reinterpreted
after the fact.

**4. The fail-open fixed today is reached on 7.2% of chunks in the wild**
(`lm_chain_error` 4 + 0 + 3 + 4 = 11 of 153). Before today every one of those
was reported as proven content on no evidence. That is not a rare path, and it
settles the open counts-divergence question below as a real decision.

**5. Cost, summed over the four pages: 16,564 ms of parent chains against
138.8 ms of field stack.** Roughly 119x. (The probe's chain walk is uncached
where production caches ancestors across chunks, so the production figure is
lower - thurrott measured 1805 ms against the probe's 2835 ms. The ratio stays
overwhelming either way.)

**6. stevequayle proved nothing about agreement, by design.**
`lm_stack_any=0` and `lm_obj_any=0`: neither method found a landmark on any of
40 chunks, so `lm_disagree=0` there could not have been anything else. Counted
as no evidence, per the criterion set in advance. What it does show is that the
enumeration told the truth on that page, and that establishing so cost 499
dereferences and 6.5 seconds.

### WHAT THIS CHANGES ABOUT CHANGE A, which was correctly killed

The reviewers' objection was precise: the parent chain is the ONLY independent
evidence that a zero-landmark enumeration lied, so removing it removes the
check. That objection was right when it was made and is now obsolete. **The
control field stack is a SECOND independent source of landmark ancestry.** It
does not consult the landmark enumeration at all, and it costs about a
millisecond per item.

So the counts fix is not "trust the enumeration and count document-wide" and
not the sampled spot-check both reviewers proposed as a mitigation. It is
"verify the enumeration cheaply, per item, from data we already fetch". That is
strictly better than anything in the reviewed brief.

NOT YET DESIGNED OR REVIEWED. The next session should write it up properly and
send it out before implementing - what the reviewers approved is not what this
would be, and the last three sessions each shipped something a review would
have caught. Open questions at minimum: whether the counts should call
getTextWithFields per quick-nav item (the walk gets it for free, the counts do
not); whether a landmark-free field stack is positive evidence of content or
merely absence of evidence; and whether `_in_scope` should be retired on these
paths or kept as the tie-breaker.

The `field_stack` probe measures the landmark question alongside the role
question, with kill criteria fixed in advance: `lm_disagree > 0` kills the
substitution, and if `lm_stack_any` and `lm_obj_any` are BOTH 0 the run sampled
no landmarks and proves nothing. It also counts `lm_chain_capped` and
`lm_chain_error`, which is the first measurement of how often the fail-open
above was actually reached on real pages.

## 2026-07-18 (late) — the object fetch is lazy, and the probe that licensed it was wrong

291 tests. Uncommitted on `scope-hardening`. `main` still v1.0.13.

### What shipped

`info.NVDAObjectAtStart` was fetched unconditionally for every walked chunk:
3+ cross-process COM round trips, 11-29 ms measured, 60-98% of the walk on
chrome-scoped pages, and on a fully positional page not one of them was needed.
Role and heading level now come from the control field stack
(`_role_level_from_fields`), and the object is fetched LAZILY via a `_get_obj`
closure only where the positional scope verdict returns None. It is NOT removed:
`_in_scope` is the identity fallback the chrome-pos design leans on as its safety
mechanism, and on identity-scoped pages the object is still the only evidence
there is. Pinned in both directions by test.

Also: `_chunk_scope` extracted from the walk, returning the DECISION KIND so the
walk DERIVES `positional_drops` instead of incrementing it beside the branch.
That counter is a safety input (the depleted-scope net keys on it), and as a bare
`+= 1` it was deletable with a green suite.

### The lesson, and it is the same one as last time

**I applied the hollow-probe test to one number and not to the number I was
relying on.** The probe reported `disagree_heading_first=0`, and I correctly said
that proved nothing because the shape never occurred. In the same breath I cited
`disagree_innermost=0` over 219 chunks as proof of equivalence. It was not.

`_role_level_from_fields` scanned the WHOLE field stream and kept the last
`controlStart`. `getTextWithFields` interleaves text with control commands, so a
paragraph containing an inline `<img>` reads as GRAPHIC — a SKIP role — and the
whole paragraph vanishes from `main_nodes` AND `all_nodes`, unrecoverable by the
depleted net. The probe implemented the SAME whole-stream rule, and its
comparison reduced roles to heading/skip/paragraph, so LINK against PARAGRAPH
scored as agreement. Two blind spots stacked, and the sample (20 top-of-document
chunks per page) contained none of the shape either way.

Both reviewers found it independently. Verified in the installed
`virtualBuffers/__init__.pyc`: NVDA's own `getEnclosingContainerRange` iterates
`getTextWithFields()` and BREAKS at the first item that is not a `controlStart`.
The leading run is the ancestor stack at the range start. Matching NVDA's own
container resolution is a better reason to prefer this rule than any count.

The probe is corrected: leading run, exact role comparison, plus a
`trailing_control_chunks` counter that reports whether the run sampled the shape
at all. **A rerun is what would establish equivalence; the 219-chunk result does
not.**

### Two more fail-opens caught in review, both mine

- `_get_obj` caught exceptions and memoised `None`. Two identity branches read
  `obj is None` as IN scope, so a transient COM failure would have admitted an
  unverified navigation chunk as content. The old eager fetch let the exception
  reach the walk's outer handler. Exceptions propagate again; timing via
  `finally`.
- A field whose INNERMOST role failed to resolve inherited its ancestor's role,
  so an unresolvable BUTTON arrived as DOCUMENT and was admitted as a paragraph.
  Now reports no evidence and pays for the object. Same reasoning for an
  unreadable heading level: level feeds heading-cluster comparisons, so a wrong 0
  can merge distinct levels — defer to the object rather than guess.

### THE BYTECODE CACHE CAN MAKE A SABOTAGE CHECK LIE

This branch has now been burned four times by tests that pass while the wiring
they cover is deleted, so sabotage checks are the control. **A sabotage harness
that rewrites a source file and immediately re-runs pytest can silently execute
the PREVIOUS version**: `.pyc` validation keys on source mtime and size, and rapid
successive rewrites defeat it non-deterministically. One check reported NOT CAUGHT
that was in fact caught. **Always run sabotage checks with `python -B`.**

Second trap from the same episode: a harness that crashes between writing the
sabotage and restoring leaves the file DAMAGED, and the next script reads that as
its baseline and faithfully "restores" the damage. Caught only because the suite
dropped to 285. Restore in a `finally`, and re-run the full suite afterwards —
never trust the restore.

### Open

1. **Rerun the corrected probe** to establish equivalence honestly, and check
   `trailing_control_chunks > 0` before believing any unanimous result.
2. **Counts are still identity-scoped on `chrome-pos`** (~630 ms), so counts and
   walk can describe different trees. FORM is the intent that moves keyboard
   focus, which is why it matters. Untouched.
3. The lazy fetch is unmeasured on real pages. `[TMTS walk-phase]` now carries a
   `fields=` phase and `obj=`/`scope=` are disjoint; the claim to check is that
   `obj=` collapses on `main-pos` and `chrome-pos` pages while landings are
   unchanged.

## 2026-07-18 (evening) — the vovsoft diagnosis in the entry below is WRONG

Four commits on `scope-hardening`, all verified on live pages. 267 tests.

### Correcting the entry below before anything else

**Open item 1 below names the wrong mechanism, and a second wrong mechanism was
added on top of it before anyone checked.** Both were disproved by the decision
traces already sitting in `nvda.log`.

- The entry says the 200-char `VERY_SUBSTANTIAL_PARAGRAPH_CHARS` shortcut caused
  it. It did not. Network Alarmer and Read Mode mislanded with descriptions of
  263/207 and 220/681/587 chars — all comfortably OVER 200. They would have won
  that rule outright.
- I then proposed walk truncation. Also wrong, and the reasoning that kills it is
  simple enough that I should have seen it unaided: the walk only removes the
  TAIL, so the blurb winning PROVES the description was walked too. Network
  Alarmer and Read Mode both mislanded with `truncated=False`.

**The real mechanism: `_find_content_section_landing`.** It matched the "Key
Features" heading and then scanned forward with NO distance limit, stopping only
at the next heading. On a page whose matching heading is the LAST one, it ran to
the end of the document and claimed the licensing paragraph 15 nodes past its own
section. It runs BEFORE the size and cluster cascade, so it outranks everything.
Fixed with a 4-node bound matching the hero gate: a heading vouches for the text
it INTRODUCES, not for everything downstream.

**The purchase-vocabulary fix proposed below was NOT implemented, deliberately.**
Four vendors (vovsoft, JAM, Ghisler, NCH) showed no shared formula — there is no
FTC-equivalent mandating purchase wording, which is the whole reason the
affiliate and SMS families are tractable. Worse, it could not have fired: the
vovsoft blurb's first 60 chars are "To receive license key and use all features
of the software, " (61 chars), so every distinctive phrase sits past the preview
cutoff, leaving only "license key" — far too broad, since installation notes and
licensing FAQs are genuine content on those same pages. And `_is_chrome_paragraph`
feeds the Z forward scan, so flagging it would make that paragraph unreachable by
Z on a real order page, where it is the content the user came for.

### Also shipped

- **Definitional lede.** The cluster gate awards the landing to the FIRST of two
  adjacent substantial paragraphs, which on a product page is routinely a
  prerequisite note above the description. `"<Subject> is a/an/the ..."` is a
  general prose pattern and the subject is the page's own H1. Built as a
  REFINEMENT, not a gate: it can only move a landing FORWARD a few nodes inside
  the block the cluster gate already chose. The cascade's documented fault is
  awarding on rule ORDER over evidence strength, so a new early gate would risk
  preempting good landings elsewhere.
- **`chrome-none` fail-open closed** (was called a merge blocker in review).
  `seen == 0` is produced BOTH by a landmark-free document and by an enumeration
  that raised before yielding its first item. The cap and deadline paths examine
  an item before breaking so they report `seen >= 1` and were already safe; the
  exception path was not. It always knew it had failed and threw that away to a
  log line. Now carried as `LandmarkScan.exhausted`, defaulting False.
- **Empty tree no longer announces failure.** IMDb played the not_found tone
  twice against a buffer holding one chunk and zero nodes, then landed correctly
  four seconds later off its own fresh documentLoadComplete. Zero nodes means the
  buffer is not built, not that the page is empty. Capped at 2.5 s to the tone
  (Casey's call), with three looks inside that window — affordable only because
  an empty walk costs 2-4 ms.

### The lesson from this round

**Two plausible mechanisms were argued at length before anyone read the decision
trace.** The trace was already on disk, and it named the function outright. The
perf finding that anchored my wrong theory was real and independently confirmed
— `NVDAObjectAtStart` IS 60-98% of those walks — which is exactly what made it
seductive: a true fact about the page, doing no work in the argument. *A correct
observation is not a diagnosis.* DEBUGGING.md already says logs before theories;
the failure was reading the perf log (shape) and not the decision trace (choice).

### Open, unchanged and still worth doing

The perf work below is untouched and still the biggest win. The field-stack probe
is written, committed, and UNRUN at `probes/field_stack/`, with kill criteria
fixed in advance — build with `python probes/build_probe.py field_stack`, trigger
with NVDA+shift+f, grep `[TMTS probe-fields]`. Note gotcha (g) in that work:
`NVDAObjectAtStart` also feeds `_in_scope`, so the object fetch may only become
LAZY on the identity path, never removed outright.

Two smaller ones surfaced in review, both real, neither started:

1. ~~**The 60-char preview makes `_EDITORIAL_DISCLOSURE_MAX_CHARS = 300` dead code
   at runtime.**~~ **DONE, same session.** Promoted to a walk-time `is_disclosure`
   flag computed over the FULL chunk text, matching `is_caption` /
   `is_boilerplate`, plus a `full_length` parameter so the preview fallback can
   still apply the length guard (the precedent is the byline filter). It cut both
   ways as predicted: phrases past char 60 were invisible, AND a long genuine
   lede whose first 60 chars contained a disclosure phrase was chrome-flagged
   with no length protection. Note the trap this nearly repeated — every
   cascade-level test can hand-set the flag, so `tests/test_tree_summary.py` now
   drives `_node_for` directly and was CONFIRMED to fail when the walk-time
   computation is deleted. Verified live on simplyrecipes.
2. **Counts are still identity-scoped on `chrome-pos`** (~630 ms), so counts and
   walk can describe different trees. FORM is the intent that moves keyboard
   focus, which is why it matters.

## 2026-07-18 — a wrong-answer cache, a regression from fixing it, and four review rounds

All of today's work is on branch `scope-hardening` (4 commits). **`main` is untouched
at v1.0.13.** A first, dead design is preserved on `chrome-pos-attempt` — read its
commit message before ever rebuilding it. 260 tests.

### What shipped to the branch

1. **`_in_scope`'s memo was a WRONG-ANSWER bug.** `{id(obj): bool}`, no strong
   reference, so recycled CPython addresses produced false hits. Reproduced against
   the old code: after 100 nav chunks, all 100 following CONTENT chunks answered
   out-of-scope. That empties `main_nodes`, trips the unscoped fallback, and is why
   the symptom always read as "the identity check unreliably fails."
2. **`[TMTS walk-phase]`** — per-call-site timing. This ended the guesswork and found
   TWO different bottlenecks: on chrome pages the parent chains are ~92% of the walk;
   on big `main-pos` pages `NVDAObjectAtStart` is ~98% and the walk truncates. Only
   measurement separated them.
3. **`_scope_looks_depleted`** — the old net only fired when the scope filter returned
   NOTHING. deadsimpletech kept 3 of 16 nodes, all chrome, and discarded a 1439-char
   article; the net stayed shut and the user got silence.
4. **`chrome-pos`** — positional chrome exclusion, bounded by `trust_boundary`.
5. **`chrome-none`** — skip the parent walk entirely on landmark-free documents.
6. **The focus-move path** now uses the walk's real scope decision.

### The three things worth remembering

**A probe can be hollow.** A probe reported `ordered=True` on 15 of 15 pages and was
presented as the evidence that made bounded trust buildable. It was worthless: NVDA
seeds each landmark search from the previous match's start offset, so nondecreasing
starts are guaranteed a priori and `ordered=False` could never have occurred. *When a
probe comes back unanimous, ask whether it could ever have come back the other way.*

**Fixing a bug can remove an accidental optimization.** The broken cache's false hits
were short-circuiting the parent walk. stevequayle.com: 113 chunks at ~10.7 ms with the
bug and a good landing; 16 chunks at ~129 ms with the fix, truncated, NO LANDING. Casey
caught it, not me — and I had seen `cache_hits=0` hours earlier and read it as "useless"
rather than "only ever working by being wrong." `chrome-none` recovered the speed
honestly (113 chunks, no truncation, 2778 ms to 1761 ms).

**Go to NVDA's source, and read it yourself.** Two designs died on beliefs about NVDA
that turned out false, both caught by reading real source. Note that the installed
NVDA's `library.zip` holds `.pyc` only — `marshal.loads(data[16:])` then `dis.dis`
works, and reflects the NVDA actually running on this machine rather than master.

### Open, in the order I would take them

1. **[SUPERSEDED 2026-07-18 evening — WRONG MECHANISM AND WRONG FIX. See the entry
   at the top of this file before acting on any of it. The cause was
   `_find_content_section_landing` scanning without a distance bound; the
   purchase-vocabulary fix proposed here was rejected and NOT implemented.]**
   **Purchase/licensing boilerplate beats real content.** vovsoft product pages: two of
   four landed on a 387-char "To receive license key..." blurb instead of the product
   description (131/178 chars). Mechanism is the documented rule-order fault — any
   paragraph 200+ chars wins immediately, so shorter genuine content must clear the
   weaker cluster/hero gates and sometimes doesn't. Fix at the CLASS level by extending
   `_looks_like_editorial_disclosure` to purchase/licensing vocabulary; this is every
   software download page, not one site. **Start here next session.**
2. **Cross-origin consent iframes fire their own landing.** BBC spoke the same paragraph
   twice 1.63 s apart; radiotimes read a cookie-consent dialog before the article.
   `url=''` fired 31 times in one day. CLAUDE.md's assumption that an iframe resolves to
   the MAIN page's TI/URL does NOT hold for cross-origin frames under Firefox site
   isolation — they get their own TreeInterceptor and no URL. Needs an NVDA-source
   answer for "is this the top-level document" before coding.
3. **Counts are still identity-scoped on `chrome-pos`** (641 ms on stevequayle,
   `counts_trunc=True`), so counts and walk can describe different trees. FORM is the
   intent that moves focus, which is why this matters.
4. **Stale positional ranges.** Captured before a walk that can run ~2 s while the buffer
   re-renders; offset comparisons don't raise, so the tri-state never fires.
5. **Before any tagged release:** Fable found three wirings that pass tests while
   sabotaged (the objectless-chunk rejection, the focus filter, the `positional_hits`
   increment) because they sit inside the NVDA-bound walk. Pin them by extraction. Also
   `_document_has_no_landmarks` has never been reviewed — it was written after round 4.

### Verified fact worth not re-deriving

In `nvdaHelper/vbufBase/storage.cpp`: `nextNodeInTree(TREEDIRECTION_FORWARD)` goes to
`firstChild` when present, else up and to `next` — PRE-ORDER, so an ancestor is always
emitted before its descendants. `findNodeByAttributes` reseeds via
`locateTextFieldNodeAtOffset`, which returns the TEXT LEAF. So every otherwise-eligible
landmark skipped because of the reseed is a DESCENDANT of an emitted one. Both reviewers
confirmed independently; Fable checked at the release tag matching the installed
2026.2beta7.

## 2026-07-14 (rest of the day) — the trigger was the real bug all along

The morning's perf work (below) was real but secondary. Two much bigger bugs were
underneath it, and BOTH were invisible to every test we had.

### 1. The add-on was speaking a paragraph other than the one it landed on

7 of 42 landings in an 83-page soak. The classifier was often CHOOSING CORRECTLY
and the user still heard something else: the right WFAA lede chosen, a Cincinnati
Reds sports headline spoken; a recipe lede chosen, "We're loading your content,
stay tuned!" spoken; a real headline chosen, a URL slug spoken.

Cause: we capture a TextInfo per node during the walk and speak it afterwards.
The walk takes 1.5-2 s, and on a hydrating page NVDA rebuilds the virtual buffer
DURING that window, so positions captured early are already stale by the end.

**The retry is NOT a fix for this, and believing it was cost a whole build.** The
buffer drifts DURING the walk, so a re-walk races exactly the same way. The
intermediate build (guard, no re-anchor) turned wrong-text into SILENCE.

The fix is to stop anchoring to an offset: verify the captured position still
holds the chosen paragraph, and on drift RE-FIND IT BY TEXT
(`TextInfo.find`, verified in NVDA source: returns bool, repositions to match
start). Costs one search instead of a second walk.

**This also explains silent landings**: a stale position that expands to an empty
range makes `speakTextInfo` neither raise nor speak.

Watch this get exercised harder now that the trigger fix has doubled the number of
loads that reach detection: on a REUSED TreeInterceptor `isReady` stays True
through the re-render, so the readiness poll never engages and detection can walk
a buffer still holding the PREVIOUS page.

### 2. The add-on ran on 9 of 31 page loads

Everything we ever fixed only matters on loads where the add-on runs. It was
silently ignoring two thirds of them. This is why pages "needed a refresh" all day.

Both false beliefs are now corrected in CLAUDE.md and SPEC.md with source citations:
- `event_treeInterceptor_gainFocus` CANNOT fire in a GlobalPlugin, on any version.
  0 firings in 31 loads is exactly what NVDA's source predicts. Deleted.
- A TreeInterceptor is bound to an accessibility-tree ROOT, not a document. NVDA
  REUSES it across navigations and the URL changes in place underneath it. The
  "same TI → skip" gate was therefore eating real navigations. The URL is the
  document identity.

Chrome/Edge are affected identically (`ChromeVBuf` inherits the Gecko buffer and
overrides neither `isAlive` nor `documentConstantIdentifier`), which matters
because most store users are not on Firefox.

### Things that were nearly expensive mistakes

- **A briefly-lowered `WALK_NODE_LIMIT` (1000 → 400) silently degraded landings and
  the page got FASTER while doing it.** The cap counts RAW CHUNKS WALKED, not
  content nodes KEPT; GitHub turns 400 raw chunks into ~195 in-scope nodes and its
  README landing sits at ~201, so the walk was starved and the page landed on a
  commit message. Only reading the landing text aloud, plus the log naming WHICH
  limit fired, caught it. **The clock must be the only thing that truncates.**
- **A fixture that PASSED against unfixed code.** The first IMDb test put the next
  heading 3 nodes after the plot summary instead of 31, so the hero gate fired and
  nothing reproduced. Fixtures are a model of the page, not the page.
- **Two CDP-driven Chrome runs produced garbage** and nearly sent us chasing a
  phantom "Chrome is broken" bug. Chrome focuses the ADDRESS BAR on a blank tab, so
  focus never entered the document, NVDA never built a buffer, and every page timed
  out the readiness poll. Casey caught it by ear — he heard the omnibox being read.
  **Only real browsing is trustworthy here.**

### On second opinions

Fable and Codex were each given the same problems, independently. Both corrected me
on things I was confident about:
- Both REJECTED the cross-page "boilerplate is what repeats" idea (see CLAUDE.md for
  why; the argument that settled it is that a blind user can learn a consistent
  wrongness but cannot learn a moving target).
- Codex read the actual NVDA node trail and killed BOTH my IMDb theory and Fable's:
  the "Clip" titles end in QUESTION MARKS, so the sentence-strict pass rightly keeps
  them, and the hero gate fails on lookahead DISTANCE, not heading absence. The
  lead-section gate is Codex's design.
- Both independently named the same structural fault: **the cascade rewards rule
  ORDER over evidence STRENGTH.** Still unfixed. It is the next real piece of work.

The pattern worth keeping: ask the model that will go read the source, and give it
the raw log rather than my summary of it.

## 2026-07-14 (seventeenth round) — main-thread freeze on long pages

Found by reading the perf log, not from a user report. The walk was
freezing NVDA's main thread for 5-12 seconds on long pages, still
happening as of 07:02 that morning (biblegateway.com Isaiah 51-66: 936
chunks, 6261ms walk). `WALK_NODE_LIMIT` was 1000 with NO wall-clock
limit, and the comment above it said "tune after we measure on real
pages." We had measured; nobody had gone back and tuned it.

Three changes, all in `tree_summary.py`:

1. `WALK_NODE_LIMIT` 1000 -> 400, plus a new `WALK_TIME_BUDGET_SEC = 1.5`
   checked per-iteration in the walk loop. The TIME budget is the real
   guard: per-chunk cost varies ~6.4ms to ~8.2ms across sites, so a node
   cap alone cannot bound the freeze. The node cap is now just a backstop.

2. The unscoped fallback no longer re-walks the document. It used to call
   `_walk_main_nodes` a second time with an "unscoped sentinel", which
   doubled detection time on exactly the slowest pages — hearthstoneaccess
   changelog spent 3679ms on a scoped walk that found nothing, then 3614ms
   re-walking the identical 361 chunks. The walk now collects every node it
   sees into `all_nodes` regardless of scope, and the fallback is a list
   assignment. Removed `_UNSCOPED_SENTINEL` and its branch in `_in_scope`,
   which became dead.

3. Perf line: `fb_raw_seen=` replaced by `all_nodes=`, and a new
   `truncated=` field says whether the walk stopped on the cap/budget
   rather than reaching the end of the document. New `[TMTS walk-truncated]`
   debug line.

Decisions and things to watch:

- **Truncation is a real trade, taken deliberately.** On a 900-paragraph
  page we now choose the landing from a partial view. This is safe because
  landing indices are always near the top (the correct BibleGateway landing
  was `main_nodes[7]`), but the TAIL of a long document no longer feeds the
  classifier's counts. A page whose character of content changes after
  paragraph 400 could in principle classify differently. Judged acceptable:
  such pages are overwhelmingly ARTICLE either way, and a six-second freeze
  is a certain harm against a speculative one.

- **The notice-keyword regex had to be split.** The walk now sees
  out-of-scope chunks, and a status keyword sitting in a cookie banner or
  footer must not boost NOTICE confidence on a page whose scope filter
  worked fine. So there are two flags: `notice_match` (in-scope only, the
  normal path) and `notice_match_all` (whole document), and the fallback
  path swaps in the latter because there main_nodes IS the whole document.
  Getting this wrong would silently change NOTICE classification on every
  page with a cookie banner.

- **`all_nodes` completeness depends on the out-of-scope-tolerance bail.**
  That bail can truncate `all_nodes` early, but it only fires AFTER at
  least one in-scope node exists — in which case `main_nodes` is non-empty
  and the fallback never runs. So `all_nodes` is always complete when it is
  actually used. If anyone changes that bail condition, re-check this.

- **NOT fixed, deliberately deferred:** the identity-based `_count_in_scope`
  parent-chain walk still runs on `chrome`-scope pages (no `<main>`, no
  single `<article>`) and cost 8047ms of the 11958ms total on the
  Hearthstone deckbuilder. Extending positional counting to that case is
  the right fix and touches the scope machinery, so it goes in its own
  round rather than riding along with a perf change that needs real-world
  soak time first.

- Unit tests can't cover any of this (the walk needs NVDA). The 130-test
  suite passing only proves the classifier and landing finders are
  untouched. Verification is soak testing against the perf log: watch for
  `truncated=True` and for total times dropping under ~2s on the long
  pages listed above.

### Same-day corrections found by soak testing (read these, they are the lesson)

**1. WALK_NODE_LIMIT=400 was wrong and silently degraded landings.** Caught
on github.com/Community-Access/accessibility-agents. The cap counts RAW
CHUNKS WALKED, not content nodes KEPT. GitHub's repo page turns 400 raw
chunks into only ~195 in-scope nodes (the rest is chrome: fork/branch/tag
counts, file browser, commit messages), and the README landing paragraph
sits at node ~201. So the cap starved the walk before it reached any
content, `find_article_landing` fell through the "very substantial" gate to
the cluster gate, and the page landed on a COMMIT MESSAGE. Meanwhile GitHub
walks at ~4ms/chunk, so the 2s clock had not come close to firing — the
backstop was doing all the truncating and the real guard sat idle. Restored
to 1000. **The time budget must be the only thing that ever truncates.**

The meta-lesson: I changed two levers (node cap AND time budget) in one
pass, and only the time budget was the right one. The page got FASTER with
the bad cap and landed somewhere plausible-sounding. Nothing but reading the
landing text out loud, plus the `truncated=` field naming WHICH limit fired,
would have caught it. If that field had just said `truncated=True` without
saying which limit, this ships broken.

**2. WALK_TIME_BUDGET_SEC 1.5 -> 2.0.** 1.5s was tuned against pages whose
content starts at the top (BibleGateway, a long newsletter). It had no
deep-content page in its sample. On GitHub the landing came in at node 201
of the 226 kept — about 25 nodes of headroom. At 2.0s that headroom is 140.
The failure mode being bought off here is severe and SILENT: truncate before
the content starts and we return no landing, which is indistinguishable to
the user from a page with nothing on it (two low beeps). A page that used to
work would quietly stop working.

### Also fixed: the trigger dropped page loads on the floor

`_maybe_fire` bailed whenever the TreeInterceptor wasn't ready, with no
second chance — and `event_treeInterceptor_gainFocus` does not fire on this
NVDA build, so nothing picked it up later. `documentLoadComplete` fires when
the DOM finishes loading, which is NOT when NVDA finishes building the
virtual buffer; on a big page the buffer lags. Observed on biblegateway:
documentLoadComplete fired twice (07:40:33, 07:40:47), both with a real
Gecko_ia2 TI whose isReady was False, both dropped. The add-on did nothing,
silently — no tone, no landing, no signal it had even tried. Casey pressed Z
to compensate, then refreshed, and only the refresh auto-landed.

Now: a bounded readiness poll (250ms x 12). Re-reads the TI from the OBJECT
each attempt, since NVDA may swap it. Gives up silently after 3s.

**Deliberately does NOT poll when the TI is None** (only when it exists but
isn't ready). None is the Thunderbird case — every message preview fires
documentLoadComplete with a null TI. Polling there would either burn cycles
for nothing or, worse, eventually start auto-landing inside email, and email
detection is deferred and undesigned.

**Caveat: this fix is UNVERIFIED.** The poll never fired on any load we
tested afterwards (the TI was ready immediately every time). It is backed by
code reading and one observed trace, nothing more.

### Open: landing speech gets eaten by page-placed focus (NOT a regression)

Intermittent. On biblegateway the caret moves to the right paragraph and
NOTHING is spoken; NVDA announces `button, collapsed, opens list, Lexham
English Bible Open menu` instead. Same page, same build: failed once,
worked once.

A `[TMTS speak-probe]` diagnostic (still in the code, remove when fixed)
proves we hand NVDA a valid 69-char range every time —
`'There is no one who guides her among all the children she has borne,\n'`.
So it is NOT an empty or stale captured position, which was my first theory
and was wrong.

What actually happens: the page moves focus to its menu button while our
walk is blocking NVDA's main thread. NVDA's focus announcement carries an
implicit speech cancel and eats our landing. We call `cancelSpeech()` then
`speakTextInfo()`, so we speak FIRST and get cut off — the exact inverse of
what SPEC intends ("the add-on's own speak call naturally cuts off whatever
NVDA was saying").

This is PRE-EXISTING, not caused by today's work. The race window is however
long we block the main thread: it was 6.3s, it is now 2.1s. Today's changes
make this bug LESS likely, not more.

Likely fix (do NOT write it on one observation — collect samples first):
defer the `speakTextInfo` by one event-loop turn so any focus announcement
queued during the walk flushes first and ours lands last. Sequencing
`speakTextInfo` against NVDA's queued focus events is an NVDA API question —
per global CLAUDE.md, look it up in NV Access docs/source, do not recall it.

## 2026-07-06 (sixteenth round) — participle bylines (Phoronix)

Soak report: phoronix.com article landed on the 85-char mixed-case
byline "Written by Michael Larabel in Arch Linux on 14 June 2026 at..."
one paragraph above the lede. The page is positionally scoped (single
<article>, no <main>), so the fast path took the FIRST substantial
paragraph — and the round-13 byline filter only catches ALL-CAPS "By "
bylines, a documented gap that bit sooner than expected.

Fix: `_looks_like_byline` now also matches participle openers
("Written/Posted/Published/Story/Reported/Reviewed/Words/Photo(s)/
Photographs by " + capitalized name), mixed case allowed — those forms
essentially never open narrative prose, unlike bare "By ...". Guards:
lowercase after "by" stays ("Written by hand, the letter..."), and a
120-char cap on the FULL paragraph length (passed as full_length from
_is_chrome_paragraph — the preview is truncated at 60, so len(preview)
alone can't enforce the cap) keeps long book-review ledes like "Written
by John Steinbeck in 1939, ..." landable. Worst case on a short
review-lede false positive: landing moves one paragraph later, never
onto chrome.

Two new tests (130 total): detector positives/negatives + the scoped
Phoronix fixture landing on the lede.

## 2026-07-06 (fifteenth round) — editorial URLs block FORM (thurrott podcasts)

Soak report: thurrott.com podcast episode page dispatched FORM(0.90) —
the new intent-in-log line paid for itself immediately — and landed on
the H1 via the form-title path instead of the 120-char episode
description. Why no existing block engaged: 10 scattered inputs (comment
box, login, search, newsletter) cleared STRONG_FORM_INPUT_COUNT, the
site exposes no <article>, the description is under 200 chars, and the
long comment paragraphs aren't adjacent (no massive duo, no 3-cluster).

Fix: `has_editorial_url` — URL matches ARTICLE hints AND not FORM hints
→ FORM blocked. Mirror image of the existing /register escape hatch.
Added "/podcast" to the ARTICLE URL hints. /blog/contact-style URLs
(match both) stay FORM-eligible. This would also have caught Armstrong
(/world-news/), giving that page two independent guards now.

Once ARTICLE, the hero gate lands exactly on the description (>=100
chars, H1 already seen, "Tagged with" heading in lookahead). Three new
tests (128 total).

Also confirmed from the log while sweeping: Fox/Roku music-videos page
landed correctly (article 0.70, 437-char lede) — the four adjacent
300-400 char body paragraphs make that class safe without URL help.
Casey's /books/337384 report has NO detection record in either log —
most likely opened in a background tab (tab switches never trigger,
locked behavior); waiting on his description before treating it as a bug.

## 2026-07-06 (fourteenth round) — walk skipped paragraphs after media-heavy blocks

Soak report: pattysworlds.com homepage landed on the King Campbell
paragraph; Casey expected "Watch your step as you walk upon this new..."
— the paragraph directly before it. The Wayback snapshot proves the page
order (welcome h3 with inline logo image, then Watch-your-step p, then
King Campbell p), but NVDA's walk yielded the h3 chunk and the King
Campbell chunk with NOTHING between: the walk itself skipped the
paragraph, not our filters (both neighbors were kept, and positional
containment is monotonic).

Root cause hypothesis (fits three incidents): the walk loop did
collapse(end=True) + move(UNIT_PARAGRAPH, 1) after every chunk. When a
chunk's end offset lands exactly on the next paragraph's start boundary
— which happens after link/image-heavy blocks — that pair advances TWO
paragraphs. Same signature on the X page (main tweet text missing right
after the avatar/author block) and dailymail (headline missing after the
hero media).

Fix: expand directly at the collapsed end position; only force a
move(UNIT_PARAGRAPH, 1) when compareEndPoints shows the expansion made
no forward progress vs the previous chunk start (that also terminates
the loop at document end when move returns 0). WALK_NODE_LIMIT still
bounds the loop. Cost per chunk: one copy + one compareEndPoints.

Also added a [TMTS walk-drops] debug line: previews of up to 10 chunks
dropped by the scope filter AFTER the scoped region started producing
nodes. Mid-region drops are anomalies; this line distinguishes
"scope filter ate it" from "NVDA never yielded it" the next time a
paragraph goes missing.

NVDA-dependent, not unit-testable. VERIFICATION PENDING: Casey revisits
pattysworlds.com on this build — expected landing is now the
Watch-your-step paragraph (170 chars, cluster gate with the 259-char King
Campbell paragraph next). The X page main-tweet text may also reappear.
If the landing does NOT change, read the walk-drops line before further
theorizing.

## 2026-07-06 (thirteenth round) — promo/byline chrome + massive-duo FORM block

Two soak reports, two general fixes:

1. dailymail.com article landed on the "• READ MORE: ..." promo box
   (109 chars) — it and the all-caps byline right after it (51 chars)
   formed a fake cluster that won gate 4. New chrome filters in
   `_is_chrome_paragraph`: `_looks_like_promo_teaser` (ALL-CAPS
   READ MORE/RELATED/SEE ALSO/DON'T MISS labels, optional leading
   bullet; case-SENSITIVE so "Read more about..." prose survives;
   EXCLUSIVE deliberately excluded — sites open real ledes with it) and
   `_looks_like_byline` (starts with exactly "By " + >=70% of letters
   uppercase; "By NASA's estimate..." stays safe; mixed-case "By John
   Smith" is a known deliberate gap). With both filtered, the cascade
   reaches the real 226-char lede. Note: the page's headline is not in
   NVDA's walk at all on dailymail (no H1 exposed before the body), so
   the lede is the right achievable landing.

2. armstrongeconomics.com blog post classified FORM (landed on the H1
   via the form-title path) because: WordPress theme exposes no
   <article> (editorial block off), the 6-input newsletter widget
   cleared STRONG_FORM_INPUT_COUNT, and the two 618/595-char body
   paragraphs missed the 3-paragraph cluster bar. New classifier block:
   `_has_massive_paragraph_duo` — two ADJACENT non-caption/boilerplate
   paragraphs >= 200 chars each block FORM, with the same URL escape
   hatch as the <article> block (/register, /signup, ... stay FORM) so
   Zoom registration pages keep their approved title-landing behavior
   even if their description chunks into multiple big paragraphs.

Also: the "moved caret" debug line now records intent+confidence — the
Armstrong diagnosis needed process-of-elimination to determine FORM had
fired, which this would have shown directly.

Six new tests (125 total): promo detector, byline detector, Daily Mail
fixture lands the lede, Armstrong fixture classifies ARTICLE, register-
URL massive-description page stays FORM, duo adjacency requirement.

## 2026-07-06 (twelfth round) — prose-run landing for X/Twitter status pages

Soak report: x.com/MarioNawfal/status/2074138801208012984 landed on the
generic "Post" heading. Two findings from the debug log + a Chrome DOM
inspection:

1. It's a quote tweet, and the MAIN tweet's text never appears in NVDA's
   UNIT_PARAGRAPH walk at all (the known sparse-walk exposure limitation;
   nothing our finders can do about text that isn't in the buffer).
2. The QUOTED tweet's text IS in the walk — as three consecutive short
   lines (19 + 34 + 61 chars). Every line but the last is under the
   50-char landing bar, so the cascade fell through to the directory
   redirect, which picked the lone "Post" heading.

General fix, no X-specific code: a "prose-run" gate between the hero
shortcut and the largest-paragraph fallback. A run of >=2 consecutive
non-chrome paragraphs, each >=15 chars, totaling >=100 chars, lands on
its first line — but only when >=2 lines AND at least half the run end
like sentences, and the run starts after a heading. Sentence-end density
is the load-bearing discriminator; pure length rules are defeated by the
two directory-redirect fixtures themselves: Montgomery's nav run (six
Title Case rows, 125 chars, zero sentence ends) and signed-in Zoom's
form-label run (sixteen labels + one "?" question = 1 ender in 17 lines).
Pre-heading runs are rejected for the same reason the hero gate requires
seen_heading (cookie banners / publisher disclaimers).

New walk-time flag `MainNode.ends_sentence` (set via `web.ends_like_sentence`
over the FULL chunk text — the terminal '.' of a 61-char line sits past
the 60-char preview cutoff, same trap as is_caption/is_boilerplate).
Fixture fallback: lines <=60 chars re-check the preview.

Six new tests (119 total): the Mario fixture lands idx 7, nav-run reject,
form-label-run reject, pre-heading reject, preview fallback, and the
ends_like_sentence detector itself. Montgomery and collapsed-Zoom
directory-redirect tests unchanged and still green.

## 2026-07-06 (eleventh round) — restored-position gate needs the seen-URL signal

First soak-test report: halturnerradioshow.com article got no auto-landing;
Z worked. The debug log showed the tenth-round gate misfiring on a FRESH
navigation: "caret mid-page (restored position) — skip". On that site the
browse cursor initializes at node 1, not at the document's first character,
so "caret past first char" alone is NOT a reliable restored-position signal.

Fix (general, no per-site code): require BOTH signals. Back navigation by
definition returns to a URL already visited this session, so the gate now
keeps a session-scoped `_seen_urls` dict (url -> monotonic timestamp,
membership checked BEFORE recording, pruned to newest 250 at 500 entries)
and only skips when caret is mid-page AND (url seen before OR the url has
a real anchor fragment — `#section` yes, `#/route` SPA fragments no, so
Zoom's `#/registration` stays unaffected). First visits now always land
even when the caret starts below the top.

The retry's companion check had the same latent bug: it abandoned when the
caret was past document-top, which on below-top-caret pages would have
abandoned EVERY retry even with the user untouched. It now captures the
caret textInfo at scheduling time and abandons only when the caret has
MOVED during the 1500 ms wait (compareEndPoints != 0). Errors resolve to
"not moved" → proceed.

Accepted trade-off: browser session restore after an NVDA restart looks
like a first visit (empty `_seen_urls`), so a restored mid-scroll tab that
fires documentLoadComplete will land. That matches pre-gate behavior and
is rare; not worth persisting URL history to disk.

Not unit-testable (event/caret plumbing, no pure-function surface); the
113 existing tests are unaffected. Verified via the debug log trail:
lines "PROCEEDING ... halturner" followed by the gate skip, then the Z
scan landing correctly on "Cuba has been hit by another island-wide...".

## 2026-07-06 (tenth round) — restored-position gate (Back navigation)

Casey: Back to search results / book lists restores the reading position,
and the addon's re-landing yanked him to the top — the opposite of
guardrail #1. Fix: `_caret_is_mid_page(ti)` — when a load event arrives
and the browse cursor is past the document's first character, skip
detection entirely (position was restored: Back nav, anchor link,
session restore). Fresh loads start at the top, so normal landings are
unaffected. Same check added to the 1500 ms retry (user arrowing during
the wait = manual takeover; abandon). Double-Z keeps bypassing (explicit
request). Errors in the caret query resolve to "proceed" so a broken
caret can never cause permanent silence.

Also LOCKED per Casey: alt-tab / tab-switch must NOT auto-trigger. The
2026.2beta5 event gap (below) is therefore the desired behavior, not a
bug — do not hook event_gainFocus to "fix" it.

## 2026-07-06 (ninth round) — confirmation landing confirmed working; one open finding

Final state verified in the live log: a real load of Zoom's confirmation
page classifies NOTICE and lands on the H1 "You have successfully
registered" (this render carries NO paragraph >= 30 chars — the page's
text is the heading plus <30-char fragments, so find_notice_landing's
heading fallback is what fires, and the earlier Z "nothing to land on"
was truthful). Casey confirmed: "perfect".

OPEN FINDING for a future round: event_treeInterceptor_gainFocus NEVER
fired once across all of today's NVDA 2026.2beta5 debug logs — every
trigger was documentLoadComplete. Automatic landings therefore only
happen on real loads/refreshes; switching to an already-open tab (or
restarting NVDA with a tab open) triggers nothing. Candidate fix:
reconsider hooking event_gainFocus with the TI-identity + landed-URL
suppression gates — originally rejected when detection cost seconds, but
detection now runs ~100-300 ms after the positional-scoping rework.
Needs a probe on 2026.2 (does treeInterceptor_gainFocus fire on stable
2026.1? was it ever firing?) before changing hooks.

## 2026-07-06 (eighth round) — Z's 50-char bar strands users on short-content pages

Casey's confirmation-page alt-tab test ran BEFORE the notice-fix build
was active (old log shows no TMTS activity for it), but it exposed a real
Z gap anyway: on Zoom's confirmation page the longest line is 44 chars,
under Z's LANDING_MIN_PARAGRAPH_CHARS=50 bar, so Z reports "Nothing else
to land on" with the message right below the cursor.

Fix in find_next_content_landing: if NO paragraph anywhere in main_nodes
clears the 50-char bar (short-content page), rescan below the cursor at
the notice bar (_NOTICE_LANDING_MIN_CHARS=30). Pages that have 50+ char
paragraphs anywhere keep the strict bar, so end-of-article Z behavior
(deliberately reporting nothing rather than hopping onto related-link
rows) is unchanged.

## 2026-07-06 (seventh round) — confirmation pages: NOTICE's zero-form gate was too strict

Post-registration, Zoom's "You have successfully registered" page got the
two-beep not-found (Casey read it as an addon error — it wasn't; both
attempts classified UNKNOWN and gave up cleanly). Log: 6 nodes, H1 32
chars, keyword match available ("successfully"), but forms=1 — the "Add
to calendar" widget counts in NVDA's formField quick-nav class — and
_classify_notice required form_input_count == 0.

Ironically surfaced BY the perf fix: before it, this page's forms would
have miscounted as 0 and NOTICE would have fired. Correct counts exposed
the too-strict gate.

Fix: keyword-matched NOTICE (0.85) now tolerates form_input_count <=
NOTICE_KEYWORD_MAX_FORM_INPUTS (2); the shape-only 0.65 path keeps the
zero-fields requirement so small real forms (login pages) still can't
classify as notices. Landing on the page: find_notice_landing → first
>=30-char paragraph → "Please check the confirmation email sent to..."
with the H1 one arrow up.

## 2026-07-06 (sixth round) — FORM focus jump was grabbing the header language picker

Perf rework verified live: counts went 930-1240 ms → 4-5 ms
(scope=main-pos), total detection ~1.5 s → ~0.3 s, and FORM finally
fires on Zoom (forms=10). But the FORM path's focus landed Casey on
"Language English" — `set_focus_on_first_form_input` focused the first
formField in the WHOLE document, and Zoom's header language-picker
combobox comes before the form.

Fix: the function now (a) filters candidates positionally to the <main>
range (rebuilt via `_find_main_landmark`, ~10 ms) and (b) prefers real
"edit" quick-nav items over the broader formField class (which includes
buttons/pickers), falling back to formField-in-main for edit-less forms.

Also confirmed live: when Zoom renders the OPEN layout (description
visible), the body cluster blocks FORM → ARTICLE lands on the
description paragraph ("Whether you're starting your business..."), which
Casey confirmed hearing on a revisit. The page genuinely oscillates
between layouts; each state now gets the right treatment.

## 2026-07-06 (fifth round) — positional scoping for counts; kills the 1 s+ parent-walk tax

Casey signed off on reworking the counts phase ("people won't wait").
Perf lines showed counts=930-1240 ms per pass on Zoom (twice per visit
with the retry), and the counts were WRONG anyway (forms=0 on a 7-input
page) because the per-item parent-chain `_in_scope` check can't confirm
`<main>` membership on many sites.

What changed in tree_summary.py:

- `_find_main_landmark(ti)` returns `(main_obj, main_range)` in one
  enumeration; `main_range` is the landmark quick-nav ITEM's textInfo
  (same coordinate-space trick as `_single_article_scope_range` — never
  `obj.makeTextInfo`, that's the documented trap).
- New `_count_in_range(ti, type, scope_range, limit)`: positional counts
  (item.textInfo START inside range), `_COUNT_SCAN_LIMIT=300` items
  scanned per type, items without textInfo counted inclusively. With
  `scope_range=None` it's a plain capped enumeration (document-wide).
- Scope matrix, ONE range shared by counts and walk: `main-pos`
  (positional, the new fast path), `main-id` (main present, range failed
  → old identity path), `article` (unchanged), `chrome` (unchanged).
- Fallback consistency: when the scoped walk comes back empty and falls
  to unscoped, AND the scoped counts were all zero (clearly bogus),
  counts are recomputed document-wide (`scope=unscoped-recount`).
  Non-zero scoped counts are kept — unscoped recounting would inflate
  them with chrome controls (NVDA's formField quick-nav includes
  buttons, so document-wide form counts on button-heavy pages are
  dangerous; the all-zero gate limits exposure to pages where we had
  nothing anyway).
- `positionally_scoped` stays article-only ON PURPOSE. Setting it for
  main-pos would bypass the hero/cluster landing gates on every page
  with `<main>`, re-landing on pre-H1 deks/disclaimers (PCMag case).
- Deleted `_find_main_landmark_obj` (superseded; the probe keeps its own
  copy).

Expected downstream behavior changes to watch during smoke testing:

- Pages where counts were previously zeroed by the identity failure can
  now classify FORM/APP (Zoom signed-in registration → FORM → announce
  "Webinar Registration" + focus First name, per Casey's "if you're
  hitting the register link you probably want to register"). The fresh
  open layout stays ARTICLE via the body-cluster block and lands on the
  description.
- counts= in the perf line should drop from ~1000 ms to low tens of ms
  on main-pos pages; judysdogblog-class 12 s freezes should vanish.
- main-pos pages whose identity walk used to WORK now walk positionally;
  chunk membership should match or improve (nav/footer excluded by
  position).

## 2026-07-06 (fourth round) — signed-in Zoom renders the collapsed tree FIRST

After the suppression fix, Casey still landed on the disability question —
but the log showed only ONE detection this visit: being signed in, Zoom now
renders the collapsed profile view immediately (name prefilled, Date & Time
and Description accordions CLOSED, H1 absent from the buffer). The
description text is simply not in the tree; no retry or suppression can
land on it. The tree: 36 nodes, one H2 ("Webinar Registration", idx 5),
one substantial paragraph (52-char question label, idx 24), copyright
correctly skipped.

Fix: the existing directory-page redirect in the largest-paragraph
fallback (lone substantial paragraph ≥5 nodes past the first heading on a
small page → land on the heading) already matched this shape except for
its node cap. Widened `len(nodes) <= 30` to `_DIRECTORY_REDIRECT_MAX_NODES
= 40`. Landing is now the "Webinar Registration" H2 — top of the form,
Description accordion one arrow up.

Watch for: pages with 31-40 nodes that USED to land on their lone
substantial paragraph now land on their first heading when the paragraph
is ≥5 nodes below it. That is the rule's documented intent (the lone
paragraph in that shape is usually a footer/address/label), but if a real
page regresses, tighten via shape, not via site.

## 2026-07-06 (third round) — SPA re-renders were yanking the cursor off good landings

Debug-level log from Casey's machine showed the real Zoom failure was NOT
the landing choice. Three detections ran on one page visit:

1. t=0: full tree (H1, date, description paragraphs 210/422/210/325/787).
   ARTICLE via body cluster, landed on the description. Correct.
2. t+9 s: Zoom re-rendered (signed-in profile swapped in, "Casey"/"Mathews"
   prefilled; Date & Time and Description collapsed into closed accordions;
   H1 gone from the tree). Fresh documentLoadComplete, NEW TI, same URL,
   past the 2 s cooldown → re-detection. Only substantial paragraph left
   was the 52-char "Do you consider yourself a person with a disability?"
   label → landed there. That's the mid-form jump Casey reported.
3. t+34 s: same again.

Fix: post-landing suppression. `_record_landing(url)` stamps URL + time on
every successful landing (both the FORM focus path and the caret path);
`_maybe_fire_ti` skips automatic detection for that URL for
`_LANDED_SUPPRESS_SEC` (120 s). Z clears the stamp (explicit re-request);
URL change lands normally. Trade-off: F5 refresh of the same URL within
120 s gets no auto-landing (Z covers it).

Also observed in the same log, documented but NOT changed (risk of broad
behavior shift mid-test): the counts phase and the walk can disagree on
scope. On Zoom, `forms=0 interactive=0` despite 7 real inputs because the
main-scoped `_iterNodesByType` enumerations discarded everything (the
known identity-based `_in_scope` failure) while `main_nodes` came from the
unscoped fallback. The summary the classifier sees is internally
inconsistent: unscoped nodes + scoped-to-nothing counts. Under-reporting
biases toward ARTICLE/silence (safe direction), but it means FORM intent
basically cannot fire on `scope=unscoped` pages. A future fix should count
totals during the same enumeration (free) and use them when the walk falls
back to unscoped, so nodes and counts describe the same tree.

## 2026-07-06 (later) — Rich-preamble forms land in browse mode, not on the first field

After installing the boilerplate fix, the hydrated Zoom registration page
classified FORM (7 inputs, strong signal) and the FORM path did what it
always does: `ui.message` the title, then focus the first input. On this
page the first input sits below an 81-char H1 and a ~2000-char description,
so Casey was "dropped in the middle of the reg form."

Fix: `web.form_wants_browse_landing(tree)` — True when any non-chrome
paragraph is >= VERY_SUBSTANTIAL_PARAGRAPH_CHARS (200). When True, the FORM
branch in `_handle_result` falls through to the normal browse-cursor
landing at `find_form_landing`'s index (first heading = form title) instead
of the focus jump. Bare forms (Google-Forms title + labels, logins) keep
the focus behavior — the 200-char bar is above any realistic field label
(Zoom's longest label was 112 chars).

Also diagnosed during this round:

- "The add-on didn't run" after install = the install needed NVDA's
  restart; once restarted, 1.0.9 was active (manifest verified, enabled,
  imports clean, zoom.us not excluded).
- The persistent perf log stopping on 2026-06-19 is NOT a bug: since the
  DEBUG gate was added, `_append_perf_line` only writes when NVDA's log
  level is DEBUG, and Casey's NVDA runs loggingLevel = OFF. Diagnostics
  on his machine need NVDA log level set to Debug first (NVDA menu →
  Preferences → Settings → General).

## 2026-07-06 — Legal footer boilerplate is never a landing (Zoom webinar shell)

Trigger: https://us02web.zoom.us/webinar/register/WN_e8hkN9vtSI2N-ITK2mW3iA#/registration
spoke "Copyright ©2026 Zoom Video Communications, Inc. All rights reserved."
instead of the page content.

Root cause (verified by fetching the page pre- and post-hydration): Zoom's
registration page is a React shell at `documentLoadComplete`. Before JS
hydrates, the ONLY paragraph clearing the 50-char substantial bar is the
footer copyright (69 chars). That line qualified as a hero paragraph →
ARTICLE at 0.65 → largest-paragraph fallback landed on it. Because the
add-on "acted," the 1500 ms hydration retry never fired. The hydrated page
(H1 title, 1958-char description, 7 form inputs) would have classified and
landed fine.

Fix (general, no per-site code): a legal-boilerplate detector
(`web._looks_like_legal_boilerplate`) joins the existing chrome family
(captions, tag lists, share payloads, a11y instructions). Signals: "all
rights reserved", copyright/© immediately followed by a 19xx/20xx year, and
the CCPA "do not sell (or share) my personal information" phrase. Each is
essentially absent from real prose; requiring the year next to
"copyright" keeps articles ABOUT copyright from matching.

Decisions worth remembering:

- Flag is computed at walk time over the FULL chunk text
  (`MainNode.is_boilerplate`), mirroring `is_caption`, because the
  "All rights reserved" tail commonly sits past the 60-char preview cutoff.
- `classifier._hero_paragraph_chars` skips boilerplate paragraphs by FLAG
  ONLY (no preview fallback there — classifier can't import detection.web
  without a cycle; tree_summary always sets the flag in production).
  Consequence: classifier fixtures must set `is_boilerplate=True` explicitly.
- The five duplicated skip-filter chains in detection/web.py were
  consolidated into `_is_chrome_paragraph`; the notice landing, form-landing
  paragraph fallback, and Z forward scan now apply it too (they previously
  had no chrome filters at all).
- The win on Zoom is indirect: filtering the copyright makes the shell
  produce NO landing → `_handle_result` returns False → the existing
  generic 1500 ms retry runs against the hydrated page. No timing tweaks,
  no Zoom-specific code.
- Left `_largest_paragraph_cluster` alone (boilerplate could theoretically
  join a body cluster, but only the ©-line matches the detector and footers
  don't sit mid-body; not worth the churn).

Not yet verified in real NVDA: whether Zoom's language-selector row merges
into a ≥50-char paragraph chunk in the shell buffer (it's a collapsed
dropdown, so probably hidden). If the shell still lands somewhere wrong,
check the `[TMTS]` debug lines for what chunk won.
