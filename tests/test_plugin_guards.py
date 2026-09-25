"""Decision logic in the GlobalPlugin, driven through fakes (tests/nvda_stubs.py).

Each guard added by the 2026-09-24 security audit gets a positive test AND its
negative twin, because "the guard fires" proves nothing until "without the
condition, it does not" shows the check can fail at all. What these cannot
prove is real NVDA or real browser behaviour; that is the VM's job.
"""

import types

import pytest

import nvda_stubs
from nvda_stubs import REC

from classifier import MainNode, TreeSummary


@pytest.fixture(scope="module")
def plugin():
	return nvda_stubs.loadPlugin()


@pytest.fixture
def gp(plugin, monkeypatch):
	REC.__init__()
	monkeypatch.setattr(plugin.cfgMod, "load", lambda: None)
	monkeypatch.setattr(plugin.cfgMod, "isSiteDisabled", lambda h: False)
	for name in ("working", "progressStart", "progressStop", "notFound"):
		monkeypatch.setattr(plugin.fbMod, name, lambda: None)
	return plugin.GlobalPlugin()


# --- Fakes -------------------------------------------------------------------


class Pos:
	"""A TextInfo stand-in: an offset into a list of paragraph texts."""

	def __init__(self, doc, offset):
		self.doc = doc
		self.offset = offset
		self.caretMoves = doc.caretMoves

	def copy(self):
		return Pos(self.doc, self.offset)

	def collapse(self, end=False):
		pass

	def expand(self, unit):
		pass

	@property
	def text(self):
		paras = self.doc.paras
		return paras[self.offset] if 0 <= self.offset < len(paras) else ""

	def compareEndPoints(self, other, which):
		return (self.offset > other.offset) - (self.offset < other.offset)

	def updateCaret(self):
		self.doc.caret = self.offset
		self.caretMoves.append(self.offset)


class Doc:
	def __init__(self, paras):
		self.paras = list(paras)
		self.caret = 0
		self.caretMoves = []


def makeTi(plugin, url, paras=("",), caret=0):
	class TI(nvda_stubs.BrowseModeDocumentTreeInterceptor):
		pass

	ti = TI()
	ti.documentConstantIdentifier = url
	ti.isReady = True
	ti.passThrough = False
	ti.doc = Doc(paras)
	ti.doc.caret = caret
	ti.makeTextInfo = lambda where: Pos(ti.doc, ti.doc.caret if where == "caret" else 0)
	return ti


def focusOn(ti):
	REC.focus = types.SimpleNamespace(treeInterceptor=ti)
	return REC.focus


def para(text):
	return MainNode(kind="paragraph", textLength=len(text), textPreview=text[:60])


# --- Mail-scheme skip on the ready path ---------------------------------------


def test_mailDocumentIsRecognisedOnlyByAMailScheme(plugin):
	isMail = plugin._isMailDocument
	assert isMail(types.SimpleNamespace(documentConstantIdentifier="imap://me@host/INBOX;UID=4"))
	assert isMail(types.SimpleNamespace(documentConstantIdentifier="mailbox:///C:/mail/Inbox?number=9"))
	# Functionality that must survive: pages that are not http but were always
	# detected, and a ready TI whose URL could not be read at all.
	assert not isMail(types.SimpleNamespace(documentConstantIdentifier="https://example.com/a"))
	assert not isMail(types.SimpleNamespace(documentConstantIdentifier="about:reader?url=https://x.org"))
	assert not isMail(types.SimpleNamespace(documentConstantIdentifier=""))
	assert not isMail(types.SimpleNamespace(documentConstantIdentifier=None))


def _captureFireTi(gp, monkeypatch):
	calls = []
	monkeypatch.setattr(gp, "_maybeFireTi", lambda ti, bypassExclusion=False: calls.append(bypassExclusion))
	return calls


def test_readyMailDocumentIsNotAutoLanded(plugin, gp, monkeypatch):
	calls = _captureFireTi(gp, monkeypatch)
	ti = makeTi(plugin, "imap://me@host/INBOX;UID=4")
	gp._maybeFire(types.SimpleNamespace(treeInterceptor=ti))
	assert calls == []


def test_readyWebAndUnreadableUrlDocumentsStillFire(plugin, gp, monkeypatch):
	calls = _captureFireTi(gp, monkeypatch)
	for url in ("https://example.com/", "", "about:reader?url=https://x.org"):
		gp._maybeFire(types.SimpleNamespace(treeInterceptor=makeTi(plugin, url)))
	assert calls == [False, False, False]


def test_explicitRequestStillWorksInAMailDocument(plugin, gp, monkeypatch):
	calls = _captureFireTi(gp, monkeypatch)
	gp._maybeFire(
		types.SimpleNamespace(treeInterceptor=makeTi(plugin, "imap://x/INBOX")), bypassExclusion=True
	)
	assert calls == [True]


# --- Delayed callbacks abandon when the user is in another document -----------


def test_focusElsewhereMeansAnotherTreeInterceptor(plugin, gp):
	a = makeTi(plugin, "https://a.example/")
	b = makeTi(plugin, "https://b.example/")
	focusOn(b)
	assert plugin._focusIsOnAnotherDocument(a)
	focusOn(a)
	assert not plugin._focusIsOnAnotherDocument(a)
	# Focus with no document (menu, address bar mid-load) is NOT elsewhere.
	REC.focus = types.SimpleNamespace(treeInterceptor=None)
	assert not plugin._focusIsOnAnotherDocument(a)
	REC.focus = None
	assert not plugin._focusIsOnAnotherDocument(a)


def _captureDetection(gp, monkeypatch):
	runs = []
	monkeypatch.setattr(gp, "_runDetection", lambda ti, attempt=0: runs.append(ti))
	return runs


def test_retryAbandonsWhenTheUserSwitchedTabs(plugin, gp, monkeypatch):
	runs = _captureDetection(gp, monkeypatch)
	a = makeTi(plugin, "https://a.example/")
	focusOn(makeTi(plugin, "https://b.example/"))
	gp._fireRetry(a, "https://a.example/", None, attempt=1)
	assert runs == []


def test_retryStillRunsWhenTheUserIsOnThePage(plugin, gp, monkeypatch):
	runs = _captureDetection(gp, monkeypatch)
	a = makeTi(plugin, "https://a.example/")
	focusOn(a)
	gp._fireRetry(a, "https://a.example/", None, attempt=1)
	assert runs == [a]


def test_readinessPollAbandonsWhenTheUserSwitchedTabs(plugin, gp, monkeypatch):
	calls = _captureFireTi(gp, monkeypatch)
	a = makeTi(plugin, "https://a.example/")
	focusOn(makeTi(plugin, "https://b.example/"))
	gp._fireReadyPoll(types.SimpleNamespace(treeInterceptor=a), False, 1)
	assert calls == []
	focusOn(a)
	gp._fireReadyPoll(types.SimpleNamespace(treeInterceptor=a), False, 1)
	assert calls == [False]


# --- Shift+Z verifies before it moves -----------------------------------------

LEDE = "The lede paragraph of the article, long enough to be a real landing."
OTHER = "A different paragraph that the re-rendered page moved into that slot."


def _saveLanding(gp, ti, offset, text):
	gp._lastInitialLandingInfo = Pos(ti.doc, offset)
	gp._lastInitialLandingUrl = ti.documentConstantIdentifier
	gp._lastInitialLandingNode = para(text)
	import weakref

	gp._lastInitialLandingTiRef = weakref.ref(ti)


def _refindIn(plugin, monkeypatch, calls):
	def find(ti, needle, verify=None):
		calls.append(ti)
		for i, text in enumerate(ti.doc.paras):
			if text.startswith(needle[:24]):
				return Pos(ti.doc, i)
		return None

	monkeypatch.setattr(plugin.tsMod, "findLandingByText", find)


def test_shiftZReturnsToAnIntactSavedLanding(plugin, gp, monkeypatch):
	finds = []
	_refindIn(plugin, monkeypatch, finds)
	ti = makeTi(plugin, "https://a.example/", ["nav", LEDE, "more"], caret=2)
	focusOn(ti)
	_saveLanding(gp, ti, 1, LEDE)
	gp.script_returnToLanding(gesture=None)
	assert ti.doc.caretMoves == [1]
	assert finds == [], "an intact bookmark needs no re-find"


def test_shiftZReFindsADriftedLandingByText(plugin, gp, monkeypatch):
	finds = []
	_refindIn(plugin, monkeypatch, finds)
	# The page re-rendered: offset 1 now holds OTHER, the lede moved to 3.
	ti = makeTi(plugin, "https://a.example/", ["nav", OTHER, "x", LEDE], caret=0)
	focusOn(ti)
	_saveLanding(gp, ti, 1, LEDE)
	gp.script_returnToLanding(gesture=None)
	assert ti.doc.caretMoves == [3], "moved to the stale offset instead of the paragraph"
	assert REC.spoken and REC.spoken[-1].text == LEDE


def test_shiftZReDetectsWhenTheLandingIsGone(plugin, gp, monkeypatch):
	finds = []
	_refindIn(plugin, monkeypatch, finds)
	fired = []
	monkeypatch.setattr(gp, "_maybeFire", lambda obj, bypassExclusion=False: fired.append(bypassExclusion))
	ti = makeTi(plugin, "https://a.example/", ["nav", OTHER], caret=0)
	focusOn(ti)
	_saveLanding(gp, ti, 1, LEDE)
	gp.script_returnToLanding(gesture=None)
	assert ti.doc.caretMoves == [], "read a paragraph that is not the landing"
	assert fired == [True], "should compute a fresh landing instead of giving up"


def test_shiftZInASecondTabOnTheSameUrlUsesThatTab(plugin, gp, monkeypatch):
	finds = []
	_refindIn(plugin, monkeypatch, finds)
	first = makeTi(plugin, "https://a.example/", ["nav", LEDE])
	second = makeTi(plugin, "https://a.example/", ["banner", "nav", LEDE])
	_saveLanding(gp, first, 1, LEDE)
	focusOn(second)
	gp.script_returnToLanding(gesture=None)
	assert first.doc.caretMoves == [], "moved the caret in the OTHER tab's document"
	assert second.doc.caretMoves == [2]
	assert finds == [second]


# --- Z walks again from the cursor on a page too long for one walk ------------


def _summary(nodes, truncated=False, fellBack=False, doc=None, base=0):
	s = TreeSummary(url="https://long.example/")
	s.mainNodes = nodes
	s.walkTruncated = truncated
	s.scopeFellBack = fellBack
	s._positions = [Pos(doc, base + i) for i in range(len(nodes))]
	return s


def _wireSummaries(plugin, monkeypatch, first, second, walks):
	def build(ti, startInfo=None):
		walks.append(startInfo)
		return first if startInfo is None else second

	monkeypatch.setattr(plugin.tsMod, "buildTreeSummary", build)
	monkeypatch.setattr(plugin.tsMod, "releaseSummary", lambda s: None)
	monkeypatch.setattr(plugin.tsMod, "getLandingTextinfo", lambda s, i: s._positions[i])


BODY = "A body paragraph that is comfortably longer than the fifty character bar."


def test_zWalksAgainFromTheCursorWhenTheFirstWalkWasCutShort(plugin, gp, monkeypatch):
	ti = makeTi(plugin, "https://long.example/", [BODY] * 600, caret=400)
	first = _summary([para(BODY)] * 300, truncated=True, doc=ti.doc)
	second = _summary([para(BODY)] * 5, doc=ti.doc, base=400)
	walks = []
	_wireSummaries(plugin, monkeypatch, first, second, walks)
	gp._scanForwardFromCaret(focusOn(ti))
	assert len(walks) == 2 and walks[1] is not None
	assert ti.doc.caretMoves == [401]
	assert "Nothing else to land on." not in REC.messages


def test_zDoesNotWalkTwiceWhenTheFirstWalkWasComplete(plugin, gp, monkeypatch):
	ti = makeTi(plugin, "https://short.example/", [BODY] * 10, caret=9)
	first = _summary([para(BODY)] * 10, truncated=False, doc=ti.doc)
	walks = []
	_wireSummaries(plugin, monkeypatch, first, None, walks)
	gp._scanForwardFromCaret(focusOn(ti))
	assert walks == [None]
	assert REC.messages == ["Nothing else to land on."]


def test_zSecondPassNeverLandsFromAFallenBackTree(plugin, gp, monkeypatch):
	ti = makeTi(plugin, "https://long.example/", [BODY] * 600, caret=400)
	first = _summary([para(BODY)] * 300, truncated=True, doc=ti.doc)
	second = _summary([para(BODY)] * 5, fellBack=True, doc=ti.doc, base=400)
	walks = []
	_wireSummaries(plugin, monkeypatch, first, second, walks)
	gp._scanForwardFromCaret(focusOn(ti))
	assert ti.doc.caretMoves == []
	assert REC.messages == ["Nothing else to land on."]


# --- NVDA+Z speaks what actually happened -------------------------------------


def _toggle(plugin, gp, monkeypatch, excluded, writeOk):
	state = {"excluded": excluded}
	monkeypatch.setattr(plugin.cfgMod, "isSiteDisabled", lambda h: state["excluded"])

	def add(h):
		if writeOk:
			state["excluded"] = True
		return writeOk

	def remove(h):
		if writeOk:
			state["excluded"] = False
		return writeOk

	monkeypatch.setattr(plugin.cfgMod, "addDisabledSite", add)
	monkeypatch.setattr(plugin.cfgMod, "removeDisabledSite", remove)
	nvda_stubs.FakeMessageDialog.answer = 5103  # wx.ID_YES
	focusOn(makeTi(plugin, "https://site.example/page"))
	gp.script_toggleSiteExclusion(gesture=None)
	return REC.messages[-1]


def test_exclusionToggleAnnouncesSuccess(plugin, gp, monkeypatch):
	assert _toggle(plugin, gp, monkeypatch, excluded=False, writeOk=True).startswith("Added")
	assert _toggle(plugin, gp, monkeypatch, excluded=True, writeOk=True).startswith("Removed")


def test_exclusionToggleAnnouncesAFailedWrite(plugin, gp, monkeypatch):
	assert _toggle(plugin, gp, monkeypatch, excluded=False, writeOk=False).startswith("Could not add")
	assert _toggle(plugin, gp, monkeypatch, excluded=True, writeOk=False).startswith("Could not remove")
