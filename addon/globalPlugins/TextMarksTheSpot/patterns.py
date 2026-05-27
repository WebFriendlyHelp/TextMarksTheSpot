# -*- coding: UTF-8 -*-
# Compiled regex patterns and blacklists used by the detectors.
# All patterns are compiled once at module load for speed.

import re

# Class / id substrings that mark a node as "unlikely" main content.
# Used by scoring.py to penalize candidates.
UNLIKELY_CLASS_ID_SUBSTRINGS = (
	"sidebar", "side-bar",
	"comment", "comments",
	"nav", "navigation", "menu",
	"header", "footer",
	"ad", "ads", "advert",
	"social", "share", "sharing",
	"cookie", "consent", "banner",
	"popup", "modal", "overlay",
	"related", "recommendation",
	"breadcrumb",
	"newsletter", "subscribe",
	"promo", "sponsor",
)

# Class / id substrings that POSITIVELY indicate main content.
POSITIVE_CLASS_ID_SUBSTRINGS = (
	"article", "post", "content", "entry", "main", "body", "story", "text",
)

# Quoted reply detection — Phase 2 (email detection).
QUOTED_REPLY_PATTERNS = (
	re.compile(r"^On .+?, .+? wrote:\s*$", re.MULTILINE),
	re.compile(r"^On .+? at .+?, .+? wrote:\s*$", re.MULTILINE),
	re.compile(r"^-{3,}\s*Original Message\s*-{3,}\s*$", re.MULTILINE | re.IGNORECASE),
	re.compile(r"^From:\s.+\nSent:\s.+\nTo:\s.+\nSubject:\s.+", re.MULTILINE),
)

# Signature valediction patterns — Phase 2.
VALEDICTION_PATTERN = re.compile(
	r"^\s*(best regards|kind regards|regards|sincerely|thanks|thank you|cheers|"
	r"best|warmly|yours truly|respectfully)\s*[,!\.]?\s*$",
	re.MULTILINE | re.IGNORECASE,
)

# Standard signature delimiter.
SIG_DELIMITER_PATTERN = re.compile(r"^-- \s*$", re.MULTILINE)

# Org-keyword pattern for signature heuristic — Phase 2.
ORG_KEYWORD_PATTERN = re.compile(
	r"\b(Dept\.|University|Corp\.|Corporation|College|Ave\.|Street|St\.|"
	r"Avenue|Director|Manager|Professor|Laboratory|Laboratories|Institute|"
	r"Division|Engineering|Sciences?|Services?)\b"
)

# URL/title signals that boost form-primary detection.
FORM_INTENT_URL_PATTERNS = (
	re.compile(r"/(register|signup|sign-up|apply|intake|contact|subscribe)(/|$|\?)", re.IGNORECASE),
)
