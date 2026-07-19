# Next session prompt (paste into a fresh session)

We're picking up Text Marks the Spot on branch `scope-hardening` (main is still
v1.0.13, unmerged, so nothing on this branch is exposed to users). Read
CLAUDE.md, DEBUGGING.md, and the TOP TWO entries of implementation-notes.md
first. 301 tests pass; run them with `python -B -m pytest tests/` from the repo
root (the `-B` matters, see the harness traps below).

Last session shipped one correctness fix, ran a probe that finally answered a
question two earlier sessions got wrong, and found a merge blocker. Three
commits, unpushed: `f4dac67` (the `_in_scope` tri-state fix), `e9b0c35` (probe
plus results), `08a52ba` (docs, blocker record, disowned-citation cleanup).

## FIRST TASK: the chrome-none merge blocker. Decide it, then fix it.

`_document_has_no_landmarks` requires `seen == 0 and exhausted and
interactive_count > 0`. `exhausted` cannot mean what the docstring claims.
NVDA's `_iterNodesByAttribs` CATCHES the native exception from
`VBuf_findNodeByAttributes` and RETURNS, so a natively failed landmark search
is an ordinary empty completed generator. Confirmed empirically:

    _find_main_landmark(FakeTI([]))      -> seen=0, exhausted=True
    _document_has_no_landmarks(scan, 5)  -> True   -> chrome-none

`chrome-none` then skips chrome checking ENTIRELY, so navigation and footer are
admitted as content and the user can land in a menu. `tests/test_chrome_scope.py:621`
gives false confidence: it uses `raise_after=0`, which makes the exception
ESCAPE, and that is the one shape `exhausted` genuinely catches.

Two options, not decided. Casey leaned toward 2 but explicitly wanted it chosen
fresh rather than at the end of a long session:

1. Delete `chrome-none`, falling back to the identity chrome filter. Sound and
   simple. Costs real speed: stevequayle's walk is 84 ms with it, and the probe
   clocked over six seconds of uncached parent chains on that page without it.
2. Keep it, corroborated by the control field stack. On a `seen == 0` page,
   check whether the leading control run shows landmarks anyway; if it does the
   enumeration lied and the shortcut is refused. About a millisecond, so unlike
   the sampled COM check the reviewers proposed it can check EVERY chunk. Needs
   the backend gate below or it fails open on WebKit the same way.

Whatever you pick, the test that must exist is the NATIVE-SWALLOW shape: an
enumeration that yields nothing and returns normally must not activate any
landmark-free shortcut. Confirm it fails when the fix is removed.

## SECOND TASK: the guarded walk path (design already reviewed)

Replace the COM parent chain with landmark ancestry read from the leading
control run of `getTextWithFields()`. Two independent reviews approved this for
the WALK only, with four conditions. Probe evidence (4 pages, 153 chunks,
2026-07-19): the field stack never missed a landmark the parent chain found
across 48 landmark-bearing chunks, caught three the chain missed and was right
about all three, and cost 138.8 ms against the chain's 16,564 ms.

Question 1, the one that could have killed it, is SETTLED IN ITS FAVOUR from
`nvdaHelper/vbufBase/storage.cpp` read directly: `getTextInRange` emits its own
opening tag unconditionally and recurses into every child overlapping the
range, starting at `rootNode`, filter defaulted to NULL. The leading run is the
complete virtual-buffer ancestor chain. Presentation filtering happens later,
in `getEnclosingContainerRange`.

The four conditions, all of which change the design:

1. "No landmark in the stack" is NOT "content". Call it `NOT_IN_CHROME`. Three
   states required: definitive-chrome, definitive-not-in-chrome, and UNKNOWN
   (failed call, `''`/`['']`, no leading controlStart, malformed field,
   unsupported backend). `_role_level_from_fields`'s `had_field` is the
   existing precedent.
2. BACKEND GATE or it is fail-open. `field["landmark"]` is backend
   normalization, not a TextInfo contract. Gecko and Chromium populate it;
   WebKit's normalizer does not. The probe does not log `backendName`.
3. The two mechanisms are independent in TRAVERSAL ONLY, not labeling.
   `_normalizeControlField` and `Ia2Web._get_landmark` compute the same `next()`
   over the same `aria.landmarkRoles` set. If a browser misreports `xml-roles`
   both go blind. (The field stack IS independent of the landmark ENUMERATION,
   which is the narrower claim that survives.)
4. `main-id` is NOT answerable this way. "Inside THE `<main>` we found" is
   identity (`cur is main_obj`); `landmark == "main"` matches any main.
   Unprobed. Keep identity there, or probe `controlIdentifier_docHandle`/`_ID`.

Combination rule (agreed, and "chrome if EITHER says chrome" was rejected
because it keeps a COM chain per content item and, for counts, a false chrome
verdict removes items WITHOUT setting `counts_truncated`, which manufactures
NOTICE and KEY_RESULT): field says chrome, exclude; field definitively
not-in-chrome, accept with no COM; unknown, call `_in_scope_verdict`; parent
unknown, keep for walk and counts, refuse for focus.

The FOCUS gate is stricter than both: the field stack is a buffer SNAPSHOT and
`setFocus()` acts on the LIVE object, and a dynamic page can reparent the
control in between (unmeasured race). Require definitive field permission AND a
live `_in_scope_verdict(...) is True` immediately before `setFocus()`. That is
one chain per FORM page, not per chunk.

Do NOT delete `trust_boundary` / `untrusted_ranges` / `_chrome_pos_verdict` in
the same change that adds the field path. Two steps, each pinned.

## HELD BACK behind probes. Do not implement these on argument.

- THE COUNTS. Do not extrapolate the 0.7-1.1 ms field-call figure; that is a
  PARAGRAPH number and a quick-nav item's range can be a whole article.
  Collapse to the item start and expand ONE CHARACTER. Budget math first:
  6 types x 300-item scan cap x ~1 ms is ~1.8 s against a 0.6 s counts budget.
  Probe must record MAX call time, not average, plus `backendName` and NVDA
  version.
- `main-id` replacement (condition 4).
- One Firefox rerun of the existing probe before calling the mechanism
  cross-engine.

ADD `backendName` TO THE PROBE BEFORE ITS NEXT RUN, whatever that run is for.
Both reviewers landed on the backend gate independently, and the existing
results cannot be attributed to Gecko or Chromium after the fact because the
probe never logged which backend produced them. Log the NVDA version with it.
This is cheap now and unrecoverable later.

Unrelated and real, found in review: `_count_in_scope` silently DROPS an item
whose `obj is None` without setting `truncated_out`, producing a TRUSTED
undercount. And `classifier.py:448` bumps LIST confidence at `article_count >= 5`
while `_ARTICLE_LIMIT = 4` caps it at 4, so that branch cannot fire.

## Probes: Casey installs and runs them himself

Build with `python probes/build_probe.py field_stack`, open the `.nvda-addon`
with `Start-Process`, and he installs and restarts NVDA. Trigger is
NVDA+control+alt+f (NOT NVDA+shift+f, the `translate` add-on owns that and
silently wins the gesture). Open pages ONE AT A TIME and wait; he cannot press a
key on eight tabs that all steal focus as they open. Verify the installed copy
before diagnosing anything (`%APPDATA%\nvda\addons\...`, and check for
`pendingInstall`).

## HOW THE LAST THREE SESSIONS FAILED. Same shape each time.

- A check came back unanimous and was cited as proof when it could never have
  come back the other way. `disagree_innermost=0` over 219 chunks was cited as
  equivalence while the probe implemented the same bug and its comparison
  scored LINK against PARAGRAPH as agreement. That run is DISOWNED; do not cite
  it. When a number is unanimous, ask whether it could have failed, and ask it
  of the number you are LEANING ON, not the convenient one.
- A hazard was noticed and MIS-FILED. The chrome-none blocker above was looked
  at directly during the Change A analysis and written down as "a pre-existing
  accepted risk" instead of as a bug. Noticing is not disposing.
- A design was believed because it was argued well. Every design here has been
  reviewed by Codex AND a Fable subagent, in parallel, and they have killed
  several and each found things the other did not. Do this before believing any
  design. It is the highest-value habit on this branch.

## HARNESS TRAPS that silently invalidate your own verification

1. A sabotage check that rewrites a source file and immediately re-runs pytest
   can execute the PREVIOUS version. `.pyc` validation keys on source mtime and
   size. Always run with `python -B`.
2. A harness that crashes between writing the sabotage and restoring leaves the
   file DAMAGED, and the next run treats the damage as its baseline. Restore in
   a `finally` from bytes captured once, and re-run the full suite afterwards
   rather than trusting the restore. A working sabotage script from last
   session is worth rebuilding from the pattern in implementation-notes.

Sabotage checks are the control on this branch: it has been burned by tests
that pass while the wiring feeding them is deleted. `tests/test_walk_wiring.py`
is the pattern, driving the real `_walk_main_nodes` through a fake
TreeInterceptor rather than hand-built node lists. Pin the CHAIN, not the
pieces, and CONFIRM each new test fails when its wiring is removed.

## House rules that cost real time when ignored

- Verify NVDA behavior from NVDA's source or the installed bytecode, never from
  recall. `marshal.loads(data[16:])` then `dis.dis` works on `library.zip` and
  reflects the NVDA actually running. For C++, DOWNLOAD and read the file
  directly; a WebFetch summary of this exact codebase once asserted the
  opposite of the truth while quoting the code that disproved it.
- Read the DECISION TRACE in `nvda.log`, not just the `[TMTS perf]` line. A
  correct observation is not a diagnosis.
- An automated URL sweep is only valid with Casey present and AT the focused
  browser. Programmatic focus is not focus. Any sweep must count new perf-log
  lines per page and abort when the first few come back void. Heartbeat beep
  every ~3 seconds at 750 Hz (distinct from the add-on's 500/400/220).
- Do not commit unless Casey asks. Do not tune for specific sites; fixes go in
  at the class level or not at all.
