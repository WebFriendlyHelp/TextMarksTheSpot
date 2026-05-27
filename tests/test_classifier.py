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
