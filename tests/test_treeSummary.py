# Tests for treeSummary's _nodeFor chunk classifier.
#
# treeSummary.py has guarded NVDA imports so it loads cleanly outside
# NVDA. The _nodeFor function only touches obj.role.name and obj.level
# (plus obj.IA2Attributes for heading-level fallback), so we mock those
# directly and test the role → MainNode mapping without NVDA runtime.

import treeSummary


class _Role:
	def __init__(self, name):
		self.name = name


class _Obj:
	def __init__(self, roleName, level=None, ia2=None):
		self.role = _Role(roleName)
		if level is not None:
			self.level = level
		if ia2 is not None:
			self.IA2Attributes = ia2


def test_nodeForSkipsButtonRole():
	# Regression: krdo.com's AI-generated FAQ question buttons ("What is
	# the duration of the pothole repair surge in Colorado Springs?")
	# were emitted as paragraphs and won the landing via cluster check
	# (adjacent question buttons each ≥50 chars). The walker now filters
	# BUTTON role at chunk emission time so the classifier never sees them.
	assert (
		treeSummary._nodeFor(
			_Obj("BUTTON"),
			"What is the duration of the pothole repair surge in Colorado Springs?",
		)
		is None
	)


def test_nodeForSkipsToggleButtonRole():
	# TOGGLEBUTTON role covers FAQ disclosure widgets (expandable sections).
	# Same reason as BUTTON — UI, not content.
	assert treeSummary._nodeFor(_Obj("TOGGLEBUTTON"), "Show details") is None


def test_nodeForEmitsParagraphForPlainText():
	# Non-special role → paragraph node with stripped text length.
	node = treeSummary._nodeFor(_Obj("STATICTEXT"), "Article body content here.")
	assert node is not None
	assert node.kind == "paragraph"
	assert node.textLength == len("Article body content here.")


def test_nodeForEmitsHeadingForHeadingRole():
	# HEADING role → heading node with level from obj.level.
	node = treeSummary._nodeFor(_Obj("HEADING", level=1), "Section Title")
	assert node is not None
	assert node.kind == "heading"
	assert node.level == 1


def test_nodeForEmitsNoneForGraphicRole():
	# Existing GRAPHIC skip still applies — pin behavior we already had.
	assert treeSummary._nodeFor(_Obj("GRAPHIC"), "alt text") is None


def test_nodeForEmitsParagraphWhenObjIsNone():
	# textInfo chunks sometimes have NVDAObjectAtStart=None; treat the
	# bare text as a paragraph.
	node = treeSummary._nodeFor(None, "Bare text chunk.")
	assert node is not None
	assert node.kind == "paragraph"


def test_nodeForSkipsEmptyText():
	# Whitespace-only or empty text shouldn't be emitted, regardless of role.
	assert treeSummary._nodeFor(_Obj("STATICTEXT"), "   ") is None
	assert treeSummary._nodeFor(None, "") is None


def test_nodeForDoesNotSkipLinkRole():
	# LINK is deliberately NOT in the skip list — inline links inside
	# article body paragraphs are common, and the paragraph carrying them
	# is real content. Verify the walker still emits link-role chunks.
	node = treeSummary._nodeFor(_Obj("LINK"), "Read more about this topic.")
	assert node is not None
	assert node.kind == "paragraph"


def test_nodeForComputesTheDisclosureFlagOverFullText():
	# PINS THE WIRING, not just the rule. The landing cascade reads
	# MainNode.isDisclosure, and every cascade-level test can hand-set that
	# flag - so deleting this computation would leave the whole suite green
	# while the runtime silently stopped detecting disclosures. Twice already
	# on this branch a safety input turned out to be deletable without a test
	# noticing, so the chain gets tested, not the pieces.
	#
	# Full text, deliberately: the giveaway phrase sits past the 60-char
	# preview cutoff, which is the entire reason this moved to walk time.
	text = "Before we get to the recipe, a quick word from our team: this post contains affiliate links."
	assert len(text) > 60
	node = treeSummary._nodeFor(None, text)
	assert node.isDisclosure is True
	# textPreview alone could never have reached the phrase.
	assert "affiliate" not in node.textPreview


def test_nodeForLeavesOrdinaryProseUndisclosed():
	node = treeSummary._nodeFor(
		None,
		"She originally appeared on the show in 1998 and has been a fixture since.",
	)
	assert node.isDisclosure is False


def test_nodeForDisclosureFlagRespectsTheLengthGuard():
	# A long paragraph that mentions affiliate links is an article ABOUT
	# affiliate marketing, not a disclosure. The guard can only be applied
	# against the real length, which is what walk time has and the preview
	# path did not.
	longText = (
		"This post contains referral links, and that is precisely what we want "
		"to talk about today, because the economics of creator compensation "
		"have shifted enormously over the past decade and almost nobody outside "
		"the industry understands how the money actually moves, who ends up "
		"paying for it, or why the disclosure language you skim past reads the "
		"way it does."
	)
	assert len(longText) > 300
	assert treeSummary._nodeFor(None, longText).isDisclosure is False
