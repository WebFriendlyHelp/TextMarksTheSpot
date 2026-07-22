# The capture log must stay OFF for everyone who did not deliberately ask for it.
#
# _append_capture records the FULL url of every page detected, query string and
# all, plus previews of the text on it. On one real day of browsing that included
# an invoice link, OAuth authorization codes, and an application path carrying a
# client secret. Shipping that to users who merely turned NVDA's log level up to
# DEBUG (which people do for unrelated reasons, and which is what used to gate
# this) would be recording where they go without them ever knowing.
#
# So the gate is a marker file nobody creates by accident. These tests pin the
# gate itself and the fact that _append_capture honors it. Delete the check in
# tree_summary._append_capture and test_disabled_writes_nothing fails.

import os

import tree_summary


def _reset(monkeypatch, appdata):
	monkeypatch.setattr(tree_summary, "_CAPTURE_ENABLED", None, raising=False)
	monkeypatch.setattr(tree_summary, "_CAPTURE_LOG_PATH_CACHE", None, raising=False)
	monkeypatch.setenv("APPDATA", str(appdata))
	nvda_dir = os.path.join(str(appdata), "nvda")
	os.makedirs(nvda_dir, exist_ok=True)
	return nvda_dir


def test_disabled_without_marker(monkeypatch, tmp_path):
	_reset(monkeypatch, tmp_path)
	assert tree_summary._capture_enabled() is False


def test_enabled_with_marker(monkeypatch, tmp_path):
	nvda_dir = _reset(monkeypatch, tmp_path)
	open(os.path.join(nvda_dir, tree_summary._CAPTURE_MARKER_NAME), "w").close()
	assert tree_summary._capture_enabled() is True


def test_disabled_when_appdata_missing(monkeypatch, tmp_path):
	_reset(monkeypatch, tmp_path)
	monkeypatch.delenv("APPDATA", raising=False)
	assert tree_summary._capture_enabled() is False


def test_disabled_when_the_marker_check_itself_raises(monkeypatch, tmp_path):
	# A permission error, a dead network drive, anything: the answer is OFF.
	# Failing open here would start recording on a machine we could not even
	# read a filename on, which is the worst place to guess "yes".
	_reset(monkeypatch, tmp_path)

	def _boom(_path):
		raise OSError("cannot stat")

	monkeypatch.setattr(os.path, "exists", _boom)
	assert tree_summary._capture_enabled() is False


def test_verdict_is_cached_for_the_session(monkeypatch, tmp_path):
	# Creating the marker mid-session must not switch recording on underneath a
	# user who is already browsing; it takes effect at the next NVDA restart.
	nvda_dir = _reset(monkeypatch, tmp_path)
	assert tree_summary._capture_enabled() is False
	open(os.path.join(nvda_dir, tree_summary._CAPTURE_MARKER_NAME), "w").close()
	assert tree_summary._capture_enabled() is False


class _FakeSummary:
	url = "https://example.com/private/page?token=secret"
	has_main_landmark = True
	article_count = 1
	form_input_count = 0
	interactive_control_count = 3
	counts_truncated = False
	positionally_scoped = False
	main_nodes = ()


def test_disabled_writes_nothing(monkeypatch, tmp_path):
	nvda_dir = _reset(monkeypatch, tmp_path)
	tree_summary._append_capture(_FakeSummary())
	assert os.listdir(nvda_dir) == [], "capture log written with no opt-in marker present"


def test_enabled_writes_a_record(monkeypatch, tmp_path):
	nvda_dir = _reset(monkeypatch, tmp_path)
	open(os.path.join(nvda_dir, tree_summary._CAPTURE_MARKER_NAME), "w").close()
	tree_summary._append_capture(_FakeSummary())
	log_path = os.path.join(nvda_dir, "TextMarksTheSpot-captures.jsonl")
	assert os.path.exists(log_path)
	assert "example.com/private/page" in open(log_path, encoding="utf-8").read()
