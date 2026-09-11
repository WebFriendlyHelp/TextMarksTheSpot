# Golden-corpus regression test.
#
# tests/fixtures/local/capture_corpus.jsonl holds FAITHFUL page snapshots captured
# from real browsing (see _appendCapture in treeSummary.py): every field the
# classifier and landing finders actually read. Replaying a record reproduces the
# add-on's real decision exactly, with no NVDA. This locks in the landings we've
# verified on real pages, so a future classifier/landing change that regresses one
# of them fails here instead of in a soak.
#
# The corpus is DELIBERATELY NOT IN THE REPOSITORY (.gitignore covers
# tests/fixtures/local/). It is a record of someone's real browsing: full URLs,
# query strings and all, plus previews of the text on each page. That does not
# belong in a public repo, and a data file shaped like a browsing log is an
# invitation to paste more of one in. Keep it local; keep adding to it by hand
# from pages worth pinning. Every case below skips itself when the file is
# absent, so a fresh clone runs green with no corpus at all.
#
# Each case asserts a substring of the LANDED node's preview — readable and
# stable against the frozen fixture. A known-bad landing is an xfail carrying the
# desired target, so it flips to a failure (telling us to drop the xfail) the day
# it starts landing right.

import json
import os

import pytest

from replay_captures import replay  # noqa: E402  (adds the addon dir to sys.path)

_CORPUS = os.path.join(os.path.dirname(__file__), "fixtures", "local", "capture_corpus.jsonl")


def _records():
	if not os.path.exists(_CORPUS):
		pytest.skip("no local capture corpus (tests/fixtures/local/) - see this file's header")
	with open(_CORPUS, encoding="utf-8") as fh:
		return [json.loads(line) for line in fh if line.strip()]


def _find(urlFrag):
	for r in _records():
		if urlFrag in r["url"]:
			return r
	raise AssertionError(f"no captured record with URL containing {urlFrag!r}")


# (url fragment, expected substring of the landed node's preview, xfail reason or None)
CASES = [
	# Confirmed-correct landings on real ledes / opening content.
	("thegatewaypundit", "The Orange traffic barrel", None),  # dated-byline fix
	("redstate.com/wardclark", "On Sunday, a new report", None),  # opinion-disclaimer fix
	("dailymail.com/sciencetech", "A tropical storm erupted", None),
	("zerohedge.com/news", "markets had been pricing", None),
	("zdnet.com/article/lastpass", "third-party supplier breach", None),
	("flexibits.com/blog", "Booking a meeting with your teammates", None),
	("arstechnica.com/", "When your vehicle outlives its cloud", None),
	("windowslatest.com", "Azure Linux 4.0", None),
	# Aggregator front page: landing on the first bullet headline is correct
	# (nothing on the page ends like a sentence; see findArticleLanding).
	("stevequayle.com", "Apocalypse Early Warning System", None),
	# News index / homepage pages: the headline-list gate lands on the first
	# headline instead of deep chrome (newsletter box / footer). These were the
	# 2026-07-21 mislandings (Tom's Hardware on a newsletter CTA, etc.).
	("tomshardware.com", "Nvidia's DLSS 5", None),
	("lite.cnn.com", "A timeline of US strikes on boats", None),
	("text.npr.org", "A homeless man was charged", None),
	# KNOWN GAP, LEFT DELIBERATELY (Casey's call, 2026-07-21): the author bio
	# ("After a 7-year corporate stint, Tanveer found his love for writing...",
	# 337 chars) wins the very-substantial gate before the real body. It has NO
	# structural anchor the add-on can see (no "About the author" heading, not in
	# a landmark) - it's a plain paragraph after the date line, indistinguishable
	# from a first body paragraph without open-vocabulary word-matching that would
	# risk eating real ledes. So it stays as-is; the cost is one Down arrow. This
	# xfail documents the shape, not a TODO. Anchored bios (under a heading / in a
	# footer) sit AFTER the body and never mislead the landing.
	("xda-developers", "Most modern Wi-Fi", "author bio, no reliable anchor - left deliberately, not a TODO"),
]


@pytest.mark.parametrize("urlFrag,expect,xfailReason", CASES)
def test_corpusLanding(urlFrag, expect, xfailReason):
	if xfailReason:
		pytest.xfail(xfailReason)
	rec = _find(urlFrag)
	out = replay(rec)
	preview = out["landing_preview"] or ""
	assert expect in preview, (
		f"{urlFrag}: expected {expect!r} in landed preview, "
		f"got {out['intent']} idx={out['landing_idx']} :: {preview!r}"
	)
