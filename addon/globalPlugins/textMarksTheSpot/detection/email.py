# -*- coding: UTF-8 -*-
# Email content-start detection.
#
# Client-agnostic. The trigger fires on whatever message-body area gains focus;
# this function takes the body text and returns an offset into it.
#
# Strategy:
#   1. Strip leading email-header noise if present (From:, To:, Subject: blocks
#      that some clients render inline above the body).
#   2. Strip quoted reply chain — patterns from patterns.py:
#      - "On <date>, <name> wrote:" prelude + following >-prefixed lines
#      - "From: ... Sent: ... To: ... Subject: ..." Outlook-style blocks
#   3. Strip trailing signature — patterns from patterns.py:
#      - "-- " standard sig delimiter
#      - Valediction (best regards, thanks, sincerely) + trailing K lines
#      - Org-keyword pattern (Director, Manager, Corp., Ave., etc.)
#   4. Return offset to the first non-empty line of what remains.
#
# Phase 2 — defer until web detection ships.

# TODO: def detect_email_content_start(body_text) -> Optional[int]
