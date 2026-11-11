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
	addon_version="1.0.19",
	# Brief changelog for this version
	# Translators: what's new content for the add-on version to be shown in the add-on store
	addon_changelog=_("""Z gets out of the way when a web app wants it, and a tab you are not reading stays quiet.

Turning single letter navigation off now covers Z too. When you press NVDA+Shift+Space to turn single letter navigation off, so a web app's own one-key shortcuts reach the page, Z and Shift+Z kept running the add-on anyway and the page never got the key. Gmail uses Z for undo, so that one hurt. Both keys now go straight to the page while single letter navigation is off, like every other letter, and work as before when you turn it back on.
Programs that type for you keep their z's. With the add-on running, text a program typed for you, such as a password manager filling in a password, a text expander or an AutoHotkey script, could come out with its z and capital Z letters in the wrong order or missing. Z and Shift+Z now only belong to the add-on in browse mode on a web page; everywhere else they go straight to the program, the same as without the add-on.
Shift+Z works when a page starts you in a form field. If a page put your cursor in an edit box when it opened, such as a sign-in page, and you were in browse mode, Shift+Z did nothing at all and made no sound, so there was no way to tell the key had even been heard. Pressing Z twice on an excluded site had the same problem. Both now run, and you get either a landing or the two low beeps. In focus mode the keys still type into the field, as they should. One thing to know: on a form page this puts you in the first field of the form, even if you were further down.
A page reloading in another tab no longer talks over you. If a tab you had left reloaded, or something inside it finished loading, while you were reading a different tab, the add-on could play its working sound, read you that other page's paragraph, or even move your focus into one of its fields. It now leaves a page alone while you are reading somewhere else. When you go back to that tab, press Shift+Z for a landing.
The NVDA+Z question comes to the front. The question that asks whether to add a site to your exclusion list could open behind the browser, especially with a portable copy of NVDA, and then you heard nothing after pressing NVDA+Z. It now comes forward where you can answer it, and you are put back in the page afterwards.
An article stays an article whatever tracking text is on its link. A short article with a comment box could be treated as a sign-up form when the link that brought you there had something like "ref=createaccount" tacked on the end, and a sign-up form moves your keyboard focus into a field. That tacked-on part no longer counts. Wikipedia-style sign-in links are still recognized as sign-in pages, however the link spells out its colon.
The add-on's help page is easier to read. The documentation link for the add-on now opens a plain web page with the instructions and the full list of changes, without GitHub's menus and file list in front of them.
Ready for translations. Nothing changes in English, but the add-on now uses its own translations, so when someone contributes one, the spoken messages will come out in that language too, not just the add-on's name and description.

Known gaps, unchanged from 1.0.18: a video row that also carries a written description under each video can still trip the headline wall, so some search results pages land on a video. Consent banners that never say what they store, the "We value your privacy" wording, are still not caught, and that costs you one press of Down Arrow. On some articles the cursor lands on the author's biography instead of the story; recipe sites can still land on a marketing line or a reader's review; the Verge and TechCrunch home pages lead with a large featured story and land on a headline further down the list; single-field sign-in pages that ask for your email first still get no landing (the two low beeps); and script-drawn result widgets like the fast.com speed test are still not detected."""),
	# Author(s)
	addon_author="Casey Mathews <help@webfriendlyhelp.com>",
	# URL for the add-on documentation support
	addon_url="https://webfriendlyhelp.github.io/TextMarksTheSpot/",
	# URL for the add-on repository where the source code can be found
	addon_sourceURL="https://github.com/WebFriendlyHelp/TextMarksTheSpot",
	# Documentation file name
	addon_docFileName="readme.html",
	# Minimum NVDA version supported (e.g. "2019.3.0", minor version is optional)
	addon_minimumNVDAVersion="2024.1.0",
	# Last NVDA version supported/tested (e.g. "2024.4.0", ideally more recent than minimum version)
	addon_lastTestedNVDAVersion="2026.3.1",
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
