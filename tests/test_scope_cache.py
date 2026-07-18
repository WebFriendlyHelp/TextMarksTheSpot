# Scope-cache safety for tree_summary._in_scope.
#
# The cache is keyed on id(obj) — a CPython memory address. The objects it
# describes are TRANSIENT: NVDA caches each fetched parent on its child, so a
# chain stays alive only while the child does, NVDA's global instance registry
# is weak and holds nothing, and _walk_main_nodes rebinds `obj` on every chunk.
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
# _in_scope is duck-typed over NVDAObjects (the NVDA imports in tree_summary
# are guarded), so fakes exercise it exactly.

import tree_summary as ts


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

def test_cache_entries_pin_their_objects():
	cache = {}
	leaf = _chain("", "", "navigation")
	ts._in_scope(leaf, None, cache)
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

def test_transient_chains_do_not_inherit_each_others_verdicts():
	cache = {}
	# Chrome first, then content — the nav-to-content boundary, walked with
	# transient chains exactly as the real walk does. Each iteration's chain
	# is garbage by the next iteration.
	verdicts = []
	for i in range(200):
		in_nav = i < 100
		leaf = _chain("", "", "navigation" if in_nav else "")
		verdicts.append(ts._in_scope(leaf, None, cache))
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

def test_stale_entry_under_a_matching_key_cannot_hit():
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
	assert ts._in_scope(content, None, cache) is True


def test_stats_counts_misses_and_parent_derefs():
	cache = {}
	stats = {}
	ts._in_scope(_chain("", "", "navigation"), None, cache, stats)
	assert stats.get("cache_misses") == 1
	assert stats.get("cache_hits", 0) == 0
	# Two parent hops to reach the nav landmark from the leaf.
	assert stats.get("parent_derefs") == 2


def test_stats_counts_a_hit_on_the_same_object():
	cache = {}
	stats = {}
	leaf = _chain("", "navigation")
	ts._in_scope(leaf, None, cache, stats)
	ts._in_scope(leaf, None, cache, stats)
	assert stats.get("cache_hits") == 1
	assert stats.get("cache_misses") == 1
