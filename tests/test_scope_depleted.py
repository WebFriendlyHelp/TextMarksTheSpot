# The depleted-scope safety net: _scopeLooksDepleted.
#
# The original fallback only fired when the scope filter produced NOTHING. That
# catches total scope failure and misses near-total failure, which is worse: it
# hands the classifier a confident wrong answer instead of an obvious blank.
#
# deadsimpletech.com/blog/midwinter, 2026-07-18. No <main>, so the identity
# chrome filter ran. It kept 3 of 16 walked nodes - all chrome, the first being
# "Get new articles delivered to your inbox" - and discarded the whole article,
# including a 1439-character paragraph. mainNodes was non-empty, so the net
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
# buildTreeSummary needs NVDA.

import treeSummary as ts


class N:
	"""Stand-in for MainNode: only the fields the predicate reads."""

	def __init__(self, kind="paragraph", textLength=0, isBoilerplate=False, isCaption=False):
		self.kind = kind
		self.textLength = textLength
		self.isBoilerplate = isBoilerplate
		self.isCaption = isCaption


def chromeIsh():
	"""What the filter kept on the real page: short chrome fragments."""
	return [N(textLength=42), N(textLength=18), N(textLength=25)]


def articleDoc():
	"""What the walk actually saw: the chrome plus real prose."""
	return chromeIsh() + [
		N(kind="heading", textLength=30),
		N(textLength=1439),
		N(textLength=880),
	]


# ---------------------------------------------------------------------------
# The incident itself.
# ---------------------------------------------------------------------------


def test_deadsimpletechShapeIsRecognisedAsDepleted():
	assert ts._scopeLooksDepleted("chrome", chromeIsh(), articleDoc()) is True


def test_mainIdScopeIsAlsoCovered():
	# The other identity-based scope has the same unreliable parent walk.
	assert ts._scopeLooksDepleted("main-id", chromeIsh(), articleDoc()) is True


# ---------------------------------------------------------------------------
# Guards. Each of these is a page that works today and must keep working.
# ---------------------------------------------------------------------------


def test_positionalScopesAreNeverSecondGuessed():
	# A single-<article> page legitimately drops comments and sidebars; that
	# is the entire job those scopes exist to do. Overruling them would undo
	# it. Same shape as the incident, but must NOT widen.
	for kind in ("article", "main-pos", "unscoped"):
		assert ts._scopeLooksDepleted(kind, chromeIsh(), articleDoc()) is False


def test_chromePosISEligible():
	# Regression guard for a defect this file previously PINNED AS CORRECT.
	# chrome-pos was excluded here, which meant that on the commonest
	# no-<main> shape - one nav landmark at the top, so the trust boundary
	# sits at offset 0 and every chunk takes the identity path anyway - the
	# page reported chrome-pos and had its safety net switched off, re-opening
	# the exact silence bug this net was added to fix. Found by two
	# independent reviews, 2026-07-18.
	assert ts._scopeLooksDepleted("chrome-pos", chromeIsh(), articleDoc()) is True


def test_aLoneLongParagraphIsNotEvidenceOfASwallowedArticle():
	# The false positive both reviewers raised: a small form / checkout /
	# login page whose only long text is a cookie-consent notice, a
	# subscription pitch or a help panel sitting in a correctly excluded
	# banner. isBoilerplate and isCaption are lexical and do not catch
	# those. One long paragraph proves long text exists, not that an article
	# was discarded - so the net now needs TWO.
	doc = chromeIsh() + [N(textLength=900)]
	assert ts._scopeLooksDepleted("chrome", chromeIsh(), doc) is False


def test_scopedTreeWithRealContentIsLeftAlone():
	# The filter did its job: it kept the article. Nothing to widen.
	scoped = chromeIsh() + [N(textLength=300)]
	assert ts._scopeLooksDepleted("chrome", scoped, scoped + [N(textLength=1439)]) is False


def test_shortPageEverywhereDoesNotTripIt():
	# A genuinely brief page - notice, small form, link list. No 200+ char
	# paragraph anywhere, so there is no evidence the filter ate anything.
	doc = chromeIsh() + [N(textLength=60), N(textLength=90)]
	assert ts._scopeLooksDepleted("chrome", chromeIsh(), doc) is False


def test_footerLegalBoilerplateCannotTriggerWidening():
	# The most likely false positive: a small form page whose only long text
	# is the footer legal notice. Widening there could land the user in the
	# footer. The walk-time isBoilerplate flag keeps it out.
	doc = chromeIsh() + [N(textLength=1200, isBoilerplate=True)]
	assert ts._scopeLooksDepleted("chrome", chromeIsh(), doc) is False


def test_photoCreditCannotTriggerWidening():
	doc = chromeIsh() + [N(textLength=400, isCaption=True)]
	assert ts._scopeLooksDepleted("chrome", chromeIsh(), doc) is False


def test_aLongHeadingIsNotArticleContent():
	# Only paragraphs count. A page of long headings is a directory, not an
	# article the filter swallowed.
	doc = chromeIsh() + [N(kind="heading", textLength=1439)]
	assert ts._scopeLooksDepleted("chrome", chromeIsh(), doc) is False


def test_moderatelySubstantialScopedContentBlocksWidening():
	# The asymmetry is the safety margin: 100 in scope is enough to say "the
	# filter kept something real", while the document needs 200 to overrule.
	scoped = chromeIsh() + [N(textLength=100)]
	doc = scoped + [N(textLength=1439)]
	assert ts._scopeLooksDepleted("chrome", scoped, doc) is False


def test_documentContentJustUnderTheBarDoesNotTrigger():
	doc = chromeIsh() + [N(textLength=199)]
	assert ts._scopeLooksDepleted("chrome", chromeIsh(), doc) is False


# ---------------------------------------------------------------------------
# Degenerate inputs: the empty case still belongs to the ORIGINAL net, and
# this predicate must not claim it or double-handle it.
# ---------------------------------------------------------------------------


def test_emptyScopedTreeIsNotThisPredicatesBusiness():
	assert ts._scopeLooksDepleted("chrome", [], articleDoc()) is False


def test_emptyDocumentCannotWiden():
	assert ts._scopeLooksDepleted("chrome", chromeIsh(), []) is False


def test_nothingWasDroppedMeansNothingToWidenTo():
	nodes = articleDoc()
	assert ts._scopeLooksDepleted("chrome", nodes, nodes) is False


# ---------------------------------------------------------------------------
# chrome-pos eligibility keys on EVIDENCE, not on the scope name.
# ---------------------------------------------------------------------------


def test_chromePosThatActuallyScopedPositionallyIsNotWidened():
	# The false positive the second reviewer constructed: a page whose
	# positional exclusions WORKED, correctly removing nav and a cookie
	# banner, then widened back open on the strength of two long chrome
	# paragraphs - re-admitting exactly the text that was correctly removed.
	# One positional EXCLUSION is evidence that removal work happened.
	assert ts._scopeLooksDepleted("chrome-pos", chromeIsh(), articleDoc(), positionalDrops=1) is False


def test_chromePosWithZeroPositionalDecisionsIsStillEligible():
	# The mirror case, and why blanket exclusion was wrong: a trust boundary
	# at offset 0 means nothing is decided positionally, so the page is
	# chrome-scoped in all but name and needs the net.
	assert ts._scopeLooksDepleted("chrome-pos", chromeIsh(), articleDoc(), positionalDrops=0) is True


def test_mainIdIgnoresThePositionalCount():
	# main-id is the ONLY scope that still cannot decide positionally: the field
	# stack answers "inside ANY marked chrome landmark", while main-id asks the
	# IDENTITY question "inside THE <main> we found", so it is deliberately kept
	# on the parent chain. A stray non-zero count must not change eligibility.
	assert ts._scopeLooksDepleted("main-id", chromeIsh(), articleDoc(), positionalDrops=7) is True


def test_chromeScopeNowRespectsItsOwnExclusions():
	"""WAS "identity scopes ignore the positional count", and that premise died
	when the field-stack path landed.

	A chrome-scoped page can now exclude real chrome WITHOUT a parent chain, via
	the field stack. Those exclusions need the same protection chrome-pos gets:
	if the page's exclusions WORKED, widening would re-admit the navigation and
	cookie text that was correctly removed. The scope NAME cannot separate "made
	no exclusions" from "made exclusions that worked"; the drop count can.
	"""
	# Exclusions worked -> do NOT widen.
	assert ts._scopeLooksDepleted("chrome", chromeIsh(), articleDoc(), positionalDrops=7) is False
	# Nothing was excluded -> the net is still available, as before.
	assert ts._scopeLooksDepleted("chrome", chromeIsh(), articleDoc(), positionalDrops=0) is True
