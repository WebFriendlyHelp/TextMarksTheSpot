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


def getDisabledSites() -> list:
	"""Return the list of disabled hostnames. Empty list if unavailable."""
	if not _NVDA_AVAILABLE:
		return []
	try:
		return list(nvdaConfig.conf[CONFIG_SECTION]["disabledSites"])
	except Exception:
		return []


def isSiteDisabled(hostname: str) -> bool:
	"""Check if hostname is in the disabled-sites list. Case-insensitive."""
	if not hostname:
		return False
	lower = hostname.lower()
	return any(h.lower() == lower for h in getDisabledSites())


def addDisabledSite(hostname: str) -> bool:
	"""Add a hostname to the disabled-sites list. Returns True if added,
	False if already present or NVDA config unavailable."""
	if not _NVDA_AVAILABLE or not hostname:
		return False
	current = getDisabledSites()
	if any(h.lower() == hostname.lower() for h in current):
		return False
	current.append(hostname)
	try:
		nvdaConfig.conf[CONFIG_SECTION]["disabledSites"] = current
		return True
	except Exception:
		return False


def removeDisabledSite(hostname: str) -> bool:
	"""Remove a hostname from the disabled-sites list. Returns True if
	removed, False if not present or NVDA config unavailable."""
	if not _NVDA_AVAILABLE or not hostname:
		return False
	current = getDisabledSites()
	lower = hostname.lower()
	newList = [h for h in current if h.lower() != lower]
	if len(newList) == len(current):
		return False
	try:
		nvdaConfig.conf[CONFIG_SECTION]["disabledSites"] = newList
		return True
	except Exception:
		return False
