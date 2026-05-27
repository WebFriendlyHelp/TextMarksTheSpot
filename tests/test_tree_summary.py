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
