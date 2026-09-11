# Bounded-trust positional chrome scoping.
#
# THE PROBLEM. A page with no <main> and no single <article> decides "is this
# chunk content?" by climbing each chunk's ancestors looking for a chrome
# landmark - up to 30 levels, every level a COM call into the browser.
# Measured on store.payproglobal.com's checkout: 1808 ms of a 2035 ms walk was
# that climb (341 parent dereferences for 33 paragraphs), against 223 ms for
# object resolution and 2 ms for expand and text combined.
#
# THE FIRST ATTEMPT, AND WHY IT DIED. Collect the chrome landmark ranges and
# exclude by position, gated on "did the enumeration finish cleanly?" - because
# a partial inventory means an unenumerated nav reads as content and a blind
# user lands in a menu. That gate cannot be built. NVDA's
# VirtualBuffer._iterNodesByAttribs discards the exception from
# VBuf_findNodeByAttributes and returns, so a native failure is
# indistinguishable from natural exhaustion (verified by disassembling
# virtualBuffers/__init__.pyc from the installed library.zip). Shelved on the
# `chrome-pos-attempt` branch.
#
# THE DESIGN THAT WORKS. Never ask whether the scan finished. Ask how far it
# got. trustBoundary is the START of the last landmark successfully placed;
# emitted starts are nondecreasing, so anything before that point was already
# enumerated. Everything before the boundary is decidable regardless of why the
# scan stopped; everything after it uses the identity walk. Truncation costs
# speed, never correctness.
#
# ORDERING ALONE IS NOT ENOUGH, and the probe that "confirmed" it was hollow.
# NVDA seeds each search with the previous match's start offset and runs
# forward, so nondecreasing starts are guaranteed BY CONSTRUCTION - the
# 15-of-15 ordered=True reading could never have been False and proved nothing.
# The real question is whether the emission is COMPLETE: a landmark starting at
# the SAME offset as the one just returned may be silently skipped, which is
# omission mid-stream and invisible to every check here. A <section
# aria-label=...> wrapping a <nav> is that shape.
#
# Closed structurally rather than by verifying NVDA's C++: a skipped
# equal-start landmark is necessarily nested inside an emitted one, so any
# chunk starting inside an emitted NON-chrome landmark defers to the identity
# filter. See _chromePosVerdict.
#
# These tests pin the boundary arithmetic and every way the design declines.

import time

import treeSummary as ts


class FakeRange:
	"""Offset-pair stand-in for a TextInfo, with NVDA's compareEndPoints
	semantics: negative / zero / positive like a subtraction."""

	def __init__(self, start, end):
		self.start = start
		self.end = end

	def copy(self):
		return FakeRange(self.start, self.end)

	def compareEndPoints(self, other, which):
		a = self.start if which.startswith("start") else self.end
		b = other.start if which.endswith("Start") else other.end
		return (a > b) - (a < b)


class ExplodingRange(FakeRange):
	def compareEndPoints(self, other, which):
		raise RuntimeError("comparison failed (simulated)")


class NoCopyRange(FakeRange):
	def copy(self):
		raise RuntimeError("copy failed (simulated)")


class FakeObj:
	def __init__(self, landmark):
		self.landmark = landmark


class FakeItem:
	def __init__(self, landmark, rng=None):
		self.obj = FakeObj(landmark)
		self.textInfo = rng


class FakeTI:
	def __init__(self, items, raiseAfter=None, slowAfter=None):
		self.items = items
		self.raiseAfter = raiseAfter
		self.slowAfter = slowAfter

	def _iterNodesByType(self, itemType):
		for i, item in enumerate(self.items):
			if self.raiseAfter is not None and i >= self.raiseAfter:
				raise RuntimeError("iterator died (simulated COM error)")
			if self.slowAfter is not None and i >= self.slowAfter:
				time.sleep(ts._FIND_MAIN_TIME_BUDGET_SEC + 0.01)
			yield item


NAV = FakeRange(0, 10)
FOOT = FakeRange(90, 100)


# ---------------------------------------------------------------------------
# The trust boundary: how far did the scan get?
# ---------------------------------------------------------------------------


def test_boundaryIsTheLastLandmarkSeen():
	scan = ts._findMainLandmark(
		FakeTI(
			[
				FakeItem("navigation", FakeRange(0, 10)),
				FakeItem("complementary", FakeRange(40, 50)),
				FakeItem("contentinfo", FakeRange(90, 100)),
			]
		)
	)
	assert scan.mainObj is None
	assert len(scan.chromeRanges) == 3
	# Boundary sits at the LAST landmark's start, so the footer and
	# everything past it stays on the identity path.
	assert scan.trustBoundary.start == 90


def test_aTruncatedScanJustMovesTheBoundaryEarlier():
	# The case the old design could not survive. Here it is merely slower:
	# the first two landmarks are still fully trustworthy.
	items = [FakeItem("navigation", FakeRange(i * 10, i * 10 + 5)) for i in range(60)]
	scan = ts._findMainLandmark(FakeTI(items))
	assert scan.trustBoundary is not None
	# Stopped at the scan cap, so the boundary is far short of the document
	# end - but it is still a valid boundary, not a wrong answer.
	assert scan.trustBoundary.start < 590


def test_anIteratorThatDiesStillYieldsAUsableBoundary():
	scan = ts._findMainLandmark(
		FakeTI(
			[
				FakeItem("navigation", FakeRange(0, 10)),
				FakeItem("complementary", FakeRange(40, 50)),
				FakeItem("contentinfo", FakeRange(90, 100)),
			],
			raiseAfter=2,
		)
	)
	# Two landmarks were seen before the failure and both remain valid.
	assert scan.trustBoundary.start == 40
	assert len(scan.chromeRanges) == 2


def test_anUnplaceableLandmarkFreezesTheBoundaryThere():
	# We cannot exclude what we cannot place, so trust stops at that point -
	# but everything BEFORE it is still known and still usable.
	scan = ts._findMainLandmark(
		FakeTI(
			[
				FakeItem("navigation", FakeRange(0, 10)),
				FakeItem("navigation", None),
				FakeItem("contentinfo", FakeRange(90, 100)),
			]
		)
	)
	assert scan.trustBoundary.start == 0
	assert len(scan.chromeRanges) == 1


def test_aDegenerateRangeFreezesTheBoundary():
	scan = ts._findMainLandmark(
		FakeTI(
			[
				FakeItem("navigation", FakeRange(0, 10)),
				FakeItem("navigation", FakeRange(20, 20)),
				FakeItem("contentinfo", FakeRange(90, 100)),
			]
		)
	)
	assert scan.trustBoundary.start == 0


def test_anInvertedRangeFreezesTheBoundary():
	scan = ts._findMainLandmark(
		FakeTI(
			[
				FakeItem("navigation", FakeRange(0, 10)),
				FakeItem("navigation", FakeRange(50, 20)),
			]
		)
	)
	assert scan.trustBoundary.start == 0


def test_anUncopyableRangeFreezesTheBoundary():
	scan = ts._findMainLandmark(
		FakeTI(
			[
				FakeItem("navigation", FakeRange(0, 10)),
				FakeItem("navigation", NoCopyRange(20, 30)),
			]
		)
	)
	assert scan.trustBoundary.start == 0


def test_outOfOrderLandmarksAreDetected():
	scan = ts._findMainLandmark(
		FakeTI(
			[
				FakeItem("navigation", FakeRange(50, 60)),
				FakeItem("banner", FakeRange(10, 20)),
			]
		)
	)
	assert scan.ordered is False


def test_noLandmarksAtAllLeavesNothingToBound():
	scan = ts._findMainLandmark(FakeTI([]))
	assert scan.trustBoundary is None
	assert scan.chromeRanges == []


def test_rangesArePrivateCopies():
	original = FakeRange(0, 10)
	scan = ts._findMainLandmark(FakeTI([FakeItem("navigation", original)]))
	assert scan.chromeRanges[0] is not original


def test_findingMainStillReturnsIt():
	scan = ts._findMainLandmark(
		FakeTI(
			[
				FakeItem("navigation", FakeRange(0, 10)),
				FakeItem("main", FakeRange(10, 90)),
			]
		)
	)
	assert scan.mainObj is not None
	assert scan.mainRange is not None


# ---------------------------------------------------------------------------
# _selectScope: the decision every bit of safety funnels through.
# buildTreeSummary cannot run outside NVDA, so without these it would be
# the one load-bearing line with no coverage.
# ---------------------------------------------------------------------------


def test_orderedScanWithABoundaryEnablesPositional():
	ranges = [NAV]
	kind, scopeRange, exclude, boundary, untrusted = ts._selectScope(
		ts.LandmarkScan(None, None, ranges, FakeRange(90, 100), ordered=True)
	)
	assert kind == "chrome-pos"
	assert exclude is ranges
	assert boundary.start == 90
	assert scopeRange is None


def test_outOfOrderPageDeclinesToTheIdentityPath():
	# A single backwards step voids the ordering argument the whole design
	# rests on. This is the runtime check that keeps "measured on 15 pages"
	# from silently becoming "assumed everywhere".
	kind, scopeRange, exclude, boundary, untrusted = ts._selectScope(
		ts.LandmarkScan(None, None, [NAV], FakeRange(90, 100), ordered=False)
	)
	assert kind == "chrome"
	assert exclude is None
	assert boundary is None


def test_noBoundaryDeclinesToTheIdentityPath():
	# Covers both "page has no landmarks" and "the enumeration died before
	# the first one" - the same observation, and only one of them is safe.
	kind, _, exclude, boundary, untrusted = ts._selectScope(
		ts.LandmarkScan(None, None, [], None, ordered=True)
	)
	assert kind == "chrome"
	assert exclude is None
	assert boundary is None


def test_mainPageNeverCarriesAnExclusionList():
	kind, scopeRange, exclude, boundary, untrusted = ts._selectScope(
		ts.LandmarkScan(FakeObj("main"), FakeRange(10, 90), [NAV], FakeRange(0, 10), True)
	)
	assert kind == "main-pos"
	assert scopeRange is not None
	assert exclude is None
	assert boundary is None


def test_mainWithoutAUsableRangeUsesIdentity():
	kind, scopeRange, exclude, _b, _u = ts._selectScope(
		ts.LandmarkScan(FakeObj("main"), None, [], None, True)
	)
	assert kind == "main-id"
	assert scopeRange is None
	assert exclude is None


def test_scopeSelectionNeverReturnsBothARangeAndAnExclusion():
	# The invariant _walkMainNodes depends on, across every combination.
	for mainObj in (None, FakeObj("main")):
		for mainRange in (None, FakeRange(10, 90)):
			for boundary in (None, FakeRange(0, 10)):
				for ordered in (False, True):
					_, sr, ex, _b, _u = ts._selectScope(
						ts.LandmarkScan(mainObj, mainRange, [NAV], boundary, ordered)
					)
					assert sr is None or ex is None


# ---------------------------------------------------------------------------
# The exclusion test: START position, tri-state on failure.
# ---------------------------------------------------------------------------


def test_chunkInsideAChromeRangeIsExcluded():
	assert ts._startsInAny(FakeRange(2, 5), [NAV, FOOT]) is True


def test_chunkOutsideEveryChromeRangeIsKept():
	assert ts._startsInAny(FakeRange(40, 50), [NAV, FOOT]) is False


def test_chunkStartingExactlyAtARangeStartIsExcluded():
	assert ts._startsInAny(FakeRange(0, 3), [NAV]) is True


def test_chunkStartingExactlyAtARangeEndIsKept():
	# End is exclusive: the first chunk after the nav belongs to the content.
	assert ts._startsInAny(FakeRange(10, 15), [NAV]) is False


def test_chunkStartingInChromeButEndingPastItIsExcluded():
	# Full containment would keep this one, disagreeing with the identity
	# filter it replaces - that asks about the object at the chunk's START.
	assert ts._startsInAny(FakeRange(8, 40), [NAV]) is True


def test_nestedAndOverlappingRangesAgree():
	banner = FakeRange(0, 50)
	navInside = FakeRange(10, 20)
	assert ts._startsInAny(FakeRange(12, 15), [banner, navInside]) is True
	assert ts._startsInAny(FakeRange(60, 65), [banner, navInside]) is False


def test_emptyRangeListExcludesNothing():
	assert ts._startsInAny(FakeRange(2, 5), []) is False


def test_comparisonFailureIsUnknownNotIncluded():
	# Tri-state matters here. Every other positional check in the module
	# treats a failed comparison as "include", which is right for counts and
	# wrong for scope: it would serve navigation as article text. None makes
	# the caller fall back to the identity filter instead of guessing.
	assert ts._startsInAny(ExplodingRange(2, 5), [NAV]) is None


# ---------------------------------------------------------------------------
# Boundary comparison.
# ---------------------------------------------------------------------------


def test_beforeTheBoundaryIsTrusted():
	assert ts._startsBefore(FakeRange(5, 8), FakeRange(90, 100)) is True


def test_atOrAfterTheBoundaryIsNotTrusted():
	assert ts._startsBefore(FakeRange(90, 95), FakeRange(90, 100)) is False
	assert ts._startsBefore(FakeRange(95, 99), FakeRange(90, 100)) is False


def test_noBoundaryTrustsNothing():
	assert ts._startsBefore(FakeRange(5, 8), None) is False


def test_boundaryComparisonFailureIsUnknown():
	assert ts._startsBefore(ExplodingRange(5, 8), FakeRange(90, 100)) is None


# ---------------------------------------------------------------------------
# The per-chunk decision. This is the wiring where a fail-open mistake
# reintroduces the release-blocker class, and until _chromePosVerdict was
# extracted, NOTHING in the suite reached it: a regression changing `is True`
# to a truthiness test, or dropping a tri-state check, would have passed the
# entire suite green. Flagged by both reviews, 2026-07-18.
# ---------------------------------------------------------------------------

BOUNDARY = FakeRange(90, 100)


def test_contentBeforeTheBoundaryAndOutsideEverythingIsKept():
	assert ts._chromePosVerdict(FakeRange(40, 50), BOUNDARY, [NAV], []) is True


def test_chunkInsideChromeIsExcluded():
	assert ts._chromePosVerdict(FakeRange(2, 5), BOUNDARY, [NAV], []) is False


def test_chunkAtOrAfterTheBoundaryDefersToIdentity():
	assert ts._chromePosVerdict(FakeRange(95, 99), BOUNDARY, [NAV], []) is None


def test_chunkInsideANonChromeLandmarkDefersToIdentity():
	# THE EQUAL-START HOLE. NVDA resumes each landmark search from the previous
	# match's START offset, so a landmark beginning at the same offset as the
	# one just returned may be silently skipped - omission mid-stream, which
	# ordering cannot detect. A <section aria-label=...> wrapping a <nav> with
	# no text between them is exactly that shape. The nav would be missing from
	# chromeRanges and its chunks would read as trusted CONTENT.
	#
	# A skipped equal-start landmark is necessarily nested inside the emitted
	# one, so any chunk it could contain also lies inside an emitted range.
	# Deferring those to the identity filter closes the hole without needing
	# to verify NVDA's C++ traversal semantics.
	region = FakeRange(30, 60)
	assert ts._chromePosVerdict(FakeRange(40, 50), BOUNDARY, [NAV], [region]) is None


def test_chunkOutsideTheNonChromeLandmarkIsStillTrusted():
	region = FakeRange(30, 60)
	assert ts._chromePosVerdict(FakeRange(70, 75), BOUNDARY, [NAV], [region]) is True


def test_chromeWinsOverUntrustedWhenBothContainTheChunk():
	# Nested chrome inside a region: the chrome range excludes it outright, and
	# an omitted landmark nested there could only exclude the same text.
	region = FakeRange(0, 60)
	assert ts._chromePosVerdict(FakeRange(2, 5), BOUNDARY, [NAV], [region]) is False


def test_aFailedChromeComparisonDefersToIdentity():
	# Never "assume not excluded" - that is how navigation becomes article text.
	assert ts._chromePosVerdict(ExplodingRange(40, 50), BOUNDARY, [NAV], []) is None


def test_aFailedBoundaryComparisonDefersToIdentity():
	assert ts._chromePosVerdict(ExplodingRange(40, 50), BOUNDARY, [], []) is None


def test_noBoundaryMeansNothingIsTrusted():
	assert ts._chromePosVerdict(FakeRange(40, 50), None, [NAV], []) is None


def test_equalStartNestingIsCoveredByTheOuterRange():
	# The concrete omission shape: outer region and inner nav share a start.
	# The region is emitted, the nav may not be. Any chunk the nav could hold
	# lies inside the region, so it defers to identity.
	region = FakeRange(20, 80)
	for chunkStart in (20, 35, 79):
		assert ts._chromePosVerdict(FakeRange(chunkStart, chunkStart + 3), BOUNDARY, [], [region]) is None


# ---------------------------------------------------------------------------
# The untrustedRanges WIRING, end to end.
#
# Both reviewers independently verified that deleting the `otherRanges`
# append, or dropping the value on the way to the walk, left all 238 tests
# green - so the entire equal-start defence could vanish without a single
# failure. This codebase has now lost safety inputs that way twice. These
# tests exist so it cannot happen a third time.
# ---------------------------------------------------------------------------


def test_scanCollectsNonChromeLandmarksSeparately():
	scan = ts._findMainLandmark(
		FakeTI(
			[
				FakeItem("navigation", FakeRange(0, 10)),
				FakeItem("region", FakeRange(20, 60)),
				FakeItem("contentinfo", FakeRange(90, 100)),
			]
		)
	)
	chromeStarts = sorted(r.start for r in scan.chromeRanges)
	otherStarts = sorted(r.start for r in scan.otherRanges)
	assert chromeStarts == [0, 90]
	# The region is NOT an exclusion - it marks where an omitted nested
	# landmark could hide.
	assert otherStarts == [20]


def test_aNonChromeLandmarkStillAdvancesTheTrustBoundary():
	# It was placed, so everything before it remains fully known.
	scan = ts._findMainLandmark(
		FakeTI(
			[
				FakeItem("navigation", FakeRange(0, 10)),
				FakeItem("region", FakeRange(20, 60)),
			]
		)
	)
	assert scan.trustBoundary.start == 20


def test_anUnplaceableNonChromeLandmarkFreezesTrustToo():
	scan = ts._findMainLandmark(
		FakeTI(
			[
				FakeItem("navigation", FakeRange(0, 10)),
				FakeItem("region", None),
				FakeItem("contentinfo", FakeRange(90, 100)),
			]
		)
	)
	assert scan.trustBoundary.start == 0
	assert scan.otherRanges == []


def test_selectScopeHandsTheNonChromeRangesToTheCaller():
	# The link in the chain that had no coverage at all: every previous
	# _selectScope test unpacked this value and then never asserted on it.
	scan = ts._findMainLandmark(
		FakeTI(
			[
				FakeItem("navigation", FakeRange(0, 10)),
				FakeItem("region", FakeRange(20, 60)),
				FakeItem("contentinfo", FakeRange(90, 100)),
			]
		)
	)
	kind, scopeRange, exclude, boundary, untrusted = ts._selectScope(scan)
	assert kind == "chrome-pos"
	assert untrusted is scan.otherRanges
	assert len(untrusted) == 1


def test_theChainEndToEndProtectsAChunkInsideARegion():
	# Scan -> select -> verdict, with no hand-built lists anywhere. A chunk
	# inside the emitted region defers to identity, because that is where an
	# omitted nested nav would be; a chunk outside every landmark does not.
	scan = ts._findMainLandmark(
		FakeTI(
			[
				FakeItem("navigation", FakeRange(0, 10)),
				FakeItem("region", FakeRange(20, 60)),
				FakeItem("contentinfo", FakeRange(90, 100)),
			]
		)
	)
	_, _, exclude, boundary, untrusted = ts._selectScope(scan)
	assert ts._chromePosVerdict(FakeRange(30, 35), boundary, exclude, untrusted) is None
	assert ts._chromePosVerdict(FakeRange(70, 75), boundary, exclude, untrusted) is True
	assert ts._chromePosVerdict(FakeRange(2, 5), boundary, exclude, untrusted) is False


def test_orderingComparisonFailureKillsChromePos():
	# The fail-closed path added this round, previously untested: an ordering
	# comparison we could not make means the order is UNKNOWN, and unknown
	# must not read as ordered.
	scan = ts._findMainLandmark(
		FakeTI(
			[
				FakeItem("navigation", FakeRange(0, 10)),
				FakeItem("navigation", ExplodingRange(20, 30)),
			]
		)
	)
	assert scan.ordered is False
	kind, _, exclude, _b, _u = ts._selectScope(scan)
	assert kind == "chrome"
	assert exclude is None


# ---------------------------------------------------------------------------
# Form-field focus eligibility. THIS PATH MOVES KEYBOARD FOCUS, and it had no
# test of any kind through four review rounds while being wrong twice. It
# fails CLOSED everywhere: elsewhere an undecidable chunk is kept because a
# stray line read aloud is recoverable, but here being wrong takes the caret
# out of the page content entirely.
# ---------------------------------------------------------------------------


class FieldItem:
	def __init__(self, rng, obj=None):
		self.textInfo = rng
		self.obj = obj


def _eligible(item, kind, scopeRange=None, chrome=None, boundary=None, untrusted=None, mainObj=None):
	return ts._formFieldInScope(item, kind, scopeRange, chrome or [], boundary, untrusted or [], mainObj, {})


def test_fieldInsideMainRangeIsEligible():
	assert _eligible(FieldItem(FakeRange(40, 45)), "main-pos", scopeRange=FakeRange(10, 90)) is True


def test_fieldOutsideMainRangeIsRejected():
	assert _eligible(FieldItem(FakeRange(2, 5)), "main-pos", scopeRange=FakeRange(10, 90)) is False


def test_mainRangeComparisonFailureRefusesToMoveFocus():
	# Fail-CLOSED. This used to answer "eligible", which is fail-open on the
	# one path that calls setFocus().
	assert _eligible(ExplodingRange(40, 45), "main-pos", scopeRange=FakeRange(10, 90)) is False


def test_chromePosFieldInANavIsRejected():
	assert (
		_eligible(
			FieldItem(FakeRange(2, 5)),
			"chrome-pos",
			chrome=[NAV],
			boundary=FakeRange(90, 100),
		)
		is False
	)


def test_chromePosFieldInContentIsEligible():
	assert (
		_eligible(
			FieldItem(FakeRange(40, 45)),
			"chrome-pos",
			chrome=[NAV],
			boundary=FakeRange(90, 100),
		)
		is True
	)


def test_chromePosFieldInUntrustedTerritoryNeedsAnObject():
	# An emitted non-chrome region may hide a reseed-omitted nav. The walker
	# defers to identity there; so must this. With no object there is no
	# identity check available, so no focus move.
	region = FakeRange(30, 60)
	assert (
		_eligible(
			FieldItem(FakeRange(40, 45)),
			"chrome-pos",
			chrome=[NAV],
			boundary=FakeRange(90, 100),
			untrusted=[region],
		)
		is False
	)


def test_fieldPastTheTrustBoundaryNeedsAnObject():
	assert (
		_eligible(
			FieldItem(FakeRange(95, 98)),
			"chrome-pos",
			chrome=[NAV],
			boundary=FakeRange(90, 100),
		)
		is False
	)


def test_mainIdPageDoesNotFallIntoTheNoMainBranch():
	# The regression review caught: a <main> exists but its range is
	# unusable, so scope is main-id. Treating that as "no main" would let a
	# field OUTSIDE <main> take focus. With no object to test identity
	# against, the answer must be no.
	assert _eligible(FieldItem(FakeRange(2, 5)), "main-id", mainObj=FakeObj("main")) is False


def test_aFieldWithNoObjectAndNoRangeIsNeverFocused():
	assert _eligible(FieldItem(None, None), "chrome") is False


# ---------------------------------------------------------------------------
# THE LANDMARK-FREE FAST PATH IS GONE. These tests keep it gone.
#
# `chrome-none` promoted a page whose landmark enumeration yielded nothing into
# a walk that skipped chrome checking ENTIRELY, on the theory that a scan which
# ran to completion and saw nothing proves the document has no landmarks.
#
# It proves no such thing. NVDA's VirtualBuffer._iterNodesByAttribs CATCHES the
# native exception from VBuf_findNodeByAttributes and RETURNS (the handler is
# PUSH_EXC_INFO / POP_TOP / POP_EXCEPT / RETURN_CONST None, with no
# CHECK_EXC_MATCH -- verified by disassembling virtualBuffers/__init__.pyc from
# the installed library.zip). A natively FAILED landmark search is therefore an
# ordinary, empty, normally-completed generator: seen=0, exhausted=True, which
# is byte-for-byte the shape of a genuinely landmark-free page.
#
# The `exhausted` flag ruled out only a Python exception ESCAPING the iterator
# -- the one shape NVDA does not produce here. The old suite pinned the BUG as
# correct: its "landmark free with working enumeration" test drove FakeTI([]),
# which IS the native-swallow shape, and asserted the shortcut engaged; while
# the test that claimed to close the hole used raiseAfter=0, the escaping
# shape. Both are corrected below.
#
# There is NO signal at the LandmarkScan layer that can separate the two
# zero-seen cases. Do not add one gated on the enumeration returning nothing.
# The per-chunk field stack is the only positive witness available.
# ---------------------------------------------------------------------------


def test_nativeSwallowShapeDoesNotUnlockAnyLandmarkFreeShortcut():
	"""THE REGRESSION TEST. An enumeration that yields nothing and returns
	normally must leave the chrome filter ENGAGED.

	This is the shape NVDA actually produces on a failed landmark search, and
	getting it wrong admits navigation and footer as article content -- a blind
	user's cursor lands in a menu.
	"""
	scan = ts._findMainLandmark(FakeTI([]))
	# Precondition: this really is the indistinguishable shape.
	assert scan.seen == 0
	assert scan.exhausted is True

	scopeKind, scopeRange, chromeExclude, boundary, untrusted = ts._selectScope(scan)

	# "chrome" means the identity parent walk decides every chunk. Any scope that
	# admits chunks without a chrome check is the bug returning.
	assert scopeKind == "chrome"
	assert scopeRange is None, "no inclusion range may be invented from an empty scan"
	assert chromeExclude is None, "no positional exclusion list can be trusted here"
	assert boundary is None
	assert untrusted is None


def test_noScopeKindAdmitsChunksWithoutAChromeCheck():
	"""The whole failure class, stated once. Whatever _selectScope returns for
	an empty scan, it must not be a scope the walk treats as "keep everything".

	Pinned by name so that reintroducing a shortcut under a NEW name still trips
	this test rather than sailing past a check that only knew the old one.
	"""
	for scan in (
		ts._findMainLandmark(FakeTI([])),
		ts._findMainLandmark(FakeTI([], raiseAfter=0)),
	):
		scopeKind, scopeRange, chromeExclude, _b, _u = ts._selectScope(scan)
		assert scopeKind == "chrome"
		assert (scopeRange, chromeExclude) == (None, None)


def test_theRemovedShortcutStaysRemoved():
	"""_document_has_no_landmarks was the merge blocker. It must not come back,
	and neither must the scope name it produced."""
	assert not hasattr(ts, "_document_has_no_landmarks")
	assert not hasattr(ts, "_SCOPE_FREE")
	src = ts._selectScope.__doc__ or ""
	assert "chrome-none" not in src


def test_aPageWithLandmarksStillScopesPositionally():
	"""The removal must not have broken the ordinary no-<main> path: a placed
	landmark still yields bounded-trust positional scoping."""
	scan = ts._findMainLandmark(FakeTI([FakeItem("navigation", FakeRange(0, 10))]))
	assert scan.seen == 1
	scopeKind, _r, chromeExclude, boundary, _u = ts._selectScope(scan)
	assert scopeKind == "chrome-pos"
	assert boundary is not None
	assert len(chromeExclude) == 1


def test_unresolvableLandmarksStillCountAsSeen():
	# An item we could not place is still evidence that landmarks EXIST.
	item = FakeItem("navigation", None)
	item.obj = None
	scan = ts._findMainLandmark(FakeTI([item]))
	assert scan.seen == 1
	scopeKind, _r, _c, _b, _u = ts._selectScope(scan)
	assert scopeKind == "chrome"
