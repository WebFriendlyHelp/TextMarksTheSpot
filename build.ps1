# Local build wrapper. Produces exactly ONE add-on file at the repo root:
# TextMarksTheSpot.nvda-addon, always holding the newest build.
#
# Why this exists: `scons` names its output TextMarksTheSpot-<version>.nvda-addon,
# and CI (.github/workflows/release.yml) verifies that versioned name against the
# pushed tag, so the SCons target cannot be renamed. But locally a versioned file
# per build piles up, and the one that gets installed is the unversioned copy.
# Two files sitting side by side is how a stale build gets installed by mistake.
# So: build, MOVE the result onto the unversioned name, and sweep any versioned
# leftovers. CI is untouched; it still runs plain `scons`.
#
# Usage:  .\build.ps1          build, then leave the single file in place
#         .\build.ps1 -Install build, then launch it so NVDA installs it

[CmdletBinding()]
param(
	[switch]$Install
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$stable = Join-Path $PSScriptRoot 'TextMarksTheSpot.nvda-addon'

# Read the version SCons will use, so we know what filename to expect.
$versionLine = Select-String -Path 'buildVars.py' -Pattern 'addon_version\s*=\s*"([^"]+)"' |
	Select-Object -First 1
if (-not $versionLine) {
	throw "Could not read addon_version from buildVars.py"
}
$version = $versionLine.Matches[0].Groups[1].Value
$built = Join-Path $PSScriptRoot "TextMarksTheSpot-$version.nvda-addon"

# The SCons target is gone after every run (we move it away), so SCons rebuilds
# it each time. That is the intent: the single file is never stale.
# `python -m SCons`, not bare `scons`: on this machine a bare `scons` on PATH
# can resolve to a stale Python 3.9 shim that cannot build this add-on.
python -m SCons
if ($LASTEXITCODE -ne 0) {
	throw "SCons failed with exit code $LASTEXITCODE"
}
if (-not (Test-Path -LiteralPath $built)) {
	throw "Expected build output not found: $built"
}

Move-Item -LiteralPath $built -Destination $stable -Force

# Sweep any versioned files left over from an earlier build or an older version.
Get-ChildItem -LiteralPath $PSScriptRoot -Filter 'TextMarksTheSpot-*.nvda-addon' -File |
	Remove-Item -Force

$size = [math]::Round((Get-Item -LiteralPath $stable).Length / 1KB)
Write-Output "Built $version -> TextMarksTheSpot.nvda-addon ($size KB)"

if ($Install) {
	Start-Process -FilePath $stable
}
