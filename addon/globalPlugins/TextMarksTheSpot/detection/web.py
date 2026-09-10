# -*- coding: UTF-8 -*-
# Article landing strategy.
#
# Per SPEC.md locked decision #7: when the classifier returns ARTICLE,
# the cursor should land on the first substantial body paragraph — past
# the headline, dek, byline, date, and (when we add chrome filtering)
# figure captions and social-share blocks.
#
# This module is pure logic on a TreeSummary. No NVDA imports. Returns an
# index into tree.mainNodes; the NVDA-binding caller maps that index back
# to a real textInfo position when walking the document the same way
# treeSummary did.

from __future__ import annotations

import dataclasses as _dataclasses
import re as _re
from typing import Optional

try:
	from ..classifier import TreeSummary
except ImportError:
	from classifier import TreeSummary


# Directory-page redirect cap: the "land on the title heading instead of a
# lone far-away paragraph" rule only applies to pages up to this many
# mainNodes. Big content pages must never redirect. 30 covered the
# Montgomery probate forms page; 40 also covers the signed-in Zoom webinar
# registration shell (36 nodes, content hidden in closed accordions).
_DIRECTORY_REDIRECT_MAX_NODES = 40

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

# How far below the page's H1 the lede may sit before _findTitleLedeLanding
# stops looking. On MacRumors it is two nodes down (the byline sits between).
# Sized for "title, maybe a byline, maybe a timestamp, then the lede" and no
# further -- past that we would be guessing at which paragraph is the opening.
_TITLE_LEDE_LOOKAHEAD = 4

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


# DEFINITIONAL LEDE. "<Subject> is a/an/the ..." is how product pages, docs and
# reference entries state what the page is ABOUT. It is a general prose pattern,
# not a site convention, and we already know the subject: the page's first
# heading.
#
# Why it is needed. The cluster gate awards the landing to the FIRST of two
# adjacent substantial paragraphs, which on a product page is routinely a
# prerequisite note or a feature line sitting above the description. Vovsoft AI
# Requester: "This program requires your own OpenAI API key..." (74) and "Local
# models can run directly on your computer..." (103) form a cluster and win,
# while "Vovsoft AI Requester is a program that can connect to OpenAI API..."
# (102) sits two nodes below and is what the user actually wants.
#
# Why it is a REFINEMENT and not another gate. This cascade's documented
# structural fault is that it awards on rule ORDER rather than evidence
# strength, so every new early gate can preempt a good landing somewhere else.
# This one can only move a landing FORWARD by a few nodes inside the block the
# cluster gate already chose. It cannot reach past a heading, and it cannot
# override a landing chosen anywhere else in the cascade.
_DEFINITIONAL_LOOKAHEAD = 4
# How far into the paragraph the subject may appear. Covers a vendor prefix
# ("Vovsoft AI Requester" for an H1 of "AI Requester") without matching a
# passing mention deep in a body paragraph.
_DEFINITIONAL_SUBJECT_WINDOW = 40
# How far after the subject the copula may sit, enough for "AI Requester 5.2 is
# a ..." but not enough to pair a subject with an unrelated later clause.
_DEFINITIONAL_COPULA_WINDOW = 15
_DEFINITIONAL_COPULAS = (" is a", " is an", " is the")
# Below this a "subject" is too generic to match on ("FAQ", "Home").
_DEFINITIONAL_MIN_SUBJECT_CHARS = 4


def _pageSubject(nodes) -> str:
	"""The page's first heading — what the page is about."""
	for node in nodes:
		if node.kind == "heading":
			return (node.textPreview or "").strip()
	return ""


def _looksLikeDefinitionalLede(text: str, subject: str) -> bool:
	"""True when this paragraph names the page's subject and says what it IS."""
	if not subject or len(subject) < _DEFINITIONAL_MIN_SUBJECT_CHARS:
		return False
	lower = (text or "").strip().lower()
	subj = subject.lower()
	pos = lower.find(subj)
	if pos < 0 or pos > _DEFINITIONAL_SUBJECT_WINDOW:
		return False
	tail = lower[pos + len(subj):pos + len(subj) + _DEFINITIONAL_COPULA_WINDOW]
	return any(copula in tail for copula in _DEFINITIONAL_COPULAS)


def _findDefinitionalLede(nodes, start, minChars, subject) -> Optional[int]:
	"""A definitional lede within _DEFINITIONAL_LOOKAHEAD nodes after `start`,
	stopping at the next heading. Returns None when there is none, which is the
	common case and leaves the caller's own choice untouched.
	"""
	end = min(start + 1 + _DEFINITIONAL_LOOKAHEAD, len(nodes))
	for j in range(start + 1, end):
		node = nodes[j]
		if node.kind == "heading":
			break
		if node.kind != "paragraph" or node.textLength < minChars:
			continue
		if _isChromeParagraph(node):
			continue
		if _looksLikeDefinitionalLede(node.textPreview, subject):
			return j
	return None


# How far past a content-section heading its paragraph may sit. Matches the
# hero gate's lookahead (web.py, heroLookahead = 4) for the same reason: a
# heading vouches for the text it INTRODUCES, not for everything downstream of
# it.
#
# Without a bound this gate ran to the next heading, and on a page whose
# matching heading is the LAST one it ran to the end of the document. Vovsoft
# product pages: "Key Features" at node 34, its spec lines at 35-37 discarded by
# the sentence-strict pass, no further heading anywhere — so the gate claimed a
# 387-char purchase blurb at node 49 and the add-on spoke licensing terms
# instead of the product description sitting at node 7. Confirmed from the live
# decision trace, and confirmed NOT to be walk truncation: sibling pages
# mislanded identically with truncated=False and with descriptions well over the
# 200-char very-substantial bar, which this gate outranks by running earlier.
_CONTENT_SECTION_MAX_DISTANCE = 4


def _findContentSectionLanding(nodes, minChars):
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
		headingText = (node.textPreview or "").strip().lower()
		if not headingText:
			continue
		# Tight match only. Real product/recipe section headings are short
		# labels ("Description", "Features", "Overview", "Specifications",
		# "About this item"). News article headings with words like
		# "features" embedded in a longer sentence ("No additional security
		# features included") should NOT match. Cap at 25 chars: the longest
		# canonical phrase is "what is in the box" (18 chars), so 25 covers
		# all real cases with a small buffer.
		if len(headingText) > 25:
			continue
		if not any(phrase in headingText for phrase in _CONTENT_SECTION_HEADING_PHRASES):
			continue
		# Found a matching section. Look for the first substantial paragraph
		# before the next heading AND within _CONTENT_SECTION_MAX_DISTANCE;
		# if none qualifies, move on to the next matching section heading.
		limit = min(i + 1 + _CONTENT_SECTION_MAX_DISTANCE, count)
		for j in range(i + 1, limit):
			n = nodes[j]
			if n.kind == "heading":
				break
			if n.kind != "paragraph" or n.textLength < minChars:
				continue
			if _isChromeParagraph(n):
				continue
			return j
	return None


def _findLeadSectionLanding(nodes) -> Optional[int]:
	"""Land on a lone substantial paragraph in the page's LEAD SECTION.

	The section is the span between the FIRST heading and the NEXT heading. If it
	holds exactly ONE non-chrome, sentence-ending paragraph of at least
	HERO_PATTERN_MIN_CHARS, and that paragraph has no substantial neighbour, then
	it is the page's lead and we land on it.

	Why this exists (IMDb, 2026-07-14 soak). The plot summary is a 166-char
	standalone paragraph. It fails every existing gate:
	  - VERY_SUBSTANTIAL (200) -- it is 166.
	  - cluster -- IMDb follows it with SHORT director/cast lines, so it has no
	    adjacent substantial paragraph.
	  - hero -- needs a heading within the 4-node lookahead, but IMDb's next
	    heading ("Videos") is 31 nodes away.
	So the cascade walked past it and landed on one of four adjacent "Clip..."
	video titles, which DO form a cluster.

	Two things people get wrong about this bug, both checked against the real
	node trail rather than assumed:
	  - The clip titles END IN QUESTION MARKS ("...Jared, Heath, or Jack?"), so
	    endsLikeSentence is genuinely True for them. The sentence-strict pass is
	    right to keep them; it is not the culprit.
	  - A heading WAS seen before the plot summary (the H1). The hero gate fails
	    on lookahead DISTANCE, not on heading absence.
	And suppressing the clip rail alone would not fix it: the cascade would run on
	and land on a 200+ char user review further down. The synopsis needs POSITIVE
	evidence, which is what this gate supplies.

	"Exactly one" is the load-bearing part, and it is what keeps this gate off
	normal articles: a news page's lead section holds MANY substantial paragraphs
	(the lede, then the next, then the next), so the count is never 1 and the gate
	declines. It also keeps us off deks, which sit alongside a real lede.

	Not a threshold change -- a new structural signal. Returns None to mean "not
	my case; run the normal cascade."
	"""
	firstHeading = next(
		(i for i, n in enumerate(nodes) if n.kind == "heading"), None
	)
	if firstHeading is None:
		return None
	nextHeading = next(
		(j for j in range(firstHeading + 1, len(nodes)) if nodes[j].kind == "heading"),
		len(nodes),
	)
	candidates = [
		j
		for j in range(firstHeading + 1, nextHeading)
		if nodes[j].kind == "paragraph"
		and nodes[j].textLength >= HERO_PATTERN_MIN_CHARS
		and not _isChromeParagraph(nodes[j])
		and _nodeEndsSentence(nodes[j])
	]
	if len(candidates) != 1:
		return None
	idx = candidates[0]
	# It must be STANDALONE. A substantial neighbour means this is the start of a
	# body run, which the cluster gate already handles correctly.
	for k in (idx - 1, idx + 1):
		if (
			0 <= k < len(nodes)
			and nodes[k].kind == "paragraph"
			and nodes[k].textLength >= LANDING_MIN_PARAGRAPH_CHARS
		):
			return None
	return idx


# Author-meta lines that a magazine/blog layout places BETWEEN a standfirst /
# dek and the article body: a read-time ("6 min read") or a standalone date
# ("6/3/2026", "June 3, 2026"). Their presence just after a title-lede
# candidate proves the candidate sits ABOVE the meta block and is therefore the
# dek, not the lede.
_READING_TIME_RE = _re.compile(r"\b\d+\s*min(?:ute)?s?\s+read\b", _re.IGNORECASE)
_NUMERIC_DATE_LINE_RE = _re.compile(r"^\s*\d{1,2}/\d{1,2}/\d{2,4}\s*$")


def _looksLikeArticleMeta(node) -> bool:
	"""True when a node is an author-meta line (read-time or a standalone date).

	These mark the byline/meta block that a magazine or blog layout sits
	between the dek and the body. Deliberately narrow: a read-time phrase, a
	whole-line numeric date, or a short line that is just a "Month DD, YYYY"
	date. Ordinary body prose does not match any of these, so a false positive
	(which only makes the title-lede gate decline in favour of the body
	cascade) is very unlikely.
	"""
	text = (node.textPreview or "").strip()
	if not text:
		return False
	if _READING_TIME_RE.search(text):
		return True
	if _NUMERIC_DATE_LINE_RE.match(text):
		return True
	if getattr(node, "textLength", len(text)) <= 40 and _BYLINE_FULLDATE_RE.search(text):
		return True
	return False


def _findTitleLedeLanding(nodes) -> Optional[int]:
	"""Land on the article's opening sentence when an embedded widget cuts it
	off from the body.

	MacRumors "Apple Just Increased Prices" (2026-07-20). The shape:

	    idx 0  H1        "Apple Just Increased Prices on MacBooks, ..."
	    idx 1  paragraph "Thursday June 25, 2026 5:44 am PDT by Hartley ..."
	    idx 2  paragraph "Apple today dramatically increased device prices ..."  (79)
	    idx 3-8          YouTube embed chrome: player name, video title, channel,
	                     subscriber count, "Watch later", "Share"
	    idx 9  paragraph "Subscribe to the MacRumors YouTube channel ..."  (59)
	    idx 10 paragraph "After temporarily taking it down earlier today ..." (149)

	idx 2 is the lede and it loses every gate on LENGTH alone: 79 chars is under
	VERY_SUBSTANTIAL (200) and under HERO_PATTERN_MIN_CHARS (100), and the video
	embed means its neighbour is a 20-char player label rather than a substantial
	paragraph, so the cluster gate declines. The cascade walked on to idx 9, which
	clusters with idx 10 and wins -- the user was dropped into the embed's own
	subscribe pitch. This is the structural fault named in CLAUDE.md: the cascade
	awards the landing on rule ORDER rather than evidence strength.

	The positive evidence this gate uses is POSITION plus GRAMMAR: sentence-ending
	prose sitting directly under the page's own H1 is the lede. Nothing else on a
	news page occupies that slot.

	Three guards keep it narrow, and each one is load-bearing:

	  1. Level-1 heading only. A nav or widget heading is an H2/H3; requiring the
	     H1 means "the page's title", which is what makes the slot meaningful. On
	     an unscoped tree whose first heading is site chrome, the gate declines
	     rather than landing on a cookie banner underneath it.
	  2. It only fires where the cascade currently walks PAST the candidate --
	     the next node must not be a substantial paragraph. When it is, the
	     cluster gate already handles the page correctly, teaser-skip included,
	     so this gate must not preempt it. That is what keeps it off the CNET
	     teaser shape (82-char teaser, 209-char narrative right after) and off
	     ordinary Wikipedia-style ledes.
	  3. A short lookahead from the H1. The lede sits under the title, possibly
	     past a byline or timestamp; it is not eight nodes down. Beyond the
	     window we are guessing, and a wrong auto-jump is worse than no jump.

	Returns None to mean "not my case; run the normal cascade."
	"""
	title = next(
		(i for i, n in enumerate(nodes) if n.kind == "heading" and n.level == 1),
		None,
	)
	if title is None:
		return None
	for i in range(title + 1, min(title + 1 + _TITLE_LEDE_LOOKAHEAD, len(nodes))):
		node = nodes[i]
		if node.kind == "heading":
			# A second heading closes the title's own section before any lede
			# appeared. Whatever follows belongs to that section, not here.
			return None
		if node.kind != "paragraph":
			continue
		if node.textLength < LANDING_MIN_PARAGRAPH_CHARS:
			continue
		if _isChromeParagraph(node) or not _nodeEndsSentence(node):
			# Bylines, timestamps and dateline fragments live in this slot too.
			# They are not disqualifying -- keep scanning past them.
			continue
		nxt = nodes[i + 1] if i + 1 < len(nodes) else None
		if (
			nxt is not None
			and nxt.kind == "paragraph"
			and nxt.textLength >= LANDING_MIN_PARAGRAPH_CHARS
		):
			# Guard 2: the ordinary cluster gate owns this shape.
			return None
		# Guard 4: a standfirst / dek sits ABOVE the author-meta block (byline,
		# date, read-time); the real body begins AFTER it. When a read-time or
		# date meta line follows this candidate before any substantial
		# paragraph, the candidate is the dek, not the lede -- decline so the
		# body cascade lands on the opening paragraph below the meta. Locked
		# decision #7: skip the dek. iinteractive.com blog posts are the
		# canonical case (headline, dek, "Sharni Zaugg", "6/3/2026", "6 min
		# read", then the 395-char body). MacRumors is unaffected: its lede is
		# followed by video-embed chrome, not a date/read-time meta line.
		window = min(i + 1 + _TITLE_LEDE_LOOKAHEAD, len(nodes))
		for k in range(i + 1, window):
			peek = nodes[k]
			if (
				peek.kind == "paragraph"
				and peek.textLength >= LANDING_MIN_PARAGRAPH_CHARS
				and not _isChromeParagraph(peek)
			):
				break  # body reached before any meta line -- candidate is the lede
			if _looksLikeArticleMeta(peek):
				return None
		return i
	return None


def _looksLikeAccessibilityInstructions(text: str) -> bool:
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


def _looksLikeTagList(text: str) -> bool:
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
	noSpaceCommas = text.count(",") - text.count(", ")
	if noSpaceCommas < 2:
		return False
	spacedCommas = text.count(", ")
	return noSpaceCommas > spacedCommas


_URL_ENCODED_TRIPLET_RE = _re.compile(r"%[0-9A-Fa-f]{2}")


def _looksLikeShareLinkPayload(text: str) -> bool:
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


# Breadcrumb navigation trail. Sites render the "you are here" path as a single
# text node — "Home > WebAIM Projects > Screen Reader User Survey" — which NVDA
# exposes as a paragraph that clears the substantial-text bar. It is pure
# navigation and must never be a landing target: WebAIM's survey-confirmation
# ("Thank you for completing...") page landed the user ON this breadcrumb
# because it was the first 30+ char paragraph in document order (2026-07-20).
# Two independent signals, either is enough:
#   1. A "You are here" navigation preamble.
#   2. A chain of >= 3 segments joined by breadcrumb separators (" > ", " > ",
#      " » "). Requiring TWO separators (three segments) keeps ordinary prose
#      that contains a single " > " (a quoted comparison, a math aside) safe;
#      natural prose essentially never strings two spaced chevrons together.
# The " / " separator is deliberately excluded — spaced slashes appear in prose
# ("and / or", "he said / she said") far more often than the chevrons do.
_BREADCRUMB_SEP_RE = _re.compile(r"\s[>›»]\s")


def _looksLikeUrlSlug(text: str) -> bool:
	"""A URL slug exposed as a text node: hyphen-joined words with NO spaces,
	e.g. "when-your-vehicle-outlives-its-cloud" (Ars Technica lists each story's
	slug as a line above its headline). Read aloud it is "when hyphen your
	hyphen ..." — never a landing. Tight: real prose always has spaces, and a
	lone compound like "state-of-the-art" rarely stands as its own paragraph.
	"""
	stripped = (text or "").strip()
	if not stripped or " " in stripped:
		return False
	return stripped.count("-") >= 2


def _looksLikeBreadcrumb(text: str) -> bool:
	if not text:
		return False
	stripped = text.strip()
	if stripped.lower().startswith("you are here"):
		return True
	return len(_BREADCRUMB_SEP_RE.findall(stripped)) >= 2


# Photo/image-credit signature. News and blog articles place a figure caption
# right next to the hero image, directly above the opening line. NVDA exposes
# that caption as a paragraph that commonly clears the 50-char "substantial"
# bar and sits immediately before the real lede — so it wins the cluster gate
# and the cursor lands on the caption instead of the article. The defining
# signal is a photo-credit attribution: a stock-agency / wire-service name or
# "Photo:/Image:/Courtesy" phrasing, almost always as a TRAILING parenthetical.
# Real article prose effectively never ends this way. fox21news.com
# ("...in downtown Denver (Getty Images)" — 103 chars — beating the 85-char
# "DENVER (KDVR) — ..." lede) is the canonical case. The end-anchor is what
# keeps the dateline's own leading "(KDVR)" parenthetical from matching.
_PHOTO_CREDIT_END_RE = _re.compile(
	r"\(\s*(?:photo|image|getty|ap|reuters|afp|epa|bloomberg|"
	r"istock(?:photo)?|shutterstock|adobe\s+stock|unsplash|pexels|pixabay|"
	r"dreamstime|depositphotos|wikimedia|file\s+photo|courtesy)\b[^)]*\)\s*\.?\s*$",
	_re.IGNORECASE,
)
# Agency / credit tokens that essentially never occur in legitimate article
# body prose, regardless of position. Caught even without the trailing-paren
# shape (e.g. "Photo credit: Jane Doe", "Image courtesy of the city").
_PHOTO_CREDIT_PHRASES = (
	"getty images",
	"associated press",
	"photo credit",
	"image credit",
	"photo courtesy",
	"image courtesy",
	"via getty",
)


# Digits either side of a slash: a date ("7/14/2026") or a fraction/score
# ("5/4"). Real sentences carry these; credit chains don't.
_SLASH_NUMBER_RE = _re.compile(r"\d\s*/\s*\d")


def _looksLikePhotoCreditChain(text: str) -> bool:
	"""Detect a slash-separated photo-credit chain with no parentheses.

	The breitbart.com case (2026-07-14 soak): the whole paragraph is
	"Matthew Jonas/MediaNews Group/Boulder Daily Camera/Getty" — a
	photographer, their outlet chain, and the agency, joined by slashes. It
	missed BOTH existing credit signals: there is no parenthetical, and it
	says "Getty" rather than the literal "Getty Images" the phrase list
	looks for. The addon landed the cursor on it as if it were the lede.

	Rather than chase agency names (an unbounded list), match the SHAPE:
	a short line built of 3+ slash-joined fragments that isn't a sentence.

	Guards against the obvious false positives:
	  - digits around a slash → a date or score, so real prose
	    ("The meeting is set for 7/14/2026 at city hall.")
	  - ends like a sentence → real prose
	    ("He asked whether the on/off switch mattered.")
	  - long → real prose; credits are short
	"""
	stripped = (text or "").strip()
	if not stripped or len(stripped) > 120:
		return False
	if stripped.count("/") < 2:
		return False
	if _SLASH_NUMBER_RE.search(stripped):
		return False
	if endsLikeSentence(stripped):
		return False
	return True


def _looksLikeImageCaption(text: str) -> bool:
	"""Detect a figure caption / photo credit masquerading as a body paragraph.

	Three signals, any one is enough:
	  1. A trailing parenthetical naming a photo agency / wire service or
	     starting with Photo/Image/Courtesy (the "...(Getty Images)" shape).
	  2. An unambiguous credit phrase anywhere ("getty images", "photo
	     credit", "photo courtesy", etc.).
	  3. A slash-separated credit chain with no parentheses at all
	     ("Matthew Jonas/MediaNews Group/Boulder Daily Camera/Getty").

	Conservative by design — real article prose doesn't carry these — so a
	false positive that skips a genuine paragraph is very unlikely.
	"""
	if not text:
		return False
	if _PHOTO_CREDIT_END_RE.search(text):
		return True
	if _looksLikePhotoCreditChain(text):
		return True
	lower = text.lower()
	return any(phrase in lower for phrase in _PHOTO_CREDIT_PHRASES)


def _nodeIsCaption(node) -> bool:
	"""True if a node is a figure caption / photo credit.

	Prefers the precomputed ``isCaption`` flag, which treeSummary sets at
	walk time over the FULL chunk text — the only place the trailing credit
	is visible, since textPreview is truncated to 60 chars. Falls back to
	re-checking textPreview so unit-test fixtures (which carry full text in
	the preview and don't set the flag) and the rare credit-within-60-chars
	case are still caught.
	"""
	if getattr(node, "isCaption", False):
		return True
	return _looksLikeImageCaption(node.textPreview or "")


# Legal footer boilerplate: copyright lines and CCPA/privacy links rows.
# These live in every site's footer and are never the content a user came
# for — but on a not-yet-hydrated SPA shell (Zoom webinar registration was
# the canonical case) the copyright line is often the ONLY paragraph that
# clears the substantial bar, so it was winning the landing and getting
# spoken as if it were the page's content. Signals, each safe on its own:
#   - "all rights reserved" — the phrase essentially never appears in prose.
#   - "copyright" / © immediately followed by a 19xx/20xx year. Requiring
#     the year keeps articles ABOUT copyright ("the copyright office ruled
#     in 2026...") from matching.
#   - The CCPA-mandated "Do Not Sell (or Share) My Personal Information"
#     link text — footer-only language, catches merged footer link rows.
#   - Purchase/terms-consent formula: "you agree to our Terms and
#     Conditions", "you agree to the Terms of Service", "you consent to
#     our Privacy Policy". Contract-law wording, as enumerable as the
#     rest. Checkout pages put this next to the Submit button as long,
#     sentence-ending prose, so it won the article cascade's
#     very-substantial gate AND (with its neighbours) faked the strong
#     body cluster that blocks FORM — store.payproglobal.com's 10-input
#     checkout classified ARTICLE and landed the user in the legalese
#     (2026-07-17). Second person + consent verb + legal object are all
#     required: "the sides agreed to the terms" (no "you") and "By
#     placing your order early, you can avoid delays" (no consent verb
#     targeting the terms) stay prose. \s covers the non-breaking spaces
#     real pages use inside "Terms\xa0and\xa0Conditions".
_LEGAL_BOILERPLATE_RE = _re.compile(
	r"\ball rights reserved\b"
	r"|\bcopyright\s*(?:©|\(c\))?\s*(?:19|20)\d{2}\b"
	r"|©\s*(?:19|20)\d{2}\b"
	r"|\bdo not sell (?:or share )?my personal information\b"
	r"|\byou\s+(?:agree|consent)\s+to\s+(?:our|the|these)\s+(?:terms|privacy\s+policy)\b",
	_re.IGNORECASE,
)


def _looksLikeLegalBoilerplate(text: str) -> bool:
	"""Detect a copyright / legal-footer line masquerading as a body paragraph.

	Conservative by design: every signal is language that effectively never
	occurs in real article prose. A false positive just means the landing
	skips to the next paragraph; a false negative means the add-on speaks a
	copyright notice as if it were the point of the page.
	"""
	if not text:
		return False
	return bool(_LEGAL_BOILERPLATE_RE.search(text))


def _nodeIsBoilerplate(node) -> bool:
	"""True if a node is legal footer boilerplate.

	Same two-layer scheme as _nodeIsCaption: prefer the walk-time
	``isBoilerplate`` flag (computed over the FULL chunk text — the
	"All rights reserved" tail commonly sits past the 60-char preview
	cutoff), fall back to re-checking the preview for fixtures and for
	lines whose signal appears early ("Copyright ©2026 ..." matches
	within the first 60 chars).
	"""
	if getattr(node, "isBoilerplate", False):
		return True
	return _looksLikeLegalBoilerplate(node.textPreview or "")


# Related-article promo teasers: news sites drop "READ MORE:" / "RELATED:"
# boxes between the byline and the article body, and the promo headline is
# long enough to clear the substantial bar. Daily Mail's "• READ MORE:
# America's greatest mystery was a lie..." (109 chars) won the cluster gate
# and got spoken as if it were the story. The label is at the START of the
# line (always inside the 60-char preview) and these promos render the label
# in ALL CAPS — the match is deliberately case-SENSITIVE so real prose
# ("Read more about the study here.") never trips it.
_PROMO_TEASER_RE = _re.compile(
	r"^\s*[•▪‣·*-]?\s*"
	r"(?:READ MORE|RELATED(?: ARTICLES?| STORY| STORIES)?|SEE ALSO"
	r"|DON'T MISS|MORE ON THIS)\s*:"
)
# Note: "EXCLUSIVE:" is deliberately NOT in the list — sites open real story
# ledes with it, so filtering it would skip genuine article openings.


def _looksLikePromoTeaser(text: str) -> bool:
	"""Detect an all-caps "READ MORE:"-style related-article promo line."""
	if not text:
		return False
	return bool(_PROMO_TEASER_RE.match(text))


# Participle byline openers: "Written by Michael Larabel in Arch Linux on
# 14 June 2026 at 05:30 AM EDT" (Phoronix). Unlike bare "By ...", these
# participle forms essentially never open a narrative body paragraph, so a
# mixed-case name is safe to match. Requires a capitalized name after "by"
# ("Written by hand, the letter..." stays) and caps total length at 120 —
# a book-review lede like "Written by John Steinbeck in 1939, The Grapes
# of Wrath endures..." usually runs longer; if one ever is that short, the
# cost is landing one paragraph later, not on chrome.
_PARTICIPLE_BYLINE_RE = _re.compile(
	r"^(?:Written|Posted|Published|Story|Reported|Reviewed|Words|Photos?|Photographs?)"
	r"\s+by\s+[A-Z]"
)
_PARTICIPLE_BYLINE_MAX_CHARS = 120

# Dated byline: "By Jenn Baker Jul. 20, 2026 7:40 pm" (Gateway Pundit, and the
# common news/CMS shape generally). This is the mixed-case "By Name" the
# all-caps rule below deliberately skips, but the publication DATE makes it
# safe: a full "Month DD, YYYY" date right after a "By Name" opener is a
# timestamp, not prose. Three guards keep it off real ledes that open with
# "By": the word after "By" must be a capitalized NAME (so "By 2026, ...",
# "By all accounts ...", "By NASA's estimate ..." with a lowercase/numeric
# second token never match... "By NASA" is caught by the weekday/temporal
# exclusion? no — NASA is a name, but a real lede "By NASA's estimate" carries
# no Month-DD-YYYY date, so the date guard rejects it); it must carry a full
# Month-DD-YYYY date (so "By January 2026, sales rose" — no day — is safe);
# and the opener word must not be a weekday ("By Monday, June 5, 2026, the
# crews ..." is temporal prose, not a byline). Short cap for the same reason
# as the participle form: a real sentence built around a date runs longer.
_BYLINE_FULLDATE_RE = _re.compile(
	r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b"
)
_BYLINE_TEMPORAL_OPENERS = frozenset({
	"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
	"then", "now", "morning", "afternoon", "evening", "midnight", "noon",
})
_DATED_BYLINE_MAX_CHARS = 120


def _looksLikeByline(text: str, fullLength: Optional[int] = None) -> bool:
	"""Detect a news byline masquerading as a body paragraph. Two forms:

	1. All-caps "By ..." (Daily Mail): starts with exactly "By " and at
	   least 70% of the alphabetic characters are uppercase. The ratio
	   protects real prose that opens with "By": "By NASA's estimate, the
	   mission will cost..." is mostly lowercase and never matches.
	   Mixed-case "By John Smith" is a known deliberate gap — it's
	   indistinguishable from prose openers like "By Tuesday, the storm
	   had..." without risking real ledes.
	2. Participle bylines "Written/Posted/Published/... by Name ..."
	   (Phoronix): mixed case allowed, capped at 120 chars — see
	   _PARTICIPLE_BYLINE_RE above.

	fullLength: the paragraph's FULL text length when `text` is a
	truncated 60-char preview (as passed by _isChromeParagraph). The
	participle cap must judge the real length, not the preview's.
	"""
	if not text:
		return False
	effectiveLength = fullLength if fullLength is not None else len(text)
	if (
		effectiveLength <= _PARTICIPLE_BYLINE_MAX_CHARS
		and _PARTICIPLE_BYLINE_RE.match(text)
	):
		return True
	if not text.startswith("By "):
		return False
	# Dated byline: "By Name ... Month DD, YYYY [time]". See _BYLINE_FULLDATE_RE.
	if effectiveLength <= _DATED_BYLINE_MAX_CHARS:
		rest = text[3:].lstrip()
		firstWord = rest.split(maxsplit=1)[0] if rest else ""
		if (
			firstWord[:1].isupper()
			and firstWord.strip(".,'").lower() not in _BYLINE_TEMPORAL_OPENERS
			and _BYLINE_FULLDATE_RE.search(text)
		):
			return True
	letters = [c for c in text[3:] if c.isalpha()]
	if len(letters) < 6:
		return False
	upper = sum(1 for c in letters if c.isupper())
	return upper / len(letters) >= 0.7


# Editorial disclosures: affiliate/referral notices and syndication notes.
#
# These are the boilerplate that READS LIKE PROSE. They are grammatical
# sentences sitting exactly where a lede should be, so the "must end like a
# sentence" rule cannot see them at all -- it was built to separate prose from
# fragments, and these are perfectly good prose.
#
# Why a phrase list and not something cleverer: the cross-page idea ("boilerplate
# is what repeats across a site") was rejected by two independent reviews. It is
# stateful, it makes the same URL land differently on visit 1 and visit 4, it
# breaks fixture-based debugging, and it does nothing on a FIRST visit -- which is
# the common case, a search click into an unfamiliar host. And for a blind user,
# predictable-and-slightly-wrong beats adaptive-and-sometimes-right: you can learn
# "this site lands one paragraph early, press Down once"; you cannot learn a
# moving target.
#
# These two families have near-mandated vocabulary (the FTC effectively dictates
# the affiliate wording), which makes them as enumerable as the "All rights
# reserved" filter already here -- and they work on the first visit.
#
# Masthead marketing ("rigorously tested in our Nashville Test Kitchen") and
# generic value-prop promos ("Keep your favorites in MyRecipes for free") are
# NOT in here. Their vocabulary is open, and a rule loose enough to catch them
# would eat real ledes ("Keep your eyes on...", "Imagine you're..."). Those stay
# a KNOWN GAP: the cost is landing one paragraph early, one Down arrow.
#
# The EXPLICIT newsletter-signup CTA is the exception, added 2026-07-21 after a
# Tom's Hardware front page landed on "Get Tom's Hardware's best news and
# in-depth reviews, straight to your inbox." Casey's rule: a newsletter box is
# never what you came to read. It has near-mandated phrasing ("to your inbox",
# "sign up for our newsletter") as enumerable as the affiliate family, so it is
# tractable where open value-prop marketing is not. See _NEWSLETTER_PROMO.

# Phrases that essentially never occur outside a disclosure. Safe on their own.
_DISCLOSURE_UNAMBIGUOUS = (
	# Affiliate / referral -- FTC-driven formula language.
	"affiliate link",
	"referral link",
	"may earn a commission",
	"we may earn",
	"earns a commission",
	"earn a small commission",
	"as an amazon associate",
	"at no extra cost to you",
	# Syndication / republication.
	"republished with permission",
	"syndicated from",
	"news partner",
	# Marketing-consent boilerplate on newsletter / SMS signup widgets. Same
	# family, same reason it is tractable: telecom marketing law drives the
	# wording, so it is formulaic. KRDO carries this ABOVE the story and we
	# landed on it repeatedly (Chrome soak, 2026-07-14).
	#
	# Each phrase is deliberately narrow enough that ordinary prose about
	# marketing or subscriptions cannot match: "voters did not agree to receive
	# a tax increase" has no "YOU agree to receive"; "readers may unsubscribe
	# from the paper" has no "unsubscribe AT ANY TIME".
	"you agree to receive",
	"message and data rates",
	"msg and data rates",
	"msg & data rates",
	"standard message rates",
	"unsubscribe at any time",
	"frequency of messages may vary",
	"consent is not a condition",
)

# "originally appeared on" is NOT safe alone -- "She originally appeared on the
# show in 1998" is ordinary prose. Publishing language only counts when the
# paragraph is also talking about ITSELF, which is what makes it a disclosure
# rather than a sentence about a person. Match the conjunction, not the keyword.
_DISCLOSURE_SELF_REFERENCE = (
	"this post",
	"this article",
	"this story",
	"this recipe",
	"this piece",
)
_DISCLOSURE_PUBLISHING = (
	"originally appeared",
	"originally published",
	"first appeared",
	"first published",
)

# Publisher opinion-disclaimer -- "The opinions expressed by contributors are
# their own and do not necessarily represent the views of RedState.com." This
# is standardized boilerplate on opinion/news sites; it sits between the byline
# and the lede, reads as a grammatical sentence, and ended sentence-strict, so
# the cascade landed on it (RedState, three articles, 2026-07-20). Matched as a
# conjunction, same discipline as the publishing family: an "expressed
# opinion/view" phrase AND a "not necessarily reflect/represent" phrase. Neither
# half is safe alone -- "the opinions expressed at the meeting were heated" is
# prose, and "these results do not necessarily represent the population" is
# prose -- but together they essentially only occur in this disclaimer. The
# giveaway "not necessarily..." half routinely sits past the 60-char preview,
# so this is computed at walk time over the full chunk text like the rest.
_DISCLOSURE_OPINION = (
	"opinions expressed",
	"views expressed",
	"opinion expressed",
	"view expressed",
)
_DISCLOSURE_NOT_NECESSARILY = (
	"not necessarily reflect",
	"not necessarily represent",
	"not necessarily those of",
	"not necessarily the views",
	"not necessarily the opinions",
	"not necessarily shared by",
)

# Explicit newsletter-signup CTA. Near-mandated phrasing, safe on its own — real
# article prose essentially never says "to your inbox" or "sign up for our
# newsletter" in a landing-length paragraph. Deliberately NOT the bare word
# "newsletter" (an article ABOUT a newsletter would trip it); each phrase names
# the SIGNUP action or the inbox delivery.
_NEWSLETTER_PROMO = (
	"to your inbox",
	"in your inbox",
	"straight to your inbox",
	"delivered to your inbox",
	"sign up for our newsletter",
	"sign up for the newsletter",
	"subscribe to our newsletter",
	"join our newsletter",
	"sign up to receive",
	"signup for our newsletter",
)

# Disclosures are SHORT. A long paragraph that mentions affiliate links is
# probably an article ABOUT affiliate marketing, i.e. real content.
_EDITORIAL_DISCLOSURE_MAX_CHARS = 300


def _looksLikeEditorialDisclosure(text: str, fullLength: int = None) -> bool:
	"""Affiliate/referral disclosure or a syndication note, both of which sit
	between the headline and the real lede and read as ordinary prose.

	Real cases from the 2026-07-14 soak:
	  "This post contains referral links for products we love."      (Pinch of Yum)
	  "This article was written by WTOP's news partner, The Banner
	   Montgomery, and republished with permission."                 (WTOP)

	`fullLength` is the chunk's REAL length when the caller only has the
	60-char preview. Without it the length guard below was dead code at runtime
	(a 60-char preview can never exceed 300), which broke the rule in BOTH
	directions: it could never reject a long paragraph, so an article whose
	opening 60 chars mention affiliate links got chrome-flagged with no length
	protection at all. Same fix, and same reason, as the byline filter's
	`fullLength`. The unit tests pass whole sentences straight in, which is why
	they validated a guard the runtime never actually applied.
	"""
	stripped = (text or "").strip()
	if not stripped:
		return False
	length = fullLength if fullLength is not None else len(stripped)
	if length > _EDITORIAL_DISCLOSURE_MAX_CHARS:
		return False
	lower = stripped.lower()
	if any(phrase in lower for phrase in _DISCLOSURE_UNAMBIGUOUS):
		return True
	# Publishing language only counts when the paragraph refers to ITSELF.
	if (
		any(p in lower for p in _DISCLOSURE_SELF_REFERENCE)
		and any(p in lower for p in _DISCLOSURE_PUBLISHING)
	):
		return True
	# Explicit newsletter-signup CTA.
	if any(p in lower for p in _NEWSLETTER_PROMO):
		return True
	# Publisher opinion-disclaimer: an "expressed opinion/view" phrase paired
	# with a "not necessarily reflect/represent" phrase.
	return (
		any(p in lower for p in _DISCLOSURE_OPINION)
		and any(p in lower for p in _DISCLOSURE_NOT_NECESSARILY)
	)


def _nodeIsDisclosure(node) -> bool:
	"""True if a node is an editorial disclosure / syndication note.

	Same two-layer scheme as _nodeIsCaption and _nodeIsBoilerplate: prefer
	the walk-time ``isDisclosure`` flag, computed over the FULL chunk text
	because the giveaway phrase routinely sits past the 60-char preview cutoff
	("To receive license key and use all features of the software, " is already
	61 chars). Falls back to re-checking the preview for fixtures, passing the
	node's real length so the 300-char guard still applies there.
	"""
	if getattr(node, "isDisclosure", False):
		return True
	return _looksLikeEditorialDisclosure(
		node.textPreview or "", fullLength=getattr(node, "textLength", None),
	)


# Cookie / tracking consent text. Matched on a CONJUNCTION, the same way
# _looksLikeEditorialDisclosure is: a first-person subject ("we", "this site",
# "we and our partners"), a placing verb, and the cookie or device-storage
# object, all within one sentence. Loose keyword matching on "cookies" alone
# would eat an article about cookie legislation, which is real prose someone
# came to read.
#
# Deliberately NOT widened to consent text that never says what it stores
# ("We value your privacy. Your GPC signal has been detected"). That wording
# is too close to ordinary prose to match safely, and the cost of missing one
# is a single Down arrow. Verified against 385 captured pages: three matches,
# all genuine consent banners, no article prose.
_COOKIE_CONSENT_RE = _re.compile(
	r"\b(we|this (?:site|website)|our (?:site|website)|we and our (?:partners|vendors))\b"
	r"[^.]{0,80}\b(use|uses|using|store|stores|storing|access(?:es)?|place|places)\b"
	r"[^.]{0,60}\b(cookies?|similar technolog(?:y|ies)|device (?:data|information))\b",
	_re.I,
)


def _looksLikeCookieConsent(text: str) -> bool:
	return bool(_COOKIE_CONSENT_RE.search(text or ""))


# Machine-serialized data rendered as a paragraph. A Google Apps Script user
# content page served a 115,605-character JSON document as ONE paragraph, which
# sails past VERY_SUBSTANTIAL_PARAGRAPH_CHARS and wins the landing outright: the
# add-on read a blind user the opening of a JSON blob. Length is not evidence of
# prose, and nothing else in the cascade was ever going to notice.
#
# Anchored at the start and requiring a quoted key, so a paragraph that merely
# contains a brace or an editor's bracketed note does not match. Verified
# against 385 captured pages: one match, the blob itself.
_SERIALIZED_DATA_RE = _re.compile(r'^\s*[\{\[].{0,400}?"\s*:\s*', _re.S)


def _looksLikeSerializedData(text: str) -> bool:
	return bool(_SERIALIZED_DATA_RE.search(text or ""))


def _isChromeParagraph(node) -> bool:
	"""Shared "never land here" filter for paragraph candidates.

	Combines every chrome shape the landing finders skip: tag/category
	rows, social-share URL payloads, screen-reader instructional text,
	figure captions / photo credits, and legal footer boilerplate. Used
	by every landing cascade so a new chrome shape only needs adding in
	one place.
	"""
	text = node.textPreview or ""
	return (
		_looksLikeTagList(text)
		or _looksLikeShareLinkPayload(text)
		or _looksLikeUrlSlug(text)
		or _looksLikeBreadcrumb(text)
		or _looksLikeAccessibilityInstructions(text)
		or _looksLikePromoTeaser(text)
		or _nodeIsDisclosure(node)
		or _looksLikeByline(text, fullLength=node.textLength)
		or _nodeIsCaption(node)
		or _nodeIsBoilerplate(node)
		or _looksLikeCookieConsent(text)
		or _looksLikeSerializedData(text)
	)


# Prose-run landing: social/chat-style pages (X single-status pages were the
# trigger) expose one logical message as a RUN of consecutive short paragraph
# lines — each under the 50-char landing bar, together clearly the content.
# A run of >= _PROSE_RUN_MIN_LINES consecutive non-chrome paragraphs, each
# >= _PROSE_RUN_MIN_LINE_CHARS, totaling >= _PROSE_RUN_MIN_TOTAL_CHARS,
# qualifies as a landing (on its FIRST line) only when at least
# _PROSE_RUN_MIN_SENTENCE_ENDS lines AND at least half the run end like
# sentences. The sentence-end requirement is what separates real prose from
# the two shapes that defeat any purely length-based rule: nav/directory link
# runs (Montgomery probate: six 17-26 char Title Case rows, no punctuation)
# and form-label runs (signed-in Zoom: sixteen 18-char labels plus one
# "...disability?" question — 1 sentence-ender out of 17 lines).
_PROSE_RUN_MIN_LINES = 2
_PROSE_RUN_MIN_LINE_CHARS = 15
_PROSE_RUN_MIN_TOTAL_CHARS = 100
_PROSE_RUN_MIN_SENTENCE_ENDS = 2

# Trailing closing quotes/brackets that may follow terminal punctuation.
_SENTENCE_END_CLOSERS = "\"'”’)]»"


def endsLikeSentence(text: str) -> bool:
	"""True when text ends with sentence-terminal punctuation (. ! ? or an
	ellipsis), allowing trailing closing quotes/brackets after it. Called by
	treeSummary at walk time over the FULL chunk text to set
	MainNode.endsSentence — the terminal character of a 61+ char line sits
	past the 60-char preview cutoff, so a preview check is not enough.
	"""
	stripped = (text or "").rstrip()
	stripped = stripped.rstrip(_SENTENCE_END_CLOSERS)
	return stripped.endswith((".", "!", "?", "…"))


def _nodeEndsSentence(node) -> bool:
	# Prefer the walk-time flag; fall back to the preview for fixtures and
	# for lines short enough that the preview is the full text.
	if getattr(node, "endsSentence", False):
		return True
	if node.textLength <= 60:
		return endsLikeSentence(node.textPreview or "")
	return False


def _findProseRunLanding(nodes) -> Optional[int]:
	"""Find the first qualifying prose run and return the index of its first
	line, or None. See the _PROSE_RUN_* constants above for what qualifies.
	Only runs that start AFTER a heading are considered — pre-heading
	sentence-shaped runs are typically cookie banners / publisher
	disclaimers, the same pre-H1 chrome the hero gate guards against.
	"""
	seenHeading = False
	runStart = None
	runTotal = 0
	runLen = 0
	runSentenceEnds = 0
	runStartedAfterHeading = False

	def runQualifies() -> bool:
		return (
			runStartedAfterHeading
			and runLen >= _PROSE_RUN_MIN_LINES
			and runTotal >= _PROSE_RUN_MIN_TOTAL_CHARS
			and runSentenceEnds >= _PROSE_RUN_MIN_SENTENCE_ENDS
			and runSentenceEnds * 2 >= runLen
		)

	for i, node in enumerate(nodes):
		eligible = (
			node.kind == "paragraph"
			and node.textLength >= _PROSE_RUN_MIN_LINE_CHARS
			and not _isChromeParagraph(node)
		)
		if eligible:
			if runStart is None:
				runStart = i
				runTotal = 0
				runLen = 0
				runSentenceEnds = 0
				runStartedAfterHeading = seenHeading
			runTotal += node.textLength
			runLen += 1
			if _nodeEndsSentence(node):
				runSentenceEnds += 1
		else:
			if runStart is not None and runQualifies():
				return runStart
			runStart = None
			if node.kind == "heading":
				seenHeading = True
	if runStart is not None and runQualifies():
		return runStart
	return None


# News-article dateline: an AP-style "CITY (SOURCE) - " / "CITY - " opener that
# marks the genuine first line of the story body. The location is in capitals,
# optionally followed by a parenthetical wire-service / station tag, then an
# em-dash, en-dash, or spaced hyphen. It lives in the first ~30 chars, so the
# 60-char textPreview always shows it. — = em-dash, – = en-dash.
_NEWS_DATELINE_RE = _re.compile(
	r"^[A-Z][A-Z.&'\- ]{1,30}?(?:\([A-Za-z0-9.\-/ ]+\)\s*)?[—–-]\s",
)


def _looksLikeNewsDateline(text: str) -> bool:
	"""True if text opens with an AP-style dateline ("DENVER (KDVR) - ...").

	Protects a short-but-real lede from the teaser-skip rule below. A news
	lede is frequently under 100 chars and immediately followed by a long
	body paragraph — which looks exactly like a CNET-style teaser and would
	otherwise be skipped. The dateline is the signal that this short line is
	the real start of the article, not a teaser to step past.
	"""
	if not text:
		return False
	return bool(_NEWS_DATELINE_RE.match(text))


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


def _findBloggingPromptLanding(nodes):
	"""If a Jetpack daily-writing-prompt widget is present, return the index
	of the prompt question (the node immediately after the label). Returns
	None when no such widget is found, so the caller falls through to the
	normal article-shape heuristics.
	"""
	count = len(nodes)
	for i, node in enumerate(nodes):
		text = (node.textPreview or "").strip().lower()
		if not text:
			continue
		if not any(text == lbl or text.startswith(lbl) for lbl in _BLOGGING_PROMPT_LABELS):
			continue
		if i + 1 < count:
			nxt = nodes[i + 1]
			# The question should be the next text node, not another label or
			# a stray short fragment. 15 chars clears "View all responses"-style
			# link text while admitting any real question.
			if nxt.kind == "paragraph" and nxt.textLength >= 15:
				return i + 1
	return None


def _firstSubstantialParagraph(nodes, minChars) -> Optional[int]:
	"""Return the index of the first paragraph >= minChars, skipping the same
	chrome shapes the main cascade skips (tag lists, share-link payloads,
	accessibility instructions). Returns None if none qualifies.

	Used only when the tree is positionally scoped to a single <article>: the
	nav/comments/footer have already been excluded by position, so the first
	real paragraph is the genuine opening line and we don't need the defensive
	hero/cluster gates that guard noisy unscoped trees.
	"""
	for i, node in enumerate(nodes):
		if node.kind != "paragraph" or node.textLength < minChars:
			continue
		if _isChromeParagraph(node):
			continue
		return i
	return None


def _sentenceStrictView(tree: TreeSummary) -> Optional[TreeSummary]:
	"""A copy of ``tree`` in which every PARAGRAPH that doesn't end like a
	sentence is flagged as boilerplate, so the landing cascade skips it.

	Indices align 1:1 with the original ``tree.mainNodes`` — nodes are
	replaced, never removed — so an index found here is valid in the original.
	Headings are left alone: they legitimately don't end in terminal
	punctuation, and the directory-page redirect lands on one.

	Returns None when no paragraph ends like a sentence (nothing to gain, and
	the strict pass would just find nothing).

	Why: in the 2026-07-14 soak, all 9 GOOD landings were prose ending in
	terminal punctuation, and all 4 BAD ones were paragraphs that weren't:
	a photo credit ending "…/Getty", an ad banner ending "…Founded By
	Veterans", a self-promo ending "…Preferred Source", and another story's
	headline ending "…the law". One signal separated every good landing from
	every bad one, so it's a pass over the whole cascade rather than four
	more shape-matching filters.

	This reuses isBoilerplate purely as the "skip me" channel that
	_isChromeParagraph already honours — it avoids threading a strict-mode
	flag through the eight functions that call it, and it mutates nothing.
	"""
	nodes = tree.mainNodes
	if not any(
		n.kind == "paragraph" and _nodeEndsSentence(n)
		for n in nodes
	):
		return None
	strictNodes = [
		_dataclasses.replace(n, isBoilerplate=True)
		if (n.kind == "paragraph" and not n.isBoilerplate and not _nodeEndsSentence(n))
		else n
		for n in nodes
	]
	return _dataclasses.replace(tree, mainNodes=strictNodes)


# Headline-list (index / homepage) landing. A news index is a WALL of headline
# links: a run of consecutive medium paragraphs that are article TITLES (mostly
# NOT sentence-ending), with no real article body. Casey's rule: land on the
# FIRST headline, the way stevequayle.com already lands on its first bullet.
# Tom's Hardware, lite.cnn, and text.npr were landing deep in chrome because
# their newsletter/footer/bio prose (grammatical, sentence-ending) hijacked the
# sentence-strict pass; this gate runs first and lands on the first headline.
_HEADLINE_MIN_CHARS = 30       # shorter than this is nav/label, not a headline
_HEADLINE_MAX_CHARS = 250      # longer is prose, not a title
_HEADLINE_RUN_MIN = 6          # need a real WALL, not a couple of nav rows
_HEADLINE_SENTENCE_FRAC_MAX = 0.5  # titles mostly don't end like sentences
_HEADLINE_GAP_MAX = 2          # short/chrome nodes inside the wall are transparent


def _hasArticleBodyCluster(nodes) -> bool:
	"""True when the page has a real article body: >= 2 consecutive non-chrome
	sentence-ending paragraphs of >= 100 chars. This is what separates an ARTICLE
	(with maybe a related-stories rail) from an INDEX (all titles, no body)."""
	run = 0
	for node in nodes:
		if (
			node.kind == "paragraph"
			and node.textLength >= 100
			and node.endsSentence
			and not _isChromeParagraph(node)
		):
			run += 1
			if run >= 2:
				return True
		elif node.kind == "heading" or (node.kind == "paragraph" and node.textLength >= _HEADLINE_MIN_CHARS):
			run = 0
	return False


def _repeatsPreviousMember(nodes, members, node) -> bool:
	"""True when this headline-ish node is the SAME item as the previous member,
	emitted a second time in a longer form.

	WHY THIS EXISTS. A media rail commonly emits each item twice: the bare title,
	then the title with its source appended. Google's video rail does exactly
	that ("How to Mod Minecraft for Beginners!" then "How to Mod Minecraft for
	Beginners! by <channel> on YouTube"). Three videos then read as SIX headline
	members, _HEADLINE_RUN_MIN is met, the wall fires on a page that has no wall,
	and a Google results page lands on a video title instead of its first result.
	Reproduced on four captured Google pages (2026-09-10): the wall fired on the
	tachyon and mod queries, whose rails carry three videos, and declined on the
	quark and moon queries, whose rails carry one fewer. Nothing about this is
	Google-specific; any rail that repeats a title in a longer form trips it.

	Compared against the PREVIOUS MEMBER, not the previous node, because the two
	emissions are separated by the source and date lines the gap tolerance
	already steps over.

	THE 60-CHARACTER PREVIEW IS THE CONSTRAINT that shapes this rule. textPreview
	is truncated, so two genuinely distinct long titles can share a preview and
	read as duplicates. Two things keep that harmless: the comparison is confined
	to CONSECUTIVE members, so a wall of distinct items loses at most a neighbour
	here and there out of dozens; and the repeat must be at least as long as what
	it repeats, so a shorter follow-on never collapses into a longer title.

	This removes the node from the MEMBER COUNT only. members[0] is the bare
	title and is already the landing candidate, so what the wall lands ON does
	not change; what changes is whether the wall fires at all.
	"""
	if not members:
		return False
	prev = nodes[members[-1]]
	prevText = normalizeForMatch(getattr(prev, "textPreview", "") or "")
	thisText = normalizeForMatch(getattr(node, "textPreview", "") or "")
	if len(prevText) < _HEADLINE_MIN_CHARS:
		# Too short to be a distinctive prefix; collapsing on a few generic
		# words would eat real, separate items.
		return False
	return thisText.startswith(prevText) and node.textLength >= prev.textLength


def _findHeadlineListLanding(nodes) -> Optional[int]:
	"""Index/homepage detection: the FIRST run of >= _HEADLINE_RUN_MIN
	consecutive headline-ish paragraphs (medium length, non-chrome), mostly
	non-sentence-ending, on a page with no article body. Returns the first
	member's index, or None. See the header comment above."""
	if _hasArticleBodyCluster(nodes):
		return None
	i, count = 0, len(nodes)
	while i < count:
		members, gap, j = [], 0, i
		while j < count:
			node = nodes[j]
			if node.kind == "heading":
				break
			headlineish = (
				node.kind == "paragraph"
				and _HEADLINE_MIN_CHARS <= node.textLength <= _HEADLINE_MAX_CHARS
				and not _isChromeParagraph(node)
			)
			if headlineish and _repeatsPreviousMember(nodes, members, node):
				# A REPEAT OF THE MEMBER ALREADY COUNTED, not a second item.
				# Transparent: neither a member nor a gap.
				pass
			elif headlineish:
				members.append(j)
				gap = 0
			elif members:
				gap += 1
				if gap > _HEADLINE_GAP_MAX:
					break
			j += 1
		if len(members) >= _HEADLINE_RUN_MIN:
			sent = sum(1 for m in members if _nodeEndsSentence(nodes[m]))
			if sent / len(members) <= _HEADLINE_SENTENCE_FRAC_MAX:
				return members[0]
		i = max(j, i + 1)
	return None


def findArticleLanding(tree: TreeSummary) -> Optional[int]:
	"""Land on real body prose, preferring paragraphs that end like a sentence.

	Two passes over the same cascade:

	  1. STRICT — non-sentence-ending paragraphs treated as chrome. This is
	     what skips photo credits, ad banners, self-promos and other stories'
	     headlines, all of which are substantial enough to win the cluster and
	     hero gates but are not prose.

	  2. UNRESTRICTED — the original cascade, unchanged.

	Pass 2 is NOT a safety net, it is load-bearing. On a link-aggregator front
	page (stevequayle.com) every item is a bulleted headline and NOTHING ends
	like a sentence; landing on the first headline is the CORRECT behavior
	there. Without pass 2 such a page would land nowhere at all. There is a
	test pinning this: testArticleLandingFallsBackWhenNoSentenceEnders.

	Index/homepage pages (a wall of headline links, no article body) are handled
	FIRST by _findHeadlineListLanding, so a stray prose sentence in a
	newsletter box or footer can't hijack pass 1 into landing on chrome. This
	closes the "known hole" the two passes alone left open.
	"""
	idx = _findHeadlineListLanding(tree.mainNodes)
	if idx is not None:
		return idx
	strict = _sentenceStrictView(tree)
	if strict is not None:
		idx = _findArticleLandingImpl(strict)
		# Only TRUST the strict pass if it actually did the thing it exists to
		# do: land on prose that ends like a sentence. If it lands anywhere
		# else, it has nothing to offer and we fall back.
		#
		# This guard is not defensive padding — without it the strict pass
		# BROKE the X/Twitter single-status page. A tweet arrives as a run of
		# short line-per-paragraph chunks that individually don't end in
		# terminal punctuation; flagging them as chrome shattered the
		# consecutive run the prose-run gate needs, the cascade fell through
		# to a weaker gate, and it returned the generic "Post" heading at
		# index 0. Pinned by testArticleLandingProseRunOnXStatusPage.
		if idx is not None:
			node = tree.mainNodes[idx]
			if node.kind == "paragraph" and _nodeEndsSentence(node):
				return idx
	return _findArticleLandingImpl(tree)


def _findArticleLandingImpl(tree: TreeSummary) -> Optional[int]:
	"""Pick the best landing index in tree.mainNodes for an ARTICLE-classified
	page. The browse cursor will be moved to that paragraph and NVDA will
	speak it; we want to land on real BODY content, not on chrome (sidebar
	links, recent-post widgets, byline boilerplate) that happens to be
	substantial-length.

	Strategy: walk mainNodes in document order. A substantial paragraph
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

	Returns None if nothing in mainNodes qualifies at all.
	"""
	nodes = tree.mainNodes
	count = len(nodes)
	minChars = LANDING_MIN_PARAGRAPH_CHARS

	# First: the Jetpack daily-writing-prompt widget, if present. The prompt
	# question is the best orientation line on these posts but reliably loses
	# the cluster/hero gates below, so match the widget shape and land on it.
	idx = _findBloggingPromptLanding(nodes)
	if idx is not None:
		return idx

	# When the walk was positionally scoped to a single <article>, the tree is
	# already chrome-free, so the first substantial paragraph is the real
	# opening line. The hero/cluster gates below exist to skip pre-content
	# chrome in noisy unscoped trees; on a clean tree they overshoot the genuine
	# first paragraph (e.g. a 64-char prompt question followed by a short intro
	# line, which the gates skip in favor of a later list cluster).
	if getattr(tree, "positionallyScoped", False):
		idx = _firstSubstantialParagraph(nodes, minChars)
		if idx is not None:
			return idx

	# Next: look for a heading whose text matches a known content-section
	# label ("About this item", "Description", "Overview", "Features",
	# etc.) and land on the first substantial paragraph after it. This is
	# the strongest signal we have on heavily-chromed pages (Amazon
	# product pages, recipe sites, software docs) where article-shape
	# heuristics struggle to distinguish content from chrome.
	idx = _findContentSectionLanding(nodes, minChars)
	if idx is not None:
		return idx

	# Lead-section gate: a lone substantial sentence-ending paragraph between the
	# first heading and the next one is the page's lead. Runs BEFORE the size and
	# cluster gates, because those award the landing on rule ORDER rather than
	# EVIDENCE STRENGTH -- a weak two-paragraph cluster of 50-char fragments
	# returns immediately and beats a stronger candidate sitting earlier in the
	# document. That is precisely how IMDb's plot summary lost to a rail of video
	# clip titles. See _findLeadSectionLanding.
	idx = _findLeadSectionLanding(nodes)
	if idx is not None:
		return idx

	# Title-lede gate: sentence-ending prose directly under the page's H1 is the
	# opening line, even when it is too short for the size gates and an embedded
	# widget (a video player, a newsletter box) sits between it and the body so
	# the cluster gate cannot see it. Declines whenever the cluster gate can
	# handle the page itself. See _findTitleLedeLanding.
	idx = _findTitleLedeLanding(nodes)
	if idx is not None:
		return idx

	# How far to look ahead for a section-ending heading when checking
	# the hero/section-intro pattern. Some landing pages have a substantial
	# hero paragraph followed by 1-3 short banner/CTA lines before the
	# next H2/H3 — e.g., acb.org has hero + 2 conference-banner lines
	# before "Top Links" H2. Capped to prevent confusing distant content
	# with a hero pattern.
	heroLookahead = 4

	subject = _pageSubject(nodes)

	seenHeading = False
	for i, node in enumerate(nodes):
		if node.kind == "heading":
			seenHeading = True
		if node.kind != "paragraph" or node.textLength < minChars:
			continue
		# Chrome shapes (tag rows, share payloads, screen-reader help text,
		# photo credits, legal boilerplate) are never landing candidates.
		if _isChromeParagraph(node):
			continue
		# Very substantial paragraphs (>= 200 chars) are unambiguously
		# article body — accept immediately. Without this rule, a long
		# article intro can lose to later bullet-list clusters whose
		# adjacent items both pass the 50-char "substantial" bar.
		if node.textLength >= VERY_SUBSTANTIAL_PARAGRAPH_CHARS:
			return i
		if i + 1 >= count:
			# Last node — can't check neighbors for hero/cluster pattern.
			# Do NOT accept it just because it's last: on pages where the
			# scoped walk failed and mainNodes contains nav + footer, the
			# last substantial paragraph is often the footer disclaimer
			# (bestmidi.com/bg/: "This website is not affiliated with
			# Blizzard Entertainment." was winning over the actual intro).
			# Defer to the largest-paragraph fallback below — it handles
			# legitimate single-paragraph pages just as well.
			continue
		nxt = nodes[i + 1]
		# A: cluster start — immediately adjacent substantial paragraph.
		if nxt.kind == "paragraph" and nxt.textLength >= minChars:
			# Teaser-skip: when the candidate is short (<100 chars) and the
			# next paragraph is substantially longer (>2x AND >=150 chars),
			# prefer the next. CNET news articles commonly carry an 80-char
			# TLDR-style teaser between the H1 and the actual narrative
			# opening — "X can be a huge time saver, once you commit them
			# to memory." (82 chars) followed by "When I first started
			# using an iMac all the way back in 2008..." (209 chars). The
			# narrative paragraph is where a reader actually wants to be.
			# ...unless the short candidate is a news dateline lede
			# ("DENVER (KDVR) - ..."). That's the genuine opening line, not a
			# teaser: a short dateline lede followed by a long second paragraph
			# is the normal shape of a news story, so skipping to the long
			# paragraph would overshoot where the article actually starts.
			if (
				node.textLength < 100
				and nxt.textLength >= 150
				and nxt.textLength > node.textLength * 2
				and not _looksLikeNewsDateline(node.textPreview)
			):
				return i + 1
			# The cluster's FIRST paragraph is not always what the page is
			# about: on product and reference pages a prerequisite note or a
			# feature line commonly sits above the sentence that says what the
			# thing IS. Prefer that sentence when it is a few nodes below.
			# Returns None on ordinary prose, leaving this landing as-is.
			lede = _findDefinitionalLede(nodes, i, minChars, subject)
			if lede is not None:
				return lede
			return i
		# B: hero / section-intro — a heading appears within heroLookahead
		# nodes BEFORE any other substantial paragraph. The hero shortcut
		# uses a STRICTER threshold (HERO_PATTERN_MIN_CHARS=100) than the
		# 50-char "candidate" bar above: a 50-99 char paragraph followed
		# by a heading is just as likely to be UI metadata (account label,
		# breadcrumb, widget title) as a real hero — landing there is
		# wrong on app pages like calendar.google.com. Shorter candidates
		# fall through to the largest-paragraph fallback below, which on
		# app pages correctly picks the real content.
		if node.textLength < HERO_PATTERN_MIN_CHARS:
			continue
		# The hero shortcut also requires that we've ALREADY seen a heading
		# in mainNodes. Without this, a substantial publisher disclaimer
		# / dek / byline paragraph BEFORE the article's H1 wins because
		# the H1 itself is in the hero lookahead window. PCMag's "editors
		# select and review products..." disclaimer (167 chars) was the
		# canonical case. Article body comes AFTER the H1; pre-H1
		# substantial paragraphs are almost always chrome.
		if not seenHeading:
			continue
		heroQualifies = False
		end = min(i + 1 + heroLookahead, count)
		for j in range(i + 1, end):
			peek = nodes[j]
			if peek.kind == "heading":
				heroQualifies = True
				break
			if peek.kind == "paragraph" and peek.textLength >= minChars:
				# A later substantial paragraph means a cluster is coming;
				# THIS paragraph isn't the hero.
				break
		if heroQualifies:
			return i

	# Prose-run gate: no single paragraph qualified above, but the page may
	# carry its content as a run of consecutive SHORT lines — X/Twitter
	# single-status pages split one tweet into line-per-paragraph chunks
	# (19 + 34 + 61 chars on the canonical MarioNawfal page), each below
	# the 50-char bar, so every gate above misses them and the directory
	# redirect below would land on the generic "Post" heading instead.
	# Sentence-end density separates these runs from nav menus and
	# form-label runs; see _findProseRunLanding.
	idx = _findProseRunLanding(nodes)
	if idx is not None:
		return idx

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
	bestIdx = None
	bestLen = 0
	substantialCount = 0
	firstHeadingIdx = None
	for i, node in enumerate(nodes):
		if node.kind == "heading" and firstHeadingIdx is None:
			firstHeadingIdx = i
		if node.kind == "paragraph" and node.textLength >= minChars:
			# Skip the same chrome shapes the primary loop skips.
			if _isChromeParagraph(node):
				continue
			substantialCount += 1
			if node.textLength > bestLen:
				bestLen = node.textLength
				bestIdx = i

	# Directory-page redirect: a small page (≤30 nodes) with exactly one
	# substantial paragraph far past an earlier heading is almost always
	# a navigation/listing page where the "substantial" paragraph is the
	# footer (courthouse address, business hours, copyright). The user
	# wants to land at the title heading, not the footer.
	# montgomeryprobatecourtal.gov/resources/all-probate-forms is the
	# canonical case: H "All Probate Forms" at idx 7, courthouse address
	# paragraph at idx 21, no other substantial text. Land at idx 7.
	# The node cap was 30; widened to 40 for the signed-in Zoom webinar
	# registration page (36 nodes): its description/date live in CLOSED
	# accordions (not in the buffer at all), the only heading is the
	# "Webinar Registration" H2 at idx 5, and the lone substantial
	# paragraph is a 52-char question label at idx 24 mid-form. Same
	# pattern, slightly bigger page — the heading is the right landing.
	if (
		bestIdx is not None
		and substantialCount == 1
		and firstHeadingIdx is not None
		and firstHeadingIdx < bestIdx
		and (bestIdx - firstHeadingIdx) >= 5
		and len(nodes) <= _DIRECTORY_REDIRECT_MAX_NODES
	):
		return firstHeadingIdx
	return bestIdx


# Mirrored from classifier.py — controls when adjacent same-level headings
# count as a single cluster. Must match the classifier's value so we land
# at the same cluster the classifier identified.
_HEADING_CLUSTER_MAX_CHARS_BETWEEN = 300


def formWantsBrowseLanding(tree: TreeSummary) -> bool:
	"""True when a FORM-classified page should get a normal browse-mode
	landing (cursor on the title, spoken) instead of the announce-title-
	then-focus-first-input treatment.

	The signal is a very-substantial descriptive paragraph (>=
	VERY_SUBSTANTIAL_PARAGRAPH_CHARS, non-chrome) anywhere on the page.
	Registration pages commonly carry a real description between the title
	and the fields (Zoom webinar registration: 81-char H1 + ~2000-char
	description + 7 inputs was the canonical case). Jumping focus to the
	first input skips the user past all of that context; landing on the
	title lets them arrow through the description and into the form.

	Bare forms (Google-Forms-style title + field labels, login pages) have
	no such paragraph and keep the focus-first-input behavior.

	A TRUNCATED walk cannot prove the preamble is ABSENT — the paragraph
	may sit past where the clock stopped, and this check keys on absence.
	store.payproglobal.com's checkout flipped on exactly that: a fast walk
	(47 nodes) saw the 237-char trust-badge paragraph and landed in browse
	mode at the top of the order, while a slow hydrating refresh truncated
	at 34 nodes, read as "bare form", and jumped keyboard focus to the
	Quantity field (2026-07-17). The landing must not depend on walk
	timing, so a truncated walk takes the browse landing — the fail-safe
	branch, since it never moves focus. Genuinely bare forms almost never
	truncate (they are small pages); a huge survey that does truncate
	lands on its title in browse mode, which is still a correct entry
	point.
	"""
	if tree.walkTruncated:
		return True
	return any(
		n.kind == "paragraph"
		and n.textLength >= VERY_SUBSTANTIAL_PARAGRAPH_CHARS
		and not _isChromeParagraph(n)
		for n in tree.mainNodes
	)


def findFormLanding(tree: TreeSummary) -> Optional[int]:
	"""For FORM intent: land on the form's title (first heading) so the
	user hears "Form X" / "Survey Y" first, then can arrow forward to
	read the description and reach the input fields.

	On full-page forms (Google Forms, signup pages, intake forms) this
	is the right entry point — the user wants context before answering.
	On pages that auto-focused an input, SILENT_FOCUS_HONORED already
	caught them upstream and we don't reach here.

	Priority:
	  1. First heading — typically the form's title or section label.
	  2. First substantive paragraph (>= 30 chars) that ENDS LIKE A
	     SENTENCE — a form's description reads like a sentence, while the
	     page-header furniture above it doesn't. The PayPro Global
	     checkout is the canonical case (2026-07-17): no heading anywhere,
	     and the plain first-substantive rule landed on the vendor's
	     slogan under the logo ("exponential growth in file management
	     productivity" — a 50-char fragment, no terminal punctuation)
	     instead of the order summary's product description right below
	     "You're Buying", which does end like a sentence.
	  3. First substantive paragraph regardless of punctuation — so a
	     fragments-only form still gets its old landing.
	  4. First node — last resort.
	"""
	nodes = tree.mainNodes
	if not nodes:
		return None
	for i, n in enumerate(nodes):
		if n.kind == "heading":
			return i
	fallback = None
	for i, n in enumerate(nodes):
		if n.kind == "paragraph" and n.textLength >= 30:
			if _isChromeParagraph(n):
				continue
			if _nodeEndsSentence(n):
				return i
			if fallback is None:
				fallback = i
	if fallback is not None:
		return fallback
	return 0


def findKeyResultLanding(tree: TreeSummary) -> Optional[int]:
	"""For KEY_RESULT intent: land on the LABEL paragraph so the user can
	hear the label first, then arrow forward to hear the value and unit.

	The classifier already validated the pattern exists; we just need to
	re-locate the label index. We delegate to the classifier's public
	pattern finder to keep matching logic in one place.
	"""
	try:
		from ..classifier import findKeyResultPatternIndex
	except ImportError:
		from classifier import findKeyResultPatternIndex
	return findKeyResultPatternIndex(tree.mainNodes)


_NOTICE_LANDING_MIN_CHARS = 30


def findNoticeLanding(tree: TreeSummary) -> Optional[int]:
	"""For NOTICE intent: return the index of the status sentence — the
	one the user came here to read (e.g. "The form is no longer accepting
	responses", "Thank you for submitting", "Page not found").

	Strategy: walk document order and return the first meaningful node,
	skipping chrome shapes (a status page's message is never a copyright
	line, a breadcrumb, or a photo credit).

	  1. A substantial paragraph (>= _NOTICE_LANDING_MIN_CHARS, non-chrome)
	     is the message. This is the common case: closed forms and error
	     pages carry the status as a sentence ("This form is no longer
	     accepting responses", "Page not found. Try the homepage."), often
	     under a generic title heading. Landing on the sentence, not the
	     title, is what the user came for.
	  2. A heading is the message ONLY when no status paragraph follows it
	     before the next heading. Some confirmation pages put the whole
	     status in the heading and give the paragraphs to follow-up prompts:
	     WebAIM's survey-confirmation page is H1 "Screen Reader User Survey
	     Completed", then the paragraphs are "share this with others" /
	     "check out our services" — the message is the heading, so the old
	     paragraph-first rule sailed past it to the share prompt. The
	     lookahead is what keeps case 1 intact: a title heading with a
	     status sentence under it still yields to the sentence.

	The previous rule was paragraph-first with headings as a pure fallback,
	which failed both ways — it landed on a breadcrumb before the real
	message, and it could never land on a heading that WAS the message.
	Chrome-skipping plus the "first paragraph in document order" idea (not
	"first paragraph after the first heading") still fixes the original
	bestmidi.com/bg/ case, where the intro sentence precedes any heading.

	Returns None only if tree.mainNodes is empty.
	"""
	nodes = tree.mainNodes
	if not nodes:
		return None

	def _isStatusParagraph(n) -> bool:
		return (
			n.kind == "paragraph"
			and n.textLength >= _NOTICE_LANDING_MIN_CHARS
			and not _isChromeParagraph(n)
		)

	for i, n in enumerate(nodes):
		if _isStatusParagraph(n):
			return i
		if n.kind == "heading":
			# Is this heading merely a title sitting above a status
			# sentence? If a status paragraph appears before the next
			# heading, it is — skip this heading and let that paragraph
			# win. Otherwise the heading itself carries the status.
			headingOwnsStatus = True
			for m in nodes[i + 1:]:
				if m.kind == "heading":
					break
				if _isStatusParagraph(m):
					headingOwnsStatus = False
					break
			if headingOwnsStatus:
				return i

	# Nothing substantial and no heading — anchor on the first node so the
	# caller still has something to speak.
	return 0


def findListLanding(tree: TreeSummary) -> Optional[int]:
	"""For LIST intent: return the index of the first heading in the
	largest same-level heading cluster. That's typically the first story
	headline / search result / video title — the same target a sighted
	person would scan to first on an index page. Moving the cursor there
	makes the page feel "ready to scan" instead of silent.

	Returns None if no heading cluster is identifiable in mainNodes.
	"""
	bestStart = None
	bestSize = 0
	curStart = None
	curSize = 0
	curLevel: Optional[int] = None
	charsSince = 0

	for i, node in enumerate(tree.mainNodes):
		if node.kind == "heading":
			if curLevel == node.level and charsSince <= _HEADING_CLUSTER_MAX_CHARS_BETWEEN:
				curSize += 1
			else:
				curStart = i
				curSize = 1
				curLevel = node.level
			charsSince = 0
			if curSize > bestSize:
				bestSize = curSize
				bestStart = curStart
		elif node.kind == "paragraph":
			charsSince += node.textLength

	return bestStart


_Z_SEQUENCE_MAX_GAP = 30
"""Maximum number of mainNodes between the last Z-sequence landing and the
next eligible heading. Beyond this we treat the next heading as out of the
article body — typically a sidebar widget heading or a related-content rail.
30 covers even long news article subsections; a longer gap is a strong signal
that the cursor has walked off the article and into chrome."""


def findNextContentLanding(
	tree: TreeSummary,
	afterIdx: int,
) -> Optional[int]:
	"""Z-key forward scan: return the index of the next substantial
	content paragraph in mainNodes strictly after `afterIdx`. Skips
	headings (NVDA's H key handles those) and the same chrome paragraphs
	the article-landing cascade skips (tag lists, share-link payloads,
	accessibility instructions, PDF-viewer disclaimers).

	Returns None if no eligible paragraph exists past `afterIdx`. The
	caller speaks a "nothing else to land on" message and leaves the
	cursor where it is.

	This is the Z key's "find me the next interesting thing to read"
	behavior, scanning from wherever the user currently is. It deliberately
	does NOT track or use the previous addon-landing index — Z is meant
	to advance from the user's CURRENT position, not from the last place
	the addon dropped them.
	"""
	for i in range(afterIdx + 1, len(tree.mainNodes)):
		node = tree.mainNodes[i]
		if node.kind != "paragraph":
			continue
		if node.textLength < LANDING_MIN_PARAGRAPH_CHARS:
			continue
		if _isChromeParagraph(node):
			continue
		return i
	# Short-content fallback: on pages where NOTHING clears the 50-char bar
	# anywhere (confirmation / status pages — Zoom's "You have successfully
	# registered" page tops out at a 44-char line), Z would strand the user
	# with "Nothing else to land on" while real content sits right there.
	# Only then, rescan below the cursor with the notice bar (30 chars).
	# Article-class pages (which have 50+ char paragraphs somewhere) keep
	# the strict bar, so end-of-article Z behavior is unchanged.
	if not any(
		n.kind == "paragraph" and n.textLength >= LANDING_MIN_PARAGRAPH_CHARS
		for n in tree.mainNodes
	):
		for i in range(afterIdx + 1, len(tree.mainNodes)):
			node = tree.mainNodes[i]
			if node.kind != "paragraph":
				continue
			if node.textLength < _NOTICE_LANDING_MIN_CHARS:
				continue
			if _isChromeParagraph(node):
				continue
			return i
	return None


def findNextHeadingLanding(
	tree: TreeSummary,
	afterIdx: int,
	maxGap: int = _Z_SEQUENCE_MAX_GAP,
) -> Optional[int]:
	"""Phase 1.5 Z-sequence: return the index of the next heading in
	mainNodes strictly after `afterIdx`, provided it sits within
	`maxGap` nodes. Returns None if there is no further heading OR if
	the next heading is too far away to plausibly belong to the same
	article body (sidebar / related-content territory).

	Used by the multi-press Z behavior: first Z press lands at the page's
	primary landing, subsequent presses advance to the next section
	(next heading) so the user can walk through major sections without
	leaving the add-on's gesture.
	"""
	maxIdx = min(afterIdx + 1 + maxGap, len(tree.mainNodes))
	for i in range(afterIdx + 1, maxIdx):
		if tree.mainNodes[i].kind == "heading":
			return i
	return None


# ---------------------------------------------------------------------------
# Stale-position guard (2026-07-14 soak)
#
# The addon captures a TextInfo per node during the walk and speaks it
# afterwards. On pages that keep hydrating, NVDA rebuilds its virtual buffer
# underneath us and the captured position then points at a DIFFERENT paragraph.
# We choose correctly and read from a stale bookmark. Observed on 7 of 42
# landings, e.g. chose the correct WFAA lede and spoke a Cincinnati Reds sports
# headline; chose a recipe lede and spoke "We're loading your content, stay
# tuned!".
#
# The caller re-expands the captured position and asks whether the buffer still
# holds the paragraph it chose. Lives here (not in __init__.py) so it is pure
# and unit-testable -- a FALSE mismatch would silently kill a GOOD landing, so
# this logic is the last thing that should go untested.
# ---------------------------------------------------------------------------

# How many leading characters must still match. Deliberately lenient: real drift
# is never subtle (a wholly different paragraph), while a false mismatch costs a
# good landing.
LANDING_MATCH_CHARS = 24


def normalizeForMatch(text: str) -> str:
	# Collapse whitespace runs, including the NBSPs news sites litter through
	# their ledes, so cosmetic spacing differences can't read as drift.
	return " ".join((text or "").replace("\xa0", " ").split()).strip()


def landingTextMatches(actualText: str, node) -> bool:
	"""True if the buffer still holds the paragraph the classifier chose.

	``node.textPreview`` is the paragraph's first ~60 chars AT WALK TIME.
	``actualText`` is what the captured position expands to NOW.

	Returns True when there is nothing to compare against: an empty preview is
	not evidence of drift, and this guard must never itself be the reason a page
	goes silent.
	"""
	expected = normalizeForMatch(getattr(node, "textPreview", "") or "")
	actual = normalizeForMatch(actualText)
	if not expected:
		return True
	n = min(len(expected), LANDING_MATCH_CHARS)
	return actual[:n] == expected[:n]
