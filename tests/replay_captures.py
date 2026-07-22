#!/usr/bin/env python3
"""Replay captured page snapshots through the classifier + landing finders.

The add-on writes one JSON record per detection to
`%APPDATA%\\nvda\\TextMarksTheSpot-captures.jsonl` (see `_append_capture` in
tree_summary.py). Each record carries the FULL node list with every field the
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
    "addon", "globalPlugins", "TextMarksTheSpot",
)
sys.path.insert(0, _ADDON)

import classifier as cls  # noqa: E402
from detection import web  # noqa: E402

# classify() intent -> the landing finder the trigger dispatches to
# (mirrors _handle_result in __init__.py). Intents with no browse-cursor
# landing (SILENT_FOCUS_HONORED, APP, VIDEO, UNKNOWN) map to None.
_LANDING_FINDERS = {
    cls.Intent.ARTICLE: web.find_article_landing,
    cls.Intent.NOTICE: web.find_notice_landing,
    cls.Intent.LIST: web.find_list_landing,
    cls.Intent.FORM: web.find_form_landing,
    cls.Intent.KEY_RESULT: getattr(web, "find_key_result_landing", None),
}


def _default_capture_path() -> str:
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "nvda", "TextMarksTheSpot-captures.jsonl")


def _node_from_row(row: list) -> cls.MainNode:
    # [kind, level, length, preview, is_caption, is_boilerplate, is_disclosure, ends_sentence]
    kind, level, length, preview, is_cap, is_boiler, is_disc, ends = row
    return cls.MainNode(
        kind=kind, level=level, text_length=length, text_preview=preview or "",
        is_caption=is_cap, is_boilerplate=is_boiler, is_disclosure=is_disc,
        ends_sentence=ends,
    )


def summary_from_record(rec: dict) -> cls.TreeSummary:
    return cls.TreeSummary(
        url=rec.get("url", ""),
        has_main_landmark=rec.get("has_main", False),
        article_count=rec.get("article", 0),
        positionally_scoped=rec.get("positionally_scoped", False),
        form_input_count=rec.get("forms", 0),
        interactive_control_count=rec.get("interactive", 0),
        counts_truncated=rec.get("counts_trunc", False),
        main_nodes=[_node_from_row(r) for r in rec.get("nodes", [])],
    )


def replay(rec: dict) -> dict:
    """Return {url, intent, confidence, landing_idx, landing_preview}."""
    tree = summary_from_record(rec)
    result = cls.classify(tree)
    finder = _LANDING_FINDERS.get(result.intent)
    idx = finder(tree) if finder is not None else None
    preview = None
    if idx is not None and 0 <= idx < len(tree.main_nodes):
        preview = tree.main_nodes[idx].text_preview
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
    path = _default_capture_path()
    url_filter = None
    args = list(argv)
    if "--url" in args:
        i = args.index("--url")
        url_filter = args[i + 1] if i + 1 < len(args) else None
        del args[i:i + 2]
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
            if url_filter and url_filter not in rec.get("url", ""):
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
