# Classifier tests.
#
# Each test constructs a synthetic TreeSummary (the input the classifier
# receives in production) and asserts the returned Intent. Cases here are
# the page shapes we've actually hit during development — every fix from
# this session has at least one test that would have failed without it.

import classifier as cls


def _node(kind, length, level=None, preview=""):
	return cls.MainNode(kind=kind, level=level, text_length=length, text_preview=preview)


def _summary(**overrides):
	# Defaults: nothing on the page. Tests override the fields they care about.
	defaults = dict(
		url="",
		has_main_landmark=True,
		article_count=0,
		main_nodes=[],
		form_input_count=0,
		interactive_control_count=0,
		focused_control_is_editable=False,
		notice_keyword_match=False,
	)
	defaults.update(overrides)
	return cls.TreeSummary(**defaults)


# ---------------------------------------------------------------------------
# Guardrail #6: focused editable control short-circuits everything.
# ---------------------------------------------------------------------------

def test_silent_focus_honored_overrides_all_other_signals():
	# Even with a clear article body cluster, focused-editable wins.
	tree = _summary(
		focused_control_is_editable=True,
		main_nodes=[_node("paragraph", 200), _node("paragraph", 180), _node("paragraph", 220)],
		article_count=1,
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.SILENT_FOCUS_HONORED
	assert result.confidence == 1.0


# ---------------------------------------------------------------------------
# FORM
# ---------------------------------------------------------------------------

def test_form_fires_with_enough_inputs_and_no_content_competition():
	tree = _summary(form_input_count=5)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.FORM


def test_form_blocked_when_article_count_is_untrusted():
	# A truncated article count (budget / scan cap / iterator exception) can
	# be a zeroed UNDERCOUNT on a real news article, which would drop the
	# has_editorial_content FORM block and let the page's scattered inputs
	# (newsletter, search, comments) classify it FORM — moving keyboard
	# focus. Editorial content unknown → FORM must decline. (Neutral URL:
	# neither a form hint nor an editorial hint, so this pins the
	# article-trust gate alone.)
	tree = _summary(
		url="https://example.com/page/",
		form_input_count=5,
		article_count=0,
		article_count_truncated=True,
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.FORM


def test_form_survives_untrusted_article_count_on_form_url():
	# The form-URL escape hatch outranks the editorial block, exactly as it
	# does for a present <article> — a genuine /register page stays FORM
	# even when the article count couldn't be trusted.
	tree = _summary(
		url="https://example.com/register/",
		form_input_count=5,
		article_count=0,
		article_count_truncated=True,
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.FORM


def test_form_blocked_by_substantial_hero():
	# Wordpress homepage pattern: contact form widgets + intro paragraph.
	# With weak form signal (3 inputs, just at the threshold), hero blocks.
	tree = _summary(
		form_input_count=3,
		main_nodes=[_node("paragraph", 400)],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.FORM


def test_form_overrides_hero_when_input_count_is_strong():
	# Regression: Pre-ETS Vendor Fair Google Form had 6+ form inputs
	# (name, email, multiple region checkboxes) AND a lead run that
	# accumulated hero_chars from label text. The old form_blocked rule
	# (has_hero blocks unconditionally) wedged ARTICLE-hero to win and
	# landed the user on a checkbox label. With STRONG_FORM_INPUT_COUNT
	# override, form_input_count >= 5 makes FORM fire over the hero block.
	tree = _summary(
		form_input_count=8,
		main_nodes=[
			_node("heading", 60, level=1, preview="Form title"),
			_node("paragraph", 86, preview="Label or description text"),
			_node("paragraph", 60, preview="More label text"),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.FORM


def test_form_still_blocked_by_real_body_cluster_even_with_many_inputs():
	# A real article with embedded survey widgets shouldn't get demoted to
	# FORM just because the form_input_count is high. Real body cluster
	# (multiple consecutive 100+ char paragraphs totaling ≥500 chars)
	# remains an absolute FORM blocker.
	tree = _summary(
		form_input_count=10,
		main_nodes=[
			_node("heading", 40, level=1),
			_node("paragraph", 250),
			_node("paragraph", 300),
			_node("paragraph", 280),
		],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.FORM


# ---------------------------------------------------------------------------
# ARTICLE
# ---------------------------------------------------------------------------

def test_article_with_article_element_and_body_cluster_is_high_confidence():
	tree = _summary(
		article_count=1,
		main_nodes=[
			_node("heading", 30, level=1),
			_node("paragraph", 200),
			_node("paragraph", 180),
			_node("paragraph", 220),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.ARTICLE
	assert result.confidence >= 0.85


def test_article_via_short_hero_fires_after_threshold_lowered():
	# Regression: bestmidi.com/bg/ has a 60-char intro and no body cluster.
	# With the old HERO_PARAGRAPH_MIN_CHARS=100 this returned UNKNOWN; the
	# decoupled threshold of 50 now classifies it as ARTICLE via hero.
	tree = _summary(
		main_nodes=[
			_node("paragraph", 60, preview="Text-based info and tools for X."),
			_node("paragraph", 12),
			_node("heading", 13, level=2),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.ARTICLE


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

def test_list_via_heading_cluster():
	# 5 same-level headings interleaved with short list-item text.
	nodes = []
	for _ in range(5):
		nodes.append(_node("heading", 30, level=2))
		nodes.append(_node("paragraph", 50))
	tree = _summary(main_nodes=nodes)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.LIST


# ---------------------------------------------------------------------------
# APP
# ---------------------------------------------------------------------------

def test_app_fires_with_many_controls_and_no_body_or_heading_cluster():
	tree = _summary(interactive_control_count=15)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.APP


# ---------------------------------------------------------------------------
# NOTICE
# ---------------------------------------------------------------------------

def test_notice_with_keyword_match_is_high_confidence():
	# Google Forms closed page shape — small, one heading, status sentence.
	tree = _summary(
		notice_keyword_match=True,
		main_nodes=[
			_node("heading", 28, level=1, preview="Web App Accessibility Survey"),
			_node("paragraph", 130, preview="The form ... is no longer accepting responses"),
			_node("paragraph", 50),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.NOTICE
	assert result.confidence >= 0.85


def test_notice_without_keyword_lower_confidence_but_still_fires():
	# Small page with one heading and a short status sentence — no keyword.
	tree = _summary(
		main_nodes=[
			_node("heading", 28, level=1),
			_node("paragraph", 45),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.NOTICE


def test_notice_does_not_fire_on_real_article_pages():
	# Real article with body cluster — ARTICLE must win, not NOTICE.
	tree = _summary(
		main_nodes=[
			_node("heading", 40, level=1),
			_node("paragraph", 250),
			_node("paragraph", 300),
			_node("paragraph", 280),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.ARTICLE


def test_shape_only_notice_declines_when_counts_truncated():
	# Same shape as the shape-only NOTICE above, but the counts phase hit
	# its wall-clock budget — interactive_control_count may be a huge
	# undercount (a busy page reading as 0 controls). Shape evidence IS
	# small counts, so shape-only NOTICE must decline and leave the page
	# to the 1500 ms retry, which will see honest counts.
	tree = _summary(
		counts_truncated=True,
		main_nodes=[
			_node("heading", 28, level=1),
			_node("paragraph", 45),
		],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.NOTICE


def test_keyword_notice_survives_counts_truncated():
	# The keyword path rests on real walked TEXT (status keyword), not on
	# counts, so a truncated count phase must not silence a genuine
	# "no longer accepting responses" page.
	tree = _summary(
		counts_truncated=True,
		notice_keyword_match=True,
		main_nodes=[
			_node("heading", 28, level=1, preview="Web App Accessibility Survey"),
			_node("paragraph", 130, preview="The form ... is no longer accepting responses"),
			_node("paragraph", 50),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.NOTICE


def test_notice_blocked_by_too_many_headings():
	# Many headings = not a notice page.
	tree = _summary(
		main_nodes=[
			_node("heading", 30, level=1),
			_node("heading", 20, level=2),
			_node("heading", 20, level=2),
			_node("heading", 20, level=2),
			_node("heading", 20, level=2),
			_node("paragraph", 40),
		],
		notice_keyword_match=True,
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.NOTICE


# ---------------------------------------------------------------------------
# KEY_RESULT — label + value [+ unit] widget pattern.
# ---------------------------------------------------------------------------

def test_key_result_fires_for_fast_com_style_speed_widget():
	# Pattern: short language-link chrome, then label / value / unit.
	# No body cluster, no headings — pure widget page.
	tree = _summary(
		main_nodes=[
			_node("paragraph", 8, preview="English"),
			_node("paragraph", 9, preview="Español"),
			_node("paragraph", 22, preview="Your Internet speed is"),  # label
			_node("paragraph", 3, preview="170"),                       # value
			_node("paragraph", 4, preview="Mbps"),                      # unit
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.KEY_RESULT


def test_key_result_handles_caveat_between_value_and_unit():
	# fast.com renders a caveat paragraph between the value and the unit
	# when the connection is unstable. As long as the unit appears within
	# the lookahead window AND no PARAGRAPH_MIN_CHARS body paragraph stops
	# the search, the pattern matches.
	# 80 chars stays under PARAGRAPH_MIN_CHARS=100 so the lookahead can
	# still reach "Mbps".
	tree = _summary(
		main_nodes=[
			_node("paragraph", 22, preview="Your Internet speed is"),
			_node("paragraph", 3, preview="170"),
			_node("paragraph", 80, preview="* Your network is unstable. Estimate only."),
			_node("paragraph", 4, preview="Mbps"),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.KEY_RESULT


def test_key_result_fires_with_implicit_unit_in_value():
	# "85%" — the % IS the unit, no separate node needed.
	tree = _summary(
		main_nodes=[
			_node("paragraph", 13, preview="Battery level"),
			_node("paragraph", 3, preview="85%"),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.KEY_RESULT


def test_key_result_declines_when_counts_truncated():
	# KEY_RESULT's whole premise is "few controls, no form" — both gates
	# lean on counts being real. A budget-truncated count phase can report
	# 0 controls on a control-dense page, so KEY_RESULT must decline.
	tree = _summary(
		counts_truncated=True,
		main_nodes=[
			_node("paragraph", 22, preview="Your Internet speed is"),
			_node("paragraph", 3, preview="170"),
			_node("paragraph", 4, preview="Mbps"),
		],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.KEY_RESULT


def test_key_result_does_not_fire_when_body_cluster_precedes():
	# Article with "Score: 5" mentioned inline AFTER a body paragraph.
	# Body cluster wins (real article); KEY_RESULT skipped.
	tree = _summary(
		main_nodes=[
			_node("paragraph", 250),  # body
			_node("paragraph", 220),  # body
			_node("paragraph", 12, preview="Final score"),
			_node("paragraph", 3, preview="2-1"),
		],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.KEY_RESULT


def test_key_result_does_not_fire_without_unit_or_implicit_unit():
	# "Final score: 5" with no Mbps/min/% etc. after, and no $/%/° in
	# value — pattern is ambiguous, do NOT fire.
	tree = _summary(
		main_nodes=[
			_node("paragraph", 11, preview="Final score"),
			_node("paragraph", 1, preview="5"),
			_node("paragraph", 30, preview="That is the final tally for the game"),
		],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.KEY_RESULT


def test_key_result_does_not_fire_on_apps_with_many_controls():
	# Dashboard with 15 controls — even if a label/value/unit triplet
	# exists, KEY_RESULT must yield to APP / etc.
	tree = _summary(
		interactive_control_count=15,
		main_nodes=[
			_node("paragraph", 22, preview="Your Internet speed is"),
			_node("paragraph", 3, preview="170"),
			_node("paragraph", 4, preview="Mbps"),
		],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.KEY_RESULT


def test_key_result_does_not_fire_on_form_pages():
	# Pages with form inputs should fall through to FORM logic, not steal
	# the user with a coincidental label/value/unit.
	tree = _summary(
		form_input_count=4,
		main_nodes=[
			_node("paragraph", 22, preview="Your Internet speed is"),
			_node("paragraph", 3, preview="170"),
			_node("paragraph", 4, preview="Mbps"),
		],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.KEY_RESULT


# ---------------------------------------------------------------------------
# UNKNOWN
# ---------------------------------------------------------------------------

def test_unknown_when_no_signal():
	tree = _summary()
	result = cls.classify(tree)
	assert result.intent == cls.Intent.UNKNOWN
	assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# Legal footer boilerplate vs hero (Zoom webinar registration regression)
# ---------------------------------------------------------------------------

def _boilerplate_node(length, preview=""):
	return cls.MainNode(
		kind="paragraph", text_length=length, text_preview=preview, is_boilerplate=True,
	)


def test_copyright_footer_alone_is_not_an_article_hero():
	# Pre-hydration Zoom webinar registration shell: the ONLY substantial
	# paragraph is the footer copyright (flagged at walk time). It must not
	# qualify as a hero, so the page must NOT classify as ARTICLE — leaving
	# no landing and letting the caller's retry wait for hydration.
	tree = _summary(
		has_main_landmark=False,
		interactive_control_count=8,
		main_nodes=[
			_node("paragraph", 20, preview="Skip to Main Content"),
			_node("paragraph", 22, preview="Accessibility Overview"),
			_node("paragraph", 7, preview="Support"),
			_boilerplate_node(69, preview="Copyright ©2026 Zoom Video Communications, Inc. All rights"),
		],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.ARTICLE


def test_form_not_blocked_by_footer_copyright_pseudo_hero():
	# A plain 3-input form page whose only 50+ char paragraph is the footer
	# copyright. Before the boilerplate-aware hero computation, that line
	# created has_hero=True and blocked FORM (weak form signal), leaving the
	# page unhandled. The copyright must not count as a hero.
	tree = _summary(
		form_input_count=3,
		main_nodes=[
			_node("heading", 20, level=1, preview="Contact us"),
			_boilerplate_node(69, preview="Copyright ©2026 Example Corp. All rights reserved."),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.FORM


def test_hydrated_zoom_registration_classifies_as_form():
	# The REAL hydrated Zoom webinar registration page (measured 2026-07-06):
	# H1 title (81 chars), one 1958-char description block, 7 form inputs,
	# footer copyright. Strong form signal (>= 5 inputs) must win — the
	# description hero does not block, and the copyright stays irrelevant.
	tree = _summary(
		url="https://us02web.zoom.us/webinar/register/WN_abc#/registration",
		form_input_count=7,
		interactive_control_count=12,
		main_nodes=[
			_node("heading", 81, level=1, preview="AI as Assistive Technology: A Practical Stack for Entrepren"),
			_node("heading", 20, level=2, preview="Webinar Registration"),
			_node("paragraph", 1958, preview="Whether you're starting your business or scaling one, AI is"),
			_boilerplate_node(69, preview="Copyright ©2026 Zoom Video Communications, Inc. All rights"),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.FORM


def test_zoom_registration_confirmation_classifies_as_notice():
	# The post-registration page (2026-07-06 debug log): 6 nodes, H1 "You
	# have successfully registered" (32 chars), short paragraphs, ONE form
	# field (the "Add to calendar" widget counts in NVDA's formField
	# class), 2 interactives. The old NOTICE gate required zero form
	# fields, so this classified UNKNOWN and the user got the not-found
	# beeps on a page that is the textbook NOTICE case.
	tree = _summary(
		url="https://us02web.zoom.us/rest/webinar/registrant/WN_abc/info?ac=approved",
		form_input_count=1,
		interactive_control_count=2,
		notice_keyword_match=True,
		main_nodes=[
			_node("heading", 32, level=1, preview="You have successfully registered"),
			_node("paragraph", 44, preview="Please check the confirmation email sent to"),
			_node("paragraph", 24, preview="he**@webfriendlyhelp.com"),
			_node("paragraph", 15, preview="Add to calendar"),
			_node("paragraph", 7, preview="Support"),
			_node("paragraph", 22, preview="Accessibility overview"),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.NOTICE
	assert result.confidence >= 0.85


def test_shape_only_notice_still_requires_zero_form_fields():
	# A small login-ish page (2 inputs, H1, short text, no status keyword)
	# must NOT become a NOTICE just because the keyword path now tolerates
	# form fields — the 0.65 shape-only path keeps the zero-fields gate.
	tree = _summary(
		form_input_count=2,
		interactive_control_count=4,
		main_nodes=[
			_node("heading", 7, level=1, preview="Sign in"),
			_node("paragraph", 35, preview="Enter your username and password."),
		],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.NOTICE


# ---------------------------------------------------------------------------
# Massive-duo FORM block (armstrongeconomics newsletter-widget regression)
# ---------------------------------------------------------------------------

def test_blog_with_massive_paragraph_pair_is_not_form():
	# Regression: armstrongeconomics.com war blog post (2026-07-06 soak).
	# WordPress theme exposes NO <article> (so the editorial block was off)
	# and a 6-input newsletter widget cleared the strong-form bar. The two
	# ADJACENT 618/595-char body paragraphs miss the 3-paragraph cluster
	# bar, so nothing blocked FORM and the user landed on the H1 via the
	# form-title path instead of the lede. The massive-duo block must
	# classify this as ARTICLE.
	nodes = [
		_node("paragraph", 15, preview="Skip to content"),
		_node("paragraph", 151, preview="Follow on Linkedin (opens in new tab) Follow on Fa"),
		_node("paragraph", 6, preview="Events"),
		_node("paragraph", 16, preview="Knowledge Center"),
		_node("paragraph", 13, preview="Store Account"),
		_node("heading", 51, level=1, preview="Zelensky Angers Allies by Honoring Ukrainian Nazis"),
		_node("paragraph", 15, preview="SPREAD THE LOVE"),
		_node("paragraph", 7, preview="Twitter"),
		_node("paragraph", 8, preview="Facebook"),
		_node("paragraph", 618, preview="Europe's united front behind Zelensky is beginning"),
		_node("paragraph", 595, preview="The bureaucrats in Brussels have spent years insis"),
	]
	tree = _summary(
		url="https://www.armstrongeconomics.com/world-news/war/zelensky-angers-allies/",
		has_main_landmark=False,
		article_count=0,
		main_nodes=nodes,
		form_input_count=6,
		interactive_control_count=11,
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.ARTICLE


def test_register_url_with_massive_description_stays_form():
	# The escape hatch: a Zoom-style registration page whose rich
	# description happens to chunk into two adjacent 200+ char paragraphs
	# must STAY a form — the /register URL is the explicit signal.
	nodes = [
		_node("heading", 81, level=1, preview="AI as Assistive Technology: A Practical Stack for"),
		_node("paragraph", 900, preview="Whether you're starting your business or scaling o"),
		_node("paragraph", 1100, preview="In this webinar we will walk through the exact too"),
	]
	tree = _summary(
		url="https://us02web.zoom.us/webinar/register/WN_abc#/registration",
		has_main_landmark=True,
		article_count=0,
		main_nodes=nodes,
		form_input_count=7,
		interactive_control_count=9,
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.FORM


def test_massive_duo_requires_adjacency():
	# Two big paragraphs separated by a heading are sections, not a body
	# duo — the helper itself must not fire.
	nodes = [
		_node("paragraph", 300),
		_node("heading", 20, level=2),
		_node("paragraph", 300),
	]
	assert cls._has_massive_paragraph_duo(nodes) is False
	nodes_adjacent = [
		_node("paragraph", 300),
		_node("paragraph", 300),
	]
	assert cls._has_massive_paragraph_duo(nodes_adjacent) is True


def test_editorial_url_blocks_form_on_podcast_page():
	# Regression: thurrott.com podcast episode page (2026-07-06 soak).
	# 10 form inputs (comment box, login, search, newsletter), no <article>
	# exposed, episode description only 120 chars, long comment paragraphs
	# not adjacent — none of the other FORM blocks engaged and the page
	# dispatched FORM(0.90), landing on the H1 via the form-title path.
	# The /podcasts/ URL is editorial and must block FORM.
	nodes = [
		_node("paragraph", 18, preview="Upgrade to Premium"),
		_node("paragraph", 6, preview="Log In"),
		_node("heading", 37, level=1, preview="First Ring Daily 1977: The Way of GPU"),
		_node("paragraph", 120, preview="On this episode of First Ring Daily, NVIDIA has a"),
		_node("heading", 11, level=3, preview="Tagged with"),
		_node("paragraph", 159, preview="We maintain the community forums so our readers ha"),
		_node("paragraph", 124, preview="By participating in the conversations on this webs"),
		_node("paragraph", 318, preview="I remember listening to a Podcast a few years ago"),
		_node("paragraph", 196, preview="I think the problem is that, while Nintendo is ver"),
	]
	tree = _summary(
		url="https://www.thurrott.com/podcasts/337378/first-ring-daily-1977-the-way-of-gpu",
		has_main_landmark=False,
		article_count=0,
		main_nodes=nodes,
		form_input_count=10,
		interactive_control_count=11,
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.FORM


def test_editorial_url_does_not_block_form_when_url_also_matches_form():
	# /blog/contact matches both ARTICLE (/blog/) and FORM (/contact) —
	# FORM must stay eligible.
	nodes = [
		_node("heading", 10, level=1, preview="Contact Us"),
		_node("paragraph", 30, preview="Send us a message below."),
	]
	tree = _summary(
		url="https://example.com/blog/contact",
		has_main_landmark=True,
		article_count=0,
		main_nodes=nodes,
		form_input_count=5,
		interactive_control_count=6,
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.FORM


# ---------------------------------------------------------------------------
# Form-input counting: the count is now REAL INPUTS ONLY
#
# tree_summary used to fill form_input_count from NVDA's "formField" quick-nav
# type, which counts BUTTONS as form fields. A control-dense CONTENT page
# therefore maxed the counter (IMDb title pages and a TV station front page both
# reported 10) and classified as FORM -- and the bare-form branch MOVED THE
# USER'S KEYBOARD FOCUS into the site's search box.
#
# It now counts only edit / comboBox / checkBox / radioButton, so the honest
# numbers are much smaller, and STRONG_FORM_INPUT_COUNT came down 5 -> 4 to
# match. These tests pin BOTH sides of that boundary.
# ---------------------------------------------------------------------------

def test_content_page_with_one_search_box_is_not_a_form():
	# IMDb / a TV station front page: lots of buttons, ONE real search box, and
	# a single substantial content paragraph. Must not be FORM -- FORM is the
	# branch that hijacks the user's focus.
	nodes = [
		_node("heading", 14, level=1, preview="The Dark Knight"),
		_node("paragraph", 166,
		      preview="When a menace known as the Joker wreaks havoc and chaos on the"),
	]
	result = cls.classify(_summary(
		main_nodes=nodes,
		form_input_count=1,          # the search box, and nothing else
		interactive_control_count=11,  # buttons galore -- must not matter
	))
	assert result.intent != cls.Intent.FORM


def test_registration_form_with_four_real_inputs_is_a_form():
	# Wikipedia Special:CreateAccount -- username, password, confirm, email.
	# Honest count is 4. With STRONG_FORM_INPUT_COUNT left at 5 this fell below
	# the bar, the hero-paragraph gate blocked FORM, and a genuine registration
	# form classified as an ARTICLE -- landing the user on the help text NEXT TO
	# the form instead of in it. Casey hit exactly that.
	nodes = [
		_node("heading", 16, level=1, preview="Create account"),
		_node("paragraph", 120,
		      preview="Email is required to recover your account if you lose your pass"),
	]
	result = cls.classify(_summary(
		main_nodes=nodes,
		form_input_count=4,
		interactive_control_count=11,
	))
	assert result.intent == cls.Intent.FORM


def test_account_creation_url_is_a_form_url_not_an_article_url():
	# Wikipedia's account-creation page redirects to
	# auth.wikimedia.org/enwiki/wiki/Special:CreateAccount. That path contains
	# "/wiki/", which matches the ARTICLE url hints, so has_editorial_url blocked
	# FORM and a registration form classified as an encyclopedia article --
	# landing the user on the help text BESIDE the form instead of in it.
	nodes = [
		_node("heading", 16, level=1, preview="Create account"),
		_node("paragraph", 120,
		      preview="Email is required to recover your account if you lose your pass"),
	]
	result = cls.classify(_summary(
		url="https://auth.wikimedia.org/enwiki/wiki/Special:CreateAccount",
		main_nodes=nodes,
		form_input_count=4,
		interactive_control_count=11,
	))
	assert result.intent == cls.Intent.FORM


def test_wiki_article_url_still_reads_as_editorial():
	# The guard above must not turn every /wiki/ page into a form. An ordinary
	# encyclopedia article with a search box stays an ARTICLE.
	nodes = [
		_node("heading", 20, level=1, preview="Battle of Midway"),
		_node("paragraph", 240, preview="The Battle of Midway was a major naval battle."),
		_node("paragraph", 210, preview="It took place from June 4 to 7, 1942."),
		_node("paragraph", 190, preview="The United States Navy defeated an attacking fleet."),
	]
	result = cls.classify(_summary(
		url="https://en.wikipedia.org/wiki/Battle_of_Midway",
		main_nodes=nodes,
		form_input_count=1,
		interactive_control_count=11,
	))
	assert result.intent != cls.Intent.FORM
