# -*- coding: UTF-8 -*-
# Form-primary-goal detection.
#
# Only fires when web.py finds NO strong article candidate AND the page has
# a form occupying the main content area. Optional URL/title boost signals.
#
# Triggers:
#   - URL/title contains /register, /signup, /apply, /intake, /contact,
#     /sign-up, /subscribe (registration intent)
#   - Page form has >= N visible fields and they dominate the content area
#
# DOES NOT fire on:
#   - Newsletter signup widgets embedded in an article
#   - Search bars
#   - Comment forms below an article
#
# Returns the position of the first form field, or None.

# TODO: def detect_form_primary(treeInterceptor) -> Optional[Position]
