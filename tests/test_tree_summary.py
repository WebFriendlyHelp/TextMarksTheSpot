# Tests for tree_summary's _node_for chunk classifier.
#
# tree_summary.py has guarded NVDA imports so it loads cleanly outside
# NVDA. The _node_for function only touches obj.role.name and obj.level
# (plus obj.IA2Attributes for heading-level fallback), so we mock those
# directly and test the role → MainNode mapping without NVDA runtime.

import tree_summary


class _Role:
	def __init__(self, name):
		self.name = name


class _Obj:
	def __init__(self, role_name, level=None, ia2=None):
		self.role = _Role(role_name)
		if level is not None:
			self.level = level
		if ia2 is not None:
			self.IA2Attributes = ia2


def test_node_for_skips_button_role():
	# Regression: krdo.com's AI-generated FAQ question buttons ("What is
	# the duration of the pothole repair surge in Colorado Springs?")
	# were emitted as paragraphs and won the landing via cluster check
	# (adjacent question buttons each ≥50 chars). The walker now filters
	# BUTTON role at chunk emission time so the classifier never sees them.
	assert tree_summary._node_for(
		_Obj("BUTTON"),
		"What is the duration of the pothole repair surge in Colorado Springs?",
	) is None


def test_node_for_skips_toggle_button_role():
	# TOGGLEBUTTON role covers FAQ disclosure widgets (expandable sections).
	# Same reason as BUTTON — UI, not content.
	assert tree_summary._node_for(_Obj("TOGGLEBUTTON"), "Show details") is None


def test_node_for_emits_paragraph_for_plain_text():
	# Non-special role → paragraph node with stripped text length.
	node = tree_summary._node_for(_Obj("STATICTEXT"), "Article body content here.")
	assert node is not None
	assert node.kind == "paragraph"
	assert node.text_length == len("Article body content here.")


def test_node_for_emits_heading_for_heading_role():
	# HEADING role → heading node with level from obj.level.
	node = tree_summary._node_for(_Obj("HEADING", level=1), "Section Title")
	assert node is not None
	assert node.kind == "heading"
	assert node.level == 1


def test_node_for_emits_none_for_graphic_role():
	# Existing GRAPHIC skip still applies — pin behavior we already had.
	assert tree_summary._node_for(_Obj("GRAPHIC"), "alt text") is None


def test_node_for_emits_paragraph_when_obj_is_none():
	# textInfo chunks sometimes have NVDAObjectAtStart=None; treat the
	# bare text as a paragraph.
	node = tree_summary._node_for(None, "Bare text chunk.")
	assert node is not None
	assert node.kind == "paragraph"


def test_node_for_skips_empty_text():
	# Whitespace-only or empty text shouldn't be emitted, regardless of role.
	assert tree_summary._node_for(_Obj("STATICTEXT"), "   ") is None
	assert tree_summary._node_for(None, "") is None


def test_node_for_does_not_skip_link_role():
	# LINK is deliberately NOT in the skip list — inline links inside
	# article body paragraphs are common, and the paragraph carrying them
	# is real content. Verify the walker still emits link-role chunks.
	node = tree_summary._node_for(_Obj("LINK"), "Read more about this topic.")
	assert node is not None
	assert node.kind == "paragraph"


def test_node_for_computes_the_disclosure_flag_over_full_text():
	# PINS THE WIRING, not just the rule. The landing cascade reads
	# MainNode.is_disclosure, and every cascade-level test can hand-set that
	# flag - so deleting this computation would leave the whole suite green
	# while the runtime silently stopped detecting disclosures. Twice already
	# on this branch a safety input turned out to be deletable without a test
	# noticing, so the chain gets tested, not the pieces.
	#
	# Full text, deliberately: the giveaway phrase sits past the 60-char
	# preview cutoff, which is the entire reason this moved to walk time.
	text = (
		"Before we get to the recipe, a quick word from our team: this post "
		"contains affiliate links."
	)
	assert len(text) > 60
	node = tree_summary._node_for(None, text)
	assert node.is_disclosure is True
	# text_preview alone could never have reached the phrase.
	assert "affiliate" not in node.text_preview


def test_node_for_leaves_ordinary_prose_undisclosed():
	node = tree_summary._node_for(
		None,
		"She originally appeared on the show in 1998 and has been a fixture since.",
	)
	assert node.is_disclosure is False


def test_node_for_disclosure_flag_respects_the_length_guard():
	# A long paragraph that mentions affiliate links is an article ABOUT
	# affiliate marketing, not a disclosure. The guard can only be applied
	# against the real length, which is what walk time has and the preview
	# path did not.
	long_text = (
		"This post contains referral links, and that is precisely what we want "
		"to talk about today, because the economics of creator compensation "
		"have shifted enormously over the past decade and almost nobody outside "
		"the industry understands how the money actually moves, who ends up "
		"paying for it, or why the disclosure language you skim past reads the "
		"way it does."
	)
	assert len(long_text) > 300
	assert tree_summary._node_for(None, long_text).is_disclosure is False
