# -*- coding: UTF-8 -*-
# Text Marks the Spot — page intent classifier (pure-function form).
#
# Locked design decision #7 in SPEC.md: every page or message is classified
# by intent (article, list, form, video, app, unknown), and a per-intent
# strategy decides what the add-on does next.
#
# This module is pure logic: takes a TreeSummary (a snapshot of what NVDA's
# tree looks like), returns a ClassifierResult. No NVDA imports here so we
# can unit-test against synthetic fixtures without running NVDA. The NVDA
# binding (walking the real tree to build a TreeSummary) lives elsewhere.

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import Optional


class Intent(enum.Enum):
	SILENT_FOCUS_HONORED = "silent_focus_honored"
	FORM = "form"
	ARTICLE = "article"
	LIST = "list"
	APP = "app"
	# A small page whose whole purpose is to deliver a single status message
	# to the user — closed forms, "Thank you for submitting", "404 not
	# found", "Account created", maintenance pages. The user wants to land
	# on the status sentence so they don't have to navigate to find it.
	NOTICE = "notice"
	# A "label + value [+ unit]" widget pattern at the lead of the page —
	# speed test results (fast.com), weather widgets, stock single-quote
	# pages, battery indicators, currency conversions. Land on the label
	# so arrowing forward speaks the value.
	KEY_RESULT = "key_result"
	UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Input: a structured snapshot of what NVDA's tree exposes for the page.
# Everything here must be derivable from the accessibility tree alone — no
# <meta>/<head> signals, no raw HTML. URL is OK; treeInterceptor exposes it.
# ---------------------------------------------------------------------------

@dataclass
class MainNode:
	# One item inside <main> (or the document root if no <main>), in document
	# order. NVDA exposes both headings and paragraph text when walking by
	# UNIT_PARAGRAPH and checking role on each NVDAObjectAtStart — that walk
	# produces the interleaved sequence this list represents.
	kind: str                    # "heading" or "paragraph"
	level: Optional[int] = None  # heading level 1-6; None for paragraphs
	textLength: int = 0         # chars
	textPreview: str = ""       # first ~60 chars, for fixture readability only
	# True when this paragraph is a figure caption / photo credit. Computed
	# at walk time over the FULL chunk text (not the truncated preview),
	# because the giveaway — a trailing "(Getty Images)"-style credit — is
	# usually past the 60-char preview cutoff. Landing finders skip these.
	isCaption: bool = False
	# True when this paragraph is legal footer boilerplate — a copyright
	# line ("Copyright ©2026 ... All rights reserved.") or a CCPA links row
	# ("Do Not Sell My Personal Information"). Computed at walk time over
	# the FULL chunk text, same as isCaption (the "All rights reserved"
	# tail commonly sits past the 60-char preview cutoff). Landing finders
	# skip these, and _heroParagraphChars ignores them so a not-yet-
	# hydrated SPA shell whose only substantial text is the footer
	# copyright (Zoom webinar registration was the canonical case) can't
	# classify as ARTICLE and land the user on the copyright line.
	isBoilerplate: bool = False
	# True when this paragraph is an editorial disclosure — an affiliate /
	# referral note, a syndication credit, or marketing-consent boilerplate.
	# Computed at walk time over the FULL chunk text for two reasons, not one:
	# the giveaway phrase routinely sits past the 60-char preview cutoff, AND
	# the filter's 300-char "a disclosure is SHORT" guard can only be applied
	# against the real length. Checking the preview alone made that guard dead
	# code, so a long genuine lede whose opening 60 chars mentioned affiliate
	# links was chrome-flagged with no length protection. Landing finders skip
	# these.
	isDisclosure: bool = False
	# True when the FULL chunk text ends like a sentence (terminal . ! ? or
	# ellipsis, allowing trailing closing quotes/brackets). Computed at walk
	# time because the terminal punctuation on a 61+ char line sits past the
	# 60-char preview cutoff. Backs the prose-run landing gate in
	# detection/web.py: runs of consecutive SHORT lines (tweet/chat text
	# split line-per-paragraph) qualify as content only when most lines end
	# like sentences — nav menus and form-label runs don't.
	endsSentence: bool = False


@dataclass
class TreeSummary:
	url: str = ""

	# Landmark / structural signals
	hasMainLandmark: bool = False
	articleCount: int = 0          # number of <article> elements in the document

	# True when mainNodes came from a POSITIONAL walk scoped to a single
	# <article> (no <main> landmark, exactly one article). The tree is then
	# free of nav/comments/footer chrome, so landing finders can trust the
	# first substantial paragraph as the real content start instead of applying
	# the defensive hero/cluster gates that exist only for noisy unscoped trees.
	positionallyScoped: bool = False

	# Document-order interleaved nodes inside <main>.
	mainNodes: list[MainNode] = field(default_factory=list)

	# Interactive controls inside <main>.
	formInputCount: int = 0           # editable inputs, comboboxes, etc.
	interactiveControlCount: int = 0  # all interactive: buttons + inputs + links + widgets

	# Guardrail #6: did the page auto-focus an editable control before we fired?
	focusedControlIsEditable: bool = False

	# Set by treeSummary when any node's text matches a status-keyword regex
	# (success/submission/closed/expired/maintenance/error patterns). Used by
	# the NOTICE intent to boost confidence when the page shape is ambiguous.
	noticeKeywordMatch: bool = False

	# Set by treeSummary when the counts phase hit its wall-clock budget or
	# a scan cap, so formInputCount / interactiveControlCount may be
	# UNDERCOUNTS. Undercounting is fail-safe for FORM and APP (both fire on
	# LARGE counts), but NOTICE's shape-only path and KEY_RESULT fire on
	# SMALL counts — a truncated interactive count of 0 on a busy page would
	# make them MORE likely, so they must decline when this is set and leave
	# the page to the 1500 ms retry instead.
	countsTruncated: bool = False

	# Set when the paragraph WALK stopped on a limit (the 2.0 s time budget
	# or the node cap) instead of reaching the end of the document, so
	# mainNodes is a PREFIX of the page. Anything keyed on the ABSENCE of
	# a node shape must treat that absence as unknown when this is set —
	# formWantsBrowseLanding was the incident: a slow hydrating refresh
	# of store.payproglobal.com's checkout truncated the walk before the
	# 200+ char preamble paragraphs, "no rich preamble" selected the
	# bare-form path, and keyboard focus jumped to the Quantity field,
	# while a fast walk of the same page landed in browse mode at the top
	# of the order (2026-07-17). Landing must not depend on walk timing.
	walkTruncated: bool = False

	# Set when the ARTICLE count specifically was truncated (budget, scan
	# cap, or iterator exception). Tracked separately from countsTruncated
	# because articleCount==0 is the undercount that is NOT fail-safe: it
	# drops the hasEditorialContent FORM block, and FORM moves keyboard
	# focus. When set, FORM treats editorial content as UNKNOWN and blocks
	# (with the same form-URL escape hatch as a present <article>).
	articleCountTruncated: bool = False


@dataclass
class ClassifierResult:
	intent: Intent
	confidence: float
	reason: str

	def __str__(self) -> str:
		return f"{self.intent.value} ({self.confidence:.2f}): {self.reason}"


# ---------------------------------------------------------------------------
# Tunables — gathered in one place so we can sweep them later.
# ---------------------------------------------------------------------------

PARAGRAPH_MIN_CHARS = 100         # what counts as a "substantial" body paragraph
PARAGRAPH_CLUSTER_MIN_SIZE = 3    # how many in a row to call it a cluster
PARAGRAPH_CLUSTER_MIN_CHARS = 500 # combined chars across the cluster

# Two ADJACENT paragraphs this long each are unambiguous editorial content
# even though they miss the 3-paragraph cluster bar. armstrongeconomics.com
# blog posts are the canonical case: two 600-char body paragraphs plus a
# 6-input newsletter widget classified as FORM (articleCount=0 on that
# WordPress theme, so the <article> editorial block never engaged) and the
# user landed on the H1 via the form-title path instead of the lede.
MASSIVE_DUO_MIN_CHARS_EACH = 200

# A run of same-level headings is broken when the text between consecutive
# members exceeds this many chars. Calibrated so news/search-snippet pages
# (snippets 100-250 chars per result) still cluster, but article section
# dividers (300+ chars of body between section H2s) break.
HEADING_CLUSTER_MAX_CHARS_BETWEEN = 300

FORM_INPUT_THRESHOLD = 3          # min inputs to suspect a form intent

# A login form is only 2 real inputs (username/email + password), so it can
# never reach FORM_INPUT_THRESHOLD by count alone — starttesting.net/login
# classified UNKNOWN and played the not-found beeps (2026-07-16). When the
# URL says unambiguously "this is an auth page", 2 inputs meet the bar.
# "Unambiguously" is doing real work: unlike the loose substring hints in
# URL_HINTS (which only ever BOOST or UNBLOCK a count that already met the
# threshold), this check LOWERS the bar on a path that ends with FORM moving
# keyboard focus — so it requires the auth word to be a whole path segment.
# /login, /signup?next=/home and auth.example.org match; a blog post at
# /login-security-tips does not. The floor stays at 2: one input plus an
# auth-ish URL is still just a search box on a page whose URL happens to
# contain the word. (Known gap, accepted: single-input staged logins like
# Google's email-first page stay below the bar; Z covers them.)
AUTH_FORM_MIN_INPUTS = 2
_AUTH_URL_SEGMENT_RE = re.compile(
	r"(?:^|[/.:])"
	r"(?:log-?in|sign-?in|sign-?up|register|registration|createaccount|userlogin|auth)"
	r"(?:$|[/?#&.:])"
)
# When formInputCount crosses this bar, the page is unambiguously a form
# regardless of how much heroChars or other "looks like article" signal
# accumulates from form label text in the lead run. Without this override,
# multi-checkbox Google Forms (Pre-ETS Vendor Fair etc.) had ARTICLE-hero
# winning and landing the user on a checkbox label instead of dispatching
# to the FORM path. A page with this many form inputs but a real article body
# would still have hasBodyClusterStrong block FORM via the other gate.
#
# 5 -> 4 on 2026-07-14, because THE THING BEING MEASURED CHANGED. This bar was
# calibrated when formInputCount came from NVDA's "formField" quick-nav type,
# which counts BUTTONS as form fields. So "5" never meant five inputs; it meant
# five inputs-and-buttons, which any control-dense page clears trivially (IMDb
# and a TV station front page both reported 10, and got their focus hijacked
# into a search box as a result).
#
# treeSummary now counts only real inputs (edit / comboBox / checkBox /
# radioButton). Honest counts are much smaller: Wikipedia's account-creation
# form and WebAIM's contact form both report 4. Left at 5, those fall below the
# bar, the hero-paragraph gate blocks FORM, and a genuine registration form
# classifies as an ARTICLE -- landing the user on help text NEXT TO the form
# instead of in it. Casey hit exactly that on Special:CreateAccount.
#
# 4 is the right bar for REAL inputs: a login is 2, a contact form 3-4, a
# registration form 4+. A content page has a lone search box (1), sometimes a
# newsletter email as well (2). Blog comment forms can reach 4, but those pages
# carry an <article> or a strong body cluster, and BOTH of those block FORM
# unconditionally -- this override only ever competes with the hero gate.
STRONG_FORM_INPUT_COUNT = 4
HEADING_CLUSTER_MIN_SIZE = 5      # min same-level adjacent headings to call it a list
ARTICLE_DEMOTE_TO_LIST_AT = 3     # this many <article> siblings = list, not article
APP_CONTROL_FLOOR = 10            # min interactive controls to suspect app intent

# Hero-paragraph fallback (landing-page / mission-statement pattern):
# a substantial intro paragraph sitting in the lead position, even without
# a full body cluster, is enough to classify as article at lower confidence.
#
# DECOUPLED from PARAGRAPH_MIN_CHARS deliberately: many real landing pages
# have intro paragraphs in the 50-100 char range (e.g., bestmidi.com/bg/'s
# "Text-based info and tools for Hearthstone and Battlegrounds." at 60).
# Using the full PARAGRAPH_MIN_CHARS=100 here excludes those legitimate
# heroes. Cluster detection (real article body) still uses the higher
# 100-char bar, so this doesn't make ARTICLE fire on stub pages.
HERO_PARAGRAPH_MIN_CHARS = 50

# When the page has BOTH a hero paragraph AND a borderline heading cluster
# (cards on a landing page), hero >= this many chars wins the tiebreak —
# we treat the page as article (the hero is the content) instead of list
# (the cards are nav). General rule, no per-site customization.
HERO_OVERRIDES_LIST_CHARS = 300

CONFIDENCE_THRESHOLD = 0.6        # below this, return UNKNOWN

# KEY_RESULT intent — fast.com / weather / battery / stock-quote pattern.
# A short label paragraph followed by a value paragraph (mostly digits)
# and either an explicit unit paragraph or an implicit unit char (% $ °).
KEY_RESULT_LABEL_MIN_CHARS = 10
KEY_RESULT_LABEL_MAX_CHARS = 40
KEY_RESULT_VALUE_MAX_CHARS = 8
KEY_RESULT_UNIT_MAX_CHARS = 8
KEY_RESULT_UNIT_LOOKAHEAD = 3      # nodes after the value to scan for unit
# Common units that, when standing alone as a short paragraph, confirm a
# label+value+unit triplet. Lower-cased for matching.
_KEY_RESULT_UNIT_WORDS = frozenset({
	"mbps", "kbps", "gbps", "bps", "tbps",
	"gb", "mb", "kb", "tb", "pb",
	"ms", "sec", "min", "mins", "hr", "hrs",
	"usd", "eur", "gbp", "jpy", "cad", "aud", "chf",
	"%", "kg", "g", "lb", "lbs", "oz", "mg",
	"°c", "°f",
	"mph", "kph", "kmh", "mps",
	"fps", "hz", "khz", "mhz", "ghz",
	"mi", "km", "cm", "mm", "ft", "in", "yd",
})
_KEY_RESULT_IMPLICIT_UNIT_CHARS = "%$°€£¥"

# NOTICE intent (closed forms, success/error pages, "Thank you", 404s).
# Fires only when the page is small and quiet — bigger pages with similar
# keywords (an article that mentions "thank you" in the middle) must not
# match. All checks are AND-ed.
NOTICE_MIN_TEXT_CHARS = 20        # need at least a sentence
NOTICE_MAX_TOTAL_CHARS = 1500     # bigger than this and it's a real content page
NOTICE_MAX_HEADINGS = 3           # 1 H1 + maybe 1-2 supporting headings
NOTICE_MAX_INTERACTIVES = 6       # a few CTAs / footer links, no real UI
# With a status-keyword match, tolerate a couple of form controls: real
# confirmation pages carry widgets like "Add to calendar" that NVDA's
# formField quick-nav class counts (Zoom's "You have successfully
# registered" page counts 1). The shape-only 0.65 path still requires
# ZERO form fields so bare login pages can't classify as notices.
NOTICE_KEYWORD_MAX_FORM_INPUTS = 2

# URL-pattern tiebreakers (lowercase substring match).
URL_HINTS = {
	# Sign-in / account-creation paths were missing, and they are the two most
	# common forms on the web. Wikipedia's account-creation page redirects to
	# auth.wikimedia.org/enwiki/wiki/Special:CreateAccount -- which contains
	# "/wiki/", matches the ARTICLE hints below, and so was blocked from FORM as
	# an "editorial URL". A registration form was being treated as an
	# encyclopedia article, landing the user on the help text BESIDE the form
	# instead of in it. (2026-07-14 soak.)
	Intent.FORM:    (
		"/signup", "/sign-up", "/register", "/contact", "/apply", "/intake",
		"/login", "/signin", "/sign-in", "/log-in",
		"createaccount", "userlogin", "/auth/",
		# A survey / questionnaire page is a form: its whole purpose is to
		# collect answers. WebAIM's Screen Reader User Survey wraps the
		# questions in a single <article>, which blocked FORM and landed the
		# user mid-questions on the longest question label (2026-07-20).
		# "/poll" is deliberately omitted -- plain substring matching would
		# catch "/pollution". "/survey" collides only with the niche
		# "/surveying", which a real body cluster still blocks unconditionally.
		"/survey", "/questionnaire",
	),
	Intent.ARTICLE: ("/article/", "/news/", "/blog/", "/post/", "/story/", "/posts/", "/wiki/", "/podcast"),
	Intent.LIST:    ("/search", "/results", "/category/", "/tag/", "/feed", "/topic/"),
	Intent.APP:     ("/app/", "/compose", "/dashboard", "/admin/"),
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def classify(tree: TreeSummary) -> ClassifierResult:
	# 1. Guardrail #6 — honor website-placed focus on form controls.
	if tree.focusedControlIsEditable:
		return ClassifierResult(
			Intent.SILENT_FOCUS_HONORED, 1.0,
			"Focused editable control — honoring page-placed focus",
		)

	url = tree.url.lower()

	# Compute hero/cluster signals once — used to gate FORM and later by
	# article/list paths.
	bodySize, bodyChars = _largestParagraphCluster(tree.mainNodes)
	headingSize, headingLevel = _largestHeadingCluster(tree.mainNodes)
	heroChars = _heroParagraphChars(tree.mainNodes)

	# 1.5: High-confidence NOTICE — keyword match on a notice-shaped page is
	# a strong "this is a status message" signal that should win over a
	# weaker ARTICLE hero fallback. Without this, a Google Forms closed
	# page (small, 1 H1, one status paragraph) gets classified as ARTICLE
	# at 0.65 via the hero rule before NOTICE (0.85) gets a chance.
	# Functionally both land on the same paragraph, but the intent label
	# matters for downstream features (Z-sequence phasing in SPEC).
	if tree.noticeKeywordMatch:
		earlyNotice = _classifyNotice(tree)
		if earlyNotice is not None and earlyNotice.confidence >= 0.85:
			return earlyNotice

	# 2. Form intent. Threshold + URL boost. Blocked when the page is
	#    ALSO obviously content:
	#    - 3+ <article> siblings (news homepages with newsletter widgets)
	#    - substantial hero paragraph (>= HERO_PARAGRAPH_MIN_CHARS) — a
	#      WordPress homepage with intro text + sidebar widgets isn't
	#      a form page, regardless of how many search/login widgets
	#      live in the sidebar
	#    - substantial body cluster (article page with embedded search etc.)
	strongArticleCluster = tree.articleCount >= ARTICLE_DEMOTE_TO_LIST_AT
	hasHero = heroChars >= HERO_PARAGRAPH_MIN_CHARS
	hasBodyClusterStrong = (
		bodySize >= PARAGRAPH_CLUSTER_MIN_SIZE
		and bodyChars >= PARAGRAPH_CLUSTER_MIN_CHARS
	)
	# Strong form signal (>= STRONG_FORM_INPUT_COUNT inputs) overrides the
	# hero block — a page with 5+ form inputs is a form even if its label
	# text accumulates into a "hero" run. Real-article body cluster still
	# blocks FORM (a sidebar form widget on a news article shouldn't win).
	# The hero block also yields to the form-URL escape hatch, same as the
	# <article> and massive-duo blocks: a signup page's one-line intro
	# ("You can join an existing organization or create one later.", 58
	# chars on starttesting.net/signup) clears the 50-char hero bar while a
	# 3-input registration form sits below STRONG_FORM_INPUT_COUNT, so
	# without the hatch the page classified ARTICLE and the prose-run gate
	# landed the user on the password hint mid-form (2026-07-16).
	strongFormSignal = tree.formInputCount >= STRONG_FORM_INPUT_COUNT
	# Any <article> element on the page is a strong editorial-content
	# signal. A news article (CNET, Wired, NYT, etc.) commonly wraps the
	# story body in <article> AND has 5+ form fields scattered around the
	# page (newsletter signup, search, comment box). The strongFormSignal
	# check would otherwise dispatch these as FORM and move keyboard focus
	# to whichever input came first — usually the newsletter signup box.
	# Block FORM whenever <article> is present unless the URL explicitly
	# looks like a form (/signup, /register, /apply, /intake, /contact).
	# Legitimate signup pages match that URL pattern.
	#
	# A TRUNCATED article count (budget / scan cap / iterator exception)
	# counts as editorial-content-UNKNOWN and blocks the same way: a zeroed
	# undercount here is the one truncation that would make FORM MORE
	# likely, and FORM moves keyboard focus. The form-URL escape hatch
	# still applies, so a genuine /register page survives.
	hasEditorialContent = tree.articleCount >= 1 or tree.articleCountTruncated
	# A pair of ADJACENT massive paragraphs (>= MASSIVE_DUO_MIN_CHARS_EACH
	# each, no heading between) is article body even though it misses the
	# 3-paragraph cluster bar. Same URL escape hatch as the <article>
	# block: a registration page with a rich two-paragraph description
	# (/register, /signup, ...) legitimately stays FORM.
	hasMassiveDuo = _hasMassiveParagraphDuo(tree.mainNodes)
	# An editorial URL (/news/, /blog/, /podcast, /article/, ...) is the
	# mirror image of the FORM URL escape hatch: content pages carry
	# comment boxes, logins, search and newsletter widgets that add up to
	# a strong input count, and sites like thurrott.com expose no
	# <article> for the editorial block to key on. A URL that matches
	# BOTH (e.g. /blog/contact) stays eligible for FORM.
	# The strict segment match also counts as a form-URL hint for the escape
	# hatches and the confidence boost (it is stronger evidence than the
	# loose substring hints, not weaker) — without this, a 2-input login on
	# a URL the loose hints miss (e.g. /auth with no trailing slash) would
	# meet the bar but stall at 0.52 confidence and return UNKNOWN.
	isAuthUrl = _urlIsAuthForm(url)
	formUrlHint = _urlMatches(url, Intent.FORM) or isAuthUrl
	hasEditorialUrl = _urlMatches(url, Intent.ARTICLE) and not formUrlHint
	formBlocked = (
		strongArticleCluster
		or hasBodyClusterStrong
		or (hasHero and not strongFormSignal and not formUrlHint)
		or (hasEditorialContent and not formUrlHint)
		or (hasMassiveDuo and not formUrlHint)
		or hasEditorialUrl
	)
	meetsInputBar = tree.formInputCount >= FORM_INPUT_THRESHOLD or (
		isAuthUrl and tree.formInputCount >= AUTH_FORM_MIN_INPUTS
	)
	if meetsInputBar and not formBlocked:
		confidence = min(0.6 + 0.08 * (tree.formInputCount - FORM_INPUT_THRESHOLD), 0.9)
		if formUrlHint:
			confidence = min(confidence + 0.15, 0.99)
		if confidence >= CONFIDENCE_THRESHOLD:
			return ClassifierResult(
				Intent.FORM, confidence,
				f"{tree.formInputCount} form inputs in main content",
			)

	# (cluster measurements already computed above for the FORM gate.)

	# 4. List intent — checked BEFORE article because multiple <article> siblings
	#    or a strong heading cluster demote what would otherwise look like an
	#    article into a list. EXCEPT: a substantial hero paragraph or body
	#    cluster blocks BOTH list paths. News article pages commonly wrap
	#    each related-stories card in <article>, inflating articleCount to
	#    5+ even on a single-article page — but the article also has a
	#    substantial hero or body cluster that should win.
	isListByArticles = (
		strongArticleCluster
		and not hasHero
		and not hasBodyClusterStrong
	)
	isListByHeadings = (
		headingSize >= HEADING_CLUSTER_MIN_SIZE
		and heroChars < HERO_OVERRIDES_LIST_CHARS
	)
	if isListByArticles or isListByHeadings:
		confidence = 0.7
		if tree.articleCount >= 5:
			confidence = 0.85
		if headingSize >= 10:
			confidence = max(confidence, 0.9)
		if _urlMatches(url, Intent.LIST):
			confidence = min(confidence + 0.1, 0.99)
		if confidence >= CONFIDENCE_THRESHOLD:
			return ClassifierResult(
				Intent.LIST, confidence,
				f"article_count={tree.articleCount}, "
				f"heading_cluster={headingSize}@L{headingLevel}, "
				f"body_cluster={bodySize}",
			)

	# 5. Article intent.
	hasArticleElement = tree.articleCount == 1
	hasBodyCluster = (
		bodySize >= PARAGRAPH_CLUSTER_MIN_SIZE
		and bodyChars >= PARAGRAPH_CLUSTER_MIN_CHARS
	)
	if hasArticleElement and hasBodyCluster:
		return ClassifierResult(
			Intent.ARTICLE, 0.9,
			f"<article> element + body cluster ({bodySize} paragraphs, {bodyChars} chars)",
		)
	if hasBodyCluster:
		confidence = 0.7
		if _urlMatches(url, Intent.ARTICLE):
			confidence = 0.85
		return ClassifierResult(
			Intent.ARTICLE, confidence,
			f"body cluster ({bodySize} paragraphs, {bodyChars} chars), "
			f"no <article> wrapper",
		)

	# 5.5: KEY_RESULT — short "label + value [+ unit]" widget pattern at the
	#      lead of the page. Catches fast.com (speed test), weather widgets,
	#      stock single-quote pages, battery indicators, currency
	#      conversions. Fires only when no body cluster exists (so real
	#      articles with embedded "Score: 5" mentions never match) and only
	#      at lead position (the pattern must appear before any 100+ char
	#      body paragraph).
	keyResult = _classifyKeyResult(tree)
	if keyResult is not None:
		return keyResult

	# 5b. Article fallback — landing-page / hero-paragraph pattern.
	#     A page with substantial paragraph text in a contiguous lead run but
	#     no full body cluster. Catches mission-statement homepages, About-style
	#     pages, and landing pages whose intro paragraph is followed by cards.
	if headingSize < HEADING_CLUSTER_MIN_SIZE or heroChars >= HERO_OVERRIDES_LIST_CHARS:
		if heroChars >= HERO_PARAGRAPH_MIN_CHARS:
			confidence = 0.65
			if tree.articleCount == 1:
				confidence = 0.75
			if _urlMatches(url, Intent.ARTICLE):
				confidence = min(confidence + 0.1, 0.9)
			if confidence >= CONFIDENCE_THRESHOLD:
				return ClassifierResult(
					Intent.ARTICLE, confidence,
					f"hero paragraph ({heroChars} chars in lead position), no body cluster",
				)

	# 6. App intent.
	hasManyControls = tree.interactiveControlCount >= APP_CONTROL_FLOOR
	noBodyCluster = bodySize < PARAGRAPH_CLUSTER_MIN_SIZE
	noHeadingCluster = headingSize < HEADING_CLUSTER_MIN_SIZE
	if hasManyControls and noBodyCluster and noHeadingCluster:
		confidence = 0.65
		if _urlMatches(url, Intent.APP):
			confidence = 0.8
		if confidence >= CONFIDENCE_THRESHOLD:
			return ClassifierResult(
				Intent.APP, confidence,
				f"{tree.interactiveControlCount} interactive controls, no body or heading cluster",
			)

	# 7. Notice intent — last meaningful check before UNKNOWN.
	#    Catches closed forms, "Thank you for submitting", 404 / error pages,
	#    "Account created" confirmations, maintenance pages. Strictly small
	#    pages only — anything with real article body or many controls has
	#    already been claimed above.
	notice = _classifyNotice(tree)
	if notice is not None:
		return notice

	# 8. Unknown.
	return ClassifierResult(
		Intent.UNKNOWN, 0.0,
		"No signal above threshold — guardrail #3 silent",
	)


def _classifyNotice(tree: TreeSummary) -> Optional[ClassifierResult]:
	# NOTICE's shape evidence is SMALL counts, and truncated counts read as
	# small — a busy page whose count phase timed out at 0 interactives
	# would sail through shapeOk. When the counts are untrustworthy, only
	# the keyword path (real text evidence from the walk) may proceed.
	if tree.countsTruncated and not tree.noticeKeywordMatch:
		return None
	# Shape: small total text, few headings, few interactives, no real form.
	totalChars = sum(n.textLength for n in tree.mainNodes)
	headingCount = sum(1 for n in tree.mainNodes if n.kind == "heading")

	shapeOk = (
		totalChars >= NOTICE_MIN_TEXT_CHARS
		and totalChars <= NOTICE_MAX_TOTAL_CHARS
		and headingCount <= NOTICE_MAX_HEADINGS
		and tree.interactiveControlCount <= NOTICE_MAX_INTERACTIVES
	)
	if not shapeOk:
		return None

	# Two paths above the confidence threshold:
	# - Shape + status-keyword match → high confidence ("Thank you for...",
	#   "no longer accepting", "page not found", etc.). Tolerates a couple
	#   of form controls — confirmation pages carry "Add to calendar"-style
	#   widgets that count as form fields (Zoom registration confirmation).
	# - Shape alone, with at least one heading paired to body text → medium
	#   confidence (catches closed forms / error pages whose text doesn't
	#   match our keyword list). Requires ZERO form fields so small real
	#   forms (login pages) can't classify as notices.
	if tree.noticeKeywordMatch and tree.formInputCount <= NOTICE_KEYWORD_MAX_FORM_INPUTS:
		return ClassifierResult(
			Intent.NOTICE, 0.85,
			f"notice shape ({totalChars} chars, {headingCount} headings) "
			f"+ status keyword match",
		)
	if tree.formInputCount == 0 and 1 <= headingCount <= 2:
		return ClassifierResult(
			Intent.NOTICE, 0.65,
			f"notice shape ({totalChars} chars, {headingCount} heading(s))",
		)
	return None


# ---------------------------------------------------------------------------
# Cluster helpers — walk the interleaved node list once each.
# ---------------------------------------------------------------------------

def _largestParagraphCluster(nodes: list[MainNode]) -> tuple[int, int]:
	# Largest run of consecutive paragraph nodes, each >= PARAGRAPH_MIN_CHARS,
	# uninterrupted by any heading. Returns (cluster_size, totalChars).
	#
	# Caption/boilerplate-flagged paragraphs are TRANSPARENT — skipped, not
	# run-breaking. They must not COUNT as body: store.payproglobal.com's
	# 10-input checkout carried three adjacent 100+ char "paragraphs" near
	# the Submit button (trust-badge alt-text blob, the "By placing your
	# order, you agree to our Terms..." consent line, a data-sharing note)
	# that formed a fake strong cluster, blocking FORM and classifying the
	# checkout as ARTICLE — the user landed in the legalese (2026-07-17).
	# But they must not BREAK the run either: a long mid-article figure
	# caption splitting a real article's body cluster would drop the very
	# FORM block that keeps keyboard focus out of a news page's widgets.
	bestSize, bestChars = 0, 0
	curSize, curChars = 0, 0
	for n in nodes:
		if n.kind == "heading":
			curSize, curChars = 0, 0
		elif n.kind == "paragraph":
			if n.isCaption or n.isBoilerplate:
				continue
			if n.textLength >= PARAGRAPH_MIN_CHARS:
				curSize += 1
				curChars += n.textLength
				if curSize > bestSize:
					bestSize, bestChars = curSize, curChars
			else:
				curSize, curChars = 0, 0
	return bestSize, bestChars


def _hasMassiveParagraphDuo(nodes: list[MainNode]) -> bool:
	# True when two ADJACENT paragraph nodes are each >=
	# MASSIVE_DUO_MIN_CHARS_EACH chars, with nothing between them and
	# neither flagged as caption/boilerplate. See classify()'s FORM gate.
	prevMassive = False
	for n in nodes:
		if (
			n.kind == "paragraph"
			and n.textLength >= MASSIVE_DUO_MIN_CHARS_EACH
			and not n.isCaption
			and not n.isBoilerplate
		):
			if prevMassive:
				return True
			prevMassive = True
		else:
			prevMassive = False
	return False


def _largestHeadingCluster(nodes: list[MainNode]) -> tuple[int, int]:
	# Largest run of same-level headings, allowing up to
	# HEADING_CLUSTER_MAX_CHARS_BETWEEN chars of paragraph text between
	# consecutive members. Returns (run_size, level).
	bestSize, bestLevel = 0, 0
	curSize, curLevel = 0, 0
	charsSinceLast = 0

	for n in nodes:
		if n.kind == "heading":
			if curLevel == n.level and charsSinceLast <= HEADING_CLUSTER_MAX_CHARS_BETWEEN:
				curSize += 1
			else:
				curSize = 1
				curLevel = n.level
			charsSinceLast = 0
			if curSize > bestSize:
				bestSize, bestLevel = curSize, curLevel
		elif n.kind == "paragraph":
			charsSinceLast += n.textLength
	return bestSize, bestLevel


def _heroParagraphChars(nodes: list[MainNode]) -> int:
	# Largest run of consecutive paragraphs (no heading between) that contains
	# at least one paragraph >= HERO_PARAGRAPH_MIN_CHARS. Returns the total
	# char count summed across the run.
	#
	# Uses HERO_PARAGRAPH_MIN_CHARS (50), NOT PARAGRAPH_MIN_CHARS (100):
	# landing pages and tool homepages commonly have intro paragraphs in
	# the 50-100 char range (e.g., "Text-based info and tools for X." at
	# 60 chars). Cluster detection elsewhere still uses the 100-char bar.
	#
	# Captures landing-page / mission-statement patterns:
	# - acb.org: H1, P(400, mission), H2 ... → hero = 400+
	# - nfb.org: H1, H1, P(470, mission), H3 ... → hero = 470
	# - bestmidi.com/bg/: nav, P(60, intro), short stats → hero accumulates
	#   to >50 because the 60-char intro is in the lead run
	# A page of short link-list items never qualifies because none of the
	# items is itself substantial enough.
	best = 0
	curChars = 0
	curHasSubstantial = False
	for n in nodes:
		if n.kind == "heading":
			if curHasSubstantial and curChars > best:
				best = curChars
			curChars = 0
			curHasSubstantial = False
		elif n.kind == "paragraph":
			# Legal footer boilerplate (copyright lines, CCPA links rows)
			# never counts as hero text. On a not-yet-hydrated SPA shell the
			# footer copyright is often the ONLY substantial paragraph; letting
			# it qualify as a hero classified the shell as ARTICLE and landed
			# the user on the copyright (Zoom webinar registration). Skipping
			# it here leaves the shell with no signal → no landing → the
			# generic 1500 ms retry gets its chance against the hydrated page.
			if n.isBoilerplate:
				continue
			curChars += n.textLength
			if n.textLength >= HERO_PARAGRAPH_MIN_CHARS:
				curHasSubstantial = True
	if curHasSubstantial and curChars > best:
		best = curChars
	return best


def _urlMatches(url: str, intent: Intent) -> bool:
	return any(hint in url for hint in URL_HINTS.get(intent, ()))


def _urlIsAuthForm(url: str) -> bool:
	# Whole-path-segment auth-page match (see _AUTH_URL_SEGMENT_RE). Caller
	# passes the already-lowercased URL.
	return bool(_AUTH_URL_SEGMENT_RE.search(url))


# ---------------------------------------------------------------------------
# KEY_RESULT pattern detection.
# ---------------------------------------------------------------------------

def _classifyKeyResult(tree: TreeSummary) -> Optional[ClassifierResult]:
	# Apps and forms don't qualify — too much interactivity to be a single
	# key-result widget page.
	if tree.interactiveControlCount > APP_CONTROL_FLOOR:
		return None
	if tree.formInputCount > 0:
		return None
	# Both gates above lean on counts being real. A count phase that hit its
	# budget can report 0 controls on a control-dense page, so decline and
	# let the retry see the page with honest counts.
	if tree.countsTruncated:
		return None
	labelIdx = findKeyResultPatternIndex(tree.mainNodes)
	if labelIdx is None:
		return None
	return ClassifierResult(
		Intent.KEY_RESULT, 0.8,
		f"label+value[+unit] pattern at idx {labelIdx}",
	)


def findKeyResultPatternIndex(nodes: list[MainNode]) -> Optional[int]:
	"""Find a "label + value [+ unit]" pattern at lead position.

	Returns the LABEL node's index, or None.

	Lead position: the pattern must appear before any substantial body
	paragraph (>= PARAGRAPH_MIN_CHARS). This is the key gate — articles
	that mention "Score: 5" inline can't match because the article body
	would already have triggered the stop condition.

	Exposed publicly so detection/web.py's findKeyResultLanding can
	re-locate the same idx without duplicating the matching logic.
	"""
	count = len(nodes)
	for i in range(count):
		n = nodes[i]
		# Stop searching as soon as we hit substantial body content — the
		# pattern is invalid below that point (it's article material).
		if n.kind == "paragraph" and n.textLength >= PARAGRAPH_MIN_CHARS:
			return None
		if i + 1 >= count:
			break
		label = nodes[i]
		value = nodes[i + 1]
		if not _looksLikeKeyResultLabel(label):
			continue
		if not _looksLikeKeyResultValue(value):
			continue
		# Implicit unit (% in value, $ in value, etc.) is enough.
		if any(c in value.textPreview for c in _KEY_RESULT_IMPLICIT_UNIT_CHARS):
			return i
		# Otherwise look for an explicit unit within the next few nodes.
		# Allows for intermediate notes (e.g. fast.com renders a caveat
		# between the value and "Mbps" when the connection is unstable).
		end = min(i + 2 + KEY_RESULT_UNIT_LOOKAHEAD, count)
		for j in range(i + 2, end):
			u = nodes[j]
			if _looksLikeKeyResultUnit(u):
				return i
	return None


def _looksLikeKeyResultLabel(node: MainNode) -> bool:
	if node.kind != "paragraph":
		return False
	if not (KEY_RESULT_LABEL_MIN_CHARS <= node.textLength <= KEY_RESULT_LABEL_MAX_CHARS):
		return False
	s = node.textPreview.strip()
	if not s:
		return False
	# Labels are mostly non-digit text. If a chunk is >30% digits, it's a
	# value, not a label.
	digitCount = sum(c.isdigit() for c in s)
	if digitCount > len(s) * 0.3:
		return False
	return True


def _looksLikeKeyResultValue(node: MainNode) -> bool:
	if node.kind != "paragraph":
		return False
	if not (1 <= node.textLength <= KEY_RESULT_VALUE_MAX_CHARS):
		return False
	s = node.textPreview.strip()
	if not s:
		return False
	# Must contain at least one digit and be predominantly value-shaped
	# characters (digits + formatting + unit hints).
	if not any(c.isdigit() for c in s):
		return False
	allowed = sum(
		1 for c in s
		if c.isdigit() or c in ".,%$-+°€£¥"
	)
	return allowed >= len(s) * 0.7


def _looksLikeKeyResultUnit(node: MainNode) -> bool:
	if node.kind != "paragraph":
		return False
	if not (1 <= node.textLength <= KEY_RESULT_UNIT_MAX_CHARS):
		return False
	s = node.textPreview.strip().lower()
	return s in _KEY_RESULT_UNIT_WORDS
