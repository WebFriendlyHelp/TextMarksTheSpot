#!/usr/bin/env python3
"""Build a .nvda-addon for any TMTS probe folder.

Usage: python probes/build_probe.py <probe_name>

The .nvda-addon is just a zip with manifest.ini and addon/ at the root.
Using Python's zipfile module instead of PowerShell's Compress-Archive
because the latter sometimes produces zips NVDA's parser rejects when the
source paths contain spaces — and our project lives under "Text Marks the
Spot" which has spaces.
"""

from __future__ import annotations

import os
import sys
import re
import zipfile
from pathlib import Path


def main(probe_name: str) -> int:
	script_dir = Path(__file__).resolve().parent
	probe_dir = script_dir / probe_name
	if not probe_dir.is_dir():
		print(f"ERROR: probe folder not found: {probe_dir}", file=sys.stderr)
		return 1

	manifest = probe_dir / "manifest.ini"
	addon_dir = probe_dir / "addon"
	if not manifest.is_file():
		print(f"ERROR: missing manifest.ini in {probe_dir}", file=sys.stderr)
		return 1
	if not addon_dir.is_dir():
		print(f"ERROR: missing addon/ folder in {probe_dir}", file=sys.stderr)
		return 1

	manifest_text = manifest.read_text(encoding="utf-8")
	name_m = re.search(r"^\s*name\s*=\s*(.+?)\s*$", manifest_text, re.MULTILINE)
	ver_m = re.search(r"^\s*version\s*=\s*(.+?)\s*$", manifest_text, re.MULTILINE)
	if not name_m or not ver_m:
		print("ERROR: manifest.ini missing 'name' or 'version'", file=sys.stderr)
		return 1
	addon_name = name_m.group(1).strip()
	addon_ver = ver_m.group(1).strip()

	out_path = probe_dir / f"{addon_name}-{addon_ver}.nvda-addon"
	if out_path.exists():
		out_path.unlink()

	with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
		# manifest.ini at root.
		zf.write(manifest, arcname="manifest.ini")
		# Contents of addon/ at root — strip the addon/ prefix. NVDA expects
		# globalPlugins/ etc. directly under the addon root after extraction,
		# NOT under an addon/ subfolder. The source-tree addon/ convention is
		# just for organization; build tools (SCons, ours) unwrap it.
		for root, _dirs, files in os.walk(addon_dir):
			for f in files:
				abs_path = Path(root) / f
				rel = abs_path.relative_to(addon_dir).as_posix()
				zf.write(abs_path, arcname=rel)

	print(f"Built: {out_path}")
	return 0


if __name__ == "__main__":
	if len(sys.argv) != 2:
		print("Usage: python probes/build_probe.py <probe_name>", file=sys.stderr)
		sys.exit(2)
	sys.exit(main(sys.argv[1]))
