# -*- coding: UTF-8 -*-
# TMTS shadow-mode diagnostic.
#
# Runs the full pipeline on every new document but does NOT act on it.
# Logs what tree_summary built, what classifier returned, and (for ARTICLE
# intent) where the article landing strategy would put the cursor.
#
# Read-only. No cursor moves, no speech, no tones.
# Install, browse for a few minutes, then grep NVDA log for [TMTS shadow].

import time

import wx

import api
import globalPluginHandler
from logHandler import log
from scriptHandler import script

from . import classifier as cls_mod
from . import tree_summary as ts_mod
from .detection import web as web_mod

# Defer detection by this many ms after the document-load / focus event.
# Empirically necessary: when the events fire, NVDA's virtual buffer landmark
# index is often not yet populated on large pages, so _iterNodesByType
# ("landmark") returns nothing and our <main>-scoping silently fails. 200ms
# gives Firefox/NVDA time to fully wire the accessibility tree.
# Dual-fire diagnostic: we run detection twice per page so we can see which
# timing wins for each site. Some pages have landmarks indexed immediately
# (wdbo, webfriendlyhelp); others need a few seconds (nfb). And some lose
# landmarks to JS DOM mutation after a delay (wdbo). Two data points per
# page tells us what production needs.
_LATE_FIRE_DELAY_MS = 5000


def _dump_landmarks(ti):
	# One-line landmark summary: count, whether 'main' is present, list of types.
	try:
		types = []
		has_main = False
		for item in ti._iterNodesByType("landmark"):
			obj = getattr(item, "obj", None)
			if obj is None:
				continue
			lm = (
				getattr(obj, "landmark", None)
				or getattr(obj, "landmarkType", None)
				or ""
			)
			lm_str = str(lm) if lm else ""
			if lm_str:
				types.append(lm_str)
			if lm_str.lower() == "main":
				has_main = True
		return has_main, types
	except Exception:
		return False, []


class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	def __init__(self):
		super().__init__()
		self._last_ti = None

	@script(
		description="TMTS probe: deep landmark/structure dump for current page",
		gesture="kb:NVDA+shift+l",
	)
	def script_deep_dump(self, gesture):
		focus = api.getFocusObject()
		ti = getattr(focus, "treeInterceptor", None) if focus else None
		if ti is None:
			log.info("[TMTS deep] no treeInterceptor on current focus")
			return
		url = getattr(ti, "documentConstantIdentifier", "") or ""
		log.info(f"[TMTS deep] url={url!r}")
		# Try every interesting QuickNav type and dump what we get.
		types_to_probe = (
			"landmark", "article", "main", "region", "heading", "frame",
			"embeddedObject", "graphic",
		)
		for t in types_to_probe:
			try:
				items = list(ti._iterNodesByType(t))
			except Exception as e:
				log.info(f"[TMTS deep] {t}: ERROR {e}")
				continue
			log.info(f"[TMTS deep] {t}: count={len(items)}")
			for i, item in enumerate(items[:5]):
				obj = getattr(item, "obj", None)
				if obj is None:
					log.info(f"[TMTS deep]   [{i}] (no .obj)")
					continue
				attrs = {
					"role": str(getattr(obj.role, "name", obj.role)),
					"landmark": getattr(obj, "landmark", None),
					"landmarkType": getattr(obj, "landmarkType", None),
					"name": (getattr(obj, "name", "") or "")[:50],
					"roleText": getattr(obj, "roleText", None),
				}
				log.info(f"[TMTS deep]   [{i}] {attrs}")

	def event_gainFocus(self, obj, nextHandler):
		try:
			self._maybe_schedule(obj, source="gainFocus")
		finally:
			nextHandler()

	def event_documentLoadComplete(self, obj, nextHandler):
		try:
			self._maybe_schedule(obj, source="docLoad")
		finally:
			nextHandler()

	def _maybe_schedule(self, obj, source):
		# Dual-fire: immediate AND delayed. Different sites have different
		# landmark-index timing; we log both so we can compare.
		ti = getattr(obj, "treeInterceptor", None)
		if ti is None or ti is self._last_ti or not getattr(ti, "isReady", False):
			return
		self._last_ti = ti
		# Early fire — synchronous, before JS DOM mutations.
		self._fire(ti, f"{source}/early")
		# Late fire — after a beat, lets slow-indexing sites catch up.
		# Resolve TI fresh at fire time in case the page replaced it.
		wx.CallLater(_LATE_FIRE_DELAY_MS, self._fire_late, source)

	def _fire_late(self, source):
		focus = api.getFocusObject()
		ti = getattr(focus, "treeInterceptor", None) if focus is not None else None
		if ti is None or not getattr(ti, "isReady", False):
			log.info(f"[TMTS shadow] [{source}/late] no live TI at fire time")
			return
		self._fire(ti, f"{source}/late")

	def _fire(self, ti, source):
		try:

			t0 = time.monotonic()
			summary = ts_mod.build_tree_summary(ti)
			t1 = time.monotonic()
			result = cls_mod.classify(summary)
			t2 = time.monotonic()
			landing_idx = None
			if result.intent == cls_mod.Intent.ARTICLE:
				landing_idx = web_mod.find_article_landing(summary)
			t3 = time.monotonic()

			landing_preview = ""
			if landing_idx is not None and 0 <= landing_idx < len(summary.main_nodes):
				n = summary.main_nodes[landing_idx]
				landing_preview = f" land=[{n.kind} L{n.level} len={n.text_length}]"
			has_main, landmark_types = _dump_landmarks(ti)
			log.info(
				f"[TMTS shadow] [{source}] {result.intent.value}({result.confidence:.2f})"
				f" main={has_main}"
				f" lm={len(landmark_types)}({','.join(landmark_types[:8])})"
				f" nodes={len(summary.main_nodes)}"
				f" art={summary.article_count}"
				f" form={summary.form_input_count}"
				f" idx={landing_idx}{landing_preview}"
				f" {1000 * (t3 - t0):.0f}ms"
				f" url={summary.url!r}"
			)
		except Exception as e:
			log.warning(f"[TMTS shadow] error: {e}", exc_info=True)
