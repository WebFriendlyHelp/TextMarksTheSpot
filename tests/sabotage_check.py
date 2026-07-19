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
TREE = os.path.join(ROOT, "addon", "globalPlugins", "TextMarksTheSpot", "tree_summary.py")


def run_pytest(*args):
	env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
	return subprocess.run(
		[sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
		cwd=ROOT, env=env, capture_output=True, text=True,
	)


# Each sabotage reintroduces the merge blocker in a different disguise, so a
# test that only recognises the ORIGINAL spelling is caught here too.
SABOTAGES = [
	(
		"chrome-none returns verbatim",
		'	return "chrome", None, None, None, None',
		'	if landmarks.seen == 0 and landmarks.exhausted:\n'
		'		return "chrome-none", None, None, None, None\n'
		'	return "chrome", None, None, None, None',
	),
	(
		"same shortcut under a new name",
		'	return "chrome", None, None, None, None',
		'	if landmarks.seen == 0 and landmarks.exhausted:\n'
		'		return "unscoped-fast", None, None, None, None\n'
		'	return "chrome", None, None, None, None',
	),
	(
		"shortcut smuggled in as an empty exclusion list",
		'	return "chrome", None, None, None, None',
		'	if landmarks.seen == 0 and landmarks.exhausted:\n'
		'		return "chrome", None, [], None, []\n'
		'	return "chrome", None, None, None, None',
	),
	# --- Task 2: landmark ancestry from the control field stack -------------
	(
		"backend gate removed (the WebKit fail-open)",
		"	fields_carry_landmarks = _fields_carry_landmarks(info)",
		"	fields_carry_landmarks = True",
	),
	(
		"field verdict never consulted on the chrome path",
		"	if main_obj is None and field_verdict is not None:",
		"	if False:",
	),
	(
		"condition 4 violated: field stack allowed to answer main-id",
		"	if main_obj is None and field_verdict is not None:",
		"	if field_verdict is not None:",
	),
	(
		"malformed / absent control run reads as content instead of unknown",
		"	if not saw_control:\n		# No leading controlStart at all.",
		"	if False:\n		# No leading controlStart at all.",
	),
	(
		"field exclusions no longer counted as positional drops",
		"			if scope_decision in (_SCOPE_CHROME_DROP, _SCOPE_FIELD_DROP):",
		"			if scope_decision == _SCOPE_CHROME_DROP:",
	),
	(
		"depleted net stops respecting chrome-scope exclusions",
		'	elif scope_kind in ("chrome", "chrome-pos") and positional_drops == 0:',
		'	elif scope_kind == "chrome-pos" and positional_drops == 0:\n'
		'		pass\n'
		'	elif scope_kind == "chrome":',
	),
]


def main():
	original = open(TREE, "rb").read()          # captured ONCE, before anything
	failures = []
	try:
		base = run_pytest("tests/")
		if base.returncode != 0:
			print("BASELINE IS ALREADY RED -- fix that first.")
			print(base.stdout[-3000:])
			return 1
		print("baseline: green")

		text = original.decode("utf-8")
		for name, find, replace in SABOTAGES:
			if text.count(find) != 1:
				failures.append(f"{name}: anchor not unique ({text.count(find)} hits)")
				continue
			open(TREE, "w", encoding="utf-8", newline="").write(text.replace(find, replace, 1))
			res = run_pytest("tests/")
			if res.returncode == 0:
				failures.append(f"{name}: SUITE STAYED GREEN -- the test does not catch this")
				print(f"  NOT CAUGHT: {name}")
			else:
				print(f"  caught:     {name}")
	finally:
		open(TREE, "wb").write(original)

	# Do not trust the restore -- prove it.
	assert open(TREE, "rb").read() == original, "RESTORE FAILED; source is damaged"
	final = run_pytest("tests/")
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
