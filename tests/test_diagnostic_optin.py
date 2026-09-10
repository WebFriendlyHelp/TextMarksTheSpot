# Both diagnostic logs must stay OFF for everyone who did not deliberately
# ask for them.
#
# The capture log records the FULL url of every page detected, query string and
# all, plus previews of the text on it. The perf log records the same url on
# every line, and it is PERSISTENT: it survives NVDA restarts and accumulates
# for months. On one real day of browsing that included an invoice link, OAuth
# authorization codes, and an application path carrying a client secret.
#
# Both used to be gated on NVDA's DEBUG log level, which is not consent. People
# raise the log level for unrelated reasons and would never guess a screen-reader
# add-on had started keeping a record of where they go. The gate is now a marker
# file nobody creates by accident.
#
# These tests pin the gate and pin BOTH writers honoring it. The two writers are
# checked separately on purpose: they were gated at different times, and a suite
# that only watched the capture log would not notice the perf log going back to
# collecting by default. Delete either check in treeSummary and the matching
# "writes nothing" test fails.

import os

import treeSummary


def _reset(monkeypatch, appdata):
	monkeypatch.setattr(treeSummary, "_DIAG_ENABLED", None, raising=False)
	monkeypatch.setattr(treeSummary, "_CAPTURE_LOG_PATH_CACHE", None, raising=False)
	monkeypatch.setattr(treeSummary, "_PERF_LOG_PATH_CACHE", None, raising=False)
	monkeypatch.setenv("APPDATA", str(appdata))
	nvdaDir = os.path.join(str(appdata), "nvda")
	os.makedirs(nvdaDir, exist_ok=True)
	return nvdaDir


def _optIn(nvdaDir):
	open(os.path.join(nvdaDir, treeSummary._DIAG_MARKER_NAME), "w").close()


# --- the gate itself ----------------------------------------------------


def test_disabledWithoutMarker(monkeypatch, tmp_path):
	_reset(monkeypatch, tmp_path)
	assert treeSummary._diagnosticsEnabled() is False


def test_enabledWithMarker(monkeypatch, tmp_path):
	nvdaDir = _reset(monkeypatch, tmp_path)
	_optIn(nvdaDir)
	assert treeSummary._diagnosticsEnabled() is True


def test_disabledWhenAppdataMissing(monkeypatch, tmp_path):
	_reset(monkeypatch, tmp_path)
	monkeypatch.delenv("APPDATA", raising=False)
	assert treeSummary._diagnosticsEnabled() is False


def test_disabledWhenTheMarkerCheckItselfRaises(monkeypatch, tmp_path):
	# A permission error, a dead network drive, anything: the answer is OFF.
	# Failing open here would start recording on a machine we could not even
	# read a filename on, which is the worst place to guess "yes".
	_reset(monkeypatch, tmp_path)

	def _boom(_path):
		raise OSError("cannot stat")

	monkeypatch.setattr(os.path, "exists", _boom)
	assert treeSummary._diagnosticsEnabled() is False


def test_verdictIsCachedForTheSession(monkeypatch, tmp_path):
	# Creating the marker mid-session must not switch recording on underneath a
	# user who is already browsing; it takes effect at the next NVDA restart.
	nvdaDir = _reset(monkeypatch, tmp_path)
	assert treeSummary._diagnosticsEnabled() is False
	_optIn(nvdaDir)
	assert treeSummary._diagnosticsEnabled() is False


# --- the capture log ----------------------------------------------------


class _FakeSummary:
	url = "https://example.com/private/page?token=secret"
	hasMainLandmark = True
	articleCount = 1
	formInputCount = 0
	interactiveControlCount = 3
	countsTruncated = False
	# Every field _appendCapture reads must exist here. It swallows all
	# exceptions, so a missing attribute drops the WHOLE record silently
	# rather than raising; this stand-in going stale looks exactly like
	# capture logging being broken (2026-09-10).
	articleCountTruncated = False
	walkTruncated = False
	positionallyScoped = False
	mainNodes = ()


def test_captureDisabledWritesNothing(monkeypatch, tmp_path):
	nvdaDir = _reset(monkeypatch, tmp_path)
	treeSummary._appendCapture(_FakeSummary())
	assert os.listdir(nvdaDir) == [], "capture log written with no opt-in marker present"


def test_captureEnabledWritesARecord(monkeypatch, tmp_path):
	nvdaDir = _reset(monkeypatch, tmp_path)
	_optIn(nvdaDir)
	treeSummary._appendCapture(_FakeSummary())
	logPath = os.path.join(nvdaDir, "TextMarksTheSpot-captures.jsonl")
	assert os.path.exists(logPath)
	assert "example.com/private/page" in open(logPath, encoding="utf-8").read()


# --- the persistent perf log --------------------------------------------

_PERF_LINE = "[TMTS perf] total=42ms url='https://example.com/private/page?token=secret'"


def test_perfLogDisabledWritesNothing(monkeypatch, tmp_path):
	nvdaDir = _reset(monkeypatch, tmp_path)
	treeSummary._appendPerfLine(_PERF_LINE)
	assert os.listdir(nvdaDir) == [], "perf log written with no opt-in marker present"


def test_perfLogEnabledWritesTheLine(monkeypatch, tmp_path):
	nvdaDir = _reset(monkeypatch, tmp_path)
	_optIn(nvdaDir)
	treeSummary._appendPerfLine(_PERF_LINE)
	logPath = os.path.join(nvdaDir, "TextMarksTheSpot-perf.log")
	assert os.path.exists(logPath)
	assert "example.com/private/page" in open(logPath, encoding="utf-8").read()


# ---------------------------------------------------------------------------
# The suite must not write into the DEVELOPER'S OWN logs either.
#
# Added 2026-08-18 after it happened. The gate is a marker file under
# %APPDATA%\nvda, and a developer collecting real data necessarily HAS that
# marker -- so on exactly the machine where the logs matter, the suite was
# writing to them. `_logLandmarkProbe` calls `_appendPerfLine`, and several
# tests drive the landmark scan directly, so one sabotage_check.py run put 1022
# synthetic probe lines into a real perf log holding 4 real ones.
#
# The perf log self-rotates at 1 MB keeping one generation, so this does not
# merely add noise: enough test runs DESTROY the real browsing data the log was
# turned on to collect, and nothing looks wrong while it happens. conftest.py
# repoints APPDATA at an empty temp directory at import time; these pin it.
# ---------------------------------------------------------------------------

def test_appdataIsRedirectedAwayFromTheRealOne():
	real = os.path.expanduser("~")
	appdata = os.environ.get("APPDATA", "")
	assert appdata, "conftest should have set APPDATA for the test session"
	assert "tmts-test-appdata" in appdata, (
		f"APPDATA is {appdata!r}; the suite is pointed at a real profile and "
		"will write into the user's own diagnostic logs"
	)
	assert not appdata.startswith(os.path.join(real, "AppData", "Roaming")), appdata


def test_diagnosticsAreOffByDefaultUnderTheTestAppdata():
	# The consequence that actually matters: with no marker in the redirected
	# APPDATA, every writer is inert no matter what any individual test does.
	treeSummary._DIAG_ENABLED = None
	try:
		assert treeSummary._diagnosticsEnabled() is False
	finally:
		treeSummary._DIAG_ENABLED = None


def _snapshot(root):
	"""Every file under `root`, with its size. Names alone are not enough: the
	leak APPENDS to a perf log that already exists, so a directory listing is
	unchanged by it and a test watching only names stays green through the very
	bug it was written for. That happened to the first version of this test."""
	out = {}
	for dirpath, _dirnames, filenames in os.walk(root):
		for name in filenames:
			full = os.path.join(dirpath, name)
			try:
				out[full] = os.path.getsize(full)
			except OSError:
				pass
	return out


def test_theLandmarkProbeWritesNothingByDefault():
	# The specific writer that leaked. It is reached from the landmark scan,
	# which plenty of tests drive, so it is the one most likely to leak again.
	treeSummary._DIAG_ENABLED = None
	treeSummary._PERF_LOG_PATH_CACHE = None
	try:
		root = os.path.join(os.environ["APPDATA"], "nvda")
		before = _snapshot(root)
		treeSummary._logLandmarkProbe(["navigation", "banner"], True, 0, "exhausted")
		after = _snapshot(root)
		assert before == after, (
			"the landmark probe wrote to a real diagnostic log during the test "
			f"run: {[k for k in after if after.get(k) != before.get(k)]}"
		)
	finally:
		treeSummary._DIAG_ENABLED = None
		treeSummary._PERF_LOG_PATH_CACHE = None


# ---------------------------------------------------------------------------
# The SESSION log is gated too (2026-08-18).
#
# The persistent logs were gated in July, which closed the real hazard: a
# structured, timestamped, one-line-per-page record of full urls that survives
# restarts and accrues for months. What was left ungated was the copy that goes
# to NVDA's own session log via log.debug, carrying the same urls plus 60-char
# previews of the paragraphs on the page.
#
# Measured before changing anything: NVDA's own default log level is INFO and it
# logs spoken text via log.io at the IO level, so at the default none of this
# was ever written. It only appeared once a user raised the level, at which
# point NVDA is itself logging every phrase it speaks. We were never the
# dominant source of page content in such a log -- but we were the tidiest, one
# clean greppable url= per page load, which is the shape a browsing record
# actually takes. Casey's call: his machine logs, nobody else's.
#
# Every log.debug now goes through treeSummary.dlog. log.info (3 lifecycle
# lines) and log.exception (15, all static strings) stay ungated on purpose --
# they say nothing about where anyone has been, and they are what makes a crash
# report from a stranger worth having.
# ---------------------------------------------------------------------------

def test_gatedDebugIsSilentWithoutTheMarker(monkeypatch, tmp_path):
	_reset(monkeypatch, tmp_path)
	seen = []
	monkeypatch.setattr(treeSummary.log, "debug", lambda *a, **k: seen.append(a))
	treeSummary.dlog.debug("[TMTS perf] url='https://example.com/private?token=abc'")
	assert seen == [], f"a url reached the session log without opt-in: {seen}"


def test_gatedDebugSpeaksOnceTheMarkerExists(monkeypatch, tmp_path):
	# The other direction. A gate that is always closed would pass the test
	# above while making the add-on undiagnosable, so pin that opting in works.
	nvdaDir = _reset(monkeypatch, tmp_path)
	_optIn(nvdaDir)
	seen = []
	monkeypatch.setattr(treeSummary.log, "debug", lambda *a, **k: seen.append(a))
	treeSummary.dlog.debug("[TMTS perf] url='https://example.com/'")
	assert len(seen) == 1, "opting in did not re-enable diagnostic logging"


def test_noUngatedDebugCallSurvivesInTheAddon():
	# The audit that makes the one-rule design worth having. "Gate the sensitive
	# lines" would need correct judgement at every future call site; "no bare
	# log.debug anywhere" is checkable, so check it. The single permitted
	# occurrence is the one inside _GatedDebugLog itself.
	import pathlib

	root = pathlib.Path(__file__).resolve().parent.parent
	plugin = root / "addon" / "globalPlugins" / "TextMarksTheSpot"
	offenders = []
	for path in sorted(plugin.rglob("*.py")):
		for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
			stripped = line.strip()
			if stripped.startswith("#"):
				continue
			if "log.debug(" in line and "dlog.debug(" not in line:
				if "log.debug(*args, **kwargs)" in line:
					continue  # the gated helper's own call
				offenders.append(f"{path.name}:{i}: {stripped[:70]}")
	assert not offenders, (
		"ungated log.debug calls can put a user's urls and page text into "
		"NVDA's log:\n" + "\n".join(offenders)
	)


def test_lifecycleAndCrashLoggingStayUngated():
	# Deliberately NOT gated, and worth pinning so a later privacy sweep does
	# not quietly take them too. These carry no url and no page text, and they
	# are the only thing that makes a bug report from someone who never opted in
	# worth anything.
	import pathlib

	root = pathlib.Path(__file__).resolve().parent.parent
	plugin = root / "addon" / "globalPlugins" / "TextMarksTheSpot"
	infoCalls = 0
	for path in plugin.rglob("*.py"):
		text = path.read_text(encoding="utf-8")
		infoCalls += text.count("log.info(")
		# An f-string on an exception line would mean interpolated content on an
		# ungated path, which is the one way these could start leaking.
		assert 'log.exception(f"' not in text, f"{path.name} interpolates into an ungated log"
	assert infoCalls >= 3, "the lifecycle log lines went missing"
