# -*- coding: UTF-8 -*-
# Hand-coded TreeSummary fixtures for the pages we've probed.
#
# Each fixture captures roughly what NVDA's accessibility tree would expose
# when walking <main> in document order: landmark presence, article count,
# the interleaved sequence of headings and paragraphs, and control counts.
# Numbers are best-effort observations from rendered pages — close enough in
# shape to exercise the classifier.
#
# Each fixture also carries an `expectedIntent` for the test harness to
# check against. When the classifier disagrees, that's signal — either the
# fixture is wrong or the classifier is.

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "TextMarksTheSpot"))

from classifier import TreeSummary, MainNode, Intent


# Tiny helpers so fixtures stay readable.
def H(level: int, preview: str = "") -> MainNode:
	return MainNode(kind="heading", level=level, textLength=len(preview), textPreview=preview)

def P(chars: int, preview: str = "") -> MainNode:
	return MainNode(kind="paragraph", textLength=chars, textPreview=preview)


# ---------------------------------------------------------------------------
# Articles
# ---------------------------------------------------------------------------

WIKIPEDIA_MEMORIAL_DAY = (
	"Wikipedia: Memorial Day (article)",
	Intent.ARTICLE,
	TreeSummary(
		url="https://en.wikipedia.org/wiki/Memorial_Day",
		hasMainLandmark=True,
		articleCount=0,  # Wikipedia uses <main>/<div role="main">, not <article>
		mainNodes=[
			H(1, "Memorial Day"),
			# Lead section — 4 substantial paragraphs before first H2.
			P(280), P(420), P(510), P(380),
			H(2, "History"),
			H(3, "Early observances"),
			P(320), P(290), P(450), P(510),
			H(3, "Civil War era"),
			P(480), P(350), P(410), P(530), P(460),
			H(3, "20th century"),
			P(390), P(280), P(510),
			H(2, "Observances"),
			P(420), P(310), P(280),
			H(2, "Traditions"),
			P(390), P(440),
			H(2, "Controversy"),
			P(310), P(280),
			H(2, "See also"),
			H(2, "References"),
		],
		formInputCount=1,
		interactiveControlCount=120,
		focusedControlIsEditable=False,
	),
)

MAKEUSEOF_ARTICLE = (
	"MakeUseOf: writing-habits article",
	Intent.ARTICLE,
	TreeSummary(
		url="https://www.makeuseof.com/writing-habits-that-make-you-sound-like-chatgpt/",
		hasMainLandmark=True,
		articleCount=1,
		mainNodes=[
			H(1, "5 writing habits that make you sound like ChatGPT"),
			# Intro paragraphs
			P(420), P(380), P(290),
			H(2, "1. Overusing transitional phrases"),
			P(310), P(280), P(350),
			H(2, "2. Robotic sentence structure"),
			P(410), P(220), P(380),
			H(2, "3. Vague filler words"),
			P(290), P(340), P(280),
			H(2, "4. Predictable conclusions"),
			P(310), P(360),
			H(2, "5. Avoiding contractions"),
			P(330), P(280),
			# Related-articles rail at the bottom uses H5
			H(5, "Related: 4 Reasons Why AI Checkers Might Flag..."),
			H(5, "Related: How to Detect AI-Written Text"),
			H(5, "Related: One-Third of New Websites Are AI"),
		],
		formInputCount=0,
		interactiveControlCount=45,
		focusedControlIsEditable=False,
	),
)

WDBO_ARTICLE = (
	"WDBO: Coast Guard rescue (article)",
	Intent.ARTICLE,
	TreeSummary(
		url="https://www.wdbo.com/news/local/coast-guard-saves-7-after-boat-breakdown-22-miles-off-new-smyrna-beach/CFAC53HIBJGGVAFQUGNXYBOGMQ/",
		hasMainLandmark=True,
		articleCount=1,
		mainNodes=[
			H(1, "Coast Guard saves 7 after boat breakdown..."),
			H(2, "Coast Guard highlights safety measures..."),  # dek
			# Short article body — 5 paragraphs.
			P(180), P(140), P(110), P(120), P(160),
			# Related-articles rail at the bottom — H2 cluster of 4.
			H(2, "Listen"),
			H(2, "Florida woman arrested..."),
			H(2, "VIDEO: Two Lake Brantley Teens..."),
			H(2, "More from WDBO"),
		],
		formInputCount=0,
		interactiveControlCount=35,
		focusedControlIsEditable=False,
	),
)

WEBFRIENDLYHELP_HOME = (
	"webfriendlyhelp.com home (WordPress homepage with body text)",
	Intent.ARTICLE,
	TreeSummary(
		url="https://webfriendlyhelp.com/",
		hasMainLandmark=True,
		articleCount=1,  # WordPress wraps the page in <article>
		mainNodes=[
			H(2, "WFH Updates"),
			H(1, "Welcome to WebFriendlyHelp.com!"),
			# Body paragraphs — substantial despite being a homepage.
			P(115, "If you are blind or have difficulty with your vision..."),
			P(280, "My name is Casey Mathews, and I love helping..."),
			P(190, "I have nearly thirty years experience..."),
			P(150, "To learn more about me, check out the about page..."),
		],
		formInputCount=1,  # search box in sidebar
		interactiveControlCount=25,
		focusedControlIsEditable=False,
	),
)

PATTYSWORLDS_HOME = (
	"pattysworlds.com home (WordPress homepage with body + post list)",
	Intent.ARTICLE,
	TreeSummary(
		url="https://pattysworlds.com/",
		hasMainLandmark=True,
		articleCount=1,
		mainNodes=[
			H(3, "Welcome to Patty's Worlds!"),
			# Welcome message — 5 substantial paragraphs
			P(220), P(280), P(260), P(310), P(180), P(120),
			H(2, "RAMBLES BLOG RECENT POSTS"),
			# Recent posts use list items, not headings. Each list item is
			# a link with short text — exposed as paragraphs in NVDA's tree.
			P(140), P(180), P(160), P(120), P(150), P(130),
			H(2, "LATEST COMMENTS"),
			P(80), P(95), P(70),
		],
		formInputCount=1,
		interactiveControlCount=50,
		focusedControlIsEditable=False,
	),
)

ACB_HOME = (
	"acb.org home (landing page with single hero paragraph + cards)",
	Intent.ARTICLE,
	TreeSummary(
		url="https://acb.org/",
		hasMainLandmark=True,
		articleCount=0,  # Drupal site, often no <article>
		mainNodes=[
			H(1, "Fostering Voice, Choice, and Community"),
			P(400, "You're not alone in your journey through vision loss..."),
			# Conference banner — small text blocks
			P(80, "2026 ACB Conference & Convention"),
			P(70, "July 24 - 31 in St. Louis, MO..."),
			H(2, "Top Links"),
			# Bullet list of 11 links
			P(40), P(35), P(45), P(30), P(50), P(55), P(45), P(40), P(35), P(45), P(50),
			H(2, "News"),
			# News teasers
			P(150), P(140), P(85), P(165), P(140), P(155),
		],
		formInputCount=1,
		interactiveControlCount=60,
		focusedControlIsEditable=False,
	),
)

NFB_HOME = (
	"nfb.org home (landing page with stacked H1s + hero paragraph + cards)",
	Intent.ARTICLE,
	TreeSummary(
		url="https://nfb.org/",
		hasMainLandmark=True,
		articleCount=0,
		mainNodes=[
			# Drupal exposes both the page-title H1 and the hero H1.
			H(1, "Homepage"),
			H(1, "Welcome to the Movement"),
			P(470, "We advance the lives of our members and all blind people..."),
			# Cards — each is an H3 with a short blurb beneath.
			H(3, "Give $25"),
			P(180),
			H(3, "Center of Excellence in Nonvisual Accessibility"),
			P(120),
			H(3, "Access On Podcast"),
			P(130),
			H(3, "Self-Advocacy Toolkit and Tracking Form"),
			P(110),
			H(3, "NFB-NEWSLINE"),
			P(95),
		],
		formInputCount=1,
		interactiveControlCount=55,
		focusedControlIsEditable=False,
	),
)

GLIDANCE_HOME = (
	"glidance.io home (marketing landing with hero + body sections)",
	Intent.ARTICLE,
	TreeSummary(
		url="https://glidance.io/",
		hasMainLandmark=True,
		articleCount=0,
		mainNodes=[
			H(1, "The World's First Intelligent Guide."),
			P(180, "Glide is pioneering the future of independent mobility..."),
			H(2, "A Smarter Way to Navigate Your World."),
			P(90, "Glide offers a groundbreaking leap..."),
			P(270, "With two wheels connected to the ground..."),
			P(130, "Whether it's a trip to the store..."),
			P(240, "Leveraging cutting-edge AI, sensors and robotics..."),
			H(2, "Built For Every Journey."),
			P(210, "Glide is light, intuitive, and built for real-world..."),
			H(3, "Glide's Capabilities"),
			H(4, "Smart Indoor & Outdoor Navigation."),
			P(110, "Walk with ease and without veering..."),
			H(4, "Line Maintenance & Obstacle Avoidance."),
			P(140, "Maintain a purposeful line..."),
			H(4, "Locate Doors, Elevators, Stairs, & More."),
			P(80, "Glide finds key targets..."),
		],
		formInputCount=0,
		interactiveControlCount=25,
		focusedControlIsEditable=False,
	),
)

APPLEVIS_ARTICLE = (
	"applevis.com app description article (YES IPTV Player)",
	Intent.ARTICLE,
	TreeSummary(
		url="https://www.applevis.com/apps/ios/entertainment/yes-iptv-player",
		hasMainLandmark=True,
		articleCount=0,
		mainNodes=[
			H(1, "YES IPTV Player"),
			# Category label and link — short text
			P(25, "Category Entertainment"),
			H(3, "Description of App"),
			# Body paragraphs interleaved with a short disclaimer that resets
			# the body_cluster algorithm but not the hero run.
			P(265, "YES IPTV Player elevates your IPTV experience..."),
			P(95, "YES IPTV PLAYER DOES NOT PROVIDE ANY CONTENT..."),
			P(400, "YES IPTV Player is designed as an alternative..."),
			H(4, "Key Features"),
			# Many bullet items follow — each short.
			P(35), P(70), P(75), P(85), P(60), P(50), P(80), P(70),
			P(55), P(65), P(75), P(50), P(80), P(60), P(85), P(70),
			H(3, "Forum Topics"),
			P(30), P(35), P(40),
			H(3, "Comments"),
			P(180), P(140), P(220),
		],
		formInputCount=0,
		interactiveControlCount=40,
		focusedControlIsEditable=False,
	),
)

SAM_GOV_HOME = (
	"sam.gov home (gov portal: services + register CTA + announcements)",
	Intent.ARTICLE,
	TreeSummary(
		url="https://sam.gov/",
		hasMainLandmark=True,
		articleCount=0,
		mainNodes=[
			H(1, "SAM.gov | Home"),
			P(40, "Official U.S. Government Website 100% Free"),
			H(2, "The Official U.S. Government System for:"),
			# 6 service description list items
			P(30), P(30), P(35), P(35), P(30), P(40),
			H(2, "Already know what you want to find?"),
			# Search form section — no paragraphs here, just form controls
			H(2, "Register Your Entity or Get a Unique Entity ID"),
			P(110, "Register your entity or get a Unique Entity ID..."),
			H(2, "Announcements"),
			# Each announcement: date (short) + link title (short) + excerpt (substantial)
			P(10), P(60), P(250),
			P(10), P(50), P(200),
			P(10), P(70), P(290),
			P(10), P(45), P(210),
			P(10), P(50), P(230),
		],
		formInputCount=2,  # search domain dropdown + text field
		interactiveControlCount=60,
		focusedControlIsEditable=False,
	),
)

LWORKS_HOME = (
	"l-works.net home (small-business landing with tagline + game cards)",
	Intent.ARTICLE,
	TreeSummary(
		url="https://l-works.net/",
		hasMainLandmark=True,
		articleCount=0,
		mainNodes=[
			H(1, "Welcome to LWorks"),
			P(62, "Affordable Computer Games for Those with Visual Impairments."),
			P(250, "Since 2002, LWorks has been creating innovative audio games..."),
			H(2, "Featured Games"),
			H(5, "Super Egg Hunt"),
			P(190),
			H(5, "Blinded Guide"),
			P(230),
			H(5, "Brain Station"),
			P(190),
			H(5, "Super Liam"),
			P(210),
			H(5, "Super Liam 2"),
			P(180),
			H(5, "Slide"),
			P(180),
			H(5, "The Great Toy Robbery"),
			P(210),
			H(2, "About LWorks"),
			P(150),
			H(2, "More Games Available"),
			P(70),
			P(120),
		],
		formInputCount=0,
		interactiveControlCount=20,
		focusedControlIsEditable=False,
	),
)

SSA_HOME = (
	"ssa.gov home (gov landing page with short hero + card grid)",
	Intent.ARTICLE,
	TreeSummary(
		url="https://www.ssa.gov/",
		hasMainLandmark=True,
		articleCount=0,
		mainNodes=[
			H(2, "Your most-needed services, online"),
			P(130, "With a secure my Social Security account..."),
			# First card row — 4 H4s
			H(4, "Get a benefits estimate"),
			P(50, "Sign in to calculate your benefits estimate."),
			H(4, "Check eligibility"),
			P(80, "See what benefits you may qualify for..."),
			H(4, "Check your status"),
			P(80, "See where you are in your application..."),
			H(4, "Replace your card"),
			P(50, "Find the best way to replace your card."),
			H(2, "Life events"),
			# Second card row — 4 H4s with sub-lists
			H(4, "Age milestones"),
			P(40), P(35), P(35),
			H(4, "Health changes"),
			P(40), P(40), P(40),
			H(4, "Legal status changes"),
			P(35), P(40),
			H(4, "Personal information changes"),
			P(30), P(45), P(40),
			H(2, "Services"),
			H(2, "Popular tasks"),
			P(30), P(35), P(30),
		],
		formInputCount=1,
		interactiveControlCount=80,
		focusedControlIsEditable=False,
	),
)

STARBUCKS_HOME = (
	"starbucks.com home (marketing homepage, hero + product cards)",
	Intent.ARTICLE,
	TreeSummary(
		url="https://www.starbucks.com/",
		hasMainLandmark=True,
		articleCount=0,
		mainNodes=[
			H(2, "It's a great day for coffee"),  # promo strip at top
			H(1, "It's Starbucks summer"),
			P(190, "Enticing new flavors and returning favorites are here..."),
			H(2, "Unicorn Cake Pop"),
			P(95, "Vanilla cake, white chocolate icing..."),
			H(2, "At the airport? Order ahead."),
			P(150, "Summer travel tip: Place your order..."),
			H(2, "Cheers to the grads!"),
			P(100, "Celebrate their achievements..."),
		],
		formInputCount=0,
		interactiveControlCount=30,
		focusedControlIsEditable=False,
	),
)

CLEVERBRAILLE_HOME = (
	"cleverbraille.com home (WordPress homepage, minimal)",
	Intent.ARTICLE,
	TreeSummary(
		url="https://cleverbraille.com/",
		hasMainLandmark=True,
		articleCount=1,
		mainNodes=[
			# No H1 visible — just body paragraphs in the main region.
			P(180, "Braille Literacy has been a topic of much discussion..."),
			P(170, "It is my hope that Clever Braille will provide..."),
			P(190, "Additionally, there is a blog where I have posted..."),
			P(130, "For more of a peek into me and what I hope..."),
		],
		formInputCount=0,
		interactiveControlCount=12,
		focusedControlIsEditable=False,
	),
)


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------

BBC_NEWS_HOMEPAGE = (
	"BBC News homepage (list)",
	Intent.LIST,
	TreeSummary(
		url="https://www.bbc.com/news",
		hasMainLandmark=True,
		articleCount=0,  # BBC News doesn't wrap each story card in <article>
		mainNodes=[
			H(1, "News"),
			H(2, "Deal with US not imminent, Iran says"),
			P(80),
			H(2, "White House gunman had previous run-ins..."),
			P(120),
			H(2, "Threat of massive chemical tank explosion..."),
			P(95),
			H(2, "Three killed in Uganda after crashing..."),
			P(75),
			H(2, "Netanyahu says Israel will intensify..."),
			P(110),
			H(2, "Russia threatens more Kyiv strikes..."),
			P(90),
			H(2, "Iran-Israel-US story"),
			P(85),
			H(2, "California fire update"),
			P(100),
			H(2, "Africa story"),
			P(70),
			H(2, "Middle East analysis"),
			P(95),
			H(2, "Europe story"),
			P(105),
			H(2, "Asia story"),
			P(80),
		],
		formInputCount=0,
		interactiveControlCount=180,
		focusedControlIsEditable=False,
	),
)

DDG_SEARCH = (
	"DuckDuckGo: search results (list)",
	Intent.LIST,
	TreeSummary(
		url="https://html.duckduckgo.com/html/?q=memorial+day+history",
		hasMainLandmark=True,
		articleCount=0,
		mainNodes=[
			H(2, "Memorial Day - Wikipedia"),
			P(180),
			H(2, "Memorial Day | Weekend, Meaning, Facts | Britannica"),
			P(220),
			H(2, "Memorial Day: 2026 Date, Meaning & Origins | HISTORY"),
			P(195),
			H(2, "Memorial Day - Origins, History & Significance"),
			P(160),
			H(2, "When is Memorial Day 2026 and what is its history?"),
			P(170),
			H(2, "Memorial Day: From Decoration Day to today"),
			P(200),
			H(2, "VA | Office of Public Affairs - Memorial Day"),
			P(175),
		],
		formInputCount=1,  # the search box itself
		interactiveControlCount=50,
		focusedControlIsEditable=False,
	),
)

STEVE_QUAYLE = (
	"stevequayle.com (aggregator)",
	Intent.LIST,
	TreeSummary(
		url="https://www.stevequayle.com/",
		hasMainLandmark=False,  # legacy site, no semantic landmarks
		articleCount=0,
		mainNodes=[
			H(3, "Soldiers Lost, Stories Untold..."),
			P(20),
			H(3, "Story 2"),
			P(30),
			H(3, "Story 3"),
			P(25),
			H(3, "Story 4"),
			P(40),
			H(3, "Story 5"),
			P(15),
			H(3, "Story 6"),
			P(35),
			H(3, "Story 7"),
			H(3, "Story 8"),
		],
		formInputCount=0,
		interactiveControlCount=90,
		focusedControlIsEditable=False,
	),
)


# ---------------------------------------------------------------------------
# Portal / dashboard
# ---------------------------------------------------------------------------

XFINITY_PORTAL = (
	"xfinity.com (portal — APP at low confidence is fine)",
	Intent.APP,
	TreeSummary(
		url="https://www.xfinity.com/",
		hasMainLandmark=True,
		articleCount=0,
		mainNodes=[
			H(1, "Xfinity"),
			H(2, "My Account"),
			P(60),
			H(2, "Internet"),
			P(80),
			H(2, "TV"),
			P(40),
		],
		formInputCount=2,
		interactiveControlCount=70,
		focusedControlIsEditable=False,
	),
)


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

GENERIC_SIGNUP = (
	"Generic signup form (synthetic)",
	Intent.FORM,
	TreeSummary(
		url="https://example.com/signup",
		hasMainLandmark=True,
		articleCount=0,
		mainNodes=[
			H(1, "Create your account"),
			P(60),
		],
		formInputCount=6,
		interactiveControlCount=8,
		focusedControlIsEditable=False,
	),
)


# ---------------------------------------------------------------------------
# Guardrail #6 — focus already on an editable control
# ---------------------------------------------------------------------------

ARTICLE_WITH_FOCUS_ON_SEARCH = (
	"Article page where site auto-focused the search box",
	Intent.SILENT_FOCUS_HONORED,
	TreeSummary(
		url="https://example.com/news/some-article",
		hasMainLandmark=True,
		articleCount=1,
		mainNodes=[
			H(1, "Some Article Title"),
			P(280), P(320), P(410), P(290), P(350),
			H(2, "Section 1"),
			P(310),
			H(2, "Section 2"),
			P(280),
		],
		formInputCount=1,
		interactiveControlCount=30,
		focusedControlIsEditable=True,  # the gating condition
	),
)

WIKIPEDIA_HOMEPAGE = (
	"wikipedia.org homepage — site auto-focuses search box",
	Intent.SILENT_FOCUS_HONORED,
	TreeSummary(
		url="https://www.wikipedia.org/",
		hasMainLandmark=True,
		articleCount=0,
		mainNodes=[
			# Logo + search-box area. Minimal text content.
			P(60, "Wikipedia The Free Encyclopedia"),
		],
		formInputCount=1,
		interactiveControlCount=20,
		focusedControlIsEditable=True,  # Wikipedia places focus in search on load
	),
)

DDG_HOMEPAGE = (
	"duckduckgo.com homepage — site auto-focuses search box",
	Intent.SILENT_FOCUS_HONORED,
	TreeSummary(
		url="https://duckduckgo.com/",
		hasMainLandmark=True,
		articleCount=0,
		mainNodes=[
			# Minimal content on the homepage — logo, search input, a few links.
			P(40),
		],
		formInputCount=1,
		interactiveControlCount=15,
		focusedControlIsEditable=True,  # DDG places focus in the search box on load
	),
)


# ---------------------------------------------------------------------------
# All fixtures
# ---------------------------------------------------------------------------

ALL_FIXTURES = [
	WIKIPEDIA_MEMORIAL_DAY,
	MAKEUSEOF_ARTICLE,
	WDBO_ARTICLE,
	WEBFRIENDLYHELP_HOME,
	PATTYSWORLDS_HOME,
	GLIDANCE_HOME,
	STARBUCKS_HOME,
	SSA_HOME,
	SAM_GOV_HOME,
	APPLEVIS_ARTICLE,
	LWORKS_HOME,
	CLEVERBRAILLE_HOME,
	ACB_HOME,
	NFB_HOME,
	BBC_NEWS_HOMEPAGE,
	DDG_SEARCH,
	STEVE_QUAYLE,
	XFINITY_PORTAL,
	GENERIC_SIGNUP,
	ARTICLE_WITH_FOCUS_ON_SEARCH,
	WIKIPEDIA_HOMEPAGE,
	DDG_HOMEPAGE,
]
