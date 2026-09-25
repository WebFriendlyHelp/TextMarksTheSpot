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
	addon_version="1.0.17",
	# Brief changelog for this version
	# Translators: what's new content for the add-on version to be shown in the add-on store
	addon_changelog=_("""A web page can no longer freeze NVDA, and Z keeps working all the way down a long page.

NVDA no longer goes silent on certain pages. A paragraph padded with tens of thousands of blank spaces, or a long run of repeated brackets, could lock NVDA up for several seconds while the add-on looked at it, and during that time NVDA said nothing at all. On a test page it froze for nearly five seconds and then landed on the padding. It now reads the same page in a fraction of a second and lands on the real story.
Z works to the bottom of long pages. The add-on only has a couple of seconds to read a page, and it always started reading from the top. On a very long page, like a Bible Gateway chapter or a big discussion thread, once you had read past the point it could reach in that time, Z said "Nothing else to land on" with plenty of page left. When that happens now, it reads again starting from where you are.
Shift+Z checks before it moves you. Some pages rebuild themselves after the add-on lands. Shift+Z could then return you to the old position after a different paragraph had moved into it, and read you that paragraph instead. It now makes sure the paragraph is still the one it saved, finds it again by its wording if the page moved it, and works out a fresh landing if it is gone. With the same page open in two tabs, Shift+Z in the second tab no longer uses the first tab's saved spot.
The page you left stays quiet when you switch tabs. If you switched to another tab while a page was still loading, that first page could finish, speak its landing, or move your focus into one of its fields while you were reading the other tab. It now notices you have moved on and stays quiet.
No automatic landing inside email messages. In a mail program that shows messages as web pages, such as Thunderbird, a message could in some cases get an automatic landing, even though email is not supported yet. It now leaves messages alone. Pressing Z twice or Shift+Z still works there if you ask for it.
An article stays an article whatever link brought you there. Some links carry a "send me back here after signing in" address, and a sign-in address in that part of the link could make an ordinary article with a comment box count as a sign-in form, which moves your keyboard focus into a field. That part of the link no longer counts.
Big forms can't hold up NVDA while the add-on finds the first field. Finding the first field now stops after a set limit instead of checking every field on the page, so a page with hundreds of fields outside the form can't stall NVDA.
The exclusion list is more dependable. NVDA+Z now tells you if the list could not be saved, instead of saying the site was added. And a site written with a dot on the end, or an international domain name written either way, now counts as the same site.
The diagnostic log never writes on secure screens. Even with the log switched on, nothing is written on the Windows sign-in or lock screen. A portable copy of NVDA now looks for the switch-on file in its own configuration folder, as the documentation always said.

Known gaps, unchanged from 1.0.16: a video row that also carries a written description under each video can still trip the headline wall, so some search results pages land on a video. Consent banners that never say what they store, the "We value your privacy" wording, are still not caught, and that costs you one press of Down Arrow. On some articles the cursor lands on the author's biography instead of the story; recipe sites can still land on a marketing line or a reader's review; the Verge and TechCrunch home pages lead with a large featured story and land on a headline further down the list; single-field sign-in pages that ask for your email first still get no landing (the two low beeps); and script-drawn result widgets like the fast.com speed test are still not detected."""),
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
