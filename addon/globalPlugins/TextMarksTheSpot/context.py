# -*- coding: UTF-8 -*-
# Detect the surrounding context: am I in a browser, a webmail UI, or a
# native email client? This decides which detector to dispatch to.
#
# Browser detection: check the focused application module name
# (firefox, chrome, msedge, brave, opera, etc.)
#
# Webmail detection: browser + URL pattern (mail.google.com, outlook.live.com,
# outlook.office.com, etc.). Triggers email.py instead of web.py for the
# message-body area.
#
# Native email client: thunderbird, outlook desktop. Triggers email.py.
#
# Disabled site/app check: consult config.disabled_sites and config.disabled_apps
# and short-circuit to None ("do nothing") if matched.

# TODO: def detect_context(focus) -> Literal["web", "webmail", "email", "disabled"]
