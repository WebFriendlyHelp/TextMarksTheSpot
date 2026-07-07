# -*- coding: UTF-8 -*-
# Text Marks the Spot — NVDA binding layer for the intent classifier.
#
# Walks NVDA's browse-mode tree and produces a `classifier.TreeSummary`.
# This is the bridge between everything we've designed (pure-Python
# classifier with hand-coded fixtures) and the real accessibility tree.
#
# Read-only. Never moves the cursor, never speaks, never plays tones.
# Per SPEC.md: the trigger module is what kicks off detection; this module
# only inspects.
#
# Runs inside NVDA only. NVDA imports are guarded so this file can be
# imported (but not called) from unit tests on a workstation without NVDA.

from __future__ import annotations

import datetime
import os
import re
import time
from typing import Optional


# Status-keyword regex — matches the most common "go read this one thing"
# phrases on small notice / status pages. Used by the NOTICE classifier to
# boost confidence when the page shape is ambiguous. Case-insensitive,
# whole-word-ish where it matters (no false matches on substrings).
#
# Curated from common patterns: form submission success / failure / closed,
# account / payment / order confirmations, expired sessions, maintenance,
# error / not-found pages.
_NOTICE_PATTERNS = (
	# Confirmations / success
	r"\bthank(?:s| you)\b",
	r"\bsuccessfully\b",
	r"\bwe(?:'ve|\s+have)\s+received\b",
	r"\bcheck your email\b",
	r"\bemail (?:has been )?sent\b",
	r"\b(?:submission|response|order|payment|application|account|booking|reservation|message)\s+"
	r"(?:has been|is)\s+"
	r"(?:received|recorded|submitted|created|confirmed|cancell?ed|completed)\b",
	# Unavailable / closed
	r"\bno longer\s+(?:accepting|available)\b",
	r"\bhas\s+(?:ended|expired|closed)\b",
	r"\bis\s+(?:closed|unavailable)\b",
	r"\bsession\s+(?:has\s+)?expired\b",
	r"\b(?:under\s+)?maintenance\b",
	r"\bwe(?:'ll|\s+will)\s+be\s+(?:right\s+)?back\b",
	r"\bcoming\s+soon\b",
	r"\b(?:service|temporarily)\s+unavailable\b",
	r"\btry again later\b",
	# Errors / not found / soft Google-style errors
	r"\bpage not found\b",
	r"\b404\b",
	r"\baccess denied\b",
	r"\bforbidden\b",
	r"\bsomething went wrong\b",
	r"\bsorry,?\s+(?:we|something|unable|the file|but)\b",
	r"\bunable to\s+(?:open|load|display|find|access|complete|process)\b",
	r"\bwe\s+(?:can'?t|cannot|couldn'?t|could not)\s+(?:find|display|load|open|access|process)\b",
	r"\b(?:not authorized|unauthorized|permission denied)\b",
	r"\b(?:file|page|item|content)\s+(?:not found|unavailable|deleted|removed)\b",
)
_NOTICE_RE = re.compile("|".join(_NOTICE_PATTERNS), re.IGNORECASE)

try:
	import api
	import controlTypes
	import textInfos
	from logHandler import log
	_NVDA_AVAILABLE = True
except ImportError:
	_NVDA_AVAILABLE = False
	# Stub for unit tests outside NVDA.
	class _StubLog:
		def info(self, *a, **k): pass
		def warning(self, *a, **k): pass
	log = _StubLog()

try:
	from .classifier import TreeSummary, MainNode
except ImportError:
	from classifier import TreeSummary, MainNode

# Figure-caption / photo-credit and legal-boilerplate detectors live in the
# landing module so the patterns stay in one unit-tested place. We call them
# here over the FULL chunk text (the trailing credit / "All rights reserved"
# tail is usually past the 60-char preview cutoff) and stash the results on
# each MainNode (is_caption / is_boilerplate).
try:
	from .detection.web import (
		_looks_like_image_caption,
		_looks_like_legal_boilerplate,
		ends_like_sentence,
	)
except ImportError:
	from detection.web import (
		_looks_like_image_caption,
		_looks_like_legal_boilerplate,
		ends_like_sentence,
	)


# Internal: per-summary list of captured textInfo positions, one per entry
# in summary.main_nodes. Keyed by id(summary) so the data lives only as
# long as the summary does. Not on TreeSummary itself because TreeSummary
# is pure data (used by fixture-based unit tests with no real textInfos).
# get_landing_textinfo() reads from here.
_captured_positions: dict = {}


# Caps on the document walk. Real pages can be huge (Wikipedia has thousands
# of paragraph units); the speed budget is <50ms per detection (SPEC). 1000
# nodes is a starting cap — tune after we measure on real pages.
WALK_NODE_LIMIT = 1000

# Text-content roles we treat as paragraph candidates when walking by
# UNIT_PARAGRAPH. Non-content roles get silently skipped so they don't
# pollute the paragraph count.
#
# Interactive-control roles (BUTTON, TOGGLEBUTTON) are filtered here even
# though they may carry substantial text (e.g. AI-generated FAQ question
# buttons stacked above article bodies on news sites — krdo.com's
# "What is the duration of the pothole repair surge in Colorado Springs?"
# button was the canonical case). Those buttons aren't article content
# and shouldn't compete with real paragraphs for the landing.
#
# LINK is NOT filtered: inline links inside article body paragraphs are
# common, and the paragraph containing them is real content. NVDA's
# UNIT_PARAGRAPH walk usually groups inline links with surrounding text,
# so a paragraph-level chunk reporting role=LINK is rare in practice.
_PARAGRAPH_SKIP_ROLES_NAMES = (
	"GRAPHIC", "SEPARATOR", "UNKNOWN",
	"BUTTON", "TOGGLEBUTTON",
)

# Roles that count as a focused editable control for guardrail #6.
_EDITABLE_FOCUS_ROLES_NAMES = (
	"EDITABLETEXT", "COMBOBOX", "LISTBOX",
	"RADIOBUTTON", "CHECKBOX",
)


# Persistent perf log — survives NVDA restarts so we can collect data over
# days and ask a fresh AI session to read it. Lives next to NVDA's own
# data folder. Self-rotates at 1 MB so it never grows without bound.
_PERF_LOG_MAX_BYTES = 1_000_000
_PERF_LOG_PATH_CACHE: Optional[str] = None


def _perf_log_path() -> Optional[str]:
	global _PERF_LOG_PATH_CACHE
	if _PERF_LOG_PATH_CACHE is not None:
		return _PERF_LOG_PATH_CACHE
	appdata = os.environ.get("APPDATA")
	if not appdata:
		return None
	_PERF_LOG_PATH_CACHE = os.path.join(appdata, "nvda", "TextMarksTheSpot-perf.log")
	return _PERF_LOG_PATH_CACHE


def _append_perf_line(line: str) -> None:
	# Append one timestamped line to the persistent perf log. Swallows all
	# IO errors so a locked / unwritable log can never break detection.
	#
	# Only writes when NVDA's logging level is DEBUG. Users in normal
	# operation should not accumulate a perf log file in their AppData;
	# the file is for troubleshooting, and troubleshooting users set
	# NVDA's log level explicitly to capture data.
	import logging
	if not log.isEnabledFor(logging.DEBUG):
		return
	path = _perf_log_path()
	if path is None:
		return
	try:
		try:
			if os.path.getsize(path) > _PERF_LOG_MAX_BYTES:
				rotated = path + ".old"
				try:
					os.remove(rotated)
				except OSError:
					pass
				os.rename(path, rotated)
		except OSError:
			pass  # file doesn't exist yet, or rotation race — both fine
		ts = datetime.datetime.now().isoformat(timespec="seconds")
		with open(path, "a", encoding="utf-8") as fh:
			fh.write(f"{ts} {line}\n")
	except Exception:
		pass


def build_tree_summary(treeInterceptor) -> TreeSummary:
	"""Inspect the browse-mode tree and produce a TreeSummary for the
	classifier. Read-only. Returns an empty TreeSummary if the interceptor
	is None or unusable.

	Scoping: when a <main> landmark is present, all counts and node walking
	are filtered to nodes inside <main>. When no <main> exists, nodes inside
	chrome landmarks (navigation, banner, contentinfo, complementary, search)
	are excluded instead. This matches what a sighted person sees as "the
	page content" rather than the full document.
	"""
	if not _NVDA_AVAILABLE:
		raise RuntimeError(
			"tree_summary requires NVDA — not available outside the NVDA runtime",
		)
	if treeInterceptor is None or treeInterceptor.rootNVDAObject is None:
		return TreeSummary()

	t0 = time.monotonic()
	main_obj, main_range = _find_main_landmark(treeInterceptor)
	t1 = time.monotonic()
	# Cache _in_scope decisions across all helpers within this single
	# build_tree_summary call. id(obj) → bool. Discarded on return.
	# Only the identity-based fallback paths use it now.
	scope_cache: dict = {}

	summary = TreeSummary()
	summary.url = _get_document_url(treeInterceptor)
	summary.focused_control_is_editable = _is_focus_editable()
	summary.has_main_landmark = main_obj is not None
	# Classifier thresholds: ARTICLE_DEMOTE_TO_LIST_AT=3, STRONG_FORM_INPUT_COUNT=5
	# (form confidence caps near 10), APP_CONTROL_FLOOR=10. We cap each count
	# slightly above the largest threshold the classifier consults.
	_ARTICLE_LIMIT = 4
	_FORM_LIMIT = 10
	_INTERACTIVE_LIMIT = 11

	# Scope selection, ONE range for both counts and walk so the summary
	# is internally consistent (previously the counts could be scoped to a
	# <main> the identity check couldn't confirm — coming back 0/0/0 —
	# while main_nodes fell back to unscoped: the classifier then saw a
	# 7-input form as having no form fields at all).
	#   main-pos:  <main> present and its positional range built (fast path)
	#   main-id:   <main> present, no usable range → identity checks (old path)
	#   article:   no <main>, exactly one <article> → positional article range
	#   chrome:    no <main>, no single article → identity chrome filter
	scope_range = main_range
	scope_kind = "main-pos" if main_range is not None else ("main-id" if main_obj is not None else "chrome")

	# Article count first — the article-scope decision below needs it.
	if scope_range is not None:
		summary.article_count = _count_in_range(treeInterceptor, "article", scope_range, limit=_ARTICLE_LIMIT)
	else:
		summary.article_count = _count_in_scope(treeInterceptor, "article", main_obj, scope_cache, limit=_ARTICLE_LIMIT)
	if main_obj is None and summary.article_count == 1:
		article_range = _single_article_scope_range(treeInterceptor)
		if article_range is not None:
			scope_range = article_range
			scope_kind = "article"

	if scope_range is not None:
		summary.form_input_count = _count_in_range(treeInterceptor, "formField", scope_range, limit=_FORM_LIMIT)
	else:
		summary.form_input_count = _count_in_scope(treeInterceptor, "formField", main_obj, scope_cache, limit=_FORM_LIMIT)
	# Interactive subtypes ordered most-common first so the running-sum
	# short-circuit usually triggers on the first one or two enumerations
	# (link-heavy pages dominate). Each per-type call also caps at the
	# running headroom so it can't overshoot the global cap.
	running = 0
	for t in ("link", "button", "edit", "comboBox", "checkBox", "radioButton"):
		remaining = _INTERACTIVE_LIMIT - running
		if remaining <= 0:
			break
		if scope_range is not None:
			running += _count_in_range(treeInterceptor, t, scope_range, limit=remaining)
		else:
			running += _count_in_scope(treeInterceptor, t, main_obj, scope_cache, limit=remaining)
	summary.interactive_control_count = running
	t2 = time.monotonic()
	positions: list = []
	# Single-element flag the walker flips on first regex match. List used
	# as a mutable container so nested helpers can update it.
	notice_match = [False]
	# Mutable raw-count container so we can log raw_seen on EVERY walk,
	# not just empty ones (existing walk-empty log only fires when result
	# is empty — leaves us blind on slow non-empty walks).
	raw_count = [0]
	summary.main_nodes = _walk_main_nodes(treeInterceptor, main_obj, scope_cache, positions, notice_match, raw_count, scope_range)
	t3 = time.monotonic()
	fallback_ran = False
	fallback_raw_count = [0]
	# Fallback: if the scoped walk produced zero nodes, skip the
	# chrome-filtered intermediate walk and go straight to unscoped.
	#
	# Why skip chrome-filtered: it uses the SAME parent-chain walk we
	# just used (just looking for landmark-type matches instead of
	# main_obj identity). If the parent walk couldn't find main_obj
	# reliably (which is what's wrong on Calendar, webaim.org/projects/
	# million, etc. — see CLAUDE.md "Known limitations"), it almost
	# certainly can't find chrome landmarks reliably either. The
	# chrome-filtered fallback would visit all chunks again at the same
	# cost as the failed walk and return empty 90% of the time.
	#
	# Doubling detection time on a 400-node page (~4 s → ~8 s) for a
	# fallback that rarely succeeds is a bad trade. Unscoped reliably
	# produces usable content; the classifier and landing finders handle
	# the noise (nav and footer text getting through) better than they
	# handle an empty walk result.
	counts_rescoped = False
	if not summary.main_nodes:
		fallback_ran = True
		positions.clear()
		summary.main_nodes = _walk_main_nodes(treeInterceptor, _UNSCOPED_SENTINEL, {}, positions, notice_match, fallback_raw_count)
		# Consistency: main_nodes now describe the WHOLE document. If the
		# scoped counts came back all-zero (the scope was clearly bogus —
		# Zoom counted 0 forms on a 7-input page), recount document-wide so
		# the classifier sees the same tree the nodes came from. Cheap:
		# scope_range=None means a capped enumeration with no per-item
		# work. Non-zero scoped counts are kept — they carry real signal
		# and unscoped recounting would inflate them with chrome controls.
		if (
			summary.article_count == 0
			and summary.form_input_count == 0
			and summary.interactive_control_count == 0
		):
			counts_rescoped = True
			summary.article_count = _count_in_range(treeInterceptor, "article", None, limit=_ARTICLE_LIMIT)
			summary.form_input_count = _count_in_range(treeInterceptor, "formField", None, limit=_FORM_LIMIT)
			running = 0
			for t in ("link", "button", "edit", "comboBox", "checkBox", "radioButton"):
				remaining = _INTERACTIVE_LIMIT - running
				if remaining <= 0:
					break
				running += _count_in_range(treeInterceptor, t, None, limit=remaining)
			summary.interactive_control_count = running
		scope_kind = "unscoped-recount" if counts_rescoped else "unscoped"
	t4 = time.monotonic()
	# The tree is trustworthy (chrome-free) for the LANDING FINDERS only in
	# the single-<article> positional case — deliberately NOT for main-pos:
	# sites commonly put deks/bylines/disclaimers inside <main> before the
	# H1, and the defensive hero/cluster landing gates exist for exactly
	# those. Loosening them for every <main> page would regress landings
	# (PCMag's pre-H1 disclaimer was the canonical case).
	summary.positionally_scoped = scope_kind == "article" and not fallback_ran
	summary.notice_keyword_match = notice_match[0]
	_captured_positions[id(summary)] = positions
	perf_line = (
		f"[TMTS perf] total={(t4-t0)*1000:.0f}ms "
		f"find_main={(t1-t0)*1000:.0f}ms "
		f"counts={(t2-t1)*1000:.0f}ms "
		f"walk={(t3-t2)*1000:.0f}ms "
		f"fallback={(t4-t3)*1000:.0f}ms (ran={fallback_ran}) "
		f"raw_seen={raw_count[0]} fb_raw_seen={fallback_raw_count[0]} "
		f"main_nodes={len(summary.main_nodes)} has_main={summary.has_main_landmark} scope={scope_kind} "
		f"article={summary.article_count} forms={summary.form_input_count} "
		f"interactive={summary.interactive_control_count} url={summary.url!r}"
	)
	log.debug(perf_line)
	_append_perf_line(perf_line)
	return summary


def get_landing_textinfo(summary, index: int):
	"""Return the textInfo captured at main_nodes[index] during the walk,
	or None if no capture exists. The returned textInfo is collapsed to
	the START of the paragraph so .updateCaret() lands at the beginning.
	"""
	positions = _captured_positions.get(id(summary), ())
	if 0 <= index < len(positions):
		return positions[index]
	return None


def release_summary(summary) -> None:
	"""Drop captured positions for a summary we're done with."""
	_captured_positions.pop(id(summary), None)


# ---------------------------------------------------------------------------
# URL
# ---------------------------------------------------------------------------

def _get_document_url(treeInterceptor) -> str:
	# documentConstantIdentifier is the most stable URL accessor on
	# browse-mode tree interceptors. On non-web interceptors (e.g., desktop
	# email clients) it may be empty or a non-URL identifier — that's fine,
	# the URL-hint matching is just a tiebreaker.
	try:
		url = getattr(treeInterceptor, "documentConstantIdentifier", "") or ""
		return str(url)
	except Exception:
		return ""


# ---------------------------------------------------------------------------
# Guardrail #6 — is focus already on an editable form control?
# ---------------------------------------------------------------------------

def is_focus_editable() -> bool:
	"""Public wrapper around _is_focus_editable so the trigger can check
	this BEFORE building a full tree summary or playing any feedback tone.
	On pages that auto-focus a search box (e.g. duckduckgo.com), we must
	stay completely silent — no working tone, no pulse, no work."""
	return _is_focus_editable()


def set_focus_on_first_form_input(treeInterceptor) -> bool:
	"""For FORM intent: move keyboard focus to the first form input found
	in document order. Triggers NVDA's own focus speech (field name +
	role + value) — which works regardless of whether the user is in
	browse or focus mode. Returns True if focus was set.

	This is more aggressive than moving the browse cursor: it overrides
	whatever the page auto-focused (e.g. Google Forms snapping to its
	own first field, which may differ from the first form input in
	document order). The trade-off is intentional — the user explicitly
	asked to land on "the box itself" rather than the page title.
	"""
	if not _NVDA_AVAILABLE or treeInterceptor is None:
		return False
	# Positional main-range filter: the old version focused the FIRST
	# formField in the whole document, which on Zoom's registration page
	# was the language-picker combobox in the page header ("Language
	# English") — chrome, not the form. Fields outside <main> are never
	# the form the user came for. Also prefer real EDIT boxes over the
	# broader formField quick-nav class (which includes buttons and
	# pickers): "the first named box" means a text field when one exists.
	_, main_range = _find_main_landmark(treeInterceptor)

	def _in_main(item) -> bool:
		if main_range is None:
			return True
		ti = getattr(item, "textInfo", None)
		if ti is None:
			return True
		try:
			return (
				ti.compareEndPoints(main_range, "startToStart") >= 0
				and ti.compareEndPoints(main_range, "startToEnd") < 0
			)
		except Exception:
			return True

	for item_type in ("edit", "formField"):
		try:
			for item in treeInterceptor._iterNodesByType(item_type):
				if not _in_main(item):
					continue
				obj = getattr(item, "obj", None)
				if obj is None:
					continue
				try:
					obj.setFocus()
					return True
				except Exception:
					continue
		except Exception:
			continue
	return False


def _is_focus_editable() -> bool:
	try:
		focus = api.getFocusObject()
	except Exception:
		return False
	if focus is None:
		return False

	# Role check
	role_name = getattr(focus.role, "name", None) or str(focus.role)
	if role_name in _EDITABLE_FOCUS_ROLES_NAMES:
		return True

	# State check — contenteditable / role=textbox surfaces via STATE_EDITABLE
	try:
		if controlTypes.State.EDITABLE in focus.states:
			return True
	except Exception:
		pass

	return False


# ---------------------------------------------------------------------------
# Landmark and structural counts
# ---------------------------------------------------------------------------

_CHROME_LANDMARK_TYPES = frozenset({
	"navigation", "banner", "contentinfo", "complementary", "search",
})

_PARENT_WALK_MAX_DEPTH = 30  # safety cap for parent-chain walks


def _landmark_type(obj) -> str:
	# Returns the landmark type for obj (e.g. "main", "navigation"), or "".
	lm = getattr(obj, "landmark", None) or getattr(obj, "landmarkType", None) or ""
	return str(lm).lower() if lm else ""


def _find_main_landmark(treeInterceptor):
	"""Return (main_obj, main_range) for the first <main> landmark, or
	(None, None). One enumeration finds both.

	main_range is the landmark quick-nav item's own textInfo — the same
	positional-scoping trick proven for the single-<article> case: ranges
	built by the tree interceptor share the walk's coordinate space, so
	compareEndPoints is meaningful (obj.makeTextInfo does NOT — see
	_single_article_scope_range). A usable range lets both the counts and
	the walk decide "inside <main>?" by position — reliable where the
	identity-based parent-chain check silently fails (Calendar, Zoom), and
	FAST: a buffer-offset comparison per item instead of a COM parent
	chain per item. The parent chains were the dominant detection cost
	(~1 s on Zoom's 44-node page, 12.4 s on judysdogblog).
	"""
	try:
		for item in treeInterceptor._iterNodesByType("landmark"):
			obj = getattr(item, "obj", None)
			if obj is None:
				continue
			if _landmark_type(obj) != "main":
				continue
			rng = getattr(item, "textInfo", None)
			if rng is None:
				try:
					rng = treeInterceptor.makeTextInfo(obj)
				except Exception:
					rng = None
			if rng is not None:
				try:
					rng = rng.copy()
				except Exception:
					pass
			return obj, rng
	except Exception:
		pass
	return None, None


def _single_article_scope_range(treeInterceptor):
	"""Return a TextInfo spanning the single <article> element, or None.

	Used for POSITIONAL scoping when the document has no <main> landmark but
	exactly one <article> (common on blog/news themes). The identity-based
	chrome filter fails to exclude nav/comments/footer on many such themes
	(see CLAUDE.md "Known limitations" — NVDA hands back different object
	instances for the same logical landmark, so the parent-chain check
	misses). An article's text range, by contrast, is stable: the nav lives
	before it and comments/footer/sidebar live after it, so a position test
	cleanly separates post body from chrome.

	Returns None when there isn't exactly one article, or the range can't be
	built — caller then falls back to the identity-based chrome filter.
	"""
	try:
		found = None
		for item in treeInterceptor._iterNodesByType("article"):
			# Prefer the quick-nav item's own textInfo: the tree interceptor
			# built it in the SAME coordinate space as the walk's positions,
			# so compareEndPoints is meaningful. obj.makeTextInfo() does NOT
			# share that space in browse mode (it builds a range against the
			# object, not the virtual buffer) and matched nothing — that's the
			# documented "makeTextInfo can be more restrictive than expected"
			# trap. Fall back to treeInterceptor.makeTextInfo(obj) only if the
			# item exposes no textInfo.
			ti = getattr(item, "textInfo", None)
			if ti is None:
				obj = getattr(item, "obj", None)
				if obj is not None:
					try:
						ti = treeInterceptor.makeTextInfo(obj)
					except Exception:
						ti = None
			if ti is None:
				continue
			if found is not None:
				# More than one <article> (e.g. related-post cards). Ambiguous
				# which is the post body — skip positional scoping.
				return None
			found = ti
		if found is None:
			return None
		rng = found.copy()
		try:
			log.debug(f"[TMTS scope] article range chars={len(rng.text or '')}")
		except Exception:
			pass
		return rng
	except Exception:
		return None


_UNSCOPED_SENTINEL = "__unscoped__"


def _in_scope(obj, main_obj, cache: dict) -> bool:
	# Decide whether obj is "page content" for classification purposes.
	# If main_obj is set: obj must be inside the main landmark.
	# If no main landmark: obj must NOT be inside a chrome landmark.
	# Walks obj.parent up to _PARENT_WALK_MAX_DEPTH ancestors.
	# `cache` is a {id(obj): bool} dict scoped to one build_tree_summary
	# call; all ancestors visited during the walk are cached with the
	# final decision, so subsequent siblings short-circuit immediately.
	if obj is None:
		return False
	# Unscoped sentinel: accept everything. Used as the last-resort fallback
	# on pages where both main-scoped and chrome-filtered walks produce no
	# nodes (e.g., themes that wrap the article body in role="complementary").
	if main_obj is _UNSCOPED_SENTINEL:
		return True
	key = id(obj)
	if key in cache:
		return cache[key]

	visited = []
	cur = obj
	result = None
	for _ in range(_PARENT_WALK_MAX_DEPTH):
		if cur is None:
			break
		ckey = id(cur)
		if ckey in cache:
			result = cache[ckey]
			break
		visited.append(ckey)
		if main_obj is not None:
			if cur is main_obj or cur == main_obj:
				result = True
				break
		else:
			lm = _landmark_type(cur)
			if lm == "main":
				result = True
				break
			if lm in _CHROME_LANDMARK_TYPES:
				result = False
				break
		try:
			cur = cur.parent
		except Exception:
			break

	if result is None:
		# main_obj set and never reached → not in main → out of scope.
		# No main_obj and never hit a chrome landmark → in scope.
		result = main_obj is None

	for vkey in visited:
		cache[vkey] = result
	return result


def _count_in_scope(treeInterceptor, item_type: str, main_obj, cache: dict, limit: int = 0) -> int:
	# Count quick-nav items of item_type that pass _in_scope. If `limit` is
	# positive, return as soon as count reaches it — the classifier only
	# compares counts against fixed thresholds (e.g. APP_CONTROL_FLOOR=10),
	# so anything above the largest threshold is wasted precision and an
	# expensive parent-walk for nothing. Saves hundreds of _in_scope calls
	# on heavy pages with many links.
	try:
		count = 0
		for item in treeInterceptor._iterNodesByType(item_type):
			obj = getattr(item, "obj", None)
			if obj is not None and _in_scope(obj, main_obj, cache):
				count += 1
				if limit and count >= limit:
					return count
		return count
	except Exception:
		return 0


# Hard cap on quick-nav items SCANNED per count enumeration. The classifier
# only compares counts against small fixed thresholds; on a page with
# thousands of links, scanning past a few hundred items buys nothing.
_COUNT_SCAN_LIMIT = 300


def _count_in_range(treeInterceptor, item_type: str, scope_range, limit: int = 0) -> int:
	"""Count quick-nav items of item_type POSITIONALLY: an item counts when
	its range STARTS inside scope_range. With scope_range=None, counts the
	whole document. No parent-chain walks — a buffer-offset comparison per
	item — so this is orders of magnitude cheaper than _count_in_scope and
	immune to the identity-check failure that made counts come back 0 on
	pages with a perfectly real <main> (Zoom registration: forms=0 on a
	7-input form).

	Items that expose no textInfo are counted as in scope (inclusive bias:
	the classifier's FORM/APP gates are guarded by content signals anyway).
	"""
	try:
		count = 0
		scanned = 0
		for item in treeInterceptor._iterNodesByType(item_type):
			scanned += 1
			if scanned > _COUNT_SCAN_LIMIT:
				break
			if scope_range is not None:
				ti = getattr(item, "textInfo", None)
				if ti is not None:
					try:
						if not (
							ti.compareEndPoints(scope_range, "startToStart") >= 0
							and ti.compareEndPoints(scope_range, "startToEnd") < 0
						):
							continue
					except Exception:
						pass
			count += 1
			if limit and count >= limit:
				return count
		return count
	except Exception:
		return 0


# ---------------------------------------------------------------------------
# Document walk — produce the interleaved heading + paragraph node list.
# ---------------------------------------------------------------------------

# Early-exit the whole-document walk after this many consecutive
# out-of-scope nodes. Bounded walking (starting at main_obj's first
# position) was tried and produced too few nodes on real pages — NVDA's
# main_obj.makeTextInfo can be more restrictive than expected. Walking
# the whole doc and filtering is more reliable; this just bails once
# we've clearly walked off the end of main into the footer.
_OUT_OF_SCOPE_TOLERANCE = 50


def _walk_main_nodes(treeInterceptor, main_obj, cache: dict, positions_out: list, notice_match_out: Optional[list] = None, raw_count_out: Optional[list] = None, scope_range=None) -> list[MainNode]:
	# Walk the whole document by UNIT_PARAGRAPH; emit only nodes that
	# pass _in_scope (inside <main> if present, or outside chrome
	# landmarks if not). Bail out once we've had _OUT_OF_SCOPE_TOLERANCE
	# consecutive out-of-scope nodes (most likely we're in the footer).
	#
	# notice_match_out (optional, single-element list): the walker flips
	# its first element to True the first time it sees a chunk of text
	# matching the status-keyword regex. Used by the NOTICE classifier.
	result: list[MainNode] = []
	try:
		info = treeInterceptor.makeTextInfo(textInfos.POSITION_FIRST)
	except Exception:
		return result

	consecutive_out = 0
	have_seen_in_scope = False
	# Diagnostic counters (only used when result is empty at end of walk).
	raw_seen = 0
	raw_with_obj = 0
	raw_with_text = 0
	# Diagnostic: previews of chunks the scope filter dropped AFTER the
	# scoped region had started producing nodes. Mid-region drops are
	# anomalies (containment is positionally monotonic), so if a paragraph
	# the user expected goes missing, this line says whether the scope
	# filter ate it or NVDA's walk never yielded it at all.
	dropped_after_start: list = []
	# Start position of the previously processed chunk, for the forward-
	# progress check below.
	prev_start = None
	for _ in range(WALK_NODE_LIMIT):
		try:
			info.expand(textInfos.UNIT_PARAGRAPH)
			# Forward-progress guard. The old loop unconditionally did
			# collapse(end=True) + move(UNIT_PARAGRAPH, 1) after every
			# chunk. When a chunk's end offset lands EXACTLY on the next
			# paragraph's start boundary (common after link/image-heavy
			# blocks — pattysworlds' welcome heading with an inline logo
			# image), that pair advances TWO paragraphs and silently skips
			# one ("Watch your step..." was never walked; same signature as
			# the missing main-tweet text on X). Now we expand directly at
			# the collapsed end position and only force a move when the
			# expansion made no forward progress.
			if prev_start is not None:
				try:
					progressed = info.compareEndPoints(prev_start, "startToStart") > 0
				except Exception:
					progressed = True
				if not progressed:
					info.collapse()
					if not info.move(textInfos.UNIT_PARAGRAPH, 1):
						break
					continue
			try:
				bookmark = info.copy()
				bookmark.collapse()
				prev_start = bookmark
			except Exception:
				prev_start = None
			text = info.text or ""
			obj = info.NVDAObjectAtStart
			raw_seen += 1
			if obj is not None:
				raw_with_obj += 1
			if text.strip():
				raw_with_text += 1

			if scope_range is not None:
				# Positional containment: keep the chunk only if it falls
				# inside the article's range. Stable across accesses, unlike
				# the parent-chain identity check. Fall back to the identity
				# filter only if the comparison itself errors.
				try:
					in_scope = (
						info.compareEndPoints(scope_range, "startToStart") >= 0
						and info.compareEndPoints(scope_range, "endToEnd") <= 0
					)
				except Exception:
					in_scope = obj is None or _in_scope(obj, main_obj, cache)
			else:
				in_scope = obj is None or _in_scope(obj, main_obj, cache)
			if in_scope:
				consecutive_out = 0
				have_seen_in_scope = True
				node = _node_for(obj, text)
				if node is not None:
					result.append(node)
					# Run the notice-keyword regex against the FULL text
					# (text_preview is truncated). Stops at the first hit.
					if (
						notice_match_out is not None
						and not notice_match_out[0]
						and text
						and _NOTICE_RE.search(text)
					):
						notice_match_out[0] = True
					# Capture a collapsed-to-start position parallel to
					# main_nodes so get_landing_textinfo can move the
					# caret there later without a second walk.
					try:
						pos = info.copy()
						pos.collapse()
						positions_out.append(pos)
					except Exception:
						positions_out.append(None)
			else:
				consecutive_out += 1
				if have_seen_in_scope and len(dropped_after_start) < 10 and text.strip():
					dropped_after_start.append(text.strip()[:40])
				# Only bail AFTER we've seen at least one in-scope node;
				# otherwise we might quit before reaching main (the nav/
				# banner at the top of the document can easily exceed
				# the tolerance before main starts).
				if have_seen_in_scope and consecutive_out > _OUT_OF_SCOPE_TOLERANCE:
					break

			# No unconditional move here — the next iteration expands at
			# this collapsed end position, and the progress guard at the
			# top forces a move only when that fails to advance.
			info.collapse(end=True)
		except Exception:
			break

	if dropped_after_start:
		log.debug(
			f"[TMTS walk-drops] {len(dropped_after_start)} chunk(s) dropped by the "
			f"scope filter after the scoped region started: {dropped_after_start}"
		)

	if raw_count_out is not None:
		raw_count_out[0] = raw_seen
	# If we produced nothing, log raw-walk diagnostics so we can tell
	# WHY the walk failed: did it visit no chunks at all, did it visit
	# chunks but they had no obj/text, or did everything filter out?
	if not result:
		log.debug(
			f"[TMTS walk-empty] raw_seen={raw_seen} raw_with_obj={raw_with_obj} "
			f"raw_with_text={raw_with_text} main_obj_set={main_obj is not None}"
		)
	return result


def _node_for(obj, text: str) -> Optional[MainNode]:
	# Classify the current chunk as heading, paragraph, or skip. Returns
	# None to mean "skip" (don't add to the node list).
	if obj is None:
		stripped = text.strip()
		if not stripped:
			return None
		return MainNode(
			kind="paragraph",
			text_length=len(stripped),
			text_preview=stripped[:60],
			is_caption=_looks_like_image_caption(stripped),
			is_boilerplate=_looks_like_legal_boilerplate(stripped),
			ends_sentence=ends_like_sentence(stripped),
		)

	role_name = getattr(obj.role, "name", None) or str(obj.role)

	if role_name == "HEADING":
		level = _heading_level(obj)
		return MainNode(
			kind="heading",
			level=level,
			text_length=len(text),
			text_preview=text[:60],
		)

	if role_name in _PARAGRAPH_SKIP_ROLES_NAMES:
		return None

	stripped = text.strip()
	if not stripped:
		return None
	return MainNode(
		kind="paragraph",
		text_length=len(stripped),
		text_preview=stripped[:60],
		is_caption=_looks_like_image_caption(stripped),
		is_boilerplate=_looks_like_legal_boilerplate(stripped),
		ends_sentence=ends_like_sentence(stripped),
	)


def _heading_level(obj) -> int:
	# NVDA exposes heading level on a `level` attribute for browse-mode
	# heading objects. Some legacy paths use `headingLevel` or IA2 attribute
	# 'level'. Try in order.
	for attr in ("level", "headingLevel"):
		value = getattr(obj, attr, None)
		if isinstance(value, int) and value > 0:
			return value
	try:
		ia2 = getattr(obj, "IA2Attributes", None) or {}
		raw = ia2.get("level")
		if raw is not None:
			return int(raw)
	except (TypeError, ValueError):
		pass
	return 0


