$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$releaseRoot = Join-Path (Get-Location) 'release'
$pmPath = Join-Path $releaseRoot 'LarkPM-1.0.3'
$bridgePath = Join-Path $releaseRoot 'LinkinNotes-LarkPM-bridge'
New-Item -ItemType Directory -Path (Join-Path $pmPath 'sidecar'), (Join-Path $bridgePath 'sidecar') -Force | Out-Null
Copy-Item -LiteralPath 'src-tauri/target/release/larkpm.exe' -Destination (Join-Path $pmPath 'LarkPM.exe')
Copy-Item -LiteralPath 'src-tauri/sidecar/larkpm-backend.exe' -Destination (Join-Path $pmPath 'sidecar/larkpm-backend.exe')
Copy-Item -LiteralPath 'README.md' -Destination $pmPath
Copy-Item -LiteralPath '../LinkinNotes/src-tauri/target/release/linkin-notes.exe' -Destination (Join-Path $bridgePath 'LinkinNotes.exe')
Copy-Item -LiteralPath '../LinkinNotes/build/larkpm-bridge/sidecar/linkin-backend.exe' -Destination (Join-Path $bridgePath 'sidecar/linkin-backend.exe')
Copy-Item -LiteralPath 'README.md' -Destination $bridgePath
Compress-Archive -Path "$pmPath/*" -DestinationPath (Join-Path $releaseRoot 'LarkPM-1.0.3-windows-x64.zip') -Force
Compress-Archive -Path "$bridgePath/*" -DestinationPath (Join-Path $releaseRoot 'LinkinNotes-LarkPM-bridge-windows-x64.zip') -Force
Get-Item -LiteralPath (Join-Path $releaseRoot 'LarkPM-1.0.3-windows-x64.zip'), (Join-Path $releaseRoot 'LinkinNotes-LarkPM-bridge-windows-x64.zip') | Select-Object Name, Length
