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
import weakref
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

from . import classifier as clsMod
from . import config as cfgMod
from . import feedback as fbMod
from . import treeSummary as tsMod
# Diagnostic logging is opt-in; see treeSummary._GatedDebugLog.
from .treeSummary import dlog
from .detection import web as webMod


def _hostnameFromUrl(url: str):
	"""Extract the hostname (e.g. 'forums.audiogames.net') from a URL.
	Returns None for empty / unparseable input."""
	if not url:
		return None
	try:
		return urlparse(url).hostname
	except Exception:
		return None


def _getCurrentGestureDisplay(className: str, script_name: str) -> str:
	"""Look up the current keyboard binding for a script and return its
	display label (e.g. "NVDA+Z"). Honors NVDA's user and locale gesture
	remappings so the spoken hotkey stays correct if the user has rebound.
	Falls back to a default string if any part of the lookup fails."""
	default = "NVDA+Z"
	try:
		import inputCore
		# NVDA's gesture maps are dicts: gesture_id -> list of bindings,
		# where each binding is (module_path, className, script_name).
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
					if binding[1] == className and binding[2] == script_name:
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

# URL schemes that mean "this is a web document". Mirrors the allowlist NVDA
# itself uses to tell web pages from email messages
# (browseMode.py:2406-2413 -- "we don't want to remember caret positions for
# email messages, etc."). Mail clients expose imap: / mailbox: / news: URLs, so
# this keeps us out of Thunderbird message previews without hard-coding an app
# name, and keeps us out of the next mail client too.
_WEB_URL_SCHEMES = ("http:", "https:", "file:")


def _isWebDocument(ti) -> bool:
	"""True if this TreeInterceptor is a web document (not an email message).

	Only consulted on the readiness-poll path, which is the one place we act on a
	document NVDA did not hand us a TreeInterceptor for up front. Email detection
	is deferred and undesigned; moving the user's cursor inside their inbox would
	be exactly the "act when unsure" the guardrails forbid.
	"""
	try:
		url = str(getattr(ti, "documentConstantIdentifier", "") or "").strip().lower()
	except Exception:
		return False
	if not url:
		return False
	return url.startswith(_WEB_URL_SCHEMES)


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

	# Delay between attempts when the walk produced NO NODES AT ALL. That is not
	# a page without content, it is a virtual buffer that does not exist yet.
	#
	# Sized against a HARD CEILING of 2.5 s from page load to the failure tone
	# (Casey's call, 2026-07-18: waiting longer than that to be told "nothing
	# found" is worse than the occasional miss). Three looks at 0 / 1.25 / 2.5 s
	# fit inside it because an EMPTY walk is nearly free -- the two IMDb misses
	# took 2 ms and 4 ms, there being nothing to walk -- so these delays are
	# essentially the whole wall clock. A tree WITH nodes keeps the original
	# single 1500 ms retry; those walks cost seconds and must not be repeated.
	_EMPTY_RETRY_DELAY_MS = 1250

	# Total detection attempts per page load, including the first. Only an
	# EMPTY tree earns a third: a page that yielded real nodes and still had no
	# landing has genuinely answered, and re-walking it costs seconds on
	# exactly the heavy pages that can least afford it. Bounded so a document
	# that never builds cannot retry forever.
	#
	# This does NOT have to catch every slow page. A buffer that finishes later
	# fires its own documentLoadComplete and lands normally, which is exactly
	# what rescued IMDb at +4 s while these attempts were still coming up empty.
	_MAX_DETECTION_ATTEMPTS = 3

	# Readiness poll for a TreeInterceptor that exists but hasn't finished
	# building. 250ms x 12 = up to 3s of waiting, which covers the observed
	# BibleGateway case (the buffer was still not ready 14s after the first
	# documentLoadComplete, but a SECOND documentLoadComplete arrives on
	# these pages and restarts the poll — we do not need one poll chain to
	# span the whole load). Bounded so a document that never becomes ready
	# (a non-browse-mode frame) can't leave a timer chain running forever.
	_READY_POLL_MS = 250
	_READY_POLL_MAX_ATTEMPTS = 12

	# After a SUCCESSFUL landing on a URL, suppress further AUTOMATIC
	# detections for that same URL for this long. SPA pages can re-render
	# and fire fresh documentLoadComplete events well past the 2 s refire
	# cooldown (Zoom webinar registration re-rendered at +9 s and +34 s
	# when it swapped in the signed-in profile), and the re-rendered tree
	# is often WORSE for landing (Zoom collapses the description into
	# accordions) — re-detecting yanked the user off a good landing into
	# the middle of the form. One page visit, one landing. The Z key
	# always re-runs on demand; a real navigation (URL change) is a new
	# page and lands normally.
	_LANDED_SUPPRESS_SEC = 120.0

	def __init__(self):
		super().__init__()
		cfgMod.load()
		log.info("[TMTS] GlobalPlugin.__init__ — addon loaded, Z binding registered")
		# Last TreeInterceptor we fired on, held WEAKLY.
		#
		# A strong reference here pins a dead TreeInterceptor, its rootNVDAObject,
		# and its COM proxies in memory for as long as the add-on runs. NVDA itself
		# stores TI references on NVDAObjects as weakrefs precisely so killed
		# interceptors can be collected (NVDAObjects/__init__.py:461,467). We were
		# leaking one per browsing session.
		#
		# Paired with the URL below: "same document" means same TI AND same URL.
		# The TI alone is NOT a document identity -- NVDA reuses the interceptor
		# across navigations and the URL changes in place underneath it.
		self._lastTiRef = None
		# URL + timestamp debounce: catches the case where NVDA gives us a
		# NEW TI object for what is logically the same page load (common on
		# sites that swap the DOM during hydration / JS routing).
		self._lastUrl = None
		self._lastFireTime = 0.0
		# Post-landing suppression state: the URL we last successfully
		# landed on and when. See _LANDED_SUPPRESS_SEC.
		self._lastLandedUrl = None
		self._lastLandedTime = 0.0
		# Pending wx.CallLater handle for the deferred-retry mechanism.
		# Cancelled whenever a new detection cycle starts (real navigation,
		# Z press, refresh, alt-tab to a new TI).
		self._pendingRetry = None
		# Pending wx.CallLater handle for the TreeInterceptor readiness poll.
		self._pendingReadyPoll = None
		# URLs seen this NVDA session (url -> monotonic timestamp). Backs
		# the restored-position gate: Back navigation by definition returns
		# to a URL we've already processed, so "caret mid-page" only means
		# "restored position" when the URL is in this set. First visits to
		# pages whose caret happens to initialize below the top (halturner
		# radioshow article pages) must still land.
		self._seenUrls = {}
		# Shift+Z support: the textInfo captured at the last successful
		# initial-detection landing. Shift+Z calls updateCaret on this
		# directly — no recalculation. Reset on new TI / page load.
		self._lastInitialLandingInfo = None
		self._lastInitialLandingUrl = None

	def terminate(self):
		# Called by NVDA on add-on disable, uninstall, or reload. We must
		# explicitly cancel any pending wx.CallLater and stop the background
		# pulse timer — otherwise they'd fire against a torn-down plugin
		# (logging errors at best, crashing NVDA at worst). Per global
		# CLAUDE.md: never rely on __del__ for screen-reader-adjacent state.
		try:
			self._cancelPendingRetry()
		except Exception:
			log.exception("[TMTS] terminate: cancel_pending_retry failed")
		try:
			self._cancelPendingReadyPoll()
		except Exception:
			log.exception("[TMTS] terminate: cancel_pending_ready_poll failed")
		try:
			fbMod.progressStop()
		except Exception:
			log.exception("[TMTS] terminate: progressStop failed")
		self._lastInitialLandingInfo = None
		self._lastInitialLandingUrl = None
		log.info("[TMTS] terminate: clean shutdown complete")
		super().terminate()

	def event_documentLoadComplete(self, obj, nextHandler):
		dlog.debug(f"[TMTS event] documentLoadComplete obj={obj!r}")
		try:
			self._maybeFire(obj)
		finally:
			nextHandler()

	# NOTE: there used to be an event_treeInterceptor_gainFocus handler here,
	# described as our second trigger and our backstop for a missed
	# documentLoadComplete. It NEVER FIRED. Not "not on this build" -- it cannot
	# fire, on any NVDA version, by construction.
	#
	# Verified in NVDA source by two independent reviews: global plugins only
	# receive events dispatched through eventHandler.executeEvent ->
	# _EventExecuter.gen (eventHandler.py:141-167). treeInterceptor_gainFocus is
	# never dispatched that way. It is a plain METHOD that core calls directly on
	# the TreeInterceptor object itself (eventHandler.py:425, and
	# virtualBuffers/__init__.py:611 and :620). Its base definition
	# (browseMode.py:319-324) documents it as "only fired upon entering this
	# treeInterceptor when it was not the current treeInterceptor before".
	#
	# The field data agrees exactly: 0 firings across 31 page loads.
	#
	# So documentLoadComplete is our ONLY trigger and always has been. It never
	# had a backstop. Do not re-add this handler; if you want the "browse document
	# became ready" moment, the poll in _maybeFire is the supported route.

	def _lastTi(self):
		"""The last TreeInterceptor we fired on, or None if it has been collected.

		Held weakly (see __init__). A dead TI can never compare equal to a live
		one, so a collected referent simply means "no match" -- which is the
		correct answer anyway.
		"""
		ref = self._lastTiRef
		if ref is None:
			return None
		try:
			return ref()
		except Exception:
			return None

	def _setLastTi(self, ti):
		try:
			self._lastTiRef = weakref.ref(ti) if ti is not None else None
		except TypeError:
			# Not weak-referenceable. Rather than take a strong reference (which is
			# the leak we are fixing), forget it -- the URL gate still debounces.
			dlog.debug("[TMTS] TI is not weak-referenceable; not remembering it")
			self._lastTiRef = None

	def _maybeFire(self, obj, bypassExclusion=False):
		ti = getattr(obj, "treeInterceptor", None)
		# documentLoadComplete is our ONLY trigger (the treeInterceptor_gainFocus
		# hook never existed in practice -- see the note above), so anything we
		# drop here is dropped forever.
		#
		# Two ways the TI isn't usable at event time:
		#   - it EXISTS but isn't built yet. documentLoadComplete means "the DOM
		#     finished loading", which is not when NVDA finishes constructing the
		#     virtual buffer; on a big page the buffer lags. (biblegateway fired
		#     twice with a real Gecko_ia2 TI whose isReady was False, both dropped;
		#     the user pressed Z, then refreshed, and only the refresh landed.)
		#   - it is None. NVDA only builds a TI in its pre-step when the loaded
		#     object is the focus or a focus ancestor (eventHandler.py:431-432), so
		#     unfocused and sub-document loads arrive with none.
		#
		# Poll in BOTH cases. We used to skip the None case entirely for fear of
		# auto-landing inside Thunderbird message previews, which fire
		# documentLoadComplete with a null TI. That fear was right; dropping the
		# event was the wrong cure. The principled filter is the one NVDA itself
		# uses to tell web documents from email: a URL-SCHEME allowlist.
		# browseMode.py:2406-2413 gates on http/https/ftp/ftps/file, commented "we
		# don't want to remember caret positions for email messages, etc." Mail
		# clients expose imap:/mailbox:/news: URLs, so the scheme check keeps us
		# out of Thunderbird without hard-coding an app name -- and keeps us out of
		# the next mail client too.
		if ti is None or not getattr(ti, "isReady", False):
			self._scheduleReadyPoll(obj, bypassExclusion, attempt=1)
			return
		self._maybeFireTi(ti, bypassExclusion=bypassExclusion)

	def _scheduleReadyPoll(self, obj, bypassExclusion, attempt):
		self._cancelPendingReadyPoll()
		dlog.debug(f"[TMTS] ti not ready — readiness poll attempt {attempt}/{self._READY_POLL_MAX_ATTEMPTS}")
		try:
			self._pendingReadyPoll = wx.CallLater(
				self._READY_POLL_MS,
				self._fireReadyPoll,
				obj,
				bypassExclusion,
				attempt,
			)
		except Exception:
			log.exception("[TMTS] failed to schedule readiness poll")
			self._pendingReadyPoll = None

	def _cancelPendingReadyPoll(self):
		if self._pendingReadyPoll is None:
			return
		try:
			if self._pendingReadyPoll.IsRunning():
				self._pendingReadyPoll.Stop()
		except Exception:
			pass
		self._pendingReadyPoll = None

	def _fireReadyPoll(self, obj, bypassExclusion, attempt):
		# Runs on the wx main thread _READY_POLL_MS after scheduling.
		self._pendingReadyPoll = None
		try:
			ti = getattr(obj, "treeInterceptor", None)
		except Exception:
			# Object died under us (user navigated away). Nothing to do.
			dlog.debug("[TMTS] readiness poll: object gone — abandon")
			return
		if ti is not None and getattr(ti, "isReady", False):
			# Now that a TI exists we can see the URL, so this is where we enforce
			# the web-only rule. NVDA uses the same scheme allowlist to separate web
			# documents from email (browseMode.py:2406-2413). Without this, polling
			# the TI-is-None case would eventually auto-land inside a Thunderbird
			# message preview -- email detection is deferred and undesigned, and
			# hijacking the user's cursor in their inbox is exactly the kind of
			# "act when unsure" the guardrails forbid.
			if not _isWebDocument(ti):
				dlog.debug("[TMTS] readiness poll: not a web document (scheme) — abandon")
				return
			dlog.debug(f"[TMTS] readiness poll: ready after {attempt} attempt(s) — proceeding")
			self._maybeFireTi(ti, bypassExclusion=bypassExclusion)
			return
		if attempt >= self._READY_POLL_MAX_ATTEMPTS:
			# Give up silently. We never played a tone, so from the user's
			# side nothing happened — same as before this poll existed. Z
			# remains the manual escape hatch.
			dlog.debug(f"[TMTS] readiness poll: still not ready after {attempt} attempts — giving up")
			return
		self._scheduleReadyPoll(obj, bypassExclusion, attempt + 1)

	def _maybeFireTi(self, ti, bypassExclusion=False):
		if ti is None or not getattr(ti, "isReady", False):
			dlog.debug(f"[TMTS] _maybe_fire_ti: ti not ready ({ti!r})")
			return
		# A ready TI means this cycle is live; any readiness poll still
		# pending from an earlier event is now stale.
		self._cancelPendingReadyPoll()
		# NOTE: the pending-retry cancel used to live HERE, above the gates. That
		# was a bug: a duplicate/iframe documentLoadComplete would cancel the
		# useful 1500ms hydration retry from the real page load, then hit a gate
		# below and return WITHOUT scheduling a new one. The retry died silently.
		# Only an ACCEPTED navigation may cancel the previous page's retry, so the
		# cancel now sits after the gates, just before we proceed.
		#
		# User-managed site exclusion list. The double-Z one-shot path
		# sets bypassExclusion=True to force detection regardless of the
		# saved exclusion entry, without modifying the persisted list.
		url = ""
		try:
			url = str(getattr(ti, "documentConstantIdentifier", "") or "")
		except Exception:
			url = ""
		hostname = _hostnameFromUrl(url)
		if not bypassExclusion and hostname and cfgMod.isSiteDisabled(hostname):
			dlog.debug(f"[TMTS] _maybe_fire_ti: site {hostname!r} is on exclusion list — skip")
			return
		# SAME DOCUMENT = same TreeInterceptor AND same URL.
		#
		# This gate used to be TI identity ALONE, on the belief that "NVDA tears
		# down the TI on reload, so a reused TI means the document didn't change."
		# That belief is false, and it was the single most damaging bug in the
		# add-on: it silently swallowed 17 of 31 real page loads in one session.
		#
		# What NVDA actually does (verified in source, twice, independently):
		# a TreeInterceptor is bound to an ACCESSIBILITY-TREE ROOT, not to a URL or
		# a navigation. treeInterceptorHandler.update() returns the EXISTING
		# interceptor whenever the object already has one (treeInterceptorHandler.py
		# :48-78) and only builds a new one when none exists. Gecko keeps its
		# interceptor alive as long as the root accessible is not defunct
		# (gecko_ia2.py:309-329). So on same-tab navigation Firefox commonly keeps
		# the root, NVDA reuses the TI, and the URL changes IN PLACE underneath it.
		# NVDA documents that explicitly for SPAs: documentConstantIdentifier
		# "should reflect the most up to date URL" (browseMode.py:2387-2396), and on
		# Gecko it is a live COM call, not a cached value (gecko_ia2.py:610-614).
		#
		# So the URL is the document's identity; the TI object is just the container.
		#
		# Why this still skips what it should: an iframe/ad load fires its own
		# documentLoadComplete, but its obj resolves through containment to the MAIN
		# page's TI, whose URL is the MAIN page's URL -- same TI, same URL, skipped.
		# Duplicate double-fires for one document likewise.
		#
		# Known gap, accepted: a genuine re-navigation to the IDENTICAL url on a
		# reused TI (F5, a form POST that returns the same URL) is skipped. That is
		# not a regression -- the old identity gate skipped it too -- and Z covers
		# it. Fixing it needs a document-generation signal NVDA does not expose.
		if ti is self._lastTi() and url and url == self._lastUrl:
			dlog.debug("[TMTS] _maybeFireTi: same TI AND same URL — skip")
			return
		if ti is self._lastTi() and not url:
			# No URL to compare (Gecko returns None on COMError). Fall back to the
			# old identity-only behaviour rather than firing blind.
			dlog.debug("[TMTS] _maybeFireTi: same TI, no URL available — skip")
			return
		# URL + cooldown catches the SPA-ish case where NVDA gives us a
		# fresh TI for what is actually still the same logical page load
		# (DDG, Gmail, etc. emit duplicate events with new TI objects).
		# `url` was extracted above for the exclusion-list check; reuse it.
		now = time.monotonic()
		elapsed = now - self._lastFireTime
		if (
			url
			and url == self._lastUrl
			and elapsed < self._REFIRE_COOLDOWN_SEC
		):
			dlog.debug(f"[TMTS] _maybe_fire_ti: cooldown blocking url={url!r} elapsed={elapsed:.2f}s")
			self._setLastTi(ti)
			return
		# Post-landing suppression: we already landed on this URL recently.
		# SPA re-renders (new TI, same URL, seconds to minutes later) must
		# not yank the user off that landing — or off wherever they've
		# read to since. Z re-runs detection on demand.
		landedElapsed = now - self._lastLandedTime
		if (
			url
			and url == self._lastLandedUrl
			and landedElapsed < self._LANDED_SUPPRESS_SEC
		):
			dlog.debug(
				f"[TMTS] _maybe_fire_ti: already landed on url={url!r} "
				f"{landedElapsed:.1f}s ago — suppressing re-detection"
			)
			self._setLastTi(ti)
			self._lastUrl = url
			self._lastFireTime = now
			return
		dlog.debug(f"[TMTS] _maybe_fire_ti: PROCEEDING url={url!r} elapsed={elapsed:.2f}s ti_changed={ti is not self._lastTi()}")
		# This is an ACCEPTED navigation, and only now may we cancel the previous
		# page's pending hydration retry. Doing it earlier (above the gates) meant
		# a duplicate or iframe documentLoadComplete killed the real page's retry
		# and then bailed at a gate without scheduling a replacement.
		self._cancelPendingRetry()
		self._setLastTi(ti)
		self._lastUrl = url
		self._lastFireTime = now
		# Session URL memory for the restored-position gate below. Membership
		# is checked BEFORE recording — "seen before" must mean an earlier
		# page visit, not this one.
		urlSeenBefore = bool(url) and url in self._seenUrls
		if url:
			if len(self._seenUrls) >= 500:
				# Prune the oldest half so long sessions stay bounded.
				for stale in sorted(self._seenUrls, key=self._seenUrls.get)[:250]:
					del self._seenUrls[stale]
			self._seenUrls[url] = now
		# Guardrail #6 pre-check: if the page placed focus on an editable
		# control (DDG home's search box, login pages, etc.), stay totally
		# silent — no working tone, no pulse, no detection. The classifier
		# would otherwise catch this too, but only AFTER we'd already played
		# the working tone, which is exactly what was firing on DDG.
		if tsMod.isFocusEditable():
			dlog.debug(f"[TMTS] _maybe_fire_ti: focus editable — skip")
			return
		# Restored-position gate: when the user comes BACK to a page they
		# already visited this session and the browse cursor is not at the
		# very top, the browser restored their place (Back to search
		# results, a book list mid-scroll). Yanking them to a landing from
		# there is exactly the "supplant natural navigation" failure
		# guardrail #1 forbids. The gate requires BOTH signals: caret
		# mid-page alone is NOT enough, because some pages initialize the
		# caret slightly below the top on a first visit (halturner
		# radioshow articles start at node 1) and those must still land.
		# A cross-page anchor link (foo.html#section) is also an explicit
		# user target even on first visit — honor it. SPA route fragments
		# starting with '#/' (Zoom's #/registration) are NOT anchors.
		fragment = url.partition("#")[2]
		hasAnchor = bool(fragment) and not fragment.startswith("/")
		if (
			not bypassExclusion
			and (urlSeenBefore or hasAnchor)
			and self._caretIsMidPage(ti)
		):
			dlog.debug(
				f"[TMTS] _maybe_fire_ti: caret mid-page on "
				f"{'revisited' if urlSeenBefore else 'anchored'} url — skip"
			)
			return
		# Do NOT pre-cancel speech here. Detection runs silently while NVDA
		# does its normal page-load chatter (title, URL, focus). The only
		# moment of interruption is the speakTextInfo call below when we
		# have a landing paragraph — that naturally cuts off NVDA's chatter.
		# Pre-cancelling here silenced NVDA's voice on pages our classifier
		# doesn't act on (form/app/unknown), making the add-on feel broken.
		try:
			self._runDetection(ti)
		except Exception:
			log.exception("[TMTS] detection error")

	def _runDetection(self, ti, attempt=0):
		# First attempt plays the working tone + pulse. Retries run
		# silently — no second working tone (user already heard one) and
		# no pulse (the wait between attempts already conveys "thinking").
		isRetry = attempt > 0
		if not isRetry:
			fbMod.working()
			fbMod.progressStart()
		acted = False
		# Initialised before the try: if buildTreeSummary raises, the
		# scheduling decision below still has to be answerable, and a failed
		# build must not read as "the tree was empty, keep waiting".
		unbuilt = False
		couldRetry = attempt == 0
		try:
			summary = tsMod.buildTreeSummary(ti)
			try:
				# AN EMPTY TREE IS NOT AN ANSWER. Zero nodes does not mean
				# "this page has no content" — it means NVDA's virtual buffer
				# is not built yet. A real loaded document always yields text;
				# if the scope filter had eaten everything the unscoped
				# fallback would have refilled it. So the two outcomes get
				# different treatment: a page that HAS content and offers no
				# landing is a genuine no-result and earns the notFound tone,
				# while a page with nothing in it at all earns another wait.
				#
				# IMDb, 2026-07-18: detection fired at page-load and again on
				# the 1500 ms retry, both against a buffer holding ONE chunk
				# and zero nodes, and announced failure. Four seconds later a
				# fresh load event walked 190 chunks and landed correctly on
				# the plot summary. The user heard "nothing found" about a page
				# that plainly had content.
				unbuilt = not summary.mainNodes
				couldRetry = attempt == 0 or (
					unbuilt and attempt + 1 < self._MAX_DETECTION_ATTEMPTS
				)
				acted = self._handleResult(
					ti, summary, isRetry=isRetry, isFinal=not couldRetry,
				)
			finally:
				tsMod.releaseSummary(summary)
		finally:
			if not isRetry:
				fbMod.progressStop()
		# Real long-term fix for SPA hydration delay: if an attempt didn't
		# produce a landing, wait and look again. The page may still be
		# loading async content into NVDA's virtual buffer (calendar
		# appointments, Gmail thread list, search results). Generic — no
		# site-specific code.
		#
		# An unbuilt tree gets the LONGER delay: the buffer was not merely
		# incomplete, it was absent, so another 1500 ms is unlikely to be
		# enough. Bounded by _MAX_DETECTION_ATTEMPTS so a page that never
		# builds cannot retry forever.
		if not acted and couldRetry:
			delay = self._EMPTY_RETRY_DELAY_MS if unbuilt else self._RETRY_DELAY_MS
			self._scheduleRetry(ti, attempt + 1, delay)

	def _scheduleRetry(self, ti, attempt=1, delayMs=None):
		# Capture the URL at scheduling time so the retry can verify the
		# user hasn't navigated away by the time it fires.
		if delayMs is None:
			delayMs = self._RETRY_DELAY_MS
		try:
			expectedUrl = str(getattr(ti, "documentConstantIdentifier", "") or "")
		except Exception:
			expectedUrl = ""
		# Capture where the caret sits NOW so the retry can tell whether
		# the user started reading during the wait. Comparing against the
		# top of the document would be wrong — on some pages the caret
		# never starts at the top, and those pages could then never retry.
		try:
			caretAtSchedule = ti.makeTextInfo(textInfos.POSITION_CARET)
		except Exception:
			caretAtSchedule = None
		dlog.debug(
			f"[TMTS] scheduling retry (attempt {attempt}) in {delayMs}ms "
			f"for url={expectedUrl!r}"
		)
		try:
			self._pendingRetry = wx.CallLater(
				delayMs,
				self._fireRetry,
				ti,
				expectedUrl,
				caretAtSchedule,
				attempt,
			)
		except Exception:
			log.exception("[TMTS] failed to schedule retry")
			self._pendingRetry = None

	def _cancelPendingRetry(self):
		if self._pendingRetry is None:
			return
		try:
			if self._pendingRetry.IsRunning():
				self._pendingRetry.Stop()
		except Exception:
			pass
		self._pendingRetry = None

	def _fireRetry(self, ti, expectedUrl, caretAtSchedule=None, attempt=1):
		# Runs on the wx main thread after the scheduled delay.
		self._pendingRetry = None
		if not getattr(ti, "isReady", False):
			dlog.debug("[TMTS] retry: TI no longer ready — abandon")
			return
		try:
			currentUrl = str(getattr(ti, "documentConstantIdentifier", "") or "")
		except Exception:
			currentUrl = ""
		if currentUrl != expectedUrl:
			dlog.debug(f"[TMTS] retry: url changed (was {expectedUrl!r}, now {currentUrl!r}) — abandon")
			return
		# If the user started reading during the wait (caret moved from
		# where it was when the retry was scheduled), the retry must not
		# yank them — they've taken over manually. Compared against the
		# scheduling-time position, NOT the top of the document, because
		# some pages initialize the caret below the top.
		if caretAtSchedule is not None:
			try:
				caretNow = ti.makeTextInfo(textInfos.POSITION_CARET)
				moved = caretNow.compareEndPoints(caretAtSchedule, "startToStart") != 0
			except Exception:
				moved = False
			if moved:
				dlog.debug("[TMTS] retry: caret moved during wait — abandon")
				return
		dlog.debug(f"[TMTS] retry: firing (attempt {attempt})")
		try:
			self._runDetection(ti, attempt=attempt)
		except Exception:
			log.exception("[TMTS] retry error")

	def _caretIsMidPage(self, ti) -> bool:
		# True when the browse cursor sits past the first character of the
		# document. Errors resolve to False (proceed with detection) — the
		# gate must never turn a broken caret query into permanent silence.
		try:
			caret = ti.makeTextInfo(textInfos.POSITION_CARET)
			first = ti.makeTextInfo(textInfos.POSITION_FIRST)
			return caret.compareEndPoints(first, "startToStart") > 0
		except Exception:
			return False

	def _recordLanding(self, url):
		# Remember that we successfully landed on this URL so later
		# automatic same-URL triggers (SPA re-renders) get suppressed for
		# _LANDED_SUPPRESS_SEC. Z clears this — it's an explicit re-request.
		self._lastLandedUrl = url or None
		self._lastLandedTime = time.monotonic()

	def _handleResult(self, ti, summary, isRetry=False, isFinal=True):
		# Returns True if we acted (moved caret + spoke). False otherwise.
		# A False result on a non-final attempt triggers a scheduled retry
		# instead of playing notFound right away.
		#
		# isFinal, NOT isRetry, gates the failure tone. They used to be the
		# same thing because there was exactly one retry. Now an empty tree can
		# earn a further attempt, and announcing "nothing found" before the
		# last look is how IMDb reported failure on a page it went on to land
		# correctly. Silence costs nothing here; a wrong failure tone teaches
		# the user to distrust the add-on.
		result = clsMod.classify(summary)
		# Build a verbose diagnostic snippet about the classifier's view.
		from .classifier import _largestParagraphCluster, _largestHeadingCluster, _heroParagraphChars
		bsize, bchars = _largestParagraphCluster(summary.mainNodes)
		hsize, hlvl = _largestHeadingCluster(summary.mainNodes)
		hero = _heroParagraphChars(summary.mainNodes)
		firstNode = ""
		if summary.mainNodes:
			n = summary.mainNodes[0]
			firstNode = f" first=({n.kind} L{n.level} len={n.textLength} {n.textPreview!r})"

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
		if result.intent == clsMod.Intent.FORM and not webMod.formWantsBrowseLanding(summary):
			# Bare form (no substantial descriptive paragraph): announce the
			# title mode-agnostically and put keyboard focus on the first
			# field. Rich-preamble forms fall through to the browse-mode
			# landing below instead — focusing the first input on those
			# pages skips the user past the title and description (Zoom
			# webinar registration was the canonical case).
			idx = webMod.findFormLanding(summary)
			titleText = ""
			if idx is not None and 0 <= idx < len(summary.mainNodes):
				titleText = summary.mainNodes[idx].textPreview.strip()
			if titleText:
				try:
					ui.message(titleText)
				except Exception:
					log.exception("[TMTS] FORM ui.message failed")
			focusSet = tsMod.setFocusOnFirstFormInput(ti)
			dlog.debug(
				f"[TMTS] FORM: title={titleText!r} focus_set={focusSet} "
				f"url={summary.url!r} retry={isRetry}"
			)
			# Consider it acted if we either announced the title or moved
			# focus. Both are real user-perceptible actions.
			acted = bool(titleText or focusSet)
			if acted:
				self._recordLanding(summary.url)
			return acted

		if result.intent == clsMod.Intent.FORM:
			# Rich-preamble form: land in browse mode on the form's title
			# (or description fallback) so the user gets context first and
			# arrows down through the description into the fields.
			idx = webMod.findFormLanding(summary)
		elif result.intent == clsMod.Intent.ARTICLE:
			idx = webMod.findArticleLanding(summary)
		elif result.intent == clsMod.Intent.LIST:
			idx = webMod.findListLanding(summary)
		elif result.intent == clsMod.Intent.NOTICE:
			idx = webMod.findNoticeLanding(summary)
		elif result.intent == clsMod.Intent.KEY_RESULT:
			idx = webMod.findKeyResultLanding(summary)
		else:
			dlog.debug(
				f"[TMTS] no-action: {result.intent.value}({result.confidence:.2f}) "
				f"main={summary.hasMainLandmark} nodes={len(summary.mainNodes)} "
				f"art={summary.articleCount} form={summary.formInputCount} "
				f"body={bsize}/{bchars} head={hsize}@L{hlvl} hero={hero}"
				f"{firstNode} url={summary.url!r} retry={isRetry}"
			)
			# Guardrail #6: stay silent when the page placed focus itself.
			# Other no-action cases either retry (first attempt) or play
			# notFound (final attempt).
			if result.intent != clsMod.Intent.SILENT_FOCUS_HONORED and isFinal:
				fbMod.notFound()
			return False
		if idx is None:
			dlog.debug(
				f"[TMTS] {result.intent.value} but no landing index "
				f"main={summary.hasMainLandmark} nodes={len(summary.mainNodes)} "
				f"first_nodes={[(n.kind, n.textLength, n.textPreview[:40]) for n in summary.mainNodes[:6]]} "
				f"url={summary.url!r} retry={isRetry}"
			)
			if isFinal:
				fbMod.notFound()
			return False
		landingInfo = tsMod.getLandingTextinfo(summary, idx)
		if landingInfo is None:
			dlog.debug(
				f"[TMTS] {result.intent.value} idx={idx} but no textinfo found "
				f"main={summary.hasMainLandmark} nodes={len(summary.mainNodes)} "
				f"url={summary.url!r} retry={isRetry}"
			)
			if isFinal:
				fbMod.notFound()
			return False
		landedNode = summary.mainNodes[idx]
		try:
			# STALE-POSITION GUARD (2026-07-14 soak — the big one).
			#
			# We capture a TextInfo per node during the walk and speak it
			# afterwards. But the page keeps hydrating and re-rendering while we
			# walk, NVDA rebuilds its virtual buffer, and the captured position
			# then points somewhere else entirely. We choose the right paragraph
			# and read from a stale bookmark.
			#
			# Observed on 7 of 42 landings. The classifier's choice was often
			# CORRECT and the user still heard something else:
			#
			#   allrecipes    chose the signup promo   spoke "My Recipes Logo"
			#   simplyrecipes chose the signup promo   spoke "Start Saving These Dishes"
			#   tasteofhome   chose the real lede      spoke "We're loading your content, stay tuned!"
			#   arstechnica   chose a real headline    spoke "hackers-quickly-prove-that-neo…" (a URL slug)
			#   wfaa          chose the correct lede   spoke a Cincinnati Reds sports headline
			#   npr           chose the Iran story     spoke a different story
			#   applevis      chose the intro para     spoke "Welcome to AppleVis"
			#
			# It also explains the biblegateway silent-landing: when the stale
			# position lands on an empty range, speakTextInfo neither raises nor
			# speaks. Same root cause, different symptom.
			#
			# So: re-expand the captured position and check it still holds the
			# paragraph we chose. This runs BEFORE updateCaret — a stale position
			# moves the browse cursor to the wrong place too, not just the speech.
			#
			# On mismatch we act as if we found nothing, which hands the page to
			# the existing retry (a fresh walk at +_RETRY_DELAY_MS against the
			# now-settled buffer). No new machinery.
			speechInfo = landingInfo.copy()
			speechInfo.expand(textInfos.UNIT_PARAGRAPH)
			try:
				actualText = speechInfo.text or ""
			except Exception:
				actualText = ""
			if not webMod.landingTextMatches(actualText, landedNode):
				# RECOVER BY TEXT, don't just give up.
				#
				# The offset drifted, but we still know WHAT we chose. Re-find
				# that text in the buffer as it exists right now.
				#
				# The retry is NOT a substitute for this. The buffer drifts
				# DURING the 1.5-2s walk, so a re-walk races exactly the same
				# way and lands stale again -- Serious Eats bailed, retried,
				# and went silent. Re-anchoring on the text sidesteps the race
				# entirely and costs one find() instead of a second walk.
				# The verifier is passed IN so the finder can try SHORTER needles
				# than the full 60-char preview, which it needs to do because
				# find() is literal while this check normalises, and because
				# this check only compares 24 chars anyway. Inside the finder a
				# rung is only used when it is UNIQUE in the document -- that,
				# not this check, is what stops a short needle matching the
				# wrong paragraph; a repeated lede opening passes this check
				# happily. What this check adds is the case uniqueness cannot
				# see: a unique hit sitting MID-paragraph. The outer check below
				# is left in place as defence in depth.
				recovered = tsMod.findLandingByText(
					ti,
					landedNode.textPreview,
					verify=lambda found: webMod.landingTextMatches(found, landedNode),
				)
				recoveredInfo = None
				if recovered is not None:
					cand = recovered.copy()
					cand.expand(textInfos.UNIT_PARAGRAPH)
					try:
						candText = cand.text or ""
					except Exception:
						candText = ""
					# Verify the re-found position really is our paragraph.
					# find() returns the FIRST hit; if that hit isn't the text we
					# wanted, we are no better off than before.
					if webMod.landingTextMatches(candText, landedNode):
						recoveredInfo = recovered
						speechInfo = cand
				if recoveredInfo is None:
					dlog.debug(
						f"[TMTS stale-landing] captured position drifted and text "
						f"re-find failed — NOT speaking. "
						f"chose={landedNode.textPreview[:60]!r} "
						f"buffer_now={webMod.normalizeForMatch(actualText)[:60]!r} "
						f"idx={idx} url={summary.url!r} retry={isRetry}"
					)
					# The DENOMINATOR, persistent. `[TMTS find-shortened]` on
					# its own cannot answer whether shortening earns its place:
					# an absence of it could mean shortening never helps, or it
					# could mean drift stopped happening at all, and those call
					# for opposite decisions. This line and its recovered twin
					# make drift countable. Deliberately carries NO page text —
					# the debug line above has that, and this one is going to a
					# file that accrues for months.
					tsMod._appendPerfLine(
						f"[TMTS drift] outcome=failed retry={isRetry} url={summary.url!r}"
					)
					# Reading the WRONG paragraph is worse than reading none.
					if isFinal:
						fbMod.notFound()
					return False
				dlog.debug(
					f"[TMTS stale-recovered] offset drifted; re-anchored by text. "
					f"chose={landedNode.textPreview[:60]!r} "
					f"stale_buffer_had={webMod.normalizeForMatch(actualText)[:40]!r} "
					f"idx={idx} url={summary.url!r}"
				)
				# See the failed branch above: this is the other half of the
				# denominator. A `find-shortened` line always sits immediately
				# before one of these, so the two together say how often
				# shortening was what did the rescuing.
				tsMod._appendPerfLine(
					f"[TMTS drift] outcome=recovered retry={isRetry} url={summary.url!r}"
				)
				landingInfo = recoveredInfo
			# Move the browse-mode caret to the landing position. We use
			# updateCaret first; that's the canonical way to position the
			# browse cursor in NVDA. Then we speak the destination so the
			# user gets immediate feedback that we acted (NVDA's natural
			# announce-on-caret-move is unreliable for programmatic moves).
			landingInfo.updateCaret()
			# Cancel pending chrome speech (page title, "Skip to content",
			# any in-flight NVDA announcements) so the user hears ONLY our
			# landing paragraph. The cursor has already moved.
			speech.cancelSpeech()
			speech.speakTextInfo(speechInfo, reason=controlTypes.OutputReason.CARET)
			firstEight = [
				(n.kind, n.textLength, n.textPreview[:40])
				for n in summary.mainNodes[:8]
			]
			# Diagnostic: list every paragraph >= 50 chars in mainNodes —
			# these are the candidates the article-landing cascade considered.
			# Helps explain why the addon picked the index it did, especially
			# when firstEight doesn't show the landing.
			# The trailing "S"/"-" is endsSentence. It is load-bearing and
			# invisible: the sentence-strict landing pass throws away every
			# paragraph that doesn't end like a sentence, so a paragraph whose
			# chunk text ends in a site's expander label ("... Read all") reads
			# as a non-sentence and gets discarded even though it IS the content.
			# Without this in the log you cannot tell "the cascade chose badly"
			# from "the strict pass never saw the good paragraph at all".
			substantial = [
				(i, n.textLength, "S" if n.endsSentence else "-", n.textPreview[:50])
				for i, n in enumerate(summary.mainNodes)
				if n.kind == "paragraph" and n.textLength >= 50
			]
			# Diagnostic: every heading in mainNodes (kind+idx+level+preview).
			# Combined with `substantial` this gives the full picture of what
			# the cascade saw.
			headings = [
				(i, n.level, n.textPreview[:40])
				for i, n in enumerate(summary.mainNodes)
				if n.kind == "heading"
			]
			dlog.debug(
				f"[TMTS] moved caret to idx={idx} kind={landedNode.kind} "
				f"intent={result.intent.value}({result.confidence:.2f}) "
				f"len={landedNode.textLength} preview={landedNode.textPreview[:60]!r} "
				f"first_8={firstEight} substantial={substantial} headings={headings} "
				f"nodes={len(summary.mainNodes)} url={summary.url!r} retry={isRetry}"
			)
			# Save the landing textInfo so Shift+Z can snap back to it
			# later without recalculating. Copy first so the saved object
			# survives even if the original is mutated by later cursor
			# moves elsewhere.
			try:
				self._lastInitialLandingInfo = landingInfo.copy()
				self._lastInitialLandingUrl = summary.url
			except Exception:
				log.exception("[TMTS] failed to save Shift+Z return-to-landing position")
				self._lastInitialLandingInfo = None
				self._lastInitialLandingUrl = None
			self._recordLanding(summary.url)
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
		hostname = _hostnameFromUrl(url)
		isExcluded = bool(hostname) and cfgMod.isSiteDisabled(hostname)
		# NVDA's getLastScriptRepeatCount() returns 0 on first press, 1
		# on second press within ~500 ms, etc. A double-Z is the user's
		# explicit "force detection this one time on this excluded site"
		# — we bypass the exclusion check without changing the saved list.
		isDoublePress = getLastScriptRepeatCount() >= 1
		# All Z paths bypass the URL+cooldown debounce AND the post-landing
		# suppression — Z is an explicit user request to redo detection.
		self._lastTiRef = None
		self._lastUrl = None
		self._lastFireTime = 0.0
		self._lastLandedUrl = None
		self._lastLandedTime = 0.0
		if isDoublePress and isExcluded:
			# No spoken announcement here — the working tone + the
			# subsequent detection-result speech are sufficient feedback
			# that the bypass fired. A verbal "One-time detection on
			# <hostname>" was too long in real use; the user already knows
			# they pressed Z twice deliberately.
			self._maybeFire(focus, bypassExclusion=True)
			return
		if isExcluded:
			toggleKey = _getCurrentGestureDisplay("GlobalPlugin", "toggleSiteExclusion")
			# Translators: spoken when Z is pressed on a site that's in
			# the exclusion list. {hostname} is the website, {hotkey} is
			# the current binding for the exclusion toggle (NVDA+Z by
			# default, but reflects user remappings).
			ui.message(_(
				"Text Marks the Spot is disabled for {hostname}. "
				"Press {hotkey} to remove this site from the exclusion list, "
				"or press Z twice for a one-time detection."
			).format(hostname=hostname, hotkey=toggleKey))
			return
		# Z = scan forward from the user's current cursor position for the
		# next substantial content paragraph. Independent of whether or
		# where the addon previously landed: Z always starts from where
		# the user actually is right now. NVDA's H handles next-heading
		# already; Z deliberately skips headings to add value NVDA's
		# built-in keys don't.
		self._scanForwardFromCaret(focus)

	def _scanForwardFromCaret(self, focus):
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
		fbMod.working()
		try:
			summary = tsMod.buildTreeSummary(ti)
			try:
				try:
					caretInfo = ti.makeTextInfo(textInfos.POSITION_CARET)
				except Exception:
					log.exception("[TMTS] Z: failed to read caret position")
					# Translators: spoken when Z can't determine the current
					# cursor position (rare).
					ui.message(_("Cannot scan from the current position."))
					return
				# Find the highest main_node index whose textInfo starts at
				# or before the current caret. That's the user's "current"
				# position — the next content scan starts at index+1.
				currentIdx = -1
				for i in range(len(summary.mainNodes)):
					nodeInfo = tsMod.getLandingTextinfo(summary, i)
					if nodeInfo is None:
						continue
					try:
						cmp = nodeInfo.compareEndPoints(caretInfo, "startToStart")
					except Exception:
						continue
					if cmp <= 0:
						currentIdx = i
					else:
						break
				nextIdx = webMod.findNextContentLanding(summary, currentIdx)
				if nextIdx is None:
					# Diagnostic: dump the full node list — "nothing below
					# the cursor" has repeatedly turned out to mean either
					# a mis-computed currentIdx or content chunked below
					# the substantial bar, and without this line the log
					# says nothing about which.
					dlog.debug(
						f"[TMTS] Z: no landing below current_idx={currentIdx} "
						f"nodes={[(i, n.kind, n.textLength, n.textPreview[:30]) for i, n in enumerate(summary.mainNodes)]} "
						f"url={summary.url!r}"
					)
					# Translators: spoken when Z is pressed and no more
					# content paragraphs exist below the cursor.
					ui.message(_("Nothing else to land on."))
					return
				landingInfo = tsMod.getLandingTextinfo(summary, nextIdx)
				if landingInfo is None:
					# Translators: spoken when the next-content position
					# could not be resolved (rare — usually means the
					# tree changed underneath us).
					ui.message(_("Cannot move to the next content paragraph."))
					return
				landingInfo.updateCaret()
				speech.cancelSpeech()
				speechInfo = landingInfo.copy()
				speechInfo.expand(textInfos.UNIT_PARAGRAPH)
				speech.speakTextInfo(speechInfo, reason=controlTypes.OutputReason.CARET)
				landedNode = summary.mainNodes[nextIdx]
				dlog.debug(
					f"[TMTS] Z scan-from-caret to idx={nextIdx} kind={landedNode.kind} "
					f"len={landedNode.textLength} preview={landedNode.textPreview[:60]!r} "
					f"current_idx={currentIdx} url={summary.url!r}"
				)
			finally:
				tsMod.releaseSummary(summary)
		except Exception:
			log.exception("[TMTS] Z scan-from-caret failed")

	@script(
		# Translators: input help for the Shift+Z return-to-landing gesture.
		description=_("Return the cursor to the add-on's landing position on this page, running detection first if none is saved."),
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
			self._lastInitialLandingInfo is None
			or self._lastInitialLandingUrl != url
		):
			# No saved landing for THIS page. Announcing that and stopping
			# left the user stranded whenever the auto-trigger structurally
			# could not fire: switching to an already-open tab produces no
			# documentLoadComplete, so detection never ran and no gesture
			# could summon it (the starttesting.net login tab, 2026-07-16).
			# Shift+Z means "take me to the landing" -- if none exists yet,
			# compute one now, same one-shot path as double-Z on an excluded
			# site. Feedback is the working tone + landing speech (or the
			# two-beep not-found), deliberately no spoken preamble, matching
			# the double-Z one-shot rationale.
			hostname = _hostnameFromUrl(url)
			if hostname and cfgMod.isSiteDisabled(hostname):
				# Exclusion is still honored here -- the user turned this
				# site off, and double-Z is the documented one-time
				# override, not Shift+Z.
				# Translators: spoken when Shift+Z has no saved landing for
				# the current page (no detection has run, or URL changed).
				ui.message(_("No saved landing on this page."))
				return
			# An explicit user request must not be debounced: reset the
			# document-identity / cooldown / post-landing gates exactly as
			# the Z script does. bypassExclusion=True additionally lifts
			# the restored-position caret gate (the flag gates both);
			# exclusion itself was already checked just above.
			self._lastTiRef = None
			self._lastUrl = None
			self._lastFireTime = 0.0
			self._lastLandedUrl = None
			self._lastLandedTime = 0.0
			dlog.debug(f"[TMTS] Shift+Z: no saved landing for url={url!r} — running on-demand detection")
			self._maybeFire(focus, bypassExclusion=True)
			return
		fbMod.working()
		try:
			self._lastInitialLandingInfo.updateCaret()
			speech.cancelSpeech()
			speechInfo = self._lastInitialLandingInfo.copy()
			speechInfo.expand(textInfos.UNIT_PARAGRAPH)
			speech.speakTextInfo(speechInfo, reason=controlTypes.OutputReason.CARET)
			dlog.debug(f"[TMTS] Shift+Z return-to-landing on url={url!r}")
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
		hostname = _hostnameFromUrl(url)
		if not hostname:
			# Translators: spoken when NVDA+Z can't identify the site.
			ui.message(_("Unable to determine the website for exclusion."))
			return
		# Toggle: dialog confirms the add or remove action.
		currentlyExcluded = cfgMod.isSiteDisabled(hostname)
		if currentlyExcluded:
			# Translators: dialog prompt — confirms removing a site from the exclusion list.
			prompt = _("Remove {hostname} from the Text Marks the Spot exclusion list?").format(hostname=hostname)
		else:
			# Translators: dialog prompt — confirms adding a site to the exclusion list.
			prompt = _("Add {hostname} to the Text Marks the Spot exclusion list?").format(hostname=hostname)

		def _showDialog():
			with wx.MessageDialog(
				gui.mainFrame,
				prompt,
				# Translators: dialog title for the site-exclusion confirm.
				_("Text Marks the Spot: Site Exclusion"),
				style=wx.YES_NO | wx.ICON_QUESTION,
			) as dialog:
				result = dialog.ShowModal()
			if result != wx.ID_YES:
				# Translators: spoken when the user cancels the
				# site-exclusion dialog (clicks No instead of Yes).
				ui.message(_("No change. Exclusion list unchanged."))
				return
			if currentlyExcluded:
				cfgMod.removeDisabledSite(hostname)
				# Translators: spoken confirmation after removal from exclusion list.
				ui.message(_("Removed {hostname} from exclusion list.").format(hostname=hostname))
			else:
				cfgMod.addDisabledSite(hostname)
				# Translators: spoken confirmation after addition to exclusion list.
				ui.message(_("Added {hostname} to exclusion list.").format(hostname=hostname))

		wx.CallAfter(_showDialog)
