# Budget / scan-cap / exception behavior of tree_summary's count helpers.
#
# These helpers are pure Python over a duck-typed treeInterceptor (NVDA
# imports in tree_summary are guarded), so we can exercise the exact
# pathological-page contracts with fake iterators:
#
#   1. An already-expired deadline starts NO new enumeration (zero fetches).
#   2. The scan cap stops FETCHING at the cap (item cap+1 is never pulled
#      from the iterator — the fetch is the hanging COM call on a stuck
#      page, so "process the item in hand, never fetch past the budget").
#   3. An iterator exception preserves the partial count AND sets the
#      truncated flag — an exception must never masquerade as a
#      trustworthy zero (it would sail through the small-count intents
#      that counts_truncated exists to protect).
#
# These pin the three release-blocking findings from the 2026-07-15
# independent review of the counts-budget hardening.

import time

import tree_summary as ts


class FakeItem:
	def __init__(self):
		self.obj = object()
		self.textInfo = None


class FakeTI:
	"""Duck-typed treeInterceptor: yields `count` items, tracking how many
	were actually pulled from the iterator. Raises after `raise_after`
	items when set."""

	def __init__(self, count, raise_after=None):
		self.count = count
		self.raise_after = raise_after
		self.fetched = 0

	def _iterNodesByType(self, item_type):
		for i in range(self.count):
			if self.raise_after is not None and i >= self.raise_after:
				raise RuntimeError("iterator died (simulated COM error)")
			self.fetched += 1
			yield FakeItem()


EXPIRED = time.monotonic() - 1.0
FAR_FUTURE = time.monotonic() + 3600.0


# ---------------------------------------------------------------------------
# Expired deadline: no new enumeration starts, truncated is set.
# ---------------------------------------------------------------------------

def test_count_in_range_expired_deadline_fetches_nothing():
	ti = FakeTI(50)
	flag = [False]
	n = ts._count_in_range(ti, "link", None, limit=0, deadline=EXPIRED, truncated_out=flag)
	assert n == 0
	assert ti.fetched == 0
	assert flag[0] is True


def test_count_in_scope_expired_deadline_fetches_nothing():
	ti = FakeTI(50)
	flag = [False]
	n = ts._count_in_scope(ti, "link", None, {}, limit=0, deadline=EXPIRED, truncated_out=flag)
	assert n == 0
	assert ti.fetched == 0
	assert flag[0] is True


def test_count_form_inputs_expired_deadline_skips_even_edit():
	# The old code exempted the first type ("edit") from the clock, so a
	# phase budget already exhausted by the article count still launched a
	# fresh enumeration on the hanging page. Now nothing starts.
	ti = FakeTI(50)
	flag = [False]
	n = ts._count_form_inputs(ti, None, None, {}, 10, deadline=EXPIRED, truncated_out=flag)
	assert n == 0
	assert ti.fetched == 0
	assert flag[0] is True


def test_single_article_scope_range_expired_deadline_returns_none():
	ti = FakeTI(1)
	assert ts._single_article_scope_range(ti, deadline=EXPIRED) is None
	assert ti.fetched == 0


# ---------------------------------------------------------------------------
# Scan cap: stop FETCHING at the cap, set truncated, keep the partial count.
# ---------------------------------------------------------------------------

def test_count_in_range_scan_cap_never_fetches_past_cap():
	ti = FakeTI(ts._COUNT_SCAN_LIMIT + 100)
	flag = [False]
	n = ts._count_in_range(ti, "link", None, limit=0, deadline=FAR_FUTURE, truncated_out=flag)
	assert ti.fetched == ts._COUNT_SCAN_LIMIT
	assert n == ts._COUNT_SCAN_LIMIT
	assert flag[0] is True


def test_count_in_scope_scan_cap_never_fetches_past_cap():
	ti = FakeTI(ts._COUNT_SCAN_LIMIT + 100)
	flag = [False]
	ts._count_in_scope(ti, "link", None, {}, limit=0, deadline=FAR_FUTURE, truncated_out=flag)
	assert ti.fetched == ts._COUNT_SCAN_LIMIT
	assert flag[0] is True


def test_scan_cap_not_flagged_when_enumeration_finishes_first():
	ti = FakeTI(5)
	flag = [False]
	n = ts._count_in_range(ti, "link", None, limit=0, deadline=FAR_FUTURE, truncated_out=flag)
	assert n == 5
	assert flag[0] is False


def test_limit_reached_is_not_truncation():
	# Hitting the in-scope LIMIT is a completed answer ("at least N"), not
	# a truncation — the classifier only compares against thresholds below
	# the limit, so nothing was lost.
	ti = FakeTI(50)
	flag = [False]
	n = ts._count_in_range(ti, "link", None, limit=11, deadline=FAR_FUTURE, truncated_out=flag)
	assert n == 11
	assert flag[0] is False


# ---------------------------------------------------------------------------
# Iterator exception: partial count preserved, truncated set.
# ---------------------------------------------------------------------------

def test_count_in_range_exception_preserves_partial_count_and_flags():
	ti = FakeTI(50, raise_after=7)
	flag = [False]
	n = ts._count_in_range(ti, "link", None, limit=0, deadline=FAR_FUTURE, truncated_out=flag)
	assert n == 7
	assert flag[0] is True


def test_count_in_scope_exception_preserves_partial_count_and_flags():
	ti = FakeTI(50, raise_after=7)
	flag = [False]
	n = ts._count_in_scope(ti, "link", None, {}, limit=0, deadline=FAR_FUTURE, truncated_out=flag)
	assert n == 7
	assert flag[0] is True


def test_exception_at_first_item_is_not_a_trustworthy_zero():
	ti = FakeTI(50, raise_after=0)
	flag = [False]
	n = ts._count_in_range(ti, "link", None, limit=0, deadline=FAR_FUTURE, truncated_out=flag)
	assert n == 0
	assert flag[0] is True
