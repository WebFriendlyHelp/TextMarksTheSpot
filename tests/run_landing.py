# -*- coding: UTF-8 -*-
# Test harness for the article landing strategy.
#
# For every fixture the classifier labels as ARTICLE, this harness checks
# that find_article_landing() returns the index a human reader would expect.
# Non-article fixtures are skipped (the article strategy isn't called on
# them; other intents have their own strategies — not built yet).
#
# Run:    python tests/run_landing.py

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "textMarksTheSpot"))
sys.path.insert(0, os.path.dirname(__file__))

from classifier import Intent
from detection.web import find_article_landing
from classifier_fixtures import (
	WIKIPEDIA_MEMORIAL_DAY,
	MAKEUSEOF_ARTICLE,
	WDBO_ARTICLE,
	WEBFRIENDLYHELP_HOME,
	PATTYSWORLDS_HOME,
	GLIDANCE_HOME,
	STARBUCKS_HOME,
	SSA_HOME,
	SAM_GOV_HOME,
	APPLEVIS_ARTICLE,
	LWORKS_HOME,
	CLEVERBRAILLE_HOME,
	ACB_HOME,
	NFB_HOME,
)


# Human-encoded ground truth: index into fixture.main_nodes where the cursor
# should land for each ARTICLE fixture. Reviewed against the page content the
# user named as the target.
EXPECTED_LANDING = [
	(WIKIPEDIA_MEMORIAL_DAY, 1),    # H1, P 280 (lead)
	(MAKEUSEOF_ARTICLE,      1),    # H1, P 420 (intro)
	(WDBO_ARTICLE,           2),    # H1, H2 dek, P 180 (body)
	(WEBFRIENDLYHELP_HOME,   2),    # H2, H1, P 115 (welcome)
	(PATTYSWORLDS_HOME,      1),    # H3, P 220 (welcome)
	(GLIDANCE_HOME,          1),    # H1, P 180 (hero)
	(STARBUCKS_HOME,         2),    # H2 promo, H1, P 190 (hero)
	(SSA_HOME,               1),    # H2, P 130 (register CTA paragraph)
	(SAM_GOV_HOME,          11),    # H1, P 40, H2, 6×short P, H2, H2, P 110
	(APPLEVIS_ARTICLE,       3),    # H1, P 25, H3, P 265 (description)
	(LWORKS_HOME,            2),    # H1, P 62 tagline, P 250 (description)
	(CLEVERBRAILLE_HOME,     0),    # P 180 (first node)
	(ACB_HOME,               1),    # H1, P 400 (hero)
	(NFB_HOME,               2),    # H1, H1, P 470 (mission)
]


def main() -> int:
	pass_count = 0
	fail_count = 0

	print()
	print("Article landing strategy report")
	print("-" * 60)
	for fixture, expected_index in EXPECTED_LANDING:
		label, expected_intent, tree = fixture
		if expected_intent != Intent.ARTICLE:
			print(f"[SKIP] {label} (not an article fixture)")
			continue

		got = find_article_landing(tree)
		ok = (got == expected_index)
		marker = "PASS" if ok else "FAIL"
		print(f"[{marker}] {label}")
		print(f"       expected landing index: {expected_index}")
		print(f"       got:                    {got}")
		if got is not None and 0 <= got < len(tree.main_nodes):
			n = tree.main_nodes[got]
			preview = n.text_preview or ""
			print(f"       landed on: {n.kind} (len={n.text_length}) {preview!r}")
		print()

		if ok:
			pass_count += 1
		else:
			fail_count += 1

	print("-" * 60)
	print(f"Total: {pass_count} pass, {fail_count} fail")
	return 0 if fail_count == 0 else 1


if __name__ == "__main__":
	sys.exit(main())
