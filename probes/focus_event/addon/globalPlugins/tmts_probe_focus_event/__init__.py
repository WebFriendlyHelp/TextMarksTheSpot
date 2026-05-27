# -*- coding: UTF-8 -*-
# TMTS probe 1 — observe focus events and treeInterceptor transitions.
#
# Background: NVDA source review (eventHandler.py, doPreGainFocus) showed
# that `event_treeInterceptor_gainFocus` is NOT dispatched to GlobalPlugins
# — it's called directly on the treeInterceptor by NVDA's core. So our
# trigger has to be `event_gainFocus` on a GlobalPlugin, with our own
# bookkeeping to detect when the treeInterceptor object identity changes.
#
# This probe logs every focus event plus whether the treeInterceptor changed,
# so we can verify the bookkeeping matches what we expect on real pages.
# Read-only. No speech, no tones, no UI. Log lines only.

import time

import globalPluginHandler
from logHandler import log


class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	def __init__(self):
		super().__init__()
		self._last_ti = None

	def event_gainFocus(self, obj, nextHandler):
		ts = time.monotonic()
		try:
			ti = getattr(obj, "treeInterceptor", None)
			ti_changed = ti is not self._last_ti
			ti_ready = bool(getattr(ti, "isReady", False)) if ti is not None else False
			role = getattr(obj, "role", None)
			url = ""
			if ti is not None:
				url = getattr(ti, "documentConstantIdentifier", "") or ""
			log.info(
				f"[TMTS probe 1 focus] t={ts:.3f} ti_changed={ti_changed} "
				f"ti_ready={ti_ready} ti_id={id(ti) if ti else 0} "
				f"obj_role={role!r} url={url!r}"
			)
			if ti_changed and ti is not None:
				self._last_ti = ti
		except Exception as e:
			log.warning(f"[TMTS probe 1 focus] error: {e}")
		nextHandler()

	def event_documentLoadComplete(self, obj, nextHandler):
		ts = time.monotonic()
		try:
			ti = getattr(obj, "treeInterceptor", None)
			url = getattr(ti, "documentConstantIdentifier", "") if ti else ""
			log.info(f"[TMTS probe 1 load] t={ts:.3f} url={url!r}")
		except Exception as e:
			log.warning(f"[TMTS probe 1 load] error: {e}")
		nextHandler()
