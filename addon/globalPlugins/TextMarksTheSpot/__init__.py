# -*- coding: UTF-8 -*-
# Text Marks the Spot — GlobalPlugin entry point.
#
# Hooks event_documentLoadComplete only — fires when a virtual buffer's
# document finishes loading, which covers initial page load and same-tab
# navigation but NOT alt-tab focus restore. We deliberately do not hook
# event_gainFocus: that fires on every focus change (including alt-tab
# back to an existing page), and the TI-identity debounce isn't reliable
# enough to suppress those, leading to perceived freezes when the user
# returns to a browser window.
#
# On ARTICLE / LIST intent, moves the browse-mode caret to the landing
# position and speaks that single paragraph (NVDA's announce-on-
# programmatic-caret-move is unreliable, so we speak it ourselves). The
# speakTextInfo call is the interrupt point — it cuts off NVDA's page-
# load chatter at the moment we have something to say. The user drives
# further reading with the standard NVDA keys (per SPEC.md decisions).
#
# Z key (browse mode) re-runs detection from the current position. It is
# also the manual escape hatch for SPA route changes / dynamic content
# that don't fire event_documentLoadComplete.

import time
from urllib.parse import urlparse

import api
import browseMode
import controlTypes
import globalPluginHandler
import gui
import speech
import textInfos
import ui
import wx
from logHandler import log
from scriptHandler import script, getLastScriptRepeatCount

from . import classifier as cls_mod
from . import config as cfg_mod
from . import feedback as fb_mod
from . import tree_summary as ts_mod
from .detection import web as web_mod


def _hostname_from_url(url: str):
	"""Extract the hostname (e.g. 'forums.audiogames.net') from a URL.
	Returns None for empty / unparseable input."""
	if not url:
		return None
	try:
		return urlparse(url).hostname
	except Exception:
		return None


def _get_current_gesture_display(class_name: str, script_name: str) -> str:
	"""Look up the current keyboard binding for a script and return its
	display label (e.g. "NVDA+Z"). Honors NVDA's user and locale gesture
	remappings so the spoken hotkey stays correct if the user has rebound.
	Falls back to a default string if any part of the lookup fails."""
	default = "NVDA+Z"
	try:
		import inputCore
		# NVDA's gesture maps are dicts: gesture_id -> list of bindings,
		# where each binding is (module_path, class_name, script_name).
		# We walk user first (overrides), then locale (default + locale-
		# specific remappings).
		for gmap in (
			inputCore.manager.userGestureMap,
			inputCore.manager.localeGestureMap,
		):
			try:
				entries = gmap.entries
			except Exception:
				continue
			for gid, bindings in list(entries.items()):
				for binding in bindings:
					if not (isinstance(binding, (tuple, list)) and len(binding) >= 3):
						continue
					if binding[1] == class_name and binding[2] == script_name:
						# Found a binding for our script. NVDA's display
						# formatter returns (source, display_name).
						try:
							display = inputCore.getDisplayTextForGestureIdentifier(gid)
							if isinstance(display, (tuple, list)) and len(display) >= 2:
								return str(display[1])
							return str(display)
						except Exception:
							return default
	except Exception:
		log.exception("[TMTS] gesture-display lookup failed")
	return default


# Translators: NVDA input help category name for Text Marks the Spot.
_CATEGORY = _("Text Marks the Spot")

log.info("[TMTS] module imported; defining GlobalPlugin")


class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	scriptCategory = _CATEGORY

	# Within this many seconds of a previous fire for the same URL, don't
	# refire detection. Catches SPA-ish sites (DDG, Gmail, Twitter) that
	# emit event_documentLoadComplete multiple times for a single visible
	# page load — without this, each emission spawned a fresh round of
	# beeps.
	_REFIRE_COOLDOWN_SEC = 2.0

	# Delay before re-attempting detection when the first attempt produced
	# no actionable result. Lets SPA apps (Gmail, Calendar, Twitter, etc.)
	# finish hydrating async content into NVDA's virtual buffer.
	_RETRY_DELAY_MS = 1500

	def __init__(self):
		super().__init__()
		cfg_mod.load()
		log.info("[TMTS] GlobalPlugin.__init__ — addon loaded, Z binding registered")
		# Cheap fast-path debounce: same TI as last time → already handled.
		self._last_ti = None
		# URL + timestamp debounce: catches the case where NVDA gives us a
		# NEW TI object for what is logically the same page load (common on
		# sites that swap the DOM during hydration / JS routing).
		self._last_url = None
		self._last_fire_time = 0.0
		# Pending wx.CallLater handle for the deferred-retry mechanism.
		# Cancelled whenever a new detection cycle starts (real navigation,
		# Z press, refresh, alt-tab to a new TI).
		self._pending_retry = None
		# Shift+Z support: the textInfo captured at the last successful
		# initial-detection landing. Shift+Z calls updateCaret on this
		# directly — no recalculation. Reset on new TI / page load.
		self._last_initial_landing_info = None
		self._last_initial_landing_url = None

	def terminate(self):
		# Called by NVDA on add-on disable, uninstall, or reload. We must
		# explicitly cancel any pending wx.CallLater and stop the background
		# pulse timer — otherwise they'd fire against a torn-down plugin
		# (logging errors at best, crashing NVDA at worst). Per global
		# CLAUDE.md: never rely on __del__ for screen-reader-adjacent state.
		try:
			self._cancel_pending_retry()
		except Exception:
			log.exception("[TMTS] terminate: cancel_pending_retry failed")
		try:
			fb_mod.progress_stop()
		except Exception:
			log.exception("[TMTS] terminate: progress_stop failed")
		self._last_initial_landing_info = None
		self._last_initial_landing_url = None
		log.info("[TMTS] terminate: clean shutdown complete")
		super().terminate()

	def event_documentLoadComplete(self, obj, nextHandler):
		log.debug(f"[TMTS event] documentLoadComplete obj={obj!r}")
		try:
			self._maybe_fire(obj)
		finally:
			nextHandler()

	def event_treeInterceptor_gainFocus(self, treeInterceptor, nextHandler):
		# Narrower than event_gainFocus — only fires when a TreeInterceptor
		# specifically gains focus, NOT for every focus change inside a
		# document or on alt-tab between windows. This is the right hook
		# for "user just arrived at a browse-mode document".
		#
		# On refresh: NVDA tears down the old TI and creates a new one →
		# event_treeInterceptor_gainFocus fires with a different TI object.
		# On alt-tab back: same TI regains focus → fires, but the URL
		# matches and the cooldown might NOT have elapsed if recent. The
		# TI-identity check in _maybe_fire catches the same-TI case.
		log.debug(f"[TMTS event] treeInterceptor_gainFocus ti={treeInterceptor!r}")
		try:
			self._maybe_fire_ti(treeInterceptor)
		finally:
			nextHandler()

	def _maybe_fire(self, obj, bypass_exclusion=False):
		ti = getattr(obj, "treeInterceptor", None)
		self._maybe_fire_ti(ti, bypass_exclusion=bypass_exclusion)

	def _maybe_fire_ti(self, ti, bypass_exclusion=False):
		if ti is None or not getattr(ti, "isReady", False):
			log.debug(f"[TMTS] _maybe_fire_ti: ti not ready ({ti!r})")
			return
		# A new detection cycle invalidates any pending retry from a prior
		# load — the page state we'd have retried against is gone.
		self._cancel_pending_retry()
		# User-managed site exclusion list. The double-Z one-shot path
		# sets bypass_exclusion=True to force detection regardless of the
		# saved exclusion entry, without modifying the persisted list.
		url = ""
		try:
			url = str(getattr(ti, "documentConstantIdentifier", "") or "")
		except Exception:
			url = ""
		hostname = _hostname_from_url(url)
		if not bypass_exclusion and hostname and cfg_mod.is_site_disabled(hostname):
			log.debug(f"[TMTS] _maybe_fire_ti: site {hostname!r} is on exclusion list — skip")
			return
		# TI-identity check: on alt-tab back to a browser tab, NVDA reuses
		# the existing TreeInterceptor Python object — same object identity
		# means the document hasn't reloaded. Refresh creates a NEW TI
		# (different identity). If your NVDA version does the opposite,
		# log lines below tell us which.
		if ti is self._last_ti:
			log.debug(f"[TMTS] _maybe_fire_ti: same TI as last fire — skip")
			return
		# URL + cooldown catches the SPA-ish case where NVDA gives us a
		# fresh TI for what is actually still the same logical page load
		# (DDG, Gmail, etc. emit duplicate events with new TI objects).
		# `url` was extracted above for the exclusion-list check; reuse it.
		now = time.monotonic()
		elapsed = now - self._last_fire_time
		if (
			url
			and url == self._last_url
			and elapsed < self._REFIRE_COOLDOWN_SEC
		):
			log.debug(f"[TMTS] _maybe_fire_ti: cooldown blocking url={url!r} elapsed={elapsed:.2f}s")
			self._last_ti = ti
			return
		log.debug(f"[TMTS] _maybe_fire_ti: PROCEEDING url={url!r} elapsed={elapsed:.2f}s ti_changed={ti is not self._last_ti}")
		self._last_ti = ti
		self._last_url = url
		self._last_fire_time = now
		# Guardrail #6 pre-check: if the page placed focus on an editable
		# control (DDG home's search box, login pages, etc.), stay totally
		# silent — no working tone, no pulse, no detection. The classifier
		# would otherwise catch this too, but only AFTER we'd already played
		# the working tone, which is exactly what was firing on DDG.
		if ts_mod.is_focus_editable():
			log.debug(f"[TMTS] _maybe_fire_ti: focus editable — skip")
			return
		# Do NOT pre-cancel speech here. Detection runs silently while NVDA
		# does its normal page-load chatter (title, URL, focus). The only
		# moment of interruption is the speakTextInfo call below when we
		# have a landing paragraph — that naturally cuts off NVDA's chatter.
		# Pre-cancelling here silenced NVDA's voice on pages our classifier
		# doesn't act on (form/app/unknown), making the add-on feel broken.
		try:
			self._run_detection(ti)
		except Exception:
			log.exception("[TMTS] detection error")

	def _run_detection(self, ti, is_retry=False):
		# First attempt plays the working tone + pulse. The retry runs
		# silently — no second working tone (user already heard one) and
		# no pulse (the wait between attempts already conveys "thinking").
		if not is_retry:
			fb_mod.working()
			fb_mod.progress_start()
		acted = False
		try:
			summary = ts_mod.build_tree_summary(ti)
			try:
				acted = self._handle_result(ti, summary, is_retry=is_retry)
			finally:
				ts_mod.release_summary(summary)
		finally:
			if not is_retry:
				fb_mod.progress_stop()
		# Real long-term fix for SPA hydration delay: if the first attempt
		# didn't produce a landing, schedule ONE retry. The page may still
		# be loading async content into NVDA's virtual buffer (calendar
		# appointments, Gmail thread list, search results). The retry runs
		# generically — no site-specific code.
		if not is_retry and not acted:
			self._schedule_retry(ti)

	def _schedule_retry(self, ti):
		# Capture the URL at scheduling time so the retry can verify the
		# user hasn't navigated away by the time it fires.
		try:
			expected_url = str(getattr(ti, "documentConstantIdentifier", "") or "")
		except Exception:
			expected_url = ""
		log.debug(f"[TMTS] scheduling retry in {self._RETRY_DELAY_MS}ms for url={expected_url!r}")
		try:
			self._pending_retry = wx.CallLater(
				self._RETRY_DELAY_MS,
				self._fire_retry,
				ti,
				expected_url,
			)
		except Exception:
			log.exception("[TMTS] failed to schedule retry")
			self._pending_retry = None

	def _cancel_pending_retry(self):
		if self._pending_retry is None:
			return
		try:
			if self._pending_retry.IsRunning():
				self._pending_retry.Stop()
		except Exception:
			pass
		self._pending_retry = None

	def _fire_retry(self, ti, expected_url):
		# Runs on the wx main thread after _RETRY_DELAY_MS.
		self._pending_retry = None
		if not getattr(ti, "isReady", False):
			log.debug("[TMTS] retry: TI no longer ready — abandon")
			return
		try:
			current_url = str(getattr(ti, "documentConstantIdentifier", "") or "")
		except Exception:
			current_url = ""
		if current_url != expected_url:
			log.debug(f"[TMTS] retry: url changed (was {expected_url!r}, now {current_url!r}) — abandon")
			return
		log.debug("[TMTS] retry: firing")
		try:
			self._run_detection(ti, is_retry=True)
		except Exception:
			log.exception("[TMTS] retry error")

	def _handle_result(self, ti, summary, is_retry=False):
		# Returns True if we acted (moved caret + spoke). False otherwise.
		# On the first attempt (is_retry=False), a False result triggers a
		# scheduled retry instead of playing not_found right away.
		result = cls_mod.classify(summary)
		# Build a verbose diagnostic snippet about the classifier's view.
		from .classifier import _largest_paragraph_cluster, _largest_heading_cluster, _hero_paragraph_chars
		bsize, bchars = _largest_paragraph_cluster(summary.main_nodes)
		hsize, hlvl = _largest_heading_cluster(summary.main_nodes)
		hero = _hero_paragraph_chars(summary.main_nodes)
		first_node = ""
		if summary.main_nodes:
			n = summary.main_nodes[0]
			first_node = f" first=({n.kind} L{n.level} len={n.text_length} {n.text_preview!r})"

		# Phase 1: act on ARTICLE and LIST.
		#  - ARTICLE → land at first body / hero paragraph (auto-read on)
		#  - LIST → land at first heading in the dominant cluster
		#    (helps the user start scanning headlines without Tab-hunting)
		# Other intents (form, video, app, unknown, silent_focus_honored)
		# stay silent — the user's normal NVDA keys take over.
		# FORM uses a different speech mechanism. The standard browse-mode
		# speakTextInfo path gets swallowed when the page auto-focuses an
		# input (NVDA enters focus mode at the input, and browse-mode
		# speech is suppressed). Google Forms is the canonical example.
		# Instead: announce the form title via ui.message (mode-agnostic),
		# then setFocus on the first form input so NVDA's own focus speech
		# tells the user about the field they're now on. Combined effect:
		# user hears "form title" + "field name role" without depending
		# on whichever mode the page put NVDA into.
		if result.intent == cls_mod.Intent.FORM:
			idx = web_mod.find_form_landing(summary)
			title_text = ""
			if idx is not None and 0 <= idx < len(summary.main_nodes):
				title_text = summary.main_nodes[idx].text_preview.strip()
			if title_text:
				try:
					ui.message(title_text)
				except Exception:
					log.exception("[TMTS] FORM ui.message failed")
			focus_set = ts_mod.set_focus_on_first_form_input(ti)
			log.debug(
				f"[TMTS] FORM: title={title_text!r} focus_set={focus_set} "
				f"url={summary.url!r} retry={is_retry}"
			)
			# Consider it acted if we either announced the title or moved
			# focus. Both are real user-perceptible actions.
			return bool(title_text or focus_set)

		if result.intent == cls_mod.Intent.ARTICLE:
			idx = web_mod.find_article_landing(summary)
		elif result.intent == cls_mod.Intent.LIST:
			idx = web_mod.find_list_landing(summary)
		elif result.intent == cls_mod.Intent.NOTICE:
			idx = web_mod.find_notice_landing(summary)
		elif result.intent == cls_mod.Intent.KEY_RESULT:
			idx = web_mod.find_key_result_landing(summary)
		else:
			log.debug(
				f"[TMTS] no-action: {result.intent.value}({result.confidence:.2f}) "
				f"main={summary.has_main_landmark} nodes={len(summary.main_nodes)} "
				f"art={summary.article_count} form={summary.form_input_count} "
				f"body={bsize}/{bchars} head={hsize}@L{hlvl} hero={hero}"
				f"{first_node} url={summary.url!r} retry={is_retry}"
			)
			# Guardrail #6: stay silent when the page placed focus itself.
			# Other no-action cases either retry (first attempt) or play
			# not_found (final attempt).
			if result.intent != cls_mod.Intent.SILENT_FOCUS_HONORED and is_retry:
				fb_mod.not_found()
			return False
		if idx is None:
			log.debug(
				f"[TMTS] {result.intent.value} but no landing index "
				f"main={summary.has_main_landmark} nodes={len(summary.main_nodes)} "
				f"first_nodes={[(n.kind, n.text_length, n.text_preview[:40]) for n in summary.main_nodes[:6]]} "
				f"url={summary.url!r} retry={is_retry}"
			)
			if is_retry:
				fb_mod.not_found()
			return False
		landing_info = ts_mod.get_landing_textinfo(summary, idx)
		if landing_info is None:
			log.debug(
				f"[TMTS] {result.intent.value} idx={idx} but no textinfo found "
				f"main={summary.has_main_landmark} nodes={len(summary.main_nodes)} "
				f"url={summary.url!r} retry={is_retry}"
			)
			if is_retry:
				fb_mod.not_found()
			return False
		try:
			# Move the browse-mode caret to the landing position. We use
			# updateCaret first; that's the canonical way to position the
			# browse cursor in NVDA. Then we speak the destination so the
			# user gets immediate feedback that we acted (NVDA's natural
			# announce-on-caret-move is unreliable for programmatic moves).
			landing_info.updateCaret()
			# Cancel pending chrome speech (page title, "Skip to content",
			# any in-flight NVDA announcements) so the user hears ONLY our
			# landing paragraph. The cursor has already moved.
			speech.cancelSpeech()
			# Expand to the paragraph so we speak the full landing text.
			speech_info = landing_info.copy()
			speech_info.expand(textInfos.UNIT_PARAGRAPH)
			speech.speakTextInfo(speech_info, reason=controlTypes.OutputReason.CARET)
			landed_node = summary.main_nodes[idx]
			first_eight = [
				(n.kind, n.text_length, n.text_preview[:40])
				for n in summary.main_nodes[:8]
			]
			# Diagnostic: list every paragraph >= 50 chars in main_nodes —
			# these are the candidates the article-landing cascade considered.
			# Helps explain why the addon picked the index it did, especially
			# when first_eight doesn't show the landing.
			substantial = [
				(i, n.text_length, n.text_preview[:50])
				for i, n in enumerate(summary.main_nodes)
				if n.kind == "paragraph" and n.text_length >= 50
			]
			# Diagnostic: every heading in main_nodes (kind+idx+level+preview).
			# Combined with `substantial` this gives the full picture of what
			# the cascade saw.
			headings = [
				(i, n.level, n.text_preview[:40])
				for i, n in enumerate(summary.main_nodes)
				if n.kind == "heading"
			]
			log.debug(
				f"[TMTS] moved caret to idx={idx} kind={landed_node.kind} "
				f"len={landed_node.text_length} preview={landed_node.text_preview[:60]!r} "
				f"first_8={first_eight} substantial={substantial} headings={headings} "
				f"nodes={len(summary.main_nodes)} url={summary.url!r} retry={is_retry}"
			)
			# Save the landing textInfo so Shift+Z can snap back to it
			# later without recalculating. Copy first so the saved object
			# survives even if the original is mutated by later cursor
			# moves elsewhere.
			try:
				self._last_initial_landing_info = landing_info.copy()
				self._last_initial_landing_url = summary.url
			except Exception:
				log.exception("[TMTS] failed to save Shift+Z return-to-landing position")
				self._last_initial_landing_info = None
				self._last_initial_landing_url = None
			return True
		except Exception:
			log.exception("[TMTS] cursor move failed")
			return False

	@script(
		# Translators: input help for the re-run-detection script.
		description=_("Re-run content detection on the current document."),
		gesture="kb:z",
		category=_CATEGORY,
	)
	def script_retrigger(self, gesture):
		# Only act when the user is in a browse-mode document (browser
		# page, message body, etc.). In edit fields, terminals, native
		# apps, the Z key should pass through to the underlying app so
		# it gets typed normally.
		focus = api.getFocusObject()
		ti = getattr(focus, "treeInterceptor", None) if focus is not None else None
		if (
			ti is None
			or not isinstance(ti, browseMode.BrowseModeDocumentTreeInterceptor)
			or getattr(ti, "passThrough", False)
		):
			# Not in active browse mode (no TI, wrong TI type, or browse mode
			# is in focus/forms mode where keys go to the page). Let the host
			# app receive the Z keystroke.
			gesture.send()
			return
		# Determine the current hostname / exclusion state once.
		url = ""
		try:
			ti = getattr(focus, "treeInterceptor", None)
			if ti is not None:
				url = str(getattr(ti, "documentConstantIdentifier", "") or "")
		except Exception:
			url = ""
		hostname = _hostname_from_url(url)
		is_excluded = bool(hostname) and cfg_mod.is_site_disabled(hostname)
		# NVDA's getLastScriptRepeatCount() returns 0 on first press, 1
		# on second press within ~500 ms, etc. A double-Z is the user's
		# explicit "force detection this one time on this excluded site"
		# — we bypass the exclusion check without changing the saved list.
		is_double_press = getLastScriptRepeatCount() >= 1
		# All Z paths bypass the URL+cooldown debounce — Z is an explicit
		# user request to redo detection.
		self._last_ti = None
		self._last_url = None
		self._last_fire_time = 0.0
		if is_double_press and is_excluded:
			# No spoken announcement here — the working tone + the
			# subsequent detection-result speech are sufficient feedback
			# that the bypass fired. A verbal "One-time detection on
			# <hostname>" was too long in real use; the user already knows
			# they pressed Z twice deliberately.
			self._maybe_fire(focus, bypass_exclusion=True)
			return
		if is_excluded:
			toggle_key = _get_current_gesture_display("GlobalPlugin", "toggleSiteExclusion")
			# Translators: spoken when Z is pressed on a site that's in
			# the exclusion list. {hostname} is the website, {hotkey} is
			# the current binding for the exclusion toggle (NVDA+Z by
			# default, but reflects user remappings).
			ui.message(_(
				"Text Marks the Spot is disabled for {hostname}. "
				"Press {hotkey} to remove this site from the exclusion list, "
				"or press Z twice for a one-time detection."
			).format(hostname=hostname, hotkey=toggle_key))
			return
		# Z = scan forward from the user's current cursor position for the
		# next substantial content paragraph. Independent of whether or
		# where the addon previously landed: Z always starts from where
		# the user actually is right now. NVDA's H handles next-heading
		# already; Z deliberately skips headings to add value NVDA's
		# built-in keys don't.
		self._scan_forward_from_caret(focus)

	def _scan_forward_from_caret(self, focus):
		# Build a fresh tree summary, find the next content paragraph
		# strictly after the current caret position, and move there. The
		# scan uses the same chrome filters as the article-landing cascade
		# (tag lists, share-link payloads, accessibility-instruction text,
		# PDF-viewer disclaimers) so Z lands on content, not chrome.
		#
		# If no eligible paragraph is found below the cursor, "Nothing else
		# to land on" is announced and the cursor stays put. No wrapping.
		ti = getattr(focus, "treeInterceptor", None) if focus is not None else None
		if ti is None or not getattr(ti, "isReady", False):
			return
		# Audible acknowledgment that Z was received, before the (potentially
		# slow) tree walk and caret-position search.
		fb_mod.working()
		try:
			summary = ts_mod.build_tree_summary(ti)
			try:
				try:
					caret_info = ti.makeTextInfo(textInfos.POSITION_CARET)
				except Exception:
					log.exception("[TMTS] Z: failed to read caret position")
					# Translators: spoken when Z can't determine the current
					# cursor position (rare).
					ui.message(_("Cannot scan from the current position."))
					return
				# Find the highest main_node index whose textInfo starts at
				# or before the current caret. That's the user's "current"
				# position — the next content scan starts at index+1.
				current_idx = -1
				for i in range(len(summary.main_nodes)):
					node_info = ts_mod.get_landing_textinfo(summary, i)
					if node_info is None:
						continue
					try:
						cmp = node_info.compareEndPoints(caret_info, "startToStart")
					except Exception:
						continue
					if cmp <= 0:
						current_idx = i
					else:
						break
				next_idx = web_mod.find_next_content_landing(summary, current_idx)
				if next_idx is None:
					# Translators: spoken when Z is pressed and no more
					# content paragraphs exist below the cursor.
					ui.message(_("Nothing else to land on."))
					return
				landing_info = ts_mod.get_landing_textinfo(summary, next_idx)
				if landing_info is None:
					# Translators: spoken when the next-content position
					# could not be resolved (rare — usually means the
					# tree changed underneath us).
					ui.message(_("Cannot move to the next content paragraph."))
					return
				landing_info.updateCaret()
				speech.cancelSpeech()
				speech_info = landing_info.copy()
				speech_info.expand(textInfos.UNIT_PARAGRAPH)
				speech.speakTextInfo(speech_info, reason=controlTypes.OutputReason.CARET)
				landed_node = summary.main_nodes[next_idx]
				log.debug(
					f"[TMTS] Z scan-from-caret to idx={next_idx} kind={landed_node.kind} "
					f"len={landed_node.text_length} preview={landed_node.text_preview[:60]!r} "
					f"current_idx={current_idx} url={summary.url!r}"
				)
			finally:
				ts_mod.release_summary(summary)
		except Exception:
			log.exception("[TMTS] Z scan-from-caret failed")

	@script(
		# Translators: input help for the Shift+Z return-to-landing gesture.
		description=_("Return the cursor to the add-on's last detected landing position on this page."),
		gesture="kb:shift+z",
		category=_CATEGORY,
	)
	def script_returnToLanding(self, gesture):
		# Snap back to the position the addon's initial detection chose.
		# No recalculation — uses the textInfo captured at detection time.
		# Outside browse mode, pass through (uppercase Z).
		focus = api.getFocusObject()
		ti = getattr(focus, "treeInterceptor", None) if focus is not None else None
		if (
			ti is None
			or not isinstance(ti, browseMode.BrowseModeDocumentTreeInterceptor)
			or getattr(ti, "passThrough", False)
		):
			gesture.send()
			return
		# Verify the saved landing is for the page we're currently on.
		url = ""
		try:
			url = str(getattr(ti, "documentConstantIdentifier", "") or "")
		except Exception:
			url = ""
		if (
			self._last_initial_landing_info is None
			or self._last_initial_landing_url != url
		):
			# Translators: spoken when Shift+Z has no saved landing for
			# the current page (no detection has run, or URL changed).
			ui.message(_("No saved landing on this page."))
			return
		fb_mod.working()
		try:
			self._last_initial_landing_info.updateCaret()
			speech.cancelSpeech()
			speech_info = self._last_initial_landing_info.copy()
			speech_info.expand(textInfos.UNIT_PARAGRAPH)
			speech.speakTextInfo(speech_info, reason=controlTypes.OutputReason.CARET)
			log.debug(f"[TMTS] Shift+Z return-to-landing on url={url!r}")
		except Exception:
			log.exception("[TMTS] Shift+Z failed")
			# Translators: spoken when the saved landing position could not
			# be restored (rare — usually means the page changed).
			ui.message(_("Could not return to the saved landing."))

	@script(
		# Translators: input help for the NVDA+Z site-exclusion toggle.
		description=_("Add or remove the current website from the Text Marks the Spot exclusion list."),
		gesture="kb:NVDA+z",
		category=_CATEGORY,
	)
	def script_toggleSiteExclusion(self, gesture):
		# Only act when the user is in a browse-mode document. Outside
		# browse mode (terminals, app fields), NVDA+Z has no meaning for
		# us — pass it through so the host application can use it.
		focus = api.getFocusObject()
		ti = getattr(focus, "treeInterceptor", None) if focus is not None else None
		if (
			ti is None
			or not isinstance(ti, browseMode.BrowseModeDocumentTreeInterceptor)
			or getattr(ti, "passThrough", False)
		):
			gesture.send()
			return
		# Identify the current site.
		url = ""
		try:
			url = str(getattr(ti, "documentConstantIdentifier", "") or "")
		except Exception:
			url = ""
		hostname = _hostname_from_url(url)
		if not hostname:
			# Translators: spoken when NVDA+Z can't identify the site.
			ui.message(_("Unable to determine the website for exclusion."))
			return
		# Toggle: dialog confirms the add or remove action.
		currently_excluded = cfg_mod.is_site_disabled(hostname)
		if currently_excluded:
			# Translators: dialog prompt — confirms removing a site from the exclusion list.
			prompt = _("Remove {hostname} from the Text Marks the Spot exclusion list?").format(hostname=hostname)
		else:
			# Translators: dialog prompt — confirms adding a site to the exclusion list.
			prompt = _("Add {hostname} to the Text Marks the Spot exclusion list?").format(hostname=hostname)

		def _show_dialog():
			with wx.MessageDialog(
				gui.mainFrame,
				prompt,
				# Translators: dialog title for the site-exclusion confirm.
				_("Text Marks the Spot — Site Exclusion"),
				style=wx.YES_NO | wx.ICON_QUESTION,
			) as dialog:
				result = dialog.ShowModal()
			if result != wx.ID_YES:
				# Translators: spoken when the user cancels the
				# site-exclusion dialog (clicks No instead of Yes).
				ui.message(_("No change. Exclusion list unchanged."))
				return
			if currently_excluded:
				cfg_mod.remove_disabled_site(hostname)
				# Translators: spoken confirmation after removal from exclusion list.
				ui.message(_("Removed {hostname} from exclusion list.").format(hostname=hostname))
			else:
				cfg_mod.add_disabled_site(hostname)
				# Translators: spoken confirmation after addition to exclusion list.
				ui.message(_("Added {hostname} to exclusion list.").format(hostname=hostname))

		wx.CallAfter(_show_dialog)
