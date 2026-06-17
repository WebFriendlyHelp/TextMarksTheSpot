# -*- coding: UTF-8 -*-
# Article landing strategy.
#
# Per SPEC.md locked decision #7: when the classifier returns ARTICLE,
# the cursor should land on the first substantial body paragraph — past
# the headline, dek, byline, date, and (when we add chrome filtering)
# figure captions and social-share blocks.
#
# This module is pure logic on a TreeSummary. No NVDA imports. Returns an
# index into tree.main_nodes; the NVDA-binding caller maps that index back
# to a real textInfo position when walking the document the same way
# tree_summary did.

from __future__ import annotations

from typing import Optional

try:
	from ..classifier import TreeSummary
except ImportError:
	from classifier import TreeSummary


# Lower than the classifier's PARAGRAPH_MIN_CHARS=100 cluster bar on purpose.
# Landing-page intro paragraphs commonly run 50-100 chars (e.g., bestmidi.com/bg/
# at 60 chars). When the classifier promoted such a page to ARTICLE via the
# hero fallback, the landing finder needs the same lowered bar or it returns
# None and the user gets the "not found" tone with no useful target.
LANDING_MIN_PARAGRAPH_CHARS = 50

# Stricter bar for the "hero pattern" shortcut (substantial paragraph + heading
# within lookahead → land here). A 50-99 char paragraph could be UI metadata
# (e.g. Calendar's "Google Account: Casey Mathews (help@webf...)" at 56 chars,
# followed by a "Drawer" heading) — landing there is wrong. Only ≥100-char
# paragraphs can win via the hero shortcut. Shorter "candidates" fall through
# to the largest-paragraph fallback, which on app pages correctly picks the
# real content (e.g. Calendar's 181-char first appointment).
HERO_PATTERN_MIN_CHARS = 100

# A paragraph this long is unambiguously real article body — it wins the
# primary loop on its own without needing a substantial neighbor or
# heading-in-lookahead. Without this rule, a long article intro that's
# bracketed by short transitional sentences loses to later bullet-list
# clusters whose adjacent items each pass the 50-char "substantial" bar.
# malwarebytes blog post (280-char intro → short bridge → multiple ~117-char
# bullets) was the canonical case. 200 chars is roughly two long sentences:
# short enough to catch real article paragraphs, long enough that page
# chrome (cookie banners, marketing taglines) rarely qualifies.
VERY_SUBSTANTIAL_PARAGRAPH_CHARS = 200


# Heading text that signals "real article content lives directly under
# this heading." These show up across many site categories — e-commerce
# product pages (Amazon "About this item"), recipe sites ("Description"),
# software docs ("Overview"), reviews ("Features"), how-to articles
# ("What's included"). The landing finder checks for these BEFORE the
# normal article-shape heuristics — if found, the first substantial
# paragraph after the heading wins, no matter how much chrome surrounds
# the page. Match is case-insensitive substring on the heading text.
_CONTENT_SECTION_HEADING_PHRASES = (
	"about this item",
	"product description",
	"description",
	"overview",
	"features",
	"specifications",
	"what's in the box",
	"what is in the box",
	"what's included",
	"what is included",
)


_ACCESSIBILITY_INSTRUCTION_PHRASES = (
	# Standard NVDA-aware UX writing for "you're focused on this widget".
	"you are currently on",
	# Amazon's keyboard-navigation help for combo widgets.
	"to move between items",
	# Generic "press [modifier] to ..." instructional pattern.
	"press alt+",
	"press shift+",
	# Share/menu widget instructional text on government & municipal
	# sites (montgomeryprobatecourtal and many others). The widget
	# exposes "Share & Bookmark, Press Enter to show all options,
	# press Tab go to next option" as a paragraph; it's not content.
	"share & bookmark",
	"press enter to show",
	"press tab to",
	# PDF-viewer disclaimers — pages that link to PDF forms commonly
	# carry text like "Free viewers are required for some of the
	# attached documents..." or "You may need Adobe Reader to view
	# these forms." These read as substantial paragraphs (50-150
	# chars) but are page chrome, not real content. Montgomery probate
	# forms page is the canonical case.
	"free viewers are required",
	"adobe reader",
	"adobe acrobat",
	"pdf reader",
)


def _find_content_section_landing(nodes, min_chars):
	"""Look for a heading whose text matches a known "real content lives
	here" phrase (e.g. "About this item", "Description", "Overview") and
	return the index of the first substantial paragraph following it.

	Skips paragraphs caught by the tag-list and accessibility-instruction
	filters. If the matching section has no substantial paragraph before
	the next heading, moves on to the next matching section heading.

	Returns None if no content-section landing exists. Caller falls back
	to the normal article-shape heuristics.
	"""
	count = len(nodes)
	for i, node in enumerate(nodes):
		if node.kind != "heading":
			continue
		heading_text = (node.text_preview or "").strip().lower()
		if not heading_text:
			continue
		# Tight match only. Real product/recipe section headings are short
		# labels ("Description", "Features", "Overview", "Specifications",
		# "About this item"). News article headings with words like
		# "features" embedded in a longer sentence ("No additional security
		# features included") should NOT match. Cap at 25 chars: the longest
		# canonical phrase is "what is in the box" (18 chars), so 25 covers
		# all real cases with a small buffer.
		if len(heading_text) > 25:
			continue
		if not any(phrase in heading_text for phrase in _CONTENT_SECTION_HEADING_PHRASES):
			continue
		# Found a matching section. Look for the first substantial paragraph
		# before the next heading; if none qualifies, move on.
		for j in range(i + 1, count):
			n = nodes[j]
			if n.kind == "heading":
				break
			if n.kind != "paragraph" or n.text_length < min_chars:
				continue
			if _looks_like_tag_list(n.text_preview):
				continue
			if _looks_like_share_link_payload(n.text_preview):
				continue
			if _looks_like_accessibility_instructions(n.text_preview):
				continue
			return j
	return None


def _looks_like_accessibility_instructions(text: str) -> bool:
	"""Detect screen-reader instructional text appended to interactive
	widgets. Amazon product pages are the canonical case — dropdowns and
	picker controls carry text like "Shop by Room, You are currently on
	a drop-down. To open this, press alt+down arrow." It reads as prose
	(50-150 chars, real punctuation), but it's UI help, not content.

	Matched phrases are standard NVDA-aware UX writing; they don't
	appear in legitimate article body text. False positives are
	unlikely.

	This filter doesn't broadly fix Amazon's chrome-heavy landing (that's
	a Phase 3+ "product page intent" project) but eliminates one common
	false-positive class.
	"""
	if not text:
		return False
	lower = text.lower()
	return any(phrase in lower for phrase in _ACCESSIBILITY_INSTRUCTION_PHRASES)


def _looks_like_tag_list(text: str) -> bool:
	"""Detect a comma-joined list of tags/categories rather than prose.

	Tag/category rows on blogs and news sites are commonly rendered as
	a single text node like "CoPilot,Microsoft 365,Microsoft Excel" —
	8+ items joined by commas with NO space between them. Real article
	prose uses commas WITH spaces ("Word, Excel, and PowerPoint") as
	standard punctuation.

	Counting "no-space commas" against "spaced commas" is a stable
	structural signal: prose almost never has more no-space commas than
	spaced ones, while tag rows have all no-space commas.

	The office-watch.com article was landing on a 126-char tag row that
	won the hero shortcut because the article's H1 followed it. Filtering
	tag lists from landing candidates lets the real body win instead.
	"""
	if not text:
		return False
	no_space_commas = text.count(",") - text.count(", ")
	if no_space_commas < 2:
		return False
	spaced_commas = text.count(", ")
	return no_space_commas > spaced_commas


import re as _re
_URL_ENCODED_TRIPLET_RE = _re.compile(r"%[0-9A-Fa-f]{2}")


def _looks_like_share_link_payload(text: str) -> bool:
	"""Detect text that's really a URL-parameter string from a social-share
	button — typically exposed as a "paragraph" when accessibility layers
	stringify the button's href or data-url attribute.

	Two signals, either is enough on its own:

	  1. Contains "url=http" or "url=https" — the canonical LinkedIn
	     "share-offsite?url=https%3A%2F%2F..." pattern, and the same
	     shape Twitter/X, Pinterest, and Facebook share endpoints use.
	  2. Three or more URL-encoded triplets (%XX) in the text. Real
	     article prose almost never has more than one or two; a tight
	     cluster of them is overwhelmingly a URL string.

	On a LinkedIn-share-link-heavy news article (Fox21, many others),
	these strings would otherwise win the "first substantial paragraph"
	rule because they're long enough to clear the size threshold.
	"""
	if not text:
		return False
	lower = text.lower()
	if "url=http" in lower:
		return True
	return len(_URL_ENCODED_TRIPLET_RE.findall(text)) >= 3


# Label nodes that mark a Jetpack "Daily writing prompt" widget. WordPress.com
# injects this block at the top of any post written from a daily prompt, and it
# renders as three consecutive nodes: this label, the prompt question, then a
# "View all responses" link. The question frames the whole post and is the best
# orientation line on these pages — but it's commonly a lone 50-99 char
# paragraph that loses both the cluster gate (its neighbor is the short "View
# all responses" link) and the hero gate (under HERO_PATTERN_MIN_CHARS). Match
# is on the widget's label text, so this fires across every blog that uses the
# feature — it is a cross-site shape rule, not a per-site special case.
_BLOGGING_PROMPT_LABELS = (
	"daily writing prompt",
)


def _find_blogging_prompt_landing(nodes):
	"""If a Jetpack daily-writing-prompt widget is present, return the index
	of the prompt question (the node immediately after the label). Returns
	None when no such widget is found, so the caller falls through to the
	normal article-shape heuristics.
	"""
	count = len(nodes)
	for i, node in enumerate(nodes):
		text = (node.text_preview or "").strip().lower()
		if not text:
			continue
		if not any(text == lbl or text.startswith(lbl) for lbl in _BLOGGING_PROMPT_LABELS):
			continue
		if i + 1 < count:
			nxt = nodes[i + 1]
			# The question should be the next text node, not another label or
			# a stray short fragment. 15 chars clears "View all responses"-style
			# link text while admitting any real question.
			if nxt.kind == "paragraph" and nxt.text_length >= 15:
				return i + 1
	return None


def _first_substantial_paragraph(nodes, min_chars) -> Optional[int]:
	"""Return the index of the first paragraph >= min_chars, skipping the same
	chrome shapes the main cascade skips (tag lists, share-link payloads,
	accessibility instructions). Returns None if none qualifies.

	Used only when the tree is positionally scoped to a single <article>: the
	nav/comments/footer have already been excluded by position, so the first
	real paragraph is the genuine opening line and we don't need the defensive
	hero/cluster gates that guard noisy unscoped trees.
	"""
	for i, node in enumerate(nodes):
		if node.kind != "paragraph" or node.text_length < min_chars:
			continue
		text = node.text_preview or ""
		if _looks_like_tag_list(text):
			continue
		if _looks_like_share_link_payload(text):
			continue
		if _looks_like_accessibility_instructions(text):
			continue
		return i
	return None


def find_article_landing(tree: TreeSummary) -> Optional[int]:
	"""Pick the best landing index in tree.main_nodes for an ARTICLE-classified
	page. The browse cursor will be moved to that paragraph and NVDA will
	speak it; we want to land on real BODY content, not on chrome (sidebar
	links, recent-post widgets, byline boilerplate) that happens to be
	substantial-length.

	Strategy: walk main_nodes in document order. A substantial paragraph
	(>= LANDING_MIN_PARAGRAPH_CHARS) qualifies as a landing target only
	when it has one of these neighboring shapes:

	  A. Followed by another substantial paragraph (cluster start — typical
	     article body or sustained content).
	  B. Followed by a heading (hero / section-intro — a single hero
	     paragraph before the next section heading, common on landing
	     pages like ACB, NFB, Glidance, SSA, l-works).

	Pick the FIRST qualifying paragraph. This skips isolated substantial-
	length items that sit between short link-text entries (e.g., a recent-
	post widget link that happens to be exactly 100 chars between two
	shorter neighbors).

	Fallback (no neighbor-qualifying paragraph found): pick the LARGEST
	substantial paragraph anywhere. Handles terse pages with one big
	paragraph and otherwise scattered short text.

	Returns None if nothing in main_nodes qualifies at all.
	"""
	nodes = tree.main_nodes
	count = len(nodes)
	min_chars = LANDING_MIN_PARAGRAPH_CHARS

	# First: the Jetpack daily-writing-prompt widget, if present. The prompt
	# question is the best orientation line on these posts but reliably loses
	# the cluster/hero gates below, so match the widget shape and land on it.
	idx = _find_blogging_prompt_landing(nodes)
	if idx is not None:
		return idx

	# When the walk was positionally scoped to a single <article>, the tree is
	# already chrome-free, so the first substantial paragraph is the real
	# opening line. The hero/cluster gates below exist to skip pre-content
	# chrome in noisy unscoped trees; on a clean tree they overshoot the genuine
	# first paragraph (e.g. a 64-char prompt question followed by a short intro
	# line, which the gates skip in favor of a later list cluster).
	if getattr(tree, "positionally_scoped", False):
		idx = _first_substantial_paragraph(nodes, min_chars)
		if idx is not None:
			return idx

	# Next: look for a heading whose text matches a known content-section
	# label ("About this item", "Description", "Overview", "Features",
	# etc.) and land on the first substantial paragraph after it. This is
	# the strongest signal we have on heavily-chromed pages (Amazon
	# product pages, recipe sites, software docs) where article-shape
	# heuristics struggle to distinguish content from chrome.
	idx = _find_content_section_landing(nodes, min_chars)
	if idx is not None:
		return idx

	# How far to look ahead for a section-ending heading when checking
	# the hero/section-intro pattern. Some landing pages have a substantial
	# hero paragraph followed by 1-3 short banner/CTA lines before the
	# next H2/H3 — e.g., acb.org has hero + 2 conference-banner lines
	# before "Top Links" H2. Capped to prevent confusing distant content
	# with a hero pattern.
	hero_lookahead = 4

	seen_heading = False
	for i, node in enumerate(nodes):
		if node.kind == "heading":
			seen_heading = True
		if node.kind != "paragraph" or node.text_length < min_chars:
			continue
		# Tag/category rows render as a single substantial paragraph but
		# aren't prose. Skip them so they don't win via the hero shortcut
		# just because an article heading happens to follow.
		if _looks_like_tag_list(node.text_preview):
			continue
		# URL-parameter payloads from social-share buttons exposed as text.
		if _looks_like_share_link_payload(node.text_preview):
			continue
		# Screen-reader instructional text appended to interactive widgets
		# (Amazon dropdowns). UI help, not article content.
		if _looks_like_accessibility_instructions(node.text_preview):
			continue
		# Very substantial paragraphs (>= 200 chars) are unambiguously
		# article body — accept immediately. Without this rule, a long
		# article intro can lose to later bullet-list clusters whose
		# adjacent items both pass the 50-char "substantial" bar.
		if node.text_length >= VERY_SUBSTANTIAL_PARAGRAPH_CHARS:
			return i
		if i + 1 >= count:
			# Last node — can't check neighbors for hero/cluster pattern.
			# Do NOT accept it just because it's last: on pages where the
			# scoped walk failed and main_nodes contains nav + footer, the
			# last substantial paragraph is often the footer disclaimer
			# (bestmidi.com/bg/: "This website is not affiliated with
			# Blizzard Entertainment." was winning over the actual intro).
			# Defer to the largest-paragraph fallback below — it handles
			# legitimate single-paragraph pages just as well.
			continue
		nxt = nodes[i + 1]
		# A: cluster start — immediately adjacent substantial paragraph.
		if nxt.kind == "paragraph" and nxt.text_length >= min_chars:
			# Teaser-skip: when the candidate is short (<100 chars) and the
			# next paragraph is substantially longer (>2x AND >=150 chars),
			# prefer the next. CNET news articles commonly carry an 80-char
			# TLDR-style teaser between the H1 and the actual narrative
			# opening — "X can be a huge time saver, once you commit them
			# to memory." (82 chars) followed by "When I first started
			# using an iMac all the way back in 2008..." (209 chars). The
			# narrative paragraph is where a reader actually wants to be.
			if (
				node.text_length < 100
				and nxt.text_length >= 150
				and nxt.text_length > node.text_length * 2
			):
				return i + 1
			return i
		# B: hero / section-intro — a heading appears within hero_lookahead
		# nodes BEFORE any other substantial paragraph. The hero shortcut
		# uses a STRICTER threshold (HERO_PATTERN_MIN_CHARS=100) than the
		# 50-char "candidate" bar above: a 50-99 char paragraph followed
		# by a heading is just as likely to be UI metadata (account label,
		# breadcrumb, widget title) as a real hero — landing there is
		# wrong on app pages like calendar.google.com. Shorter candidates
		# fall through to the largest-paragraph fallback below, which on
		# app pages correctly picks the real content.
		if node.text_length < HERO_PATTERN_MIN_CHARS:
			continue
		# The hero shortcut also requires that we've ALREADY seen a heading
		# in main_nodes. Without this, a substantial publisher disclaimer
		# / dek / byline paragraph BEFORE the article's H1 wins because
		# the H1 itself is in the hero lookahead window. PCMag's "editors
		# select and review products..." disclaimer (167 chars) was the
		# canonical case. Article body comes AFTER the H1; pre-H1
		# substantial paragraphs are almost always chrome.
		if not seen_heading:
			continue
		hero_qualifies = False
		end = min(i + 1 + hero_lookahead, count)
		for j in range(i + 1, end):
			peek = nodes[j]
			if peek.kind == "heading":
				hero_qualifies = True
				break
			if peek.kind == "paragraph" and peek.text_length >= min_chars:
				# A later substantial paragraph means a cluster is coming;
				# THIS paragraph isn't the hero.
				break
		if hero_qualifies:
			return i

	# Fallback: largest substantial paragraph anywhere.
	# Note: when the page hasn't finished hydrating, this fallback may
	# pick chrome text (e.g., "Google Account: ..." on Calendar's first
	# moment of load). That's expected at this layer — the caller's retry
	# mechanism handles the "page not ready" case generically by re-running
	# detection 1500 ms later, by which time the real content is in the
	# virtual buffer. We do NOT add a thin-walk gate here because it would
	# be a site-symptom band-aid; the retry is the principled fix.
	#
	# Also track substantial-paragraph count and the first-heading index so
	# we can detect a "directory page" pattern below — small pages where
	# the only substantial paragraph is a footer (address / copyright) and
	# the right landing is the page title heading near the top.
	best_idx = None
	best_len = 0
	substantial_count = 0
	first_heading_idx = None
	for i, node in enumerate(nodes):
		if node.kind == "heading" and first_heading_idx is None:
			first_heading_idx = i
		if node.kind == "paragraph" and node.text_length >= min_chars:
			# Skip tag/category rows the same way the primary loop does.
			if _looks_like_tag_list(node.text_preview):
				continue
			# Skip URL-parameter payloads from social-share buttons.
			if _looks_like_share_link_payload(node.text_preview):
				continue
			# Skip screen-reader instructional text the same way.
			if _looks_like_accessibility_instructions(node.text_preview):
				continue
			substantial_count += 1
			if node.text_length > best_len:
				best_len = node.text_length
				best_idx = i

	# Directory-page redirect: a small page (≤30 nodes) with exactly one
	# substantial paragraph far past an earlier heading is almost always
	# a navigation/listing page where the "substantial" paragraph is the
	# footer (courthouse address, business hours, copyright). The user
	# wants to land at the title heading, not the footer.
	# montgomeryprobatecourtal.gov/resources/all-probate-forms is the
	# canonical case: H "All Probate Forms" at idx 7, courthouse address
	# paragraph at idx 21, no other substantial text. Land at idx 7.
	if (
		best_idx is not None
		and substantial_count == 1
		and first_heading_idx is not None
		and first_heading_idx < best_idx
		and (best_idx - first_heading_idx) >= 5
		and len(nodes) <= 30
	):
		return first_heading_idx
	return best_idx


# Mirrored from classifier.py — controls when adjacent same-level headings
# count as a single cluster. Must match the classifier's value so we land
# at the same cluster the classifier identified.
_HEADING_CLUSTER_MAX_CHARS_BETWEEN = 300


def find_form_landing(tree: TreeSummary) -> Optional[int]:
	"""For FORM intent: land on the form's title (first heading) so the
	user hears "Form X" / "Survey Y" first, then can arrow forward to
	read the description and reach the input fields.

	On full-page forms (Google Forms, signup pages, intake forms) this
	is the right entry point — the user wants context before answering.
	On pages that auto-focused an input, SILENT_FOCUS_HONORED already
	caught them upstream and we don't reach here.

	Priority:
	  1. First heading — typically the form's title or section label.
	  2. First substantive paragraph (>= 30 chars) — fallback for forms
	     with no heading but a description above the fields.
	  3. First node — last resort.
	"""
	nodes = tree.main_nodes
	if not nodes:
		return None
	for i, n in enumerate(nodes):
		if n.kind == "heading":
			return i
	for i, n in enumerate(nodes):
		if n.kind == "paragraph" and n.text_length >= 30:
			return i
	return 0


def find_key_result_landing(tree: TreeSummary) -> Optional[int]:
	"""For KEY_RESULT intent: land on the LABEL paragraph so the user can
	hear the label first, then arrow forward to hear the value and unit.

	The classifier already validated the pattern exists; we just need to
	re-locate the label index. We delegate to the classifier's public
	pattern finder to keep matching logic in one place.
	"""
	try:
		from ..classifier import find_key_result_pattern_index
	except ImportError:
		from classifier import find_key_result_pattern_index
	return find_key_result_pattern_index(tree.main_nodes)


_NOTICE_LANDING_MIN_CHARS = 30


def find_notice_landing(tree: TreeSummary) -> Optional[int]:
	"""For NOTICE intent: return the index of the status sentence — the
	one the user came here to read (e.g. "The form is no longer accepting
	responses", "Thank you for submitting", "Page not found").

	Strategy:
	  1. First paragraph >= _NOTICE_LANDING_MIN_CHARS in DOCUMENT ORDER.
	     This is the simplest and most reliable heuristic on small pages:
	     the meaningful sentence is usually one of the first substantial
	     text nodes, regardless of whether it sits before or after the
	     first heading. The previous "first paragraph after the first
	     heading" rule failed on pages where the intro sentence precedes
	     any heading (bestmidi.com/bg/ — log showed it landing on a
	     footer text node at idx 18 because the only heading detected
	     was a region H2 deep in the page).
	  2. First heading — at least announces what page this is.
	  3. First node — last resort.

	Returns None only if tree.main_nodes is empty.
	"""
	nodes = tree.main_nodes
	if not nodes:
		return None

	# 1. First substantial paragraph anywhere in document order.
	for i, n in enumerate(nodes):
		if n.kind == "paragraph" and n.text_length >= _NOTICE_LANDING_MIN_CHARS:
			return i

	# 2. First heading.
	for i, n in enumerate(nodes):
		if n.kind == "heading":
			return i

	# 3. First node.
	return 0


def find_list_landing(tree: TreeSummary) -> Optional[int]:
	"""For LIST intent: return the index of the first heading in the
	largest same-level heading cluster. That's typically the first story
	headline / search result / video title — the same target a sighted
	person would scan to first on an index page. Moving the cursor there
	makes the page feel "ready to scan" instead of silent.

	Returns None if no heading cluster is identifiable in main_nodes.
	"""
	best_start = None
	best_size = 0
	cur_start = None
	cur_size = 0
	cur_level: Optional[int] = None
	chars_since = 0

	for i, node in enumerate(tree.main_nodes):
		if node.kind == "heading":
			if cur_level == node.level and chars_since <= _HEADING_CLUSTER_MAX_CHARS_BETWEEN:
				cur_size += 1
			else:
				cur_start = i
				cur_size = 1
				cur_level = node.level
			chars_since = 0
			if cur_size > best_size:
				best_size = cur_size
				best_start = cur_start
		elif node.kind == "paragraph":
			chars_since += node.text_length

	return best_start


_Z_SEQUENCE_MAX_GAP = 30
"""Maximum number of main_nodes between the last Z-sequence landing and the
next eligible heading. Beyond this we treat the next heading as out of the
article body — typically a sidebar widget heading or a related-content rail.
30 covers even long news article subsections; a longer gap is a strong signal
that the cursor has walked off the article and into chrome."""


def find_next_content_landing(
	tree: TreeSummary,
	after_idx: int,
) -> Optional[int]:
	"""Z-key forward scan: return the index of the next substantial
	content paragraph in main_nodes strictly after `after_idx`. Skips
	headings (NVDA's H key handles those) and the same chrome paragraphs
	the article-landing cascade skips (tag lists, share-link payloads,
	accessibility instructions, PDF-viewer disclaimers).

	Returns None if no eligible paragraph exists past `after_idx`. The
	caller speaks a "nothing else to land on" message and leaves the
	cursor where it is.

	This is the Z key's "find me the next interesting thing to read"
	behavior, scanning from wherever the user currently is. It deliberately
	does NOT track or use the previous addon-landing index — Z is meant
	to advance from the user's CURRENT position, not from the last place
	the addon dropped them.
	"""
	for i in range(after_idx + 1, len(tree.main_nodes)):
		node = tree.main_nodes[i]
		if node.kind != "paragraph":
			continue
		if node.text_length < LANDING_MIN_PARAGRAPH_CHARS:
			continue
		text = node.text_preview or ""
		if _looks_like_tag_list(text):
			continue
		if _looks_like_share_link_payload(text):
			continue
		if _looks_like_accessibility_instructions(text):
			continue
		return i
	return None


def find_next_heading_landing(
	tree: TreeSummary,
	after_idx: int,
	max_gap: int = _Z_SEQUENCE_MAX_GAP,
) -> Optional[int]:
	"""Phase 1.5 Z-sequence: return the index of the next heading in
	main_nodes strictly after `after_idx`, provided it sits within
	`max_gap` nodes. Returns None if there is no further heading OR if
	the next heading is too far away to plausibly belong to the same
	article body (sidebar / related-content territory).

	Used by the multi-press Z behavior: first Z press lands at the page's
	primary landing, subsequent presses advance to the next section
	(next heading) so the user can walk through major sections without
	leaving the add-on's gesture.
	"""
	max_idx = min(after_idx + 1 + max_gap, len(tree.main_nodes))
	for i in range(after_idx + 1, max_idx):
		if tree.main_nodes[i].kind == "heading":
			return i
	return None
