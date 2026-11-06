param([string]$LinkinRoot = (Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'LinkinNotes'))
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath (Join-Path $LinkinRoot 'backend/pm_api.py'))) { throw 'LinkinNotes bridge is not installed' }
Copy-Item -LiteralPath (Join-Path (Split-Path $PSScriptRoot -Parent) 'backend/workspace.py') -Destination (Join-Path $LinkinRoot 'backend/pm_workspace.py')
