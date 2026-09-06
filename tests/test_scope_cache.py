# Scope-cache safety for treeSummary._inScope.
#
# The cache is keyed on id(obj) — a CPython memory address. The objects it
# describes are TRANSIENT: NVDA caches each fetched parent on its child, so a
# chain stays alive only while the child does, NVDA's global instance registry
# is weak and holds nothing, and _walkMainNodes rebinds `obj` on every chunk.
# CPython then hands the freed blocks back LIFO, so the next chunk's freshly
# allocated NVDAObjects land on exactly the addresses just cached.
#
# Before 2026-07-18 the cache stored {id(obj): bool} — the address alone. A
# dead entry therefore matched a LIVE, UNRELATED object and handed it the dead
# object's scope verdict. Adjacent chunks usually share a verdict, which masked
# it everywhere except the nav-to-content boundary — the one decision that
# decides whether the user lands on navigation text instead of the article.
#
# The fix is to store the object alongside the verdict so the entry PINS the
# address for the life of the cache. These tests pin that invariant, because it
# is invisible in the calling code and trivially undone by a future "the object
# in the value is unused, drop it" cleanup.
#
# _inScope is duck-typed over NVDAObjects (the NVDA imports in treeSummary
# are guarded), so fakes exercise it exactly.

import treeSummary as ts


class FakeObj:
	"""Minimal stand-in for an NVDAObject: a landmark type and a parent."""

	def __init__(self, landmark="", parent=None):
		self.landmark = landmark
		self.parent = parent


def _chain(*landmarks):
	"""Build a child-to-root chain; returns the deepest child.

	_chain("", "navigation") is a plain node inside a nav landmark.
	"""
	obj = None
	for lm in reversed(landmarks):
		obj = FakeObj(landmark=lm, parent=obj)
	return obj


# ---------------------------------------------------------------------------
# The invariant: every cache entry keeps the object it describes alive, and
# the key still matches that object's identity.
# ---------------------------------------------------------------------------

def test_cacheEntriesPinTheirObjects():
	cache = {}
	leaf = _chain("", "", "navigation")
	ts._inScope(leaf, None, cache)
	assert cache, "walk cached nothing — the memo is doing no work at all"
	for key, entry in cache.items():
		obj, verdict = entry
		assert isinstance(verdict, bool)
		# The stored object IS the one the key names. If the value were a
		# bare bool this could not be checked, which is the whole point:
		# nothing would stop the address being recycled underneath it.
		assert id(obj) == key


# ---------------------------------------------------------------------------
# The bug itself: a later, unrelated object must never inherit a dead
# object's verdict. Held addresses cannot be recycled, so this cannot recur
# while the invariant above holds.
# ---------------------------------------------------------------------------

def test_transientChainsDoNotInheritEachOthersVerdicts():
	cache = {}
	# Chrome first, then content — the nav-to-content boundary, walked with
	# transient chains exactly as the real walk does. Each iteration's chain
	# is garbage by the next iteration.
	verdicts = []
	for i in range(200):
		inNav = i < 100
		leaf = _chain("", "", "navigation" if inNav else "")
		verdicts.append(ts._inScope(leaf, None, cache))
		del leaf
	# No <main> anywhere, so: inside a chrome landmark is out of scope,
	# everything else is in scope. A false cache hit shows up here as a
	# content chunk answering False (or a nav chunk answering True).
	assert verdicts[:100] == [False] * 100
	assert verdicts[100:] == [True] * 100


# ---------------------------------------------------------------------------
# Diagnostics: the stats dict backs the [TMTS walk-phase] log line, which is
# how we find out whether the memo earns its keep on a real page.
# ---------------------------------------------------------------------------

def test_staleEntryUnderAMatchingKeyCannotHit():
	# Belt and braces for the invariant above: even if a future edit lets an
	# entry outlive the object it describes, a key collision must degrade to a
	# MISS (slower, correct) rather than returning the stale verdict. Forged
	# here by planting an entry whose key matches a live object but whose
	# stored object is a different one.
	cache = {}
	content = _chain("", "")
	decoy = _chain("", "navigation")
	cache[id(content)] = (decoy, False)
	# Not inside any chrome landmark, and no <main>, so the honest answer is
	# in-scope. Returning the planted False would mean the stale entry won.
	assert ts._inScope(content, None, cache) is True


def test_statsCountsMissesAndParentDerefs():
	cache = {}
	stats = {}
	ts._inScope(_chain("", "", "navigation"), None, cache, stats)
	assert stats.get("cache_misses") == 1
	assert stats.get("cache_hits", 0) == 0
	# Two parent hops to reach the nav landmark from the leaf.
	assert stats.get("parent_derefs") == 2


def test_statsCountsAHitOnTheSameObject():
	cache = {}
	stats = {}
	leaf = _chain("", "navigation")
	ts._inScope(leaf, None, cache, stats)
	ts._inScope(leaf, None, cache, stats)
	assert stats.get("cache_hits") == 1
	assert stats.get("cache_misses") == 1


# ---------------------------------------------------------------------------
# UNDECIDED IS NOT "IN SCOPE". Added 2026-07-18 after adversarial review.
#
# _inScope used to end with `result = mainObj is None` for EVERY way of
# leaving the parent walk without an answer — a parent dereference that raised,
# or a chain deeper than the 30-ancestor cap. On a page with no <main> that
# expression is True, so "we could not prove this is chrome" was returned as
# "this is proven content".
#
# It is worst exactly where the design leans on it hardest: chrome-pos routes
# its undecidable chunks to this filter AS its safety mechanism, and
# _formFieldInScope documented itself as failing closed while delegating
# here — so the path that calls setFocus() could drop a blind user's caret into
# a header search box on nothing more than one COM failure.
#
# _inScopeVerdict is now tri-state. The bool wrapper keeps the old default
# for callers whose policy really is "keep what you cannot classify"; the focus
# path takes the tri-state and refuses anything that is not True.
# ---------------------------------------------------------------------------

class ExplodingParent(FakeObj):
	"""An object whose parent dereference raises, like a COM call failing
	mid-chain."""

	@property
	def parent(self):
		raise RuntimeError("parent dereference failed (simulated COM error)")

	@parent.setter
	def parent(self, value):
		pass


def test_aFailedParentDereferenceIsUndecidedNotContent():
	obj = ExplodingParent(landmark="")
	assert ts._inScopeVerdict(obj, None, {}) is None, (
		"a COM failure mid-chain proves nothing about the ancestry; "
		"returning True here serves navigation as article text"
	)


def test_aChainDeeperThanTheCapIsUndecidedNotContent():
	# 40 plain ancestors, cap is 30: the walk runs out of budget before it
	# can reach anything conclusive.
	obj = _chain(*([""] * 40))
	assert ts._inScopeVerdict(obj, None, {}) is None


def test_runningOutOfAncestorsCleanlyISAnAnswer():
	# The one case the old blanket default got right, and the regression the
	# tri-state could most easily break: a complete chain with no chrome on it
	# is genuinely content, not "undecided".
	assert ts._inScopeVerdict(_chain("", "", ""), None, {}) is True


def test_aChromeAncestorStillDecidesAgainst():
	assert ts._inScopeVerdict(_chain("", "navigation"), None, {}) is False


def test_anUndecidedWalkCachesNothing():
	# The propagation half of the bug. The old code cached its unearned True
	# against EVERY ancestor visited on the way, so one COM failure handed the
	# same verdict to every sibling underneath that chain.
	cache: dict = {}
	ts._inScopeVerdict(ExplodingParent(landmark=""), None, cache)
	assert cache == {}, (
		"an undecided walk wrote a verdict into the cache; that is how a "
		"single failure becomes every sibling's answer"
	)


def test_theBoolWrapperKeepsTheOldDefaultForTheWalk():
	# Deliberate: the walk and the counts keep what they cannot classify (a
	# stray line read aloud is recoverable, and an undercount is poison for
	# the small-count intents). Only the focus path fails closed. If this ever
	# needs to change, change it on measurement, not by accident.
	assert ts._inScope(ExplodingParent(landmark=""), None, {}) is True
	assert ts._inScope(ExplodingParent(landmark=""), object(), {}) is False
