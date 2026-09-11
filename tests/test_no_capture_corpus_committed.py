# A capture record must never be committed to this repository.
#
# The capture log is a record of real browsing: the FULL url of every page
# detected, query string and all, plus previews of the text on it. A corpus of
# them was tracked here once (13 public news pages, no tokens, so it was
# precedent rather than exposure) and was removed 2026-07-22. .gitignore keeps
# tests/fixtures/local/ out, but .gitignore only protects the ONE path someone
# thought of. This test protects the property.
#
# It looks for the SHAPE rather than the path or the filename, because the
# realistic way this comes back is not someone re-adding the same file. It is a
# future session banking a corpus somewhere new, under a new name, believing it
# is fine because it "only has a few pages in it".
#
# Detection is a real JSON parse, not a substring match, so source files that
# merely discuss the format (this one included) do not trip it.

import json
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Anything larger is not a hand-authored fixture; reading it here would only
# slow the suite. A capture corpus big enough to matter is far under this.
_MAX_BYTES = 4_000_000


def _trackedFiles():
	try:
		out = subprocess.run(
			["git", "ls-files", "-z"],
			cwd=ROOT,
			capture_output=True,
			text=True,
			timeout=30,
		)
	except (OSError, subprocess.SubprocessError):
		pytest.skip("git not available")
	if out.returncode != 0:
		pytest.skip("not a git checkout")
	return [p for p in out.stdout.split("\0") if p]


def _looksLikeACaptureRecord(line):
	line = line.strip()
	if not line.startswith("{"):
		return False
	try:
		rec = json.loads(line)
	except ValueError:
		return False
	if not isinstance(rec, dict):
		return False
	# The two fields that make a record a page capture: where the user was, and
	# what was on the page. Either alone is ordinary config; together they are a
	# browsing record.
	return "url" in rec and "nodes" in rec


def test_noCaptureRecordIsTracked():
	offenders = []
	for rel in _trackedFiles():
		path = os.path.join(ROOT, rel)
		try:
			if os.path.getsize(path) > _MAX_BYTES:
				continue
			with open(path, encoding="utf-8") as fh:
				for lineno, line in enumerate(fh, 1):
					if _looksLikeACaptureRecord(line):
						offenders.append(f"{rel}:{lineno}")
						break
		except (OSError, UnicodeDecodeError):
			continue  # binary or unreadable; not a corpus

	assert not offenders, (
		"page-capture records are tracked in git: "
		+ ", ".join(offenders)
		+ ". These contain real urls and page text. Move the file under "
		"tests/fixtures/local/ (gitignored) and keep repo fixtures hand-authored."
	)
