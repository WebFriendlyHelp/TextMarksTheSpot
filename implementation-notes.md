# Implementation notes

Newest entries at the top.

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
