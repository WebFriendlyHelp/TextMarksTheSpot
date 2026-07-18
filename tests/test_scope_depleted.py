# The depleted-scope safety net: _scope_looks_depleted.
#
# The original fallback only fired when the scope filter produced NOTHING. That
# catches total scope failure and misses near-total failure, which is worse: it
# hands the classifier a confident wrong answer instead of an obvious blank.
#
# deadsimpletech.com/blog/midwinter, 2026-07-18. No <main>, so the identity
# chrome filter ran. It kept 3 of 16 walked nodes - all chrome, the first being
# "Get new articles delivered to your inbox" - and discarded the whole article,
# including a 1439-character paragraph. main_nodes was non-empty, so the net
# stayed closed. The classifier correctly reported no article in what it was
# given, declined to land, scheduled the hydration retry, and the retry
# abandoned because the caret had moved. Net effect for the user: silence,
# indistinguishable from the add-on never running.
#
# Pressing Z landed on the real prose immediately, because Z scans the buffer
# directly and never consults the scope filter. That is what proved the content
# was present the whole time.
#
# These tests pin the widening AND, more importantly, the guards that keep it
# off pages that work today. The predicate is pure so it can be tested at all -
# build_tree_summary needs NVDA.

import tree_summary as ts


class N:
	"""Stand-in for MainNode: only the fields the predicate reads."""

	def __init__(self, kind="paragraph", text_length=0, is_boilerplate=False, is_caption=False):
		self.kind = kind
		self.text_length = text_length
		self.is_boilerplate = is_boilerplate
		self.is_caption = is_caption


def chrome_ish():
	"""What the filter kept on the real page: short chrome fragments."""
	return [N(text_length=42), N(text_length=18), N(text_length=25)]


def article_doc():
	"""What the walk actually saw: the chrome plus real prose."""
	return chrome_ish() + [
		N(kind="heading", text_length=30),
		N(text_length=1439),
		N(text_length=880),
	]


# ---------------------------------------------------------------------------
# The incident itself.
# ---------------------------------------------------------------------------

def test_deadsimpletech_shape_is_recognised_as_depleted():
	assert ts._scope_looks_depleted("chrome", chrome_ish(), article_doc()) is True


def test_main_id_scope_is_also_covered():
	# The other identity-based scope has the same unreliable parent walk.
	assert ts._scope_looks_depleted("main-id", chrome_ish(), article_doc()) is True


# ---------------------------------------------------------------------------
# Guards. Each of these is a page that works today and must keep working.
# ---------------------------------------------------------------------------

def test_positional_scopes_are_never_second_guessed():
	# A single-<article> page legitimately drops comments and sidebars; that
	# is the entire job those scopes exist to do. Overruling them would undo
	# it. Same shape as the incident, but must NOT widen.
	for kind in ("article", "main-pos", "unscoped"):
		assert ts._scope_looks_depleted(kind, chrome_ish(), article_doc()) is False


def test_chrome_pos_IS_eligible():
	# Regression guard for a defect this file previously PINNED AS CORRECT.
	# chrome-pos was excluded here, which meant that on the commonest
	# no-<main> shape - one nav landmark at the top, so the trust boundary
	# sits at offset 0 and every chunk takes the identity path anyway - the
	# page reported chrome-pos and had its safety net switched off, re-opening
	# the exact silence bug this net was added to fix. Found by two
	# independent reviews, 2026-07-18.
	assert ts._scope_looks_depleted("chrome-pos", chrome_ish(), article_doc()) is True


def test_a_lone_long_paragraph_is_not_evidence_of_a_swallowed_article():
	# The false positive both reviewers raised: a small form / checkout /
	# login page whose only long text is a cookie-consent notice, a
	# subscription pitch or a help panel sitting in a correctly excluded
	# banner. is_boilerplate and is_caption are lexical and do not catch
	# those. One long paragraph proves long text exists, not that an article
	# was discarded - so the net now needs TWO.
	doc = chrome_ish() + [N(text_length=900)]
	assert ts._scope_looks_depleted("chrome", chrome_ish(), doc) is False


def test_scoped_tree_with_real_content_is_left_alone():
	# The filter did its job: it kept the article. Nothing to widen.
	scoped = chrome_ish() + [N(text_length=300)]
	assert ts._scope_looks_depleted("chrome", scoped, scoped + [N(text_length=1439)]) is False


def test_short_page_everywhere_does_not_trip_it():
	# A genuinely brief page - notice, small form, link list. No 200+ char
	# paragraph anywhere, so there is no evidence the filter ate anything.
	doc = chrome_ish() + [N(text_length=60), N(text_length=90)]
	assert ts._scope_looks_depleted("chrome", chrome_ish(), doc) is False


def test_footer_legal_boilerplate_cannot_trigger_widening():
	# The most likely false positive: a small form page whose only long text
	# is the footer legal notice. Widening there could land the user in the
	# footer. The walk-time is_boilerplate flag keeps it out.
	doc = chrome_ish() + [N(text_length=1200, is_boilerplate=True)]
	assert ts._scope_looks_depleted("chrome", chrome_ish(), doc) is False


def test_photo_credit_cannot_trigger_widening():
	doc = chrome_ish() + [N(text_length=400, is_caption=True)]
	assert ts._scope_looks_depleted("chrome", chrome_ish(), doc) is False


def test_a_long_heading_is_not_article_content():
	# Only paragraphs count. A page of long headings is a directory, not an
	# article the filter swallowed.
	doc = chrome_ish() + [N(kind="heading", text_length=1439)]
	assert ts._scope_looks_depleted("chrome", chrome_ish(), doc) is False


def test_moderately_substantial_scoped_content_blocks_widening():
	# The asymmetry is the safety margin: 100 in scope is enough to say "the
	# filter kept something real", while the document needs 200 to overrule.
	scoped = chrome_ish() + [N(text_length=100)]
	doc = scoped + [N(text_length=1439)]
	assert ts._scope_looks_depleted("chrome", scoped, doc) is False


def test_document_content_just_under_the_bar_does_not_trigger():
	doc = chrome_ish() + [N(text_length=199)]
	assert ts._scope_looks_depleted("chrome", chrome_ish(), doc) is False


# ---------------------------------------------------------------------------
# Degenerate inputs: the empty case still belongs to the ORIGINAL net, and
# this predicate must not claim it or double-handle it.
# ---------------------------------------------------------------------------

def test_empty_scoped_tree_is_not_this_predicates_business():
	assert ts._scope_looks_depleted("chrome", [], article_doc()) is False


def test_empty_document_cannot_widen():
	assert ts._scope_looks_depleted("chrome", chrome_ish(), []) is False


def test_nothing_was_dropped_means_nothing_to_widen_to():
	nodes = article_doc()
	assert ts._scope_looks_depleted("chrome", nodes, nodes) is False
