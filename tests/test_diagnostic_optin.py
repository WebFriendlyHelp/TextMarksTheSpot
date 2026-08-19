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
# collecting by default. Delete either check in tree_summary and the matching
# "writes nothing" test fails.

import os

import tree_summary


def _reset(monkeypatch, appdata):
	monkeypatch.setattr(tree_summary, "_DIAG_ENABLED", None, raising=False)
	monkeypatch.setattr(tree_summary, "_CAPTURE_LOG_PATH_CACHE", None, raising=False)
	monkeypatch.setattr(tree_summary, "_PERF_LOG_PATH_CACHE", None, raising=False)
	monkeypatch.setenv("APPDATA", str(appdata))
	nvda_dir = os.path.join(str(appdata), "nvda")
	os.makedirs(nvda_dir, exist_ok=True)
	return nvda_dir


def _opt_in(nvda_dir):
	open(os.path.join(nvda_dir, tree_summary._DIAG_MARKER_NAME), "w").close()


# --- the gate itself ----------------------------------------------------


def test_disabled_without_marker(monkeypatch, tmp_path):
	_reset(monkeypatch, tmp_path)
	assert tree_summary._diagnostics_enabled() is False


def test_enabled_with_marker(monkeypatch, tmp_path):
	nvda_dir = _reset(monkeypatch, tmp_path)
	_opt_in(nvda_dir)
	assert tree_summary._diagnostics_enabled() is True


def test_disabled_when_appdata_missing(monkeypatch, tmp_path):
	_reset(monkeypatch, tmp_path)
	monkeypatch.delenv("APPDATA", raising=False)
	assert tree_summary._diagnostics_enabled() is False


def test_disabled_when_the_marker_check_itself_raises(monkeypatch, tmp_path):
	# A permission error, a dead network drive, anything: the answer is OFF.
	# Failing open here would start recording on a machine we could not even
	# read a filename on, which is the worst place to guess "yes".
	_reset(monkeypatch, tmp_path)

	def _boom(_path):
		raise OSError("cannot stat")

	monkeypatch.setattr(os.path, "exists", _boom)
	assert tree_summary._diagnostics_enabled() is False


def test_verdict_is_cached_for_the_session(monkeypatch, tmp_path):
	# Creating the marker mid-session must not switch recording on underneath a
	# user who is already browsing; it takes effect at the next NVDA restart.
	nvda_dir = _reset(monkeypatch, tmp_path)
	assert tree_summary._diagnostics_enabled() is False
	_opt_in(nvda_dir)
	assert tree_summary._diagnostics_enabled() is False


# --- the capture log ----------------------------------------------------


class _FakeSummary:
	url = "https://example.com/private/page?token=secret"
	has_main_landmark = True
	article_count = 1
	form_input_count = 0
	interactive_control_count = 3
	counts_truncated = False
	positionally_scoped = False
	main_nodes = ()


def test_capture_disabled_writes_nothing(monkeypatch, tmp_path):
	nvda_dir = _reset(monkeypatch, tmp_path)
	tree_summary._append_capture(_FakeSummary())
	assert os.listdir(nvda_dir) == [], "capture log written with no opt-in marker present"


def test_capture_enabled_writes_a_record(monkeypatch, tmp_path):
	nvda_dir = _reset(monkeypatch, tmp_path)
	_opt_in(nvda_dir)
	tree_summary._append_capture(_FakeSummary())
	log_path = os.path.join(nvda_dir, "TextMarksTheSpot-captures.jsonl")
	assert os.path.exists(log_path)
	assert "example.com/private/page" in open(log_path, encoding="utf-8").read()


# --- the persistent perf log --------------------------------------------

_PERF_LINE = "[TMTS perf] total=42ms url='https://example.com/private/page?token=secret'"


def test_perf_log_disabled_writes_nothing(monkeypatch, tmp_path):
	nvda_dir = _reset(monkeypatch, tmp_path)
	tree_summary._append_perf_line(_PERF_LINE)
	assert os.listdir(nvda_dir) == [], "perf log written with no opt-in marker present"


def test_perf_log_enabled_writes_the_line(monkeypatch, tmp_path):
	nvda_dir = _reset(monkeypatch, tmp_path)
	_opt_in(nvda_dir)
	tree_summary._append_perf_line(_PERF_LINE)
	log_path = os.path.join(nvda_dir, "TextMarksTheSpot-perf.log")
	assert os.path.exists(log_path)
	assert "example.com/private/page" in open(log_path, encoding="utf-8").read()


# ---------------------------------------------------------------------------
# The suite must not write into the DEVELOPER'S OWN logs either.
#
# Added 2026-08-18 after it happened. The gate is a marker file under
# %APPDATA%\nvda, and a developer collecting real data necessarily HAS that
# marker -- so on exactly the machine where the logs matter, the suite was
# writing to them. `_log_landmark_probe` calls `_append_perf_line`, and several
# tests drive the landmark scan directly, so one sabotage_check.py run put 1022
# synthetic probe lines into a real perf log holding 4 real ones.
#
# The perf log self-rotates at 1 MB keeping one generation, so this does not
# merely add noise: enough test runs DESTROY the real browsing data the log was
# turned on to collect, and nothing looks wrong while it happens. conftest.py
# repoints APPDATA at an empty temp directory at import time; these pin it.
# ---------------------------------------------------------------------------

def test_appdata_is_redirected_away_from_the_real_one():
	real = os.path.expanduser("~")
	appdata = os.environ.get("APPDATA", "")
	assert appdata, "conftest should have set APPDATA for the test session"
	assert "tmts-test-appdata" in appdata, (
		f"APPDATA is {appdata!r}; the suite is pointed at a real profile and "
		"will write into the user's own diagnostic logs"
	)
	assert not appdata.startswith(os.path.join(real, "AppData", "Roaming")), appdata


def test_diagnostics_are_off_by_default_under_the_test_appdata():
	# The consequence that actually matters: with no marker in the redirected
	# APPDATA, every writer is inert no matter what any individual test does.
	tree_summary._DIAG_ENABLED = None
	try:
		assert tree_summary._diagnostics_enabled() is False
	finally:
		tree_summary._DIAG_ENABLED = None


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


def test_the_landmark_probe_writes_nothing_by_default():
	# The specific writer that leaked. It is reached from the landmark scan,
	# which plenty of tests drive, so it is the one most likely to leak again.
	tree_summary._DIAG_ENABLED = None
	tree_summary._PERF_LOG_PATH_CACHE = None
	try:
		root = os.path.join(os.environ["APPDATA"], "nvda")
		before = _snapshot(root)
		tree_summary._log_landmark_probe(["navigation", "banner"], True, 0, "exhausted")
		after = _snapshot(root)
		assert before == after, (
			"the landmark probe wrote to a real diagnostic log during the test "
			f"run: {[k for k in after if after.get(k) != before.get(k)]}"
		)
	finally:
		tree_summary._DIAG_ENABLED = None
		tree_summary._PERF_LOG_PATH_CACHE = None


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
# Every log.debug now goes through tree_summary.dlog. log.info (3 lifecycle
# lines) and log.exception (15, all static strings) stay ungated on purpose --
# they say nothing about where anyone has been, and they are what makes a crash
# report from a stranger worth having.
# ---------------------------------------------------------------------------

def test_gated_debug_is_silent_without_the_marker(monkeypatch, tmp_path):
	_reset(monkeypatch, tmp_path)
	seen = []
	monkeypatch.setattr(tree_summary.log, "debug", lambda *a, **k: seen.append(a))
	tree_summary.dlog.debug("[TMTS perf] url='https://example.com/private?token=abc'")
	assert seen == [], f"a url reached the session log without opt-in: {seen}"


def test_gated_debug_speaks_once_the_marker_exists(monkeypatch, tmp_path):
	# The other direction. A gate that is always closed would pass the test
	# above while making the add-on undiagnosable, so pin that opting in works.
	nvda_dir = _reset(monkeypatch, tmp_path)
	_opt_in(nvda_dir)
	seen = []
	monkeypatch.setattr(tree_summary.log, "debug", lambda *a, **k: seen.append(a))
	tree_summary.dlog.debug("[TMTS perf] url='https://example.com/'")
	assert len(seen) == 1, "opting in did not re-enable diagnostic logging"


def test_no_ungated_debug_call_survives_in_the_addon():
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


def test_lifecycle_and_crash_logging_stay_ungated():
	# Deliberately NOT gated, and worth pinning so a later privacy sweep does
	# not quietly take them too. These carry no url and no page text, and they
	# are the only thing that makes a bug report from someone who never opted in
	# worth anything.
	import pathlib

	root = pathlib.Path(__file__).resolve().parent.parent
	plugin = root / "addon" / "globalPlugins" / "TextMarksTheSpot"
	info_calls = 0
	for path in plugin.rglob("*.py"):
		text = path.read_text(encoding="utf-8")
		info_calls += text.count("log.info(")
		# An f-string on an exception line would mean interpolated content on an
		# ungated path, which is the one way these could start leaking.
		assert 'log.exception(f"' not in text, f"{path.name} interpolates into an ungated log"
	assert info_calls >= 3, "the lifecycle log lines went missing"
