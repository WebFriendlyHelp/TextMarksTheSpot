# Budget / scan-cap / exception behavior of treeSummary's count helpers.
#
# These helpers are pure Python over a duck-typed treeInterceptor (NVDA
# imports in treeSummary are guarded), so we can exercise the exact
# pathological-page contracts with fake iterators:
#
#   1. An already-expired deadline starts NO new enumeration (zero fetches).
#   2. The scan cap stops FETCHING at the cap (item cap+1 is never pulled
#      from the iterator — the fetch is the hanging COM call on a stuck
#      page, so "process the item in hand, never fetch past the budget").
#   3. An iterator exception preserves the partial count AND sets the
#      truncated flag — an exception must never masquerade as a
#      trustworthy zero (it would sail through the small-count intents
#      that countsTruncated exists to protect).
#
# These pin the three release-blocking findings from the 2026-07-15
# independent review of the counts-budget hardening.

import time

import treeSummary as ts


class FakeItem:
	def __init__(self):
		self.obj = object()
		self.textInfo = None


class FakeTI:
	"""Duck-typed treeInterceptor: yields `count` items, tracking how many
	were actually pulled from the iterator. Raises after `raiseAfter`
	items when set."""

	def __init__(self, count, raiseAfter=None):
		self.count = count
		self.raiseAfter = raiseAfter
		self.fetched = 0

	def _iterNodesByType(self, itemType):
		for i in range(self.count):
			if self.raiseAfter is not None and i >= self.raiseAfter:
				raise RuntimeError("iterator died (simulated COM error)")
			self.fetched += 1
			yield FakeItem()


EXPIRED = time.monotonic() - 1.0
FAR_FUTURE = time.monotonic() + 3600.0


# ---------------------------------------------------------------------------
# Expired deadline: no new enumeration starts, truncated is set.
# ---------------------------------------------------------------------------


def test_countInRangeExpiredDeadlineFetchesNothing():
	ti = FakeTI(50)
	flag = [False]
	n = ts._countInRange(ti, "link", None, limit=0, deadline=EXPIRED, truncatedOut=flag)
	assert n == 0
	assert ti.fetched == 0
	assert flag[0] is True


def test_countInScopeExpiredDeadlineFetchesNothing():
	ti = FakeTI(50)
	flag = [False]
	n = ts._countInScope(ti, "link", None, {}, limit=0, deadline=EXPIRED, truncatedOut=flag)
	assert n == 0
	assert ti.fetched == 0
	assert flag[0] is True


def test_countFormInputsExpiredDeadlineSkipsEvenEdit():
	# The old code exempted the first type ("edit") from the clock, so a
	# phase budget already exhausted by the article count still launched a
	# fresh enumeration on the hanging page. Now nothing starts.
	ti = FakeTI(50)
	flag = [False]
	n = ts._countFormInputs(ti, None, None, {}, 10, deadline=EXPIRED, truncatedOut=flag)
	assert n == 0
	assert ti.fetched == 0
	assert flag[0] is True


def test_singleArticleScopeRangeExpiredDeadlineReturnsNone():
	ti = FakeTI(1)
	assert ts._singleArticleScopeRange(ti, deadline=EXPIRED) is None
	assert ti.fetched == 0


# ---------------------------------------------------------------------------
# Scan cap: stop FETCHING at the cap, set truncated, keep the partial count.
# ---------------------------------------------------------------------------


def test_countInRangeScanCapNeverFetchesPastCap():
	ti = FakeTI(ts._COUNT_SCAN_LIMIT + 100)
	flag = [False]
	n = ts._countInRange(ti, "link", None, limit=0, deadline=FAR_FUTURE, truncatedOut=flag)
	assert ti.fetched == ts._COUNT_SCAN_LIMIT
	assert n == ts._COUNT_SCAN_LIMIT
	assert flag[0] is True


def test_countInScopeScanCapNeverFetchesPastCap():
	ti = FakeTI(ts._COUNT_SCAN_LIMIT + 100)
	flag = [False]
	ts._countInScope(ti, "link", None, {}, limit=0, deadline=FAR_FUTURE, truncatedOut=flag)
	assert ti.fetched == ts._COUNT_SCAN_LIMIT
	assert flag[0] is True


def test_scanCapNotFlaggedWhenEnumerationFinishesFirst():
	ti = FakeTI(5)
	flag = [False]
	n = ts._countInRange(ti, "link", None, limit=0, deadline=FAR_FUTURE, truncatedOut=flag)
	assert n == 5
	assert flag[0] is False


def test_limitReachedIsNotTruncation():
	# Hitting the in-scope LIMIT is a completed answer ("at least N"), not
	# a truncation — the classifier only compares against thresholds below
	# the limit, so nothing was lost.
	ti = FakeTI(50)
	flag = [False]
	n = ts._countInRange(ti, "link", None, limit=11, deadline=FAR_FUTURE, truncatedOut=flag)
	assert n == 11
	assert flag[0] is False


# ---------------------------------------------------------------------------
# Iterator exception: partial count preserved, truncated set.
# ---------------------------------------------------------------------------


def test_countInRangeExceptionPreservesPartialCountAndFlags():
	ti = FakeTI(50, raiseAfter=7)
	flag = [False]
	n = ts._countInRange(ti, "link", None, limit=0, deadline=FAR_FUTURE, truncatedOut=flag)
	assert n == 7
	assert flag[0] is True


def test_countInScopeExceptionPreservesPartialCountAndFlags():
	ti = FakeTI(50, raiseAfter=7)
	flag = [False]
	n = ts._countInScope(ti, "link", None, {}, limit=0, deadline=FAR_FUTURE, truncatedOut=flag)
	assert n == 7
	assert flag[0] is True


def test_exceptionAtFirstItemIsNotATrustworthyZero():
	ti = FakeTI(50, raiseAfter=0)
	flag = [False]
	n = ts._countInRange(ti, "link", None, limit=0, deadline=FAR_FUTURE, truncatedOut=flag)
	assert n == 0
	assert flag[0] is True


# ---------------------------------------------------------------------------
# scannedOut: the passive [TMTS counts-phase] measurement. It must report the
# true items-scanned on every exit path and NEVER alter the count or the
# truncated flag (it is a probe, not a control signal).
# ---------------------------------------------------------------------------


def test_scannedOutMatchesFetchedOnFullScan():
	ti = FakeTI(40)
	scanned = [0]
	n = ts._countInRange(ti, "link", None, limit=0, deadline=FAR_FUTURE, scannedOut=scanned)
	assert n == 40
	assert scanned[0] == 40 == ti.fetched


def test_scannedOutCountsUpToTheLimitEarlyReturn():
	# The limit short-circuit returns mid-loop; scanned must reflect the items
	# actually pulled (the parent-chain cost we are trying to measure), not the
	# whole page.
	ti = FakeTI(500)
	scanned = [0]
	n = ts._countInScope(ti, "link", None, {}, limit=10, deadline=FAR_FUTURE, scannedOut=scanned)
	assert n == 10
	assert scanned[0] == 10 == ti.fetched


def test_scannedOutReachesScanCap():
	ti = FakeTI(5000)
	scanned = [0]
	flag = [False]
	ts._countInRange(ti, "link", None, limit=0, deadline=FAR_FUTURE, truncatedOut=flag, scannedOut=scanned)
	assert scanned[0] == ts._COUNT_SCAN_LIMIT
	assert flag[0] is True


def test_scannedOutAccumulatesAcrossFormTypes():
	# _countFormInputs sums four enumerations; scannedOut must accumulate
	# across all of them so the "forms" call site reports total items scanned.
	ti = FakeTI(3)  # scopeRange=None counts every item, so 3 per type
	scanned = [0]
	n = ts._countFormInputs(ti, None, None, {}, 100, deadline=FAR_FUTURE, scannedOut=scanned)
	assert n == 12  # 4 types * 3
	assert scanned[0] == 12


def test_scannedOutDoesNotChangeCountOrTruncation():
	# Same inputs, with and without the probe: identical count and flag.
	a = ts._countInRange(
		FakeTI(50, raiseAfter=7), "link", None, limit=0, deadline=FAR_FUTURE, truncatedOut=(fa := [False])
	)
	b = ts._countInRange(
		FakeTI(50, raiseAfter=7),
		"link",
		None,
		limit=0,
		deadline=FAR_FUTURE,
		truncatedOut=(fb := [False]),
		scannedOut=[0],
	)
	assert a == b == 7
	assert fa[0] == fb[0] is True
