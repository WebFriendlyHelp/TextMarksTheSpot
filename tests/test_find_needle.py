# Re-anchoring a drifted landing by TEXT, driven end to end.
#
# WHY THIS FILE EXISTS. `findLandingByText` is the last thing standing
# between a drifted capture and a silent page. It used to do ONE literal search
# at the full width of the 60-char walk-time preview, and that search was
# strictly harder to satisfy than the check that judges its own result:
#
#   * WIDTH. web.landingTextMatches compares LANDING_MATCH_CHARS (24). We
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

import treeSummary as ts
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
		return self.doc.paragraphAt(self.offset)

	def copy(self):
		return FakeInfo(self.doc, self.offset, self.whole)

	def collapse(self):
		self.whole = False

	def expand(self, unit):
		assert unit == _FakeTextInfos.UNIT_PARAGRAPH
		self.whole = False

	def find(self, needle, caseSensitive=False):
		self.doc.findCalls.append(needle)
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
		self.findCalls = []
		self.allFetches = 0

	def paragraphAt(self, offset):
		pos = 0
		for p in self.paragraphs:
			end = pos + len(p)
			if pos <= offset <= end:
				return p
			pos = end + 1
		return ""

	def makeTextInfo(self, position):
		if position == _FakeTextInfos.POSITION_ALL:
			self.allFetches += 1
			return FakeInfo(self, 0, whole=True)
		return FakeInfo(self, 0, whole=False)


class Node:
	def __init__(self, textPreview):
		self.textPreview = textPreview


@pytest.fixture(autouse=True)
def _fakeNvda(monkeypatch):
	monkeypatch.setattr(ts, "textInfos", _FakeTextInfos, raising=False)
	monkeypatch.setattr(ts, "_NVDA_AVAILABLE", True)


def verifierFor(node):
	return lambda found: web.landingTextMatches(found, node)


# ---------------------------------------------------------------------------
# Shape of the needle ladder.
# ---------------------------------------------------------------------------

def test_searchFloorIsBelowTheVerificationWidth():
	# Worth holding, but note what it is NOT: this ordering was once written
	# down as the reason shortening is safe, and it is far too weak for that.
	# Four characters of margin does not stop a repeated opening -- see
	# test_theVerifierAloneWouldNotCatchARepeatedOpening, which
	# measures it. Uniqueness is the safety property. This just keeps the
	# verifier from being narrower than the shortest thing we search for,
	# which would make it useless as the second check.
	assert ts._MIN_FIND_NEEDLE_CHARS < web.LANDING_MATCH_CHARS


def test_candidatesNeverFallBelowTheFloor():
	for needle in ("x" * 60, "word " * 12, "short one here ok now", "a b c d e f g h"):
		for cand in ts._needleCandidates(needle):
			assert len(cand) >= ts._MIN_FIND_NEEDLE_CHARS, (needle, cand)


def test_candidatesAreLongestFirstAndStartWithTheFullNeedle():
	needle = "The council voted on Tuesday to approve the new transit levy plan"
	cands = ts._needleCandidates(needle)
	assert cands[0] == needle
	lengths = [len(c) for c in cands]
	assert lengths == sorted(lengths, reverse=True), lengths


def test_candidatesAreDeduped():
	cands = ts._needleCandidates("The council voted Tuesday on a levy")
	assert len(cands) == len(set(cands))


# ---------------------------------------------------------------------------
# The two failures that motivated the change.
# ---------------------------------------------------------------------------

LEDE = "The council voted on Tuesday to approve the new transit levy"


def test_recoversWhenTheTailOfThePreviewChanged():
	# Hydration rewrote the paragraph past char ~40 (a link got injected, the
	# byline resolved). The full-width needle cannot match; the head still can.
	doc = FakeDoc([
		"Skip to main content",
		"The council voted on Tuesday to approve a revised transit levy today",
	])
	node = Node(LEDE)
	info = ts.findLandingByText(doc, LEDE, verify=verifierFor(node))
	assert info is not None, "a recoverable landing was thrown away"
	info.expand(_FakeTextInfos.UNIT_PARAGRAPH)
	assert info.text.startswith("The council voted on Tuesday")


def test_fullWidthSearchAloneWouldHaveFailedThatPage():
	# Pins the premise of the test above: without a verifier we do exactly one
	# full-width search, and on this page it finds nothing. If this ever starts
	# passing, the previous test is no longer testing what it claims.
	doc = FakeDoc([
		"Skip to main content",
		"The council voted on Tuesday to approve a revised transit levy today",
	])
	assert ts.findLandingByText(doc, LEDE) is None
	assert len(doc.findCalls) == 1


def test_recoversWhenNbspsCameBackAsOrdinarySpaces():
	# The walk captured the NBSPs news sites litter through their ledes; the
	# rebuilt buffer has plain spaces. find() is literal, so the raw needle
	# misses, while the verifier would have accepted the paragraph happily.
	captured = "The council voted on" + NBSP + "Tuesday to approve the new transit levy"
	doc = FakeDoc([
		"Skip to main content",
		"The council voted on Tuesday to approve the new transit levy",
	])
	node = Node(captured)
	info = ts.findLandingByText(doc, captured, verify=verifierFor(node))
	assert info is not None, "an NBSP swap silenced a landing that was right there"
	info.expand(_FakeTextInfos.UNIT_PARAGRAPH)
	assert info.text.startswith("The council voted")


# ---------------------------------------------------------------------------
# Safety: a shorter needle must not be allowed to speak the wrong paragraph.
# ---------------------------------------------------------------------------

def test_theVerifierAloneWouldNotCatchARepeatedOpening():
	# Measured, not assumed, and the reason the uniqueness rule exists.
	# landingTextMatches compares 24 normalised characters, so a teaser that
	# repeats its own lede's opening IS accepted as the lede. Any design that
	# leans on the verifier to police shortened needles is leaning on this.
	teaser = "The council voted on Tuesday, and here is what else you missed"
	assert web.landingTextMatches(teaser, Node(LEDE)) is True


def test_anAmbiguousRungIsRefusedEvenThoughTheVerifierWouldPassIt():
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
	info = ts.findLandingByText(doc, LEDE, verify=verifierFor(node))
	assert info is None, (
		"a shortened needle that matched in two places was used anyway; "
		"find() returns the FIRST hit, so this is the wrong paragraph being "
		"spoken to a blind user"
	)


def test_anUnambiguousRungStillWinsOnAPageThatHasATeaser():
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
	info = ts.findLandingByText(doc, LEDE, verify=verifierFor(node))
	assert info is not None, "an unambiguous shortened rung was refused"
	info.expand(_FakeTextInfos.UNIT_PARAGRAPH)
	assert info.text.startswith("The council voted on Tuesday to approve a revised")


def test_aUniqueRungInsideAnotherParagraphIsRejectedByTheVerifier():
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
	info = ts.findLandingByText(doc, LEDE, verify=verifierFor(node))
	assert info is None, (
		"a unique hit buried mid-paragraph was accepted; uniqueness proves "
		"there is one hit, only the verifier proves the hit is a paragraph "
		"that begins with what the classifier chose"
	)


def test_shorteningIsGatedOnAVerifierBeingSupplied():
	# With no verifier there is nothing to catch a false hit, so the finder
	# must not shorten. One search, full width, exactly as before.
	doc = FakeDoc([
		"Skip to main content",
		"The council voted on Tuesday to approve a revised transit levy today",
	])
	assert ts.findLandingByText(doc, LEDE) is None
	assert doc.findCalls == [LEDE], doc.findCalls
	assert doc.allFetches == 0, "the unverified path must not pull the buffer copy"


# ---------------------------------------------------------------------------
# Budget. find() re-fetches the whole remaining story text on every call, so
# the ladder must not be run blind.
# ---------------------------------------------------------------------------

def test_absentCandidatesNeverCostARealSearch():
	# Nothing on this page resembles the needle. The buffer copy is taken once
	# and every rung is ruled out against it, so no find() is paid for at all.
	doc = FakeDoc(["Cookies", "We value your privacy and use cookies to improve"])
	node = Node(LEDE)
	assert ts.findLandingByText(doc, LEDE, verify=verifierFor(node)) is None
	assert doc.findCalls == [], doc.findCalls
	assert doc.allFetches == 1, doc.allFetches


def test_theHappyPathCostsOneSearch():
	doc = FakeDoc(["Skip to main content", LEDE])
	node = Node(LEDE)
	info = ts.findLandingByText(doc, LEDE, verify=verifierFor(node))
	assert info is not None
	assert doc.findCalls == [LEDE], doc.findCalls
	assert doc.allFetches == 1


def test_aNeedleBelowTheFloorIsRefusedOutright():
	doc = FakeDoc(["short", "another"])
	node = Node("short")
	assert ts.findLandingByText(doc, "short", verify=verifierFor(node)) is None
	assert doc.findCalls == []
