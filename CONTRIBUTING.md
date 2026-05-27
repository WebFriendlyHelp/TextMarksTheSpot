# Contributing to Text Marks the Spot

Thanks for being here.

Text Marks the Spot is an NVDA add-on, pure Python, that jumps the browse cursor to where real content starts on a web page. The thing the add-on cares about most is staying out of the way: keyboard-only use, screen reader correctness across NVDA's speech modes, low-vision usability, and clear user-facing wording.

## Before you start

Have a look at:

- `readme.md` for what the add-on does from a user perspective.
- `SPEC.md` for the design: guardrails, the intent classifier, the per-intent landing strategies, known limitations, and how we test.
- `CLAUDE.md` for the codebase tour, the build workflow, and which modules carry the weight today.

Then check existing [Issues](https://github.com/WebFriendlyHelp/textMarksTheSpot/issues) and [Discussions](https://github.com/WebFriendlyHelp/textMarksTheSpot/discussions) before opening something new. Discussions are for questions, ideas, and feedback. Issues are for confirmed bugs, regressions, and concrete feature work.

## Drive-by contributions

You do not need to be assigned to contribute.

If you want to work on an issue, leave a short comment so others can see it is in progress. For anything larger than a typo, open a draft PR early rather than waiting for assignment. Small doc fixes and focused test additions can go straight to a PR.

Labels like `claimed` or `needs maintainer` exist for coordination. They are not permission gates.

### Claiming work

The first person to comment with a clear plan normally gets priority on that issue. If a week passes with no visible progress, the issue may open back up. If your plans change, drop a quick comment so someone else can pick it up.

## Development setup

The build uses NV Access's official add-on template. SCons handles the actual packaging. Pure Python, no native libraries.

One-time tool install on Windows:

```powershell
python -m pip install --user scons markdown pytest
winget install --id mlocati.GetText
```

Then from the project root:

```powershell
# Build the .nvda-addon
scons

# Run the unit tests (classifier + landing logic, no NVDA needed)
python -m pytest tests/ -q

# Clean SCons build artifacts
scons -c
```

Install the resulting `textMarksTheSpot-<version>.nvda-addon` in NVDA via Tools, Manage add-ons, Install.

## Accessibility

Accessibility is what this add-on does, so the bar for accessibility inside the add-on is high.

Practical rules when making changes:

- Keep keyboard-only use working. The add-on never rebinds NVDA's built-in keys.
- Respect NVDA's speech mode. Route content speech through `speech.speak*` so it honors mode automatically. Functional status tones go through `tones.beep` directly and stay on across modes.
- Do not pre-cancel speech on page load. Cancel only at the moment your code actually has something to say.
- If the page placed focus on a real input, stay silent. The site already decided where the user should start.
- No emoji or Unicode box-drawing characters in any string that is spoken or shown in console output. Screen readers read each glyph aloud.
- Plain language in user-facing text.

If your change touches accessibility behavior, call it out in the pull request.

## AI-assisted contributions

AI-assisted work is allowed. It still has to be reviewable, and it still has to be safe to merge.

Read `AI_CODE_GENERATION_POLICY.md` before submitting AI-assisted changes. Treat generated output as a draft, not as code you trust by default. Keep changes small. Do not ask an AI tool to reproduce a specific third-party project, and discard output that looks copied. If AI assistance materially affected the change, mention it in the PR and say how you validated it.

## Pull request process

1. Fork the repo and branch from `main`.
2. If the PR is about an existing issue, link it in the PR body and say whether you commented on the issue first.
3. Keep changes focused. One concern per PR.
4. Update tests, docs, or `changelog.md` when they are affected.
5. Run `python -m pytest tests/ -q` before opening the PR. The pure-Python tests cover the classifier and landing logic. Behavior that touches NVDA APIs (events, tree walks, speech) is verified manually in NVDA.
6. Fill out the PR template.

## Maintainer notes

`main` is protected. Normal changes go through a PR and pass the required CI check. Direct pushes to `main` are not part of the normal flow.

Maintainers may bypass branch protection only for urgent fixes that need to reach users quickly, like a release-blocking issue.

Do not rewrite shared branch history. Force-pushes, non-fast-forward updates, and tag rewrites should stay blocked in branch protection.

Merging to `main` does not publish a new add-on version to users. Updates ship when a new tagged release is created and the release workflow publishes the `.nvda-addon`.

## Release notes

If a change affects users directly, update `changelog.md` in plain language. New detection behaviors, gesture changes, accessibility improvements, new exclusions or settings, or any wording change users will notice.

## Testing real NVDA behavior

The pure-Python tests under `tests/` cover the classifier and the landing logic. They run without NVDA, fast.

Anything that touches NVDA APIs has to be tested in NVDA itself. Build with `scons`, install the `.nvda-addon`, restart NVDA (or press `NVDA+Ctrl+F3` to reload add-ons), then reproduce the change on real pages. Cover Firefox and Chrome. Watch `[TMTS]` lines in the NVDA log viewer (`NVDA+F1`). Cycle through speech modes with `NVDA+S` and confirm the behavior matches the expectation.

When you start using a new NVDA API for the first time, write a tiny standalone probe add-on first to see how the API actually behaves. The `probes/` folder has examples.

## Good first contributions

Good places to start:

- documentation fixes
- plain-language improvements
- accessibility text improvements
- adding a classifier fixture for a page that misbehaves
- adding a regression test for current behavior

Look for issues labeled `good first issue` or `help wanted` if you do not have a starting point.

## Code style

Match the existing style. Prefer small readable changes over broad refactors. Do not raise the minimum supported NVDA version unless that migration is intentional and coordinated. Do not remove accessibility behavior without a clear replacement.

## Questions

If you are not sure whether something is an issue, a discussion, or a PR, start with a discussion:

https://github.com/WebFriendlyHelp/textMarksTheSpot/discussions
