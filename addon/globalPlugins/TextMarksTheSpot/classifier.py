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
	text_length: int = 0         # chars
	text_preview: str = ""       # first ~60 chars, for fixture readability only
	# True when this paragraph is a figure caption / photo credit. Computed
	# at walk time over the FULL chunk text (not the truncated preview),
	# because the giveaway — a trailing "(Getty Images)"-style credit — is
	# usually past the 60-char preview cutoff. Landing finders skip these.
	is_caption: bool = False


@dataclass
class TreeSummary:
	url: str = ""

	# Landmark / structural signals
	has_main_landmark: bool = False
	article_count: int = 0          # number of <article> elements in the document

	# True when main_nodes came from a POSITIONAL walk scoped to a single
	# <article> (no <main> landmark, exactly one article). The tree is then
	# free of nav/comments/footer chrome, so landing finders can trust the
	# first substantial paragraph as the real content start instead of applying
	# the defensive hero/cluster gates that exist only for noisy unscoped trees.
	positionally_scoped: bool = False

	# Document-order interleaved nodes inside <main>.
	main_nodes: list[MainNode] = field(default_factory=list)

	# Interactive controls inside <main>.
	form_input_count: int = 0           # editable inputs, comboboxes, etc.
	interactive_control_count: int = 0  # all interactive: buttons + inputs + links + widgets

	# Guardrail #6: did the page auto-focus an editable control before we fired?
	focused_control_is_editable: bool = False

	# Set by tree_summary when any node's text matches a status-keyword regex
	# (success/submission/closed/expired/maintenance/error patterns). Used by
	# the NOTICE intent to boost confidence when the page shape is ambiguous.
	notice_keyword_match: bool = False


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

# A run of same-level headings is broken when the text between consecutive
# members exceeds this many chars. Calibrated so news/search-snippet pages
# (snippets 100-250 chars per result) still cluster, but article section
# dividers (300+ chars of body between section H2s) break.
HEADING_CLUSTER_MAX_CHARS_BETWEEN = 300

FORM_INPUT_THRESHOLD = 3          # min inputs to suspect a form intent
# When form_input_count crosses this bar, the page is unambiguously a form
# regardless of how much hero_chars or other "looks like article" signal
# accumulates from form label text in the lead run. Without this override,
# multi-checkbox Google Forms (Pre-ETS Vendor Fair etc.) had ARTICLE-hero
# winning and landing the user on a checkbox label instead of dispatching
# to the FORM path. A page with 5+ form inputs but real article body
# would still have has_body_cluster_strong block FORM via the other gate.
STRONG_FORM_INPUT_COUNT = 5
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

# URL-pattern tiebreakers (lowercase substring match).
URL_HINTS = {
	Intent.FORM:    ("/signup", "/sign-up", "/register", "/contact", "/apply", "/intake"),
	Intent.ARTICLE: ("/article/", "/news/", "/blog/", "/post/", "/story/", "/posts/", "/wiki/"),
	Intent.LIST:    ("/search", "/results", "/category/", "/tag/", "/feed", "/topic/"),
	Intent.APP:     ("/app/", "/compose", "/dashboard", "/admin/"),
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def classify(tree: TreeSummary) -> ClassifierResult:
	# 1. Guardrail #6 — honor website-placed focus on form controls.
	if tree.focused_control_is_editable:
		return ClassifierResult(
			Intent.SILENT_FOCUS_HONORED, 1.0,
			"Focused editable control — honoring page-placed focus",
		)

	url = tree.url.lower()

	# Compute hero/cluster signals once — used to gate FORM and later by
	# article/list paths.
	body_size, body_chars = _largest_paragraph_cluster(tree.main_nodes)
	heading_size, heading_level = _largest_heading_cluster(tree.main_nodes)
	hero_chars = _hero_paragraph_chars(tree.main_nodes)

	# 1.5: High-confidence NOTICE — keyword match on a notice-shaped page is
	# a strong "this is a status message" signal that should win over a
	# weaker ARTICLE hero fallback. Without this, a Google Forms closed
	# page (small, 1 H1, one status paragraph) gets classified as ARTICLE
	# at 0.65 via the hero rule before NOTICE (0.85) gets a chance.
	# Functionally both land on the same paragraph, but the intent label
	# matters for downstream features (Z-sequence phasing in SPEC).
	if tree.notice_keyword_match:
		early_notice = _classify_notice(tree)
		if early_notice is not None and early_notice.confidence >= 0.85:
			return early_notice

	# 2. Form intent. Threshold + URL boost. Blocked when the page is
	#    ALSO obviously content:
	#    - 3+ <article> siblings (news homepages with newsletter widgets)
	#    - substantial hero paragraph (>= HERO_PARAGRAPH_MIN_CHARS) — a
	#      WordPress homepage with intro text + sidebar widgets isn't
	#      a form page, regardless of how many search/login widgets
	#      live in the sidebar
	#    - substantial body cluster (article page with embedded search etc.)
	strong_article_cluster = tree.article_count >= ARTICLE_DEMOTE_TO_LIST_AT
	has_hero = hero_chars >= HERO_PARAGRAPH_MIN_CHARS
	has_body_cluster_strong = (
		body_size >= PARAGRAPH_CLUSTER_MIN_SIZE
		and body_chars >= PARAGRAPH_CLUSTER_MIN_CHARS
	)
	# Strong form signal (>= STRONG_FORM_INPUT_COUNT inputs) overrides the
	# hero block — a page with 5+ form inputs is a form even if its label
	# text accumulates into a "hero" run. Real-article body cluster still
	# blocks FORM (a sidebar form widget on a news article shouldn't win).
	strong_form_signal = tree.form_input_count >= STRONG_FORM_INPUT_COUNT
	# Any <article> element on the page is a strong editorial-content
	# signal. A news article (CNET, Wired, NYT, etc.) commonly wraps the
	# story body in <article> AND has 5+ form fields scattered around the
	# page (newsletter signup, search, comment box). The strong_form_signal
	# check would otherwise dispatch these as FORM and move keyboard focus
	# to whichever input came first — usually the newsletter signup box.
	# Block FORM whenever <article> is present unless the URL explicitly
	# looks like a form (/signup, /register, /apply, /intake, /contact).
	# Legitimate signup pages match that URL pattern.
	has_editorial_content = tree.article_count >= 1
	form_blocked = (
		strong_article_cluster
		or has_body_cluster_strong
		or (has_hero and not strong_form_signal)
		or (has_editorial_content and not _url_matches(url, Intent.FORM))
	)
	if tree.form_input_count >= FORM_INPUT_THRESHOLD and not form_blocked:
		confidence = min(0.6 + 0.08 * (tree.form_input_count - FORM_INPUT_THRESHOLD), 0.9)
		if _url_matches(url, Intent.FORM):
			confidence = min(confidence + 0.15, 0.99)
		if confidence >= CONFIDENCE_THRESHOLD:
			return ClassifierResult(
				Intent.FORM, confidence,
				f"{tree.form_input_count} form inputs in main content",
			)

	# (cluster measurements already computed above for the FORM gate.)

	# 4. List intent — checked BEFORE article because multiple <article> siblings
	#    or a strong heading cluster demote what would otherwise look like an
	#    article into a list. EXCEPT: a substantial hero paragraph or body
	#    cluster blocks BOTH list paths. News article pages commonly wrap
	#    each related-stories card in <article>, inflating article_count to
	#    5+ even on a single-article page — but the article also has a
	#    substantial hero or body cluster that should win.
	is_list_by_articles = (
		strong_article_cluster
		and not has_hero
		and not has_body_cluster_strong
	)
	is_list_by_headings = (
		heading_size >= HEADING_CLUSTER_MIN_SIZE
		and hero_chars < HERO_OVERRIDES_LIST_CHARS
	)
	if is_list_by_articles or is_list_by_headings:
		confidence = 0.7
		if tree.article_count >= 5:
			confidence = 0.85
		if heading_size >= 10:
			confidence = max(confidence, 0.9)
		if _url_matches(url, Intent.LIST):
			confidence = min(confidence + 0.1, 0.99)
		if confidence >= CONFIDENCE_THRESHOLD:
			return ClassifierResult(
				Intent.LIST, confidence,
				f"article_count={tree.article_count}, "
				f"heading_cluster={heading_size}@L{heading_level}, "
				f"body_cluster={body_size}",
			)

	# 5. Article intent.
	has_article_element = tree.article_count == 1
	has_body_cluster = (
		body_size >= PARAGRAPH_CLUSTER_MIN_SIZE
		and body_chars >= PARAGRAPH_CLUSTER_MIN_CHARS
	)
	if has_article_element and has_body_cluster:
		return ClassifierResult(
			Intent.ARTICLE, 0.9,
			f"<article> element + body cluster ({body_size} paragraphs, {body_chars} chars)",
		)
	if has_body_cluster:
		confidence = 0.7
		if _url_matches(url, Intent.ARTICLE):
			confidence = 0.85
		return ClassifierResult(
			Intent.ARTICLE, confidence,
			f"body cluster ({body_size} paragraphs, {body_chars} chars), "
			f"no <article> wrapper",
		)

	# 5.5: KEY_RESULT — short "label + value [+ unit]" widget pattern at the
	#      lead of the page. Catches fast.com (speed test), weather widgets,
	#      stock single-quote pages, battery indicators, currency
	#      conversions. Fires only when no body cluster exists (so real
	#      articles with embedded "Score: 5" mentions never match) and only
	#      at lead position (the pattern must appear before any 100+ char
	#      body paragraph).
	key_result = _classify_key_result(tree)
	if key_result is not None:
		return key_result

	# 5b. Article fallback — landing-page / hero-paragraph pattern.
	#     A page with substantial paragraph text in a contiguous lead run but
	#     no full body cluster. Catches mission-statement homepages, About-style
	#     pages, and landing pages whose intro paragraph is followed by cards.
	if heading_size < HEADING_CLUSTER_MIN_SIZE or hero_chars >= HERO_OVERRIDES_LIST_CHARS:
		if hero_chars >= HERO_PARAGRAPH_MIN_CHARS:
			confidence = 0.65
			if tree.article_count == 1:
				confidence = 0.75
			if _url_matches(url, Intent.ARTICLE):
				confidence = min(confidence + 0.1, 0.9)
			if confidence >= CONFIDENCE_THRESHOLD:
				return ClassifierResult(
					Intent.ARTICLE, confidence,
					f"hero paragraph ({hero_chars} chars in lead position), no body cluster",
				)

	# 6. App intent.
	has_many_controls = tree.interactive_control_count >= APP_CONTROL_FLOOR
	no_body_cluster = body_size < PARAGRAPH_CLUSTER_MIN_SIZE
	no_heading_cluster = heading_size < HEADING_CLUSTER_MIN_SIZE
	if has_many_controls and no_body_cluster and no_heading_cluster:
		confidence = 0.65
		if _url_matches(url, Intent.APP):
			confidence = 0.8
		if confidence >= CONFIDENCE_THRESHOLD:
			return ClassifierResult(
				Intent.APP, confidence,
				f"{tree.interactive_control_count} interactive controls, no body or heading cluster",
			)

	# 7. Notice intent — last meaningful check before UNKNOWN.
	#    Catches closed forms, "Thank you for submitting", 404 / error pages,
	#    "Account created" confirmations, maintenance pages. Strictly small
	#    pages only — anything with real article body or many controls has
	#    already been claimed above.
	notice = _classify_notice(tree)
	if notice is not None:
		return notice

	# 8. Unknown.
	return ClassifierResult(
		Intent.UNKNOWN, 0.0,
		"No signal above threshold — guardrail #3 silent",
	)


def _classify_notice(tree: TreeSummary) -> Optional[ClassifierResult]:
	# Shape: small total text, few headings, few interactives, no real form.
	total_chars = sum(n.text_length for n in tree.main_nodes)
	heading_count = sum(1 for n in tree.main_nodes if n.kind == "heading")

	shape_ok = (
		total_chars >= NOTICE_MIN_TEXT_CHARS
		and total_chars <= NOTICE_MAX_TOTAL_CHARS
		and heading_count <= NOTICE_MAX_HEADINGS
		and tree.interactive_control_count <= NOTICE_MAX_INTERACTIVES
		and tree.form_input_count == 0
	)
	if not shape_ok:
		return None

	# Two paths above the confidence threshold:
	# - Shape + status-keyword match → high confidence ("Thank you for...",
	#   "no longer accepting", "page not found", etc.).
	# - Shape alone, with at least one heading paired to body text → medium
	#   confidence (catches closed forms / error pages whose text doesn't
	#   match our keyword list).
	if tree.notice_keyword_match:
		return ClassifierResult(
			Intent.NOTICE, 0.85,
			f"notice shape ({total_chars} chars, {heading_count} headings) "
			f"+ status keyword match",
		)
	if 1 <= heading_count <= 2:
		return ClassifierResult(
			Intent.NOTICE, 0.65,
			f"notice shape ({total_chars} chars, {heading_count} heading(s))",
		)
	return None


# ---------------------------------------------------------------------------
# Cluster helpers — walk the interleaved node list once each.
# ---------------------------------------------------------------------------

def _largest_paragraph_cluster(nodes: list[MainNode]) -> tuple[int, int]:
	# Largest run of consecutive paragraph nodes, each >= PARAGRAPH_MIN_CHARS,
	# uninterrupted by any heading. Returns (cluster_size, total_chars).
	best_size, best_chars = 0, 0
	cur_size, cur_chars = 0, 0
	for n in nodes:
		if n.kind == "heading":
			cur_size, cur_chars = 0, 0
		elif n.kind == "paragraph":
			if n.text_length >= PARAGRAPH_MIN_CHARS:
				cur_size += 1
				cur_chars += n.text_length
				if cur_size > best_size:
					best_size, best_chars = cur_size, cur_chars
			else:
				cur_size, cur_chars = 0, 0
	return best_size, best_chars


def _largest_heading_cluster(nodes: list[MainNode]) -> tuple[int, int]:
	# Largest run of same-level headings, allowing up to
	# HEADING_CLUSTER_MAX_CHARS_BETWEEN chars of paragraph text between
	# consecutive members. Returns (run_size, level).
	best_size, best_level = 0, 0
	cur_size, cur_level = 0, 0
	chars_since_last = 0

	for n in nodes:
		if n.kind == "heading":
			if cur_level == n.level and chars_since_last <= HEADING_CLUSTER_MAX_CHARS_BETWEEN:
				cur_size += 1
			else:
				cur_size = 1
				cur_level = n.level
			chars_since_last = 0
			if cur_size > best_size:
				best_size, best_level = cur_size, cur_level
		elif n.kind == "paragraph":
			chars_since_last += n.text_length
	return best_size, best_level


def _hero_paragraph_chars(nodes: list[MainNode]) -> int:
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
	cur_chars = 0
	cur_has_substantial = False
	for n in nodes:
		if n.kind == "heading":
			if cur_has_substantial and cur_chars > best:
				best = cur_chars
			cur_chars = 0
			cur_has_substantial = False
		elif n.kind == "paragraph":
			cur_chars += n.text_length
			if n.text_length >= HERO_PARAGRAPH_MIN_CHARS:
				cur_has_substantial = True
	if cur_has_substantial and cur_chars > best:
		best = cur_chars
	return best


def _url_matches(url: str, intent: Intent) -> bool:
	return any(hint in url for hint in URL_HINTS.get(intent, ()))


# ---------------------------------------------------------------------------
# KEY_RESULT pattern detection.
# ---------------------------------------------------------------------------

def _classify_key_result(tree: TreeSummary) -> Optional[ClassifierResult]:
	# Apps and forms don't qualify — too much interactivity to be a single
	# key-result widget page.
	if tree.interactive_control_count > APP_CONTROL_FLOOR:
		return None
	if tree.form_input_count > 0:
		return None
	label_idx = find_key_result_pattern_index(tree.main_nodes)
	if label_idx is None:
		return None
	return ClassifierResult(
		Intent.KEY_RESULT, 0.8,
		f"label+value[+unit] pattern at idx {label_idx}",
	)


def find_key_result_pattern_index(nodes: list[MainNode]) -> Optional[int]:
	"""Find a "label + value [+ unit]" pattern at lead position.

	Returns the LABEL node's index, or None.

	Lead position: the pattern must appear before any substantial body
	paragraph (>= PARAGRAPH_MIN_CHARS). This is the key gate — articles
	that mention "Score: 5" inline can't match because the article body
	would already have triggered the stop condition.

	Exposed publicly so detection/web.py's find_key_result_landing can
	re-locate the same idx without duplicating the matching logic.
	"""
	count = len(nodes)
	for i in range(count):
		n = nodes[i]
		# Stop searching as soon as we hit substantial body content — the
		# pattern is invalid below that point (it's article material).
		if n.kind == "paragraph" and n.text_length >= PARAGRAPH_MIN_CHARS:
			return None
		if i + 1 >= count:
			break
		label = nodes[i]
		value = nodes[i + 1]
		if not _looks_like_key_result_label(label):
			continue
		if not _looks_like_key_result_value(value):
			continue
		# Implicit unit (% in value, $ in value, etc.) is enough.
		if any(c in value.text_preview for c in _KEY_RESULT_IMPLICIT_UNIT_CHARS):
			return i
		# Otherwise look for an explicit unit within the next few nodes.
		# Allows for intermediate notes (e.g. fast.com renders a caveat
		# between the value and "Mbps" when the connection is unstable).
		end = min(i + 2 + KEY_RESULT_UNIT_LOOKAHEAD, count)
		for j in range(i + 2, end):
			u = nodes[j]
			if _looks_like_key_result_unit(u):
				return i
	return None


def _looks_like_key_result_label(node: MainNode) -> bool:
	if node.kind != "paragraph":
		return False
	if not (KEY_RESULT_LABEL_MIN_CHARS <= node.text_length <= KEY_RESULT_LABEL_MAX_CHARS):
		return False
	s = node.text_preview.strip()
	if not s:
		return False
	# Labels are mostly non-digit text. If a chunk is >30% digits, it's a
	# value, not a label.
	digit_count = sum(c.isdigit() for c in s)
	if digit_count > len(s) * 0.3:
		return False
	return True


def _looks_like_key_result_value(node: MainNode) -> bool:
	if node.kind != "paragraph":
		return False
	if not (1 <= node.text_length <= KEY_RESULT_VALUE_MAX_CHARS):
		return False
	s = node.text_preview.strip()
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


def _looks_like_key_result_unit(node: MainNode) -> bool:
	if node.kind != "paragraph":
		return False
	if not (1 <= node.text_length <= KEY_RESULT_UNIT_MAX_CHARS):
		return False
	s = node.text_preview.strip().lower()
	return s in _KEY_RESULT_UNIT_WORDS
