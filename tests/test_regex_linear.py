"""The full-text detectors must run in linear time on hostile page text.

Every walked chunk's FULL text goes through `_looksLikeImageCaption` and
`_looksLikeLegalBoilerplate` on NVDA's main thread, inside a single regex call
the 2 s walk deadline cannot interrupt. Before 2026-09-24 both were quadratic:
"Copyright" plus 40,000 non-breaking spaces froze NVDA for about five seconds,
and "(ap " repeated 40,000 times for about two. A frozen screen reader leaves a
blind user with no output at all, so a web page must not be able to do that.

Two kinds of test, because each alone proves a nearby proposition:
  * TIMING tests prove the hostile inputs are now fast. They alone would pass
    on a fix that simply stopped matching anything.
  * EQUIVALENCE tests prove the new code answers exactly what the old pattern
    answered, over many random strings built from the characters that matter.
    They alone would pass on the old slow code.
"""

import random
import re
import time

from detection import web

# The patterns exactly as they were before the fix, kept here as the reference
# the new code must agree with. Only ever run on short strings.
_OLD_PHOTO = re.compile(
	r"\(\s*(?:photo|image|getty|ap|reuters|afp|epa|bloomberg|"
	r"istock(?:photo)?|shutterstock|adobe\s+stock|unsplash|pexels|pixabay|"
	r"dreamstime|depositphotos|wikimedia|file\s+photo|courtesy)\b[^)]*\)\s*\.?\s*$",
	re.IGNORECASE,
)
_OLD_LEGAL = re.compile(
	r"\ball rights reserved\b"
	r"|\bcopyright\s*(?:©|\(c\))?\s*(?:19|20)\d{2}\b"
	r"|©\s*(?:19|20)\d{2}\b"
	r"|\bdo not sell (?:or share )?my personal information\b"
	r"|\byou\s+(?:agree|consent)\s+to\s+(?:our|the|these)\s+(?:terms|privacy\s+policy)\b",
	re.IGNORECASE,
)

# Generous: the fixed code takes a few milliseconds here, the old code took
# seconds. A loaded CI runner still clears this by two orders of magnitude.
_BUDGET_SEC = 0.5
_N = 40_000


def _timed(fn, arg):
	t = time.perf_counter()
	result = fn(arg)
	return result, time.perf_counter() - t


def test_copyrightFollowedByAHugeWhitespaceRunIsFast():
	for ws in (" ", " ", "\t"):
		result, took = _timed(web._looksLikeLegalBoilerplate, "Copyright" + ws * _N + "x")
		assert result is False
		assert took < _BUDGET_SEC, f"{took:.2f}s on {ws!r}"


def test_copyrightWithHugeRunStillMatchesARealYear():
	# The negative twin: the fast path must still FIND a copyright line.
	assert web._looksLikeLegalBoilerplate("Copyright" + " " * _N + "2026 Acme")
	assert web._looksLikeLegalBoilerplate("Copyright  ©  2024 Example Corp.")


def test_repeatedCreditOpenersWithNoCloseAreFast():
	for payload in ("(ap " * _N, "(photo " * _N, "(ap " * _N + ")x", "(getty) " + "(ap " * _N + ")!"):
		result, took = _timed(web._looksLikeImageCaption, payload)
		assert result is False
		assert took < _BUDGET_SEC, f"{took:.2f}s on {payload[:20]!r}..."


def test_hugeWhitespaceAfterTheCreditParenIsFast():
	result, took = _timed(web._looksLikeImageCaption, "Caption (AP Photo)" + " " * _N + "x")
	assert result is False
	assert took < _BUDGET_SEC


def test_longCaptionWithRealTrailingCreditStillMatches():
	assert web._looksLikeImageCaption("word " * _N + "(Getty Images)")
	assert web._looksLikeImageCaption("A scenic overlook at sunset (Photo: Jane Doe) .  ")


# Alphabet chosen to exercise every branch of both patterns: parens, periods,
# whitespace of three kinds, the agency and copyright words, digits and ©.
_TOKENS = [
	"(",
	")",
	".",
	" ",
	" ",
	"\t",
	"ap",
	"AP",
	"photo",
	"getty",
	"file photo",
	"x",
	"copyright",
	"©",
	"(c)",
	"20",
	"19",
	"26",
	"all rights reserved",
	"a",
	"!",
]


def _randomText(rng):
	return "".join(rng.choice(_TOKENS) for _ in range(rng.randint(0, 14)))


def test_photoCreditAnswersExactlyAsTheOldPatternDid():
	rng = random.Random(20260924)
	for _ in range(60_000):
		s = _randomText(rng)
		assert web._hasTrailingPhotoCredit(s) == bool(_OLD_PHOTO.search(s)), repr(s)


def test_legalBoilerplateAnswersExactlyAsTheOldPatternDid():
	rng = random.Random(20260925)
	for _ in range(60_000):
		s = _randomText(rng)
		assert bool(web._LEGAL_BOILERPLATE_RE.search(s)) == bool(_OLD_LEGAL.search(s)), repr(s)
