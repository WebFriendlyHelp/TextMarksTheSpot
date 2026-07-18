# Positional chrome scoping: the landmark-scan completeness contract and the
# start-position exclusion test.
#
# Background (2026-07-18). A page with no <main> and no single <article> used
# to decide "is this chunk content?" by climbing each chunk's ancestors looking
# for a chrome landmark — up to 30 levels, every level a COM call into the
# browser. Measured on store.payproglobal.com's checkout: of a 2035 ms walk,
# 1808 ms was that climb (341 parent dereferences for 33 paragraphs), against
# 223 ms for object resolution and 2 ms for expand and text combined.
#
# The replacement asks the same question from the other side: collect the
# CHROME landmark ranges during the landmark enumeration that already happens,
# then exclude any chunk STARTING inside one. Offset arithmetic, no browser
# calls.
#
# The danger is entirely in the failure direction. The landmark enumeration can
# stop early (0.5 s budget, 50-item cap, iterator exception), and a truncated
# scan yields a PARTIAL chrome inventory. Used as if complete, a navigation
# block nobody enumerated stops looking like navigation, becomes content, and a
# blind user lands in a menu instead of the article. So a partial inventory is
# never a partial answer: anything short of natural exhaustion falls back to
# the old identity path, slow and correct. These tests pin that interlock from
# every direction it can fail, because it is invisible at the call site.

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
	"""Duck-typed treeInterceptor yielding a fixed landmark list. `slow_after`
	makes each subsequent fetch burn wall clock so the real deadline fires."""

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


# ---------------------------------------------------------------------------
# Completeness: the interlock. Only natural exhaustion counts.
# ---------------------------------------------------------------------------

def test_clean_scan_with_chrome_landmarks_is_complete():
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", FakeRange(0, 10)),
		FakeItem("contentinfo", FakeRange(90, 100)),
	]))
	assert scan.complete is True
	assert scan.main_obj is None
	assert len(scan.chrome_ranges) == 2


def test_no_landmarks_at_all_is_complete_with_an_empty_list():
	# The landmark-free page: a complete scan that excludes nothing. This is
	# the biggest win, not a degenerate case — it is the page that used to pay
	# a full 30-level parent climb per chunk to arrive at "in scope".
	scan = ts._find_main_landmark(FakeTI([]))
	assert scan.complete is True
	assert scan.chrome_ranges == []


def test_non_chrome_non_main_landmarks_are_ignored_but_keep_completeness():
	# A "region" landmark is neither content-defining nor chrome; it should
	# neither be excluded nor spoil the scan.
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("region", FakeRange(0, 10)),
		FakeItem("navigation", FakeRange(20, 30)),
	]))
	assert scan.complete is True
	assert len(scan.chrome_ranges) == 1


def test_iterator_exception_marks_incomplete():
	scan = ts._find_main_landmark(FakeTI(
		[FakeItem("navigation", FakeRange(0, 10)) for _ in range(5)],
		raise_after=2,
	))
	assert scan.complete is False


def test_scan_cap_marks_incomplete():
	scan = ts._find_main_landmark(FakeTI(
		[FakeItem("navigation", FakeRange(i, i + 1))
		 for i in range(ts._FIND_MAIN_SCAN_LIMIT + 10)]
	))
	assert scan.complete is False


def test_deadline_marks_incomplete():
	scan = ts._find_main_landmark(FakeTI(
		[FakeItem("navigation", FakeRange(i, i + 1)) for i in range(5)],
		slow_after=1,
	))
	assert scan.complete is False


def test_chrome_landmark_without_a_textinfo_marks_incomplete():
	# We cannot place this nav block, so we cannot exclude it. Guessing would
	# mean serving its contents as article text.
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", None),
		FakeItem("contentinfo", FakeRange(90, 100)),
	]))
	assert scan.complete is False


def test_degenerate_chrome_range_marks_incomplete():
	# A collapsed range excludes nothing, so treating it as a real exclusion
	# would silently admit the whole landmark.
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", FakeRange(10, 10)),
	]))
	assert scan.complete is False


def test_uncopyable_chrome_range_marks_incomplete():
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", NoCopyRange(0, 10)),
	]))
	assert scan.complete is False


def test_unresolvable_landmark_item_marks_incomplete():
	# An item whose obj is None cannot be classified, so we do not know
	# whether it was the navigation. The old identity filter tolerated this
	# because it asked each CHUNK about its own ancestors — a separate object
	# instance that could still answer "navigation". Positional exclusion has
	# only this inventory to go on, so an unclassifiable entry poisons it.
	item = FakeItem("navigation", FakeRange(0, 10))
	item.obj = None
	scan = ts._find_main_landmark(FakeTI([item, FakeItem("contentinfo", FakeRange(90, 100))]))
	assert scan.complete is False


def test_inverted_chrome_range_marks_incomplete():
	# start past end matches nothing in _starts_in_any, so treating it as a
	# real exclusion would quietly admit the whole landmark.
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", FakeRange(20, 10)),
	]))
	assert scan.complete is False


def test_finding_main_returns_early_and_is_not_complete():
	# Returning at <main> leaves the chrome inventory partial by construction.
	# Harmless (a <main> page scopes by main_range) but it must not claim to
	# be complete.
	scan = ts._find_main_landmark(FakeTI([
		FakeItem("navigation", FakeRange(0, 10)),
		FakeItem("main", FakeRange(10, 90)),
		FakeItem("contentinfo", FakeRange(90, 100)),
	]))
	assert scan.main_obj is not None
	assert scan.main_range is not None
	assert scan.complete is False


def test_ranges_are_private_copies():
	# The walk compares against these long after the scan; a live reference
	# could be repositioned underneath us.
	original = FakeRange(0, 10)
	scan = ts._find_main_landmark(FakeTI([FakeItem("navigation", original)]))
	assert scan.chrome_ranges[0] is not original


# ---------------------------------------------------------------------------
# The gate that consumes `complete`. Every bit of safety in this change
# funnels through _select_scope, and build_tree_summary (its only caller)
# cannot run outside NVDA — so without these the decisive test would be the
# one line in the module with no coverage.
# ---------------------------------------------------------------------------

def test_incomplete_scan_falls_back_to_the_identity_path():
	kind, scope_range, exclude = ts._select_scope(
		ts.LandmarkScan(None, None, [FakeRange(0, 10)], complete=False)
	)
	assert kind == "chrome"
	# The partial inventory must NOT be handed on as an exclusion list.
	assert exclude is None
	assert scope_range is None


def test_complete_scan_enables_positional_chrome():
	ranges = [FakeRange(0, 10)]
	kind, scope_range, exclude = ts._select_scope(
		ts.LandmarkScan(None, None, ranges, complete=True)
	)
	assert kind == "chrome-pos"
	assert exclude is ranges
	assert scope_range is None


def test_complete_scan_with_no_chrome_landmarks_excludes_nothing():
	kind, scope_range, exclude = ts._select_scope(
		ts.LandmarkScan(None, None, [], complete=True)
	)
	assert kind == "chrome-pos"
	assert exclude == []


def test_main_page_never_uses_chrome_exclusion():
	# Even if a chrome list came back non-empty, a <main> page scopes INTO
	# main and must not also carry an exclusion list — the walk and the
	# counts disagree about how to combine the two.
	kind, scope_range, exclude = ts._select_scope(
		ts.LandmarkScan(FakeObj("main"), FakeRange(10, 90), [FakeRange(0, 10)], complete=True)
	)
	assert kind == "main-pos"
	assert scope_range is not None
	assert exclude is None


def test_main_without_a_usable_range_uses_identity():
	kind, scope_range, exclude = ts._select_scope(
		ts.LandmarkScan(FakeObj("main"), None, [], complete=False)
	)
	assert kind == "main-id"
	assert scope_range is None
	assert exclude is None


def test_scope_selection_never_returns_both_a_range_and_an_exclusion():
	# The invariant _walk_main_nodes and _count_in_range depend on, checked
	# across every combination the scan can produce.
	for main_obj in (None, FakeObj("main")):
		for main_range in (None, FakeRange(10, 90)):
			for complete in (False, True):
				_, scope_range, exclude = ts._select_scope(
					ts.LandmarkScan(main_obj, main_range, [FakeRange(0, 10)], complete)
				)
				assert scope_range is None or exclude is None


# ---------------------------------------------------------------------------
# The exclusion test itself: START position, not containment.
# ---------------------------------------------------------------------------

NAV = FakeRange(0, 10)
FOOT = FakeRange(90, 100)


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
	# filter it replaces — that asks about the object at the chunk's START.
	assert ts._starts_in_any(FakeRange(8, 40), [NAV]) is True


def test_nested_and_overlapping_ranges_agree():
	banner = FakeRange(0, 50)
	nav_inside = FakeRange(10, 20)
	assert ts._starts_in_any(FakeRange(12, 15), [banner, nav_inside]) is True
	assert ts._starts_in_any(FakeRange(60, 65), [banner, nav_inside]) is False


def test_empty_range_list_excludes_nothing():
	assert ts._starts_in_any(FakeRange(2, 5), []) is False


def test_comparison_failure_keeps_the_chunk():
	# Inclusive bias, matching the rest of the module: showing a line of
	# navigation is recoverable, hiding the article is not.
	assert ts._starts_in_any(ExplodingRange(2, 5), [NAV]) is False


# ---------------------------------------------------------------------------
# Counts honour the same exclusion, so the counts phase stops paying for
# parent chains too (it was 619 ms of the 2663 ms checkout load).
# ---------------------------------------------------------------------------

class CountItem:
	def __init__(self, rng):
		self.textInfo = rng
		# Present so a regression that reads .obj here (the expensive path
		# this replaces) is visible rather than silent.
		self.obj = FakeObj("")


class CountTI:
	def __init__(self, ranges):
		self.ranges = ranges

	def _iterNodesByType(self, item_type):
		for r in self.ranges:
			yield CountItem(r)


FAR_FUTURE = time.monotonic() + 3600.0


def test_counts_skip_items_starting_in_chrome():
	ti = CountTI([FakeRange(1, 2), FakeRange(5, 6), FakeRange(40, 41), FakeRange(95, 96)])
	n = ts._count_in_range(ti, "edit", None, deadline=FAR_FUTURE, exclude_ranges=[NAV, FOOT])
	assert n == 1


def test_counts_with_an_empty_exclusion_list_count_everything():
	ti = CountTI([FakeRange(1, 2), FakeRange(40, 41)])
	n = ts._count_in_range(ti, "edit", None, deadline=FAR_FUTURE, exclude_ranges=[])
	assert n == 2


def test_counts_keep_items_with_no_textinfo():
	# Inclusive bias again: an item we cannot place still counts.
	ti = CountTI([None, FakeRange(1, 2)])
	n = ts._count_in_range(ti, "edit", None, deadline=FAR_FUTURE, exclude_ranges=[NAV])
	assert n == 1
