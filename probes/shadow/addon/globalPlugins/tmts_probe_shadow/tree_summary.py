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

from typing import Optional

try:
	import api
	import controlTypes
	import textInfos
	_NVDA_AVAILABLE = True
except ImportError:
	_NVDA_AVAILABLE = False

try:
	from .classifier import TreeSummary, MainNode
except ImportError:
	from classifier import TreeSummary, MainNode


# Caps on the document walk. Real pages can be huge (Wikipedia has thousands
# of paragraph units); the speed budget is <50ms per detection (SPEC). 1000
# nodes is a starting cap — tune after we measure on real pages.
WALK_NODE_LIMIT = 1000

# Text-content roles we treat as paragraph candidates when walking by
# UNIT_PARAGRAPH. Non-content roles (graphics, separators, unknown) get
# silently skipped so they don't pollute the paragraph count.
_PARAGRAPH_SKIP_ROLES_NAMES = (
	"GRAPHIC", "SEPARATOR", "UNKNOWN",
)

# Roles that count as a focused editable control for guardrail #6.
_EDITABLE_FOCUS_ROLES_NAMES = (
	"EDITABLETEXT", "COMBOBOX", "LISTBOX",
	"RADIOBUTTON", "CHECKBOX",
)


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

	main_obj = _find_main_landmark_obj(treeInterceptor)
	# Cache _in_scope decisions across all helpers within this single
	# build_tree_summary call. id(obj) → bool. Discarded on return.
	# Saves redundant parent-chain walks when many leaf objects share
	# ancestors (e.g., all paragraphs inside main share the path to main).
	scope_cache: dict = {}

	summary = TreeSummary()
	summary.url = _get_document_url(treeInterceptor)
	summary.focused_control_is_editable = _is_focus_editable()
	summary.has_main_landmark = main_obj is not None
	summary.article_count = _count_in_scope(treeInterceptor, "article", main_obj, scope_cache)
	summary.primary_video = _has_video_in_scope(treeInterceptor, main_obj, scope_cache)
	summary.form_input_count = _count_in_scope(treeInterceptor, "formField", main_obj, scope_cache)
	summary.interactive_control_count = sum(
		_count_in_scope(treeInterceptor, t, main_obj, scope_cache)
		for t in ("button", "link", "edit", "comboBox", "checkBox", "radioButton")
	)
	summary.main_nodes = _walk_main_nodes(treeInterceptor, main_obj, scope_cache)
	return summary


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


def _find_main_landmark_obj(treeInterceptor):
	# Returns the first <main> landmark NVDAObject in the document, or None.
	try:
		for item in treeInterceptor._iterNodesByType("landmark"):
			obj = getattr(item, "obj", None)
			if obj is None:
				continue
			if _landmark_type(obj) == "main":
				return obj
	except Exception:
		pass
	return None


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


def _count_in_scope(treeInterceptor, item_type: str, main_obj, cache: dict) -> int:
	# Count quick-nav items of item_type that pass _in_scope.
	try:
		count = 0
		for item in treeInterceptor._iterNodesByType(item_type):
			obj = getattr(item, "obj", None)
			if obj is not None and _in_scope(obj, main_obj, cache):
				count += 1
		return count
	except Exception:
		return 0


def _has_video_in_scope(treeInterceptor, main_obj, cache: dict) -> bool:
	# Check whether any <video>-like role appears in the in-scope region.
	# Falls back to recursive role scan if QuickNav doesn't expose video.
	try:
		for item in treeInterceptor._iterNodesByType("embeddedObject"):
			obj = getattr(item, "obj", None)
			if obj is None:
				continue
			role_name = getattr(obj.role, "name", None) or str(obj.role)
			if "VIDEO" in role_name and _in_scope(obj, main_obj, cache):
				return True
	except Exception:
		pass
	# Fallback: scan the subtree of main (or root if no main).
	try:
		scope_root = main_obj if main_obj is not None else treeInterceptor.rootNVDAObject
		return _role_present_in_tree(scope_root, "VIDEO")
	except Exception:
		return False


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


def _walk_main_nodes(treeInterceptor, main_obj, cache: dict) -> list[MainNode]:
	# Walk the whole document by UNIT_PARAGRAPH; emit only nodes that
	# pass _in_scope (inside <main> if present, or outside chrome
	# landmarks if not). Bail out once we've had _OUT_OF_SCOPE_TOLERANCE
	# consecutive out-of-scope nodes (most likely we're in the footer).
	result: list[MainNode] = []
	try:
		info = treeInterceptor.makeTextInfo(textInfos.POSITION_FIRST)
	except Exception:
		return result

	consecutive_out = 0
	have_seen_in_scope = False
	for _ in range(WALK_NODE_LIMIT):
		try:
			info.expand(textInfos.UNIT_PARAGRAPH)
			text = info.text or ""
			obj = info.NVDAObjectAtStart

			in_scope = obj is None or _in_scope(obj, main_obj, cache)
			if in_scope:
				consecutive_out = 0
				have_seen_in_scope = True
				node = _node_for(obj, text)
				if node is not None:
					result.append(node)
			else:
				consecutive_out += 1
				# Only bail AFTER we've seen at least one in-scope node;
				# otherwise we might quit before reaching main (the nav/
				# banner at the top of the document can easily exceed
				# the tolerance before main starts).
				if have_seen_in_scope and consecutive_out > _OUT_OF_SCOPE_TOLERANCE:
					break

			info.collapse(end=True)
			moved = info.move(textInfos.UNIT_PARAGRAPH, 1)
			if not moved:
				break
		except Exception:
			break

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


# ---------------------------------------------------------------------------
# Recursive helper — used by video detection until we have a better probe.
# ---------------------------------------------------------------------------

def _role_present_in_tree(obj, role_substring: str, max_depth: int = 6) -> bool:
	if obj is None or max_depth <= 0:
		return False
	role_name = getattr(obj.role, "name", None) or str(obj.role)
	if role_substring in role_name:
		return True
	try:
		child = obj.firstChild
	except Exception:
		child = None
	while child is not None:
		if _role_present_in_tree(child, role_substring, max_depth - 1):
			return True
		try:
			child = child.next
		except Exception:
			break
	return False
