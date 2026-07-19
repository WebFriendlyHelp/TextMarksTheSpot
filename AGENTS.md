# Text Marks the Spot Instructions

## Start Here

- Read `SPEC.md` first. It is the load-bearing source for locked decisions, shipped behavior, deferred phases, and build steps.
- Read `DEBUGGING.md` before diagnosing a landing or announcement incident. Read `CLAUDE.md` for architecture and repository conventions.

## Project Rules

- Never replace natural NVDA navigation or add speculative behavior outside the locked scope. Keep shipped behavior distinct from planned phases.
- Diagnose incidents from logs and fixtures before changing landing rules. Prefer one general fix with regression coverage over a site-specific patch.
- Use the documented SCons build and test workflow. Confirm the installed add-on is the build just produced before interpreting runtime results.
- Explicitly unload or shut down screen-reader integration on exit; never rely on object destruction.
- Update `SPEC.md`, `DEBUGGING.md`, changelog, or existing user documentation when their source-of-truth behavior changes.
- Add-on-store submission, release publication, and other outward actions require explicit approval.
