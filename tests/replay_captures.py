#!/usr/bin/env python3
"""Replay captured page snapshots through the classifier + landing finders.

The add-on writes one JSON record per detection to
`%APPDATA%\\nvda\\TextMarksTheSpot-captures.jsonl` (see `_appendCapture` in
treeSummary.py). Each record carries the FULL node list with every field the
classifier and landing finders actually read — kind, level, length, 60-char
preview, and the four walk-time flags. Those finders never look at anything
else, so replaying a record reproduces the add-on's real decision EXACTLY,
with no NVDA and no browser. That makes captures.jsonl a faithful regression
corpus built from real browsing.

Usage:
    python tests/replay_captures.py                 # reads the AppData capture log
    python tests/replay_captures.py path/to/file.jsonl
    python tests/replay_captures.py --url substr    # only rows whose URL contains substr

This is a REPORTING tool: it prints, per captured page, the classified intent
and the landing the finders would pick (index + preview). Turn a row whose
decision you have verified into a permanent assertion by copying its node list
into tests/test_landing.py or tests/test_classifier.py.
"""

from __future__ import annotations

import json
import os
import sys

# The classifier and landing finders live in the add-on package; import them
# the same way the unit tests do.
_ADDON = os.path.join(
	os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
	"addon",
	"globalPlugins",
	"TextMarksTheSpot",
)
sys.path.insert(0, _ADDON)

import classifier as cls  # noqa: E402
from detection import web  # noqa: E402

# classify() intent -> the landing finder the trigger dispatches to
# (mirrors _handleResult in __init__.py). Intents with no browse-cursor
# landing (SILENT_FOCUS_HONORED, APP, VIDEO, UNKNOWN) map to None.
_LANDING_FINDERS = {
	cls.Intent.ARTICLE: web.findArticleLanding,
	cls.Intent.NOTICE: web.findNoticeLanding,
	cls.Intent.LIST: web.findListLanding,
	cls.Intent.FORM: web.findFormLanding,
	cls.Intent.KEY_RESULT: getattr(web, "findKeyResultLanding", None),
}


def _defaultCapturePath() -> str:
	appdata = os.environ.get("APPDATA", "")
	return os.path.join(appdata, "nvda", "TextMarksTheSpot-captures.jsonl")


def _nodeFromRow(row: list) -> cls.MainNode:
	# [kind, level, length, preview, isCaption, isBoilerplate, isDisclosure, endsSentence]
	kind, level, length, preview, isCap, isBoiler, isDisc, ends = row
	return cls.MainNode(
		kind=kind,
		level=level,
		textLength=length,
		textPreview=preview or "",
		isCaption=isCap,
		isBoilerplate=isBoiler,
		isDisclosure=isDisc,
		endsSentence=ends,
	)


def summaryFromRecord(rec: dict) -> cls.TreeSummary:
	return cls.TreeSummary(
		url=rec.get("url", ""),
		hasMainLandmark=rec.get("has_main", False),
		articleCount=rec.get("article", 0),
		positionallyScoped=rec.get("positionally_scoped", False),
		formInputCount=rec.get("forms", 0),
		interactiveControlCount=rec.get("interactive", 0),
		countsTruncated=rec.get("counts_trunc", False),
		articleCountTruncated=rec.get("article_count_trunc", False),
		walkTruncated=rec.get("walk_trunc", False),
		mainNodes=[_nodeFromRow(r) for r in rec.get("nodes", [])],
	)


def replay(rec: dict) -> dict:
	"""Return {url, intent, confidence, landing_idx, landing_preview}."""
	tree = summaryFromRecord(rec)
	result = cls.classify(tree)
	finder = _LANDING_FINDERS.get(result.intent)
	idx = finder(tree) if finder is not None else None
	preview = None
	if idx is not None and 0 <= idx < len(tree.mainNodes):
		preview = tree.mainNodes[idx].textPreview
	return {
		"url": rec.get("url", ""),
		"intent": result.intent.name,
		"confidence": round(result.confidence, 2),
		"landing_idx": idx,
		"landing_preview": preview,
	}


def main(argv: list) -> int:
	# Captured previews carry arbitrary page text; the Windows console default
	# (cp1252) can't encode it. Force UTF-8 and never crash on an odd glyph.
	try:
		sys.stdout.reconfigure(encoding="utf-8", errors="replace")
	except Exception:
		pass
	path = _defaultCapturePath()
	urlFilter = None
	args = list(argv)
	if "--url" in args:
		i = args.index("--url")
		urlFilter = args[i + 1] if i + 1 < len(args) else None
		del args[i : i + 2]
	if args:
		path = args[0]

	if not os.path.exists(path):
		print(f"No capture file at: {path}")
		print("Browse a few pages with the add-on (NVDA log level DEBUG) to fill it.")
		return 1

	rows = 0
	with open(path, "r", encoding="utf-8") as fh:
		for line in fh:
			line = line.strip()
			if not line:
				continue
			try:
				rec = json.loads(line)
			except json.JSONDecodeError:
				continue
			if urlFilter and urlFilter not in rec.get("url", ""):
				continue
			out = replay(rec)
			rows += 1
			idx = out["landing_idx"]
			landing = "no landing" if idx is None else f"idx={idx} :: {out['landing_preview']!r}"
			print(f"{out['intent']}({out['confidence']}) | {landing}")
			print(f"    {out['url']}")
	print(f"\n{rows} record(s) replayed.")
	return 0


if __name__ == "__main__":
	raise SystemExit(main(sys.argv[1:]))
