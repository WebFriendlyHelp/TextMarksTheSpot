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


REC = Recorder()


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
		return FakeMessageDialog.answer


class BrowseModeDocumentTreeInterceptor:
	pass


class _GlobalPluginBase:
	def __init__(self):
		pass

	def terminate(self):
		pass


def _script(**kwargs):
	return lambda fn: fn


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

	mod("api", getFocusObject=lambda: REC.focus)
	mod("browseMode", BrowseModeDocumentTreeInterceptor=BrowseModeDocumentTreeInterceptor)
	mod("controlTypes", OutputReason=types.SimpleNamespace(CARET="caret"))
	mod("globalPluginHandler", GlobalPlugin=_GlobalPluginBase)
	mod("gui", mainFrame=None)
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
