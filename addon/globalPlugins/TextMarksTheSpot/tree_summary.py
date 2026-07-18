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
		def debug(self, *a, **k): pass
		def info(self, *a, **k): pass
		def warning(self, *a, **k): pass
		def exception(self, *a, **k): pass
		# Mirrors logging.Logger so code guarded by a level check (the perf
		# log writer) runs unchanged under the unit tests. Answering False
		# also keeps tests from touching the real perf log on disk.
		def isEnabledFor(self, level): return False
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
# in summary.main_nodes. Keyed by id(summary). Not on TreeSummary itself
# because TreeSummary is pure data (used by fixture-based unit tests with no
# real textInfos). get_landing_textinfo() reads from here.
#
# This is id()-keyed like the old _in_scope cache was, but it is NOT exposed
# to the address-recycling bug that one had (see _in_scope), and the reason
# is worth stating so nobody "fixes" it by analogy: every entry is WRITTEN
# during its own summary's build, before any read of it can happen, so a
# recycled address is always overwritten with the current summary's own
# positions first. Reads only ever happen for a LIVE summary, whose address
# cannot collide with another live object. The residual risk is a leak (held
# TextInfos) if a caller forgets release_summary, never a wrong answer.
_captured_positions: dict = {}


# Caps on the document walk. Real pages can be huge (Wikipedia has thousands
# of paragraph units). The walk runs on NVDA's MAIN THREAD, so every
# millisecond here is a millisecond NVDA is frozen.
#
# The old cap was 1000 nodes with no time limit, and the comment said "tune
# after we measure on real pages." We measured (perf log, 2026-07-01..14):
#
#   biblegateway.com Isaiah 51-66   936 chunks   6261ms   (~6.7ms/chunk)
#   nlsbard.loc.gov search results 1000 chunks   6861ms   (~6.9ms/chunk)
#   github.com (long README)        742 chunks   6120ms   (~8.2ms/chunk)
#   toptechtidbits newsletter       845 chunks   5438ms   (~6.4ms/chunk)
#
# So 1000 nodes is a ~7 SECOND main-thread freeze, and the node cap alone
# can't bound it because per-chunk cost varies by a factor of ~2 across
# sites. The wall-clock deadline is the real guard; the node cap is a
# backstop for the (hypothetical) page with very cheap chunks.
#
# Truncating is safe for our purpose: we need enough of the top of the
# document to pick a landing, not the whole document.
#
# The NODE CAP IS A BACKSTOP ONLY. The wall-clock budget below is what
# bounds the freeze; this exists solely so a page of pathologically cheap
# chunks can't spin forever under the time limit. It must stay high enough
# that it NEVER binds before the clock does.
#
# It was briefly set to 400 and that was a mistake, caught in soak testing
# the same day. This cap counts RAW CHUNKS WALKED, not content nodes KEPT,
# and on a chrome-heavy tree most raw chunks get filtered out: GitHub's repo
# page turned 400 raw chunks into just 195 in-scope nodes, which starved the
# walk before it ever reached the README (the landing paragraph sits around
# node 201). The page then landed on a commit message. Meanwhile GitHub
# walks at ~4ms/chunk, so the 2s clock had not come close to firing — the
# backstop was doing the truncating and the real guard was idle. Keep this
# generous and let the clock govern.
WALK_NODE_LIMIT = 1000

# Wall-clock ceiling for the walk, in seconds. SPEC's aspirational budget is
# 50ms; that is not reachable through NVDA's UNIT_PARAGRAPH walk on a real
# document, and pretending otherwise is how we ended up with no time limit
# at all.
#
# Was 1.5s, raised to 2.0s on the same day after soak-testing found the
# margin too thin. The binding case is a page whose CONTENT STARTS DEEP:
# github.com/Community-Access/accessibility-agents front-loads ~200 nodes of
# chrome (fork/branch/tag counts, the file browser, commit messages) before
# the README's prose, and the landing came in at main_nodes[201] of the 226
# we had kept when the 1.5s budget cut the walk. About 25 nodes of headroom.
#
# That is the failure mode this whole mechanism can introduce: truncate
# before the content starts and we return no landing at all, which sounds
# EXACTLY like a page with nothing on it (two low beeps). A page that used
# to work would silently stop working. 1.5s was tuned against BibleGateway
# and a long newsletter, where content starts at the top; it did not have a
# deep-content page in its sample. 2.0s still holds the freeze to roughly a
# third of the old 6.1s on that same page, and half a second is a cheap
# price for not losing landings on GitHub-shaped trees.
WALK_TIME_BUDGET_SEC = 2.0

# A walk at or above this gets its per-call-site breakdown written to the
# PERSISTENT perf log ([TMTS walk-phase]); faster walks log to the session log
# only. Half the budget: high enough that ordinary pages (the log's median
# total is ~400 ms for the WHOLE detection) never write a second line, low
# enough to catch a page heading for truncation, not just one that got there.
_WALK_PHASE_LOG_THRESHOLD_SEC = 1.0

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
	landmarks = _find_main_landmark(treeInterceptor)
	main_obj, main_range = landmarks.main_obj, landmarks.main_range
	t1 = time.monotonic()
	# Cache _in_scope decisions across all helpers within this single
	# build_tree_summary call. id(obj) → (obj, bool). Discarded on return.
	# Only the identity-based fallback paths use it now.
	scope_cache: dict = {}

	summary = TreeSummary()
	summary.url = _get_document_url(treeInterceptor)
	summary.focused_control_is_editable = _is_focus_editable()
	summary.has_main_landmark = main_obj is not None
	# Classifier thresholds: ARTICLE_DEMOTE_TO_LIST_AT=3, STRONG_FORM_INPUT_COUNT=4
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
	#   chrome-pos: no <main>, ordered scan with a trust boundary → exclude
	#              the chrome landmark ranges by START position before the
	#              boundary, outside untrusted_ranges. This is the path that
	#              removes the parent chains, which are measurably the whole
	#              cost here: 1887 ms of a 2041 ms walk on stevequayle.com,
	#              275 parent dereferences for 19 chunks, and the walk
	#              truncating with too few nodes to classify anything.
	#   chrome:    no <main> and nothing to bound trust with → identity
	#              chrome filter, the old per-chunk parent walk.
	#
	# NOTE for anyone reading an older copy of this comment: it used to say
	# positional chrome scoping "was built and then SHELVED — the safety
	# interlock it needs cannot be implemented". That was true of the FIRST
	# design (branch `chrome-pos-attempt`, which gated on whether the landmark
	# enumeration completed — unobservable). It is not true of this one, which
	# never asks whether the scan finished, only how far it got. See
	# _select_scope.
	scope_kind, scope_range, chrome_exclude, trust_boundary, untrusted_ranges = _select_scope(landmarks)

	# ONE wall-clock deadline for the whole counts phase (article + form
	# inputs + interactive), checked per item inside every enumeration —
	# see the comment on _COUNT_TIME_BUDGET_SEC for the krdo/stackoverflow
	# incidents that made this necessary. counts_truncated records whether
	# any budget or scan cap fired: truncated counts are UNDERCOUNTS, which
	# is fail-safe for FORM/APP (they fire on large counts) but poison for
	# NOTICE/KEY_RESULT (they fire on small ones) — the classifier consults
	# the flag to keep truncation from manufacturing those intents.
	counts_deadline = time.monotonic() + _COUNT_TIME_BUDGET_SEC
	counts_truncated = [False]
	# The article count gets its OWN truncation flag on top of the shared
	# one: an untrusted article count is the one undercount that is NOT
	# fail-safe. article_count==0 is what drops the has_editorial_content
	# FORM block, and FORM is the branch that moves keyboard focus — the
	# deadline-order argument below covers deadline exhaustion, but the
	# 300-item scan cap (or an iterator exception) can zero the article
	# count WITH time remaining, letting the form count still reach its
	# threshold. The classifier treats a truncated article count as
	# "editorial content unknown" and blocks FORM (same URL escape hatch
	# as a present <article>).
	article_truncated = [False]

	# Article count first — the article-scope decision below needs it, and
	# the ORDER is load-bearing for the fail-safe argument: if the article
	# count is ever truncated to 0 by the DEADLINE (dropping the
	# has_editorial_content FORM block), the budget is by then exhausted,
	# so the form count that follows breaks at its first item and comes
	# back too small to clear FORM_INPUT_THRESHOLD anyway. Moving the form
	# count first would break that implicit guarantee. (Scan-cap and
	# exception truncation leave time on the clock — article_truncated
	# covers those.)
	if scope_range is not None:
		summary.article_count = _count_in_range(treeInterceptor, "article", scope_range, limit=_ARTICLE_LIMIT, deadline=counts_deadline, truncated_out=article_truncated)
	else:
		summary.article_count = _count_in_scope(treeInterceptor, "article", main_obj, scope_cache, limit=_ARTICLE_LIMIT, deadline=counts_deadline, truncated_out=article_truncated)
	if article_truncated[0]:
		counts_truncated[0] = True
	if main_obj is None and summary.article_count == 1:
		article_range = _single_article_scope_range(treeInterceptor, deadline=counts_deadline)
		if article_range is not None:
			scope_range = article_range
			scope_kind = "article"

	summary.form_input_count = _count_form_inputs(
		treeInterceptor, scope_range, main_obj, scope_cache, _FORM_LIMIT,
		deadline=counts_deadline, truncated_out=counts_truncated,
	)
	# Interactive subtypes ordered most-common first so the running-sum
	# short-circuit usually triggers on the first one or two enumerations
	# (link-heavy pages dominate). Each per-type call also caps at the
	# running headroom so it can't overshoot the global cap.
	running = 0
	for t in ("link", "button", "edit", "comboBox", "checkBox", "radioButton"):
		remaining = _INTERACTIVE_LIMIT - running
		if remaining <= 0:
			break
		if time.monotonic() > counts_deadline:
			log.debug(
				f"[TMTS count-budget] interactive count stopped at type "
				f"'{t}' (running={running})"
			)
			counts_truncated[0] = True
			break
		if scope_range is not None:
			running += _count_in_range(treeInterceptor, t, scope_range, limit=remaining, deadline=counts_deadline, truncated_out=counts_truncated)
		else:
			running += _count_in_scope(treeInterceptor, t, main_obj, scope_cache, limit=remaining, deadline=counts_deadline, truncated_out=counts_truncated)
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
	# Every node the walk produces, in-scope or not, with parallel positions.
	# This IS the unscoped walk result — collected during the one traversal
	# we were going to do anyway.
	all_nodes: list = []
	all_positions: list = []
	notice_match_all = [False]
	walk_truncated = [False]
	walk_positional = [0]
	summary.main_nodes = _walk_main_nodes(
		treeInterceptor, main_obj, scope_cache, positions, notice_match, raw_count, scope_range,
		all_nodes_out=all_nodes,
		all_positions_out=all_positions,
		notice_match_all_out=notice_match_all,
		truncated_out=walk_truncated,
		exclude_ranges=chrome_exclude,
		trust_boundary=trust_boundary,
		untrusted_ranges=untrusted_ranges,
		positional_out=walk_positional,
	)
	t3 = time.monotonic()
	fallback_ran = False
	# Fallback: if the scoped walk produced zero nodes, the scope filter is
	# bogus for this page (the identity-based parent-chain check is known
	# unreliable — see CLAUDE.md "Known limitations"). Fall back to the
	# whole document.
	#
	# This used to RE-WALK the document from scratch with an unscoped
	# filter, which doubled detection time on exactly the pages that were
	# already slowest: hearthstoneaccess.com/changelog.html spent 3679ms on
	# a scoped walk that found nothing, then 3614ms re-walking the identical
	# 361 chunks (7373ms total). But the walk already visited every one of
	# those chunks and knows their text, role, and position — the only thing
	# the scope filter did was decline to keep them. So we keep them as we
	# go and the fallback is now a list assignment.
	#
	# The out-of-scope tolerance bail can truncate all_nodes early, but that
	# bail only fires AFTER at least one in-scope node exists — so it can only
	# affect the DEPLETED branch below, never the empty one. See the note in
	# _scope_looks_depleted about why that is acceptable.
	counts_rescoped = False
	depleted = _scope_looks_depleted(scope_kind, summary.main_nodes, all_nodes, walk_positional[0])
	if all_nodes and (not summary.main_nodes or depleted):
		fallback_ran = True
		summary.main_nodes = all_nodes
		positions[:] = all_positions
		# main_nodes is now the whole document, so the notice keyword must be
		# the whole-document one too.
		notice_match[0] = notice_match_all[0]
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
			# Fresh budget: the phase deadline above expired during the walk.
			# These are unscoped capped enumerations (no per-item work), so
			# they normally finish in a few ms — the deadline only matters on
			# a page whose iterator itself hangs. The recount REPLACES the
			# scoped counts wholesale, so the truncation flag is reset and
			# reflects the recount alone.
			recount_deadline = time.monotonic() + _COUNT_TIME_BUDGET_SEC
			counts_truncated = [False]
			article_truncated = [False]
			summary.article_count = _count_in_range(treeInterceptor, "article", None, limit=_ARTICLE_LIMIT, deadline=recount_deadline, truncated_out=article_truncated)
			if article_truncated[0]:
				counts_truncated[0] = True
			summary.form_input_count = _count_form_inputs(
				treeInterceptor, None, None, {}, _FORM_LIMIT,
				deadline=recount_deadline, truncated_out=counts_truncated,
			)
			running = 0
			for t in ("link", "button", "edit", "comboBox", "checkBox", "radioButton"):
				remaining = _INTERACTIVE_LIMIT - running
				if remaining <= 0:
					break
				if time.monotonic() > recount_deadline:
					counts_truncated[0] = True
					break
				running += _count_in_range(treeInterceptor, t, None, limit=remaining, deadline=recount_deadline, truncated_out=counts_truncated)
			summary.interactive_control_count = running
		# Name the DEPLETED case distinctly in the perf line. It is a different
		# event from an empty scope (the filter produced something, it was just
		# all chrome), and telling them apart is what will show whether this
		# widening is firing where it should — or, if a landing regresses on a
		# page that used to be fine, whether this is why.
		if depleted:
			# Keep the recount fact rather than losing it to the rename: both
			# are useful when reading a soak log.
			scope_kind = "unscoped-depleted-recount" if counts_rescoped else "unscoped-depleted"
		else:
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
	summary.counts_truncated = counts_truncated[0]
	summary.article_count_truncated = article_truncated[0]
	summary.walk_truncated = walk_truncated[0]
	_captured_positions[id(summary)] = positions
	perf_line = (
		f"[TMTS perf] total={(t4-t0)*1000:.0f}ms "
		f"find_main={(t1-t0)*1000:.0f}ms "
		f"counts={(t2-t1)*1000:.0f}ms "
		f"walk={(t3-t2)*1000:.0f}ms "
		f"fallback={(t4-t3)*1000:.0f}ms (ran={fallback_ran}) "
		f"truncated={walk_truncated[0]} counts_trunc={counts_truncated[0]} "
		f"raw_seen={raw_count[0]} all_nodes={len(all_nodes)} "
		f"main_nodes={len(summary.main_nodes)} has_main={summary.has_main_landmark} scope={scope_kind} "
		f"chrome_ranges={len(landmarks.chrome_ranges)} lm_ordered={landmarks.ordered} "
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


# Shortest paragraph-preview we'll accept as a search needle when re-locating a
# landing by text. Too short and we risk matching some unrelated fragment of
# chrome earlier in the document; find() returns the FIRST hit, not the best
# one. 20 chars of real paragraph text is effectively unique on a real page.
_MIN_FIND_NEEDLE_CHARS = 20


def find_landing_by_text(treeInterceptor, needle: str):
	"""Re-locate a paragraph by its TEXT in the CURRENT buffer.

	Why this exists (2026-07-14 soak):

	We capture a TextInfo per node during the walk and use it afterwards. But
	the walk takes 1.5-2 seconds, and on a page that is still hydrating NVDA
	rebuilds its virtual buffer DURING that window. Positions captured early in
	the walk are already stale by the time the walk ends. So the offset is not a
	reliable anchor, and re-walking does NOT fix it -- the retry hits the same
	race and just adds another 2s of staleness. (Serious Eats: chose a Caesar
	salad description, buffer held "15 mins"; the retry landed nowhere and the
	page went silent.)

	The text is the stable anchor, not the offset. NVDA's TextInfo.find(text)
	searches forward from the TextInfo's position and, per NVDA's source,
	"locates the given text and positions this TextInfo object at the start",
	returning True/False. So we search the buffer as it exists NOW.

	Returns a TextInfo collapsed to the start of the match, or None.
	"""
	if not _NVDA_AVAILABLE or treeInterceptor is None:
		return None
	needle = (needle or "").strip()
	if len(needle) < _MIN_FIND_NEEDLE_CHARS:
		# Too short to search for safely -- caller falls back to "no landing".
		return None
	try:
		info = treeInterceptor.makeTextInfo(textInfos.POSITION_FIRST)
		if not info.find(needle):
			return None
		info.collapse()
		return info
	except Exception:
		log.exception("[TMTS] find_landing_by_text failed")
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


def _form_field_in_scope(item, scope_kind, scope_range, chrome_exclude, trust_boundary, untrusted_ranges, main_obj, cache) -> bool:
	"""Is this form field somewhere we are willing to MOVE KEYBOARD FOCUS?

	Mirrors the walk's scope decision exactly, because the two disagreeing is
	precisely how a blind user's focus ends up in a header search box while
	the landing logic knows perfectly well that region is chrome.

	Fails CLOSED throughout. Everywhere else in this module an undecidable
	chunk is kept, on the reasoning that showing a stray line is recoverable.
	That reasoning does not transfer here: the cost of being wrong is not a
	line of nav read aloud, it is the caret leaving the page content. When
	nothing can decide, the answer is "not this field" — the caller then
	announces the form title and moves nothing, which is the fail-safe
	branch.
	"""
	ti = getattr(item, "textInfo", None)
	obj = getattr(item, "obj", None)

	# Positional INCLUSION (main-pos / article): must be inside the range.
	if scope_range is not None:
		if ti is None:
			return obj is not None and _in_scope(obj, main_obj, cache)
		try:
			return (
				ti.compareEndPoints(scope_range, "startToStart") >= 0
				and ti.compareEndPoints(scope_range, "startToEnd") < 0
			)
		except Exception:
			return False

	# Positional EXCLUSION (chrome-pos): same three-step verdict the walk
	# uses, with the same deferral to identity for untrusted territory.
	if scope_kind == "chrome-pos" and ti is not None:
		verdict = _chrome_pos_verdict(ti, trust_boundary, chrome_exclude, untrusted_ranges)
		if verdict is not None:
			return verdict

	# Identity (main-id, chrome, or anything the above could not decide).
	# No object means no evidence, and no evidence means no focus move.
	return obj is not None and _in_scope(obj, main_obj, cache)


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
	# THIS BRANCH MOVES KEYBOARD FOCUS, so it gets the walk's FULL scope
	# decision, not a private approximation of it.
	#
	# It has been wrong twice. Originally it filtered against <main> only,
	# and with no <main> that returned True for EVERY field — so "first form
	# input in document order" meant the first editable element anywhere,
	# routinely the header search box. The first repair added a chrome-range
	# rejection, which fixed the common case but still diverged from the
	# walker in three ways review found (2026-07-18): a main-id page (a
	# <main> exists but its range is unusable) fell into the no-main branch
	# and could focus a field OUTSIDE <main>; an emitted non-chrome region
	# that may hide a reseed-omitted nav was treated as safe here while the
	# walker treats it as untrusted; and a failed comparison answered
	# "eligible" — fail-OPEN on the path that calls setFocus().
	#
	# So: one scope decision, made by _select_scope, applied by
	# _form_field_in_scope. Divergence between "where the article is" and
	# "where we are willing to put the user's focus" is the bug, not the
	# implementation detail.
	landmarks = _find_main_landmark(treeInterceptor)
	scope_kind, scope_range, chrome_exclude, trust_boundary, untrusted_ranges = _select_scope(landmarks)
	cache: dict = {}

	def _in_main(item) -> bool:
		return _form_field_in_scope(
			item, scope_kind, scope_range, chrome_exclude, trust_boundary,
			untrusted_ranges, landmarks.main_obj, cache,
		)

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


# Wall-clock ceiling for the <main> landmark lookup. Normally this returns in
# a few tens of ms, but on a page in a broken loading state each quick-nav
# item can hang on a COM call: krdo.com (2026-07-14 perf log) spent 1868ms in
# find_main on a document that produced ZERO walkable nodes. Giving up just
# means falling back to chrome scope, which the counts-phase budget below now
# bounds — so a slow landmark scan is never worth multiple seconds of frozen
# main thread.
_FIND_MAIN_TIME_BUDGET_SEC = 0.5
# Items scanned backstop for the same loop (a page with hundreds of cheap
# landmarks shouldn't spin under the clock; <main> is essentially always
# among the first few).
_FIND_MAIN_SCAN_LIMIT = 50


class LandmarkScan:
	"""Result of the one landmark enumeration build_tree_summary makes.

	main_obj / main_range: the first <main> landmark and its positional
	range, or None.

	chrome_ranges: positional ranges of the CHROME landmarks seen
	(navigation, banner, contentinfo, complementary, search).

	other_ranges: positional ranges of the NON-chrome landmarks seen
	(main, region, form, article...). These are not exclusions — they mark
	where a nested landmark could have been SILENTLY OMITTED. See
	_select_scope.

	trust_boundary: the range of the LAST landmark this scan vouched for.
	Chunks starting STRICTLY BEFORE its start are decidable from
	chrome_ranges alone; anything at or after it must use the identity
	filter. See _select_scope for why this is the whole design.

	ordered: every landmark's start was >= the previous one's. False kills
	the bounded-trust premise for this page (see trust_boundary).
	"""

	__slots__ = ("main_obj", "main_range", "chrome_ranges", "other_ranges", "trust_boundary", "ordered")

	def __init__(self, main_obj=None, main_range=None, chrome_ranges=None, trust_boundary=None, ordered=True, other_ranges=None):
		self.main_obj = main_obj
		self.main_range = main_range
		self.chrome_ranges = chrome_ranges if chrome_ranges is not None else []
		self.other_ranges = other_ranges if other_ranges is not None else []
		self.trust_boundary = trust_boundary
		self.ordered = ordered


def _usable_range(item):
	"""A landmark quick-nav item's own textInfo as a private copy, or None if
	it has none, the copy fails, or the range is degenerate/inverted.

	MUST come from item.textInfo. Do NOT substitute
	obj.makeTextInfo(POSITION_ALL): that builds a range in a different
	coordinate space, compares as degenerate against the walk's positions,
	and would silently match nothing — the documented trap in
	_single_article_scope_range. Here a doubtful range must read as None,
	because for a CHROME landmark it would mean failing to exclude a
	navigation block.
	"""
	rng = getattr(item, "textInfo", None)
	if rng is None:
		return None
	try:
		rng = rng.copy()
	except Exception:
		return None
	try:
		# Collapsed excludes nothing; inverted (start past end) matches
		# nothing. Anything not strictly start-before-end is unusable.
		if rng.compareEndPoints(rng, "startToEnd") >= 0:
			return None
	except Exception:
		return None
	return rng


def _starts_before(info, boundary):
	"""Tri-state: True / False / None when the comparison itself fails.

	None matters. Every other positional check in this module treats a failed
	comparison as "include the chunk", which is right for counts but wrong
	for scope — there it would serve navigation as article text, which the
	guardrails call worse than doing nothing. Callers turn None into "use the
	identity filter for this chunk".
	"""
	if boundary is None:
		return False
	try:
		return info.compareEndPoints(boundary, "startToStart") < 0
	except Exception:
		return None


def _starts_in_any(info, ranges):
	"""Tri-state: does info's START fall inside any of `ranges`?

	START, not full containment, deliberately. The identity filter this
	replaces asks about `info.NVDAObjectAtStart` — the object at the chunk's
	start — so a paragraph whose expansion runs past the end of a navigation
	block is out of scope under BOTH rules. Requiring full containment would
	quietly disagree at every landmark boundary.

	Nested and overlapping chrome landmarks need no special handling: both
	exclude the same text and a duplicate answer is the same answer. A linear
	scan is right — the landmark scan is capped at 50 items and each
	comparison is offset arithmetic inside NVDA's buffer, not a browser call.

	Returns None if ANY comparison raised, so the caller can fall back to the
	identity filter rather than guess. Guessing "not excluded" here is how a
	nav block becomes article text.
	"""
	failed = False
	for rng in ranges:
		try:
			if (
				info.compareEndPoints(rng, "startToStart") >= 0
				and info.compareEndPoints(rng, "startToEnd") < 0
			):
				return True
		except Exception:
			failed = True
	return None if failed else False


def _chrome_pos_verdict(info, trust_boundary, chrome_ranges, untrusted_ranges):
	"""Positional in-scope verdict for one chunk, or None for "ask the
	identity filter".

	Extracted from _walk_main_nodes so it can be tested at all: the walk needs
	a live NVDA buffer, and this is precisely the wiring where a fail-open
	mistake would reintroduce the release-blocker class (a chunk of navigation
	served as article text). Returning None is always safe — it costs a parent
	chain, nothing else.

	Three questions, in order:

	  1. Is the chunk before the trust boundary? If not (or if the comparison
	     failed), we cannot vouch for the landmark inventory here.
	  2. Does it start inside an emitted CHROME landmark? Then it is chrome.
	     Sound even if a nested landmark was silently omitted, because nested
	     chrome inside chrome excludes the same text.
	  3. Does it start inside an emitted NON-CHROME landmark? Then it is
	     UNTRUSTED, because that is the one place an omitted nested nav could
	     hide (see _select_scope). Only a chunk inside no emitted landmark at
	     all can be positively called content.

	Every tri-state None from the range helpers propagates to None here. There
	is deliberately no "assume not excluded" branch.
	"""
	if _starts_before(info, trust_boundary) is not True:
		return None
	excluded = _starts_in_any(info, chrome_ranges)
	if excluded is True:
		return False
	if excluded is not False:
		return None
	if _starts_in_any(info, untrusted_ranges or ()) is not False:
		return None
	return True


# Bars for _scope_looks_depleted. Deliberately asymmetric: the scoped tree
# must have nothing even MODERATELY substantial (100), while the document must
# have something UNARGUABLY substantial (200) before we overrule the filter.
# The gap is the safety margin — a page that is genuinely just short text
# everywhere never trips it.
_DEPLETED_SCOPED_SUBSTANTIAL = 100
_DEPLETED_DOC_SUBSTANTIAL = 200


def _scope_looks_depleted(scope_kind: str, main_nodes: list, all_nodes: list, positional_drops: int = 0) -> bool:
	"""True when the scope filter kept nodes but threw away the article.

	The existing fallback only fires when the scoped walk produces NOTHING.
	That catches total scope failure and misses the worse case — near-total
	failure, which yields a confident wrong answer instead of an obvious
	blank. deadsimpletech.com/blog/midwinter, 2026-07-18: the identity chrome
	filter kept 3 of 16 walked nodes, all of them chrome ("Get new articles
	delivered to your inbox"), and discarded the entire article INCLUDING a
	1439-character paragraph. main_nodes was non-empty, so the net stayed
	closed, the classifier correctly saw no article in what it was handed,
	declined to land, and the user got silence. Pressing Z landed fine,
	because Z scans the buffer directly and never consults this filter — that
	is what proved the content was there all along.

	Guards, each earning its place:

	  - IDENTITY-DECIDED WALKS ONLY (`chrome`, `main-id`, and `chrome-pos`
	    when it made zero positional decisions). The positional scopes are
	    trustworthy and their exclusions are deliberate: a single-<article>
	    page legitimately drops comments and sidebars, and second-guessing
	    that would undo the work those scopes exist to do. This widening
	    exists specifically because the parent-chain check is unreliable.
	  - The scoped tree must have kept FEWER nodes than the document has, or
	    there is nothing to widen to.
	  - The scoped tree must contain NO substantial non-chrome paragraph. If
	    it has real content, the filter did its job and we leave it alone.
	  - The document must contain a clearly substantial non-chrome paragraph.
	    Captions and legal boilerplate are excluded via the walk-time flags,
	    so a footer copyright or a photo credit cannot trigger this — that
	    matters, because the most likely false positive is a small form page
	    whose only long text is a footer legal notice.

	Note on all_nodes completeness: the walk's out-of-scope tolerance bail can
	cut all_nodes short, but only after at least one in-scope node exists — so
	on this branch all_nodes may be a PREFIX of the document. That is
	acceptable here: a prefix containing a 200+ char paragraph is still better
	evidence than a scoped tree containing none, and the landing finders'
	chrome heuristics still run over whatever we hand them.
	"""
	# chrome-pos is eligible ONLY when the walk actually fell back to
	# identity, which is what `positional_drops == 0` means.
	#
	# Two wrong answers were tried before this one. Excluding chrome-pos
	# outright re-opened the bug the net exists to fix: on a page whose only
	# landmark is a nav at the top, the trust boundary sits at offset 0, so
	# NOTHING starts before it, every chunk takes the identity path, and the
	# page is chrome-scoped in all but name — with its safety net switched
	# off. Admitting chrome-pos unconditionally went too far the other way: a
	# page whose positional exclusions WORKED could be widened back open on
	# the strength of two long chrome paragraphs, re-admitting the very
	# navigation and cookie text that was correctly removed.
	#
	# The scope NAME cannot tell those apart; the count of positional
	# EXCLUSIONS can. Zero means positional scoping REMOVED nothing here, so
	# there is no correct exclusion work for widening to undo. Counting all
	# positional decisions was wrong: an ordinary content chunk outside every
	# landmark scores an INCLUSION, which is not evidence of removal, and one
	# of those could block a needed widening (review, 2026-07-18).
	#
	# HONEST LIMIT, do not oversell this: zero drops does not PROVE widening
	# is right. Identity can correctly remove chrome on a page that made no
	# positional exclusion, and widening would re-admit it. This narrows the
	# failure window; it does not close it. The 100/200-twice bars and the
	# `unscoped-depleted` perf tag are the other two layers.
	if scope_kind in ("chrome", "main-id"):
		pass
	elif scope_kind == "chrome-pos" and positional_drops == 0:
		pass
	else:
		return False
	if not main_nodes or not all_nodes:
		return False
	if len(main_nodes) >= len(all_nodes):
		return False

	def _real_paragraph(n, bar):
		return (
			n.kind == "paragraph"
			and n.text_length >= bar
			and not getattr(n, "is_boilerplate", False)
			and not getattr(n, "is_caption", False)
		)

	if any(_real_paragraph(n, _DEPLETED_SCOPED_SUBSTANTIAL) for n in main_nodes):
		return False
	# TWO substantial paragraphs, not one. A single long paragraph proves only
	# that long text exists somewhere, not that an article was discarded — and
	# the likeliest single long paragraph on a small page is chrome the filter
	# correctly excluded: a cookie-consent notice, a subscription pitch, a
	# help panel, a terms blurb. The caption and boilerplate flags are lexical
	# and do not catch those (same open-vocabulary problem that keeps
	# _looks_like_editorial_disclosure out of promo text). A real article that
	# the filter swallowed has a RUN of them — deadsimpletech's discarded body
	# was 618, 563, 699, 1002, 460 and 1439 characters. Requiring two keeps
	# that case and drops the lone-notice false positive, which matters
	# because those are the checkout and login pages v1.0.13 just fixed.
	substantial = 0
	for n in all_nodes:
		if _real_paragraph(n, _DEPLETED_DOC_SUBSTANTIAL):
			substantial += 1
			if substantial >= 2:
				return True
	return False


def _log_landmark_probe(types: list, ordered: bool, no_range: int, stopped: str) -> None:
	"""Emit `[TMTS landmark-probe]`.

	READ THIS BEFORE DELETING ANYTHING HERE. This started as a passive probe
	whose docstring said it "changes no behaviour and feeds no decision" and
	"retire once there is a verdict". Both statements are now FALSE for the
	ordering computation: `probe_ordered` flows into `LandmarkScan.ordered`
	and gates chrome-pos in `_select_scope`. Deleting the computation would
	silently remove a safety input. Only the LOG LINE below is disposable.

	What the line is still good for: `stopped=` shows how often the landmark
	scan is cut short in real browsing, and `n=` / `types=` show landmark
	shapes across real sites, which is what future scoping work will need.

	What it is NOT evidence of, despite appearances: `ordered=`. Each search
	is seeded with the previous match's start offset and runs forward, so the
	emitted starts are nondecreasing BY CONSTRUCTION. The 15-of-15
	`ordered=True` reading that this design was originally justified with was
	guaranteed a priori and proved nothing. The property that actually
	mattered — whether the emission is COMPLETE at equal-start nesting — is
	invisible here, and is handled structurally instead (see
	`_chrome_pos_verdict` and `untrusted_ranges`). Do not cite this field as
	safety evidence again.

	Only fires on pages with NO <main>: the scan returns early once <main> is
	found, so such a page has only been asked about the landmarks before it.
	"""
	if not types:
		return
	line = (
		f"[TMTS landmark-probe] n={len(types)} ordered={ordered} "
		f"no_range={no_range} stopped={stopped} types={','.join(types[:12])}"
	)
	log.debug(line)
	_append_perf_line(line)


def _select_scope(landmarks: "LandmarkScan"):
	"""Pick the scoping strategy. Returns
	(scope_kind, scope_range, chrome_exclude, trust_boundary, untrusted_ranges).

	scope_range and chrome_exclude are never both set — an INCLUSION range or
	an EXCLUSION list, never both. Callers depend on that.

	Pure and NVDA-free on purpose: build_tree_summary cannot run outside NVDA,
	so this would otherwise be the one load-bearing decision with no coverage.

	  main-pos:   <main> present with a usable range → scope INTO it
	  main-id:    <main> present, no usable range → identity checks
	  chrome-pos: no <main> → exclude the chrome landmark ranges by START
	              position, but only before trust_boundary and only outside
	              untrusted_ranges (both below)
	  chrome:     nothing to bound trust with → identity filter

	WHY BOUNDED TRUST
	-----------------
	The first attempt (shelved on `chrome-pos-attempt`) gated on "did the
	landmark enumeration finish cleanly?". That is UNIMPLEMENTABLE: NVDA's
	VirtualBuffer._iterNodesByAttribs discards the exception from
	VBuf_findNodeByAttributes and returns, so a native failure is
	indistinguishable from natural exhaustion (verified by disassembling
	virtualBuffers/__init__.pyc from the installed library.zip).

	So we never ask whether the scan finished, only how far it got.
	trust_boundary is the START of the last landmark we successfully placed;
	`_starts_before` uses a STRICT comparison, so a chunk starting exactly at
	the boundary is untrusted. `trust_frozen` in the scan is monotone, so if
	the boundary landmark was placed then every earlier emitted landmark was
	placed too. Truncation therefore costs speed, never correctness.

	WHY untrusted_ranges — THE HOLE THAT ORDERING DOES NOT CLOSE
	------------------------------------------------------------
	Bounded trust needs more than "starts arrive in order". It needs the
	emitted prefix to be COMPLETE. Two independent reviews found the gap
	(2026-07-18), and it is not theoretical:

	NVDA resumes each search from the PREVIOUS MATCH'S START OFFSET and
	searches forward. Whether a landmark starting at the SAME offset as the
	one just returned is emitted or skipped is not observable from Python. If
	it is skipped, that is OMISSION MID-STREAM, which ordering cannot detect
	and truncation logic cannot catch. Concretely: `<section aria-label=...>`
	wrapping a `<nav>` with no text between them puts both at the same offset.
	The section is emitted; the nav may not be. The nav is then absent from
	chrome_ranges, a later footer advances the boundary past it, and every
	chunk of that navigation reads as trusted CONTENT — a blind user lands in
	a menu, which is the exact failure this design exists to prevent. Today's
	identity filter catches it, because the parent chain hits the nav.

	VERIFIED IN NVDA'S C++, because the fix DOES depend on it (an earlier
	draft of this comment claimed otherwise, wrongly). In
	nvdaHelper/vbufBase/storage.cpp: `VBufStorage_fieldNode_t::nextNodeInTree`
	with TREEDIRECTION_FORWARD moves to `firstChild` when present, else up and
	to `next` — a PRE-ORDER walk, so an ancestor is always emitted before its
	descendants. And `findNodeByAttributes` reseeds via
	`locateTextFieldNodeAtOffset`, which returns the TEXT LEAF at that offset,
	so the next search resumes from inside the just-matched landmark's own
	subtree. Every otherwise-eligible landmark skipped BECAUSE OF THE RESEED
	is therefore a DESCENDANT of an emitted landmark (stated precisely: native
	code also skips hidden, zero-length and non-matching nodes for unrelated
	reasons, which is not this case), which is stronger than the equal-start case alone. The outer
	member is always the one emitted; the dangerous inverse (inner emitted,
	outer skipped and extending past it) cannot occur.

	Given that, any chunk a skipped landmark could contain also lies inside an
	emitted landmark's range. Therefore:

	  - inside an emitted CHROME range  → excluded (a nested chrome landmark
	    inside chrome excludes the same text, so omission is harmless)
	  - inside an emitted NON-CHROME range → UNTRUSTED, use the identity
	    filter (this is where an omitted nested nav could hide)
	  - inside no emitted range at all  → cannot contain an omitted landmark,
	    so the positional answer is sound

	untrusted_ranges is that middle set. It costs one extra list and one more
	linear scan of a set capped at 50.

	A NOTE ON THE `ordered` FLAG, so nobody mistakes it for the safety story:
	because each search is seeded with the previous match's start, emitted
	starts are nondecreasing BY CONSTRUCTION. The probe's 15-of-15
	`ordered=True` was therefore guaranteed a priori and is NOT evidence of
	anything. The flag is kept as a cheap tripwire (one comparison, fails
	closed) but the safety rests on trust_boundary and untrusted_ranges.
	"""
	if landmarks.main_range is not None:
		return "main-pos", landmarks.main_range, None, None, None
	if landmarks.main_obj is not None:
		return "main-id", None, None, None, None
	if landmarks.ordered and landmarks.trust_boundary is not None:
		return (
			"chrome-pos",
			None,
			landmarks.chrome_ranges,
			landmarks.trust_boundary,
			landmarks.other_ranges,
		)
	return "chrome", None, None, None, None


def _find_main_landmark(treeInterceptor) -> "LandmarkScan":
	"""Enumerate landmarks ONCE. Returns a LandmarkScan carrying the <main>
	landmark and, for pages without one, the chrome inventory and trust
	boundary that let the walk scope positionally instead of by parent chain.

	main_range is the landmark quick-nav item's own textInfo — the same
	positional-scoping trick proven for the single-<article> case: ranges
	built by the tree interceptor share the walk's coordinate space, so
	compareEndPoints is meaningful (obj.makeTextInfo does NOT — see
	_single_article_scope_range). A usable range lets both the counts and
	the walk decide "inside <main>?" by position — reliable where the
	identity-based parent-chain check silently fails (Calendar, Zoom), and
	FAST: a buffer-offset comparison per item instead of a COM parent
	chain per item. The parent chains were the dominant detection cost
	(~1 s on Zoom's 44-node page, 12.4 s on judysdogblog), and on the
	no-<main> pages that still pay them, 1808 ms of a 2035 ms walk
	(measured 2026-07-18 — see the shelved `chrome-pos-attempt` branch and
	CLAUDE.md's Known-limitations bullet for why the obvious fix is
	blocked).
	"""
	deadline = time.monotonic() + _FIND_MAIN_TIME_BUDGET_SEC
	scanned = 0
	# --- Landmark-ordering probe (diagnostic only; see _log_landmark_probe) ---
	probe_types: list = []
	probe_ordered = True
	probe_no_range = 0
	probe_prev = None
	probe_stopped = "exhausted"
	# --- Bounded-trust inventory (see LandmarkScan / _select_scope) ---
	chrome_ranges: list = []
	other_ranges: list = []
	trust_boundary = None
	# Once we hit a landmark we cannot place, everything from THERE on is
	# unknown, so the boundary stops advancing and we stop collecting.
	trust_frozen = False
	try:
		for item in treeInterceptor._iterNodesByType("landmark"):
			scanned += 1
			obj = getattr(item, "obj", None)
			lm = _landmark_type(obj) if obj is not None else "?"
			probe_types.append(lm or "-")
			# Ordering check. Compare each landmark's start against the
			# previous one; a single backwards step disproves document order.
			# Costs one offset comparison per landmark and holds ONE range
			# alive at a time — no copies, no parent chains.
			probe_rng = getattr(item, "textInfo", None)
			if probe_rng is None:
				probe_no_range += 1
			else:
				if probe_prev is not None:
					try:
						if probe_rng.compareEndPoints(probe_prev, "startToStart") < 0:
							probe_ordered = False
					except Exception:
						# Fails CLOSED. A comparison we could not make means
						# the order is UNKNOWN, and unknown must not read as
						# ordered — this value gates the whole bounded-trust
						# path in _select_scope.
						probe_ordered = False
				probe_prev = probe_rng

			if not trust_frozen:
				# An item we cannot RESOLVE is one we cannot CLASSIFY, and it
				# may be the navigation. An item we cannot PLACE is one we
				# cannot exclude. Either freezes the boundary here: everything
				# before this landmark is still fully known and stays usable.
				usable = _usable_range(item) if obj is not None else None
				if usable is None:
					trust_frozen = True
				else:
					if lm in _CHROME_LANDMARK_TYPES:
						chrome_ranges.append(usable)
					else:
						# NOT an exclusion. This marks territory where a
						# nested landmark may have been silently omitted, so
						# chunks inside it cannot be trusted to positional
						# scoping. See _select_scope.
						other_ranges.append(usable)
					# The boundary advances to this landmark's START. Any
					# landmark containing a chunk before this point must itself
					# have started earlier, so ordering guarantees we already
					# enumerated it.
					trust_boundary = usable

			if obj is None or lm != "main":
				# Budget checks AFTER examining the item in hand: the COM
				# cost was fetching it, and throwing away an already-fetched
				# <main> would degrade the page to chrome scope for zero
				# time saved. The check only guards fetching the NEXT item.
				if scanned >= _FIND_MAIN_SCAN_LIMIT or time.monotonic() > deadline:
					log.debug(
						f"[TMTS count-budget] landmark scan stopped after "
						f"{scanned} item(s) — treating page as having no <main>"
					)
					probe_stopped = "cap" if scanned >= _FIND_MAIN_SCAN_LIMIT else "deadline"
					# Do NOT log here — the fall-through below logs once. This
					# used to log at both points, emitting every capped page
					# TWICE and double-counting it in the very dataset the
					# probe exists to build.
					break
				continue
			# The <main> range gets the SAME usability check as the chrome
			# ranges: a degenerate or inverted range selected main-pos and
			# then matched nothing, silently scoping the page to an empty
			# region. Falling back to makeTextInfo is retained only as a
			# last resort, and is checked the same way.
			rng = _usable_range(item)
			if rng is None:
				try:
					rng = treeInterceptor.makeTextInfo(obj)
					if rng is not None and rng.compareEndPoints(rng, "startToEnd") >= 0:
						rng = None
				except Exception:
					rng = None
			# Found <main>: we stop enumerating, so this page tells us nothing
			# about ordering past this point and is NOT probe evidence. The
			# chrome inventory is partial by construction here, which is
			# harmless: _select_scope never routes a <main> page to chrome-pos.
			# One caveat, since "never read" would be too strong — on a
			# main-id page (main found, range unusable)
			# set_focus_on_first_form_input DOES consult this partial list.
			# Safe because that filter only ever REJECTS candidates, so a
			# missing range leaves a field eligible exactly as before.
			return LandmarkScan(obj, rng, chrome_ranges, trust_boundary, probe_ordered, other_ranges)
	except Exception:
		probe_stopped = "exception"
		_log_landmark_probe(probe_types, probe_ordered, probe_no_range, probe_stopped)
		return LandmarkScan(None, None, chrome_ranges, trust_boundary, probe_ordered, other_ranges)
	_log_landmark_probe(probe_types, probe_ordered, probe_no_range, probe_stopped)
	return LandmarkScan(None, None, chrome_ranges, trust_boundary, probe_ordered, other_ranges)


def _single_article_scope_range(treeInterceptor, deadline: Optional[float] = None):
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

	`deadline` is the shared counts-phase budget: this runs INSIDE the counts
	phase, and even on a genuinely single-article page the iterator must be
	pumped a second time to prove there is no second article — on a page
	stuck mid-load that second fetch is a hanging COM call (the krdo freeze
	class). Past the deadline we return None; unconfirmed single-ness must
	not positionally scope the walk.
	"""
	try:
		found = None
		scanned = 0
		# Expired budget → no new enumeration at all; and per-item checks at
		# the loop BOTTOM so they guard fetching the NEXT item (the hanging
		# COM call) rather than discarding the one already paid for.
		if deadline is not None and time.monotonic() > deadline:
			return None
		for item in treeInterceptor._iterNodesByType("article"):
			scanned += 1
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
			if ti is not None:
				if found is not None:
					# More than one <article> (e.g. related-post cards).
					# Ambiguous which is the post body — skip positional
					# scoping.
					return None
				found = ti
			if scanned >= _COUNT_SCAN_LIMIT or (
				deadline is not None and time.monotonic() > deadline
			):
				# Out of budget before the enumeration finished: single-ness
				# is UNCONFIRMED, and unconfirmed single-ness must not
				# positionally scope the walk.
				return None
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


def _in_scope(obj, main_obj, cache: dict, stats: Optional[dict] = None) -> bool:
	# Decide whether obj is "page content" for classification purposes.
	# If main_obj is set: obj must be inside the main landmark.
	# If no main landmark: obj must NOT be inside a chrome landmark.
	# Walks obj.parent up to _PARENT_WALK_MAX_DEPTH ancestors.
	# `cache` is a {id(obj): (obj, bool)} dict scoped to one
	# build_tree_summary call; all ancestors visited during the walk are
	# cached with the final decision, so subsequent siblings short-circuit
	# immediately.
	#
	# THE VALUE MUST KEEP A STRONG REFERENCE TO THE OBJECT. This used to be
	# {id(obj): bool}, storing the address alone, and that was a
	# WRONG-ANSWER bug, not a tidiness issue (2026-07-18):
	#
	#   The ancestors walked here are transient. NVDA caches each fetched
	#   parent on its child, so the chain stays alive only while the child
	#   does -- NVDA's global instance registry is weak and holds nothing.
	#   _walk_main_nodes rebinds `obj` on the next chunk, the whole previous
	#   chain becomes garbage, and CPython hands freed blocks back LIFO. The
	#   next chunk then allocates NVDAObjects of the same classes and sizes
	#   into exactly those addresses. Measured: 2000 transient objects of one
	#   class occupied 2 distinct addresses.
	#
	#   So a cache keyed on a dead address matched LIVE, UNRELATED objects
	#   and handed them the dead object's verdict. Adjacent chunks usually
	#   share a verdict, which masked it -- except at the nav-to-content
	#   boundary, which is the one decision that matters. This is a strong
	#   candidate for the flakiness CLAUDE.md attributes purely to NVDA
	#   returning fresh instances (Calendar, bestmidi).
	#
	# Keeping the object in the value pins the address for the life of the
	# cache, so an id can never be recycled underneath an entry. Cost is one
	# extra reference per visited ancestor for the duration of a single
	# build_tree_summary call.
	#
	# Keying on the OBJECT instead does NOT work and must not be attempted:
	# NVDAObject.__eq__ is logical (it delegates to _isEqual) but
	# NVDAObject.__hash__ is plain super().__hash__(), i.e. address-based
	# (verified in NVDA's own bytecode, NVDAObjects/__init__.pyc). Logically
	# equal objects therefore hash differently and a dict keyed on them
	# misses just as badly, while also violating the hash/eq invariant.
	#
	# `stats` (optional dict) collects hit/miss/parent-dereference counts so
	# the walk can report how much this cache actually does. It is
	# diagnostic only; nothing branches on it.
	#
	# There used to be an "unscoped sentinel" value for main_obj that made
	# this accept everything, for the last-resort re-walk of the whole
	# document. That re-walk is gone (the walk now collects out-of-scope
	# nodes as it goes — see build_tree_summary), so nothing passes the
	# sentinel and the branch was dead.
	if obj is None:
		return False
	key = id(obj)
	entry = cache.get(key)
	# The `is` check makes a stale hit impossible BY CONSTRUCTION rather than
	# by argument. Pinning the object already prevents the address being
	# recycled, so this can only fire if a future edit drops the strong
	# reference — at which point it degrades to a miss (a slower but correct
	# answer) instead of silently resurrecting the old behaviour.
	if entry is not None and entry[0] is obj:
		if stats is not None:
			stats["cache_hits"] = stats.get("cache_hits", 0) + 1
		return entry[1]
	if stats is not None:
		stats["cache_misses"] = stats.get("cache_misses", 0) + 1

	# Objects visited on this chain, kept as (id, obj) pairs so the write
	# below can pin every one of them. Holding the objects here also keeps
	# their addresses stable for the duration of THIS walk.
	visited = []
	cur = obj
	result = None
	for _ in range(_PARENT_WALK_MAX_DEPTH):
		if cur is None:
			break
		ckey = id(cur)
		entry = cache.get(ckey)
		if entry is not None and entry[0] is cur:
			if stats is not None:
				stats["cache_hits"] = stats.get("cache_hits", 0) + 1
			result = entry[1]
			break
		visited.append((ckey, cur))
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
			if stats is not None:
				stats["parent_derefs"] = stats.get("parent_derefs", 0) + 1
			cur = cur.parent
		except Exception:
			break

	if result is None:
		# main_obj set and never reached → not in main → out of scope.
		# No main_obj and never hit a chrome landmark → in scope.
		result = main_obj is None

	for vkey, vobj in visited:
		cache[vkey] = (vobj, result)
	return result


def _count_in_scope(treeInterceptor, item_type: str, main_obj, cache: dict, limit: int = 0, deadline: Optional[float] = None, truncated_out: Optional[list] = None) -> int:
	# Count quick-nav items of item_type that pass _in_scope. If `limit` is
	# positive, return as soon as count reaches it — the classifier only
	# compares counts against fixed thresholds (e.g. APP_CONTROL_FLOOR=10),
	# so anything above the largest threshold is wasted precision and an
	# expensive parent-walk for nothing. Saves hundreds of _in_scope calls
	# on heavy pages with many links.
	#
	# Scan cap + deadline: the in-scope LIMIT alone can't bound this loop —
	# when the parent-chain identity check is failing (its known failure
	# mode), nothing counts as in scope, so the loop scans EVERY item of the
	# type and pays a parent walk for each. Stack Overflow's tag page spent
	# 2038ms here across its hundreds of links (2026-07-14 perf log). The
	# scan cap mirrors _count_in_range's; the deadline is the shared
	# counts-phase budget, checked per item because a single enumeration
	# can outlive any between-enumeration check.
	#
	# Check placement (both loops): an already-expired deadline is checked
	# BEFORE the loop so no new enumeration starts at all, and the per-item
	# checks sit at the BOTTOM so they guard fetching the NEXT item — the
	# fetch is the hanging COM call; the item in hand is already paid for.
	# On any truncation OR iterator exception the count is a partial
	# UNDERCOUNT, so truncated_out is set — an exception must not
	# masquerade as a trustworthy zero (it would sail through the small-
	# count intents the counts_truncated flag exists to protect).
	count = 0
	if deadline is not None and time.monotonic() > deadline:
		if truncated_out is not None:
			truncated_out[0] = True
		return count
	try:
		scanned = 0
		for item in treeInterceptor._iterNodesByType(item_type):
			scanned += 1
			obj = getattr(item, "obj", None)
			if obj is not None and _in_scope(obj, main_obj, cache):
				count += 1
				if limit and count >= limit:
					return count
			if scanned >= _COUNT_SCAN_LIMIT or (
				deadline is not None and time.monotonic() > deadline
			):
				if truncated_out is not None:
					truncated_out[0] = True
				break
	except Exception:
		if truncated_out is not None:
			truncated_out[0] = True
	return count


# Hard cap on quick-nav items SCANNED per count enumeration. The classifier
# only compares counts against small fixed thresholds; on a page with
# thousands of links, scanning past a few hundred items buys nothing.
_COUNT_SCAN_LIMIT = 300


def _count_in_range(treeInterceptor, item_type: str, scope_range, limit: int = 0, deadline: Optional[float] = None, truncated_out: Optional[list] = None) -> int:
	"""Count quick-nav items of item_type POSITIONALLY: an item counts when
	its range STARTS inside scope_range. With scope_range=None, counts the
	whole document. No parent-chain walks — a buffer-offset comparison per
	item — so this is orders of magnitude cheaper than _count_in_scope and
	immune to the identity-check failure that made counts come back 0 on
	pages with a perfectly real <main> (Zoom registration: forms=0 on a
	7-input form).

	Items that expose no textInfo are counted as in scope (inclusive bias:
	the classifier's FORM/APP gates are guarded by content signals anyway).

	`deadline` (the shared counts-phase budget) is checked per item: on a
	page stuck mid-load, the quick-nav iterator itself can hang on COM
	calls, and a between-enumerations check can't stop an enumeration
	already in progress.

	Check placement and exception handling mirror _count_in_scope: expired
	deadline pre-checked so no new enumeration starts, per-item checks at
	the loop BOTTOM so they guard the NEXT fetch (and an out-of-range item
	can't skip them), truncated_out set on any truncation or iterator
	exception so a partial count never reads as a trustworthy small one.
	"""
	count = 0
	if deadline is not None and time.monotonic() > deadline:
		if truncated_out is not None:
			truncated_out[0] = True
		return count
	try:
		scanned = 0
		for item in treeInterceptor._iterNodesByType(item_type):
			scanned += 1
			in_range = True
			if scope_range is not None:
				ti = getattr(item, "textInfo", None)
				if ti is not None:
					try:
						in_range = (
							ti.compareEndPoints(scope_range, "startToStart") >= 0
							and ti.compareEndPoints(scope_range, "startToEnd") < 0
						)
					except Exception:
						in_range = True
			if in_range:
				count += 1
				if limit and count >= limit:
					return count
			if scanned >= _COUNT_SCAN_LIMIT or (
				deadline is not None and time.monotonic() > deadline
			):
				if truncated_out is not None:
					truncated_out[0] = True
				break
	except Exception:
		if truncated_out is not None:
			truncated_out[0] = True
	return count


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


# What actually makes a page a FORM: things the user TYPES INTO or CHOOSES
# FROM. Deliberately NOT "button".
#
# We used to count NVDA's "formField" quick-nav type, but in NVDA's definition a
# BUTTON is a form field. The classifier's own declaration of this value reads
# "editable inputs, comboboxes, etc." — so the field's contract and its
# implementation disagreed, and the classifier was asking for inputs and being
# handed inputs PLUS every button on the page.
#
# On a control-dense CONTENT page that instantly maxes the counter: an IMDb
# title page (rate / watchlist / share / trailer / cast expanders) and a TV
# station front page (menus, play buttons) both reported forms=10, double the
# STRONG_FORM_INPUT_COUNT bar of 5. Both were then classified FORM, and the bare-
# form branch MOVED THE USER'S KEYBOARD FOCUS into the site's search box. A movie
# page is not a form; a news front page is not a form. (2026-07-14 soak.)
#
# Counting only real inputs fixes this at the root, with no threshold tuning: a
# genuine form (Google Forms, the Zoom registration page) still has many edits /
# combos / checkboxes / radios, while a content page has a lone search box.
_FORM_INPUT_TYPES = ("edit", "comboBox", "checkBox", "radioButton")

# Wall-clock ceiling for the ENTIRE counts phase of build_tree_summary: the
# article count, all four form-input enumerations, and all six interactive
# enumerations share ONE deadline, checked per item inside every enumeration.
#
# This used to be a 0.4s budget covering only the form-input count, checked
# only BETWEEN enumerations with "edit" exempt. Two ways real pages blew
# through it (2026-07-14 perf log):
#   - krdo.com stuck mid-load: every _iterNodesByType call hung on COM, and
#     the unbudgeted enumerations (article, always-run "edit", all six
#     interactive types) stacked up to counts=8436ms on a page that produced
#     ZERO walkable nodes. A between-types check can't stop an enumeration
#     already hanging; a per-item check stops it at the next item.
#   - stackoverflow.com tag page (no <main>): the identity path scanned
#     hundreds of links at a parent-chain walk each — 2038ms. (Also capped
#     by _COUNT_SCAN_LIMIT in _count_in_scope now.)
#
# 0.6s covers the whole phase: healthy pages finish counts in 4-300ms, so the
# budget only bites on pathological ones. Undercounting is failing safe — a
# smaller count can only make the classifier LESS likely to call FORM or APP,
# and the FORM branch is the one that moves the user's focus.
#
# The form-input types stay ordered so the decisive one runs first: "edit"
# alone separates a real form (many text inputs) from a content page (one
# search box), so if the clock cuts the rest we still have the signal that
# matters.
_COUNT_TIME_BUDGET_SEC = 0.6


def _count_form_inputs(treeInterceptor, scope_range, main_obj, scope_cache: dict, limit: int, deadline: Optional[float] = None, truncated_out: Optional[list] = None) -> int:
	# Sum the real input types, stopping as soon as we reach the cap (so an
	# obvious form doesn't pay for four full enumerations) or the clock.
	# `deadline` is the shared counts-phase deadline from build_tree_summary
	# (every current caller passes one); the None default is defensive for
	# future callers and takes a fresh budget so no path can run unbounded.
	if deadline is None:
		deadline = time.monotonic() + _COUNT_TIME_BUDGET_SEC
	total = 0
	for i, t in enumerate(_FORM_INPUT_TYPES):
		remaining = limit - total
		if remaining <= 0:
			break
		# The between-types check stops us starting a new enumeration past
		# the deadline; the per-item deadline inside each enumeration stops
		# one that's already running. This applies to "edit" too: on a
		# healthy page the article count ahead of us costs milliseconds, so
		# edit always effectively runs — the only way to arrive here expired
		# is the pathological hanging-COM page, where starting one more
		# enumeration is exactly the freeze this budget exists to prevent.
		# The undercount is safe because truncated_out gates every
		# count-sensitive intent (FORM via article trust, NOTICE/KEY_RESULT
		# via counts_truncated).
		if time.monotonic() > deadline:
			log.debug(
				f"[TMTS count-budget] form-input count stopped after {i} of "
				f"{len(_FORM_INPUT_TYPES)} types (total={total})"
			)
			if truncated_out is not None:
				truncated_out[0] = True
			break
		if scope_range is not None:
			total += _count_in_range(treeInterceptor, t, scope_range, limit=remaining, deadline=deadline, truncated_out=truncated_out)
		else:
			total += _count_in_scope(treeInterceptor, t, main_obj, scope_cache, limit=remaining, deadline=deadline, truncated_out=truncated_out)
	return total


def _walk_main_nodes(treeInterceptor, main_obj, cache: dict, positions_out: list, notice_match_out: Optional[list] = None, raw_count_out: Optional[list] = None, scope_range=None, all_nodes_out: Optional[list] = None, all_positions_out: Optional[list] = None, notice_match_all_out: Optional[list] = None, truncated_out: Optional[list] = None, exclude_ranges=None, trust_boundary=None, untrusted_ranges=None, positional_out: Optional[list] = None) -> list[MainNode]:
	# Walk the whole document by UNIT_PARAGRAPH; emit only nodes that
	# pass _in_scope (inside <main> if present, or outside chrome
	# landmarks if not). Bail out once we've had _OUT_OF_SCOPE_TOLERANCE
	# consecutive out-of-scope nodes (most likely we're in the footer),
	# or once we exceed WALK_NODE_LIMIT / WALK_TIME_BUDGET_SEC.
	#
	# notice_match_out (optional, single-element list): the walker flips
	# its first element to True the first time it sees a chunk of text
	# matching the status-keyword regex. Used by the NOTICE classifier.
	#
	# all_nodes_out / all_positions_out (optional lists): every node this
	# walk produces gets appended here REGARDLESS of scope, with its
	# parallel position. This is what the caller uses instead of re-walking
	# the document unscoped when the scope filter rejects everything. The
	# old code ran a whole second walk for that case, which on
	# hearthstoneaccess.com/changelog.html meant 3679ms of scoped walk that
	# found nothing followed by 3614ms of unscoped walk over the identical
	# 361 chunks. The chunks are already in hand the first time through;
	# collecting them costs a _node_for call and a textInfo copy, not a
	# second traversal.
	#
	# truncated_out (optional, single-element list): set to True if we
	# stopped on the node cap or the time budget rather than reaching the
	# end of the document.
	result: list[MainNode] = []
	walk_start = time.monotonic()
	deadline = walk_start + WALK_TIME_BUDGET_SEC
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
	# Per-call-site timing, emitted as [TMTS walk-phase] at the end of the
	# walk. The aggregate walk= number in the perf line cannot say WHICH
	# cross-process call owns the time, and on store.payproglobal.com's
	# checkout (2026-07-17) that ambiguity blocked a fix: every phase slowed
	# together on the bad loads, so "the parent chains are the cost" was a
	# guess. These accumulators settle it in one page load. A
	# time.monotonic() pair is nanoseconds against calls that run in
	# milliseconds, so measuring is free relative to what it measures.
	t_expand = 0.0
	t_text = 0.0
	t_obj = 0.0
	t_scope = 0.0
	scope_stats: dict = {}
	# How the scope decision was actually reached, per chunk. The whole point
	# of bounded trust is that positional should dominate and identity should
	# only mop up the tail past the last landmark; if these come back the
	# other way round on real pages, the boundary is landing too early.
	positional_hits = 0
	positional_drops = 0
	identity_hits = 0
	# Start position of the previously processed chunk, for the forward-
	# progress check below.
	prev_start = None
	truncated = False
	for _ in range(WALK_NODE_LIMIT):
		# Wall-clock guard. Checked per-iteration: one time.monotonic() call
		# is nanoseconds against a ~7ms expand(), so the check is free
		# relative to the work it's bounding.
		if time.monotonic() > deadline:
			truncated = True
			break
		try:
			_t = time.monotonic()
			info.expand(textInfos.UNIT_PARAGRAPH)
			t_expand += time.monotonic() - _t
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
			_t = time.monotonic()
			text = info.text or ""
			t_text += time.monotonic() - _t
			_t = time.monotonic()
			obj = info.NVDAObjectAtStart
			t_obj += time.monotonic() - _t
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
					_t = time.monotonic()
					in_scope = obj is None or _in_scope(obj, main_obj, cache, scope_stats)
					t_scope += time.monotonic() - _t
			elif exclude_ranges is not None:
				# Bounded-trust positional scoping. Before the trust boundary
				# the chrome inventory is provably complete (see
				# _select_scope), so the chunk is content unless it STARTS
				# inside a chrome landmark — offset arithmetic, no browser
				# calls. At or after the boundary, and on ANY comparison
				# failure, fall back to the identity walk: guessing
				# "not excluded" there is how a nav block becomes article
				# text.
				_t = time.monotonic()
				verdict = _chrome_pos_verdict(
					info, trust_boundary, exclude_ranges, untrusted_ranges,
				)
				if verdict is not None:
					positional_hits += 1
					if verdict is False:
						positional_drops += 1
				if verdict is None:
					if obj is None:
						# NO EVIDENCE AT ALL. Positional could not decide and
						# there is no object to ask, so the identity filter
						# cannot run either.
						#
						# Everywhere else in this module an objectless chunk
						# defaults to IN scope, and that was harmless while
						# identity was the primary mechanism. It is not
						# harmless here: chrome-pos deliberately routes its
						# uncertain chunks to the identity filter AS its
						# safety mechanism, so this is precisely the chunk
						# class the design leans on that filter for — and for
						# these chunks the filter is absent. Defaulting to
						# "content" would hand back exactly the fail-open
						# result the tri-state plumbing exists to prevent
						# (2026-07-18 review).
						#
						# So: out of scope. The chunk still reaches all_nodes,
						# so the depleted-scope net can recover it if this
						# ever strips a page bare, and the cost of being wrong
						# is a missed paragraph rather than a landing in a
						# navigation menu.
						verdict = False
					else:
						verdict = _in_scope(obj, main_obj, cache, scope_stats)
					identity_hits += 1
				in_scope = verdict
				t_scope += time.monotonic() - _t
			else:
				_t = time.monotonic()
				in_scope = obj is None or _in_scope(obj, main_obj, cache, scope_stats)
				identity_hits += 1
				t_scope += time.monotonic() - _t
			# Build the node once, regardless of scope. An out-of-scope node
			# still goes into all_nodes_out so the caller can use it if the
			# scope filter turns out to have rejected the entire document.
			node = _node_for(obj, text)
			pos = None
			if node is not None:
				# Capture a collapsed-to-start position parallel to the node
				# list so get_landing_textinfo can move the caret there later
				# without a second walk.
				try:
					pos = info.copy()
					pos.collapse()
				except Exception:
					pos = None
				if all_nodes_out is not None:
					all_nodes_out.append(node)
					if all_positions_out is not None:
						all_positions_out.append(pos)
					# The notice-keyword regex, evaluated over the whole
					# document. Kept separate from the in-scope match below
					# because a status keyword sitting in a cookie banner or
					# footer must not boost NOTICE confidence on a page whose
					# scope filter worked fine. Only the fallback path (where
					# main_nodes IS the whole document) consults this.
					if (
						notice_match_all_out is not None
						and not notice_match_all_out[0]
						and text
						and _NOTICE_RE.search(text)
					):
						notice_match_all_out[0] = True

			if in_scope:
				consecutive_out = 0
				have_seen_in_scope = True
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
					positions_out.append(pos)
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
	else:
		# The for loop ran to completion without breaking, which means we
		# consumed every one of WALK_NODE_LIMIT iterations rather than
		# reaching the end of the document.
		truncated = True

	# Where the walk's wall clock actually went, per call site. The aggregate
	# walk= number in the perf line cannot name the expensive call, and on the
	# store.payproglobal.com checkout that ambiguity was what blocked a fix.
	#
	# Session log: always. Persistent log: only for a SLOW or TRUNCATED walk.
	# The persistent log self-rotates at 1 MB, so writing a second line for
	# every routine page load would halve the history we keep — and a healthy
	# 40 ms walk has nothing to explain. The slow ones are exactly the ones
	# the user hits days apart, where the session log is long gone.
	walk_total = time.monotonic() - walk_start
	phase_line = (
		f"[TMTS walk-phase] walk_total={walk_total*1000:.0f}ms "
		f"expand={t_expand*1000:.0f}ms text={t_text*1000:.0f}ms "
		f"obj={t_obj*1000:.0f}ms scope={t_scope*1000:.0f}ms "
		f"chunks={raw_seen} parent_derefs={scope_stats.get('parent_derefs', 0)} "
		f"cache_hits={scope_stats.get('cache_hits', 0)} "
		f"cache_misses={scope_stats.get('cache_misses', 0)} "
		f"positional={positional_hits} pos_drops={positional_drops} identity={identity_hits}"
	)
	log.debug(phase_line)
	if truncated or walk_total >= _WALK_PHASE_LOG_THRESHOLD_SEC:
		# Lands immediately BEFORE the [TMTS perf] line for the same
		# detection, which is what ties it to a URL.
		_append_perf_line(phase_line)

	if truncated:
		log.debug(
			f"[TMTS walk-truncated] stopped at raw_seen={raw_seen} "
			f"(node cap {WALK_NODE_LIMIT}, time budget {WALK_TIME_BUDGET_SEC}s) — "
			f"landing will be chosen from the document so far"
		)
	if truncated_out is not None:
		truncated_out[0] = truncated

	if dropped_after_start:
		log.debug(
			f"[TMTS walk-drops] {len(dropped_after_start)} chunk(s) dropped by the "
			f"scope filter after the scoped region started: {dropped_after_start}"
		)

	if positional_out is not None:
		positional_out[0] = positional_drops
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


