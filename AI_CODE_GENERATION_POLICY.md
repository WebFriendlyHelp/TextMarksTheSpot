# AI Code Generation Policy

## Summary

This repository may contain code generated partially or entirely with AI
tools such as large language models (LLMs). AI assistance is used as a
drafting and productivity aid, not as a substitute for project
responsibility.

This project follows a transparency and risk-reduction approach:

- AI output is treated as draft material produced from written requirements.
- Generated code should be kept small and reviewable when practical.
- Readability and maintainability take priority over artificial uniqueness.
- If output appears derived from a known third-party source, it should be
  discarded and replaced with a new implementation.
- Automated checks such as linting, testing, and other repository safeguards
  should be used where available.
- The repository openly discloses that AI-assisted development is used.

## Purpose

This document explains how AI-generated code may be used in this repository
and what safeguards are expected to reduce legal, licensing, maintenance,
and security risk.

## Scope

This policy applies to source code, scripts, configuration, and documentation
that may be generated or influenced by AI tools, including but not limited to:

- ChatGPT
- Claude
- GitHub Copilot
- Local language models
- Other AI-assisted coding systems

## Disclosure of AI Usage

This project may contain code or documentation generated substantially or
partially by AI systems.

AI tools may be used to:

- generate initial implementations
- modify or refactor existing code
- generate configuration or scripts
- assist with debugging
- assist with documentation or release text

Human judgment is still required to decide whether generated output belongs in
the repository.

## Core Development Guidelines

### Generate from Requirements

Prompts should describe desired behavior, constraints, and acceptance criteria
rather than asking an AI system to reproduce a specific external project or
codebase.

Preferred prompt style:

> Implement a feature with the following behavior and constraints...

### Prefer Small Components

When practical, generate smaller pieces of code rather than large monolithic
systems.

Examples:

- helper functions
- focused modules
- adapters or integration code
- tests
- configuration scripts

Smaller units are easier to review, replace, and validate.

### Maintain Readable Code

Readability and maintainability take priority over attempts to make generated
code look artificially different.

Do not intentionally degrade naming, structure, or formatting in an attempt to
hide provenance concerns.

### Avoid Cosmetic Rewriting

Renaming variables, reformatting code, or rearranging lines does not meaningfully
reduce provenance risk.

If generated output raises origin concerns, replace it with a fresh
implementation instead of cosmetically editing it.

### Replace Suspicious Output

Discard and replace generated output if it appears to:

- closely match known external code
- include licensing headers or notices from another project
- reference a specific third-party source unexpectedly
- reproduce a known public implementation beyond what is reasonably incidental

## Validation and Safeguards

Generated output should be reviewed with the same care as any other change.

Contributors are expected to:

- run the repository's required checks before opening a PR
- add or update tests when behavior changes
- review generated code for correctness, readability, and project fit
- avoid submitting code they do not have the right to contribute

Additional repository safeguards such as dependency scanning, static analysis,
or security tooling should be used where available.

## Limitations

AI-generated output may contain mistakes, security flaws, licensing problems,
or incorrect assumptions.

Users and contributors should understand that:

- generated output can be wrong even when it looks polished
- prompts do not guarantee originality or suitability
- review and automated checks reduce risk but do not eliminate it

## Responsibility and Contributions

By contributing to this repository, contributors agree that:

- they have the right to submit their contribution
- they understand this project may use AI-assisted development
- they will avoid knowingly submitting incompatible third-party code
- they will describe relevant AI assistance in the pull request when it
  materially affected the change

## Policy Updates

This policy may change as legal guidance, tooling, and project practices around
AI-assisted development evolve.
