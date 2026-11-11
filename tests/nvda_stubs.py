"""Just enough of NVDA to import the GlobalPlugin and drive its logic in tests.

The plugin's __init__.py imports api, wx, speech and friends at module level,
which is why it had no unit tests at all before 2026-09-24. The guards added
that day (mail-scheme skip, background-tab retry abandon, Shift+Z verification,
the Z second pass, the exclusion-failure message) are decisions, not NVDA
calls, so they can be pinned here with fakes. What this CANNOT prove is how
real NVDA and a real browser behave; that stays with the VM harness.

Isolation matters: the stub modules are only in sys.modules while the package
imports, then removed, and the package is loaded under its own name
(`tmtsPlugin`), so the top-level `treeSummary` / `classifier` modules the rest
of the suite imports never see a fake NVDA and never flip _NVDA_AVAILABLE.
"""

import builtins
import importlib.util
import sys
import types
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "addon" / "globalPlugins" / "TextMarksTheSpot"


class Recorder:
	"""Collects calls so a test can assert what was spoken or moved."""

	def __init__(self):
		self.messages = []
		self.spoken = []
		self.cancels = 0
		self.callLaters = []
		self.focus = None
		self.popupEvents = []


REC = Recorder()

ADDON_GETTEXT_MARK = "[addon catalogue] "


class FakeCallLater:
	def __init__(self, delay, fn, *args):
		self.delay = delay
		self.fn = fn
		self.args = args
		self.running = True
		REC.callLaters.append(self)

	def IsRunning(self):
		return self.running

	def Stop(self):
		self.running = False


class FakeMessageDialog:
	answer = None  # set by the test to wx.ID_YES or not

	def __init__(self, *a, **k):
		pass

	def __enter__(self):
		return self

	def __exit__(self, *a):
		return False

	def ShowModal(self):
		REC.popupEvents.append("ShowModal")
		return FakeMessageDialog.answer


class FakeMainFrame:
	"""gui.mainFrame: records the prePopup/postPopup pair around a dialog."""

	def prePopup(self):
		REC.popupEvents.append("prePopup")

	def postPopup(self):
		REC.popupEvents.append("postPopup")


class BrowseModeDocumentTreeInterceptor:
	pass


class _GlobalPluginBase:
	def __init__(self):
		pass

	def terminate(self):
		pass

	def getScript(self, gesture):
		"""NVDA's ScriptableObject.getScript, reduced: the bound script whose
		@script gestures include one of the gesture's normalized identifiers."""
		for ident in getattr(gesture, "normalizedIdentifiers", ()):
			for name in dir(type(self)):
				if not name.startswith("script_"):
					continue
				fn = getattr(type(self), name)
				if ident in getattr(fn, "_stubGestures", ()):
					return getattr(self, name)
		return None


def _script(**kwargs):
	def deco(fn):
		gestures = list(kwargs.get("gestures", ()))
		if kwargs.get("gesture"):
			gestures.append(kwargs["gesture"])
		fn._stubGestures = [g.lower() for g in gestures]
		return fn

	return deco


class _Log:
	def debug(self, *a, **k):
		pass

	info = warning = exception = error = debug

	def isEnabledFor(self, level):
		return False


def _modules():
	m = {}

	def mod(name, **attrs):
		module = types.ModuleType(name)
		module.__dict__.update(attrs)
		m[name] = module
		return module

	def initTranslation():
		# NVDA's version installs the add-on's own gettext as `_` in the
		# CALLING module (addonHandler.initTranslation, installed 2026.3.1).
		# The marker prefix lets a test see which `_` a string went through.
		sys._getframe(1).f_globals["_"] = lambda s: ADDON_GETTEXT_MARK + s

	mod("addonHandler", initTranslation=initTranslation)
	mod("api", getFocusObject=lambda: REC.focus)
	mod("browseMode", BrowseModeDocumentTreeInterceptor=BrowseModeDocumentTreeInterceptor)
	mod("controlTypes", OutputReason=types.SimpleNamespace(CARET="caret"))
	mod("globalPluginHandler", GlobalPlugin=_GlobalPluginBase)
	mod("gui", mainFrame=FakeMainFrame())
	mod(
		"speech",
		cancelSpeech=lambda: setattr(REC, "cancels", REC.cancels + 1),
		speakTextInfo=lambda info, reason=None: REC.spoken.append(info),
	)
	mod("textInfos", POSITION_CARET="caret", POSITION_FIRST="first", UNIT_PARAGRAPH="paragraph")
	mod("ui", message=lambda text: REC.messages.append(text))
	mod(
		"wx",
		CallLater=FakeCallLater,
		CallAfter=lambda fn, *a: fn(*a),
		MessageDialog=FakeMessageDialog,
		YES_NO=1,
		ICON_QUESTION=2,
		ID_YES=5103,
	)
	mod("logHandler", log=_Log())
	mod("scriptHandler", script=_script, getLastScriptRepeatCount=lambda: 0)
	return m


def loadPlugin():
	stubs = _modules()
	saved = {name: sys.modules.get(name) for name in stubs}
	hadUnderscore = hasattr(builtins, "_")
	sys.modules.update(stubs)
	if not hadUnderscore:
		builtins._ = lambda s: s
	try:
		spec = importlib.util.spec_from_file_location(
			"tmtsPlugin", PLUGIN / "__init__.py", submodule_search_locations=[str(PLUGIN)]
		)
		plugin = importlib.util.module_from_spec(spec)
		sys.modules["tmtsPlugin"] = plugin
		spec.loader.exec_module(plugin)
	finally:
		for name, old in saved.items():
			if old is None:
				sys.modules.pop(name, None)
			else:
				sys.modules[name] = old
		if not hadUnderscore:
			del builtins._
	# The plugin calls _() at runtime too; give it its own identity gettext.
	plugin._ = lambda s: s
	return plugin
