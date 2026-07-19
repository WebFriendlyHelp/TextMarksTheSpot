# -*- coding: UTF-8 -*-
# TMTS probe — can the control field stack replace NVDAObjectAtStart?
#
# Source review of the INSTALLED NVDA (library.zip bytecode) established that
# Gecko_ia2_TextInfo._normalizeControlField sets field['role'] (a
# controlTypes.Role member) and field['level'] (a raw STRING), and that
# storage.cpp emits the whole ancestor chain of control tags for any range.
# What source CANNOT tell us is what real pages actually produce. This probe
# answers exactly that, and nothing else.
#
# Read-only. No cursor moves, no speech, no tones. Log lines only.
# Press NVDA+shift+f on a loaded page, then grep the log for
# [TMTS probe-fields]. Disagreements are tagged DISAGREE.

import time

import api
import controlTypes
import globalPluginHandler
import textInfos
from logHandler import log
from scriptHandler import script

_MAX_CHUNKS = 40


# Chrome landmark types, copied from tree_summary._CHROME_LANDMARK_TYPES so the
# probe scores the production rule and not a paraphrase of it.
_CHROME_LANDMARK_TYPES = frozenset({
	"navigation", "banner", "contentinfo", "complementary", "search",
})

_PARENT_WALK_MAX_DEPTH = 30  # matches tree_summary._in_scope


# Copied from tree_summary so the probe compares the decision the PRODUCTION
# code actually makes. _node_for is a three-way decision -- heading, skip, or
# paragraph -- and the skip branch turns on these exact role names. Comparing
# role strings alone would score BUTTON against PARAGRAPH as agreement, which
# is the gap that made the first version of this probe unable to fail.
_PARAGRAPH_SKIP_ROLES_NAMES = (
	"GRAPHIC", "SEPARATOR", "UNKNOWN",
	"BUTTON", "TOGGLEBUTTON",
)


def _decision(role_name, level, text):
	# The _node_for decision, reduced to what a comparison needs.
	if role_name == "HEADING":
		return f"heading(level={level})"
	if role_name in _PARAGRAPH_SKIP_ROLES_NAMES:
		return "skip"
	if not (text or "").strip():
		return "skip"
	return "paragraph"


def _stack_from_fields(fields):
	# The LEADING RUN of controlStart commands, outermost to innermost —
	# stopping at the first item that is not one.
	#
	# The first version of this probe scanned the WHOLE stream and continued
	# past text and controlEnd, so on a paragraph containing an inline image
	# the last controlStart (the GRAPHIC) won. That is not the ancestor stack
	# at the range start, and it reported agreement anyway because the
	# comparison below reduced roles to heading/skip/paragraph. Corrected
	# 2026-07-18 after adversarial review; NVDA's own
	# getEnclosingContainerRange breaks at the first non-controlStart item
	# (verified in the installed virtualBuffers/__init__.pyc).
	roles = []
	heading_field = None
	innermost = None
	for cmd in fields:
		if not isinstance(cmd, textInfos.FieldCommand):
			break
		if cmd.command != "controlStart":
			break
		field = cmd.field
		role = field.get("role")
		roles.append(getattr(role, "name", None) or str(role))
		innermost = field
		if role is controlTypes.Role.HEADING:
			heading_field = field
	return roles, heading_field, innermost


# ---------------------------------------------------------------------------
# LANDMARK ANCESTRY — the second question, added 2026-07-18.
#
# _in_scope buys the answer to "is this chunk inside a chrome landmark?" with a
# COM parent chain: 13-18 ms PER DEREFERENCE, measured 1497 ms of a 2026 ms walk
# on vovsoft and 1805 ms of 2175 ms on thurrott, and roughly 650 ms of every
# chrome-scoped counts phase. NVDA's own getEnclosingContainerRange answers a
# closely related question from the control field stack instead — it pops
# control fields and tests field.get("landmark") (verified in the INSTALLED
# virtualBuffers/__init__.pyc, not from documentation). If the leading run
# carries the landmark ancestors, the same answer is available in-process for
# well under a millisecond, and — unlike every positional design tried so far —
# it does NOT depend on the landmark enumeration being complete, which is the
# constraint that killed two previous implementations.
#
# WHAT WOULD MAKE THIS FAIL, stated before the run so the result cannot be
# rationalised afterwards:
#
#   - lm_disagree > 0. The field stack and the parent chain reach different
#     verdicts on the same chunk. Any nonzero count kills the substitution
#     until the cause is understood; a chunk of navigation served as content is
#     the release-blocker failure class for this add-on.
#   - The plausible mechanism for that: the vbuf may emit control fields only
#     for nodes it has attributes for, so the field stack could be SHALLOWER
#     than the object's parent chain and miss a landmark the chain finds. That
#     is precisely what this comparison is built to detect.
#
# AND THE HOLLOW-EVIDENCE CHECK, which this project has now been burned by
# twice: if lm_stack_any and lm_obj_any are BOTH 0, the run sampled no
# landmarks at all, lm_disagree=0 was unreachable, and the result establishes
# NOTHING. Read those two counters before believing the disagreement count.
# ---------------------------------------------------------------------------

def _landmark_verdict(landmark):
	# Mirrors _in_scope's no-main branch: "main" wins, a chrome type loses,
	# anything else keeps looking.
	lm = str(landmark).lower() if landmark else ""
	if lm == "main":
		return True
	if lm in _CHROME_LANDMARK_TYPES:
		return False
	return None


def _landmark_from_fields(fields):
	"""Walk the LEADING control run outermost-to-innermost and return
	(verdict, deciding_landmark, all_landmarks_seen).

	Outermost first, matching the parent chain's innermost-first walk in
	REVERSE — so the two can disagree when a page nests a landmark inside
	another. Recorded rather than resolved: the raw list is logged so a
	disagreement is diagnosable instead of merely counted.
	"""
	seen = []
	verdict = None
	deciding = None
	for cmd in fields:
		if not isinstance(cmd, textInfos.FieldCommand):
			break
		if cmd.command != "controlStart":
			break
		field = cmd.field
		lm = field.get("landmark")
		if lm:
			seen.append(str(lm))
	# Innermost landmark wins, to match the parent chain, which stops at the
	# FIRST landmark it meets walking up.
	for lm in reversed(seen):
		v = _landmark_verdict(lm)
		if v is not None:
			verdict, deciding = v, lm
			break
	return verdict, deciding, seen


def _landmark_from_object(obj):
	"""The PRODUCTION answer: _in_scope's parent chain, no-main branch.

	Returns (verdict, deciding_landmark, derefs, outcome) where outcome is one
	of "landmark" (a landmark decided it), "root" (ran out of ancestors
	cleanly), "capped" (hit the depth cap), or "error" (a parent dereference
	raised).

	The last two are logged because production currently turns BOTH into
	"in scope" — it breaks out of the loop and returns `main_obj is None`,
	which is True. That is "chrome not proven" being reported as "content
	proven", on the path that moves keyboard focus. This probe is the only
	thing that can say how often it actually happens on real pages.
	"""
	cur = obj
	derefs = 0
	for _ in range(_PARENT_WALK_MAX_DEPTH):
		if cur is None:
			return None, None, derefs, "root"
		lm = getattr(cur, "landmark", None) or getattr(cur, "landmarkType", None) or ""
		v = _landmark_verdict(lm)
		if v is not None:
			return v, str(lm), derefs, "landmark"
		try:
			derefs += 1
			cur = cur.parent
		except Exception:
			return None, None, derefs, "error"
	return None, None, derefs, "capped"


def _obj_heading_level(obj):
	# Copy of tree_summary._heading_level so the probe measures the CURRENT
	# production path, including its obj.IA2Attributes fallback (itself a COM
	# call). Do not "simplify" this to match the field-stack answer.
	for attr in ("level", "headingLevel"):
		value = getattr(obj, attr, None)
		if isinstance(value, int) and value > 0:
			return value
	try:
		ia2 = getattr(obj, "IA2Attributes", None) or {}
		raw = ia2.get("level")
		if raw is not None:
			return int(raw)
	except (TypeError, ValueError):
		pass
	return 0


class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	@script(
		description="TMTS probe: dump control field stack vs NVDAObjectAtStart",
		# NVDA+shift+f was taken: the `translate` add-on binds it, wins the
		# gesture, and the probe silently never fires. Casey's machine runs 25
		# add-ons, so pick something deliberately obscure rather than something
		# merely plausible.
		gesture="kb:NVDA+control+alt+f",
	)
	def script_field_stack_dump(self, gesture):
		focus = api.getFocusObject()
		ti = getattr(focus, "treeInterceptor", None) if focus else None
		if ti is None or not getattr(ti, "isReady", False):
			log.info("[TMTS probe-fields] no ready treeInterceptor on current focus")
			return
		url = getattr(ti, "documentConstantIdentifier", "") or ""

		# BACKEND ATTRIBUTION. Without this, a result set cannot be attributed
		# to an engine AFTER THE FACT, and the whole mechanism this probe
		# measures is backend-dependent: field["landmark"] is written by the
		# BACKEND's _normalizeControlField, not by any TextInfo contract. Gecko
		# writes it; Chromium inherits Gecko's virtual-buffer TextInfo and so
		# writes it too; WebKit's normalizer does not contain the string
		# "landmark" at all, so on WebKit every chunk would read "no landmark"
		# and all chrome would be admitted as content.
		#
		# LOG THE TEXTINFO CLASS, NOT JUST backendName. Chromium does NOT
		# declare a distinct backend name -- it inherits Gecko's "gecko_ia2" --
		# so backendName cannot distinguish them and a capability gate written
		# against the STRING would be gating on the wrong thing. The class name
		# is what a real gate should key on (isinstance against the Gecko
		# TextInfo, which Chromium passes by inheritance).
		backend = getattr(ti, "backendName", None)
		try:
			ti_cls = type(ti.makeTextInfo(textInfos.POSITION_FIRST)).__name__
		except Exception:
			ti_cls = "?"
		try:
			import buildVersion
			nvda_ver = buildVersion.version
		except Exception:
			nvda_ver = "?"
		log.info(
			f"[TMTS probe-fields] START url={url!r} max_chunks={_MAX_CHUNKS} "
			f"backend={backend!r} ti_class={ti_cls} nvda={nvda_ver} "
			f"ti_type={type(ti).__name__}"
		)

		try:
			info = ti.makeTextInfo(textInfos.POSITION_FIRST)
			info.expand(textInfos.UNIT_PARAGRAPH)
		except Exception as e:
			log.warning(f"[TMTS probe-fields] cannot start walk: {e}")
			return

		totals = {"fields": 0.0, "obj": 0.0, "level": 0.0, "lm_chain": 0.0}
		counts = {
			"chunks": 0, "disagree": 0, "empty": 0, "no_obj": 0, "no_control": 0,
			"disagree_innermost": 0, "disagree_heading_first": 0,
			"disagree_role_exact": 0, "trailing_control_chunks": 0,
			# Landmark ancestry. lm_stack_any / lm_obj_any are the
			# hollow-evidence guards: if BOTH are 0, the run sampled no
			# landmarks and lm_disagree=0 could never have been anything else.
			"lm_stack_any": 0, "lm_obj_any": 0, "lm_disagree": 0,
			"lm_chain_capped": 0, "lm_chain_error": 0, "lm_chain_derefs": 0,
		}

		for i in range(_MAX_CHUNKS):
			try:
				text = info.text or ""

				t0 = time.perf_counter()
				fields = info.getTextWithFields()
				t_fields = time.perf_counter() - t0

				t0 = time.perf_counter()
				obj = info.NVDAObjectAtStart
				t_obj = time.perf_counter() - t0

				totals["fields"] += t_fields
				totals["obj"] += t_obj
				counts["chunks"] += 1

				# Empty-range shapes identified in source: getTextWithFields
				# returns '' when start == end, _getFieldsInRange returns ['']
				# when the buffer yields no text.
				is_empty_range = fields == "" or fields == [""]
				if is_empty_range:
					counts["empty"] += 1
					log.info(
						f"[TMTS probe-fields] [{i}] EMPTY-RANGE fields={fields!r} "
						f"text={text[:40]!r}"
					)

				roles, heading_field, innermost = _stack_from_fields(fields)
				# How many chunks even CONTAIN a control command after the
				# leading run. If this is 0 the run sampled none of the shape
				# that broke the first implementation, and disagree_role_exact
				# proves nothing about it. Ask this of every unanimous result.
				if isinstance(fields, list):
					_lead = True
					for _c in fields:
						if _lead and isinstance(_c, textInfos.FieldCommand) and _c.command == "controlStart":
							continue
						_lead = False
						if isinstance(_c, textInfos.FieldCommand) and _c.command == "controlStart":
							counts["trailing_control_chunks"] += 1
							break
				# An empty range yields no control fields BY DEFINITION, and
				# chunks_with_no_control_field is a hard-kill criterion. Counting
				# empty ranges here would manufacture a false kill signal for a
				# sound approach, so they are excluded and tracked separately.
				if not roles and not is_empty_range:
					counts["no_control"] += 1

				# Field-stack answer.
				fs_level_raw = heading_field.get("level") if heading_field else None
				fs_level_type = type(fs_level_raw).__name__
				fs_is_heading = heading_field is not None
				start_of_node = innermost.get("_startOfNode") if innermost else None
				innermost_role = roles[-1] if roles else None

				# Production answer, timed separately.
				if obj is None:
					counts["no_obj"] += 1
					obj_role = None
					obj_level = 0
					t_level = 0.0
				else:
					obj_role = getattr(obj.role, "name", None) or str(obj.role)
					t0 = time.perf_counter()
					obj_level = _obj_heading_level(obj)
					t_level = time.perf_counter() - t0
					totals["level"] += t_level

				log.info(
					f"[TMTS probe-fields] [{i}] stack={roles} innermost={innermost_role!r} "
					f"_startOfNode={start_of_node!r} fs_heading={fs_is_heading} "
					f"fs_level={fs_level_raw!r} fs_level_type={fs_level_type} "
					f"obj_role={obj_role!r} obj_level={obj_level} "
					f"t_fields={t_fields * 1000:.2f}ms t_obj={t_obj * 1000:.2f}ms "
					f"t_level={t_level * 1000:.2f}ms text={text[:60]!r}"
				)

				# --- Landmark ancestry: field stack vs the production chain ---
				lm_fs_verdict, lm_fs_deciding, lm_fs_seen = _landmark_from_fields(
					fields if isinstance(fields, list) else []
				)
				if lm_fs_seen:
					counts["lm_stack_any"] += 1
				if obj is None:
					lm_obj_verdict = lm_obj_deciding = None
					lm_outcome, lm_derefs, t_lm = "no-object", 0, 0.0
				else:
					t0 = time.perf_counter()
					(
						lm_obj_verdict, lm_obj_deciding, lm_derefs, lm_outcome,
					) = _landmark_from_object(obj)
					t_lm = time.perf_counter() - t0
					totals["lm_chain"] += t_lm
					counts["lm_chain_derefs"] += lm_derefs
					if lm_outcome == "landmark":
						counts["lm_obj_any"] += 1
					elif lm_outcome == "capped":
						counts["lm_chain_capped"] += 1
					elif lm_outcome == "error":
						counts["lm_chain_error"] += 1
				# Compare the VERDICT, including None ("no landmark decided"),
				# because None-vs-False is exactly the miss that would serve
				# navigation as content.
				if obj is not None and lm_fs_verdict != lm_obj_verdict:
					counts["lm_disagree"] += 1
					log.info(
						f"[TMTS probe-fields] LANDMARK-MISMATCH [{i}] "
						f"fs={lm_fs_verdict!r} via={lm_fs_deciding!r} stack={lm_fs_seen} "
						f"obj={lm_obj_verdict!r} via={lm_obj_deciding!r} "
						f"outcome={lm_outcome} derefs={lm_derefs} "
						f"text={text[:60]!r}"
					)
				log.info(
					f"[TMTS probe-fields] LM [{i}] fs={lm_fs_verdict!r} "
					f"fs_landmarks={lm_fs_seen} obj={lm_obj_verdict!r} "
					f"obj_via={lm_obj_deciding!r} outcome={lm_outcome} "
					f"derefs={lm_derefs} t_chain={t_lm * 1000:.2f}ms"
				)

				# The whole point of the probe: compare the DECISION _node_for
				# would reach, not the role string. Two candidate selection
				# rules are scored separately, because which one to adopt is
				# an open question and this probe is the only thing that can
				# answer it empirically.
				#
				#   INNERMOST -- the deepest control field. This is the exact
				#     structural equivalent of NVDAObjectAtStart, so it is the
				#     rule that should score ZERO disagreements. Any mismatch
				#     here is evidence the substitution is NOT equivalent.
				#   HEADING-FIRST -- any HEADING on the stack wins, else the
				#     innermost role. Expected to DISAGREE with the object on
				#     heading-wrapping-a-link, and expected to be MORE correct
				#     there. Disagreements here are informative, not fatal.
				fs_level_int = 0
				try:
					if fs_level_raw is not None:
						fs_level_int = int(fs_level_raw)
				except (TypeError, ValueError):
					fs_level_int = -1

				obj_decision = _decision(obj_role, obj_level, text) if obj is not None else None
				dec_innermost = _decision(innermost_role, fs_level_int, text)
				dec_heading_first = _decision(
					"HEADING" if fs_is_heading else innermost_role, fs_level_int, text,
				)
				# EXACT role equality, not just the reduced decision. The
				# reduced form scores LINK against PARAGRAPH as agreement,
				# because both mean "paragraph" to _node_for — which is why
				# the first run reported disagree_innermost=0 while the
				# implementation was reading the wrong control field. A probe
				# that cannot distinguish those cannot validate the
				# substitution it exists to validate.
				if obj is not None and innermost_role != obj_role:
					counts["disagree_role_exact"] += 1
					log.info(
						f"[TMTS probe-fields] ROLE-MISMATCH [{i}] "
						f"fs={innermost_role!r} obj={obj_role!r} text={text[:60]!r}"
					)
				if dec_innermost != obj_decision:
					counts["disagree_innermost"] += 1
				if dec_heading_first != obj_decision:
					counts["disagree_heading_first"] += 1

				if obj is not None and (
					dec_innermost != obj_decision
					or dec_heading_first != obj_decision
				):
					counts["disagree"] += 1
					log.info(
						f"[TMTS probe-fields] DISAGREE [{i}] "
						f"object={obj_decision!r} innermost={dec_innermost!r} "
						f"heading_first={dec_heading_first!r} | "
						f"obj_role={obj_role!r} obj_level={obj_level} "
						f"fs_innermost_role={innermost_role!r} fs_heading={fs_is_heading} "
						f"fs_level={fs_level_int} stack={roles} | text={text[:60]!r}"
					)
			except Exception as e:
				log.warning(f"[TMTS probe-fields] [{i}] error: {e}")

			# Advance. Same iteration shape as the production walk: expand at
			# the collapsed end, and only force a move when that made no
			# forward progress (a bare collapse+move skips a paragraph when a
			# chunk ends exactly on the next paragraph's start boundary).
			try:
				nxt = info.copy()
				nxt.collapse(end=True)
				nxt.expand(textInfos.UNIT_PARAGRAPH)
				if nxt.compareEndPoints(info, "startToStart") <= 0:
					nxt = info.copy()
					nxt.collapse(end=True)
					if not nxt.move(textInfos.UNIT_PARAGRAPH, 1):
						break
					nxt.expand(textInfos.UNIT_PARAGRAPH)
				info = nxt
			except Exception as e:
				log.warning(f"[TMTS probe-fields] advance failed at [{i}]: {e}")
				break

		n = max(counts["chunks"], 1)
		log.info(
			f"[TMTS probe-fields] SUMMARY url={url!r} chunks={counts['chunks']} "
			f"disagree={counts['disagree']} "
			f"disagree_innermost={counts['disagree_innermost']} "
			f"disagree_heading_first={counts['disagree_heading_first']} "
			f"disagree_role_exact={counts['disagree_role_exact']} "
			f"trailing_control_chunks={counts['trailing_control_chunks']} "
			f"lm_disagree={counts['lm_disagree']} "
			f"lm_stack_any={counts['lm_stack_any']} "
			f"lm_obj_any={counts['lm_obj_any']} "
			f"lm_chain_capped={counts['lm_chain_capped']} "
			f"lm_chain_error={counts['lm_chain_error']} "
			f"lm_chain_derefs={counts['lm_chain_derefs']} "
			f"total_lm_chain={totals['lm_chain'] * 1000:.1f}ms "
			f"empty_ranges={counts['empty']} "
			f"chunks_with_no_control_field={counts['no_control']} "
			f"chunks_with_no_object={counts['no_obj']} "
			f"avg_t_fields={totals['fields'] / n * 1000:.2f}ms "
			f"avg_t_obj={totals['obj'] / n * 1000:.2f}ms "
			f"avg_t_level={totals['level'] / n * 1000:.2f}ms "
			f"total_fields={totals['fields'] * 1000:.1f}ms "
			f"total_obj_plus_level={(totals['obj'] + totals['level']) * 1000:.1f}ms"
		)
