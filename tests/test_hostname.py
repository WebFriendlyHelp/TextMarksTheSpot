# Tests for the hostname helper used by the NVDA+Z site-exclusion feature.
#
# The helper is a pure-Python wrapper around urllib.parse.urlparse, so we
# can exercise it directly without NVDA. The config-persistence and
# wx-dialog parts can only be tested in real NVDA — they live as manual
# verification, like the rest of the NVDA binding layer.

from pathlib import Path

# __init__.py at the addon root isn't named as a normal module; import
# the helper function directly from its source file.
PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "addon" / "globalPlugins" / "TextMarksTheSpot"


def _loadHostnameHelper():
	"""Read _hostnameFromUrl out of __init__.py without importing the
	whole module (which would pull in NVDA-only imports)."""
	import re
	src = (PLUGIN_ROOT / "__init__.py").read_text(encoding="utf-8")
	match = re.search(
		r"def _hostnameFromUrl\(.*?\n((?:\t.*\n)+)",
		src,
	)
	assert match, "couldn't locate _hostnameFromUrl in __init__.py"
	# Reconstruct a callable from the source body.
	body = "from urllib.parse import urlparse\n\ndef _hostnameFromUrl(url):\n" + match.group(1)
	ns = {}
	exec(body, ns)
	return ns["_hostnameFromUrl"]


_hostnameFromUrl = _loadHostnameHelper()


def test_hostnameForTypicalHttpsUrl():
	assert _hostnameFromUrl("https://forums.audiogames.net/topic/123/") == "forums.audiogames.net"


def test_hostnameForWwwPrefix():
	assert _hostnameFromUrl("https://www.amazon.com/dp/B09JCKB28X?ref=foo") == "www.amazon.com"


def test_hostnameForSubdomain():
	assert _hostnameFromUrl("https://docs.google.com/forms/d/e/abc/viewform") == "docs.google.com"


def test_hostnameForNoneOrEmpty():
	assert _hostnameFromUrl(None) is None
	assert _hostnameFromUrl("") is None


def test_hostnameForUnparseableInput():
	# Garbage input doesn't crash — returns None or empty hostname.
	result = _hostnameFromUrl("not a url at all")
	# urllib.parse is permissive — empty/None hostname is acceptable.
	assert result is None or result == ""
