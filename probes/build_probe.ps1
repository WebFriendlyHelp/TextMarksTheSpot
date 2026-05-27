# Generic build script for any TMTS probe.
# Usage:    .\probes\build_probe.ps1 focus_event
# Produces: probes\<name>\tmts_probe_<name>-<version>.nvda-addon
#
# The .nvda-addon file is a zip with manifest.ini at the root and the
# CONTENTS of addon/ at the root (NOT the addon/ folder itself), renamed.
# So the zip looks like:
#     manifest.ini
#     globalPlugins/...
#     doc/...
# NOT:
#     manifest.ini
#     addon/globalPlugins/...
# NVDA extracts the zip to %APPDATA%\nvda\addons\<name>\ and expects
# globalPlugins/ to be a direct child. If addon/ is in the path, NVDA
# can't find the plugins and silently loads nothing.

param(
    [Parameter(Mandatory=$true)][string]$Name
)

$probeDir = Join-Path $PSScriptRoot $Name
if (-not (Test-Path $probeDir)) {
    Write-Error "Probe folder not found: $probeDir"
    exit 1
}

$manifest = Join-Path $probeDir "manifest.ini"
$addonDir = Join-Path $probeDir "addon"
if (-not (Test-Path $manifest)) { Write-Error "Missing manifest.ini in $probeDir"; exit 1 }
if (-not (Test-Path $addonDir)) { Write-Error "Missing addon/ folder in $probeDir"; exit 1 }

# Read version + name from manifest
$manifestText = Get-Content $manifest -Raw
$nameMatch    = [regex]::Match($manifestText, '(?m)^\s*name\s*=\s*(.+?)\s*$')
$versionMatch = [regex]::Match($manifestText, '(?m)^\s*version\s*=\s*(.+?)\s*$')
if (-not $nameMatch.Success)    { Write-Error "manifest.ini missing 'name'";    exit 1 }
if (-not $versionMatch.Success) { Write-Error "manifest.ini missing 'version'"; exit 1 }
$addonName    = $nameMatch.Groups[1].Value
$addonVersion = $versionMatch.Groups[1].Value

$zipPath   = Join-Path $probeDir "$addonName-$addonVersion.zip"
$addonPath = Join-Path $probeDir "$addonName-$addonVersion.nvda-addon"

# Clean prior build artifacts
if (Test-Path $zipPath)   { Remove-Item $zipPath -Force }
if (Test-Path $addonPath) { Remove-Item $addonPath -Force }

# Build via staging so addon/ contents land at zip root (NOT wrapped in addon/)
$staging = Join-Path $env:TEMP "tmts_probe_build_$Name"
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Path $staging | Out-Null
Copy-Item $manifest -Destination $staging
robocopy $addonDir $staging /E /XD __pycache__ /XF *.pyc /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -Force
Rename-Item $zipPath $addonPath -Force
Remove-Item $staging -Recurse -Force

Write-Output "Built: $addonPath"
