# -*- coding: UTF-8 -*-
# Per-page-type Z sequence state machine.
#
# See SPEC.md decision #7 for the full sequence definitions and guardrails.
#
# Each Z press advances the sequence for the current document. The sequence
# depends on the page type returned by context.py:
#
#   article      → next major section, comments, end
#   form         → first error, next empty required field, submit, terms
#   email        → first important sentence, first link, quote, signature
#   search       → next result, next result, ...
#   app          → primary CTA
#   unknown      → fall back to "re-trigger detection" (Phase 1 behavior)
#
# State resets on document change (URL change, new email opened, navigation).
#
# Honors guardrails (SPEC.md "Guardrails"):
#   - Never supplants NVDA's built-in quick-nav keys
#   - On unknown page type, returns no-sequence-result (caller falls back)
#   - Each step yields (position, announcement) for ui.message after the jump
#   - At end of sequence: returns ("end", "No more next-likely actions on this page")

# TODO: from . import context, config
# TODO: import ui

# ---------------------------------------------------------------------------
# Sequence definitions — stubs. Each entry is a list of step descriptors that
# the implementation walks. A descriptor is (finder_fn_name, announcement_key).
# The actual finder functions live in the detectors (web.py, email.py, form.py)
# and are looked up by name to keep this module dependency-light.

SEQUENCES = {
	"article": [
		# ("find_next_major_section", "section"),
		# ("find_next_major_section", "section"),
		# ("find_comments_section", "comments"),
	],
	"form": [
		# ("find_first_error", "first_error"),
		# ("find_next_empty_required_field", "next_empty"),
		# ("find_submit_button", "submit"),
		# ("find_terms_link", "terms"),
	],
	"email": [
		# ("find_first_important_sentence", "important"),
		# ("find_first_link", "first_link"),
		# ("find_quote_chain_start", "quote"),
		# ("find_signature", "signature"),
	],
	"search": [
		# ("find_next_result", "next_result"),  # repeats until end
	],
	"app": [
		# ("find_primary_cta", "primary_cta"),
	],
	# "unknown" — no sequence, caller falls back to re-trigger
}


# ---------------------------------------------------------------------------
# Per-document state. Keyed by document identity (URL for web, messageId for
# email). Stores the current step index. Cleared on document change.

_state = {}  # doc_id -> step_index


# ---------------------------------------------------------------------------
# Public API

def advance(doc_id, page_type, treeInterceptor):
	"""
	Advance the Z sequence one step for this document.

	Returns one of:
	  - (position, announcement_text)  on a successful step
	  - ("end", "No more next-likely actions on this page")  at sequence end
	  - None  if page_type is unknown — caller should fall back to re-trigger
	"""
	# TODO: look up SEQUENCES[page_type]
	# TODO: get/init step_index from _state
	# TODO: if step_index >= len(steps): return ("end", ...)
	# TODO: dispatch to the finder, return (position, _announcement_for(key))
	# TODO: increment step_index and store back
	pass


def reset(doc_id):
	"""Clear sequence state for a document — call on document change."""
	_state.pop(doc_id, None)


def clear_all():
	"""Clear all sequence state — call on add-on terminate."""
	_state.clear()


# ---------------------------------------------------------------------------
# Announcement strings — translatable.
# Keys match the second element of the sequence step descriptors above.

def _announcement_for(key):
	# TODO: return the right translatable string per key.
	# Examples (each wrapped in _() with a Translators: comment):
	#   "section"     → "Jumped to next section"
	#   "comments"    → "Jumped to comments"
	#   "first_error" → "Jumped to first error: {message}"
	#   "next_empty"  → "Jumped to next empty field: {label}"
	#   "submit"      → "Jumped to submit button"
	#   "terms"       → "Jumped to terms and privacy link"
	#   "important"   → "Jumped to first important sentence"
	#   "first_link"  → "Jumped to first link"
	#   "quote"       → "Jumped to quoted reply"
	#   "signature"   → "Jumped to signature"
	#   "next_result" → "Jumped to next result"
	#   "primary_cta" → "Jumped to primary action"
	pass
