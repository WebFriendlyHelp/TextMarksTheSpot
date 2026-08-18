# Re-anchoring a drifted landing by TEXT, driven end to end.
#
# WHY THIS FILE EXISTS. `find_landing_by_text` is the last thing standing
# between a drifted capture and a silent page. It used to do ONE literal search
# at the full width of the 60-char walk-time preview, and that search was
# strictly harder to satisfy than the check that judges its own result:
#
#   * WIDTH. web.landing_text_matches compares LANDING_MATCH_CHARS (24). We
#     demanded 60 to recover a landing we would then accept on 24.
#   * NORMALIZATION. NVDA's OffsetsTextInfo.find is literal
#     (re.search(re.escape(text), ...) over the raw buffer). The verifier
#     collapses whitespace runs and NBSPs first. A lede whose NBSPs came back
#     as ordinary spaces after a rebuild failed the SEARCH while being exactly
#     what the CHECK would have accepted.
#
# The fix tries descending prefixes plus the plain-space form. The tests below
# drive the REAL function against a fake buffer rather than asserting about the
# pure helper alone: on this project three separate safety inputs were found
# deletable with the whole suite still green, every one of them because the
# rule was tested and the WIRING was not.

import pytest

import tree_summary as ts
from detection import web

NBSP = "\xa0"


class _FakeTextInfos:
	POSITION_FIRST = "POSITION_FIRST"
	POSITION_ALL = "POSITION_ALL"
	UNIT_PARAGRAPH = "UNIT_PARAGRAPH"


class FakeInfo:
	"""Mirrors the bits of OffsetsTextInfo the finder touches.

	`find` is deliberately faithful to NVDA's: a LITERAL search (no
	normalisation of any kind) that starts at _startOffset + 1. That +1 is real
	-- NVDA does `_getTextRange(self._startOffset + 1, ...)` -- and a fake that
	searched from 0 would hide the one edge it creates.
	"""

	def __init__(self, doc, offset=0, whole=False):
		self.doc = doc
		self.offset = offset
		self.whole = whole

	@property
	def text(self):
		if self.whole:
			return self.doc.full
		return self.doc.paragraph_at(self.offset)

	def copy(self):
		return FakeInfo(self.doc, self.offset, self.whole)

	def collapse(self):
		self.whole = False

	def expand(self, unit):
		assert unit == _FakeTextInfos.UNIT_PARAGRAPH
		self.whole = False

	def find(self, needle, caseSensitive=False):
		self.doc.find_calls.append(needle)
		idx = self.doc.full.find(needle, self.offset + 1)
		if idx < 0:
			return False
		self.offset = idx
		self.whole = False
		return True


class FakeDoc:
	"""Paragraphs joined by newlines, with offset to paragraph lookup."""

	def __init__(self, paragraphs):
		self.paragraphs = list(paragraphs)
		self.full = "\n".join(self.paragraphs)
		self.find_calls = []
		self.all_fetches = 0

	def paragraph_at(self, offset):
		pos = 0
		for p in self.paragraphs:
			end = pos + len(p)
			if pos <= offset <= end:
				return p
			pos = end + 1
		return ""

	def makeTextInfo(self, position):
		if position == _FakeTextInfos.POSITION_ALL:
			self.all_fetches += 1
			return FakeInfo(self, 0, whole=True)
		return FakeInfo(self, 0, whole=False)


class Node:
	def __init__(self, text_preview):
		self.text_preview = text_preview


@pytest.fixture(autouse=True)
def _fake_nvda(monkeypatch):
	monkeypatch.setattr(ts, "textInfos", _FakeTextInfos, raising=False)
	monkeypatch.setattr(ts, "_NVDA_AVAILABLE", True)


def verifier_for(node):
	return lambda found: web.landing_text_matches(found, node)


# ---------------------------------------------------------------------------
# Shape of the needle ladder.
# ---------------------------------------------------------------------------

def test_search_floor_is_below_the_verification_width():
	# Worth holding, but note what it is NOT: this ordering was once written
	# down as the reason shortening is safe, and it is far too weak for that.
	# Four characters of margin does not stop a repeated opening -- see
	# test_the_verifier_alone_would_not_catch_a_repeated_opening, which
	# measures it. Uniqueness is the safety property. This just keeps the
	# verifier from being narrower than the shortest thing we search for,
	# which would make it useless as the second check.
	assert ts._MIN_FIND_NEEDLE_CHARS < web.LANDING_MATCH_CHARS


def test_candidates_never_fall_below_the_floor():
	for needle in ("x" * 60, "word " * 12, "short one here ok now", "a b c d e f g h"):
		for cand in ts._needle_candidates(needle):
			assert len(cand) >= ts._MIN_FIND_NEEDLE_CHARS, (needle, cand)


def test_candidates_are_longest_first_and_start_with_the_full_needle():
	needle = "The council voted on Tuesday to approve the new transit levy plan"
	cands = ts._needle_candidates(needle)
	assert cands[0] == needle
	lengths = [len(c) for c in cands]
	assert lengths == sorted(lengths, reverse=True), lengths


def test_candidates_are_deduped():
	cands = ts._needle_candidates("The council voted Tuesday on a levy")
	assert len(cands) == len(set(cands))


# ---------------------------------------------------------------------------
# The two failures that motivated the change.
# ---------------------------------------------------------------------------

LEDE = "The council voted on Tuesday to approve the new transit levy"


def test_recovers_when_the_tail_of_the_preview_changed():
	# Hydration rewrote the paragraph past char ~40 (a link got injected, the
	# byline resolved). The full-width needle cannot match; the head still can.
	doc = FakeDoc([
		"Skip to main content",
		"The council voted on Tuesday to approve a revised transit levy today",
	])
	node = Node(LEDE)
	info = ts.find_landing_by_text(doc, LEDE, verify=verifier_for(node))
	assert info is not None, "a recoverable landing was thrown away"
	info.expand(_FakeTextInfos.UNIT_PARAGRAPH)
	assert info.text.startswith("The council voted on Tuesday")


def test_full_width_search_alone_would_have_failed_that_page():
	# Pins the premise of the test above: without a verifier we do exactly one
	# full-width search, and on this page it finds nothing. If this ever starts
	# passing, the previous test is no longer testing what it claims.
	doc = FakeDoc([
		"Skip to main content",
		"The council voted on Tuesday to approve a revised transit levy today",
	])
	assert ts.find_landing_by_text(doc, LEDE) is None
	assert len(doc.find_calls) == 1


def test_recovers_when_nbsps_came_back_as_ordinary_spaces():
	# The walk captured the NBSPs news sites litter through their ledes; the
	# rebuilt buffer has plain spaces. find() is literal, so the raw needle
	# misses, while the verifier would have accepted the paragraph happily.
	captured = "The council voted on" + NBSP + "Tuesday to approve the new transit levy"
	doc = FakeDoc([
		"Skip to main content",
		"The council voted on Tuesday to approve the new transit levy",
	])
	node = Node(captured)
	info = ts.find_landing_by_text(doc, captured, verify=verifier_for(node))
	assert info is not None, "an NBSP swap silenced a landing that was right there"
	info.expand(_FakeTextInfos.UNIT_PARAGRAPH)
	assert info.text.startswith("The council voted")


# ---------------------------------------------------------------------------
# Safety: a shorter needle must not be allowed to speak the wrong paragraph.
# ---------------------------------------------------------------------------

def test_the_verifier_alone_would_not_catch_a_repeated_opening():
	# Measured, not assumed, and the reason the uniqueness rule exists.
	# landing_text_matches compares 24 normalised characters, so a teaser that
	# repeats its own lede's opening IS accepted as the lede. Any design that
	# leans on the verifier to police shortened needles is leaning on this.
	teaser = "The council voted on Tuesday, and here is what else you missed"
	assert web.landing_text_matches(teaser, Node(LEDE)) is True


def test_an_ambiguous_rung_is_refused_even_though_the_verifier_would_pass_it():
	# The lede's opening also opens a "related stories" teaser -- the Daily Mail
	# box shape. Every shortened rung therefore matches in two places, find()
	# would return the first, and the verifier (see the test above) would wave
	# it through. Uniqueness is what has to stop this.
	#
	# Note the teaser is deliberately NOT the first paragraph. An earlier draft
	# of this test put it at offset 0, where find()'s _startOffset + 1 start
	# skips it, and the test passed for that reason instead of for the rule --
	# green, and testing nothing.
	#
	# The tail of the real lede drifted, so the full-width needle misses and
	# shortening is genuinely needed here -- which is exactly when the teaser
	# becomes dangerous, because it shares the whole opening the rungs cut back
	# to.
	doc = FakeDoc([
		"Skip to main content",
		"The council voted on Tuesday to approve the measure, and here is "
		"what else you missed this week",
		"The council voted on Tuesday to approve a revised transit levy today",
	])
	node = Node(LEDE)
	assert doc.full.count("The council voted on Tuesday to approve") == 2, (
		"the page this test describes is not the page it built"
	)
	info = ts.find_landing_by_text(doc, LEDE, verify=verifier_for(node))
	assert info is None, (
		"a shortened needle that matched in two places was used anyway; "
		"find() returns the FIRST hit, so this is the wrong paragraph being "
		"spoken to a blind user"
	)


def test_an_unambiguous_rung_still_wins_on_a_page_that_has_a_teaser():
	# The counterweight to the test above, and the reason it is not enough to
	# refuse every page with a teaser on it. Here the teaser diverges early, so
	# the rung that cuts back past the divergence is still unique and the real
	# lede is still reached. If this ever starts returning None, the uniqueness
	# rule has been tightened into a page-wide veto.
	doc = FakeDoc([
		"Skip to main content",
		"Also today: what else you missed this week in local government news",
		"The council voted on Tuesday to approve a revised transit levy today",
	])
	node = Node(LEDE)
	info = ts.find_landing_by_text(doc, LEDE, verify=verifier_for(node))
	assert info is not None, "an unambiguous shortened rung was refused"
	info.expand(_FakeTextInfos.UNIT_PARAGRAPH)
	assert info.text.startswith("The council voted on Tuesday to approve a revised")


def test_a_unique_rung_inside_another_paragraph_is_rejected_by_the_verifier():
	# The rung is unique, so uniqueness is satisfied and cannot help. But the
	# only copy sits MID-paragraph, because our chosen lede was requoted inside
	# a longer block during the rebuild. Landing there would start the user in
	# the middle of someone else's sentence, so the verifier -- which asks
	# whether the found paragraph STARTS with what we chose -- has to refuse it.
	doc = FakeDoc([
		"Skip to main content",
		"As we reported earlier, The council voted on Tuesday to approve "
		"the new transit levy, which drew immediate criticism from commuters",
	])
	node = Node(LEDE)
	info = ts.find_landing_by_text(doc, LEDE, verify=verifier_for(node))
	assert info is None, (
		"a unique hit buried mid-paragraph was accepted; uniqueness proves "
		"there is one hit, only the verifier proves the hit is a paragraph "
		"that begins with what the classifier chose"
	)


def test_shortening_is_gated_on_a_verifier_being_supplied():
	# With no verifier there is nothing to catch a false hit, so the finder
	# must not shorten. One search, full width, exactly as before.
	doc = FakeDoc([
		"Skip to main content",
		"The council voted on Tuesday to approve a revised transit levy today",
	])
	assert ts.find_landing_by_text(doc, LEDE) is None
	assert doc.find_calls == [LEDE], doc.find_calls
	assert doc.all_fetches == 0, "the unverified path must not pull the buffer copy"


# ---------------------------------------------------------------------------
# Budget. find() re-fetches the whole remaining story text on every call, so
# the ladder must not be run blind.
# ---------------------------------------------------------------------------

def test_absent_candidates_never_cost_a_real_search():
	# Nothing on this page resembles the needle. The buffer copy is taken once
	# and every rung is ruled out against it, so no find() is paid for at all.
	doc = FakeDoc(["Cookies", "We value your privacy and use cookies to improve"])
	node = Node(LEDE)
	assert ts.find_landing_by_text(doc, LEDE, verify=verifier_for(node)) is None
	assert doc.find_calls == [], doc.find_calls
	assert doc.all_fetches == 1, doc.all_fetches


def test_the_happy_path_costs_one_search():
	doc = FakeDoc(["Skip to main content", LEDE])
	node = Node(LEDE)
	info = ts.find_landing_by_text(doc, LEDE, verify=verifier_for(node))
	assert info is not None
	assert doc.find_calls == [LEDE], doc.find_calls
	assert doc.all_fetches == 1


def test_a_needle_below_the_floor_is_refused_outright():
	doc = FakeDoc(["short", "another"])
	node = Node("short")
	assert ts.find_landing_by_text(doc, "short", verify=verifier_for(node)) is None
	assert doc.find_calls == []
