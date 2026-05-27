# -*- coding: UTF-8 -*-
# Text Marks the Spot — audio feedback.
#
# Brief, non-obtrusive tones so the user knows the add-on actually ran,
# without needing extra screen reader speech. Three events surface as
# sound:
#
#   working()        detection just started.
#   progress_start() detection is taking long enough to need a "still
#                    working" pulse. Re-arms a timer every 500 ms until
#                    progress_stop() is called. Runs on a background
#                    thread so beeps still fire while the main NVDA
#                    thread is busy walking the accessibility tree.
#   progress_stop()  stop the pulse. MUST be called in a finally.
#   not_found()      detection finished but produced no landing point.
#
# Success is NOT toned: the spoken paragraph is itself the success signal.
#
# Guardrail #6 caveat: when the page auto-placed focus on an editable
# control (SILENT_FOCUS_HONORED), the caller must NOT call not_found() —
# silence is required there. This module just plays sound; the policy
# lives at the call site.

from __future__ import annotations

import threading
import time

try:
	import tones
	_TONES_AVAILABLE = True
except ImportError:
	_TONES_AVAILABLE = False


# Tone constants — three distinct pitches so they're easy to tell apart by ear.
_WORKING_FREQ_HZ = 500
_WORKING_DURATION_MS = 30

_PROGRESS_FREQ_HZ = 400
_PROGRESS_DURATION_MS = 20
_PROGRESS_INTERVAL_SEC = 0.5

_NOT_FOUND_FREQ_HZ = 220
_NOT_FOUND_DURATION_MS = 60
# Two-beep sequence with a small gap between is more distinctive than a
# single tone — the user can recognize "nothing found" by the rhythm
# without confusing it with the working blip or the progress pulse.
_NOT_FOUND_GAP_MS = 80


def _beep(freq: int, duration_ms: int) -> None:
	if not _TONES_AVAILABLE:
		return
	try:
		tones.beep(freq, duration_ms)
	except Exception:
		pass


def working() -> None:
	"""Brief high-ish blip at detection start. 500 Hz / 30 ms."""
	_beep(_WORKING_FREQ_HZ, _WORKING_DURATION_MS)


def not_found() -> None:
	"""Two brief low beeps when detection finished with nothing to land on.
	A two-tone rhythm at 220 Hz is more recognizable than a single low
	tone and clearly distinct from working() (one short blip) and the
	progress pulse (single beep, repeated).

	Played on a background thread so the sequence doesn't block NVDA's
	main thread. tones.beep returns immediately (it queues audio), so
	without a small sleep both beeps would overlap into a single buzz."""
	if not _TONES_AVAILABLE:
		return

	def _play():
		try:
			tones.beep(_NOT_FOUND_FREQ_HZ, _NOT_FOUND_DURATION_MS)
			time.sleep((_NOT_FOUND_DURATION_MS + _NOT_FOUND_GAP_MS) / 1000.0)
			tones.beep(_NOT_FOUND_FREQ_HZ, _NOT_FOUND_DURATION_MS)
		except Exception:
			pass

	t = threading.Thread(target=_play, daemon=True)
	t.start()


# ---------------------------------------------------------------------------
# Progress pulse — fires on a background thread so beeps still play while
# the main NVDA thread is busy walking the tree.
# ---------------------------------------------------------------------------


class _Pulse:
	def __init__(self) -> None:
		self._timer: "threading.Timer | None" = None
		self._active: bool = False
		self._lock = threading.Lock()

	def start(self) -> None:
		with self._lock:
			# Reset any in-flight schedule so the first pulse is a fresh
			# _PROGRESS_INTERVAL_SEC from now — not stale from a prior run.
			self._cancel_timer_locked()
			self._active = True
			self._schedule_locked()

	def stop(self) -> None:
		with self._lock:
			self._active = False
			self._cancel_timer_locked()

	def _cancel_timer_locked(self) -> None:
		if self._timer is not None:
			try:
				self._timer.cancel()
			except Exception:
				pass
			self._timer = None

	def _schedule_locked(self) -> None:
		try:
			t = threading.Timer(_PROGRESS_INTERVAL_SEC, self._fire)
			t.daemon = True
			self._timer = t
			t.start()
		except Exception:
			self._timer = None

	def _fire(self) -> None:
		# Runs on the Timer's own background thread.
		with self._lock:
			if not self._active:
				return
		_beep(_PROGRESS_FREQ_HZ, _PROGRESS_DURATION_MS)
		# Re-arm under the lock, but only if still active. Without the
		# re-check, a stop() racing with the firing call could leave a
		# dangling timer that beeps once after detection finished.
		with self._lock:
			if self._active:
				self._schedule_locked()


_pulse = _Pulse()


def progress_start() -> None:
	_pulse.start()


def progress_stop() -> None:
	_pulse.stop()
