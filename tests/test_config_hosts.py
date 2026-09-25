"""Site-exclusion matching compares canonical hostnames. Added 2026-09-24.

A trailing dot is the same DNS name, and a Unicode domain is the same site as
its xn-- punycode spelling; before this, each was a different entry.
"""

import config as cfg


def _withList(monkeypatch, entries):
	monkeypatch.setattr(cfg, "getDisabledSites", lambda: list(entries))


def test_trailingDotIsTheSameSite(monkeypatch):
	_withList(monkeypatch, ["example.com"])
	assert cfg.isSiteDisabled("example.com.")
	_withList(monkeypatch, ["example.com."])
	assert cfg.isSiteDisabled("example.com")


def test_unicodeAndPunycodeAreTheSameSite(monkeypatch):
	_withList(monkeypatch, ["bücher.example"])
	assert cfg.isSiteDisabled("xn--bcher-kva.example")
	_withList(monkeypatch, ["xn--bcher-kva.example"])
	assert cfg.isSiteDisabled("BÜCHER.example")


def test_differentSitesStayDifferent(monkeypatch):
	# Negative twin: canonical comparison must not merge real neighbours.
	_withList(monkeypatch, ["example.com"])
	assert not cfg.isSiteDisabled("example.co")
	assert not cfg.isSiteDisabled("sub.example.com")
	assert not cfg.isSiteDisabled("")


def test_aNameIdnaRejectsStillComparesAsBefore(monkeypatch):
	odd = "a" * 70 + ".example"  # a label over 63 chars fails IDNA encoding
	_withList(monkeypatch, [odd.upper()])
	assert cfg.isSiteDisabled(odd)
