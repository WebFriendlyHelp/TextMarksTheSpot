---
paths:
  - "tests/test_scope_cache.py"
---

# test-scope-cache: full notes (from CLAUDE.md: Known limitations (deferred fixes))

Full text behind the one-line summaries in the root CLAUDE.md, moved here verbatim on 5 November 2026 to keep the always-loaded instructions small. Claude Code loads this file automatically when it reads or edits one of the paths above; other agents should read it before changing that code. Keep it accurate when the behavior changes, and keep the CLAUDE.md summary in step.

**The `id(obj)` memo inside `_inScope` was a wrong-answer bug, fixed 2026-07-18 — do not "simplify" the fix away.** It stored `{id(obj): bool}`, the bare address. Its ancestors are transient (NVDA caches each parent on its child, and NVDA's own instance registry is a `WeakKeyDictionary`, so the chain dies with the child when the walk rebinds `obj`), and CPython hands freed blocks back LIFO, so the next chunk's objects land on exactly the cached addresses. Measured: 2000 transient objects of one class occupied 2 distinct addresses. A dead entry therefore matched a live, unrelated object and handed it the dead one's verdict. Reproduced against the old code in `tests/test_scope_cache.py`: after 100 nav chunks, all 100 following CONTENT chunks answered out-of-scope. That empties `mainNodes`, which trips the unscoped fallback, which is why the symptom read as "the identity check unreliably fails" and why the recovered tree contains nav and footer — the bestmidi signature. The cache now stores `(obj, verdict)`, pinning the address, and verifies `entry[0] is obj` on hit so a dropped reference degrades to a miss instead of a wrong answer. Keying on the object instead does NOT work: `NVDAObject.__eq__` is logical (`_isEqual`) but `__hash__` is `super().__hash__()`, i.e. address-based, verified in NVDA's own bytecode.
