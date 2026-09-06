# Wiring inside the NVDA-bound walk, driven end to end.
#
# WHY THIS FILE EXISTS. Three times on this branch a safety input was found
# DELETABLE with the whole suite still green. Every case had the same shape:
# the RULE was tested as a pure function, and the WIRING that feeds the rule
# lived inside `_walkMainNodes`, which needs NVDA, so nothing covered it.
# The tests hand-built the very inputs the wiring was supposed to produce.
#
# `_walkMainNodes` does not actually need NVDA. It needs a treeInterceptor
# with `makeTextInfo`, and a `textInfos` module with two constants. Both are
# duck-typed, so the real walk runs here against a fake document and the
# wiring is covered by construction rather than by assertion about inputs
# someone typed in by hand.
#
# EVERY TEST BELOW WAS CONFIRMED TO FAIL when the wiring it covers is removed.
# The sabotage that each one catches is named in its docstring. If you change
# the walk, re-run that check — a green suite is not evidence here, it is the
# thing that failed us three times.

import pytest

import treeSummary as ts


# --------------------------------------------------------------------------
# Fake NVDA surface
# --------------------------------------------------------------------------

class FakeFieldCommand:
	def __init__(self, command, field=None):
		self.command = command
		self.field = field or {}


class _FakeTextInfos:
	"""The constants and the FieldCommand type the walk reads off the module."""

	POSITION_FIRST = "POSITION_FIRST"
	UNIT_PARAGRAPH = "UNIT_PARAGRAPH"
	FieldCommand = FakeFieldCommand


class FakeRole:
	def __init__(self, name):
		self.name = name


def control(role, level=None):
	"""One controlStart command, as Gecko's normalized fields produce them.

	`level` is a STRING here on purpose — that is what the probe found on all
	six real heading chunks, and an int would quietly hide a regression in the
	conversion.
	"""
	field = {"role": FakeRole(role)}
	if level is not None:
		field["level"] = str(level)
	return FakeFieldCommand("controlStart", field)


class FakeObj:
	"""Stand-in for an NVDAObject. `landmark` drives _inScope, `role` drives
	_nodeFor. `parent` is the chain the identity filter climbs."""

	def __init__(self, role="PARAGRAPH", landmark=None, parent=None):
		self.role = type("Role", (), {"name": role})()
		self.landmark = landmark
		self.parent = parent


class Chunk:
	def __init__(self, start, end, text, obj=None, fields=None):
		self.start = start
		self.end = end
		self.text = text
		self.obj = obj
		# The control field stack the buffer emits for this chunk. None means
		# the buffer emitted nothing, which is the case that must fall back to
		# an object fetch.
		self.fields = fields


class FakeInfo:
	"""A cursor over a fake document, with NVDA's TextInfo semantics for the
	handful of operations the walk performs."""

	def __init__(self, doc, start=0, end=0):
		self.doc = doc
		self.start = start
		self.end = end

	# -- chunk resolution --
	def _chunkAtStart(self):
		for c in self.doc:
			if c.start <= self.start < c.end:
				return c
		return None

	# -- TextInfo API --
	def copy(self):
		return FakeInfo(self.doc, self.start, self.end)

	def collapse(self, end=False):
		if end:
			self.start = self.end
		else:
			self.end = self.start

	def expand(self, unit):
		c = self._chunkAtStart()
		if c is None:
			raise RuntimeError("off the end of the document")
		self.start, self.end = c.start, c.end

	def move(self, unit, count):
		for c in self.doc:
			if c.start > self.start:
				self.start = self.end = c.start
				return 1
		return 0

	def compareEndPoints(self, other, which):
		a = self.start if which.startswith("start") else self.end
		b = other.start if which.endswith("Start") else other.end
		return (a > b) - (a < b)

	@property
	def text(self):
		c = self._chunkAtStart()
		return c.text if c else ""

	def getTextWithFields(self, formatConfig=None):
		c = self._chunkAtStart()
		if c is None or c.fields is None:
			return []
		return list(c.fields) + [c.text]

	@property
	def NVDAObjectAtStart(self):
		c = self._chunkAtStart()
		# Every resolution is recorded, so a test can assert that a
		# positionally-scoped page fetched NO objects at all. That assertion
		# is the only thing standing between "lazy" and "lazy in the comments
		# but eager in the code".
		if c is not None:
			FakeInfo.fetches.append(c.text[:30])
		return c.obj if c else None


FakeInfo.fetches = []


class FakeTI:
	def __init__(self, doc):
		self.doc = doc

	def makeTextInfo(self, position):
		return FakeInfo(self.doc, 0, 0)


@pytest.fixture(autouse=True)
def _fakeTextinfos(monkeypatch):
	monkeypatch.setattr(ts, "textInfos", _FakeTextInfos, raising=False)
	FakeInfo.fetches = []


def buildDoc(specs):
	"""specs: list of (text, obj) or (text, obj, fields). Offsets contiguous."""
	doc = []
	pos = 0
	for spec in specs:
		text, obj = spec[0], spec[1]
		fields = spec[2] if len(spec) > 2 else None
		width = max(len(text), 1)
		doc.append(Chunk(pos, pos + width, text, obj, fields))
		pos += width
	return doc


def walk(doc, **kw):
	"""Run the real walk, returning (nodes, allNodes, positionalDrops)."""
	allNodes = []
	positions = []
	allPositions = []
	positional = [0]
	nodes = ts._walkMainNodes(
		FakeTI(doc),
		kw.pop("mainObj", None),
		{},
		positions,
		allNodesOut=allNodes,
		allPositionsOut=allPositions,
		positionalOut=positional,
		**kw,
	)
	return nodes, allNodes, positional[0]


def para(text, landmark=None):
	"""A paragraph chunk that the buffer DOES emit a control field for, which
	is what every chunk looked like in the corrected probe run (153 chunks
	over 4 pages, 2026-07-19: chunks_with_no_control_field=0).

	It used to cite "all 219 probe chunks". That run is disowned — its
	comparison reduced roles to heading/skip/paragraph, so LINK scored as
	agreement with PARAGRAPH, and its sample contained none of the shape it
	was supposed to validate. Do not cite it again."""
	return (
		text,
		FakeObj("PARAGRAPH", landmark=landmark),
		[control("DOCUMENT"), control("PARAGRAPH")],
	)


def paraNoFields(text, landmark=None):
	"""A chunk the buffer emitted NO control field for. The probe never saw
	one, but 'never seen on 8 pages' is not 'cannot happen', so the fallback
	has to exist and has to be covered."""
	return (text, FakeObj("PARAGRAPH", landmark=landmark), None)


def rng(start, end):
	"""A bare offset pair usable as a scope/exclude range."""
	return FakeInfo([], start, end)


# --------------------------------------------------------------------------
# 1. The objectless-chunk rejection on chrome-pos
# --------------------------------------------------------------------------
#
# SABOTAGE THIS CATCHES: in _chunkScope's excludeRanges branch, change the
# `obj is None` arm from `return False, _SCOPE_IDENTITY` to return True (the
# fail-open default every other path in the module uses).
#
# Why it is not harmless there: chrome-pos routes undecided chunks to the
# identity filter AS its safety mechanism, and an objectless chunk is the one
# class where that filter cannot run at all. Fail-open means a navigation menu
# past the trust boundary reads as article text.

def test_objectlessChunkPastTrustBoundaryIsRejected():
	# Two chunks. The first is inside an emitted chrome range and has an
	# object; the second sits PAST the trust boundary with NO object, so
	# positional cannot decide and identity cannot run.
	doc = buildDoc([
		para("navigation home about contact", landmark="navigation"),
		("orphan text with no accessible object at all", None),
	])
	nodes, allNodes, drops = walk(
		doc,
		excludeRanges=[rng(0, 29)],
		trustBoundary=rng(0, 0),
		untrustedRanges=[],
	)
	texts = [n.textPreview for n in nodes]
	assert not any("orphan" in t for t in texts), (
		"an objectless chunk that neither filter could decide was admitted as "
		"content; that is the fail-open the tri-state exists to prevent"
	)
	# It must still reach allNodes so the depleted-scope net can recover it.
	assert any("orphan" in n.textPreview for n in allNodes)


# --------------------------------------------------------------------------
# 2. The positionalDrops tally
# --------------------------------------------------------------------------
#
# SABOTAGE THIS CATCHES: delete the `positionalHits`/`positionalDrops`
# derivation in _walkMainNodes (the `if scopeDecision in (...)` block), or
# stop passing `positionalOut` back out.
#
# positionalDrops is a SAFETY INPUT, not a diagnostic: _scopeLooksDepleted
# keys on `positionalDrops == 0` to decide whether a chrome-pos page whose
# exclusions actually worked may be widened back open. Zeroing it silently
# switches the depleted-scope net off on exactly the pages it protects.

def test_positionalDropsCountsChromeExclusions():
	# Note the trust boundary is the start of the LAST landmark placed, and
	# _startsBefore compares STRICTLY — so a chunk sitting exactly at the
	# boundary defers to identity by design. Both chrome chunks here are
	# strictly before it, which is what makes them positional decisions.
	doc = buildDoc([
		para("site navigation links across the top", landmark="navigation"),
		para("The real article begins here and runs on for a while."),
		para("footer legal text down at the bottom", landmark="contentinfo"),
		para("a trailing complementary region", landmark="complementary"),
	])
	nav, foot, last = doc[0], doc[2], doc[3]
	nodes, allNodes, drops = walk(
		doc,
		excludeRanges=[
			rng(nav.start, nav.end),
			rng(foot.start, foot.end),
			rng(last.start, last.end),
		],
		trustBoundary=rng(last.start, last.end),
		untrustedRanges=[],
	)
	assert drops == 2, (
		f"expected both chrome chunks counted as positional drops, got {drops}; "
		"the depleted-scope net reads this number"
	)
	assert [n.textPreview for n in nodes] == [
		"The real article begins here and runs on for a while."
	]


def test_positionalDropsIsZeroWhenNothingWasExcluded():
	# The other half of the predicate: a page where positional decided
	# everything IN must report zero, so the net can widen it.
	doc = buildDoc([
		para("The real article begins here and runs on for a while."),
		para("A second substantial paragraph of genuine body copy."),
	])
	nodes, allNodes, drops = walk(
		doc,
		excludeRanges=[rng(9000, 9001)],
		trustBoundary=rng(9000, 9001),
		untrustedRanges=[],
	)
	assert drops == 0
	assert len(nodes) == 2


# --------------------------------------------------------------------------
# 3. Scope decisions reach the node list (the walk actually consults them)
# --------------------------------------------------------------------------
#
# SABOTAGE THIS CATCHES: making _walkMainNodes ignore `inScope` and append
# every node to `result`. Every landing test hands the cascade a node list
# directly, so none of them notice that the filter stopped being applied.

def test_outOfScopeChunksAreKeptOutOfMainNodes():
	doc = buildDoc([
		para("inside the article body, a substantial sentence here."),
		para("outside it entirely, chrome text that must not land."),
	])
	inside = doc[0]
	nodes, allNodes, _ = walk(doc, scopeRange=rng(inside.start, inside.end))
	assert [n.textPreview for n in nodes] == [
		"inside the article body, a substantial sentence here."
	]
	assert len(allNodes) == 2, "both chunks must still reach allNodes"


# --------------------------------------------------------------------------
# 4. Walk-time flags are computed over the FULL text, not the 60-char preview
# --------------------------------------------------------------------------
#
# SABOTAGE THIS CATCHES: dropping the walk-time computation of isBoilerplate /
# isCaption / endsSentence in _nodeFor and leaving the cascade's preview
# fallback to cope. Every cascade test can hand-set these flags, which is
# precisely the trap the disclosure flag nearly repeated.

def test_boilerplateFlagIsComputedPastThePreviewCutoff():
	tail = (
		"This page and everything on it belongs to the publisher and may not "
		"be reproduced. Copyright 2026. All rights reserved."
	)
	assert len(tail) > 60 and "rights reserved" not in tail[:60]
	doc = buildDoc([para(tail)])
	nodes, _, _ = walk(doc)
	assert nodes[0].isBoilerplate, (
		"the boilerplate marker sits past char 60, so a preview-only check "
		"cannot see it; this flag must be computed over the full chunk text"
	)


def test_endsSentenceFlagIsComputedPastThePreviewCutoff():
	longSentence = (
		"The council met on Tuesday to consider the proposal, which had been "
		"delayed twice already."
	)
	assert len(longSentence) > 60
	doc = buildDoc([para(longSentence), para("Fragment with no stop")])
	nodes, _, _ = walk(doc)
	assert nodes[0].endsSentence
	assert not nodes[1].endsSentence


# --------------------------------------------------------------------------
# 5. The focus-move filter is actually applied
# --------------------------------------------------------------------------
#
# SABOTAGE THIS CATCHES: deleting the `if not _inMain(item): continue` guard
# in setFocusOnFirstFormInput, or having it call anything other than the
# walk's own scope decision.
#
# This is the highest-stakes wiring in the module: it is the ONE path that
# calls setFocus(). _formFieldInScope is pure and covered, but until now
# nothing checked that setFocusOnFirstFormInput consults it — which is
# exactly the failure it has already had twice (the Zoom header language
# picker, then the no-<main> header search box).

# --------------------------------------------------------------------------
# 6. The field stack replaces the object for ROLE, and the object stays lazy
# --------------------------------------------------------------------------
#
# Probe evidence (probes/field_stack, corrected run 2026-07-19, 153 chunks
# over 4 pages): chunks_with_no_control_field=0, disagree_role_exact=0 (EXACT
# role equality, not the reduced decision), trailing_control_chunks=26 so the
# inline-control shape was actually sampled, field['level'] a str.
#
# The earlier 219-chunk run is disowned and must not be cited: its comparison
# reduced roles to heading/skip/paragraph, so it could not have failed.
#
# SABOTAGE THESE CATCH: reverting to an eager `obj = info.NVDAObjectAtStart`;
# reading the OUTERMOST control field instead of the innermost; dropping the
# int() conversion on the string level; skipping empty-text chunks before the
# heading check (which deletes image-only headings).

def test_roleComesFromTheInnermostControlField():
	# A heading wrapping a link. Outermost-wins would call this a DOCUMENT and
	# heading-first would call it a heading. NEITHER probe run observed this
	# shape, so innermost is not chosen on counts — it is chosen because it
	# matches NVDA's own container resolution in getEnclosingContainerRange.
	# See _roleLevelFromFields.
	role, level, had = ts._roleLevelFromFields([
		control("DOCUMENT"), control("HEADING", 2), control("LINK"),
	])
	assert (role, level, had) == ("LINK", 0, True)


def test_headingLevelIsConvertedFromTheStringGeckoEmits():
	role, level, had = ts._roleLevelFromFields([
		control("DOCUMENT"), control("HEADING", 3),
	])
	assert role == "HEADING"
	assert level == 3 and isinstance(level, int), (
		"field['level'] is a STRING in Gecko's normalized fields; without the "
		"int() conversion every heading compares wrong against level gates"
	)


def test_onlyTheLeadingControlRunCounts():
	# The shape that broke the first version, and that the probe could not see:
	# a paragraph with an inline graphic partway through. getTextWithFields
	# interleaves TEXT with the control commands, so a whole-stream scan keeps
	# the LAST controlStart — here GRAPHIC, a SKIP role — and the paragraph
	# disappears from the node list entirely.
	#
	# NVDA's own getEnclosingContainerRange breaks at the first non-controlStart
	# item (verified in the installed virtualBuffers/__init__.pyc).
	stream = [
		control("DOCUMENT"),
		control("PARAGRAPH"),
		"Some text ",
		control("GRAPHIC"),
		FakeFieldCommand("controlEnd"),
		" more text",
		FakeFieldCommand("controlEnd"),
	]
	role, level, had = ts._roleLevelFromFields(stream)
	assert (role, had) == ("PARAGRAPH", True), (
		"a trailing inline control won the role; a paragraph containing an "
		"image would be classified GRAPHIC and skipped as content"
	)


def test_inlineControlParagraphSurvivesTheWalk():
	# The same defect, driven through the real walk rather than the helper.
	doc = buildDoc([(
		"A real body paragraph with an inline image in the middle of it.",
		FakeObj("PARAGRAPH"),
		[
			control("DOCUMENT"), control("PARAGRAPH"),
			"A real body paragraph ",
			control("GRAPHIC"), FakeFieldCommand("controlEnd"),
			" in the middle of it.", FakeFieldCommand("controlEnd"),
		],
	)])
	nodes, _, _ = walk(doc, scopeRange=rng(0, 10_000))
	assert [n.kind for n in nodes] == ["paragraph"], (
		"the paragraph was dropped because an inline graphic won the role"
	)


def test_unnamedInnermostRoleDoesNotInheritAnAncestor():
	# A BUTTON whose role fails to resolve must NOT inherit DOCUMENT and be
	# admitted as a paragraph. No usable role at the innermost position means
	# no evidence, so the caller pays for an object and gets the truth.
	class Roleless:
		pass
	stream = [control("DOCUMENT"), FakeFieldCommand("controlStart", {"role": Roleless()})]
	assert ts._roleLevelFromFields(stream) == (None, 0, False)


def test_headingWithUnreadableLevelDefersToTheObject():
	# level feeds heading-cluster comparisons in the classifier, so a wrong 0
	# can merge distinct levels and change LIST classification. An unreadable
	# level is not level zero.
	for bad in (None, "", "abc"):
		field = {"role": FakeRole("HEADING")}
		if bad is not None:
			field["level"] = bad
		assert ts._roleLevelFromFields([FakeFieldCommand("controlStart", field)]) == (None, 0, False), (
			f"heading with level={bad!r} was accepted as level 0"
		)


def test_objectFetchFailureIsNotSwallowedIntoNone():
	# An exception from NVDAObjectAtStart must NOT be memoised as None. Two
	# identity branches read `obj is None` as IN scope, so swallowing it admits
	# an unverified navigation chunk as content — fail-OPEN on the safety path.
	class Exploding(FakeInfo):
		@property
		def NVDAObjectAtStart(self):
			raise RuntimeError("COM failure (simulated)")

	class ExplodingTI:
		def __init__(self, doc):
			self.doc = doc

		def makeTextInfo(self, position):
			return Exploding(self.doc, 0, 0)

	doc = buildDoc([paraNoFields("navigation menu text that must not be admitted")])
	nodes = ts._walkMainNodes(ExplodingTI(doc), None, {}, [], allNodesOut=[])
	assert nodes == [], (
		"a COM failure produced a content node; the old eager fetch let the "
		"exception stop the walk and that must not have changed"
	)


def test_noControlFieldReportsNoEvidence():
	role, level, had = ts._roleLevelFromFields([])
	assert (role, level, had) == (None, 0, False)
	assert ts._roleLevelFromFields(None) == (None, 0, False)


def test_walkTakesTheRoleFromFieldsWithoutTouchingTheObject():
	# A positionally-scoped page: the scope decision needs no object and the
	# role now comes from the field stack, so the walk must resolve ZERO
	# objects. This is the entire performance claim, stated as an assertion.
	doc = buildDoc([
		("Chapter One", FakeObj("HEADING"), [control("DOCUMENT"), control("HEADING", 1)]),
		para("A substantial opening paragraph that runs on for a while here."),
	])
	nodes, _, _ = walk(doc, scopeRange=rng(0, 10_000))
	assert [n.kind for n in nodes] == ["heading", "paragraph"]
	assert nodes[0].level == 1
	assert FakeInfo.fetches == [], (
		f"the walk resolved {len(FakeInfo.fetches)} object(s) on a fully "
		"positional page; each one is 3+ cross-process COM round trips and "
		"none of them were needed"
	)


def test_walkFallsBackToTheObjectWhenThereIsNoControlField():
	doc = buildDoc([paraNoFields("Some text with no control field at all.")])
	nodes, _, _ = walk(doc, scopeRange=rng(0, 10_000))
	assert [n.kind for n in nodes] == ["paragraph"]
	assert FakeInfo.fetches, (
		"with no control field there is no role evidence, so the object MUST "
		"be fetched; silently treating it as a paragraph would delete "
		"image-only headings"
	)


def test_imageOnlyHeadingSurvivesTheFieldStackPath():
	# An <h1> wrapping a logo <img>: heading role, empty text. This node drives
	# seenHeading, the hero gate, the prose-run gate and findListLanding, so
	# an empty-text shortcut ahead of the role check would silently remove it.
	doc = buildDoc([
		("", FakeObj("HEADING"), [control("DOCUMENT"), control("HEADING", 1)]),
		para("Body copy following the image-only masthead heading here."),
	])
	nodes, _, _ = walk(doc, scopeRange=rng(0, 10_000))
	assert [n.kind for n in nodes] == ["heading", "paragraph"]


def test_identityScopedPageStillResolvesObjects():
	# The other half of "lazy, not removed": on an identity-scoped page the
	# object is the only evidence there is, and it must still be fetched.
	doc = buildDoc([para("Body copy on a page with no usable scope range.")])
	nodes, _, _ = walk(doc)
	assert FakeInfo.fetches, (
		"identity scoping has no positional answer; removing the object fetch "
		"here removes the chrome filter itself"
	)


class FocusItem:
	def __init__(self, name, start, end, landmark=None):
		self.name = name
		self.textInfo = rng(start, end)
		self.obj = FakeObj("EDIT", landmark=landmark)
		self.obj.focused = []
		self.obj.setFocus = lambda n=name, o=self.obj: o.focused.append(n)


class FocusTI:
	def __init__(self, items):
		self.items = items

	def _iterNodesByType(self, itemType):
		if itemType != "edit":
			return iter(())
		return iter(self.items)


def test_focusMoveSkipsAFieldInsideChrome(monkeypatch):
	# A header search box inside an emitted <nav>, then the real form field
	# below it. Document order alone would take the search box.
	search = FocusItem("header-search", 0, 10, landmark="navigation")
	real = FocusItem("real-form-field", 100, 110)
	scan = ts.LandmarkScan(
		mainObj=None,
		mainRange=None,
		chromeRanges=[rng(0, 50)],
		otherRanges=[],
		trustBoundary=rng(0, 50),
		seen=1,
		exhausted=True,
	)
	monkeypatch.setattr(ts, "_NVDA_AVAILABLE", True)
	monkeypatch.setattr(ts, "_findMainLandmark", lambda ti: scan)

	ti = FocusTI([search, real])
	assert ts.setFocusOnFirstFormInput(ti) is True
	assert search.obj.focused == [], (
		"focus was moved into a field inside a chrome landmark; this is the "
		"path that calls setFocus(), so this is a blind user's caret landing "
		"in the site header"
	)
	assert real.obj.focused == ["real-form-field"]


# ---------------------------------------------------------------------------
# The focus gate must refuse a field it could not PLACE, not just one it
# placed inside chrome. Added 2026-07-18.
#
# setFocusOnFirstFormInput calls setFocus(). Its docstring has claimed
# "Fails CLOSED throughout" since it was written, and it did not: its identity
# fallback went through _inScope, which turned an undecided parent walk into
# `mainObj is None` — True on every page without a <main>. So one failed COM
# dereference was enough to make an unplaceable field read as proven content.
#
# Driven through the real entry point with a fake quick-nav iterator, because
# this branch has been wrong twice and both times the wiring, not the
# arithmetic, was what was wrong.
# ---------------------------------------------------------------------------

class UnplaceableObj:
	"""An EDIT whose ancestry cannot be walked: the parent dereference raises,
	exactly as a COM call does on a page mid-teardown."""

	def __init__(self, name):
		self.role = type("Role", (), {"name": "EDIT"})()
		self.landmark = None
		self.focused = []
		self.setFocus = lambda n=name, o=self: o.focused.append(n)

	@property
	def parent(self):
		raise RuntimeError("parent dereference failed (simulated COM error)")


class UnplaceableItem:
	def __init__(self, name, start, end):
		self.textInfo = rng(start, end)
		self.obj = UnplaceableObj(name)


def _noMainScan():
	# A lone top nav: trustBoundary lands at offset 0, so NOTHING is before
	# it and every field falls through to the identity filter. This is the
	# commonest no-<main> page shape, which is what makes the fallback's
	# behaviour load-bearing rather than academic.
	return ts.LandmarkScan(
		mainObj=None,
		mainRange=None,
		chromeRanges=[rng(0, 50)],
		otherRanges=[],
		trustBoundary=rng(0, 50),
		seen=1,
		exhausted=True,
	)


def test_focusMoveRefusesAFieldWhoseAncestryCannotBeWalked(monkeypatch):
	unplaceable = UnplaceableItem("unplaceable", 100, 110)
	monkeypatch.setattr(ts, "_NVDA_AVAILABLE", True)
	monkeypatch.setattr(ts, "_findMainLandmark", lambda ti: _noMainScan())

	moved = ts.setFocusOnFirstFormInput(FocusTI([unplaceable]))

	assert moved is False, (
		"focus was moved to a field we could not place. 'Could not prove this "
		"is chrome' is not 'proven content', and this call moves a blind "
		"user's caret"
	)
	assert unplaceable.obj.focused == []


def test_focusMoveStillTakesAFieldItCANPlace(monkeypatch):
	# The other direction, so the fix cannot be "return False more often".
	# A walkable chain with no chrome on it is a real answer and must still
	# win the focus.
	placeable = FocusItem("real-form-field", 100, 110)
	monkeypatch.setattr(ts, "_NVDA_AVAILABLE", True)
	monkeypatch.setattr(ts, "_findMainLandmark", lambda ti: _noMainScan())

	assert ts.setFocusOnFirstFormInput(FocusTI([placeable])) is True
	assert placeable.obj.focused == ["real-form-field"]


def test_focusMoveSkipsTheUnplaceableAndTakesTheNextRealField(monkeypatch):
	# Document order puts the unplaceable field first. Refusing it must not
	# abandon the form — the user still gets the field we can vouch for.
	items = [UnplaceableItem("unplaceable", 100, 110), FocusItem("real", 200, 210)]
	monkeypatch.setattr(ts, "_NVDA_AVAILABLE", True)
	monkeypatch.setattr(ts, "_findMainLandmark", lambda ti: _noMainScan())

	assert ts.setFocusOnFirstFormInput(FocusTI(items)) is True
	assert items[0].obj.focused == []
	assert items[1].obj.focused == ["real"]


class UnplaceableNoRangeItem:
	"""A field with NO textInfo, so no positional answer is possible, whose
	ancestry also cannot be walked."""

	def __init__(self, name):
		self.textInfo = None
		self.obj = UnplaceableObj(name)


def test_focusMoveRefusesAnUnplaceableFieldUnderAPositionalScope(monkeypatch):
	# The OTHER identity fallback in _formFieldInScope: a positional scope
	# is in force but the field exposes no range. It is easy to assume that
	# branch is safe because main-pos pages have a mainObj, so the old
	# boolean default resolved to False. But `article` scope is positional
	# with NO <main> — mainObj is None — so the default was True there, and
	# an unplaceable field read as content on the setFocus() path.
	scan = ts.LandmarkScan(
		mainObj=None,
		mainRange=None,
		chromeRanges=[],
		otherRanges=[],
		trustBoundary=None,
		seen=0,
		exhausted=True,
	)
	monkeypatch.setattr(ts, "_NVDA_AVAILABLE", True)
	monkeypatch.setattr(ts, "_findMainLandmark", lambda ti: scan)
	# Force the positional branch with an article-shaped scope: a range, and
	# no mainObj behind it.
	monkeypatch.setattr(
		ts, "_selectScope", lambda lm: ("article", rng(0, 1000), None, None, None),
	)

	item = UnplaceableNoRangeItem("unplaceable-no-range")
	assert ts.setFocusOnFirstFormInput(FocusTI([item])) is False
	assert item.obj.focused == []


# ==========================================================================
# Landmark ancestry from the control field stack (Task 2, 2026-07-19).
#
# Replaces the COM parent chain on chrome-scoped pages with the landmark keys
# already present in the leading control run the walk fetches for the ROLE.
# Probe evidence, 4 pages / 153 chunks: the field stack never missed a
# landmark the parent chain found across 48 landmark-bearing chunks, caught
# three the chain missed and was right about all three, and cost 138.8 ms
# against the chain's 16,564 ms.
#
# EVERY TEST HERE WAS CONFIRMED TO FAIL when its wiring is removed. The whole
# point of this file is that the RULE being unit-tested is not evidence the
# rule is CONNECTED.
# ==========================================================================


class GeckoLikeInfo(FakeInfo):
	"""A TextInfo whose MRO carries the Gecko class NAME, which is what the
	backend gate keys on.

	Named rather than imported because treeSummary must stay importable
	outside NVDA. Chromium passes the real gate the same way: by inheritance
	from Gecko's virtual-buffer TextInfo."""


GeckoLikeInfo.__name__ = "FakeGeckoInfo"
# Rename a synthetic base so the MRO contains the gate's target name.
# The gate matches the class NAME **and** its MODULE, so a same-named class
# from anywhere else is not trusted. The fake therefore has to impersonate both.
Gecko_ia2_TextInfo = type(
	"Gecko_ia2_TextInfo", (FakeInfo,), {"__module__": "virtualBuffers.gecko_ia2"},
)


class SupportedInfo(Gecko_ia2_TextInfo):
	pass


class SupportedTI(FakeTI):
	def makeTextInfo(self, position):
		return SupportedInfo(self.doc, 0, 0)


def lm(text, landmarkKey, objLandmark=None):
	"""A chunk whose FIELD STACK carries a landmark, independent of what the
	object's parent chain would say. objLandmark is deliberately separate so a
	test can prove WHICH mechanism answered."""
	field = {"role": FakeRole("PARAGRAPH"), "landmark": landmarkKey}
	return (
		text,
		FakeObj("PARAGRAPH", landmark=objLandmark),
		[FakeFieldCommand("controlStart", {"role": FakeRole("DOCUMENT")}),
		 FakeFieldCommand("controlStart", field)],
	)


def walkSupported(doc, **kw):
	allNodes, positions, allPositions, positional = [], [], [], [0]
	nodes = ts._walkMainNodes(
		SupportedTI(doc), kw.pop("mainObj", None), {}, positions,
		allNodesOut=allNodes, allPositionsOut=allPositions,
		positionalOut=positional, **kw,
	)
	return nodes, allNodes, positional[0]


def test_fieldStackDropsANavChunkWithoutTouchingCom():
	"""SABOTAGE: delete the fieldVerdict branch in _chunkScope's chrome path.

	The nav chunk is dropped by its FIELD landmark alone -- its object carries
	no landmark, so the parent chain would have ADMITTED it. That asymmetry is
	what proves the field stack answered."""
	doc = buildDoc([
		lm("Home Products Support About Contact", "navigation"),
		para("A genuine article paragraph with enough text to be a real node."),
	])
	nodes, _all, drops = walkSupported(doc)
	texts = [n.textPreview for n in nodes]
	assert not any("Home Products" in t for t in texts), "nav must be excluded"
	assert any("genuine article" in t for t in texts)
	assert drops >= 1, "a field exclusion must count as a positional drop"


def test_fieldStackAcceptsContentWithoutResolvingAnObject():
	"""SABOTAGE: delete the definitive-NOT_IN_CHROME accept.

	A valid leading run with no landmark is POSITIVE evidence of "no chrome
	ancestor at this offset" (getTextInRange emits the complete ancestor
	chain), so it must be accepted with NO object fetch. If the accept is
	removed the walk falls through to the parent chain and fetches."""
	doc = buildDoc([
		para("A perfectly ordinary paragraph sitting outside every landmark."),
	])
	nodes, _all, _d = walkSupported(doc)
	assert len(nodes) == 1
	assert FakeInfo.fetches == [], f"paid for COM anyway: {FakeInfo.fetches}"


def test_unsupportedBackendNeverUsesTheFieldVerdict():
	"""SABOTAGE: delete the _fieldsCarryLandmarks gate in the walk.

	THE FAIL-OPEN THIS CLOSES. field['landmark'] is written by the BACKEND's
	normalizer; WebKit's does not write it at all. On such a backend every
	chunk would report "no landmark" and all chrome would be admitted. The
	plain FakeTI is not Gecko-derived, so the nav chunk must be decided by the
	parent chain -- which here means an object fetch actually happens."""
	doc = buildDoc([
		lm("Home Products Support About Contact", "navigation"),
		para("A genuine article paragraph with enough text to be a real node."),
	])
	nodes, _all, _d = walk(doc)
	assert FakeInfo.fetches, "unsupported backend must fall back to the object"


def test_mainIdKeepsTheIdentityFilter():
	"""CONDITION 4. The field stack answers "inside ANY marked chrome
	landmark"; main-id asks "inside THE <main> we found", which is an IDENTITY
	question. That equivalence is unprobed, so a page WITH a mainObj must
	still consult the parent chain even on a supported backend."""
	main = FakeObj("SECTION", landmark="main")
	doc = buildDoc([
		("Body text living under the main landmark object here.",
		 FakeObj("PARAGRAPH", parent=main),
		 [control("DOCUMENT"), control("PARAGRAPH")]),
	])
	walkSupported(doc, mainObj=main)
	assert FakeInfo.fetches, "main-id must not be answered by the field stack"


def test_malformedFieldStackFallsBackRatherThanAdmitting():
	"""A stack we cannot parse is NO EVIDENCE, never a content verdict."""
	broken = ("Some text of reasonable length for a real node here.",
	          FakeObj("PARAGRAPH"),
	          [FakeFieldCommand("controlStart", "not-a-dict")])
	doc = buildDoc([broken])
	walkSupported(doc)
	assert FakeInfo.fetches, "malformed stack must fall back to the object"


def test_noLeadingControlRunIsUnknownNotContent():
	"""SABOTAGE: delete the `sawControl` guard in _landmarkScopeFromFields.

	FOUND BY THE SABOTAGE CHECK, 2026-07-19 -- the first version of the
	malformed-stack test above did NOT cover this. It passed a controlStart
	whose field was not dict-like, which raises and returns via the exception
	handler; the `sawControl` branch is a different path entirely and was
	uncovered.

	THE DISTINCTION THAT MATTERS. An empty landmark set means "no chrome
	ancestor" ONLY when we actually saw the ancestor chain. A stream with no
	leading controlStart means we saw NOTHING, so it is UNKNOWN -- and UNKNOWN
	must reach the object, not return the empty-set content verdict.

	Asserting on the fetch count cannot catch this: a chunk with no control run
	has no field ROLE either, so the walk fetches an object regardless. The
	assertion has to be on the SCOPE outcome, so the object here carries a nav
	landmark that only the identity filter can see.
	"""
	doc = buildDoc([
		("Home Products Support About Contact Careers Press",
		 FakeObj("PARAGRAPH", landmark="navigation"),
		 []),  # non-empty stream, but no leading controlStart
		para("A genuine article paragraph with enough text to be a real node."),
	])
	nodes, _all, _d = walkSupported(doc)
	texts = [n.textPreview for n in nodes]
	assert not any("Home Products" in t for t in texts), (
		"a chunk with no leading control run must fall through to the identity "
		"filter, which drops it as navigation -- not be admitted as content"
	)
	assert any("genuine article" in t for t in texts)


# --------------------------------------------------------------------------
# Holes found by adversarial review, 2026-07-19. All three left the suite
# GREEN when the logic they cover was deleted or inverted -- the fourth
# instance of this branch's signature failure, and the reason this file exists.
# --------------------------------------------------------------------------

def test_chromePosConsultsTheFieldStackBeforePayingForCom():
	"""SABOTAGE: delete the fieldVerdict return inside the excludeRanges
	branch of _chunkScope.

	WIRED BUT UNTESTED until now. Every excludeRanges test used the plain
	FakeTI, where the backend gate forces fieldVerdict to None, and every
	supported-backend test omitted excludeRanges -- so the two were never
	exercised together and the whole branch could be deleted green.

	It is not cosmetic. Inside an untrusted range the field stack is the ONLY
	mechanism that can see a nested navigation the landmark enumeration may
	have silently omitted; without it those chunks go back to the identity
	filter the bounded-trust design was built to distrust.

	The nav chunk here sits PAST the trust boundary, so _chromePosVerdict
	declines and the field stack is the thing that must answer. Its OBJECT
	carries no landmark, so the identity filter would have admitted it -- that
	asymmetry is what proves which mechanism decided.
	"""
	doc = buildDoc([
		para("Article body text that runs on for a good long while here."),
		lm("Home About Contact Careers Press Investors", "navigation"),
	])
	nodes, allNodes, drops = walkSupported(
		doc,
		excludeRanges=[],
		trustBoundary=rng(0, 0),   # nothing is strictly before this
		untrustedRanges=[],
	)
	texts = [n.textPreview for n in nodes]
	assert not any("Home About" in t for t in texts), (
		"chrome-pos ignored the field stack and fell through to identity, "
		"which admits this chunk because its object has no landmark"
	)
	assert drops >= 1, "a field exclusion here must count as a positional drop"
	assert FakeInfo.fetches == [], (
		f"paid for a COM parent chain anyway: {FakeInfo.fetches}"
	)


def test_innermostLandmarkWinsOverAnOuterOne():
	"""SABOTAGE: change `reversed(seen)` to `seen` in
	_landmarkScopeFromFields.

	The docstring calls INNERMOST WINS the property that makes the field stack
	agree with the parent chain, which stops at the FIRST landmark it meets
	walking UP. Nothing tested it: the `lm()` helper emits exactly one landmark
	per chunk, so no nested stack existed anywhere in the suite and
	outermost-wins passed green.

	Here a <main> is nested inside a <banner>. Innermost-wins says content;
	outermost-wins says chrome and the paragraph vanishes.
	"""
	nested = (
		"Real content living inside a main that sits inside a banner.",
		FakeObj("PARAGRAPH"),
		[
			FakeFieldCommand("controlStart", {"role": FakeRole("DOCUMENT")}),
			FakeFieldCommand("controlStart", {"role": FakeRole("SECTION"), "landmark": "banner"}),
			FakeFieldCommand("controlStart", {"role": FakeRole("SECTION"), "landmark": "main"}),
			FakeFieldCommand("controlStart", {"role": FakeRole("PARAGRAPH")}),
		],
	)
	nodes, _all, _d = walkSupported(buildDoc([nested]))
	assert any("Real content" in n.textPreview for n in nodes), (
		"the innermost landmark is <main>, so this is content; reading the "
		"OUTERMOST landmark instead calls it banner and drops it"
	)


def test_innermostChromeWinsOverAnOuterMain():
	"""The mirror, so the rule is pinned in BOTH directions.

	SABOTAGE: delete the `lm == "main"` early return. That mutation also left
	the suite green, because with only the chrome check remaining a
	main-inside-banner still answers chrome by falling through -- the previous
	test alone does not catch it, and this one does the same job from the other
	side: a nav nested inside main must read as CHROME, not inherit main.
	"""
	nested = (
		"Home About Contact Careers Press Investors Legal",
		FakeObj("PARAGRAPH"),
		[
			FakeFieldCommand("controlStart", {"role": FakeRole("DOCUMENT")}),
			FakeFieldCommand("controlStart", {"role": FakeRole("SECTION"), "landmark": "main"}),
			FakeFieldCommand("controlStart", {"role": FakeRole("SECTION"), "landmark": "navigation"}),
			FakeFieldCommand("controlStart", {"role": FakeRole("PARAGRAPH")}),
		],
	)
	body = para("A genuine article paragraph with enough text to be a node.")
	nodes, _all, drops = walkSupported(buildDoc([nested, body]))
	texts = [n.textPreview for n in nodes]
	assert not any("Home About" in t for t in texts), (
		"a navigation nested inside <main> is still navigation; the innermost "
		"landmark decides"
	)
	assert any("genuine article" in t for t in texts)
	assert drops >= 1


def test_backendGateRequiresTheModuleNotJustTheName():
	"""SABOTAGE: drop the __module__ check from _fieldsCarryLandmarks.

	A name-only match would trust ANY third-party backend that happened to
	define a class called Gecko_ia2_TextInfo, and being wrongly trusted here
	means admitting chrome as content. No such collision exists in the
	installed NVDA; this closes the hole rather than fixing a live bug.
	"""
	impostor = type("Gecko_ia2_TextInfo", (FakeInfo,), {"__module__": "evil.addon"})
	assert ts._fieldsCarryLandmarks(impostor([], 0, 0)) is False
	genuine = Gecko_ia2_TextInfo([], 0, 0)
	assert ts._fieldsCarryLandmarks(genuine) is True


def test_malformedLandmarkValueIsUnknownNotContent():
	"""SABOTAGE: restore `str(lm).lower()` in _landmarkScopeFromFields.

	A non-string landmark used to be COERCED into a name -- landmark=123
	became "123", matched no chrome type, fell through the loop and returned
	the positive "no chrome ancestor here" verdict. A value we cannot
	interpret is no evidence, and this function's contract is that malformed
	means UNKNOWN. Asserted on the pure function because the walk would mask
	it: the object fallback happens to give the same answer here.
	"""
	def stack(landmarkValue):
		return [
			FakeFieldCommand("controlStart", {"role": FakeRole("DOCUMENT")}),
			FakeFieldCommand("controlStart", {"role": FakeRole("SECTION"), "landmark": landmarkValue}),
		]

	for bad in (123, [], {}, object()):
		assert ts._landmarkScopeFromFields(stack(bad)) is None, (
			f"landmark={bad!r} must read as UNKNOWN, not as a content verdict"
		)


def test_landmarkValueIsStrippedBeforeMatching():
	"""SABOTAGE: remove the .strip() on the landmark value.

	" navigation " is a navigation landmark. Without the strip it matched
	nothing and fell through to the positive content verdict, which is the
	fail-open direction."""
	stack = [
		FakeFieldCommand("controlStart", {"role": FakeRole("DOCUMENT")}),
		FakeFieldCommand("controlStart", {"role": FakeRole("SECTION"), "landmark": "  NAVIGATION  "}),
	]
	assert ts._landmarkScopeFromFields(stack) is False
