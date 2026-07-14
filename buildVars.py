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
	addon_version="1.0.10",
	# Brief changelog for this version
	# Translators: what's new content for the add-on version to be shown in the add-on store
	addon_changelog=_("""The add-on was quietly ignoring most page loads. It isn't anymore.

The add-on now actually runs when you open a page. It was skipping roughly two out of every three page loads and doing nothing at all: no tone, no landing, no sign it had tried. This is why pages so often needed a refresh, or a press of Z, before anything happened. The cause was a wrong assumption about how NVDA tracks documents. The add-on decided "this is the same page as last time" by looking at an internal NVDA object, but NVDA reuses that object across navigations and simply changes the page address underneath it. The address is now what tells one page from another. Firefox, Chrome and Edge were all affected.

The add-on no longer reads out a different paragraph than the one it moved you to. On pages that are still loading themselves in, the page could shift under the add-on between choosing a paragraph and reading it, so it would move your cursor to the right place and then read something else entirely: a sports headline on a health story, a photo credit, or a "we're loading your content" placeholder. It now checks the paragraph is still there before speaking, and finds it again by its text if the page has moved.

Long pages no longer freeze NVDA. A long Bible chapter or a big newsletter could lock NVDA up for five to twelve seconds. Reading now stops at a time limit and lands with what it has, which on every page tested was the same paragraph it would have chosen anyway.

Movie pages and news home pages no longer steal your keyboard focus. Film pages on IMDb and TV station front pages were being treated as forms, so the add-on announced the title and then dropped your cursor into the site's search box. They are now recognized as content, and an IMDb page lands on the plot summary.

Sign-in and account-creation pages are treated as forms again, so you land in the first field instead of on the help text beside it.

The cursor skips more of the text that is not the story. Affiliate and referral disclosures, syndication notes such as "republished with permission from our news partner", marketing-consent blurbs such as "by signing up, you agree to receive text messages", photo credits, ad banners, and other stories' headlines all sat exactly where a story begins and were being read as if they were the article. They are now recognized and passed over.

Landings prefer real prose. A landing spot should read like a sentence, so headlines, credits and labels that merely look substantial no longer win. Sites that are nothing but headlines, such as link aggregators, still land on the first item.

Known gaps in this release: recipe sites can still land on a site's own marketing line or a newsletter promo, and a recipe page can land on a reader's review instead of the recipe. Both are one Down arrow away from the content."""),
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
