<#
.SYNOPSIS  Build QR Studio Pro on Windows 10/11: PyInstaller app, installer (.exe) and optional portable .exe.
.EXAMPLE   powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
.EXAMPLE   powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -Portable -SkipTests
Output goes to dist\ :  QRStudioPro\ (app folder), QRStudioPro-<version>-Setup.exe, QRStudioPro-portable.exe
#>
param([switch]$Portable, [switch]$SkipTests, [switch]$SkipInstaller)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Fail($m) { Write-Host "ERROR: $m" -ForegroundColor Red; exit 1 }
function Step($m) { Write-Host "`n== $m" -ForegroundColor Cyan }

if ($env:OS -ne "Windows_NT") { Fail "This script must run on Windows (PyInstaller cannot cross-compile)." }

Step "Checking Python"
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Fail "Python 3.12+ was not found on PATH. Install it from python.org and tick 'Add to PATH'." }
$ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$ver -lt [version]"3.12") { Fail "Python 3.12 or newer is required (found $ver)." }
Write-Host "Python $ver"

Step "Creating virtual environment (.venv-build)"
if (-not (Test-Path ".venv-build")) { & python -m venv .venv-build; if ($LASTEXITCODE) { Fail "venv creation failed" } }
$vpy = ".venv-build\Scripts\python.exe"
& $vpy -m pip install --upgrade pip | Out-Null
& $vpy -m pip install -r requirements-dev.txt; if ($LASTEXITCODE) { Fail "Installing dependencies failed" }

if (-not $SkipTests) {
  Step "Running tests"
  $env:QT_QPA_PLATFORM = "offscreen"
  & $vpy -m pytest; if ($LASTEXITCODE) { Fail "Tests failed - fix them or pass -SkipTests." }
}

Step "Generating icons and version info"
& $vpy scripts\make_icons.py; if ($LASTEXITCODE) { Fail "Icon generation failed" }
& $vpy scripts\make_version_info.py; if ($LASTEXITCODE) { Fail "Version info generation failed" }
$version = (& $vpy -c "from src.version import VERSION; print(VERSION)").Trim()

Step "Building application folder with PyInstaller"
Remove-Item -Recurse -Force build, dist\QRStudioPro -ErrorAction SilentlyContinue
$env:QRSP_ONEFILE = ""
& $vpy -m PyInstaller --noconfirm --distpath dist --workpath build packaging\qr_studio.spec
if ($LASTEXITCODE) { Fail "PyInstaller failed" }

Step "Self-test of the built executable"
& "dist\QRStudioPro\QRStudioPro.exe" --selftest
# GUI executables have no console, so the report is also written to %APPDATA%\QRStudioPro\selftest.txt
$report = Join-Path $env:APPDATA "QRStudioPro\selftest.txt"
if (-not (Test-Path $report) -or -not (Select-String -Path $report -Pattern "RESULT: OK" -Quiet)) {
  if (Test-Path $report) { Get-Content $report }
  Fail "The built app failed its self-test."
}
Get-Content $report

if ($Portable) {
  Step "Building portable single-file executable"
  $env:QRSP_ONEFILE = "1"
  & $vpy -m PyInstaller --noconfirm --distpath dist --workpath build\onefile packaging\qr_studio.spec
  if ($LASTEXITCODE) { Fail "Portable build failed" }
  $env:QRSP_ONEFILE = ""
  Write-Host "Note: the single-file build unpacks itself at start-up (slower launch) and is more likely to trigger antivirus warnings."
}

if (-not $SkipInstaller) {
  Step "Building installer with Inno Setup"
  $iscc = Get-Command iscc -ErrorAction SilentlyContinue
  if (-not $iscc) {
    foreach ($p in @("$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")) {
      if (Test-Path $p) { $iscc = Get-Item $p; break }
    }
  }
  if (-not $iscc) { Fail "Inno Setup 6 not found. Install it (winget install JRSoftware.InnoSetup) or pass -SkipInstaller." }
  $isccPath = if ($iscc.PSObject.Properties.Name -contains "Source") { $iscc.Source } else { $iscc.FullName }
  & $isccPath "/DAppVersion=$version" packaging\windows_installer.iss
  if ($LASTEXITCODE) { Fail "Inno Setup failed" }
}

Step "Done"
Get-ChildItem dist | Format-Table Name, Length -AutoSize
Write-Host "The installer is NOT code-signed: Windows SmartScreen may warn on first run. See docs/PACKAGING.md." -ForegroundColor Yellow
