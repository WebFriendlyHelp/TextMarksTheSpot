# Build customizations
# Change this file instead of sconstruct or manifest files, whenever possible.

from site_scons.site_tools.NVDATool.typings import AddonInfo, BrailleTables, SymbolDictionaries, SpeechDictionaries

# Since some strings in `addon_info` are translatable,
# we need to include them in the .po files.
# Gettext recognizes only strings given as parameters to the `_` function.
# To avoid initializing translations in this module we simply import a "fake" `_` function
# which returns whatever is given to it as an argument.
from site_scons.site_tools.NVDATool.utils import _


# Add-on information variables
addon_info = AddonInfo(
	# add-on Name/identifier, internal for NVDA
	addon_name="TextMarksTheSpot",
	# Add-on summary/title, usually the user visible name of the add-on
	# Translators: Summary/title for this add-on
	# to be shown on installation and add-on information found in add-on store
	addon_summary=_("Text Marks the Spot"),
	# Add-on description
	# Translators: Long description to be shown for this add-on on add-on information from add-on store
	addon_description=_("""Get to the actual content on a web page without working so hard to find it. Hands off. Let the page load, listen for the short beeps, and you're at the start of the article. NVDA reads the first paragraph. Press Z to skim forward, Shift+Z to jump back to the start, NVDA+Z to turn the add-on off on a specific site. Runs locally, no network calls."""),
	# version
	addon_version="1.0.9",
	# Brief changelog for this version
	# Translators: what's new content for the add-on version to be shown in the add-on store
	addon_changelog=_("""The cursor no longer lands on copyright and legal text.

On pages that draw their content in after the page first loads, such as Zoom webinar registration pages, the only text present at first is the site's footer, and the add-on would land there and read the copyright line as if it were the page. Copyright lines and legal footer links are now recognized and never used as a landing spot; the add-on waits its usual moment and looks again once the real content has arrived. The Z key skips past copyright text too.

Registration pages that open with a real description now land on the page title so you can arrow through the description and into the form, instead of being dropped on the first field with everything above it skipped. Plain forms with no description still put you right on the first field.

One page visit, one landing: some web apps quietly rebuild their page seconds after it loads, and each rebuild used to trigger a fresh detection that yanked the cursor away from a good landing. Now, once the add-on has landed on a page, later rebuilds of that same page leave your cursor alone. Press Z any time for a fresh detection.

Going back to a page no longer yanks you to the top. When you press Back to return to search results or a list you were working through, your browser restores your place, and the add-on respects it: on a page you have already visited, if your cursor is anywhere past the top, it stays quiet. First visits still land as usual, and links that point into a specific section of a page are respected too.

Posts on X (Twitter) now land on the post text instead of the generic "Post" heading. A tweet reaches NVDA as several short lines, each too short to qualify on its own; runs of short lines that read like sentences are now recognized as real content.

News articles no longer land on "READ MORE" promo boxes or bylines (both the all-caps "By ..." style and the "Written by ..." style); these are now skipped as page furniture so the cursor reaches the story's real opening paragraph. And blog posts that carry a newsletter signup widget are no longer mistaken for form pages: two long body paragraphs in a row now count as proof the page is an article, while real registration pages are unaffected.

Paragraphs that follow images or link-heavy blocks are no longer invisible: a stepping quirk in how the add-on read through the page could silently skip the paragraph right after a picture or a logo heading, so it could never be landed on or found with Z.

Pages whose address says they're content (news, blog, podcast, article) are no longer treated as forms just because they carry a comment box, login, search, and newsletter widgets; pages whose address says form (register, signup, contact) keep the form treatment.

And when a form page hides its description inside collapsed sections, the add-on lands on the page heading at the top of the form instead of a lone question partway down.

Detection is also much faster: the slowest internal step could add a second or more of sluggishness per page load, and it has been reworked. The same rework fixes form detection on pages that previously counted as having no form fields at all.

Confirmation pages such as "You have successfully registered" now land on the confirmation message even when the page carries a control like Add to Calendar."""),
	# Author(s)
	addon_author="Casey Mathews <help@webfriendlyhelp.com>",
	# URL for the add-on documentation support
	addon_url="https://github.com/WebFriendlyHelp/TextMarksTheSpot",
	# URL for the add-on repository where the source code can be found
	addon_sourceURL="https://github.com/WebFriendlyHelp/TextMarksTheSpot",
	# Documentation file name
	addon_docFileName="readme.html",
	# Minimum NVDA version supported (e.g. "2019.3.0", minor version is optional)
	addon_minimumNVDAVersion="2024.1.0",
	# Last NVDA version supported/tested (e.g. "2024.4.0", ideally more recent than minimum version)
	addon_lastTestedNVDAVersion="2026.2.0",
	# Add-on update channel (default is None, denoting stable releases,
	# and for development releases, use "dev".)
	# Do not change unless you know what you are doing!
	addon_updateChannel=None,
	# Add-on license such as GPL 2
	addon_license="GPL v2",
	# URL for the license document the ad-on is licensed under
	addon_licenseURL="https://www.gnu.org/licenses/old-licenses/gpl-2.0.html",
)

# Define the python files that are the sources of your add-on.
# You can either list every file (using ""/") as a path separator,
# or use glob expressions.
# For example to include all files with a ".py" extension from the "globalPlugins" dir of your add-on
# the list can be written as follows:
# pythonSources = ["addon/globalPlugins/*.py"]
# For more information on SCons Glob expressions please take a look at:
# https://scons.org/doc/production/HTML/scons-user/apd.html
pythonSources: list[str] = [
	"addon/globalPlugins/TextMarksTheSpot/*.py",
	"addon/globalPlugins/TextMarksTheSpot/detection/*.py",
]

# Files that contain strings for translation. Usually your python sources
i18nSources: list[str] = pythonSources + ["buildVars.py"]

# Files that will be ignored when building the nvda-addon file
# Paths are relative to the addon directory, not to the root directory of your addon sources.
# You can either list every file (using ""/") as a path separator,
# or use glob expressions.
excludedFiles: list[str] = [
	"*/__pycache__",
	"*/__pycache__/*",
	"*.pyc",
	"*/*.pyc",
	"*/*/*.pyc",
]

# Base language for the NVDA add-on
# If your add-on is written in a language other than english, modify this variable.
# For example, set baseLanguage to "es" if your add-on is primarily written in spanish.
# You must also edit .gitignore file to specify base language files to be ignored.
baseLanguage: str = "en"

# Markdown extensions for add-on documentation
# Most add-ons do not require additional Markdown extensions.
# If you need to add support for markup such as tables, fill out the below list.
# Extensions string must be of the form "markdown.extensions.extensionName"
# e.g. "markdown.extensions.tables" to add tables.
markdownExtensions: list[str] = []

# Custom braille translation tables
# If your add-on includes custom braille tables (most will not), fill out this dictionary.
# Each key is a dictionary named according to braille table file name,
# with keys inside recording the following attributes:
# displayName (name of the table shown to users and translatable),
# contracted (contracted (True) or uncontracted (False) braille code),
# output (shown in output table list),
# input (shown in input table list).
brailleTables: BrailleTables = {}

# Custom speech symbol dictionaries
# Symbol dictionary files reside in the locale folder, e.g. `locale\en`, and are named `symbols-<name>.dic`.
# If your add-on includes custom speech symbol dictionaries (most will not), fill out this dictionary.
# Each key is the name of the dictionary,
# with keys inside recording the following attributes:
# displayName (name of the speech dictionary shown to users and translatable),
# mandatory (True when always enabled, False when not).
symbolDictionaries: SymbolDictionaries = {}

# Custom speech dictionaries (distinct from symbol dictionaries above)
# Speech dictionary files reside in the speechDicts folder and are named `name.dic`.
# If your add-on includes custom speech (pronunciation) dictionaries (most will not), fill out this dictionary.
# Each key is the name of the dictionary,
# with keys inside recording the following attributes:
# displayName (name of the speech dictionary shown to users and translatable),
# mandatory (True when always enabled, False when not).
speechDictionaries: SpeechDictionaries = {}
