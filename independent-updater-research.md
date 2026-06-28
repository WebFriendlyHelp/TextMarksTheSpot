# Independent (non-store) updater: research note

Status: deferred, not built. Captured 2026-06-28.

## Why this note exists

The add-on is now in the NVDA Add-on Store, so store-installed copies already
update automatically. The open question was whether to also add a self-updater
that pulls new versions straight from GitHub Releases, for the benefit of people
who sideload the `.nvda-addon` from the web page instead of using the store.

Decision for now: leave it out. If users actually ask for it, this note is the
starting point so we do not have to re-research from scratch.

Related: the readme's "Download and install" section was rewritten to steer
web-page downloaders toward the store for automatic updates, and to warn that a
direct download does not update itself (commit 7e73fb2 on main, 2026-06-28).

## Reference implementation

fastfinge's `eloquence_64` add-on has a clean, compact updater we can adapt:

- Repo: https://github.com/fastfinge/eloquence_64
- File: `addon/synthDrivers/_eloquence_updater.py` (about 130 lines)
- Companion: `addon/installTasks.py` shows the `onInstall` pattern for
  preserving user data across a pending self-install (not strictly needed for
  us, see "What we get for free" below).

What that updater does, end to end:

1. Reads its own installed version from `manifest.ini`.
2. Calls the GitHub releases API
   (`https://api.github.com/repos/OWNER/REPO/releases/latest`), reads `tag_name`
   for the version, scans the release `assets` for the one whose name ends in
   `.nvda-addon`, takes that `browser_download_url`, and reads the release notes
   from the `body` field.
3. Compares versions by parsing digit runs and comparing them as integer lists.
4. Streams the `.nvda-addon` to a temp folder with a progress callback.
5. Installs through NVDA's own machinery: `addonStore.install.installAddon`,
   falling back to `gui.addonGui.installAddon` on older NVDA.
6. Prompts for a restart via `gui.addonGui.promptUserForRestart`.

It is all Python standard library (`urllib.request`, `json`). No third-party
packages, which keeps our "pure Python, 32 and 64 bit, no native libraries"
guarantee intact. Our releases already publish a `.nvda-addon` asset, so the
asset-finding loop works against our repo unchanged. Point `REPO_OWNER` /
`REPO_NAME` at WebFriendlyHelp / TextMarksTheSpot and the engine is essentially
done.

## Effort estimate

Low to moderate. The networking, version-compare, download, and install engine
is close to copy-and-adapt. The real work is the parts around it:

1. Trigger and UI. eloquence wires the engine to a "check for updates" action
   elsewhere; we would decide between a Tools-menu item, a gesture, an automatic
   background check, or a mix.
2. Threading. The network call must not run on NVDA's main thread or it freezes
   speech. Use a background thread plus `wx.CallAfter` for anything touching UI.
3. Testing. None of this is unit-testable (network plus NVDA install machinery),
   so it is manual testing only, same posture as the rest of our NVDA-facing
   code. Cases: no update, update available, download, install, restart, and the
   failure cases (offline, timeout, GitHub rate-limited) all failing quietly.
4. Translatable strings, same `_()` discipline we already follow.

Rough size: a half-day including manual testing for the minimal manual-check
version.

## Recommended shape if we build it

Given this add-on's identity is "quiet, never nag," the in-character version is a
manual "Check for updates" command (Tools menu or a gesture), NOT an automatic
startup check that could interrupt. An auto-check, if ever wanted, should be a
once-daily throttled background check that surfaces at most a single short
notice when an update exists, and stays silent otherwise.

## Gotchas to remember

- GitHub's unauthenticated API allows 60 calls per hour per IP. Fine for a
  manual or once-per-launch check; rules out aggressive polling.
- An add-on install only takes effect after an NVDA restart, so the restart
  prompt is mandatory.
- SSL is the riskiest surface. eloquence proves plain `urllib` over HTTPS works
  inside NVDA, but it is the part to test hardest, across 32-bit and 64-bit.
- Store redundancy: a store-installed user who also has a self-updater could see
  update prompts from two directions. This is the main argument for keeping any
  self-update strictly manual, or skipping it while the store covers updates.

## What we get for free

Our per-site exclusion list lives in NVDA's config, not in the add-on folder, so
it survives a reinstall automatically. That means we do not need the
`installTasks.py` user-data-preservation dance that eloquence uses for its
dictionaries.
