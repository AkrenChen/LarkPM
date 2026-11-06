$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
python -m unittest discover -s tests -v
if ($LASTEXITCODE) { throw 'Backend tests failed' }
npm.cmd run build
if ($LASTEXITCODE) { throw 'Frontend build failed' }
python -m PyInstaller --noconfirm --clean --onefile --additional-hooks-dir scripts/pyinstaller-hooks --name larkpm-backend --distpath src-tauri/sidecar --workpath build/pyinstaller backend/service.py
if ($LASTEXITCODE) { throw 'Sidecar build failed' }
npm.cmd run tauri:build
if ($LASTEXITCODE) { throw 'Desktop build failed' }
$releasePath = Join-Path (Get-Location) 'release/LarkPM-1.0.0'
New-Item -ItemType Directory -Path (Join-Path $releasePath 'sidecar') -Force | Out-Null
Copy-Item -LiteralPath 'src-tauri/target/release/larkpm.exe' -Destination (Join-Path $releasePath 'LarkPM.exe')
Copy-Item -LiteralPath 'src-tauri/sidecar/larkpm-backend.exe' -Destination (Join-Path $releasePath 'sidecar/larkpm-backend.exe')
Copy-Item -LiteralPath 'README.md' -Destination $releasePath
Compress-Archive -Path "$releasePath/*" -DestinationPath 'release/LarkPM-1.0.0-windows-x64.zip' -Force
Copy-Item -LiteralPath 'src-tauri/target/release/bundle/nsis/LarkPM_1.0.0_x64-setup.exe' -Destination 'release/LarkPM_1.0.0_x64-setup.exe'
$artifacts = @('release/LarkPM_1.0.0_x64-setup.exe', 'release/LarkPM-1.0.0-windows-x64.zip')
$checksums = $artifacts | ForEach-Object { $hash = Get-FileHash -LiteralPath $_ -Algorithm SHA256; '{0}  {1}' -f $hash.Hash.ToLowerInvariant(), (Split-Path $_ -Leaf) }
[System.IO.File]::WriteAllLines((Join-Path (Get-Location) 'release/SHA256SUMS.txt'), $checksums, [System.Text.UTF8Encoding]::new($false))
