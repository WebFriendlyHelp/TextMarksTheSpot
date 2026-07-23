# Landing-finder tests.
#
# detection/web.py's find_article_landing / find_list_landing / find_notice_landing
# are pure functions over a TreeSummary. These tests pin the behavior on the
# page shapes we've encountered — especially the bestmidi.com regression
# where the addon was landing on a footer line.

import classifier as cls
from detection import web


def _node(kind, length, level=None, preview="", ends_sentence=False, is_disclosure=False):
	return cls.MainNode(
		kind=kind, level=level, text_length=length, text_preview=preview,
		ends_sentence=ends_sentence, is_disclosure=is_disclosure,
	)


def _summary_with(nodes):
	return cls.TreeSummary(main_nodes=nodes)


# ---------------------------------------------------------------------------
# find_article_landing
# ---------------------------------------------------------------------------

def test_article_landing_picks_cluster_start():
	# Two substantial paragraphs in a row — first is the landing.
	nodes = [
		_node("paragraph", 150),
		_node("paragraph", 200),
		_node("paragraph", 180),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 0


def test_article_landing_skips_photo_caption_before_lede():
	# Regression: fox21news.com article. The hero image's caption sits between
	# the H1 and the opening line and clears the substantial bar, so it used to
	# win the cluster gate and the cursor landed on the photo credit. The lede's
	# own leading "(KDVR)" parenthetical must NOT trip the caption filter.
	caption = "Colorado State Capitol Building from the pathways of Civic Center Park In downtown Denver (Getty Images)"
	lede = "DENVER (KDVR) - A handful of Colorado laws are set to go into effect starting in July."
	# Long second paragraph (>150 chars and >2x the lede) — without the dateline
	# guard the teaser-skip rule would treat the short lede as a teaser and
	# overshoot to here.
	body = (
		"While Colorado laws get passed all the time, the effective date is sometimes "
		"delayed to make sure people have time to comply with the law before there are "
		"penalties for non-compliance across the state."
	)
	assert len(body) > 150 and len(body) > len(lede) * 2
	nodes = [
		_node("heading", 45, level=1, preview="These Colorado laws are going into effect in July"),
		_node("paragraph", len(caption), preview=caption),
		_node("paragraph", len(lede), preview=lede),
		_node("paragraph", len(body), preview=body),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 2


def test_article_landing_skips_publisher_opinion_disclaimer():
	# RedState articles (2026-07-20, three of them, identical shape): H1, an
	# author slug, a byline, then "The opinions expressed by contributors are
	# their own and do not necessarily represent the views of RedState.com." —
	# a grammatical sentence that ended sentence-strict and clustered with the
	# adjacent share-link payload, so the cascade landed on it (idx 3). The real
	# lede is two nodes later. Passing the FULL disclaimer text as the preview
	# exercises the detector itself (not a hardcoded flag), so this fails before
	# the _DISCLOSURE_OPINION rule exists.
	disclaimer = ("The opinions expressed by contributors are their own and do "
	              "not necessarily represent the views of RedState.com.")
	share = "?subject=F-16s%20Scrambled%2C%20Flares%20Deployed%20After%20Pilots"
	# The real lede is 233 chars — very-substantial (>=200), the gate that
	# reaches it once the disclaimer is chrome. Keep the fixture length faithful.
	lede = ("The North American Aerospace Defense Command (NORAD) scrambled F-16 "
	        "fighter jets on Sunday after several general aviation aircraft breached "
	        "the temporary flight restrictions around President Trump at the World Cup "
	        "final in New Jersey.")
	assert len(lede) >= 200
	nodes = [
		_node("heading", 91, level=1, preview="F-16s Scrambled, Flares Deployed After Pilots Breach Airspace"),
		_node("paragraph", 11, preview="rusty-weiss"),
		_node("paragraph", 73, preview="By Rusty Weiss Rusty_Weiss ref_src=twsrc"),
		_node("paragraph", len(disclaimer), ends_sentence=True, preview=disclaimer),
		_node("paragraph", 427, ends_sentence=True, preview=share),
		_node("paragraph", 101, preview="A U.S. Air Force F-16 Fighting Falcon. (Credit: U."),
		_node("paragraph", len(lede), ends_sentence=True, preview=lede),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 6


def test_opinion_disclaimer_detected_and_prose_is_safe():
	# The RedState disclaimer and a BBC-style variant match; prose containing
	# only ONE half of the conjunction must not (both halves occur in ordinary
	# sentences on their own).
	assert web._looks_like_editorial_disclosure(
		"The opinions expressed by contributors are their own and do not "
		"necessarily represent the views of RedState.com.") is True
	assert web._looks_like_editorial_disclosure(
		"Views expressed in this article do not necessarily reflect those of "
		"the BBC.") is True
	assert web._looks_like_editorial_disclosure(
		"The opinions expressed at the town hall were heated and divided.") is False
	assert web._looks_like_editorial_disclosure(
		"These lab results do not necessarily represent the broader population.") is False


def test_newsletter_signup_promo_is_chrome_but_prose_is_safe():
	# Tom's Hardware front page landed on this newsletter CTA (2026-07-21); the
	# "to your inbox" giveaway sits past the 60-char preview, so this is a
	# walk-time is_disclosure flag over full text. Real prose is left alone.
	assert web._looks_like_editorial_disclosure(
		"Get Tom's Hardware's best news and in-depth reviews, straight to your inbox.") is True
	assert web._looks_like_editorial_disclosure(
		"Sign up for our newsletter to get the latest deals and reviews.") is True
	# Prose that merely mentions email / newsletters is NOT a signup CTA.
	assert web._looks_like_editorial_disclosure(
		"The startup builds a newsletter platform for independent writers.") is False
	assert web._looks_like_editorial_disclosure(
		"She opened her laptop and found the report waiting for her.") is False


def test_article_landing_skips_dated_byline():
	# Gateway Pundit (2026-07-21): "By Jenn Baker Jul. 20, 2026 7:40 pm" (with
	# the article slug jammed onto the end) is the first substantial paragraph,
	# a mixed-case "By Name" byline the all-caps rule skips. It won idx 1 and
	# the real lede sat at idx 9. The publication date makes the byline safe to
	# flag. Full byline text as the preview so the detector runs, not a flag.
	byline = "By Jenn Baker Jul. 20, 2026 7:40 pmflock-safetys-billion-dollar-surv"
	lede = ("The Orange traffic barrel on the side of Arizona State Route 60 looked "
	        "like any other piece of construction equipment.")
	nodes = [
		_node("heading", 89, level=1, preview="Flock Safety's Billion-Dollar Surveillance Machine"),
		_node("paragraph", 66, ends_sentence=True, preview=byline),
		_node("paragraph", 15, preview="TruthTweetShare"),
		_node("paragraph", 5, preview="Gettr"),
		_node("paragraph", 122, preview="GabShare on TelegramShare on LinkedInShare on Fre"),
		_node("paragraph", 25, preview="Listen to the article now"),
		_node("paragraph", 19, preview="Audio by Carbonatix"),
		_node("paragraph", 1, preview="0"),
		_node("paragraph", 96, preview="Your Firefox settings blocked this content from tr"),
		_node("paragraph", len(lede), ends_sentence=True, preview=lede),
		_node("paragraph", 136, ends_sentence=True, preview="It also had a camera lens carved into both sides,"),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 9


def test_dated_byline_detected_and_by_prose_openers_safe():
	# The dated byline matches; real ledes that open with "By" do not — the
	# guards are: a full Month-DD-YYYY date, a capitalized non-weekday name after
	# "By", and a short length.
	assert web._looks_like_byline("By Jenn Baker Jul. 20, 2026 7:40 pm") is True
	assert web._looks_like_byline("By Sarah Connor March 3, 2025") is True
	# weekday opener + date = temporal prose, not a byline
	assert web._looks_like_byline("By Monday, June 5, 2026, the crews had cleared the debris.") is False
	# no day in the date
	assert web._looks_like_byline("By January 2026, sales had risen sharply.") is False
	# no date at all
	assert web._looks_like_byline("By NASA's estimate, the mission will cost billions.") is False


def test_headline_list_fires_on_wall_of_titles():
	# Index/homepage: nav labels, then a wall of non-sentence headline titles,
	# no article body. Land on the FIRST headline.
	nodes = [
		_node("paragraph", 6, preview="Home"),
		_node("paragraph", 9, preview="Sections"),
		_node("paragraph", 62, preview="Nvidia's DLSS 5 can switch between three AI models in real"),
		_node("paragraph", 55, preview="China is considering export controls on AI technologies"),
		_node("paragraph", 48, preview="Amazon data center in Bahrain struck and destroyed"),
		_node("paragraph", 70, preview="Anthropic slapped with a settlement in a copyright case"),
		_node("paragraph", 66, preview="Intel to co-develop next-gen firewall silicon"),
		_node("paragraph", 58, preview="TSMC eyes price hikes on chip production services"),
	]
	assert web._find_headline_list_landing(nodes) == 2


def test_headline_list_declines_when_article_body_present():
	# A real article with a related-stories rail: the sentence-ending body
	# cluster must keep the headline gate OFF so the cascade lands on the body.
	nodes = [
		_node("heading", 30, level=1, preview="The Big Story"),
		_node("paragraph", 180, ends_sentence=True, preview="The event unfolded over three days, beginning when the crew"),
		_node("paragraph", 210, ends_sentence=True, preview="Officials confirmed the details in a briefing on Monday mor"),
		_node("paragraph", 160, ends_sentence=True, preview="The full impact is still being assessed by the agency invol"),
		_node("heading", 10, level=2, preview="Read more"),
		_node("paragraph", 62, preview="Nvidia's DLSS 5 can switch between three AI models in real"),
		_node("paragraph", 55, preview="China is considering export controls on AI technologies"),
		_node("paragraph", 48, preview="Amazon data center in Bahrain struck and destroyed"),
		_node("paragraph", 70, preview="Anthropic slapped with a settlement in a copyright case"),
		_node("paragraph", 66, preview="Intel to co-develop next-gen firewall silicon"),
		_node("paragraph", 58, preview="TSMC eyes price hikes on chip production services"),
	]
	assert web._find_headline_list_landing(nodes) is None
	# and the cascade lands on the body, not the rail
	assert web.find_article_landing(_summary_with(nodes)) == 1


def test_url_slug_is_chrome():
	# Ars Technica exposes each story's slug as its own line above the headline.
	assert web._is_chrome_paragraph(
		_node("paragraph", 36, preview="when-your-vehicle-outlives-its-cloud")) is True
	# Real prose with spaces is never a slug, even with hyphens.
	assert web._is_chrome_paragraph(
		_node("paragraph", 24, preview="state-of-the-art design work")) is False


def test_article_landing_skips_caption_via_flag_when_credit_truncated():
	# Production path: tree_summary truncates text_preview to 60 chars, so the
	# trailing "(Getty Images)" credit is GONE from the preview and only the
	# is_caption flag (computed over full text at walk time) marks the node.
	# The landing must still skip it.
	caption = cls.MainNode(
		kind="paragraph",
		text_length=103,
		text_preview="Colorado State Capitol Building from the pathways of Civic Ce",  # 60 chars, no credit
		is_caption=True,
	)
	lede = cls.MainNode(kind="paragraph", text_length=85, text_preview="DENVER (KDVR) - A handful of Colorado laws set to take effect")
	# Long second paragraph so teaser-skip is in play; the dateline guard must
	# still keep the landing on the lede.
	body = cls.MainNode(kind="paragraph", text_length=190, text_preview="While Colorado laws get passed all the time, the effective da")
	nodes = [
		_node("heading", 45, level=1, preview="These Colorado laws are going into effect in July"),
		caption,
		lede,
		body,
	]
	assert web.find_article_landing(_summary_with(nodes)) == 2


def test_image_caption_filter_matches_credits_not_datelines():
	# Trailing photo-credit parenthetical → caption.
	assert web._looks_like_image_caption("A scenic overlook at sunset (Getty Images)")
	assert web._looks_like_image_caption("City hall downtown. (Photo: Jane Doe)")
	assert web._looks_like_image_caption("Image courtesy of the city of Denver")
	# Leading non-credit parenthetical (news dateline) → NOT a caption.
	assert not web._looks_like_image_caption(
		"DENVER (KDVR) - A handful of Colorado laws take effect in July."
	)
	# Ordinary prose with an aside in parentheses → NOT a caption.
	assert not web._looks_like_image_caption(
		"The bill (which passed in May) raises the minimum wage statewide."
	)


def test_news_dateline_detection():
	# AP-style datelines → True (em-dash, en-dash, and spaced-hyphen separators).
	assert web._looks_like_news_dateline("DENVER (KDVR) — A handful of Colorado laws take effect.")
	assert web._looks_like_news_dateline("DENVER (KDVR) - A handful of Colorado laws take effect.")
	assert web._looks_like_news_dateline("WASHINGTON — The Senate voted Tuesday.")
	assert web._looks_like_news_dateline("NEW YORK (AP) — Stocks rose.")
	# Sentence-case prose (a CNET-style teaser) and ordinary openers → False.
	assert not web._looks_like_news_dateline("When I first started using an iMac back in 2008.")
	assert not web._looks_like_news_dateline("Keyboard shortcuts can be a huge time saver.")
	assert not web._looks_like_news_dateline("The Senate voted Tuesday to advance the bill.")


def test_article_landing_picks_hero_before_heading():
	# Hero pattern: substantial paragraph followed by a heading within lookahead.
	nodes = [
		_node("paragraph", 200),
		_node("heading", 30, level=2),
		_node("paragraph", 50),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 0


def test_article_landing_does_not_return_last_node_if_better_exists():
	# Regression: bestmidi.com/bg/ — scoped walk failed, main_nodes contains
	# nav + intro + footer. Idx 6 (60-char intro) is the right landing. The
	# old code returned idx 19 (59-char footer) via "last node, accept"
	# shortcut. The fix removes that shortcut so the largest-paragraph
	# fallback picks idx 6.
	nodes = [
		_node("paragraph", 20),   # 0 Skip to main content
		_node("paragraph", 6),    # 1-5 nav links
		_node("paragraph", 15),
		_node("paragraph", 19),
		_node("paragraph", 13),
		_node("paragraph", 15),
		_node("paragraph", 60),   # 6 intro ← target
		_node("paragraph", 12),
		_node("paragraph", 3),
		_node("paragraph", 6),
		_node("paragraph", 3),
		_node("paragraph", 13),
		_node("paragraph", 8),
		_node("paragraph", 3),
		_node("heading", 11, level=2),
		_node("paragraph", 7),
		_node("paragraph", 7),
		_node("paragraph", 19),
		_node("paragraph", 32),
		_node("paragraph", 59),   # 19 footer disclaimer ← used to land here
	]
	assert web.find_article_landing(_summary_with(nodes)) == 6


def test_article_landing_jetpack_daily_writing_prompt():
	# Regression: steviet3.wordpress.com daily-prompt post. has_main=False so
	# main_nodes leads with the nav menu, then the Jetpack "Daily writing
	# prompt" widget (label / question / "View all responses"), then short
	# intro lines, then the numbered advice list. The prompt question is a
	# lone 64-char paragraph: it loses the cluster gate (next node is the
	# 18-char "View all responses") and the hero gate (under 100 chars), so
	# the old code fell through and landed on "1. Follow your heart" (the
	# first list cluster). The widget rule should land on the question.
	nodes = [
		_node("paragraph", 4, preview="HOME"),
		_node("paragraph", 11, preview="BIBLET WALL"),
		_node("paragraph", 27, preview="AM I A WRITER OR AN AUTHOR?"),
		_node("paragraph", 5, preview="POEMS"),
		_node("paragraph", 30, preview="USEFUL INFORMATION FOR AUTHORS"),
		_node("paragraph", 7, preview="Search:"),
		_node("paragraph", 22, preview="steviet3.wordpress.com"),
		_node("paragraph", 2, preview="16"),
		_node("paragraph", 20, preview="Daily writing prompt"),       # 8 label
		_node("paragraph", 64, preview="What is something you wish you could tell your 20-"),  # 9 question
		_node("paragraph", 18, preview="View all responses"),         # 10
		_node("paragraph", 33, preview="For 20-year-old women everywhere:"),  # 11 short intro
		_node("paragraph", 89, preview="1. Follow your heart. Think about what you're good"),  # 12
		_node("paragraph", 138, preview="3. Take heed of the warnings on cigarette packets "),  # 13
	]
	assert web.find_article_landing(_summary_with(nodes)) == 9


def test_article_landing_no_prompt_widget_unaffected():
	# Sanity: a post without the widget still lands via the normal cluster
	# gate, unchanged by the widget rule.
	nodes = [
		_node("paragraph", 30, preview="For 20-year-old women everywhere:"),
		_node("paragraph", 89, preview="1. Follow your heart..."),
		_node("paragraph", 138, preview="3. Take heed..."),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 1


def test_article_landing_positionally_scoped_takes_first_substantial():
	# Regression: steviet3.wordpress.com after article-positional scoping.
	# main_nodes is now chrome-free (post metadata then content). The prompt
	# question (idx 4, 64 chars) is a lone sub-100 paragraph followed by a
	# 33-char intro, so the hero/cluster gates would skip it and land on the
	# list (idx 6). Because the tree is positionally scoped, land on the first
	# substantial paragraph instead — the question.
	nodes = [
		_node("paragraph", 2, preview="16"),
		_node("paragraph", 8, preview="Jun 2026"),
		_node("paragraph", 13, preview="≈ 10 Comments"),
		_node("paragraph", 30, preview="#dailyprompt, dailyprompt-2794"),
		_node("paragraph", 64, preview="What is something you wish you could tell your 20-"),  # 4
		_node("paragraph", 33, preview="For 20-year-old women everywhere:"),  # 5
		_node("paragraph", 89, preview="1. Follow your heart. Think about what you’re good"),  # 6
		_node("paragraph", 138, preview="3. Take heed of the warnings on cigarette packets "),  # 7
	]
	summary = cls.TreeSummary(main_nodes=nodes, positionally_scoped=True)
	assert web.find_article_landing(summary) == 4


def test_article_landing_not_scoped_keeps_defensive_gates():
	# Same shape but NOT positionally scoped (unscoped/noisy tree): the lone
	# 64-char paragraph must still lose to the list cluster, preserving the
	# defensive behavior that protects against pre-content chrome.
	nodes = [
		_node("paragraph", 64, preview="What is something you wish you could tell your 20-"),
		_node("paragraph", 33, preview="For 20-year-old women everywhere:"),
		_node("paragraph", 89, preview="1. Follow your heart..."),
		_node("paragraph", 138, preview="3. Take heed..."),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 2


def test_looks_like_tag_list_detects_no_space_comma_joined_categories():
	# Direct unit test for the helper. Tag rows look like
	# "CoPilot,Microsoft 365,Microsoft Excel,..." with no spaces.
	assert web._looks_like_tag_list("CoPilot,Microsoft 365,Microsoft Excel,Microsoft Office") is True
	assert web._looks_like_tag_list("A,B,C,D") is True


def test_looks_like_accessibility_instructions_detects_amazon_dropdown_help():
	# Amazon product pages emit text like "Shop by Room, You are currently
	# on a drop-down. To open this, press alt+down arrow." — UI help, not
	# article content. The "you are currently on" phrase is the signal.
	assert web._looks_like_accessibility_instructions(
		"Shop by Room, You are currently on a drop-down. To open this, press alt+down arrow."
	) is True
	# Case-insensitive.
	assert web._looks_like_accessibility_instructions(
		"YOU ARE CURRENTLY ON a tab control. Press right arrow to move."
	) is True


def test_looks_like_accessibility_instructions_rejects_normal_prose():
	# Prose that doesn't contain the specific phrase should pass through.
	assert web._looks_like_accessibility_instructions(
		"For years, Malwarebytes has protected people by going where they are."
	) is False
	assert web._looks_like_accessibility_instructions("") is False
	assert web._looks_like_accessibility_instructions(
		"Microsoft has quietly flipped a major switch."
	) is False


def test_content_section_landing_picks_paragraph_after_about_this_item():
	# Generic Amazon-style pattern: a chrome-heavy page where the actual
	# product description lives under an "About this item" heading.
	nodes = [
		_node("paragraph", 15, preview="Skip to content"),
		_node("paragraph", 60, preview="Recommended for you, You are currently on a button"),
		_node("paragraph", 80, preview="Sponsored, Frequently bought together"),
		_node("heading", 16, preview="About this item", level=2),
		_node("paragraph", 180, preview="Premium stainless steel with a brushed finish makes this"),
		_node("paragraph", 150, preview="Dishwasher safe and built to last for daily use"),
	]
	# Should land on idx 4 (first substantial paragraph after the
	# "About this item" heading), NOT idx 1 or 2 (chrome).
	assert web.find_article_landing(_summary_with(nodes)) == 4


def test_content_section_landing_handles_description_heading():
	# Recipe / how-to / software-doc pattern: "Description" heading is
	# where the actual content begins, with chrome before it.
	nodes = [
		_node("paragraph", 60, preview="Sponsored ads and tag widgets, click here for offers"),
		_node("heading", 11, preview="Description", level=2),
		_node("paragraph", 220, preview="This handcrafted ceramic mug holds 12 ounces and is microwave safe"),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 2


def test_content_section_landing_falls_through_when_section_empty():
	# If the matching heading has no substantial paragraph before the next
	# heading, the function gives up and lets the normal heuristics run.
	nodes = [
		_node("heading", 11, preview="Description", level=2),
		_node("paragraph", 5, preview="None."),     # too short to qualify
		_node("heading", 8, preview="Reviews", level=2),
		_node("paragraph", 250, preview="Long article body paragraph elsewhere on the page"),
	]
	# Description section has nothing substantial; falls through to the
	# very-substantial rule on idx 3.
	assert web.find_article_landing(_summary_with(nodes)) == 3


def test_content_section_landing_returns_none_with_no_matching_section():
	# Without any matching heading text, the function returns None and
	# normal article-shape heuristics apply unchanged.
	nodes = [
		_node("paragraph", 250, preview="Article intro paragraph at the top of the page"),
		_node("paragraph", 200, preview="Body paragraph two"),
	]
	# Very-substantial rule wins idx 0; content-section landing didn't fire.
	assert web.find_article_landing(_summary_with(nodes)) == 0


def test_content_section_landing_skips_a11y_instructions_under_section():
	# The substantial paragraph filters (tag-list, a11y-instructions)
	# still apply inside content sections — if the first "paragraph" after
	# "About this item" is screen-reader help, skip it.
	nodes = [
		_node("heading", 16, preview="About this item", level=2),
		_node("paragraph", 80, preview="You are currently on a tab. Press right arrow to navigate."),
		_node("paragraph", 180, preview="The real product description starts here with prose content."),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 2


def _vovsoft_ai_requester_nodes():
	"""The real node trail from vovsoft.com/software/ai-requester/, taken from
	the decision trace of a live mislanding (2026-07-18, nvda.log).

	Indices are FAITHFUL to the trace, because the distance between the
	"Key Features" heading at 34 and the licensing blurb at 49 is the entire
	point of the bug. Do not compact this fixture.

	Shape that produces the failure:
	  - genuine product description at 5-8
	  - "Key Features" heading at 34, the LAST heading on the page
	  - spec lines at 35-37 that do NOT end like sentences, so the
	    sentence-strict pass treats them as chrome and skips them
	  - short bullet lines at 38-48, all under the 50-char bar
	  - the 387-char licensing blurb at 49, which DOES end like a sentence
	"""
	nodes = [
		_node("paragraph", 13, preview="cookieconsent"),
		_node("heading", 12, level=1, preview="AI Requester"),
		_node("heading", 32, level=2, preview="Connects to OpenAI API with ease"),
		_node("paragraph", 27, preview="Release Date: June 13, 2026"),
		_node("paragraph", 30, preview="Version: 5.2 (Version History)"),
		_node("paragraph", 74, ends_sentence=True,
			preview="This program requires your own OpenAI API key for onl"),
		_node("paragraph", 103, ends_sentence=True,
			preview="Local models can run directly on your computer without"),
		_node("paragraph", 102, ends_sentence=True,
			preview="Vovsoft AI Requester is a program that can connect to"),
		_node("paragraph", 183, ends_sentence=True,
			preview="The software provides a reliable and easy-to-use interf"),
	]
	# 9-33: the feature sections. Only the shape matters here, not the text.
	nodes.append(_node("paragraph", 188, preview="Built for both offline and online environments, it"))
	while len(nodes) < 34:
		nodes.append(_node("paragraph", 40, preview="Short feature bullet line"))
	# 34: the section heading that triggers the bug. Last heading on the page.
	nodes.append(_node("heading", 12, level=2, preview="Key Features"))
	# 35-37: spec lines. Substantial enough to qualify, but they do not end
	# like sentences, so the strict pass discards them.
	nodes.append(_node("paragraph", 51, preview="Category: Communications - Chat & Instant Messaging"))
	nodes.append(_node("paragraph", 84, preview="Supports: Windows Windows 11, Windows 10, Windows 8"))
	nodes.append(_node("paragraph", 50, preview="File Size: 3.71 MB (Installer), 2.51 MB (Portable)"))
	# 38-48: short bullets, all below the landing bar.
	while len(nodes) < 49:
		nodes.append(_node("paragraph", 30, preview="Short bullet"))
	# 49: what the add-on wrongly spoke.
	nodes.append(_node("paragraph", 387, ends_sentence=True,
		preview="To receive license key and use all features of the s"))
	return nodes


def test_content_section_does_not_claim_a_distant_paragraph():
	# Regression: vovsoft product pages spoke a licensing blurb instead of the
	# product description. _find_content_section_landing matched the "Key
	# Features" heading at 34, then scanned forward with NO distance limit,
	# stopping only at the next heading. There IS no next heading, so it ran to
	# the end of the document and claimed the licensing paragraph at 49 —
	# fifteen nodes past its own section heading, in a different page section.
	#
	# Confirmed NOT to be truncation: two sibling pages mislanded identically
	# with truncated=False, and their descriptions were 263 and 207 chars,
	# comfortably over the 200-char very-substantial bar. The content-section
	# gate runs BEFORE that rule and jumped past them.
	nodes = _vovsoft_ai_requester_nodes()
	idx = web.find_article_landing(_summary_with(nodes))
	assert idx != 49, "landed on the licensing blurb, the reported bug"
	# Must land in the genuine description block near the top of the page.
	assert 5 <= idx <= 8, f"expected the product description block, got idx={idx}"


def test_definitional_lede_beats_a_prerequisite_note_above_it():
	# The cluster gate awards the landing to the FIRST of two adjacent
	# substantial paragraphs. On the real vovsoft page that is a prerequisite
	# note ("This program requires your own OpenAI API key...", 74 chars)
	# clustered with a feature line (103), while the sentence that says what the
	# product IS sits two nodes below. Casey confirmed live that the note was
	# what got spoken and that he wanted the description instead.
	nodes = _vovsoft_ai_requester_nodes()
	assert web.find_article_landing(_summary_with(nodes)) == 7


def test_definitional_lede_leaves_ordinary_article_prose_alone():
	# The refinement must be inert on news shapes. No paragraph here names the
	# page subject followed by a copula, so the cluster gate's own choice
	# stands. This is the guard that keeps a general prose rule from becoming a
	# landing-mover on every article.
	nodes = [
		_node("heading", 48, level=1,
			preview="These Colorado laws are going into effect in July"),
		_node("paragraph", 86, ends_sentence=True,
			preview="DENVER (KDVR) - A handful of Colorado laws are set to take"),
		_node("paragraph", 190, ends_sentence=True,
			preview="While Colorado laws get passed all the time, the effective"),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 1


def test_definitional_lede_ignores_a_passing_mention_deep_in_prose():
	# "is a" far from the subject, or a subject mentioned deep into the
	# paragraph, must NOT qualify — otherwise any body paragraph that happens to
	# name the product becomes a landing magnet.
	subject = "Widget Pro"
	late = (
		"After a long preamble about pricing and availability in several "
		"regions, the vendor notes that Widget Pro is a tool."
	)
	assert web._looks_like_definitional_lede(late, subject) is False
	# Subject present early, but no copula near it.
	assert web._looks_like_definitional_lede(
		"Widget Pro pricing changed last year for most customers.", subject,
	) is False
	# The real shape, including a vendor prefix before the H1 text.
	assert web._looks_like_definitional_lede(
		"Acme Widget Pro is a tool that trims images.", subject,
	) is True


def test_content_section_still_claims_an_adjacent_paragraph():
	# The distance bound must not break the case the gate exists for: on a real
	# product page the description sits directly under its section heading.
	nodes = [
		_node("paragraph", 60, preview="Sponsored ads and tag widgets, click here for offers"),
		_node("heading", 16, preview="About this item", level=2),
		_node("paragraph", 180, ends_sentence=True,
			preview="Premium stainless steel with a brushed finish makes this"),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 2


def test_article_landing_skips_screen_reader_instructions():
	# Regression scenario: Amazon-style chrome where an accessibility help
	# paragraph (84 chars) wins via cluster with the next chrome paragraph.
	# The filter eliminates this candidate; the actual article-shaped node
	# (a hypothetical 250-char product description) wins instead.
	nodes = [
		_node("paragraph", 15, preview="Skip to"),
		_node("paragraph", 84, preview="Shop by Room, You are currently on a drop-down. To open this"),
		_node("paragraph", 61, preview="To move between items, use your keyboard arrow keys"),
		_node("paragraph", 250, preview="Stainless steel construction with brushed finish makes this"),
	]
	# Idx 1 (a11y instructions) and idx 3 (250-char product description)
	# are both candidates. Without the a11y filter, idx 1 would win
	# (cluster with idx 2). With the filter, idx 3 (>= 200, very-substantial)
	# wins.
	assert web.find_article_landing(_summary_with(nodes)) == 3


def test_looks_like_tag_list_rejects_prose_with_spaced_commas():
	# Real prose uses commas WITH spaces as standard punctuation.
	assert web._looks_like_tag_list("Microsoft has quietly flipped a major switch. Copilot Agent Mode is now the default in Word, Excel, and PowerPoint.") is False
	assert web._looks_like_tag_list("Apple, Orange, Banana") is False
	# Too short or no commas at all.
	assert web._looks_like_tag_list("Some short text.") is False
	assert web._looks_like_tag_list("") is False


def test_article_landing_very_substantial_paragraph_wins_over_later_bullet_cluster():
	# Regression: malwarebytes article — 280-char intro paragraph followed
	# by a short transitional sentence, then a bullet list whose items each
	# pass the 50-char "substantial" bar. Without the very-substantial rule,
	# the bullets won via primary cluster check (idx 12 + idx 13 both ≥ 50).
	# With it, the 280-char intro is accepted on its own at idx 4.
	nodes = [
		_node("paragraph", 15, preview="Skip to content"),
		_node("paragraph", 7, preview="Sign in"),
		_node("paragraph", 8, preview="Personal"),
		_node("heading", 67, preview="Scam-checking just got a lot easier: Malwarebytes is now in", level=1),
		_node("paragraph", 280, preview="For years, Malwarebytes has protected people by going where they are"),
		_node("paragraph", 35, preview="That's where Malwarebytes comes in."),
		_node("paragraph", 30, preview="And now, with Claude."),
		_node("paragraph", 117, preview="• Check links: Paste a URL you received"),
		_node("paragraph", 110, preview="• Check email: Forward suspicious emails"),
		_node("paragraph", 100, preview="• Check messages: Paste text messages"),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 4


def test_article_landing_skips_tag_list_before_article_heading():
	# Regression: office-watch.com/2026/copilot-agent-mode-... was landing
	# on a 126-char tag row "CoPilot,Microsoft 365,Microsoft Excel,...".
	# It won the hero shortcut because (a) it was >= 100 chars and (b)
	# the article's H1 followed within lookahead. The filter now skips
	# it and the real article body (later, longer) wins via fallback.
	nodes = [
		_node("paragraph", 15, preview="Skip to content"),
		_node("paragraph", 76, preview="Your independent source of Microsoft Office news, tips and help"),
		_node("paragraph", 16, preview="MY EBOOK ACCOUNT"),
		_node("paragraph", 4, preview="WORD"),
		_node("paragraph", 5, preview="EXCEL"),
		_node("paragraph", 10, preview="POWERPOINT"),
		_node("paragraph", 7, preview="OUTLOOK"),
		_node("paragraph", 13, preview="MICROSOFT 365"),
		# The offending tag row — 126 chars, no spaces between commas.
		_node("paragraph", 126, preview="CoPilot,Microsoft 365,Microsoft Excel,Microsoft Office,Micro"),
		_node("heading", 60, preview="Copilot Agent Mode is now the default", level=1),
		# Article body cluster — the right answer.
		_node("paragraph", 280, preview="Microsoft has quietly flipped a major switch. Copilot Agent Mode is now"),
		_node("paragraph", 240, preview="It works very differently from the Copilot you may have ignored"),
	]
	# Tag row at idx 8 must be skipped. Article body cluster at idx 10/11
	# wins via primary cluster check (idx 10's next is also substantial).
	result_idx = web.find_article_landing(_summary_with(nodes))
	assert result_idx == 10, f"expected 10 (article body), got {result_idx} (would be tag row at 8 if filter missed it)"


def test_article_landing_skips_disclaimer_paragraph_before_first_heading():
	# Regression: pcmag.com — a 167-char publisher disclaimer "PCMag
	# editors select and review products..." sits BEFORE the article's
	# H1. Old code returned that disclaimer via the hero shortcut because
	# the H1 was in its lookahead window. The fix: hero shortcut requires
	# that we've already seen a heading earlier in main_nodes. Pre-H1
	# substantial paragraphs are almost always chrome (disclaimer, dek,
	# byline) — let post-H1 article body win via very-substantial or
	# cluster instead.
	nodes = [
		_node("paragraph", 20, preview="Skip to Main Content"),
		_node("paragraph", 18, preview="#AppleGuessingGame"),
		_node("paragraph", 11, preview="Comparisons"),
		_node("paragraph", 6, preview="How-To"),
		_node("paragraph", 5, preview="Deals"),
		_node("paragraph", 25, preview="Maggie: AI Product Finder"),
		# The offending disclaimer — pre-H1 substantial paragraph.
		_node("paragraph", 167, preview="PCMag editors select and review products"),
		# Article H1.
		_node("heading", 79, preview="I've Tested Every Major Antivirus", level=1),
		# Real article body.
		_node("paragraph", 280, preview="I've been testing antivirus software since the 1980s"),
		_node("paragraph", 200, preview="In a recent post, Microsoft effectively slammed that"),
	]
	# Should land on the 280-char body via very-substantial, NOT the
	# 167-char pre-H1 disclaimer.
	assert web.find_article_landing(_summary_with(nodes)) == 8


def test_article_landing_skips_short_ui_label_followed_by_heading():
	# Regression: calendar.google.com had "Google Account: Casey Mathews
	# (help@webf...)" (56 chars) at idx 6, followed by a "Drawer" heading
	# at idx 7. The old hero-pattern code returned idx 6 because of the
	# heading-in-lookahead trick, jumping the user to the account dropdown
	# instead of the first appointment (idx 46, 181 chars). The fix:
	# require the hero shortcut to be triggered only by paragraphs >=100
	# chars. 56-char "candidates" must defer to the largest-paragraph
	# fallback, which correctly picks the 181-char appointment.
	nodes = [
		_node("paragraph", 20, preview="Skip to main content"),
		_node("paragraph", 22, preview="Accessibility Feedback"),
		_node("heading", 8, preview="Calendar", level=1),
		_node("paragraph", 6, preview="Search"),
		_node("paragraph", 13, preview="Settings menu"),
		_node("paragraph", 33, preview="Switch to CalendarSwitch to Tasks"),
		_node("paragraph", 56, preview="Google Account: Casey Mathews"),
		_node("heading", 6, preview="Drawer", level=1),
		# Filler short chunks; the appointment is later.
	] + [_node("paragraph", 10) for _ in range(38)] + [
		_node("paragraph", 181, preview="2:30pm to 4pm appointment"),
	]
	# Largest paragraph is the 181-char appointment at idx 46.
	assert web.find_article_landing(_summary_with(nodes)) == 46


def test_article_landing_returns_only_substantial_paragraph_when_alone():
	# Regression guard: removing the last-node shortcut must not break the
	# legitimate single-substantial-paragraph-as-last-node case.
	nodes = [
		_node("paragraph", 6),
		_node("paragraph", 8),
		_node("paragraph", 120),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 2


def test_article_landing_returns_none_when_nothing_qualifies():
	nodes = [_node("paragraph", 10), _node("paragraph", 15)]
	assert web.find_article_landing(_summary_with(nodes)) is None


# ---------------------------------------------------------------------------
# find_list_landing
# ---------------------------------------------------------------------------

def test_list_landing_picks_first_heading_in_largest_cluster():
	# Two same-level heading clusters, the longer one wins.
	nodes = [
		_node("heading", 30, level=2),
		_node("paragraph", 50),
		_node("heading", 30, level=3),  # Different level — new cluster.
		_node("heading", 30, level=3),
		_node("heading", 30, level=3),
		_node("heading", 30, level=3),
		_node("heading", 30, level=3),
	]
	assert web.find_list_landing(_summary_with(nodes)) == 2


# ---------------------------------------------------------------------------
# find_notice_landing
# ---------------------------------------------------------------------------

def test_notice_landing_first_substantial_paragraph_in_document_order():
	# Classic notice shape: H1 + status sentence.
	nodes = [
		_node("heading", 28, level=1),
		_node("paragraph", 130),
		_node("paragraph", 50),
	]
	assert web.find_notice_landing(_summary_with(nodes)) == 1


def test_notice_landing_picks_substantial_paragraph_before_heading():
	# Regression: bestmidi.com/bg/ — the substantial intro precedes the first
	# detected heading. Old code's "first paragraph after first heading" rule
	# skipped it and landed on a much later footer text. New code picks the
	# first substantial paragraph in document order regardless of headings.
	nodes = [
		_node("paragraph", 20),
		_node("paragraph", 60),   # ← target, before any heading
		_node("paragraph", 12),
		_node("heading", 13, level=2),
		_node("paragraph", 32),
	]
	assert web.find_notice_landing(_summary_with(nodes)) == 1


def test_notice_landing_falls_back_to_heading_when_no_substantial_paragraph():
	nodes = [
		_node("paragraph", 5),
		_node("heading", 20, level=1),
		_node("paragraph", 10),
	]
	assert web.find_notice_landing(_summary_with(nodes)) == 1


def test_notice_landing_returns_zero_on_pathological_node_list():
	# Truly empty content — return idx 0 rather than None so the caller has
	# something to anchor on.
	nodes = [_node("paragraph", 5)]
	assert web.find_notice_landing(_summary_with(nodes)) == 0


def test_notice_landing_returns_none_when_main_nodes_empty():
	assert web.find_notice_landing(_summary_with([])) is None


def test_notice_landing_lands_on_thank_you_page_heading_not_breadcrumb():
	# WebAIM survey-confirmation page (2026-07-20): the status is the H1
	# "Screen Reader User Survey Completed" and the H2 "Thank you for
	# completing our screen reader user survey"; the paragraphs below are
	# follow-up prompts ("share this with others", "check out our services").
	# The page also carries a "You are here: Home > WebAIM Projects > ..."
	# breadcrumb. The old paragraph-first rule landed the user ON the
	# breadcrumb (idx 2) — the first 30+ char paragraph in document order.
	# Now the breadcrumb is chrome, and a heading that owns the status (no
	# status paragraph before the next heading) wins: land on the H1.
	nodes = [
		_node("heading", 35, level=1, preview="Screen Reader User Survey Completed"),
		_node("paragraph", 13, preview="You are here:"),
		_node("paragraph", 50, preview="Home > WebAIM Projects > Screen Reader User Survey"),
		_node("heading", 55, level=2,
		      preview="Thank you for completing our screen reader user survey"),
		_node("paragraph", 159,
		      preview="If you know other screen reader users that might be interested, ple"),
		_node("paragraph", 107,
		      preview="While you're here, please check out some of the services and resour"),
	]
	assert web.find_notice_landing(_summary_with(nodes)) == 0


def test_notice_landing_title_heading_still_yields_to_status_sentence():
	# The heading-owns-status rule must NOT regress the closed-form shape:
	# a generic title heading with the real status sentence beneath it still
	# lands on the sentence, not the title. (Google Forms "no longer
	# accepting responses" under an H1 that repeats the form's name.)
	nodes = [
		_node("heading", 18, level=1, preview="Contact Us"),
		_node("paragraph", 45, preview="This form is no longer accepting responses."),
	]
	assert web.find_notice_landing(_summary_with(nodes)) == 1


def test_breadcrumb_is_chrome_but_prose_with_one_chevron_is_not():
	# The breadcrumb filter keys on TWO spaced chevrons (three segments);
	# ordinary prose containing a single " > " must survive as a landing.
	crumb = _node("paragraph", 50,
	              preview="Home > WebAIM Projects > Screen Reader User Survey")
	you_are_here = _node("paragraph", 40, preview="You are here: Home > Projects")
	prose = _node("paragraph", 58,
	              preview="The rule fires when x > y in the comparison step.")
	assert web._is_chrome_paragraph(crumb) is True
	assert web._is_chrome_paragraph(you_are_here) is True
	assert web._is_chrome_paragraph(prose) is False


# ---------------------------------------------------------------------------
# find_form_landing
# ---------------------------------------------------------------------------

def test_form_landing_picks_first_heading():
	# Google Form "Fesshole" shape: form title heading + a few form inputs.
	# Land on the title so the user hears "Fesshole - Anonymous Confessions"
	# and can arrow forward to the description and fields.
	nodes = [
		_node("paragraph", 20, preview="Skip to main content"),
		_node("heading", 33, preview="Fesshole - Anonymous Confessions", level=1),
		_node("paragraph", 18, preview="Submit your story"),
		_node("paragraph", 5, preview="Field"),
	]
	assert web.find_form_landing(_summary_with(nodes)) == 1


def test_form_landing_falls_back_to_description_when_no_heading():
	# Some forms render the title as a styled div (no real heading role).
	# Fall back to the first substantive paragraph — that's the description.
	nodes = [
		_node("paragraph", 18, preview="Submit your story"),
		_node("paragraph", 60, preview="Tell us your most embarrassing moment in 1000 chars or less"),
		_node("paragraph", 5, preview="Name"),
	]
	assert web.find_form_landing(_summary_with(nodes)) == 1


def test_form_landing_last_resort_first_node():
	# All nodes are tiny — no heading, no substantive paragraph. Return
	# idx 0 so the user at least lands somewhere instead of nowhere.
	nodes = [
		_node("paragraph", 5, preview="Name"),
		_node("paragraph", 5, preview="Email"),
	]
	assert web.find_form_landing(_summary_with(nodes)) == 0


def test_form_landing_returns_none_on_empty():
	assert web.find_form_landing(_summary_with([])) is None


# ---------------------------------------------------------------------------
# find_key_result_landing
# ---------------------------------------------------------------------------

def test_key_result_landing_returns_label_index():
	# Pattern at lead position — return the label's index so arrowing
	# forward speaks the value.
	nodes = [
		_node("paragraph", 8),
		_node("paragraph", 22, preview="Your Internet speed is"),  # 1: label
		_node("paragraph", 3, preview="170"),                       # 2: value
		_node("paragraph", 4, preview="Mbps"),                      # 3: unit
	]
	assert web.find_key_result_landing(_summary_with(nodes)) == 1


def test_key_result_landing_with_implicit_unit():
	nodes = [
		_node("paragraph", 13, preview="Battery level"),  # 0: label
		_node("paragraph", 3, preview="85%"),             # 1: value (implicit unit)
	]
	assert web.find_key_result_landing(_summary_with(nodes)) == 0


def test_key_result_landing_returns_none_when_no_pattern():
	nodes = [
		_node("paragraph", 250),
		_node("paragraph", 220),
	]
	assert web.find_key_result_landing(_summary_with(nodes)) is None


# ---------------------------------------------------------------------------
# find_next_heading_landing — Phase 1.5 Z-sequence
# ---------------------------------------------------------------------------

def test_next_heading_returns_first_heading_after_idx():
	# Initial landing is the first paragraph (idx 0). Second Z press
	# should advance to the next H2 (idx 2).
	nodes = [
		_node("paragraph", 200, preview="intro paragraph"),
		_node("paragraph", 150, preview="continuation"),
		_node("heading", 0, level=2, preview="Second section"),
		_node("paragraph", 180, preview="body of second section"),
		_node("heading", 0, level=2, preview="Third section"),
	]
	assert web.find_next_heading_landing(_summary_with(nodes), 0) == 2


def test_next_heading_skips_paragraphs_between_headings():
	nodes = [
		_node("heading", 0, level=1, preview="Title"),
		_node("paragraph", 100),
		_node("paragraph", 80),
		_node("paragraph", 90),
		_node("heading", 0, level=2, preview="Next section"),
	]
	assert web.find_next_heading_landing(_summary_with(nodes), 0) == 4


def test_next_heading_returns_none_at_end():
	# Caller is already at the last heading — no further heading exists.
	nodes = [
		_node("heading", 0, level=1, preview="First"),
		_node("paragraph", 200),
		_node("heading", 0, level=2, preview="Last"),
		_node("paragraph", 150),
	]
	assert web.find_next_heading_landing(_summary_with(nodes), 2) is None


def test_next_heading_returns_none_when_no_headings():
	# Page is all paragraphs — sequence advance has nowhere to go.
	nodes = [
		_node("paragraph", 200),
		_node("paragraph", 150),
		_node("paragraph", 180),
	]
	assert web.find_next_heading_landing(_summary_with(nodes), 0) is None


def test_next_heading_strict_greater_than_after_idx():
	# When after_idx points at a heading, do not return that same index —
	# the user is already there.
	nodes = [
		_node("heading", 0, level=2, preview="A"),
		_node("paragraph", 200),
		_node("heading", 0, level=2, preview="B"),
	]
	assert web.find_next_heading_landing(_summary_with(nodes), 0) == 2


def test_next_heading_returns_none_when_next_heading_is_too_far():
	# Fox21 case: short article body (~14 paragraphs) followed by a long
	# gap of paragraphs/cards/links and the next heading is a sidebar
	# widget hundreds of nodes away. The Z-sequence must stop, not walk
	# into the sidebar.
	body = [_node("paragraph", 200) for _ in range(100)]
	nodes = body + [_node("heading", 0, level=3, preview="Sidebar widget")]
	# Default max_gap=30 should stop at the article body's edge.
	assert web.find_next_heading_landing(_summary_with(nodes), 0) is None


def test_next_heading_respects_custom_max_gap():
	# Caller can opt for a stricter or looser gap.
	body = [_node("paragraph", 200) for _ in range(10)]
	nodes = body + [_node("heading", 0, level=3, preview="Next section")]
	# With max_gap=5 the heading at idx 10 is unreachable (gap=10).
	assert web.find_next_heading_landing(_summary_with(nodes), 0, max_gap=5) is None
	# With max_gap=15 the same heading is reachable.
	assert web.find_next_heading_landing(_summary_with(nodes), 0, max_gap=15) == 10


# ---------------------------------------------------------------------------
# Share-link payload filter — Fox21 social-share button URL strings
# ---------------------------------------------------------------------------

def test_share_link_payload_url_equals_pattern():
	# LinkedIn "share-offsite?url=https%3A%2F%2F..." text exposed by
	# accessibility tooling. Reads as a paragraph but is really a URL.
	share = (
		"share-offsite url=https%3A%2F%2Fwww.fox21news.com%2Fnews%2F"
		"retro-pizza-hut-revival-see-which-locations-are-returning-to-"
		"the-1990s-aesthetic"
	)
	assert web._looks_like_share_link_payload(share) is True


def test_share_link_payload_dense_url_encoding():
	# Even without "url=", a string with 3+ URL-encoded triplets is
	# overwhelmingly a URL.
	encoded = "post%3A%2F%2Fid%3D42%26type%3Dshare"
	assert web._looks_like_share_link_payload(encoded) is True


def test_share_link_payload_negatives():
	# Normal prose. A paragraph that mentions one URL is still prose.
	assert web._looks_like_share_link_payload("") is False
	assert web._looks_like_share_link_payload("Just a normal sentence.") is False
	assert web._looks_like_share_link_payload(
		"For more info, see https://example.com which lists details."
	) is False
	# Single isolated %20 in an academic context: still prose.
	assert web._looks_like_share_link_payload(
		"Encoded as %20 in the URL, the space character is..."
	) is False


def test_article_landing_directory_page_picks_first_heading():
	# Regression: montgomeryprobatecourtal.gov/resources/all-probate-forms.
	# A small directory page (25 main_nodes) — title heading near the top,
	# short link/list paragraphs through the body, a 78-char Share &
	# Bookmark widget instructional paragraph (which the existing
	# accessibility-instruction filter must catch), and the only other
	# substantial paragraph is the courthouse address at the bottom.
	# Without filtering Share & Bookmark, substantial_count is 2 and the
	# directory-page redirect would not fire. WITH the filter,
	# substantial_count drops to 1 and the redirect lands at the heading.
	nodes = [
		_node("paragraph", 20, preview="Skip to Main Content"),
		_node("paragraph", 18, preview="Home ProbateOffice"),
		_node("paragraph", 19, preview="Click to open About"),
		_node("paragraph", 17, preview="Probate Resources"),
		_node("paragraph", 25, preview="Records & Recording Forms"),
		_node("paragraph", 26, preview="Internet Tag/Boat Renewals"),
		_node("paragraph", 10, preview="Contact Us"),
		_node("heading", 17, level=1, preview="All Probate Forms"),  # idx 7
		# Share & Bookmark widget — accessibility-instruction text. Must be
		# filtered out by _looks_like_accessibility_instructions.
		_node("paragraph", 78,
			preview="Share & Bookmark, Press Enter to show all options, press Tab"),
		_node("paragraph", 22, preview="Adoption Forms"),
		_node("paragraph", 20, preview="Will Forms"),
		_node("paragraph", 28, preview="Estate Administration Forms"),
		_node("paragraph", 22, preview="Guardianship Forms"),
		_node("paragraph", 21, preview="Conservatorship Forms"),
		_node("paragraph", 18, preview="Probate Court Fees"),
		_node("paragraph", 22, preview="Filing Instructions"),
		_node("paragraph", 17, preview="Records Request"),
		_node("paragraph", 12, preview="Office Hours"),
		_node("paragraph", 14, preview="Phone Numbers"),
		_node("paragraph", 13, preview="Email Contact"),
		_node("paragraph", 18, preview="Holiday Schedule"),
		# The courthouse address — the only OTHER ≥50-char paragraph.
		_node("paragraph", 112,
			preview="|Courthouse Annex III, 101 S Lawrence St. Montgomery, AL 361"),
		_node("paragraph", 30, preview="Office hours: 8am to 5pm"),
		_node("paragraph", 15, preview="© 2026 County"),
		_node("paragraph", 18, preview="Site by Webmaster"),
	]
	# Expected: idx 7 (heading "All Probate Forms"), not 8 (Share &
	# Bookmark) and not 22 (courthouse address).
	assert web.find_article_landing(_summary_with(nodes)) == 7


def test_share_and_bookmark_widget_text_is_filtered():
	# Direct unit test for the accessibility-instruction filter.
	assert web._looks_like_accessibility_instructions(
		"Share & Bookmark, Press Enter to show all options, press Tab go to next option"
	) is True
	assert web._looks_like_accessibility_instructions(
		"Press Tab to navigate between fields"
	) is True
	# Negative: real prose that happens to mention these words.
	assert web._looks_like_accessibility_instructions(
		"The bookmark contains a tab character."
	) is False


def test_content_section_matcher_ignores_long_headings():
	# Thurrott bug: "No additional security features included" (38 chars)
	# matched "features" as a substring and dispatched the content-section
	# landing to look past this heading. Real "Features" / "Description" /
	# "Overview" headings are short — restrict the matcher to ≤25 chars.
	nodes = [
		_node("heading", 30, level=1, preview="2026 Security Checkup"),
		# Real article lede — should win.
		_node("paragraph", 341,
			preview="Sometimes I'll see a terrible headline in a news feed"),
		_node("paragraph", 120, preview="And holy crap, this is among the worst"),
		# A long sentence-style heading that contains the substring "features".
		_node("heading", 38, level=2,
			preview="No additional security features included"),
		# Body paragraph after the wrongly-matched heading.
		_node("paragraph", 164,
			preview="And more … Microsoft's post warns that"),
	]
	# Expected: idx 1 (the real lede), via the very-substantial rule.
	# NOT idx 4 (the post-section body) which would mean the matcher
	# misfired on "features".
	assert web.find_article_landing(_summary_with(nodes)) == 1


def test_content_section_matcher_still_works_for_short_headings():
	# Guard: legitimate short product/recipe section headings should
	# still match. "Description" alone, "About this item", etc.
	nodes = [
		_node("paragraph", 20, preview="Skip to content"),
		_node("heading", 60, level=1, preview="Some Product Name"),
		_node("paragraph", 80, preview="Marketing tagline that is just chrome"),
		_node("heading", 11, level=2, preview="Description"),
		_node("paragraph", 220,
			preview="The real product description that we want to land on"),
	]
	# Expected: idx 4 (real description paragraph), via content-section match.
	assert web.find_article_landing(_summary_with(nodes)) == 4


def test_article_landing_prefers_longer_neighbor_when_first_is_teaser():
	# CNET case: an 82-char teaser sits right after the H1, followed by
	# a 209-char narrative opener. The teaser is too "thin" to be where
	# a reader wants to start. Prefer the longer neighbor.
	nodes = [
		_node("paragraph", 10, preview="YOUR GUIDE"),
		_node("heading", 51, level=1, preview="MacOS Keyboard Shortcuts Make Typing"),
		_node("paragraph", 82,
			preview="MacOS keyboard shortcuts can be a huge time saver, once you"),
		_node("paragraph", 209,
			preview="When I first started using an iMac all the way back in 2008"),
		_node("paragraph", 72, preview="If you think you already know them all, read on."),
	]
	# Expected: idx 3 (the 209-char narrative opener), not idx 2 (teaser).
	assert web.find_article_landing(_summary_with(nodes)) == 3


def test_article_landing_does_not_skip_substantial_first_paragraph():
	# Guard: when the first cluster paragraph is already ≥100 chars, do
	# not switch to a longer neighbor. Wikipedia ledes commonly run
	# 200-500 chars; we want to land on the first one.
	nodes = [
		_node("heading", 20, level=1, preview="Article Title"),
		_node("paragraph", 280, preview="A substantial lede paragraph that is the real start"),
		_node("paragraph", 420, preview="An even longer second paragraph continuing the lede"),
	]
	# Expected: idx 1 (the first substantial paragraph), unchanged.
	assert web.find_article_landing(_summary_with(nodes)) == 1


# ---------------------------------------------------------------------------
# find_next_content_landing — Z scan-from-cursor
# ---------------------------------------------------------------------------

def test_next_content_skips_headings():
	# Z is meant to advance through substantial content paragraphs, NOT
	# headings (NVDA's H key already handles those). A heading in the
	# scan range should be skipped.
	nodes = [
		_node("paragraph", 200, preview="Intro paragraph"),
		_node("heading", 20, level=2, preview="Section heading"),
		_node("paragraph", 180, preview="Body of the section"),
	]
	assert web.find_next_content_landing(_summary_with(nodes), 0) == 2


def test_next_content_skips_chrome_paragraphs():
	# Tag list, share link, accessibility instruction text all skipped.
	nodes = [
		_node("paragraph", 200, preview="The intro paragraph"),
		_node("paragraph", 126,
			preview="CoPilot,Microsoft 365,Microsoft Excel,Microsoft Office,Mic"),
		_node("paragraph", 78,
			preview="Share & Bookmark, Press Enter to show all options, press Tab"),
		_node("paragraph", 61,
			preview="Free viewers are required for some of the attached documents"),
		_node("paragraph", 180, preview="The body of the next section"),
	]
	# All three chrome paragraphs at idx 1, 2, 3 must be skipped. Landing
	# at idx 4 (the real body paragraph).
	assert web.find_next_content_landing(_summary_with(nodes), 0) == 4


def test_next_content_returns_none_when_nothing_below():
	# Cursor at the last substantial paragraph — nothing else to land on.
	nodes = [
		_node("paragraph", 200, preview="Last body paragraph"),
		_node("heading", 20, level=2, preview="No content past this"),
		_node("paragraph", 30, preview="Short footer line"),
	]
	assert web.find_next_content_landing(_summary_with(nodes), 0) is None


def test_pdf_viewer_disclaimer_is_filtered():
	# Government / municipal sites that link to PDF forms often carry a
	# disclaimer paragraph. Montgomery probate forms page is the canonical
	# case — the disclaimer is 61 chars and was sneaking past the filter,
	# preventing the directory-page redirect from firing.
	assert web._looks_like_accessibility_instructions(
		"Free viewers are required for some of the attached documents."
	) is True
	assert web._looks_like_accessibility_instructions(
		"You may need Adobe Reader to view these forms."
	) is True
	# Negative: prose mentioning PDFs without the disclaimer phrasing.
	assert web._looks_like_accessibility_instructions(
		"The library catalog is available as a PDF download."
	) is False


def test_article_landing_short_page_with_real_body_still_picks_paragraph():
	# Guard: don't redirect a SHORT article to its heading just because the
	# directory check is in town. A short page with a real body paragraph
	# right after the heading should still land at the paragraph.
	nodes = [
		_node("paragraph", 15, preview="Skip to content"),
		_node("paragraph", 10, preview="Nav"),
		_node("heading", 30, level=1, preview="Article Title"),
		_node("paragraph", 250, preview="The body of the article starts here, plenty of words"),
		_node("paragraph", 200, preview="And here's the second paragraph also substantial"),
	]
	# The heading is at idx 2, the substantial paragraph at idx 3.
	# Gap is only 1, NOT > 5 — directory redirect should not trigger.
	# Cluster of two substantial paragraphs wins on its own anyway.
	assert web.find_article_landing(_summary_with(nodes)) == 3


def test_article_landing_skips_share_link_payload():
	# Fox21 case: the social-share LinkedIn URL string is the FIRST
	# substantial paragraph in main_nodes. Without the filter it would
	# win the article-landing cascade. With the filter, the next real
	# body paragraph wins.
	nodes = [
		_node("paragraph", 16, preview="Skip to content"),
		_node("paragraph", 8, preview="News▾"),
		# The offending share-link payload.
		_node("paragraph", 220,
			preview="share-offsite url=https%3A%2F%2Fwww.fox21news.com%2Fnews%2Fretro-pizza-hut"),
		# Real article body.
		_node("paragraph", 205,
			preview="LOUISVILLE, Ky. (WDKY) — Foodies and families looking for"),
		_node("paragraph", 180, preview="The chain announced a phased rollout..."),
	]
	# Expected: idx=3 (article lede), not idx=2 (share-link payload).
	assert web.find_article_landing(_summary_with(nodes)) == 3


# ---------------------------------------------------------------------------
# Legal footer boilerplate (Zoom webinar registration regression)
# ---------------------------------------------------------------------------
# us02web.zoom.us/webinar/register/... at documentLoadComplete is an empty
# SPA shell: header links, a language menu, and the footer. The ONLY
# paragraph clearing the 50-char substantial bar is the copyright line, so
# the addon classified ARTICLE and spoke "Copyright (c)2026 Zoom Video
# Communications, Inc. All rights reserved." as if it were the page content.
# Landing on legal boilerplate must never happen; with no landing, the
# caller's 1500 ms retry re-runs detection against the hydrated page.

_ZOOM_COPYRIGHT = "Copyright ©2026 Zoom Video Communications, Inc. All rights reserved."
_ZOOM_PRIVACY_ROW = "Privacy & Legal Policies Do Not Sell My Personal Information Cookie Preferences"


def test_boilerplate_detector_positives_and_negatives():
	assert web._looks_like_legal_boilerplate(_ZOOM_COPYRIGHT)
	assert web._looks_like_legal_boilerplate("© 2026 Example Corp")
	assert web._looks_like_legal_boilerplate("Copyright 2019 Acme Inc.")
	assert web._looks_like_legal_boilerplate("Copyright (c) 2026 Acme Inc.")
	assert web._looks_like_legal_boilerplate(_ZOOM_PRIVACY_ROW)
	assert web._looks_like_legal_boilerplate("Do not sell or share my personal information")
	# Prose ABOUT copyright must not match — no year adjacent to the word.
	assert not web._looks_like_legal_boilerplate(
		"The copyright office ruled in 2026 that AI-generated works need human authorship."
	)
	# "rights are reserved" is not the boilerplate phrase.
	assert not web._looks_like_legal_boilerplate("All rights are reserved for members of the guild.")
	assert not web._looks_like_legal_boilerplate("")


def test_purchase_consent_line_is_legal_boilerplate():
	# store.payproglobal.com/checkout (2026-07-17): the checkout's
	# "By placing your order, you agree to our Terms and Conditions..."
	# consent paragraph is 263 chars of sentence-ending prose sitting next
	# to the Submit button, so it won the article cascade's very-substantial
	# gate and the user landed in the legalese. Purchase/terms-consent
	# wording is contract-formula language — as enumerable as "All rights
	# reserved". Note the real page uses non-breaking spaces inside
	# "Terms\xa0and\xa0Conditions"; the detector must tolerate them.
	assert web._looks_like_legal_boilerplate(
		"By placing your order, you agree to our Terms\xa0and\xa0Conditions and "
		"Privacy\xa0Policy and acknowledge that you are purchasing from PayPro "
		"Global (PayPro Global, Inc., PayPro Europe Limited, PPG DIGITAL Sp. z "
		"o.o. or PayPro U.S. Inc.), an authorized e-Commerce reseller."
	)
	assert web._looks_like_legal_boilerplate(
		"By clicking Submit, you agree to the Terms of Service."
	)
	assert web._looks_like_legal_boilerplate(
		"By creating an account you consent to our Privacy Policy."
	)
	# Second-person consent is required — reported speech about other
	# parties agreeing is ordinary prose.
	assert not web._looks_like_legal_boilerplate(
		"The two sides did not agree to the terms of the ceasefire until dawn."
	)
	# And the consent verb must target the legal terms — shopping advice
	# that happens to open with "By placing your order" is prose.
	assert not web._looks_like_legal_boilerplate(
		"By placing your order early, you can avoid holiday shipping delays."
	)


def test_article_landing_returns_none_on_zoom_shell():
	# The pre-hydration Zoom shell: short header links + the copyright line.
	# No landing may be produced — None triggers the caller's retry.
	nodes = [
		_node("paragraph", 20, preview="Skip to Main Content"),
		_node("paragraph", 22, preview="Accessibility Overview"),
		_node("paragraph", 7, preview="Support"),
		_node("paragraph", 7, preview="English"),
		_node("paragraph", len(_ZOOM_COPYRIGHT), preview=_ZOOM_COPYRIGHT),
		_node("paragraph", len(_ZOOM_PRIVACY_ROW), preview=_ZOOM_PRIVACY_ROW),
	]
	assert web.find_article_landing(_summary_with(nodes)) is None


def test_article_landing_skips_boilerplate_via_flag_when_preview_truncated():
	# Production path: text_preview is cut at 60 chars, which can truncate
	# the detector's signal (the CCPA phrase in the Zoom privacy row is cut
	# mid-word). The walk-time is_boilerplate flag, computed over the full
	# text, must carry the skip on its own.
	footer = cls.MainNode(
		kind="paragraph",
		text_length=80,
		text_preview="Privacy & Legal Policies Do Not Sell My Personal Informatio",
		is_boilerplate=True,
	)
	body = _node("paragraph", 250, preview="Real article body paragraph that is long enough to win immediately.")
	nodes = [footer, body]
	assert web.find_article_landing(_summary_with(nodes)) == 1


def test_largest_paragraph_fallback_never_picks_copyright():
	# Even when the copyright line is the LARGEST substantial paragraph on
	# the page, the fallback must not pick it.
	nodes = [
		_node("heading", 30, level=1, preview="Site title"),
		_node("paragraph", 40, preview="Too short to be substantial."),
		_node("paragraph", len(_ZOOM_COPYRIGHT), preview=_ZOOM_COPYRIGHT),
	]
	assert web.find_article_landing(_summary_with(nodes)) is None


def test_notice_landing_skips_copyright_line():
	# A small status page whose first 30+ char paragraph is the footer
	# copyright: the status sentence, not the copyright, is the landing.
	nodes = [
		_node("paragraph", len(_ZOOM_COPYRIGHT), preview=_ZOOM_COPYRIGHT),
		_node("paragraph", 45, preview="This form is no longer accepting responses."),
	]
	assert web.find_notice_landing(_summary_with(nodes)) == 1


def test_z_scan_skips_copyright_footer():
	# Z forward scan from the body must not offer the copyright as the
	# "next content paragraph" — with nothing real below, it returns None
	# so the user hears "Nothing else to land on."
	nodes = [
		_node("paragraph", 250, preview="Real article body paragraph long enough to be the initial landing."),
		_node("paragraph", len(_ZOOM_COPYRIGHT), preview=_ZOOM_COPYRIGHT),
	]
	assert web.find_next_content_landing(_summary_with(nodes), 0) is None


# ---------------------------------------------------------------------------
# form_wants_browse_landing (rich-preamble form rule, Zoom registration)
# ---------------------------------------------------------------------------
# The hydrated Zoom webinar registration page classifies as FORM (7 inputs),
# but the announce-title-then-focus-first-input treatment dropped the user in
# the middle of the form, past the title and a ~2000-char description. A form
# page carrying a very-substantial descriptive paragraph gets a browse-mode
# landing on its title instead; bare forms keep the focus behavior.

def test_form_with_rich_description_wants_browse_landing():
	nodes = [
		_node("heading", 81, level=1, preview="AI as Assistive Technology: A Practical Stack for Entrepren"),
		_node("heading", 20, level=2, preview="Webinar Registration"),
		_node("paragraph", 1958, preview="Whether you're starting your business or scaling one, AI is"),
	]
	assert web.form_wants_browse_landing(_summary_with(nodes)) is True
	# And the landing itself is the form title (first heading).
	assert web.find_form_landing(_summary_with(nodes)) == 0


def test_bare_form_keeps_focus_landing():
	# Google-Forms-style: title + shortish question labels, no description
	# paragraph clearing the 200-char bar.
	nodes = [
		_node("heading", 25, level=1, preview="Vendor fair signup"),
		_node("paragraph", 112, preview="If you would like to request an accommodation to participat"),
		_node("paragraph", 61, preview="I would like to subscribe to the small business mailing lis"),
	]
	assert web.form_wants_browse_landing(_summary_with(nodes)) is False


def test_headingless_form_lands_on_sentence_not_slogan():
	# store.payproglobal.com/checkout, third round (2026-07-17): the page
	# has NO headings, so find_form_landing fell to its paragraph fallback,
	# and the first >= 30 char paragraph is the vendor's slogan under the
	# logo — "exponential growth in file management productivity", a
	# fragment with no terminal punctuation. The user landed there instead
	# of on the order summary. A form's description reads like a sentence;
	# header furniture doesn't. The sentence-ending product description
	# below "You're Buying" must win.
	nodes = [
		_node("paragraph", 8, preview="xplorer²"),
		_node("paragraph", 50, preview="exponential growth in file management productivity"),
		_node("paragraph", 13, preview="You're Buying"),
		_node("paragraph", 108, ends_sentence=True,
			preview="xplorer² professional  Explore, preview,"),
		_node("paragraph", 42, preview="Volume discount available for this produ"),
	]
	assert web.find_form_landing(cls.TreeSummary(main_nodes=nodes)) == 3
	# A fragments-only form (nothing ends like a sentence) keeps the old
	# first-substantive landing — no form loses its landing to this rule.
	frag = [
		_node("paragraph", 8, preview="Logo"),
		_node("paragraph", 45, preview="Just labels and fragments with no punctuation"),
	]
	assert web.find_form_landing(cls.TreeSummary(main_nodes=frag)) == 1


def test_truncated_walk_takes_browse_landing_not_focus_jump():
	# store.payproglobal.com/checkout, second visit (2026-07-17): a slow
	# hydrating refresh hit the 2.0 s walk budget at 34 nodes, so the
	# 200+ char preamble paragraphs near the Submit button were never
	# walked. "No rich preamble" then selected the bare-form path and
	# keyboard focus jumped to the Quantity field — while the earlier
	# fast walk of the SAME page (47 nodes) landed in browse mode at the
	# top of the order. A truncated walk cannot prove the preamble is
	# absent, and the landing must not depend on walk timing: truncation
	# takes the browse landing, the branch that never moves focus.
	nodes = [
		_node("paragraph", 8, preview="xplorer²"),
		_node("paragraph", 50, preview="exponential growth in file management productivity"),
		_node("paragraph", 13, preview="You're Buying"),
		_node("paragraph", 108, preview="xplorer² professional  Explore, preview,"),
	]
	tree = cls.TreeSummary(main_nodes=nodes, walk_truncated=True)
	assert web.form_wants_browse_landing(tree) is True
	# Same shape with a complete walk stays a bare form.
	complete = cls.TreeSummary(main_nodes=nodes, walk_truncated=False)
	assert web.form_wants_browse_landing(complete) is False


def test_form_rich_preamble_ignores_boilerplate_and_chrome():
	# A long copyright/legal paragraph must not count as a rich preamble.
	footer = cls.MainNode(
		kind="paragraph",
		text_length=260,
		text_preview="Copyright ©2026 Example Corp. All rights reserved.",
		is_boilerplate=True,
	)
	nodes = [_node("heading", 25, level=1, preview="Sign in"), footer]
	assert web.form_wants_browse_landing(_summary_with(nodes)) is False


def test_collapsed_form_shell_lands_on_heading_not_lone_question_label():
	# Signed-in Zoom webinar registration (from the 2026-07-06 debug log):
	# 36 main_nodes, description and date hidden in CLOSED accordions (so
	# their text is not in the buffer), only heading is the "Webinar
	# Registration" H2 at idx 5, and the ONLY substantial paragraph is the
	# 52-char "Do you consider yourself a person with a disability?" label
	# at idx 24, mid-form. The directory-page redirect must land on the
	# heading, not the lone question label. (Node cap widened 30 -> 40 for
	# this page.)
	nodes = []
	nodes.append(_node("paragraph", 7, preview="Loading"))                     # 0
	nodes.append(_node("paragraph", 22, preview="Accessibility overview"))     # 1
	nodes.append(_node("paragraph", 7, preview="Support"))                     # 2
	nodes.append(_node("paragraph", 11, preview="Date & Time"))                # 3
	nodes.append(_node("paragraph", 11, preview="Description"))                # 4
	nodes.append(_node("heading", 20, level=2, preview="Webinar Registration"))# 5
	nodes.append(_node("paragraph", 5, preview="Casey"))                       # 6
	nodes.append(_node("paragraph", 7, preview="Mathews"))                     # 7
	# Short field labels / values filling out the form region (idx 8-23).
	for i in range(8, 24):
		nodes.append(_node("paragraph", 18, preview=f"Field label {i}"))
	nodes.append(_node("paragraph", 52, preview="Do you consider yourself a person with a disability?"))  # 24
	for i in range(25, 34):
		nodes.append(_node("paragraph", 15, preview=f"More labels {i}"))
	nodes.append(cls.MainNode(                                                 # 34
		kind="paragraph", text_length=68,
		text_preview="Copyright ©2026 Zoom Video Communications, Inc. Al",
		is_boilerplate=True,
	))
	nodes.append(_node("paragraph", 24, preview="Privacy & Legal Policies"))   # 35
	assert len(nodes) == 36
	assert web.find_article_landing(_summary_with(nodes)) == 5


def test_lede_after_title_survives_an_embedded_video_block():
	# MacRumors "Apple Just Increased Prices" (2026-07-20 report). The lede
	# sits at idx 2, two nodes under the H1, and is 79 chars — too short for
	# VERY_SUBSTANTIAL (200) and too short for the hero gate (100). A YouTube
	# embed follows it, so the chunks at idx 3-8 are player chrome and the
	# cluster gate finds no substantial neighbour. The cascade therefore
	# walked past the lede entirely and landed on the embed's own
	# "Subscribe to the MacRumors YouTube channel" line at idx 9, which DOES
	# cluster with the 149-char paragraph after it.
	nodes = [
		_node("heading", 56, level=1,
			preview="Apple Just Increased Prices on MacBooks,"),                 # 0
		_node("paragraph", 54,
			preview="Thursday June 25, 2026 5:44 am PDT by Hartley Char"),       # 1
		_node("paragraph", 79, ends_sentence=True,
			preview="Apple today dramatically increased device prices a"),       # 2
		_node("paragraph", 20, preview="YouTube Video Player"),                  # 3
		_node("paragraph", 34, preview="Apple Just Raised Prices... By A LOT"),   # 4
		_node("paragraph", 9, preview="MacRumors"),                              # 5
		_node("paragraph", 25, preview="MacRumors648K subscribers"),             # 6
		_node("paragraph", 11, preview="Watch later"),                           # 7
		_node("paragraph", 5, preview="Share"),                                  # 8
		_node("paragraph", 59, ends_sentence=True,
			preview="Subscribe to the MacRumors YouTube channel for mor"),       # 9
		_node("paragraph", 149,
			preview="After temporarily taking it down earlier today, Ap"),       # 10
	]
	assert web.find_article_landing(_summary_with(nodes)) == 2


def test_lede_after_title_does_not_override_a_real_cluster():
	# Guard on the gate above: when the paragraph under the H1 IS followed by
	# a substantial paragraph, the ordinary cluster gate already handles the
	# page (including teaser-skip), so the new gate must decline and leave
	# the CNET teaser behavior untouched.
	nodes = [
		_node("heading", 51, level=1, preview="MacOS Keyboard Shortcuts Make Typing"),
		_node("paragraph", 82, ends_sentence=True,
			preview="MacOS keyboard shortcuts can be a huge time saver."),
		_node("paragraph", 209,
			preview="When I first started using an iMac all the way back in 2008"),
		_node("paragraph", 72, preview="If you think you already know them all, read on."),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 2


def test_lede_after_title_ignores_a_non_h1_first_heading():
	# Guard on _find_title_lede_landing: the "slot under the title" only means
	# anything when the heading IS the page title. On an unscoped tree the
	# first heading is routinely site chrome (a sidebar or widget H2), and the
	# sentence-ending paragraph beneath it is a cookie notice or a widget
	# blurb, not a lede. Requiring level 1 makes the gate decline here so the
	# very-substantial rule can claim the real body paragraph.
	nodes = [
		_node("heading", 9, level=2, preview="Main menu"),
		_node("paragraph", 62, ends_sentence=True,
			preview="We use cookies to improve your experience on this site."),
		_node("paragraph", 12, preview="Learn more"),
		_node("heading", 30, level=1, preview="The Actual Article Headline"),
		_node("paragraph", 300, ends_sentence=True,
			preview="The real body of the story begins right here and runs on"),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 4


def test_lede_after_title_does_not_reach_past_its_lookahead():
	# Guard on _find_title_lede_landing: the lede sits directly under the H1,
	# past a byline at most. A sentence-ending paragraph eight nodes down is
	# not "the slot under the title" — it is a caption, a promo, or a pull
	# quote, and claiming it would be a guess. The gate must decline and let
	# the very-substantial rule take the real body paragraph.
	nodes = [
		_node("heading", 30, level=1, preview="The Article Headline"),
		_node("paragraph", 20, preview="Share this story"),
		_node("paragraph", 15, preview="Photo gallery"),
		_node("paragraph", 18, preview="Advertisement"),
		_node("paragraph", 22, preview="Sponsored content"),
		_node("paragraph", 19, preview="Related stories"),
		_node("paragraph", 64, ends_sentence=True,
			preview="Sign up for our newsletter to get the day's top stories."),
		_node("paragraph", 11, preview="Subscribe"),
		_node("paragraph", 260, ends_sentence=True,
			preview="The story itself finally begins in this paragraph and"),
		# A second body paragraph, so the lead-section gate declines ("exactly
		# one" candidate is its load-bearing condition) and the title-lede
		# lookahead is genuinely the thing under test here.
		_node("paragraph", 180, ends_sentence=True,
			preview="And the story continues in a second body paragraph"),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 8


def test_lede_after_title_stops_at_an_intervening_heading():
	# Guard on _find_title_lede_landing: the gate's whole claim is that the
	# paragraph occupies the slot directly under the page title. Once a second
	# heading intervenes, that slot is closed — whatever follows belongs to the
	# new section, not to the title — so the gate must stop rather than scan
	# through into a widget's blurb.
	nodes = [
		_node("heading", 30, level=1, preview="The Article Headline"),
		_node("heading", 10, level=2, preview="Newsletter"),
		_node("paragraph", 60, ends_sentence=True,
			preview="Get our best stories delivered to you every morning."),
		_node("paragraph", 12, preview="Sign up"),
		_node("paragraph", 250, ends_sentence=True,
			preview="The actual story text starts here and keeps going for"),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 4


def test_lede_after_title_declines_on_a_dek_above_the_byline_block():
	# iinteractive.com/resources/blog/read-only (2026-07-22 report). The blog
	# uses a magazine layout: headline, then a DEK (standfirst summary), then
	# the author-meta block (name, date, read-time), then the body. The dek is
	# sentence-ending prose sitting directly under the H1 with a short byline
	# beneath it, so _find_title_lede_landing grabbed it exactly like the
	# MacRumors lede -- but locked decision #7 says skip the dek and land on the
	# first body paragraph. The read-time / date meta line between the dek and
	# the body is the tell: the candidate sits ABOVE the meta block, so it is
	# the dek, not the lede. The gate must decline and let the 395-char body
	# (idx 6) win via the very-substantial rule.
	nodes = [
		_node("paragraph", 11, preview="Development"),                          # 0
		_node("heading", 32, level=1,
			preview="Read Only. Read Only. Read Only."),                        # 1
		_node("paragraph", 149, ends_sentence=True,
			preview="How working with a blind client on a Power Automate project "),  # 2 (dek)
		_node("paragraph", 12, preview="Sharni Zaugg"),                         # 3
		_node("paragraph", 8, preview="6/3/2026"),                              # 4
		_node("paragraph", 10, preview="6 min read"),                           # 5
		_node("paragraph", 395, ends_sentence=True,
			preview="We recently had a client with detailed accessibility require"),  # 6 (body)
		_node("paragraph", 25, ends_sentence=True,
			preview="It took 18 hours of work."),                               # 7
		_node("paragraph", 339, ends_sentence=True,
			preview="The project was to build a purchasing approval workflow in M"),  # 8
	]
	assert web.find_article_landing(_summary_with(nodes)) == 6


def test_z_scan_falls_back_to_notice_bar_on_short_content_pages():
	# Zoom confirmation page: no paragraph anywhere clears the 50-char bar
	# (the longest real line is 44 chars). Z from the top must land on that
	# line via the 30-char fallback instead of stranding the user with
	# "Nothing else to land on."
	nodes = [
		_node("heading", 32, level=1, preview="You have successfully registered"),
		_node("paragraph", 44, preview="Please check the confirmation email sent to"),
		_node("paragraph", 24, preview="he**@webfriendlyhelp.com"),
		_node("paragraph", 15, preview="Add to calendar"),
	]
	assert web.find_next_content_landing(_summary_with(nodes), -1) == 1


def test_z_scan_keeps_strict_bar_when_page_has_substantial_paragraphs():
	# An article page: 50+ char paragraphs exist, so the fallback must NOT
	# kick in — Z past the last substantial paragraph still reports nothing
	# rather than landing on short related-link rows below the article.
	nodes = [
		_node("paragraph", 250, preview="Real article body paragraph long enough to be the initial landing."),
		_node("paragraph", 35, preview="Related: another story teaser row"),
	]
	assert web.find_next_content_landing(_summary_with(nodes), 0) is None


# ---------------------------------------------------------------------------
# Prose-run landing (X/Twitter single-status pages)
# ---------------------------------------------------------------------------

def test_ends_like_sentence_detector():
	assert web.ends_like_sentence("We are just not getting the coverage we should.") is True
	assert web.ends_like_sentence('He said "we will finish the job."') is True
	assert web.ends_like_sentence("Really?!") is True
	assert web.ends_like_sentence("And then…") is True
	assert web.ends_like_sentence('"We are doing very well with Iran. ') is True
	# Nav / label / metadata shapes.
	assert web.ends_like_sentence("Adoption Forms") is False
	assert web.ends_like_sentence("Trump on Iran:") is False
	assert web.ends_like_sentence("2:30 PM · Jul 6, 2026") is False
	assert web.ends_like_sentence("") is False


def test_article_landing_prose_run_on_x_status_page():
	# Regression: x.com/MarioNawfal/status/2074138801208012984 (2026-07-06
	# soak test). Quote tweet whose main text never appears in NVDA's walk;
	# the quoted tweet's text arrives as THREE short lines (19 + 34 + 61
	# chars), each below the 50-char bar. The old cascade fell through to
	# the directory redirect and landed on the generic "Post" heading at
	# idx 0. The prose-run gate must land on the first tweet line instead.
	nodes = [
		_node("heading", 4, level=2, preview="Post"),                      # 0
		_node("paragraph", 12, preview="Mario Nawfal"),                    # 1
		_node("paragraph", 13, preview="0xMarioNawfal"),                   # 2
		_node("paragraph", 10, preview="View media"),                      # 3
		_node("paragraph", 12, preview="Mario Nawfal"),                    # 4
		_node("paragraph", 13, preview="0xMarioNawfal"),                   # 5
		_node("paragraph", 1, preview="·"),                           # 6
		_node("paragraph", 19, preview="Trump on Iran:"),                  # 7
		_node("paragraph", 34, preview='"We are doing very well with Iran.',
			ends_sentence=True),                                           # 8
		_node("paragraph", 61,
			preview="We are just not getting the kind of coverage that we should",
			ends_sentence=True),                                           # 9
		_node("paragraph", 21, preview="2:30 PM · Jul 6, 2026"),      # 10
		_node("paragraph", 11, preview="46.9K Views"),                     # 11
		_node("paragraph", 14, preview="Read 21 replies"),                 # 12
		_node("paragraph", 13, preview="Relevant people"),                 # 13
	]
	assert web.find_article_landing(_summary_with(nodes)) == 7


def test_prose_run_rejects_nav_link_runs():
	# The Montgomery directory page opens with six consecutive 17-26 char
	# nav rows totaling 125 chars — length alone must never qualify a run.
	# No line ends like a sentence, so the run is rejected (and it also
	# starts before any heading).
	nodes = [
		_node("paragraph", 20, preview="Skip to Main Content"),
		_node("paragraph", 18, preview="Home ProbateOffice"),
		_node("paragraph", 19, preview="Click to open About"),
		_node("paragraph", 17, preview="Probate Resources"),
		_node("paragraph", 25, preview="Records & Recording Forms"),
		_node("paragraph", 26, preview="Internet Tag/Boat Renewals"),
	]
	assert web._find_prose_run_landing(nodes) is None


def test_prose_run_rejects_form_label_runs():
	# Signed-in Zoom shape: a long run of field labels with ONE question
	# ending in "?" — 1 sentence-ender in a 17-line run fails the density
	# requirement (at least 2 AND at least half the run).
	nodes = [_node("heading", 20, level=2, preview="Webinar Registration")]
	for i in range(16):
		nodes.append(_node("paragraph", 18, preview=f"Field label {i}"))
	nodes.append(_node("paragraph", 52,
		preview="Do you consider yourself a person with a disability?"))
	assert web._find_prose_run_landing(nodes) is None


def test_prose_run_rejects_pre_heading_runs():
	# Cookie-banner shape: two sentence-shaped lines BEFORE any heading.
	# Pre-heading runs are chrome (same principle as the hero gate's
	# seen-heading requirement) — must not become a landing.
	nodes = [
		_node("paragraph", 43, preview="We use cookies to improve your experience."),
		_node("paragraph", 52, preview="By clicking Accept, you agree to our use of cookies."),
		_node("heading", 12, level=1, preview="Real Article"),
	]
	assert web._find_prose_run_landing(nodes) is None


def test_prose_run_preview_fallback_detects_sentence_ends():
	# Fixture-style nodes without the walk-time flag: lines <= 60 chars
	# fall back to checking the preview, so a punctuated pair after a
	# heading still qualifies.
	nodes = [
		_node("heading", 4, level=2, preview="Post"),
		_node("paragraph", 44, preview="Short first line of a chat-style message here."),
		_node("paragraph", 58, preview="Second line that also reads like a real prose sentence."),
	]
	assert web._find_prose_run_landing(nodes) == 1


# ---------------------------------------------------------------------------
# Promo-teaser and byline chrome filters (Daily Mail regression)
# ---------------------------------------------------------------------------

def test_promo_teaser_detector():
	assert web._looks_like_promo_teaser(
		"• READ MORE: America's greatest mystery was a lie") is True
	assert web._looks_like_promo_teaser("READ MORE: The full story here") is True
	assert web._looks_like_promo_teaser("RELATED: Another headline") is True
	assert web._looks_like_promo_teaser("RELATED ARTICLES: one and two") is True
	assert web._looks_like_promo_teaser("DON'T MISS: The other thing") is True
	# Mixed-case prose never matches — the label must be ALL CAPS.
	assert web._looks_like_promo_teaser("Read more about the study here.") is False
	assert web._looks_like_promo_teaser(
		"Related: the researchers also found a second site.") is False
	# EXCLUSIVE deliberately excluded — sites open real ledes with it.
	assert web._looks_like_promo_teaser("EXCLUSIVE: Prince Harry has decided") is False


def test_byline_detector():
	assert web._looks_like_byline(
		"By STACY LIBERATORE, US SCIENCE & TECHNOLOGY EDITOR") is True
	assert web._looks_like_byline("By JOHN SMITH FOR DAILYMAIL.COM") is True
	# Real prose that opens with "By" is mostly lowercase — never matches.
	assert web._looks_like_byline(
		"By NASA's estimate, the mission will cost billions.") is False
	assert web._looks_like_byline(
		"By the time he arrived, the crowd had gone.") is False
	# Mixed-case bylines are a KNOWN GAP, deliberately not matched.
	assert web._looks_like_byline("By John Smith") is False


def test_article_landing_skips_read_more_promo_and_caps_byline():
	# Regression: dailymail.com Channel Islands article (2026-07-06 soak).
	# The "• READ MORE:" promo box (109 chars) followed by the all-caps
	# byline (51 chars) formed a fake cluster and won the landing at idx 1.
	# Both are chrome; the landing must fall through to the real lede at
	# idx 6 (a 226-char very-substantial paragraph).
	nodes = [
		_node("paragraph", 10, preview="Crime Desk"),                        # 0
		_node("paragraph", 109,
			preview="• READ MORE: America's greatest mystery was a lie: Truth abo"),  # 1
		_node("paragraph", 51,
			preview="By STACY LIBERATORE, US SCIENCE & TECHNOLOGY EDITO"),   # 2
		_node("paragraph", 20, preview="Published: 13:05 EDT"),              # 3
		_node("paragraph", 12, preview="146 comments"),                      # 4
		_node("paragraph", 9, preview="Add to bo"),                          # 5
		_node("paragraph", 226,
			preview="Hidden among the Channel Islands are 13,000-year-o"),   # 6
		_node("paragraph", 211,
			preview="Instead, it suggests Ice Age humans reached North "),   # 7
	]
	assert web.find_article_landing(_summary_with(nodes)) == 6


def test_article_landing_hero_lands_on_podcast_description():
	# Thurrott podcast page shape once it classifies ARTICLE: H1, chrome
	# rows, then a 120-char episode description immediately followed by a
	# heading ("Tagged with"). Hero gate: >= 100 chars, heading already
	# seen, heading in lookahead — lands on the description.
	nodes = [
		_node("paragraph", 18, preview="Upgrade to Premium"),
		_node("heading", 37, level=1, preview="First Ring Daily 1977: The Way of GPU"),
		_node("paragraph", 10, preview="Brad Sams"),
		_node("paragraph", 120,
			preview="On this episode of First Ring Daily, NVIDIA has a story, Xbo"),
		_node("heading", 11, level=3, preview="Tagged with"),
		_node("paragraph", 30, preview="First Ring Daily, GPU, NVIDIA"),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 3


def test_participle_byline_detector():
	# Phoronix-style mixed-case byline (85 chars full length).
	assert web._looks_like_byline(
		"Written by Michael Larabel in Arch Linux on 14 June 2026 at",
		full_length=85,
	) is True
	assert web._looks_like_byline("Posted by Jane Doe on July 4, 2026") is True
	assert web._looks_like_byline("Published by The Editorial Team") is True
	# Narrative prose: lowercase after "by" — never matches.
	assert web._looks_like_byline("Written by hand, the letter took weeks to arrive.") is False
	# Long book-review lede: participle prefix but over the 120-char cap.
	assert web._looks_like_byline(
		"Written by John Steinbeck in 1939, The Grapes of",
		full_length=200,
	) is False


def test_scoped_article_landing_skips_participle_byline():
	# Regression: phoronix.com/news/Arch-Linux-AUR-More-Malware (2026-07-06
	# soak). Positionally-scoped single-article tree; the fast path took
	# the FIRST substantial paragraph, which was the 85-char mixed-case
	# byline sitting between the H1 and the lede. Must land on the lede.
	nodes = [
		_node("heading", 75, level=1, preview="Arch Linux AUR Hit By Another Wave Of No"),
		_node("paragraph", 85, preview="Written by Michael Larabel in Arch Linux on 14 Jun"),
		_node("paragraph", 291, preview="Just a day after Arch Linux developers believed th"),
		_node("paragraph", 390, preview="Last night another round of malware in Arch Linux "),
		_node("paragraph", 267, preview="Hours later, Nicolas Boichat reported more malware"),
		_node("paragraph", 205, preview="At this stage it's a bit surprising they don't com"),
		_node("paragraph", 11, preview="97 Comments"),
	]
	summary = cls.TreeSummary(main_nodes=nodes, positionally_scoped=True)
	assert web.find_article_landing(summary) == 2


# ---------------------------------------------------------------------------
# Sentence-ending landing preference + photo-credit chains
#
# Soak test 2026-07-14: 13 real landings, 9 good, 4 bad. Every one of the 4
# bad landings was on a paragraph that does NOT end like a sentence (a photo
# credit ending in "Getty", an ad banner ending in "Veterans", a promo ending
# in "Preferred Source", another story's headline ending in "the law"). Every
# one of the 9 good landings was prose ending in terminal punctuation.
#
# So find_article_landing now runs the whole cascade ONCE over a view where
# non-sentence-ending PARAGRAPHS are treated as chrome, and only falls back to
# the unrestricted cascade if that finds nothing.
#
# The fallback is load-bearing, not a safety net: on a link-aggregator front
# page NOTHING ends like a sentence, and landing on the first headline is the
# CORRECT behavior there (stevequayle.com, confirmed by Casey). Do not remove
# it. See test_article_landing_falls_back_when_no_sentence_enders.
# ---------------------------------------------------------------------------

def test_article_landing_skips_photo_credit_chain():
	# Regression: breitbart.com article landed on main_nodes[1], the photo
	# credit "Matthew Jonas/MediaNews Group/Boulder Daily Camera/Getty".
	# It has no parenthetical and says "Getty" not "Getty Images", so it
	# missed BOTH existing photo-credit signals.
	credit = "Matthew Jonas/MediaNews Group/Boulder Daily Camera/Getty"
	nodes = [
		_node("heading", 60, level=1, preview="Automotive journalist detained by police"),
		_node("paragraph", len(credit), preview=credit),
		_node("paragraph", 220, preview="An automotive journalist was detained after a Flock camera.",
		      ends_sentence=True),
		_node("paragraph", 180, preview="The vehicle had been misidentified as stolen.",
		      ends_sentence=True),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 2


def test_looks_like_image_caption_catches_slash_credit_chain():
	assert web._looks_like_image_caption("Matthew Jonas/MediaNews Group/Boulder Daily Camera/Getty")
	# Must NOT eat real prose that merely contains slashes or a date.
	assert not web._looks_like_image_caption("The meeting is set for 7/14/2026 at city hall.")
	assert not web._looks_like_image_caption("He asked whether the on/off switch mattered.")


def test_article_landing_skips_headline_teaser_for_real_lede():
	# Regression: nypost.com (Hegseth leaks story) landed on main_nodes[8],
	# a RELATED-STORY teaser headline for a completely different article.
	# Two adjacent teasers formed a cluster and won the cluster gate.
	nodes = [
		_node("heading", 55, level=1, preview="Hegseth announces joint task force with DOJ"),
		_node("paragraph", 109,
		      preview="Family shattered after 3-time deported illegal immigrant"),
		_node("paragraph", 96,
		      preview="Trump admin sues city over sanctuary policy in new filing"),
		_node("paragraph", 210,
		      preview="Defense Secretary Pete Hegseth announced a joint task force.",
		      ends_sentence=True),
		_node("paragraph", 190, preview="The task force will prosecute leaks.",
		      ends_sentence=True),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 3


def test_article_landing_skips_ad_banner_and_promo():
	# allnewspipeline.com landed on an ad banner ("Whatfinger: Frontpage For
	# Conservative News Founded By Veterans"); dailymail.com landed on a
	# self-promo ("See more Daily Mail on Google - save us as a Preferred
	# Source"). Neither ends like a sentence.
	nodes = [
		_node("heading", 40, level=1, preview="Carrot and Stick"),
		_node("paragraph", 63,
		      preview="Whatfinger: Frontpage For Conservative News Founded By Vet"),
		_node("paragraph", 63,
		      preview="See more Daily Mail on Google - save us as a Preferred Sou"),
		_node("paragraph", 240, preview="The government has begun a new push this week.",
		      ends_sentence=True),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 3


def test_article_landing_falls_back_when_no_sentence_enders():
	# LOAD-BEARING. stevequayle.com is a link-aggregator front page: every
	# item is a bulleted story headline and NOTHING ends like a sentence.
	# Landing on the first substantial bullet is CORRECT here (confirmed by
	# Casey). If the sentence-strict pass had no fallback, this page would
	# land nowhere at all.
	nodes = [
		_node("heading", 20, level=1, preview="Steve Quayle"),
		_node("paragraph", 30, preview="Alerts"),
		_node("paragraph", 161,
		      preview="▪ Moment giant 'tsunami cloud' slams into French beach"),
		_node("paragraph", 140,
		      preview="▪ Nuclear plant goes offline after unexplained fault"),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 2


# ---------------------------------------------------------------------------
# Stale-position guard
#
# The addon captures a TextInfo per node during the walk and speaks it later.
# On pages that keep hydrating, NVDA rebuilds the buffer underneath us and the
# captured position points at a DIFFERENT paragraph. 2026-07-14 soak: 7 of 42
# landings spoke text that was NOT the paragraph the classifier chose.
#
# These tests guard BOTH directions, and the false-mismatch direction is the
# dangerous one: if this says "drifted" on a page that did NOT drift, we throw
# away a perfectly good landing and the page goes quiet.
# ---------------------------------------------------------------------------

def test_landing_match_accepts_identical_text():
	n = _node("paragraph", 60, preview="Glaucoma is an eye condition that damages the optic nerve.")
	assert web.landing_text_matches("Glaucoma is an eye condition that damages the optic nerve.", n)


def test_landing_match_tolerates_whitespace_and_nbsp():
	# News sites litter NBSPs through ledes, and the expanded range carries
	# leading/trailing whitespace and a trailing newline. None of that is drift.
	n = _node("paragraph", 60, preview="Pentagon chief\xa0Pete Hegseth\xa0on Monday announced")
	actual = "  Pentagon chief Pete Hegseth  on Monday announced the creation of a task force.\n"
	assert web.landing_text_matches(actual, n)


def test_landing_match_accepts_preview_truncated_at_60_chars():
	# text_preview is only the first ~60 chars; the real range is the full
	# paragraph. A longer actual must still match.
	preview = "NVDA (NonVisual Desktop Access) is a free, open source scree"
	n = _node("paragraph", 257, preview=preview)
	actual = ("NVDA (NonVisual Desktop Access) is a free, open source screen reader for "
	          "Microsoft Windows, developed by NV Access.")
	assert web.landing_text_matches(actual, n)


def test_landing_match_rejects_real_drift():
	# The seven real drifts from the soak. In every case the classifier chose
	# correctly and the buffer had moved on to something else entirely.
	drifts = [
		("Keep your Allrecipes favorites in MyRecipes for free.", "My Recipes Logo"),
		("Keep your Simply Recipes favorites in MyRecipes for free.", "Start Saving These Dishes"),
		("This slow-cooker beef stew recipe certainly satisfies when i",
		 " We're loading your content, stay tuned!"),
		("A “disaster waiting to happen”? Industry officials worry abo",
		 "hackers-quickly-prove-that-neo…"),
		("DALLAS — Some North Texas health agencies have provided upda",
		 "Cincinnati Reds Future HINGES on New MLB Rules as Keeping Elly De La Cruz"),
		("The U.S. military announced it will begin its blockade of Ir",
		 "Trump scraps his Hormuz shipping charge idea but presses ahead"),
		("AppleVis is the premier online resource for blind, DeafBlind", "Welcome to AppleVis"),
	]
	for preview, buffer_now in drifts:
		n = _node("paragraph", max(len(preview), 60), preview=preview)
		assert not web.landing_text_matches(buffer_now, n), f"should reject drift: {buffer_now!r}"


def test_landing_match_returns_true_when_nothing_to_compare():
	# An empty preview is NOT evidence of drift. This guard must never be the
	# reason a page goes silent on its own.
	n = _node("paragraph", 0, preview="")
	assert web.landing_text_matches("", n)
	assert web.landing_text_matches("anything at all", n)


def test_landing_match_rejects_empty_buffer_for_real_paragraph():
	# The biblegateway silent-landing: the stale position expanded to an EMPTY
	# range, so speakTextInfo neither raised nor spoke. Same root cause.
	n = _node("paragraph", 68, preview="There is no one who guides her among all the children she ha")
	assert not web.landing_text_matches("", n)


# ---------------------------------------------------------------------------
# Editorial disclosures (closed vocabulary) and the heading-bounded lead section
#
# Two second opinions (Fable, Codex) independently rejected the cross-page
# "boilerplate is what repeats" idea: it is stateful, it makes the SAME url land
# differently on visit 1 and visit 4, it destroys fixture-based debugging, and
# it does nothing on a first visit -- which is the COMMON case (a search click
# into an unfamiliar host). For a blind user, predictable-and-slightly-wrong
# beats adaptive-and-sometimes-right: you can learn "this site lands one
# paragraph early, press Down"; you cannot learn a moving target.
#
# Both proposed the same replacement, which is what these tests pin: affiliate
# disclosures and syndication notes use near-mandated phrasing (the FTC
# effectively dictates the first), so they are as enumerable as the
# "All rights reserved" filter already in the code -- and they work on the
# first visit.
# ---------------------------------------------------------------------------

def test_skips_affiliate_disclosure_for_real_lede():
	# pinchofyum.com landed on the affiliate disclosure instead of the recipe.
	nodes = [
		_node("heading", 34, level=1, preview="The Best Soft Chocolate Chip Cookies"),
		_node("paragraph", 120,
		      preview="This post contains referral links for products we love. Pinc",
		      ends_sentence=True),
		_node("paragraph", 210,
		      preview="These cookies are thick, soft, and completely irresistible.",
		      ends_sentence=True),
		_node("paragraph", 180, preview="You only need one bowl and no chilling time.",
		      ends_sentence=True),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 2


def test_skips_syndication_note_for_real_lede():
	# wtop.com. Ground truth confirmed by fetching the page: headline, byline,
	# THIS note, then the real lede.
	nodes = [
		_node("heading", 58, level=1,
		      preview="Montgomery County slapped a notice on her Little Free Librar"),
		_node("paragraph", 145,
		      preview="This article was written by WTOP’s news partner, The Banner ",
		      ends_sentence=True),
		_node("paragraph", 230,
		      preview="Carol Andress’ husband gave her a Little Free Library kit fo",
		      ends_sentence=True),
		_node("paragraph", 190, preview="She painted the wood box pastel blue and yellow.",
		      ends_sentence=True),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 2


def test_disclosure_flag_catches_a_phrase_past_the_preview_cutoff():
	# THE RUNTIME PATH, which no test used to exercise. _is_chrome_paragraph is
	# handed text_preview, truncated to 60 chars, so a disclosure whose giveaway
	# phrase sits past character 60 was invisible. tree_summary now computes the
	# verdict at walk time over the FULL chunk text, exactly as it already did
	# for is_caption and is_boilerplate.
	#
	# The preview here is innocuous on its own - the phrase would be in the
	# unseen tail - so only the flag can reject this node.
	nodes = [
		_node("heading", 34, level=1, preview="The Best Soft Chocolate Chip Cookies"),
		_node("paragraph", 120, is_disclosure=True, ends_sentence=True,
			preview="Before we get to the recipe, a quick word from our team abou"),
		_node("paragraph", 210, ends_sentence=True,
			preview="These cookies are thick, soft, and completely irresistible."),
		_node("paragraph", 180, ends_sentence=True,
			preview="You only need one bowl and no chilling time."),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 2


def test_long_lede_mentioning_affiliate_links_is_not_chrome():
	# THE OTHER DIRECTION, and the reason the guard had to become live rather
	# than just be fed better text. _EDITORIAL_DISCLOSURE_MAX_CHARS exists
	# because "a disclosure is SHORT" - a long paragraph mentioning affiliate
	# links is an article ABOUT affiliate marketing. Against a 60-char preview
	# that guard could never fire, so such a lede was chrome-flagged with no
	# length protection at all.
	lede = (
		"This post contains referral links, and that is precisely what we want "
		"to talk about today, because the economics of creator compensation "
		"have shifted enormously over the past decade and almost nobody outside "
		"the industry understands how the money actually moves, who ends up "
		"paying for it, or why the disclosure language you skim past at the top "
		"of every recipe reads the way it does."
	)
	assert len(lede) > web._EDITORIAL_DISCLOSURE_MAX_CHARS
	# Preview-only, the old runtime input: still rejected once the real length
	# is supplied alongside it.
	assert web._looks_like_editorial_disclosure(lede[:60], full_length=len(lede)) is False
	# And the node-level helper agrees, which is what the cascade actually calls.
	node = _node("paragraph", len(lede), preview=lede[:60], ends_sentence=True)
	assert web._node_is_disclosure(node) is False
	assert web._is_chrome_paragraph(node) is False


def test_editorial_disclosure_does_not_eat_real_prose():
	# Must NOT fire on an article ABOUT affiliate marketing, or on ordinary prose
	# that happens to use one of these words.
	assert not web._looks_like_editorial_disclosure(
		"The commission voted to republish the report after a lengthy debate."
	)
	assert not web._looks_like_editorial_disclosure(
		"She originally appeared on the show in 1998 and has been a fixture since."
	)


def test_lead_section_gate_lands_on_imdb_plot_summary():
	# IMDb. Codex read the real node trail: H1 "The Dark Knight" at 6, the plot at
	# 27, next heading ("Videos") at 58. The plot fails the hero gate because the
	# next heading is 31 nodes away, far outside the 4-node lookahead -- NOT
	# because no heading was seen. And the "Clip..." titles END IN QUESTION MARKS,
	# so the sentence-strict pass legitimately KEEPS them, and their cluster wins.
	#
	# The fix is a new structural signal, not a threshold change: in the section
	# between the first heading and the next one, exactly ONE non-chrome,
	# sentence-ending paragraph >= 100 chars with no substantial neighbour is the
	# lead. Suppressing the clip rail alone would NOT be enough -- the cascade
	# would run on and land on a 200+ char user review.
	nodes = [
		_node("heading", 15, level=1, preview="The Dark Knight"),
		_node("paragraph", 20, preview="2008"),
		_node("paragraph", 166,
		      preview="When a menace known as the Joker wreaks havoc and chaos on th",
		      ends_sentence=True),
	]
	# The gap is load-bearing. On the real page the next heading is 31 nodes
	# past the plot summary -- far outside the hero gate's 4-node lookahead.
	# That IS the bug: with the heading close by, the hero gate fires and the
	# page lands correctly, so a fixture without this padding does not
	# reproduce anything.
	nodes += [
		_node("paragraph", 18, preview="Christopher Nolan"),
		_node("paragraph", 22, preview="Christian Bale"),
	]
	nodes += [_node("paragraph", 12, preview=f"Cast member {i}") for i in range(28)]
	nodes += [
		_node("heading", 6, level=2, preview="Videos"),
		# The clip titles END IN QUESTION MARKS, so ends_sentence is genuinely
		# True and the sentence-strict pass rightly keeps them. Their cluster is
		# what currently wins.
		_node("paragraph", 57, preview="ClipThe Biggest Supervillain Movies and Who's Comi",
		      ends_sentence=True),
		_node("paragraph", 55, preview="ClipIs the New 'Joker' Most Like Jared, Heath, or J",
		      ends_sentence=True),
		_node("paragraph", 933, preview="Dark, yes, complex, ambitious. Christopher Nolan a",
		      ends_sentence=True),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 2


def test_lead_section_gate_does_not_fire_on_a_normal_article():
	# A normal article's lead section holds MANY substantial paragraphs, so the
	# "exactly one" requirement fails and the ordinary cascade runs. This is what
	# keeps the gate from hijacking every news page (and from landing on a dek).
	nodes = [
		_node("heading", 40, level=1, preview="Council approves the budget"),
		_node("paragraph", 150, preview="The council voted 5-4 on Tuesday evening.",
		      ends_sentence=True),
		_node("paragraph", 220, preview="The budget adds two firefighters and a librarian.",
		      ends_sentence=True),
		_node("paragraph", 180, preview="Opponents said the tax increase was too steep.",
		      ends_sentence=True),
	]
	# Falls through to the normal cascade, which lands on the first of the run.
	assert web.find_article_landing(_summary_with(nodes)) == 1


def test_skips_sms_marketing_consent_for_real_lede():
	# krdo.com (Chrome soak, 2026-07-14). Several KRDO pages carry an SMS signup
	# widget whose consent blurb sits above the story. It is grammatical prose
	# ending in a period, so the sentence rule waves it straight through, exactly
	# like the affiliate disclosures did.
	#
	# Same family, same reason it is tractable: the wording is near-formulaic
	# because telecom marketing law drives it ("you agree to receive", "message
	# and data rates may apply", "unsubscribe at any time"). Closed vocabulary.
	nodes = [
		_node("heading", 45, level=1, preview="Look of the week: Zendaya nailing her red carpet"),
		_node("paragraph", 160,
		      preview="By signing up, you agree to receive text and multimedia mark",
		      ends_sentence=True),
		_node("paragraph", 230,
		      preview="COLORADO SPRINGS, Colo. (KRDO) -- The actress turned heads a",
		      ends_sentence=True),
		_node("paragraph", 180, preview="She wore a custom gown to the premiere.",
		      ends_sentence=True),
	]
	assert web.find_article_landing(_summary_with(nodes)) == 2


def test_consent_filter_does_not_eat_real_prose():
	# Must not fire on a story ABOUT consent, marketing, or subscriptions.
	assert not web._looks_like_editorial_disclosure(
		"The senator said voters did not agree to receive a tax increase this year."
	)
	assert not web._looks_like_editorial_disclosure(
		"Readers may unsubscribe from the paper, but circulation is still climbing."
	)
