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
	VIDEO = "video"
	LIST = "list"
	APP = "app"
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


@dataclass
class TreeSummary:
	url: str = ""

	# Landmark / structural signals
	has_main_landmark: bool = False
	article_count: int = 0          # number of <article> elements in the document
	primary_video: bool = False     # is a <video> element the main-content focus?

	# Document-order interleaved nodes inside <main>.
	main_nodes: list[MainNode] = field(default_factory=list)

	# Interactive controls inside <main>.
	form_input_count: int = 0           # editable inputs, comboboxes, etc.
	interactive_control_count: int = 0  # all interactive: buttons + inputs + links + widgets

	# Guardrail #6: did the page auto-focus an editable control before we fired?
	focused_control_is_editable: bool = False


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
HEADING_CLUSTER_MIN_SIZE = 5      # min same-level adjacent headings to call it a list
ARTICLE_DEMOTE_TO_LIST_AT = 3     # this many <article> siblings = list, not article
APP_CONTROL_FLOOR = 10            # min interactive controls to suspect app intent

# Hero-paragraph fallback (landing-page / mission-statement pattern):
# a substantial intro paragraph sitting in the lead position, even without
# a full body cluster, is enough to classify as article at lower confidence.
# Matches PARAGRAPH_MIN_CHARS — _hero_paragraph_chars already requires at
# least one substantial paragraph in the lead run, so this just confirms
# that paragraph's chars count toward the fallback (not gating on a higher
# bar than what "substantial" already means elsewhere in the classifier).
HERO_PARAGRAPH_MIN_CHARS = PARAGRAPH_MIN_CHARS

# When the page has BOTH a hero paragraph AND a borderline heading cluster
# (cards on a landing page), hero >= this many chars wins the tiebreak —
# we treat the page as article (the hero is the content) instead of list
# (the cards are nav). General rule, no per-site customization.
HERO_OVERRIDES_LIST_CHARS = 300

CONFIDENCE_THRESHOLD = 0.6        # below this, return UNKNOWN

# URL-pattern tiebreakers (lowercase substring match).
URL_HINTS = {
	Intent.FORM:    ("/signup", "/sign-up", "/register", "/contact", "/apply", "/intake"),
	Intent.ARTICLE: ("/article/", "/news/", "/blog/", "/post/", "/story/", "/posts/", "/wiki/"),
	Intent.VIDEO:   ("/watch", "/video/", "/v/", "/embed/"),
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
	form_blocked = strong_article_cluster or has_hero or has_body_cluster_strong
	if tree.form_input_count >= FORM_INPUT_THRESHOLD and not form_blocked:
		confidence = min(0.6 + 0.08 * (tree.form_input_count - FORM_INPUT_THRESHOLD), 0.9)
		if _url_matches(url, Intent.FORM):
			confidence = min(confidence + 0.15, 0.99)
		if confidence >= CONFIDENCE_THRESHOLD:
			return ClassifierResult(
				Intent.FORM, confidence,
				f"{tree.form_input_count} form inputs in main content",
			)

	# 3. Video intent.
	if tree.primary_video:
		confidence = 0.75
		if _url_matches(url, Intent.VIDEO):
			confidence = 0.95
		return ClassifierResult(
			Intent.VIDEO, confidence,
			"Primary video element in main content",
		)

	# (cluster measurements already computed above for the FORM gate.)

	# 4. List intent — checked BEFORE article because multiple <article> siblings
	#    or a strong heading cluster demote what would otherwise look like an
	#    article into a list. EXCEPT: a substantial hero paragraph blocks the
	#    heading-cluster path (landing-page-with-cards pattern: the cards look
	#    list-like, but the hero IS the content).
	is_list_by_articles = tree.article_count >= ARTICLE_DEMOTE_TO_LIST_AT
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

	# 7. Unknown.
	return ClassifierResult(
		Intent.UNKNOWN, 0.0,
		"No signal above threshold — guardrail #3 silent",
	)


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
	# at least one substantial paragraph (>= PARAGRAPH_MIN_CHARS). Returns the
	# total char count summed across the run.
	#
	# Captures landing-page / mission-statement patterns:
	# - acb.org: H1, P(400, mission), H2 ... → hero = 400+
	# - nfb.org: H1, H1, P(470, mission), H3 ... → hero = 470
	#   (stacked H1s don't break the run because headings reset cur_chars but
	#    "largest run" still captures the post-H1 paragraph block)
	# A page of short link-list items never qualifies because none of the
	# items is itself substantial.
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
			if n.text_length >= PARAGRAPH_MIN_CHARS:
				cur_has_substantial = True
	if cur_has_substantial and cur_chars > best:
		best = cur_chars
	return best


def _url_matches(url: str, intent: Intent) -> bool:
	return any(hint in url for hint in URL_HINTS.get(intent, ()))
