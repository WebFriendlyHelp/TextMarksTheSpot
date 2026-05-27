# Tests for the hostname helper used by the NVDA+Z site-exclusion feature.
#
# The helper is a pure-Python wrapper around urllib.parse.urlparse, so we
# can exercise it directly without NVDA. The config-persistence and
# wx-dialog parts can only be tested in real NVDA — they live as manual
# verification, like the rest of the NVDA binding layer.

import sys
from pathlib import Path

# __init__.py at the addon root isn't named as a normal module; import
# the helper function directly from its source file.
PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "addon" / "globalPlugins" / "TextMarksTheSpot"


def _load_hostname_helper():
	"""Read _hostname_from_url out of __init__.py without importing the
	whole module (which would pull in NVDA-only imports)."""
	import re
	src = (PLUGIN_ROOT / "__init__.py").read_text(encoding="utf-8")
	match = re.search(
		r"def _hostname_from_url\(.*?\n((?:\t.*\n)+)",
		src,
	)
	assert match, "couldn't locate _hostname_from_url in __init__.py"
	# Reconstruct a callable from the source body.
	body = "from urllib.parse import urlparse\n\ndef _hostname_from_url(url):\n" + match.group(1)
	ns = {}
	exec(body, ns)
	return ns["_hostname_from_url"]


_hostname_from_url = _load_hostname_helper()


def test_hostname_for_typical_https_url():
	assert _hostname_from_url("https://forums.audiogames.net/topic/123/") == "forums.audiogames.net"


def test_hostname_for_www_prefix():
	assert _hostname_from_url("https://www.amazon.com/dp/B09JCKB28X?ref=foo") == "www.amazon.com"


def test_hostname_for_subdomain():
	assert _hostname_from_url("https://docs.google.com/forms/d/e/abc/viewform") == "docs.google.com"


def test_hostname_for_none_or_empty():
	assert _hostname_from_url(None) is None
	assert _hostname_from_url("") is None


def test_hostname_for_unparseable_input():
	# Garbage input doesn't crash — returns None or empty hostname.
	result = _hostname_from_url("not a url at all")
	# urllib.parse is permissive — empty/None hostname is acceptable.
	assert result is None or result == ""
