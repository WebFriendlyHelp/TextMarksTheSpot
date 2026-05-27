# -*- coding: UTF-8 -*-
# Test harness: run the intent classifier against all fixtures and print
# a pass/fail report. Pure Python, no NVDA needed.
#
# Run:    python tests/run_classifier.py

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "textMarksTheSpot"))
sys.path.insert(0, os.path.dirname(__file__))

from classifier import classify
from classifier_fixtures import ALL_FIXTURES


def main() -> int:
	pass_count = 0
	fail_count = 0
	results = []

	for label, expected, tree in ALL_FIXTURES:
		result = classify(tree)
		ok = result.intent == expected
		results.append((label, expected, result, ok))
		if ok:
			pass_count += 1
		else:
			fail_count += 1

	# Plain ASCII output — no Unicode box-drawing (global CLAUDE.md rule).
	print()
	print("Classifier fixture report")
	print("-" * 60)
	for label, expected, result, ok in results:
		marker = "PASS" if ok else "FAIL"
		print(f"[{marker}] {label}")
		print(f"       expected: {expected.value}")
		print(f"       got:      {result}")
		print()

	print("-" * 60)
	print(f"Total: {pass_count} pass, {fail_count} fail")
	return 0 if fail_count == 0 else 1


if __name__ == "__main__":
	sys.exit(main())
