# -*- coding: UTF-8 -*-
# Article landing strategy.
#
# Per SPEC.md locked decision #7: when the classifier returns ARTICLE,
# the cursor should land on the first substantial body paragraph — past
# the headline, dek, byline, date, and (when we add chrome filtering)
# figure captions and social-share blocks.
#
# This module is pure logic on a TreeSummary. No NVDA imports. Returns an
# index into tree.main_nodes; the NVDA-binding caller maps that index back
# to a real textInfo position when walking the document the same way
# tree_summary did.

from __future__ import annotations

from typing import Optional

try:
	from ..classifier import TreeSummary
except ImportError:
	from classifier import TreeSummary


# Same bar the classifier uses for "substantial paragraph". Defined here too
# so this module doesn't reach into classifier internals — and so we can
# tune it independently later if landing turns out to need a different bar
# than classification.
LANDING_MIN_PARAGRAPH_CHARS = 100


def find_article_landing(tree: TreeSummary) -> Optional[int]:
	"""Walk main_nodes in document order; return the index of the first
	substantial paragraph (>= LANDING_MIN_PARAGRAPH_CHARS chars). Returns
	None if no suitable target — caller should stay silent (guardrail #3).

	"Substantial" matches the classifier's bar so the article-mode strategy
	can't pick a target the classifier wouldn't have counted as content. If
	the user's intended target is a shorter tagline directly under H1, this
	will skip it and land on the next substantial paragraph (see SPEC and
	the l-works.net fixture for the rationale).

	Future refinement (when TreeSummary carries parent-role info):
	  - skip nodes inside <figure> / <figcaption>
	  - skip nodes with byline/date/share class hints
	  - skip nodes inside <aside> / role=complementary

	Currently those skips are not implemented because MainNode doesn't carry
	the parent-role data. The first-substantial-paragraph rule is the MVP.
	"""
	for i, node in enumerate(tree.main_nodes):
		if node.kind == "paragraph" and node.text_length >= LANDING_MIN_PARAGRAPH_CHARS:
			return i
	return None
