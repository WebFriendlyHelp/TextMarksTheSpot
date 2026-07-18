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
# got. trust_boundary is the START of the last landmark successfully placed;
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
# filter. See _chrome_pos_verdict.
#
# These tests pin the boundary arithmetic and every way the design declines.

import time

import tree_summary as ts


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
	def __init__(self, items, raise_after=None, slow_after=None):
		self.items = items
		self.raise_after = raise_after
		self.slow_after = slow_after

	def _iterNodesByType(self, item_type):
		for i, item in enumerate(self.items):
			if self.raise_after is not None and i >= self.raise_after:
				raise RuntimeError("iterator died (simulated COM error)")
			if self.slow_after is not None and i >= self.slow_after:
				time.sleep(ts._FIND_MAIN_TIME_BUDGET_SEC + 0.01)
			yield item


NAV = FakeRange(0, 10)
FOOT = FakeRange(90, 100)


# ---------------------------------------------------------------------------
# The trust boundary: how far did the scan get?
# ---------------------------------------------------------------------------

def test_boundary_is_the_last_landmark_seen():
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", FakeRange(0, 10)),
		FakeItem("complementary", FakeRange(40, 50)),
		FakeItem("contentinfo", FakeRange(90, 100)),
	]))
	assert scan.main_obj is None
	assert len(scan.chrome_ranges) == 3
	# Boundary sits at the LAST landmark's start, so the footer and
	# everything past it stays on the identity path.
	assert scan.trust_boundary.start == 90


def test_a_truncated_scan_just_moves_the_boundary_earlier():
	# The case the old design could not survive. Here it is merely slower:
	# the first two landmarks are still fully trustworthy.
	items = [FakeItem("navigation", FakeRange(i * 10, i * 10 + 5)) for i in range(60)]
	scan = ts._find_main_landmark(FakeTI(items))
	assert scan.trust_boundary is not None
	# Stopped at the scan cap, so the boundary is far short of the document
	# end - but it is still a valid boundary, not a wrong answer.
	assert scan.trust_boundary.start < 590


def test_an_iterator_that_dies_still_yields_a_usable_boundary():
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", FakeRange(0, 10)),
		FakeItem("complementary", FakeRange(40, 50)),
		FakeItem("contentinfo", FakeRange(90, 100)),
	], raise_after=2))
	# Two landmarks were seen before the failure and both remain valid.
	assert scan.trust_boundary.start == 40
	assert len(scan.chrome_ranges) == 2


def test_an_unplaceable_landmark_freezes_the_boundary_there():
	# We cannot exclude what we cannot place, so trust stops at that point -
	# but everything BEFORE it is still known and still usable.
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", FakeRange(0, 10)),
		FakeItem("navigation", None),
		FakeItem("contentinfo", FakeRange(90, 100)),
	]))
	assert scan.trust_boundary.start == 0
	assert len(scan.chrome_ranges) == 1


def test_a_degenerate_range_freezes_the_boundary():
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", FakeRange(0, 10)),
		FakeItem("navigation", FakeRange(20, 20)),
		FakeItem("contentinfo", FakeRange(90, 100)),
	]))
	assert scan.trust_boundary.start == 0


def test_an_inverted_range_freezes_the_boundary():
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", FakeRange(0, 10)),
		FakeItem("navigation", FakeRange(50, 20)),
	]))
	assert scan.trust_boundary.start == 0


def test_an_uncopyable_range_freezes_the_boundary():
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", FakeRange(0, 10)),
		FakeItem("navigation", NoCopyRange(20, 30)),
	]))
	assert scan.trust_boundary.start == 0


def test_out_of_order_landmarks_are_detected():
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", FakeRange(50, 60)),
		FakeItem("banner", FakeRange(10, 20)),
	]))
	assert scan.ordered is False


def test_no_landmarks_at_all_leaves_nothing_to_bound():
	scan = ts._find_main_landmark(FakeTI([]))
	assert scan.trust_boundary is None
	assert scan.chrome_ranges == []


def test_ranges_are_private_copies():
	original = FakeRange(0, 10)
	scan = ts._find_main_landmark(FakeTI([FakeItem("navigation", original)]))
	assert scan.chrome_ranges[0] is not original


def test_finding_main_still_returns_it():
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", FakeRange(0, 10)),
		FakeItem("main", FakeRange(10, 90)),
	]))
	assert scan.main_obj is not None
	assert scan.main_range is not None


# ---------------------------------------------------------------------------
# _select_scope: the decision every bit of safety funnels through.
# build_tree_summary cannot run outside NVDA, so without these it would be
# the one load-bearing line with no coverage.
# ---------------------------------------------------------------------------

def test_ordered_scan_with_a_boundary_enables_positional():
	ranges = [NAV]
	kind, scope_range, exclude, boundary, untrusted = ts._select_scope(
		ts.LandmarkScan(None, None, ranges, FakeRange(90, 100), ordered=True)
	)
	assert kind == "chrome-pos"
	assert exclude is ranges
	assert boundary.start == 90
	assert scope_range is None


def test_out_of_order_page_declines_to_the_identity_path():
	# A single backwards step voids the ordering argument the whole design
	# rests on. This is the runtime check that keeps "measured on 15 pages"
	# from silently becoming "assumed everywhere".
	kind, scope_range, exclude, boundary, untrusted = ts._select_scope(
		ts.LandmarkScan(None, None, [NAV], FakeRange(90, 100), ordered=False)
	)
	assert kind == "chrome"
	assert exclude is None
	assert boundary is None


def test_no_boundary_declines_to_the_identity_path():
	# Covers both "page has no landmarks" and "the enumeration died before
	# the first one" - the same observation, and only one of them is safe.
	kind, _, exclude, boundary, untrusted = ts._select_scope(
		ts.LandmarkScan(None, None, [], None, ordered=True)
	)
	assert kind == "chrome"
	assert exclude is None
	assert boundary is None


def test_main_page_never_carries_an_exclusion_list():
	kind, scope_range, exclude, boundary, untrusted = ts._select_scope(
		ts.LandmarkScan(FakeObj("main"), FakeRange(10, 90), [NAV], FakeRange(0, 10), True)
	)
	assert kind == "main-pos"
	assert scope_range is not None
	assert exclude is None
	assert boundary is None


def test_main_without_a_usable_range_uses_identity():
	kind, scope_range, exclude, _b, _u = ts._select_scope(
		ts.LandmarkScan(FakeObj("main"), None, [], None, True)
	)
	assert kind == "main-id"
	assert scope_range is None
	assert exclude is None


def test_scope_selection_never_returns_both_a_range_and_an_exclusion():
	# The invariant _walk_main_nodes depends on, across every combination.
	for main_obj in (None, FakeObj("main")):
		for main_range in (None, FakeRange(10, 90)):
			for boundary in (None, FakeRange(0, 10)):
				for ordered in (False, True):
					_, sr, ex, _b, _u = ts._select_scope(
						ts.LandmarkScan(main_obj, main_range, [NAV], boundary, ordered)
					)
					assert sr is None or ex is None


# ---------------------------------------------------------------------------
# The exclusion test: START position, tri-state on failure.
# ---------------------------------------------------------------------------

def test_chunk_inside_a_chrome_range_is_excluded():
	assert ts._starts_in_any(FakeRange(2, 5), [NAV, FOOT]) is True


def test_chunk_outside_every_chrome_range_is_kept():
	assert ts._starts_in_any(FakeRange(40, 50), [NAV, FOOT]) is False


def test_chunk_starting_exactly_at_a_range_start_is_excluded():
	assert ts._starts_in_any(FakeRange(0, 3), [NAV]) is True


def test_chunk_starting_exactly_at_a_range_end_is_kept():
	# End is exclusive: the first chunk after the nav belongs to the content.
	assert ts._starts_in_any(FakeRange(10, 15), [NAV]) is False


def test_chunk_starting_in_chrome_but_ending_past_it_is_excluded():
	# Full containment would keep this one, disagreeing with the identity
	# filter it replaces - that asks about the object at the chunk's START.
	assert ts._starts_in_any(FakeRange(8, 40), [NAV]) is True


def test_nested_and_overlapping_ranges_agree():
	banner = FakeRange(0, 50)
	nav_inside = FakeRange(10, 20)
	assert ts._starts_in_any(FakeRange(12, 15), [banner, nav_inside]) is True
	assert ts._starts_in_any(FakeRange(60, 65), [banner, nav_inside]) is False


def test_empty_range_list_excludes_nothing():
	assert ts._starts_in_any(FakeRange(2, 5), []) is False


def test_comparison_failure_is_unknown_not_included():
	# Tri-state matters here. Every other positional check in the module
	# treats a failed comparison as "include", which is right for counts and
	# wrong for scope: it would serve navigation as article text. None makes
	# the caller fall back to the identity filter instead of guessing.
	assert ts._starts_in_any(ExplodingRange(2, 5), [NAV]) is None


# ---------------------------------------------------------------------------
# Boundary comparison.
# ---------------------------------------------------------------------------

def test_before_the_boundary_is_trusted():
	assert ts._starts_before(FakeRange(5, 8), FakeRange(90, 100)) is True


def test_at_or_after_the_boundary_is_not_trusted():
	assert ts._starts_before(FakeRange(90, 95), FakeRange(90, 100)) is False
	assert ts._starts_before(FakeRange(95, 99), FakeRange(90, 100)) is False


def test_no_boundary_trusts_nothing():
	assert ts._starts_before(FakeRange(5, 8), None) is False


def test_boundary_comparison_failure_is_unknown():
	assert ts._starts_before(ExplodingRange(5, 8), FakeRange(90, 100)) is None


# ---------------------------------------------------------------------------
# The per-chunk decision. This is the wiring where a fail-open mistake
# reintroduces the release-blocker class, and until _chrome_pos_verdict was
# extracted, NOTHING in the suite reached it: a regression changing `is True`
# to a truthiness test, or dropping a tri-state check, would have passed the
# entire suite green. Flagged by both reviews, 2026-07-18.
# ---------------------------------------------------------------------------

BOUNDARY = FakeRange(90, 100)


def test_content_before_the_boundary_and_outside_everything_is_kept():
	assert ts._chrome_pos_verdict(FakeRange(40, 50), BOUNDARY, [NAV], []) is True


def test_chunk_inside_chrome_is_excluded():
	assert ts._chrome_pos_verdict(FakeRange(2, 5), BOUNDARY, [NAV], []) is False


def test_chunk_at_or_after_the_boundary_defers_to_identity():
	assert ts._chrome_pos_verdict(FakeRange(95, 99), BOUNDARY, [NAV], []) is None


def test_chunk_inside_a_non_chrome_landmark_defers_to_identity():
	# THE EQUAL-START HOLE. NVDA resumes each landmark search from the previous
	# match's START offset, so a landmark beginning at the same offset as the
	# one just returned may be silently skipped - omission mid-stream, which
	# ordering cannot detect. A <section aria-label=...> wrapping a <nav> with
	# no text between them is exactly that shape. The nav would be missing from
	# chrome_ranges and its chunks would read as trusted CONTENT.
	#
	# A skipped equal-start landmark is necessarily nested inside the emitted
	# one, so any chunk it could contain also lies inside an emitted range.
	# Deferring those to the identity filter closes the hole without needing
	# to verify NVDA's C++ traversal semantics.
	region = FakeRange(30, 60)
	assert ts._chrome_pos_verdict(FakeRange(40, 50), BOUNDARY, [NAV], [region]) is None


def test_chunk_outside_the_non_chrome_landmark_is_still_trusted():
	region = FakeRange(30, 60)
	assert ts._chrome_pos_verdict(FakeRange(70, 75), BOUNDARY, [NAV], [region]) is True


def test_chrome_wins_over_untrusted_when_both_contain_the_chunk():
	# Nested chrome inside a region: the chrome range excludes it outright, and
	# an omitted landmark nested there could only exclude the same text.
	region = FakeRange(0, 60)
	assert ts._chrome_pos_verdict(FakeRange(2, 5), BOUNDARY, [NAV], [region]) is False


def test_a_failed_chrome_comparison_defers_to_identity():
	# Never "assume not excluded" - that is how navigation becomes article text.
	assert ts._chrome_pos_verdict(ExplodingRange(40, 50), BOUNDARY, [NAV], []) is None


def test_a_failed_boundary_comparison_defers_to_identity():
	assert ts._chrome_pos_verdict(ExplodingRange(40, 50), BOUNDARY, [], []) is None


def test_no_boundary_means_nothing_is_trusted():
	assert ts._chrome_pos_verdict(FakeRange(40, 50), None, [NAV], []) is None


def test_equal_start_nesting_is_covered_by_the_outer_range():
	# The concrete omission shape: outer region and inner nav share a start.
	# The region is emitted, the nav may not be. Any chunk the nav could hold
	# lies inside the region, so it defers to identity.
	region = FakeRange(20, 80)
	for chunk_start in (20, 35, 79):
		assert ts._chrome_pos_verdict(
			FakeRange(chunk_start, chunk_start + 3), BOUNDARY, [], [region]
		) is None


# ---------------------------------------------------------------------------
# The untrusted_ranges WIRING, end to end.
#
# Both reviewers independently verified that deleting the `other_ranges`
# append, or dropping the value on the way to the walk, left all 238 tests
# green - so the entire equal-start defence could vanish without a single
# failure. This codebase has now lost safety inputs that way twice. These
# tests exist so it cannot happen a third time.
# ---------------------------------------------------------------------------

def test_scan_collects_non_chrome_landmarks_separately():
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", FakeRange(0, 10)),
		FakeItem("region", FakeRange(20, 60)),
		FakeItem("contentinfo", FakeRange(90, 100)),
	]))
	chrome_starts = sorted(r.start for r in scan.chrome_ranges)
	other_starts = sorted(r.start for r in scan.other_ranges)
	assert chrome_starts == [0, 90]
	# The region is NOT an exclusion - it marks where an omitted nested
	# landmark could hide.
	assert other_starts == [20]


def test_a_non_chrome_landmark_still_advances_the_trust_boundary():
	# It was placed, so everything before it remains fully known.
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", FakeRange(0, 10)),
		FakeItem("region", FakeRange(20, 60)),
	]))
	assert scan.trust_boundary.start == 20


def test_an_unplaceable_non_chrome_landmark_freezes_trust_too():
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", FakeRange(0, 10)),
		FakeItem("region", None),
		FakeItem("contentinfo", FakeRange(90, 100)),
	]))
	assert scan.trust_boundary.start == 0
	assert scan.other_ranges == []


def test_select_scope_hands_the_non_chrome_ranges_to_the_caller():
	# The link in the chain that had no coverage at all: every previous
	# _select_scope test unpacked this value and then never asserted on it.
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", FakeRange(0, 10)),
		FakeItem("region", FakeRange(20, 60)),
		FakeItem("contentinfo", FakeRange(90, 100)),
	]))
	kind, scope_range, exclude, boundary, untrusted = ts._select_scope(scan)
	assert kind == "chrome-pos"
	assert untrusted is scan.other_ranges
	assert len(untrusted) == 1


def test_the_chain_end_to_end_protects_a_chunk_inside_a_region():
	# Scan -> select -> verdict, with no hand-built lists anywhere. A chunk
	# inside the emitted region defers to identity, because that is where an
	# omitted nested nav would be; a chunk outside every landmark does not.
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", FakeRange(0, 10)),
		FakeItem("region", FakeRange(20, 60)),
		FakeItem("contentinfo", FakeRange(90, 100)),
	]))
	_, _, exclude, boundary, untrusted = ts._select_scope(scan)
	assert ts._chrome_pos_verdict(FakeRange(30, 35), boundary, exclude, untrusted) is None
	assert ts._chrome_pos_verdict(FakeRange(70, 75), boundary, exclude, untrusted) is True
	assert ts._chrome_pos_verdict(FakeRange(2, 5), boundary, exclude, untrusted) is False


def test_ordering_comparison_failure_kills_chrome_pos():
	# The fail-closed path added this round, previously untested: an ordering
	# comparison we could not make means the order is UNKNOWN, and unknown
	# must not read as ordered.
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", FakeRange(0, 10)),
		FakeItem("navigation", ExplodingRange(20, 30)),
	]))
	assert scan.ordered is False
	kind, _, exclude, _b, _u = ts._select_scope(scan)
	assert kind == "chrome"
	assert exclude is None
