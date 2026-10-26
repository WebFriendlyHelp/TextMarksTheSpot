"""Build the small GitHub Pages site: readme.md as index.html and changelog.md
as changelog.html, so users get a plain page with nothing else on it instead
of GitHub's menus and file list (Casey, 2026-10-22; layout shared with
KeyQuest and Voyager Access).

Uses Python-Markdown, already a build dependency (SCons renders the store
readme with it), rather than a hand-written parser: the changelog bolds the
lead of every bullet.

Usage: python tools/build_pages_site.py   (writes site/)
"""

import html
import re
from pathlib import Path

import markdown

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "site"
NAME = "Text Marks the Spot"
GITHUB = "https://github.com/WebFriendlyHelp/TextMarksTheSpot/blob/main/"
# Links in the Markdown that point at other files in the repository.
LOCAL_LINKS = {"changelog.md": "changelog.html", "readme.md": "index.html"}


def _rewriteLink(match):
	target = html.unescape(match.group(1))
	if target.lower() in LOCAL_LINKS:
		target = LOCAL_LINKS[target.lower()]
	elif not (re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#")):
		target = GITHUB + target
	return f'href="{html.escape(target)}"'


def markdownToHtml(text):
	body = markdown.markdown(text, extensions=["extra", "sane_lists"])
	return re.sub(r'href="([^"]*)"', _rewriteLink, body)


STYLE = """
	body { font-family: Arial, sans-serif; font-size: 18px; line-height: 1.6;
		color: #111; background: #fff; margin: 0; }
	.block { max-width: 75ch; margin: 0 auto; padding: 0 16px; }
	main { padding: 16px 0; }
	a { color: #0b57d0; }
	a:focus-visible { outline: 3px solid #111; outline-offset: 2px; }
	.skip { position: absolute; left: 8px; top: -100px; background: #fff; color: #111;
		border: 2px solid #111; padding: 8px 10px; }
	.skip:focus { top: 8px; }
	h1, h2, h3 { line-height: 1.3; }
	code, pre { font-family: Consolas, "Courier New", monospace; }
	pre { overflow-x: auto; }
	@media (prefers-color-scheme: dark) {
		body { color: #eee; background: #121212; }
		a { color: #8ab4f8; }
		a:focus-visible { outline-color: #eee; }
		.skip { background: #121212; color: #eee; border-color: #eee; }
	}
"""


def page(title, body, nav):
	return f"""<!doctype html>
<html lang="en">
<head>
	<meta charset="utf-8">
	<meta name="viewport" content="width=device-width, initial-scale=1">
	<title>{html.escape(title)}</title>
	<style>{STYLE}</style>
</head>
<body>
	<a class="skip" href="#main">Skip to main content</a>
	<header><div class="block"><p>{nav}</p></div></header>
	<main id="main"><div class="block">
{body}
	</div></main>
</body>
</html>
"""


def main():
	OUT.mkdir(exist_ok=True)
	(OUT / ".nojekyll").write_text("", encoding="utf-8")
	readme = markdownToHtml((REPO / "readme.md").read_text(encoding="utf-8"))
	news = (REPO / "changelog.md").read_text(encoding="utf-8")
	# The file's own title is "Changelog"; the page says what a user is looking at.
	news = re.sub(r"\A# Changelog\s*$", f"# New in {NAME}", news, count=1, flags=re.M)
	(OUT / "index.html").write_text(
		page(NAME, readme, f'<a href="changelog.html">New in {NAME}</a>'), encoding="utf-8"
	)
	(OUT / "changelog.html").write_text(
		page(
			f"New in {NAME}",
			markdownToHtml(news),
			f'<a href="index.html">Back to the {NAME} instructions</a>',
		),
		encoding="utf-8",
	)


if __name__ == "__main__":
	main()
