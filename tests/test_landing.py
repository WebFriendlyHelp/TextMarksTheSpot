# Landing-finder tests.
#
# detection/web.py's find_article_landing / find_list_landing / find_notice_landing
# are pure functions over a TreeSummary. These tests pin the behavior on the
# page shapes we've encountered — especially the bestmidi.com regression
# where the addon was landing on a footer line.

import classifier as cls
from detection import web


def _node(kind, length, level=None, preview=""):
	return cls.MainNode(kind=kind, level=level, text_length=length, text_preview=preview)


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
