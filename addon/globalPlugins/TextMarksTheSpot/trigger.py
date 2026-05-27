# -*- coding: UTF-8 -*-
# Auto-trigger plumbing.
#
# Hooks into NVDA's tree interceptor focus event so detection runs without
# the user pressing anything. Debounces so we don't re-detect on every minor
# focus change inside the same document. Caches the detected position per
# document so revisiting doesn't re-detect.
#
# Public API:
#   install()     — wire up event_treeInterceptor_gainFocus override
#   uninstall()   — remove hooks on add-on terminate
#   run(force=False) — manually trigger detection (called by Z hotkey)
#
# Internals:
#   - _seen_documents: dict[doc_id -> detected_position] for cache
#   - _debounce_ms: minimum gap between detections on the same document
#   - _last_run_at: timestamp of most recent detection

# TODO: install / uninstall using NVDA's extensionPoints or method override
# TODO: doc identity = (URL, lastModified) for web; (messageId) for email
