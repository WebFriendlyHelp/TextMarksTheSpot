# Security Policy

## Scope

Text Marks the Spot is an NVDA add-on, pure Python, no native libraries. It reads page structure from NVDA's accessibility tree and moves the browse-mode cursor. It does not make network calls. It does not collect telemetry. The only persistent state is a per-site exclusion list saved in NVDA's normal config directory.

Even so, security issues are possible. Things worth reporting:

- vulnerabilities in release delivery (a tampered `.nvda-addon` package, for example)
- unsafe handling of URLs, hostnames, or DOM-derived strings inside the add-on
- dependency vulnerabilities (the add-on itself ships no third-party Python packages, but the build tooling does)
- anything that could cause unintended code execution, privilege misuse, or unsafe trust decisions inside NVDA

## Supported versions

Only the latest released version gets security fixes. Older releases are not supported.

## Reporting a vulnerability

Do not open a public GitHub issue for a suspected security problem. Report it privately by email instead:

- help@webfriendlyhelp.com

Helpful to include:

- a short summary of the issue
- affected version
- steps to reproduce, if known
- impact
- any suggested mitigation

If you are not sure whether something is a security issue or a regular bug, err on the side of reporting privately first.

## Response expectations

What I will try to do:

- acknowledge the report within 7 days
- decide whether it is in scope
- coordinate a fix or mitigation if it is confirmed

This is a small project. Response times will vary. Good-faith reports are appreciated.

## Disclosure

Please give me time to ship a fix before sharing details publicly.
