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
	addon_version="1.0.15",
	# Brief changelog for this version
	# Translators: what's new content for the add-on version to be shown in the add-on store
	addon_changelog=_("""The add-on no longer keeps any record of the pages you visit.

Nothing about your browsing is written down unless you ask for it. The add-on kept a diagnostic log with a line for every page it looked at, carrying the full web address, query string and all. Two of those files were put behind a switch in the last release. The copy that went into NVDA's own log was not, and it showed up for anyone who had turned their NVDA logging level up, which people do for all sorts of unrelated reasons. All three are now silent unless you deliberately create a file named TextMarksTheSpot-diagnostics-enabled in your NVDA user configuration folder. Create nothing and the add-on records nothing about where you have been, anywhere. If you want to clear out what is already there, the files are TextMarksTheSpot-perf.log and TextMarksTheSpot-captures.jsonl in that same folder, and deleting them is safe.

Fewer pages that go quiet after finding the right paragraph. Some pages rebuild themselves while the add-on is still reading them, which moves the paragraph it had settled on. It handles that by searching for the paragraph again by its wording, and that search was fussier than the check that approves the result, so it was throwing away landings it would have been happy with. It now tries progressively shorter pieces of the wording, and copes with the invisible spacing characters some sites put between words. A piece is only used when it appears exactly once on the page, so a teaser box that repeats the story's opening line cannot capture the landing.

Magazine-style posts land on the story instead of the summary line. A layout that runs headline, then a one-line summary, then the author and date and "6 min read", then the article, used to land you on the summary line. The tell is where the author block sits: a summary comes above it, the story below. The add-on now reads past the summary to the first real paragraph. Stories that open with one short sentence and no author block, like MacRumors, still land on that sentence.

Tested with NVDA 2026.2. Nothing needed changing for it. The add-on still runs on NVDA 2024.1 and newer, on both the 32-bit builds up to 2025.3 and the 64-bit builds from 2026.1 on.

Known gaps, unchanged from 1.0.14: on some articles the cursor lands on the author's biography instead of the story; recipe sites can still land on a marketing line or a reader's review; the Verge and TechCrunch home pages lead with a large featured story and land on a headline further down the list; single-field sign-in pages that ask for your email first still get no landing (the two low beeps); and script-drawn result widgets like the fast.com speed test are still not detected."""),
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
