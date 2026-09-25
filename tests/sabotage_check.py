"""Confirm that a test actually catches the bug it claims to catch.

WHY THIS EXISTS. Three times on this branch a safety input was found DELETABLE
with the whole suite still green. A passing test is not evidence that a rule is
enforced; the only evidence is that the test FAILS when the rule is removed.

TWO HARNESS TRAPS THIS AVOIDS, both of which have silently invalidated a
verification run on this project before:

1. THE BYTECODE CACHE CAN MAKE A SABOTAGE CHECK LIE. .pyc validation keys on
   source mtime and SIZE. A sabotage written and immediately re-run can execute
   the PREVIOUS version, reporting "the test still passes" about code that was
   never loaded. Every subprocess here runs with -B, and PYTHONDONTWRITEBYTECODE
   is set in the child environment as well.

2. A CRASH BETWEEN SABOTAGE AND RESTORE LEAVES THE FILE DAMAGED, and the next
   run treats the damage as its baseline. The original bytes are captured ONCE
   up front and rewritten in a `finally`, and the full suite is re-run at the
   end rather than the restore being trusted.

Usage:  python -B tests/sabotage_check.py
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "addon", "globalPlugins", "TextMarksTheSpot")
TREE = os.path.join(PLUGIN, "treeSummary.py")
WEB = os.path.join(PLUGIN, "detection", "web.py")
INIT = os.path.join(PLUGIN, "__init__.py")
CLASSIFIER = os.path.join(PLUGIN, "classifier.py")
CONFIG = os.path.join(PLUGIN, "config.py")


def runPytest(*args):
	env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
	return subprocess.run(
		[sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
		cwd=ROOT,
		env=env,
		capture_output=True,
		text=True,
	)


# Each sabotage reintroduces the merge blocker in a different disguise, so a
# test that only recognises the ORIGINAL spelling is caught here too.
SABOTAGES = [
	(
		"chrome-none returns verbatim",
		'	return "chrome", None, None, None, None',
		"	if landmarks.seen == 0 and landmarks.exhausted:\n"
		'		return "chrome-none", None, None, None, None\n'
		'	return "chrome", None, None, None, None',
	),
	(
		"same shortcut under a new name",
		'	return "chrome", None, None, None, None',
		"	if landmarks.seen == 0 and landmarks.exhausted:\n"
		'		return "unscoped-fast", None, None, None, None\n'
		'	return "chrome", None, None, None, None',
	),
	(
		"shortcut smuggled in as an empty exclusion list",
		'	return "chrome", None, None, None, None',
		"	if landmarks.seen == 0 and landmarks.exhausted:\n"
		'		return "chrome", None, [], None, []\n'
		'	return "chrome", None, None, None, None',
	),
	# --- Task 2: landmark ancestry from the control field stack -------------
	(
		"backend gate removed (the WebKit fail-open)",
		"	fieldsCarryLandmarks = _fieldsCarryLandmarks(info)",
		"	fieldsCarryLandmarks = True",
	),
	(
		"field verdict never consulted on the chrome path",
		"	if mainObj is None and fieldVerdict is not None:",
		"	if False:",
	),
	(
		"condition 4 violated: field stack allowed to answer main-id",
		"	if mainObj is None and fieldVerdict is not None:",
		"	if fieldVerdict is not None:",
	),
	(
		"malformed / absent control run reads as content instead of unknown",
		"	if not sawControl:\n		# No leading controlStart at all.",
		"	if False:\n		# No leading controlStart at all.",
	),
	(
		"field exclusions no longer counted as positional drops",
		"			if scopeDecision in (_SCOPE_CHROME_DROP, _SCOPE_FIELD_DROP):",
		"			if scopeDecision == _SCOPE_CHROME_DROP:",
	),
	# --- Found by review 2026-07-19: BOTH of these left the suite green. ---
	(
		"chrome-pos never consults the field stack",
		# ruff format collapsed the wrapped return onto one line on 2026-09-10.
		# The anchor keeps the two surrounding lines because that collapsed
		# return now appears twice in the file and is not unique on its own.
		"		if fieldVerdict is not None:\n"
		"			return fieldVerdict, (_SCOPE_FIELD_KEEP if fieldVerdict else _SCOPE_FIELD_DROP)\n"
		"		obj = getObj()",
		"		obj = getObj()",
	),
	(
		"innermost-wins inverted to outermost-wins",
		"	for lm in reversed(seen):",
		"	for lm in seen:",
	),
	(
		"a <main> nested inside chrome no longer wins",
		'		if lm == "main":\n			return True\n',
		"",
	),
	(
		"backend gate matches on name alone (third-party impostor trusted)",
		'			if getattr(klass, "__module__", "") == _FIELD_LANDMARK_TEXTINFO_MODULE:\n'
		"				return True",
		"			return True",
	),
	(
		# The FAITHFUL form of the original bug. Deleting the isinstance guard
		# alone is NOT equivalent: .strip() then raises on a non-string and the
		# exception handler returns None anyway, so the outcome is unchanged and
		# no test can tell. str() coercion is what actually produced a content
		# verdict from a malformed value.
		"malformed landmark value coerced into a name instead of UNKNOWN",
		"			seen.append(lm.strip().lower())",
		"			seen.append(str(lm).lower())",
	),
	(
		"landmark value not stripped before matching",
		"			seen.append(lm.strip().lower())",
		"			seen.append(lm.lower())",
	),
	# --- Diagnostic-log opt-in. Both logs record the FULL url of every page
	# --- detected. The marker gate is the only thing standing between a user
	# --- and a silent record of everywhere they go, tokens and all. Each log
	# --- is sabotaged separately: they were gated at different times, and a
	# --- test that only watches the capture log would not notice the perf log
	# --- quietly going back to collecting by default.
	(
		"capture gate removed entirely",
		"	if not _diagnosticsEnabled():\n		return\n	path = _captureLogPath()",
		"	path = _captureLogPath()",
	),
	(
		"capture gate reverted to the DEBUG log level it used to use",
		"	if not _diagnosticsEnabled():\n		return\n	path = _captureLogPath()",
		"	import logging\n"
		"	if not log.isEnabledFor(logging.DEBUG):\n"
		"		return\n"
		"	path = _captureLogPath()",
	),
	(
		"perf-log gate removed entirely",
		"	if not _diagnosticsEnabled():\n		return\n	path = _perfLogPath()",
		"	path = _perfLogPath()",
	),
	(
		"perf-log gate reverted to the DEBUG log level it used to use",
		"	if not _diagnosticsEnabled():\n		return\n	path = _perfLogPath()",
		"	import logging\n"
		"	if not log.isEnabledFor(logging.DEBUG):\n"
		"		return\n"
		"	path = _perfLogPath()",
	),
	(
		"marker check fails open when APPDATA is unreadable",
		"	except Exception:\n		_DIAG_ENABLED = False\n	return _DIAG_ENABLED",
		"	except Exception:\n		_DIAG_ENABLED = True\n	return _DIAG_ENABLED",
	),
	# --- Re-anchoring a drifted landing by text. This is the last thing
	# --- standing between a drifted capture and a silent page, and the
	# --- shortening that recovers it is only safe because a STRICTER verifier
	# --- judges every hit. Each half is sabotaged separately: a suite watching
	# --- only the shortening would not notice the verifier being dropped, and
	# --- dropping the verifier is what turns a missed landing into a wrong one.
	(
		"needle ladder removed, back to one full-width search",
		"	for width in (len(needle),) + _FIND_NEEDLE_LADDER:",
		"	for width in (len(needle),):",
	),
	(
		"ladder present but every rung collapses to the full needle",
		'			cand = needle[:width].rsplit(" ", 1)[0]',
		"			cand = needle",
	),
	(
		"NBSP variant no longer offered",
		'		for form in (cand, cand.replace("\\xa0", " ")):',
		"		for form in (cand,):",
	),
	(
		"hit accepted without asking the verifier",
		"			if verify(foundText):",
		"			if True:",
	),
	(
		"shortening no longer gated on a verifier being supplied",
		"		if verify is None:",
		"		if False:",
	),
	(
		"search floor raised above the verification width",
		"_MIN_FIND_NEEDLE_CHARS = 20",
		"_MIN_FIND_NEEDLE_CHARS = 30",
	),
	(
		"ladder run blind, every rung paying for a real find()",
		"			if haystack and haystack.count(cand) != 1:",
		"			if False:",
	),
	(
		# The whole safety argument for shortening. A presence test looks like
		# a harmless simplification of this line and is the actual bug: find()
		# returns the FIRST hit, and the caller's verifier compares only 24
		# normalised characters, so a teaser repeating its lede's opening is
		# accepted as the lede.
		"uniqueness weakened to mere presence",
		"			if haystack and haystack.count(cand) != 1:",
		"			if haystack and haystack.find(cand, 1) < 0:",
	),
	(
		"uniqueness weakened to at-least-one",
		"			if haystack and haystack.count(cand) != 1:",
		"			if haystack and haystack.count(cand) < 1:",
	),
	# --- Session-log gate. The persistent logs were gated in July; this is the
	# --- copy that goes to NVDA's own log, carrying the same urls plus 60-char
	# --- previews of the page. Gated 2026-08-18 so the add-on cannot become a
	# --- browsing record on anyone's machine but the one that opted in.
	(
		"gated debug logger left permanently open",
		"		if _diagnosticsEnabled():\n			log.debug(*args, **kwargs)",
		"		if True:\n			log.debug(*args, **kwargs)",
	),
	(
		"gate inverted so opting OUT is what enables logging",
		"		if _diagnosticsEnabled():\n			log.debug(*args, **kwargs)",
		"		if not _diagnosticsEnabled():\n			log.debug(*args, **kwargs)",
	),
	(
		"depleted net stops respecting chrome-scope exclusions",
		'	elif scopeKind in ("chrome", "chrome-pos") and positionalDrops == 0:',
		'	elif scopeKind == "chrome-pos" and positionalDrops == 0:\n'
		"		pass\n"
		'	elif scopeKind == "chrome":',
	),
	# --- Security audit 2026-09-24: a web page must not be able to freeze
	# --- NVDA through a quadratic regex over a chunk's full text.
	(
		"copyright whitespace runs made backtracking again",
		r"\bcopyright\s*+(?:©|\(c\))?\s*+(?:19|20)",
		r"\bcopyright\s*(?:©|\(c\))?\s*(?:19|20)",
		WEB,
	),
	(
		"caption check goes back to the bare quadratic search",
		"	if _hasTrailingPhotoCredit(text):\n		return True",
		"	if _PHOTO_CREDIT_END_RE.search(text):\n		return True",
		WEB,
	),
	(
		"photo-credit tail check removed, so every opener rescans",
		"	if close < 0 or not _AFTER_CREDIT_PAREN_RE.fullmatch(text, close + 1):",
		"	if close < 0:",
		WEB,
	),
	(
		"shortened find rung used on presence alone when the buffer copy fails",
		"			if not haystack and cand != needle:",
		"			if False:",
	),
	(
		"diagnostics ignore NVDA's secure-mode write rule",
		"	if not folder or not _nvdaAllowsDiskWrites():",
		"	if not folder:",
	),
	(
		"diagnostics folder hard-coded to APPDATA again",
		'		configPath = getattr(getattr(globalVars, "appArgs", None), "configPath", None)',
		"		configPath = None",
	),
	(
		"log appends forever when rotation keeps failing",
		"		return size <= 2 * maxBytes",
		"		return True",
	),
	(
		"URL hints see redirect parameters again",
		"	url = _hintableUrl(tree.url)",
		"	url = tree.url.lower()",
		CLASSIFIER,
	),
	(
		"URL hints drop the query entirely",
		'		if "/" in _unquote(value):',
		"		if True:",
		CLASSIFIER,
	),
	(
		"exclusion matching forgets the trailing dot",
		'	host = (hostname or "").strip().lower().rstrip(".")',
		'	host = (hostname or "").strip().lower()',
		CONFIG,
	),
	(
		"exclusion matching forgets IDNA",
		'		return host.encode("idna").decode("ascii")',
		"		return host",
		CONFIG,
	),
	(
		"walk cut short by an error reports itself complete again",
		"			interrupted = not _isAtDocumentEnd(treeInterceptor, info)",
		"			interrupted = False",
	),
	(
		"every walk ending on an error counts as interrupted",
		"			interrupted = not _isAtDocumentEnd(treeInterceptor, info)",
		"			interrupted = True",
	),
	(
		"ready mail documents auto-landed again",
		"		if not bypassExclusion and _isMailDocument(ti):",
		"		if False:",
		INIT,
	),
	(
		"mail skip also blocks explicit requests",
		"		if not bypassExclusion and _isMailDocument(ti):",
		"		if _isMailDocument(ti):",
		INIT,
	),
	(
		"retry runs in a background tab again",
		'			return\n		if _focusIsOnAnotherDocument(ti):\n			dlog.debug("[TMTS] retry:',
		'			return\n		if False:\n			dlog.debug("[TMTS] retry:',
		INIT,
	),
	(
		"readiness poll fires in a background tab again",
		'			if _focusIsOnAnotherDocument(ti):\n				dlog.debug("[TMTS] readiness poll:',
		'			if False:\n				dlog.debug("[TMTS] readiness poll:',
		INIT,
	),
	(
		"focus with no document counts as another document",
		"	return focusTi is not None and focusTi is not ti",
		"	return focusTi is not ti",
		INIT,
	),
	(
		"Shift+Z trusts the saved bookmark without checking it",
		'				if webMod.landingTextMatches(cand.text or "", node):\n					return saved, cand',
		"				if True:\n					return saved, cand",
		INIT,
	),
	(
		"Shift+Z uses another tab's bookmark again",
		"		if savedTi is ti:",
		"		if True:",
		INIT,
	),
	(
		"Z never walks again from the cursor",
		"				if nextIdx is None and summary.walkTruncated:",
		"				if False:",
		INIT,
	),
	(
		"Z second pass walks on every page",
		"				if nextIdx is None and summary.walkTruncated:",
		"				if nextIdx is None:",
		INIT,
	),
	(
		"Z second pass lands from a fallen-back tree",
		"						if not second.scopeFellBack:",
		"						if True:",
		INIT,
	),
	(
		"NVDA+Z announces success regardless of the write",
		"				if cfgMod.addDisabledSite(hostname) or cfgMod.isSiteDisabled(hostname):",
		"				if cfgMod.addDisabledSite(hostname) or True:",
		INIT,
	),
	(
		"form-focus search unbounded again",
		"				if scanned > _FOCUS_SCAN_LIMIT or time.monotonic() > deadline:",
		"				if False:",
	),
	(
		"form-focus search loses only its deadline",
		"				if scanned > _FOCUS_SCAN_LIMIT or time.monotonic() > deadline:",
		"				if scanned > _FOCUS_SCAN_LIMIT:",
	),
	(
		"form-field object fetched eagerly again",
		'	def getObj():\n		return getattr(item, "obj", None)\n',
		'	_eager = getattr(item, "obj", None)\n\n	def getObj():\n		return _eager\n',
	),
]


def main():
	# An entry is (name, find, replace) against treeSummary.py, or
	# (name, find, replace, path) against another source file.
	entries = [e if len(e) == 4 else (*e, TREE) for e in SABOTAGES]
	paths = sorted({e[3] for e in entries})
	originals = {p: open(p, "rb").read() for p in paths}  # captured ONCE, before anything
	failures = []
	try:
		base = runPytest("tests/")
		if base.returncode != 0:
			print("BASELINE IS ALREADY RED -- fix that first.")
			print(base.stdout[-3000:])
			return 1
		print("baseline: green")

		# Anchors below are written with \n. Git can hand a file back with
		# CRLF endings after a checkout, and every MULTI-LINE anchor then misses
		# with "0 hits" - which reads like a stale anchor and quietly retires the
		# check. Normalize for matching; the original bytes are restored either
		# way in the finally.
		texts = {p: originals[p].decode("utf-8").replace("\r\n", "\n") for p in paths}
		for name, find, replace, path in entries:
			text = texts[path]
			if text.count(find) != 1:
				failures.append(f"{name}: anchor not unique ({text.count(find)} hits)")
				continue
			try:
				open(path, "w", encoding="utf-8", newline="").write(text.replace(find, replace, 1))
				res = runPytest("tests/")
			finally:
				open(path, "wb").write(originals[path])
			if res.returncode == 0:
				failures.append(f"{name}: SUITE STAYED GREEN -- the test does not catch this")
				print(f"  NOT CAUGHT: {name}")
			else:
				print(f"  caught:     {name}")
	finally:
		for p in paths:
			open(p, "wb").write(originals[p])

	# Do not trust the restore -- prove it.
	for p in paths:
		assert open(p, "rb").read() == originals[p], f"RESTORE FAILED; {p} is damaged"
	final = runPytest("tests/")
	if final.returncode != 0:
		print("POST-RESTORE SUITE IS RED:")
		print(final.stdout[-3000:])
		return 1
	print("restored, full suite green")

	if failures:
		print("\nSABOTAGE CHECK FAILED:")
		for f in failures:
			print("  - " + f)
		return 1
	print("\nAll sabotages caught.")
	return 0


if __name__ == "__main__":
	sys.exit(main())
