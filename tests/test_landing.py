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
