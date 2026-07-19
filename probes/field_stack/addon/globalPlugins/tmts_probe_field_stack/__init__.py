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

_MAX_CHUNKS = 20


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
	# Every controlStart command, outermost to innermost. Returns the role
	# name list, plus the innermost HEADING field if there is one, plus the
	# innermost field of any kind (which is what "is there a per-paragraph
	# control node" hinges on).
	roles = []
	heading_field = None
	innermost = None
	for cmd in fields:
		if not isinstance(cmd, textInfos.FieldCommand):
			continue
		if cmd.command != "controlStart":
			continue
		field = cmd.field
		role = field.get("role")
		roles.append(getattr(role, "name", None) or str(role))
		innermost = field
		if role is controlTypes.Role.HEADING:
			heading_field = field
	return roles, heading_field, innermost


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
		gesture="kb:NVDA+shift+f",
	)
	def script_field_stack_dump(self, gesture):
		focus = api.getFocusObject()
		ti = getattr(focus, "treeInterceptor", None) if focus else None
		if ti is None or not getattr(ti, "isReady", False):
			log.info("[TMTS probe-fields] no ready treeInterceptor on current focus")
			return
		url = getattr(ti, "documentConstantIdentifier", "") or ""
		log.info(f"[TMTS probe-fields] START url={url!r} max_chunks={_MAX_CHUNKS}")

		try:
			info = ti.makeTextInfo(textInfos.POSITION_FIRST)
			info.expand(textInfos.UNIT_PARAGRAPH)
		except Exception as e:
			log.warning(f"[TMTS probe-fields] cannot start walk: {e}")
			return

		totals = {"fields": 0.0, "obj": 0.0, "level": 0.0}
		counts = {
			"chunks": 0, "disagree": 0, "empty": 0, "no_obj": 0, "no_control": 0,
			"disagree_innermost": 0, "disagree_heading_first": 0,
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
			f"empty_ranges={counts['empty']} "
			f"chunks_with_no_control_field={counts['no_control']} "
			f"chunks_with_no_object={counts['no_obj']} "
			f"avg_t_fields={totals['fields'] / n * 1000:.2f}ms "
			f"avg_t_obj={totals['obj'] / n * 1000:.2f}ms "
			f"avg_t_level={totals['level'] / n * 1000:.2f}ms "
			f"total_fields={totals['fields'] * 1000:.1f}ms "
			f"total_obj_plus_level={(totals['obj'] + totals['level']) * 1000:.1f}ms"
		)
