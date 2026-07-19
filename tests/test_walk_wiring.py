# Wiring inside the NVDA-bound walk, driven end to end.
#
# WHY THIS FILE EXISTS. Three times on this branch a safety input was found
# DELETABLE with the whole suite still green. Every case had the same shape:
# the RULE was tested as a pure function, and the WIRING that feeds the rule
# lived inside `_walk_main_nodes`, which needs NVDA, so nothing covered it.
# The tests hand-built the very inputs the wiring was supposed to produce.
#
# `_walk_main_nodes` does not actually need NVDA. It needs a treeInterceptor
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

import tree_summary as ts


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
	"""Stand-in for an NVDAObject. `landmark` drives _in_scope, `role` drives
	_node_for. `parent` is the chain the identity filter climbs."""

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
	def _chunk_at_start(self):
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
		c = self._chunk_at_start()
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
		c = self._chunk_at_start()
		return c.text if c else ""

	def getTextWithFields(self, formatConfig=None):
		c = self._chunk_at_start()
		if c is None or c.fields is None:
			return []
		return list(c.fields) + [c.text]

	@property
	def NVDAObjectAtStart(self):
		c = self._chunk_at_start()
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
def _fake_textinfos(monkeypatch):
	monkeypatch.setattr(ts, "textInfos", _FakeTextInfos, raising=False)
	FakeInfo.fetches = []


def build_doc(specs):
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
	"""Run the real walk, returning (nodes, all_nodes, positional_drops)."""
	all_nodes = []
	positions = []
	all_positions = []
	positional = [0]
	nodes = ts._walk_main_nodes(
		FakeTI(doc),
		kw.pop("main_obj", None),
		{},
		positions,
		all_nodes_out=all_nodes,
		all_positions_out=all_positions,
		positional_out=positional,
		**kw,
	)
	return nodes, all_nodes, positional[0]


def para(text, landmark=None):
	"""A paragraph chunk that the buffer DOES emit a control field for, which
	is what all 219 probe chunks looked like."""
	return (
		text,
		FakeObj("PARAGRAPH", landmark=landmark),
		[control("DOCUMENT"), control("PARAGRAPH")],
	)


def para_no_fields(text, landmark=None):
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
# SABOTAGE THIS CATCHES: in _chunk_scope's exclude_ranges branch, change the
# `obj is None` arm from `return False, _SCOPE_IDENTITY` to return True (the
# fail-open default every other path in the module uses).
#
# Why it is not harmless there: chrome-pos routes undecided chunks to the
# identity filter AS its safety mechanism, and an objectless chunk is the one
# class where that filter cannot run at all. Fail-open means a navigation menu
# past the trust boundary reads as article text.

def test_objectless_chunk_past_trust_boundary_is_rejected():
	# Two chunks. The first is inside an emitted chrome range and has an
	# object; the second sits PAST the trust boundary with NO object, so
	# positional cannot decide and identity cannot run.
	doc = build_doc([
		para("navigation home about contact", landmark="navigation"),
		("orphan text with no accessible object at all", None),
	])
	nodes, all_nodes, drops = walk(
		doc,
		exclude_ranges=[rng(0, 29)],
		trust_boundary=rng(0, 0),
		untrusted_ranges=[],
	)
	texts = [n.text_preview for n in nodes]
	assert not any("orphan" in t for t in texts), (
		"an objectless chunk that neither filter could decide was admitted as "
		"content; that is the fail-open the tri-state exists to prevent"
	)
	# It must still reach all_nodes so the depleted-scope net can recover it.
	assert any("orphan" in n.text_preview for n in all_nodes)


# --------------------------------------------------------------------------
# 2. The positional_drops tally
# --------------------------------------------------------------------------
#
# SABOTAGE THIS CATCHES: delete the `positional_hits`/`positional_drops`
# derivation in _walk_main_nodes (the `if scope_decision in (...)` block), or
# stop passing `positional_out` back out.
#
# positional_drops is a SAFETY INPUT, not a diagnostic: _scope_looks_depleted
# keys on `positional_drops == 0` to decide whether a chrome-pos page whose
# exclusions actually worked may be widened back open. Zeroing it silently
# switches the depleted-scope net off on exactly the pages it protects.

def test_positional_drops_counts_chrome_exclusions():
	# Note the trust boundary is the start of the LAST landmark placed, and
	# _starts_before compares STRICTLY — so a chunk sitting exactly at the
	# boundary defers to identity by design. Both chrome chunks here are
	# strictly before it, which is what makes them positional decisions.
	doc = build_doc([
		para("site navigation links across the top", landmark="navigation"),
		para("The real article begins here and runs on for a while."),
		para("footer legal text down at the bottom", landmark="contentinfo"),
		para("a trailing complementary region", landmark="complementary"),
	])
	nav, foot, last = doc[0], doc[2], doc[3]
	nodes, all_nodes, drops = walk(
		doc,
		exclude_ranges=[
			rng(nav.start, nav.end),
			rng(foot.start, foot.end),
			rng(last.start, last.end),
		],
		trust_boundary=rng(last.start, last.end),
		untrusted_ranges=[],
	)
	assert drops == 2, (
		f"expected both chrome chunks counted as positional drops, got {drops}; "
		"the depleted-scope net reads this number"
	)
	assert [n.text_preview for n in nodes] == [
		"The real article begins here and runs on for a while."
	]


def test_positional_drops_is_zero_when_nothing_was_excluded():
	# The other half of the predicate: a page where positional decided
	# everything IN must report zero, so the net can widen it.
	doc = build_doc([
		para("The real article begins here and runs on for a while."),
		para("A second substantial paragraph of genuine body copy."),
	])
	nodes, all_nodes, drops = walk(
		doc,
		exclude_ranges=[rng(9000, 9001)],
		trust_boundary=rng(9000, 9001),
		untrusted_ranges=[],
	)
	assert drops == 0
	assert len(nodes) == 2


# --------------------------------------------------------------------------
# 3. Scope decisions reach the node list (the walk actually consults them)
# --------------------------------------------------------------------------
#
# SABOTAGE THIS CATCHES: making _walk_main_nodes ignore `in_scope` and append
# every node to `result`. Every landing test hands the cascade a node list
# directly, so none of them notice that the filter stopped being applied.

def test_out_of_scope_chunks_are_kept_out_of_main_nodes():
	doc = build_doc([
		para("inside the article body, a substantial sentence here."),
		para("outside it entirely, chrome text that must not land."),
	])
	inside = doc[0]
	nodes, all_nodes, _ = walk(doc, scope_range=rng(inside.start, inside.end))
	assert [n.text_preview for n in nodes] == [
		"inside the article body, a substantial sentence here."
	]
	assert len(all_nodes) == 2, "both chunks must still reach all_nodes"


# --------------------------------------------------------------------------
# 4. Walk-time flags are computed over the FULL text, not the 60-char preview
# --------------------------------------------------------------------------
#
# SABOTAGE THIS CATCHES: dropping the walk-time computation of is_boilerplate /
# is_caption / ends_sentence in _node_for and leaving the cascade's preview
# fallback to cope. Every cascade test can hand-set these flags, which is
# precisely the trap the disclosure flag nearly repeated.

def test_boilerplate_flag_is_computed_past_the_preview_cutoff():
	tail = (
		"This page and everything on it belongs to the publisher and may not "
		"be reproduced. Copyright 2026. All rights reserved."
	)
	assert len(tail) > 60 and "rights reserved" not in tail[:60]
	doc = build_doc([para(tail)])
	nodes, _, _ = walk(doc)
	assert nodes[0].is_boilerplate, (
		"the boilerplate marker sits past char 60, so a preview-only check "
		"cannot see it; this flag must be computed over the full chunk text"
	)


def test_ends_sentence_flag_is_computed_past_the_preview_cutoff():
	long_sentence = (
		"The council met on Tuesday to consider the proposal, which had been "
		"delayed twice already."
	)
	assert len(long_sentence) > 60
	doc = build_doc([para(long_sentence), para("Fragment with no stop")])
	nodes, _, _ = walk(doc)
	assert nodes[0].ends_sentence
	assert not nodes[1].ends_sentence


# --------------------------------------------------------------------------
# 5. The focus-move filter is actually applied
# --------------------------------------------------------------------------
#
# SABOTAGE THIS CATCHES: deleting the `if not _in_main(item): continue` guard
# in set_focus_on_first_form_input, or having it call anything other than the
# walk's own scope decision.
#
# This is the highest-stakes wiring in the module: it is the ONE path that
# calls setFocus(). _form_field_in_scope is pure and covered, but until now
# nothing checked that set_focus_on_first_form_input consults it — which is
# exactly the failure it has already had twice (the Zoom header language
# picker, then the no-<main> header search box).

# --------------------------------------------------------------------------
# 6. The field stack replaces the object for ROLE, and the object stays lazy
# --------------------------------------------------------------------------
#
# Probe evidence (probes/field_stack, 219 chunks over 8 pages):
# chunks_with_no_control_field=0, disagree_innermost=0, field['level'] a str.
#
# SABOTAGE THESE CATCH: reverting to an eager `obj = info.NVDAObjectAtStart`;
# reading the OUTERMOST control field instead of the innermost; dropping the
# int() conversion on the string level; skipping empty-text chunks before the
# heading check (which deletes image-only headings).

def test_role_comes_from_the_innermost_control_field():
	# A heading wrapping a link. INNERMOST is the rule with 219 chunks behind
	# it; outermost-wins would call this a DOCUMENT and heading-first would
	# call it a heading. The probe never observed this shape, so innermost is
	# what we implement — see _role_level_from_fields.
	role, level, had = ts._role_level_from_fields([
		control("DOCUMENT"), control("HEADING", 2), control("LINK"),
	])
	assert (role, level, had) == ("LINK", 0, True)


def test_heading_level_is_converted_from_the_string_gecko_emits():
	role, level, had = ts._role_level_from_fields([
		control("DOCUMENT"), control("HEADING", 3),
	])
	assert role == "HEADING"
	assert level == 3 and isinstance(level, int), (
		"field['level'] is a STRING in Gecko's normalized fields; without the "
		"int() conversion every heading compares wrong against level gates"
	)


def test_only_the_leading_control_run_counts():
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
	role, level, had = ts._role_level_from_fields(stream)
	assert (role, had) == ("PARAGRAPH", True), (
		"a trailing inline control won the role; a paragraph containing an "
		"image would be classified GRAPHIC and skipped as content"
	)


def test_inline_control_paragraph_survives_the_walk():
	# The same defect, driven through the real walk rather than the helper.
	doc = build_doc([(
		"A real body paragraph with an inline image in the middle of it.",
		FakeObj("PARAGRAPH"),
		[
			control("DOCUMENT"), control("PARAGRAPH"),
			"A real body paragraph ",
			control("GRAPHIC"), FakeFieldCommand("controlEnd"),
			" in the middle of it.", FakeFieldCommand("controlEnd"),
		],
	)])
	nodes, _, _ = walk(doc, scope_range=rng(0, 10_000))
	assert [n.kind for n in nodes] == ["paragraph"], (
		"the paragraph was dropped because an inline graphic won the role"
	)


def test_unnamed_innermost_role_does_not_inherit_an_ancestor():
	# A BUTTON whose role fails to resolve must NOT inherit DOCUMENT and be
	# admitted as a paragraph. No usable role at the innermost position means
	# no evidence, so the caller pays for an object and gets the truth.
	class Roleless:
		pass
	stream = [control("DOCUMENT"), FakeFieldCommand("controlStart", {"role": Roleless()})]
	assert ts._role_level_from_fields(stream) == (None, 0, False)


def test_heading_with_unreadable_level_defers_to_the_object():
	# level feeds heading-cluster comparisons in the classifier, so a wrong 0
	# can merge distinct levels and change LIST classification. An unreadable
	# level is not level zero.
	for bad in (None, "", "abc"):
		field = {"role": FakeRole("HEADING")}
		if bad is not None:
			field["level"] = bad
		assert ts._role_level_from_fields([FakeFieldCommand("controlStart", field)]) == (None, 0, False), (
			f"heading with level={bad!r} was accepted as level 0"
		)


def test_object_fetch_failure_is_not_swallowed_into_none():
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

	doc = build_doc([para_no_fields("navigation menu text that must not be admitted")])
	nodes = ts._walk_main_nodes(ExplodingTI(doc), None, {}, [], all_nodes_out=[])
	assert nodes == [], (
		"a COM failure produced a content node; the old eager fetch let the "
		"exception stop the walk and that must not have changed"
	)


def test_no_control_field_reports_no_evidence():
	role, level, had = ts._role_level_from_fields([])
	assert (role, level, had) == (None, 0, False)
	assert ts._role_level_from_fields(None) == (None, 0, False)


def test_walk_takes_the_role_from_fields_without_touching_the_object():
	# A positionally-scoped page: the scope decision needs no object and the
	# role now comes from the field stack, so the walk must resolve ZERO
	# objects. This is the entire performance claim, stated as an assertion.
	doc = build_doc([
		("Chapter One", FakeObj("HEADING"), [control("DOCUMENT"), control("HEADING", 1)]),
		para("A substantial opening paragraph that runs on for a while here."),
	])
	nodes, _, _ = walk(doc, scope_range=rng(0, 10_000))
	assert [n.kind for n in nodes] == ["heading", "paragraph"]
	assert nodes[0].level == 1
	assert FakeInfo.fetches == [], (
		f"the walk resolved {len(FakeInfo.fetches)} object(s) on a fully "
		"positional page; each one is 3+ cross-process COM round trips and "
		"none of them were needed"
	)


def test_walk_falls_back_to_the_object_when_there_is_no_control_field():
	doc = build_doc([para_no_fields("Some text with no control field at all.")])
	nodes, _, _ = walk(doc, scope_range=rng(0, 10_000))
	assert [n.kind for n in nodes] == ["paragraph"]
	assert FakeInfo.fetches, (
		"with no control field there is no role evidence, so the object MUST "
		"be fetched; silently treating it as a paragraph would delete "
		"image-only headings"
	)


def test_image_only_heading_survives_the_field_stack_path():
	# An <h1> wrapping a logo <img>: heading role, empty text. This node drives
	# seen_heading, the hero gate, the prose-run gate and find_list_landing, so
	# an empty-text shortcut ahead of the role check would silently remove it.
	doc = build_doc([
		("", FakeObj("HEADING"), [control("DOCUMENT"), control("HEADING", 1)]),
		para("Body copy following the image-only masthead heading here."),
	])
	nodes, _, _ = walk(doc, scope_range=rng(0, 10_000))
	assert [n.kind for n in nodes] == ["heading", "paragraph"]


def test_identity_scoped_page_still_resolves_objects():
	# The other half of "lazy, not removed": on an identity-scoped page the
	# object is the only evidence there is, and it must still be fetched.
	doc = build_doc([para("Body copy on a page with no usable scope range.")])
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

	def _iterNodesByType(self, item_type):
		if item_type != "edit":
			return iter(())
		return iter(self.items)


def test_focus_move_skips_a_field_inside_chrome(monkeypatch):
	# A header search box inside an emitted <nav>, then the real form field
	# below it. Document order alone would take the search box.
	search = FocusItem("header-search", 0, 10, landmark="navigation")
	real = FocusItem("real-form-field", 100, 110)
	scan = ts.LandmarkScan(
		main_obj=None,
		main_range=None,
		chrome_ranges=[rng(0, 50)],
		other_ranges=[],
		trust_boundary=rng(0, 50),
		seen=1,
		exhausted=True,
	)
	monkeypatch.setattr(ts, "_NVDA_AVAILABLE", True)
	monkeypatch.setattr(ts, "_find_main_landmark", lambda ti: scan)

	ti = FocusTI([search, real])
	assert ts.set_focus_on_first_form_input(ti) is True
	assert search.obj.focused == [], (
		"focus was moved into a field inside a chrome landmark; this is the "
		"path that calls setFocus(), so this is a blind user's caret landing "
		"in the site header"
	)
	assert real.obj.focused == ["real-form-field"]
