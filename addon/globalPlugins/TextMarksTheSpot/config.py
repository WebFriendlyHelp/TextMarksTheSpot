# -*- coding: UTF-8 -*-
# Add-on configuration — confspec + load/save against NVDA's config system.
#
# Persists across NVDA restarts via config.conf. Currently used for the
# per-site exclusion list (NVDA+Z toggle). The other keys are reserved
# for future settings-panel work (auto-read, audio-feedback, etc.) and
# safe to leave at defaults until wired.

from __future__ import annotations

try:
	import config as nvdaConfig
	_NVDA_AVAILABLE = True
except ImportError:
	_NVDA_AVAILABLE = False


CONFIG_SECTION = "TextMarksTheSpot"

confspec = {
	"autoRead": "boolean(default=True)",
	"audioFeedback": "boolean(default=True)",
	"formDetection": "boolean(default=True)",
	"disabledSites": "string_list(default=list())",
	"disabledApps": "string_list(default=list())",
}


def load():
	"""Register confspec under our section so NVDA persists settings.
	Called once on GlobalPlugin construction. Safe to call multiple times."""
	if not _NVDA_AVAILABLE:
		return
	try:
		nvdaConfig.conf.spec[CONFIG_SECTION] = confspec
	except Exception:
		pass


def get_disabled_sites() -> list:
	"""Return the list of disabled hostnames. Empty list if unavailable."""
	if not _NVDA_AVAILABLE:
		return []
	try:
		return list(nvdaConfig.conf[CONFIG_SECTION]["disabledSites"])
	except Exception:
		return []


def is_site_disabled(hostname: str) -> bool:
	"""Check if hostname is in the disabled-sites list. Case-insensitive."""
	if not hostname:
		return False
	lower = hostname.lower()
	return any(h.lower() == lower for h in get_disabled_sites())


def add_disabled_site(hostname: str) -> bool:
	"""Add a hostname to the disabled-sites list. Returns True if added,
	False if already present or NVDA config unavailable."""
	if not _NVDA_AVAILABLE or not hostname:
		return False
	current = get_disabled_sites()
	if any(h.lower() == hostname.lower() for h in current):
		return False
	current.append(hostname)
	try:
		nvdaConfig.conf[CONFIG_SECTION]["disabledSites"] = current
		return True
	except Exception:
		return False


def remove_disabled_site(hostname: str) -> bool:
	"""Remove a hostname from the disabled-sites list. Returns True if
	removed, False if not present or NVDA config unavailable."""
	if not _NVDA_AVAILABLE or not hostname:
		return False
	current = get_disabled_sites()
	lower = hostname.lower()
	new_list = [h for h in current if h.lower() != lower]
	if len(new_list) == len(current):
		return False
	try:
		nvdaConfig.conf[CONFIG_SECTION]["disabledSites"] = new_list
		return True
	except Exception:
		return False
