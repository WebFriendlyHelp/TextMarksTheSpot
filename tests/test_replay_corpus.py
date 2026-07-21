# Golden-corpus regression test.
#
# tests/fixtures/capture_corpus.jsonl holds FAITHFUL page snapshots captured from
# real browsing (see _append_capture in tree_summary.py): every field the
# classifier and landing finders actually read. Replaying a record reproduces the
# add-on's real decision exactly, with no NVDA. This locks in the landings we've
# verified on real pages this week, so a future classifier/landing change that
# regresses one of them fails here instead of in a soak.
#
# Each case asserts a substring of the LANDED node's preview — readable and
# stable against the frozen fixture. A known-bad landing is an xfail carrying the
# desired target, so it flips to a failure (telling us to drop the xfail) the day
# it starts landing right.

import json
import os

import pytest

from replay_captures import replay  # noqa: E402  (adds the addon dir to sys.path)

_CORPUS = os.path.join(os.path.dirname(__file__), "fixtures", "capture_corpus.jsonl")


def _records():
    with open(_CORPUS, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _find(url_frag):
    for r in _records():
        if url_frag in r["url"]:
            return r
    raise AssertionError(f"no captured record with URL containing {url_frag!r}")


# (url fragment, expected substring of the landed node's preview, xfail reason or None)
CASES = [
    # Confirmed-correct landings on real ledes / opening content.
    ("thegatewaypundit", "The Orange traffic barrel", None),      # dated-byline fix
    ("redstate.com/wardclark", "On Sunday, a new report", None),  # opinion-disclaimer fix
    ("dailymail.com/sciencetech", "A tropical storm erupted", None),
    ("zerohedge.com/news", "markets had been pricing", None),
    ("zdnet.com/article/lastpass", "third-party supplier breach", None),
    ("flexibits.com/blog", "Booking a meeting with your teammates", None),
    ("arstechnica.com/", "When your vehicle outlives its cloud", None),
    ("windowslatest.com", "Azure Linux 4.0", None),
    # Aggregator front page: landing on the first bullet headline is correct
    # (nothing on the page ends like a sentence; see find_article_landing).
    ("stevequayle.com", "Apocalypse Early Warning System", None),
    # KNOWN BAD: the author bio ("After a 7-year corporate stint, Tanveer found
    # his love for writing...") is 337 chars, so it wins the very-substantial
    # gate before the real body. The giveaway word sits past the 60-char preview,
    # so a fix needs a walk-time author-bio flag; deferred, not shipped blind.
    ("xda-developers", "Most modern Wi-Fi", "author bio wins very-substantial gate; needs a bio flag"),
]


@pytest.mark.parametrize("url_frag,expect,xfail_reason", CASES)
def test_corpus_landing(url_frag, expect, xfail_reason):
    if xfail_reason:
        pytest.xfail(xfail_reason)
    rec = _find(url_frag)
    out = replay(rec)
    preview = out["landing_preview"] or ""
    assert expect in preview, (
        f"{url_frag}: expected {expect!r} in landed preview, "
        f"got {out['intent']} idx={out['landing_idx']} :: {preview!r}"
    )
