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
	addon_version="1.0.11",
	# Brief changelog for this version
	# Translators: what's new content for the add-on version to be shown in the add-on store
	addon_changelog=_("""Stuck pages can no longer freeze NVDA.

A page that hangs while loading no longer locks NVDA up. One news site froze NVDA for over ten seconds while the add-on tried to size the page up. Every step of that inspection now runs on a strict clock, so even a completely stuck page costs about a second, and the same page lands correctly once it finishes loading. Normal pages are unaffected.

Busy, link-heavy pages come up faster. Counting the controls on a Stack Overflow topic listing took two extra seconds before the cursor moved. The count now stops as soon as it has learned enough, and the same landing arrives about a second and a half sooner.

When the clock does cut an inspection short, the add-on stops guessing. A half-inspected page can look smaller and simpler than it really is. Before, that could make a busy page read as a small notice page, or in the worst case treat an article as a form and move your keyboard focus into a field. Now, when the add-on could not finish looking, it declines those judgment calls, stays quiet, and takes its usual second look a moment later.

Known gaps, unchanged from 1.0.10: recipe sites can still land on a marketing line or a reader's review, and pages that draw a single result widget by script, like the fast.com speed test, are not detected at all. The two low beeps there are the add-on saying it found nothing, not an error."""),
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
