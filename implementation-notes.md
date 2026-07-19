# Implementation notes

Newest entries at the top.

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
