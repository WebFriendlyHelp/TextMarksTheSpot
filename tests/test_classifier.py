# Classifier tests.
#
# Each test constructs a synthetic TreeSummary (the input the classifier
# receives in production) and asserts the returned Intent. Cases here are
# the page shapes we've actually hit during development — every fix from
# this session has at least one test that would have failed without it.

import classifier as cls


def _node(kind, length, level=None, preview=""):
	return cls.MainNode(kind=kind, level=level, textLength=length, textPreview=preview)


def _summary(**overrides):
	# Defaults: nothing on the page. Tests override the fields they care about.
	defaults = dict(
		url="",
		hasMainLandmark=True,
		articleCount=0,
		mainNodes=[],
		formInputCount=0,
		interactiveControlCount=0,
		focusedControlIsEditable=False,
		noticeKeywordMatch=False,
	)
	defaults.update(overrides)
	return cls.TreeSummary(**defaults)


# ---------------------------------------------------------------------------
# Guardrail #6: focused editable control short-circuits everything.
# ---------------------------------------------------------------------------


def test_silentFocusHonoredOverridesAllOtherSignals():
	# Even with a clear article body cluster, focused-editable wins.
	tree = _summary(
		focusedControlIsEditable=True,
		mainNodes=[_node("paragraph", 200), _node("paragraph", 180), _node("paragraph", 220)],
		articleCount=1,
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.SILENT_FOCUS_HONORED
	assert result.confidence == 1.0


# ---------------------------------------------------------------------------
# FORM
# ---------------------------------------------------------------------------


def test_formFiresWithEnoughInputsAndNoContentCompetition():
	tree = _summary(formInputCount=5)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.FORM


def test_formBlockedWhenArticleCountIsUntrusted():
	# A truncated article count (budget / scan cap / iterator exception) can
	# be a zeroed UNDERCOUNT on a real news article, which would drop the
	# hasEditorialContent FORM block and let the page's scattered inputs
	# (newsletter, search, comments) classify it FORM — moving keyboard
	# focus. Editorial content unknown → FORM must decline. (Neutral URL:
	# neither a form hint nor an editorial hint, so this pins the
	# article-trust gate alone.)
	tree = _summary(
		url="https://example.com/page/",
		formInputCount=5,
		articleCount=0,
		articleCountTruncated=True,
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.FORM


def test_formSurvivesUntrustedArticleCountOnFormUrl():
	# The form-URL escape hatch outranks the editorial block, exactly as it
	# does for a present <article> — a genuine /register page stays FORM
	# even when the article count couldn't be trusted.
	tree = _summary(
		url="https://example.com/register/",
		formInputCount=5,
		articleCount=0,
		articleCountTruncated=True,
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.FORM


def test_formBlockedBySubstantialHero():
	# Wordpress homepage pattern: contact form widgets + intro paragraph.
	# With weak form signal (3 inputs, just at the threshold), hero blocks.
	tree = _summary(
		formInputCount=3,
		mainNodes=[_node("paragraph", 400)],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.FORM


def test_formOverridesHeroWhenInputCountIsStrong():
	# Regression: Pre-ETS Vendor Fair Google Form had 6+ form inputs
	# (name, email, multiple region checkboxes) AND a lead run that
	# accumulated heroChars from label text. The old formBlocked rule
	# (hasHero blocks unconditionally) wedged ARTICLE-hero to win and
	# landed the user on a checkbox label. With STRONG_FORM_INPUT_COUNT
	# override, formInputCount >= 5 makes FORM fire over the hero block.
	tree = _summary(
		formInputCount=8,
		mainNodes=[
			_node("heading", 60, level=1, preview="Form title"),
			_node("paragraph", 86, preview="Label or description text"),
			_node("paragraph", 60, preview="More label text"),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.FORM


def test_checkoutFormNotBlockedByLegalBoilerplateCluster():
	# store.payproglobal.com/checkout?products[1][id]=69131 (2026-07-17): a
	# 10-input checkout with zero headings and no <article>. Near the Submit
	# button sit three adjacent 100+ char paragraphs: a trust-badge alt-text
	# blob (237), the "By placing your order, you agree to our Terms and
	# Conditions..." consent line (263 — flagged isBoilerplate at walk
	# time), and a data-sharing note (127). The trio formed a fake strong
	# body cluster that blocked FORM, classified the page ARTICLE at 0.70,
	# and landed the user in the legalese. Flagged paragraphs must not count
	# as article body.
	consent = cls.MainNode(
		kind="paragraph",
		textLength=263,
		textPreview="By placing your order, you agree to our Terms and Condition",
		isBoilerplate=True,
		endsSentence=True,
	)
	tree = _summary(
		url="https://store.payproglobal.com/checkout?products[1][id]=69131",
		hasMainLandmark=False,
		formInputCount=10,
		interactiveControlCount=11,
		mainNodes=[
			_node("paragraph", 8, preview="xplorer²"),
			_node("paragraph", 50, preview="exponential growth in file management productivity"),
			_node("paragraph", 13, preview="You're Buying"),
			_node("paragraph", 108, preview="xplorer² professional  Explore, preview,"),
			_node("paragraph", 42, preview="Volume discount available for this produ"),
			_node("paragraph", 237, preview="PCI DSS Compliancy Status Trustedsite sites help k"),
			consent,
			_node("paragraph", 127, preview="Once the transaction is complete, your contact inf"),
			_node("paragraph", 61, preview="24/7 English phone support for online payment rela"),
			_node("paragraph", 100, preview="Do not hesitate to contact our CUSTOMER CARE CENTE"),
			_node("paragraph", 107, preview="Please state the order ID from the confirmation em"),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.FORM


def test_clusterTreatsFlaggedNodesAsTransparentNotBreaking():
	# The fail-safe direction of the fix above: a long mid-article figure
	# caption must NOT split a real article's body cluster — that cluster is
	# what blocks FORM (and a FORM misfire moves keyboard focus) on news
	# pages whose scattered widgets add up to a strong input count. Flagged
	# nodes are transparent: they contribute nothing, but the run survives.
	caption = cls.MainNode(
		kind="paragraph",
		textLength=120,
		textPreview="The mayor at the ribbon cutting. (Photo: Getty Images)",
		isCaption=True,
	)
	nodes = [
		_node("paragraph", 200),
		_node("paragraph", 180),
		caption,
		_node("paragraph", 220),
	]
	assert cls._largestParagraphCluster(nodes) == (3, 600)


def test_signupPageWithShortIntroStaysFormOnFormUrl():
	# starttesting.net/signup (2026-07-16): 3 real inputs (Name, Email,
	# Password) meets FORM_INPUT_THRESHOLD but sits below
	# STRONG_FORM_INPUT_COUNT, and the one-line intro "You can join an
	# existing organization or create one later." (58 chars) clears the
	# 50-char hero bar. The hero block had no form-URL escape hatch, so the
	# page classified ARTICLE(0.65) and the prose-run gate landed the user
	# on "Use at least 6 characters." — the password hint mid-form. With
	# the hatch, the /signup URL keeps it FORM.
	tree = _summary(
		url="https://starttesting.net/signup?utm_source=substack&utm_medium=email",
		formInputCount=3,
		interactiveControlCount=8,
		mainNodes=[
			_node("heading", 33, level=1, preview="Create your Start Testing account"),
			_node("paragraph", 58, preview="You can join an existing organization or"),
			_node("paragraph", 4, preview="Name"),
			_node("paragraph", 13, preview="Email address"),
			_node("paragraph", 8, preview="Password"),
			_node("paragraph", 26, preview="Use at least 6 characters."),
			_node("paragraph", 33, preview="Already have an account? Sign in."),
			_node("paragraph", 77, preview="By creating an account, you agree to our"),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.FORM


def test_loginPageWithTwoInputsIsFormOnAuthUrl():
	# starttesting.net/login (2026-07-16): email + password is only 2 real
	# inputs, below FORM_INPUT_THRESHOLD, so the page classified UNKNOWN and
	# played the not-found beeps. An unambiguous auth URL (whole path
	# segment /login) lowers the bar to AUTH_FORM_MIN_INPUTS.
	tree = _summary(
		url="https://starttesting.net/login?redirect=%2fhome&email=",
		formInputCount=2,
		interactiveControlCount=6,
		mainNodes=[
			_node("heading", 12, level=1, preview="Welcome back"),
			_node("paragraph", 13, preview="Email address"),
			_node("paragraph", 8, preview="Password"),
			_node("paragraph", 16, preview="Forgot password?"),
			_node("paragraph", 31, preview="Don't have an account? Sign up."),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.FORM


def test_twoInputsNeedAWholeAuthSegmentNotASubstring():
	# The lowered bar must not fire on a content URL that merely CONTAINS an
	# auth word. /login-security-tips substring-matches the loose "/login"
	# hint, but the strict segment matcher rejects it, so 2 inputs (search +
	# newsletter) stay below the bar and the page must not become FORM —
	# FORM moves keyboard focus.
	tree = _summary(
		url="https://example.com/login-security-tips/",
		formInputCount=2,
		mainNodes=[
			_node("heading", 40, level=1),
			_node("paragraph", 90, preview="Keeping your accounts safe starts with"),
		],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.FORM


def test_oneInputOnAuthUrlStaysBelowTheBar():
	# The floor is 2. A single input on an auth-looking URL is as likely a
	# search box; staged email-first logins are a known accepted gap.
	tree = _summary(
		url="https://example.com/login",
		formInputCount=1,
		mainNodes=[_node("heading", 12, level=1, preview="Welcome back")],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.FORM


def test_authUrlWithRealBodyClusterStillNotForm():
	# The body-cluster block is unconditional: a help-center article that
	# happens to live under /login/ must keep its article landing.
	tree = _summary(
		url="https://example.com/login/troubleshooting",
		formInputCount=2,
		mainNodes=[
			_node("heading", 40, level=1),
			_node("paragraph", 250),
			_node("paragraph", 300),
			_node("paragraph", 280),
		],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.FORM


def test_heroStillBlocksWeakFormOnNeutralUrl():
	# The mirror of the signup case: same weak form signal and hero, but a
	# URL with no form hint. The hero block must still win — a WordPress
	# homepage with an intro paragraph and a few sidebar widgets is not a
	# form page.
	tree = _summary(
		url="https://example.com/",
		formInputCount=3,
		mainNodes=[
			_node("heading", 30, level=1),
			_node("paragraph", 90, preview="Welcome to our site, where we write about"),
		],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.FORM


def test_formStillBlockedByRealBodyClusterEvenWithManyInputs():
	# A real article with embedded survey widgets shouldn't get demoted to
	# FORM just because the formInputCount is high. Real body cluster
	# (multiple consecutive 100+ char paragraphs totaling ≥500 chars)
	# remains an absolute FORM blocker.
	tree = _summary(
		formInputCount=10,
		mainNodes=[
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


def test_articleWithArticleElementAndBodyClusterIsHighConfidence():
	tree = _summary(
		articleCount=1,
		mainNodes=[
			_node("heading", 30, level=1),
			_node("paragraph", 200),
			_node("paragraph", 180),
			_node("paragraph", 220),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.ARTICLE
	assert result.confidence >= 0.85


def test_articleViaShortHeroFiresAfterThresholdLowered():
	# Regression: bestmidi.com/bg/ has a 60-char intro and no body cluster.
	# With the old HERO_PARAGRAPH_MIN_CHARS=100 this returned UNKNOWN; the
	# decoupled threshold of 50 now classifies it as ARTICLE via hero.
	tree = _summary(
		mainNodes=[
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


def test_listViaHeadingCluster():
	# 5 same-level headings interleaved with short list-item text.
	nodes = []
	for _ in range(5):
		nodes.append(_node("heading", 30, level=2))
		nodes.append(_node("paragraph", 50))
	tree = _summary(mainNodes=nodes)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.LIST


# ---------------------------------------------------------------------------
# APP
# ---------------------------------------------------------------------------


def test_appFiresWithManyControlsAndNoBodyOrHeadingCluster():
	tree = _summary(interactiveControlCount=15)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.APP


# ---------------------------------------------------------------------------
# NOTICE
# ---------------------------------------------------------------------------


def test_noticeWithKeywordMatchIsHighConfidence():
	# Google Forms closed page shape — small, one heading, status sentence.
	tree = _summary(
		noticeKeywordMatch=True,
		mainNodes=[
			_node("heading", 28, level=1, preview="Web App Accessibility Survey"),
			_node("paragraph", 130, preview="The form ... is no longer accepting responses"),
			_node("paragraph", 50),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.NOTICE
	assert result.confidence >= 0.85


def test_noticeWithoutKeywordLowerConfidenceButStillFires():
	# Small page with one heading and a short status sentence — no keyword.
	tree = _summary(
		mainNodes=[
			_node("heading", 28, level=1),
			_node("paragraph", 45),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.NOTICE


def test_noticeDoesNotFireOnRealArticlePages():
	# Real article with body cluster — ARTICLE must win, not NOTICE.
	tree = _summary(
		mainNodes=[
			_node("heading", 40, level=1),
			_node("paragraph", 250),
			_node("paragraph", 300),
			_node("paragraph", 280),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.ARTICLE


def test_shapeOnlyNoticeDeclinesWhenCountsTruncated():
	# Same shape as the shape-only NOTICE above, but the counts phase hit
	# its wall-clock budget — interactiveControlCount may be a huge
	# undercount (a busy page reading as 0 controls). Shape evidence IS
	# small counts, so shape-only NOTICE must decline and leave the page
	# to the 1500 ms retry, which will see honest counts.
	tree = _summary(
		countsTruncated=True,
		mainNodes=[
			_node("heading", 28, level=1),
			_node("paragraph", 45),
		],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.NOTICE


def test_keywordNoticeSurvivesCountsTruncated():
	# The keyword path rests on real walked TEXT (status keyword), not on
	# counts, so a truncated count phase must not silence a genuine
	# "no longer accepting responses" page.
	tree = _summary(
		countsTruncated=True,
		noticeKeywordMatch=True,
		mainNodes=[
			_node("heading", 28, level=1, preview="Web App Accessibility Survey"),
			_node("paragraph", 130, preview="The form ... is no longer accepting responses"),
			_node("paragraph", 50),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.NOTICE


def test_noticeBlockedByTooManyHeadings():
	# Many headings = not a notice page.
	tree = _summary(
		mainNodes=[
			_node("heading", 30, level=1),
			_node("heading", 20, level=2),
			_node("heading", 20, level=2),
			_node("heading", 20, level=2),
			_node("heading", 20, level=2),
			_node("paragraph", 40),
		],
		noticeKeywordMatch=True,
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.NOTICE


# ---------------------------------------------------------------------------
# KEY_RESULT — label + value [+ unit] widget pattern.
# ---------------------------------------------------------------------------


def test_keyResultFiresForFastComStyleSpeedWidget():
	# Pattern: short language-link chrome, then label / value / unit.
	# No body cluster, no headings — pure widget page.
	tree = _summary(
		mainNodes=[
			_node("paragraph", 8, preview="English"),
			_node("paragraph", 9, preview="Español"),
			_node("paragraph", 22, preview="Your Internet speed is"),  # label
			_node("paragraph", 3, preview="170"),  # value
			_node("paragraph", 4, preview="Mbps"),  # unit
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.KEY_RESULT


def test_keyResultHandlesCaveatBetweenValueAndUnit():
	# fast.com renders a caveat paragraph between the value and the unit
	# when the connection is unstable. As long as the unit appears within
	# the lookahead window AND no PARAGRAPH_MIN_CHARS body paragraph stops
	# the search, the pattern matches.
	# 80 chars stays under PARAGRAPH_MIN_CHARS=100 so the lookahead can
	# still reach "Mbps".
	tree = _summary(
		mainNodes=[
			_node("paragraph", 22, preview="Your Internet speed is"),
			_node("paragraph", 3, preview="170"),
			_node("paragraph", 80, preview="* Your network is unstable. Estimate only."),
			_node("paragraph", 4, preview="Mbps"),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.KEY_RESULT


def test_keyResultFiresWithImplicitUnitInValue():
	# "85%" — the % IS the unit, no separate node needed.
	tree = _summary(
		mainNodes=[
			_node("paragraph", 13, preview="Battery level"),
			_node("paragraph", 3, preview="85%"),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.KEY_RESULT


def test_keyResultDeclinesWhenCountsTruncated():
	# KEY_RESULT's whole premise is "few controls, no form" — both gates
	# lean on counts being real. A budget-truncated count phase can report
	# 0 controls on a control-dense page, so KEY_RESULT must decline.
	tree = _summary(
		countsTruncated=True,
		mainNodes=[
			_node("paragraph", 22, preview="Your Internet speed is"),
			_node("paragraph", 3, preview="170"),
			_node("paragraph", 4, preview="Mbps"),
		],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.KEY_RESULT


def test_keyResultDoesNotFireWhenBodyClusterPrecedes():
	# Article with "Score: 5" mentioned inline AFTER a body paragraph.
	# Body cluster wins (real article); KEY_RESULT skipped.
	tree = _summary(
		mainNodes=[
			_node("paragraph", 250),  # body
			_node("paragraph", 220),  # body
			_node("paragraph", 12, preview="Final score"),
			_node("paragraph", 3, preview="2-1"),
		],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.KEY_RESULT


def test_keyResultDoesNotFireWithoutUnitOrImplicitUnit():
	# "Final score: 5" with no Mbps/min/% etc. after, and no $/%/° in
	# value — pattern is ambiguous, do NOT fire.
	tree = _summary(
		mainNodes=[
			_node("paragraph", 11, preview="Final score"),
			_node("paragraph", 1, preview="5"),
			_node("paragraph", 30, preview="That is the final tally for the game"),
		],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.KEY_RESULT


def test_keyResultDoesNotFireOnAppsWithManyControls():
	# Dashboard with 15 controls — even if a label/value/unit triplet
	# exists, KEY_RESULT must yield to APP / etc.
	tree = _summary(
		interactiveControlCount=15,
		mainNodes=[
			_node("paragraph", 22, preview="Your Internet speed is"),
			_node("paragraph", 3, preview="170"),
			_node("paragraph", 4, preview="Mbps"),
		],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.KEY_RESULT


def test_keyResultDoesNotFireOnFormPages():
	# Pages with form inputs should fall through to FORM logic, not steal
	# the user with a coincidental label/value/unit.
	tree = _summary(
		formInputCount=4,
		mainNodes=[
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


def test_unknownWhenNoSignal():
	tree = _summary()
	result = cls.classify(tree)
	assert result.intent == cls.Intent.UNKNOWN
	assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# Legal footer boilerplate vs hero (Zoom webinar registration regression)
# ---------------------------------------------------------------------------


def _boilerplateNode(length, preview=""):
	return cls.MainNode(
		kind="paragraph",
		textLength=length,
		textPreview=preview,
		isBoilerplate=True,
	)


def test_copyrightFooterAloneIsNotAnArticleHero():
	# Pre-hydration Zoom webinar registration shell: the ONLY substantial
	# paragraph is the footer copyright (flagged at walk time). It must not
	# qualify as a hero, so the page must NOT classify as ARTICLE — leaving
	# no landing and letting the caller's retry wait for hydration.
	tree = _summary(
		hasMainLandmark=False,
		interactiveControlCount=8,
		mainNodes=[
			_node("paragraph", 20, preview="Skip to Main Content"),
			_node("paragraph", 22, preview="Accessibility Overview"),
			_node("paragraph", 7, preview="Support"),
			_boilerplateNode(69, preview="Copyright ©2026 Zoom Video Communications, Inc. All rights"),
		],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.ARTICLE


def test_formNotBlockedByFooterCopyrightPseudoHero():
	# A plain 3-input form page whose only 50+ char paragraph is the footer
	# copyright. Before the boilerplate-aware hero computation, that line
	# created hasHero=True and blocked FORM (weak form signal), leaving the
	# page unhandled. The copyright must not count as a hero.
	tree = _summary(
		formInputCount=3,
		mainNodes=[
			_node("heading", 20, level=1, preview="Contact us"),
			_boilerplateNode(69, preview="Copyright ©2026 Example Corp. All rights reserved."),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.FORM


def test_hydratedZoomRegistrationClassifiesAsForm():
	# The REAL hydrated Zoom webinar registration page (measured 2026-07-06):
	# H1 title (81 chars), one 1958-char description block, 7 form inputs,
	# footer copyright. Strong form signal (>= 5 inputs) must win — the
	# description hero does not block, and the copyright stays irrelevant.
	tree = _summary(
		url="https://us02web.zoom.us/webinar/register/WN_abc#/registration",
		formInputCount=7,
		interactiveControlCount=12,
		mainNodes=[
			_node(
				"heading", 81, level=1, preview="AI as Assistive Technology: A Practical Stack for Entrepren"
			),
			_node("heading", 20, level=2, preview="Webinar Registration"),
			_node("paragraph", 1958, preview="Whether you're starting your business or scaling one, AI is"),
			_boilerplateNode(69, preview="Copyright ©2026 Zoom Video Communications, Inc. All rights"),
		],
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.FORM


def test_zoomRegistrationConfirmationClassifiesAsNotice():
	# The post-registration page (2026-07-06 debug log): 6 nodes, H1 "You
	# have successfully registered" (32 chars), short paragraphs, ONE form
	# field (the "Add to calendar" widget counts in NVDA's formField
	# class), 2 interactives. The old NOTICE gate required zero form
	# fields, so this classified UNKNOWN and the user got the not-found
	# beeps on a page that is the textbook NOTICE case.
	tree = _summary(
		url="https://us02web.zoom.us/rest/webinar/registrant/WN_abc/info?ac=approved",
		formInputCount=1,
		interactiveControlCount=2,
		noticeKeywordMatch=True,
		mainNodes=[
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


def test_shapeOnlyNoticeStillRequiresZeroFormFields():
	# A small login-ish page (2 inputs, H1, short text, no status keyword)
	# must NOT become a NOTICE just because the keyword path now tolerates
	# form fields — the 0.65 shape-only path keeps the zero-fields gate.
	tree = _summary(
		formInputCount=2,
		interactiveControlCount=4,
		mainNodes=[
			_node("heading", 7, level=1, preview="Sign in"),
			_node("paragraph", 35, preview="Enter your username and password."),
		],
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.NOTICE


# ---------------------------------------------------------------------------
# Massive-duo FORM block (armstrongeconomics newsletter-widget regression)
# ---------------------------------------------------------------------------


def test_blogWithMassiveParagraphPairIsNotForm():
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
		hasMainLandmark=False,
		articleCount=0,
		mainNodes=nodes,
		formInputCount=6,
		interactiveControlCount=11,
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.ARTICLE


def test_registerUrlWithMassiveDescriptionStaysForm():
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
		hasMainLandmark=True,
		articleCount=0,
		mainNodes=nodes,
		formInputCount=7,
		interactiveControlCount=9,
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.FORM


def test_massiveDuoRequiresAdjacency():
	# Two big paragraphs separated by a heading are sections, not a body
	# duo — the helper itself must not fire.
	nodes = [
		_node("paragraph", 300),
		_node("heading", 20, level=2),
		_node("paragraph", 300),
	]
	assert cls._hasMassiveParagraphDuo(nodes) is False
	nodesAdjacent = [
		_node("paragraph", 300),
		_node("paragraph", 300),
	]
	assert cls._hasMassiveParagraphDuo(nodesAdjacent) is True


def test_editorialUrlBlocksFormOnPodcastPage():
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
		hasMainLandmark=False,
		articleCount=0,
		mainNodes=nodes,
		formInputCount=10,
		interactiveControlCount=11,
	)
	result = cls.classify(tree)
	assert result.intent != cls.Intent.FORM


def test_editorialUrlDoesNotBlockFormWhenUrlAlsoMatchesForm():
	# /blog/contact matches both ARTICLE (/blog/) and FORM (/contact) —
	# FORM must stay eligible.
	nodes = [
		_node("heading", 10, level=1, preview="Contact Us"),
		_node("paragraph", 30, preview="Send us a message below."),
	]
	tree = _summary(
		url="https://example.com/blog/contact",
		hasMainLandmark=True,
		articleCount=0,
		mainNodes=nodes,
		formInputCount=5,
		interactiveControlCount=6,
	)
	result = cls.classify(tree)
	assert result.intent == cls.Intent.FORM


# ---------------------------------------------------------------------------
# Form-input counting: the count is now REAL INPUTS ONLY
#
# treeSummary used to fill formInputCount from NVDA's "formField" quick-nav
# type, which counts BUTTONS as form fields. A control-dense CONTENT page
# therefore maxed the counter (IMDb title pages and a TV station front page both
# reported 10) and classified as FORM -- and the bare-form branch MOVED THE
# USER'S KEYBOARD FOCUS into the site's search box.
#
# It now counts only edit / comboBox / checkBox / radioButton, so the honest
# numbers are much smaller, and STRONG_FORM_INPUT_COUNT came down 5 -> 4 to
# match. These tests pin BOTH sides of that boundary.
# ---------------------------------------------------------------------------


def test_contentPageWithOneSearchBoxIsNotAForm():
	# IMDb / a TV station front page: lots of buttons, ONE real search box, and
	# a single substantial content paragraph. Must not be FORM -- FORM is the
	# branch that hijacks the user's focus.
	nodes = [
		_node("heading", 14, level=1, preview="The Dark Knight"),
		_node("paragraph", 166, preview="When a menace known as the Joker wreaks havoc and chaos on the"),
	]
	result = cls.classify(
		_summary(
			mainNodes=nodes,
			formInputCount=1,  # the search box, and nothing else
			interactiveControlCount=11,  # buttons galore -- must not matter
		)
	)
	assert result.intent != cls.Intent.FORM


def test_registrationFormWithFourRealInputsIsAForm():
	# Wikipedia Special:CreateAccount -- username, password, confirm, email.
	# Honest count is 4. With STRONG_FORM_INPUT_COUNT left at 5 this fell below
	# the bar, the hero-paragraph gate blocked FORM, and a genuine registration
	# form classified as an ARTICLE -- landing the user on the help text NEXT TO
	# the form instead of in it. Casey hit exactly that.
	nodes = [
		_node("heading", 16, level=1, preview="Create account"),
		_node("paragraph", 120, preview="Email is required to recover your account if you lose your pass"),
	]
	result = cls.classify(
		_summary(
			mainNodes=nodes,
			formInputCount=4,
			interactiveControlCount=11,
		)
	)
	assert result.intent == cls.Intent.FORM


def test_accountCreationUrlIsAFormUrlNotAnArticleUrl():
	# Wikipedia's account-creation page redirects to
	# auth.wikimedia.org/enwiki/wiki/Special:CreateAccount. That path contains
	# "/wiki/", which matches the ARTICLE url hints, so hasEditorialUrl blocked
	# FORM and a registration form classified as an encyclopedia article --
	# landing the user on the help text BESIDE the form instead of in it.
	nodes = [
		_node("heading", 16, level=1, preview="Create account"),
		_node("paragraph", 120, preview="Email is required to recover your account if you lose your pass"),
	]
	result = cls.classify(
		_summary(
			url="https://auth.wikimedia.org/enwiki/wiki/Special:CreateAccount",
			mainNodes=nodes,
			formInputCount=4,
			interactiveControlCount=11,
		)
	)
	assert result.intent == cls.Intent.FORM


def test_wikiArticleUrlStillReadsAsEditorial():
	# The guard above must not turn every /wiki/ page into a form. An ordinary
	# encyclopedia article with a search box stays an ARTICLE.
	nodes = [
		_node("heading", 20, level=1, preview="Battle of Midway"),
		_node("paragraph", 240, preview="The Battle of Midway was a major naval battle."),
		_node("paragraph", 210, preview="It took place from June 4 to 7, 1942."),
		_node("paragraph", 190, preview="The United States Navy defeated an attacking fleet."),
	]
	result = cls.classify(
		_summary(
			url="https://en.wikipedia.org/wiki/Battle_of_Midway",
			mainNodes=nodes,
			formInputCount=1,
			interactiveControlCount=11,
		)
	)
	assert result.intent != cls.Intent.FORM


def test_surveyUrlIsAFormNotAnArticle():
	# WebAIM Screen Reader User Survey #11 questions page (2026-07-20):
	# webaim.org/projects/screenreadersurvey11/survey. NVDA reports article=1
	# (the theme wraps the survey body in <article>) and 10 real form inputs.
	# The single <article> tripped hasEditorialContent and, with no form-URL
	# hint, blocked FORM -- so the page fell to the ARTICLE hero fallback (0.75)
	# and findArticleLanding's largest-paragraph fallback landed the user on
	# the LONGEST question label (Q13, 166 chars), mid-form. Every question is
	# separated by its short answer options, so no <article>+body-cluster and
	# no 3-in-a-row cluster ever forms to reach the right pick. The fix is the
	# same escape hatch /register and /contact use: a /survey URL is a form URL.
	nodes = [
		_node("heading", 29, level=1, preview="Screen Reader User Survey #11"),
		_node("paragraph", 13, preview="You are here:"),
		_node("paragraph", 54, preview="Home > WebAIM Projects > Screen Reader U"),
		_node("heading", 16, level=2, preview="Survey Questions"),
		_node("paragraph", 29, preview="1. Please select your region."),
		_node("paragraph", 11, preview="No Response"),
		_node("paragraph", 50, preview="2. Do you use a screen reader due to a d"),
		_node("paragraph", 3, preview="Yes"),
		_node("paragraph", 74, preview="3. Which of the following disabilities d"),
		_node("paragraph", 3, preview="Yes"),
		_node("paragraph", 51, preview="5. Please rate your proficiency using th"),
		_node("paragraph", 8, preview="Advanced"),
		_node("paragraph", 100, preview="10. Which of the following desktop/lapto"),
		_node("paragraph", 6, preview="JAWS"),
		_node("paragraph", 166, preview="13. Do you see free or low-cost desktop screen rea"),
		_node("paragraph", 5, preview="Never"),
		_node("paragraph", 124, preview="22. When navigating a web page by heading"),
		_node("paragraph", 8, preview="Somewhat"),
	]
	result = cls.classify(
		_summary(
			url="https://webaim.org/projects/screenreadersurvey11/survey",
			mainNodes=nodes,
			articleCount=1,
			formInputCount=10,
			interactiveControlCount=11,
		)
	)
	assert result.intent == cls.Intent.FORM


def test_surveyingArticleWithBodyClusterStaysEditorial():
	# Guard the /survey URL hint against its substring collision: a land-
	# SURVEYING company's article at /surveying-services contains "/survey".
	# The URL hint must only ever UNBLOCK a page that already looks like a
	# form -- a real article body (3+ substantial adjacent paragraphs) must
	# still block FORM via hasBodyClusterStrong, which has no URL hatch.
	nodes = [
		_node("heading", 24, level=1, preview="Boundary Surveying Services"),
		_node("paragraph", 240, preview="A boundary survey establishes the legal property l"),
		_node("paragraph", 210, preview="Our licensed surveyors use GPS and total stations t"),
		_node("paragraph", 190, preview="We deliver a stamped plat suitable for recording wi"),
	]
	result = cls.classify(
		_summary(
			url="https://example.com/surveying-services",
			mainNodes=nodes,
			articleCount=1,
			formInputCount=4,
			interactiveControlCount=6,
		)
	)
	assert result.intent != cls.Intent.FORM
