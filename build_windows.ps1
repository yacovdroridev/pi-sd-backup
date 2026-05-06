# build_windows.ps1
# ------------------
# Full Windows build script.  Run from the project root in PowerShell:
#
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\build_windows.ps1
#
# What it does:
#   1. Creates a Python venv in .venv\
#   2. Installs all dependencies (including PyInstaller)
#   3. Runs PyInstaller to produce dist\pi_sd_backup\
#   4. (Optional) Runs Inno Setup to produce installer_output\PiSdBackup_Setup.exe
#
# Requirements:
#   - Python 3.11+ in PATH
#   - Inno Setup 6 installed at default location (for the installer step)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$VENV_DIR = ".venv"
$PYTHON   = "python"

# ── 1. Create / reuse venv ─────────────────────────────────────────────────────
Write-Host "`n[1/4] Setting up virtual environment..." -ForegroundColor Cyan

if (-Not (Test-Path "$VENV_DIR\Scripts\activate.ps1")) {
    Write-Host "  Creating new venv at $VENV_DIR"
    & $PYTHON -m venv $VENV_DIR
} else {
    Write-Host "  Reusing existing venv at $VENV_DIR"
}

$PIP     = "$VENV_DIR\Scripts\pip.exe"
$PYEXE   = "$VENV_DIR\Scripts\python.exe"
$PYINST  = "$VENV_DIR\Scripts\pyinstaller.exe"

# ── 2. Install dependencies ────────────────────────────────────────────────────
Write-Host "`n[2/4] Installing dependencies..." -ForegroundColor Cyan
& $PIP install --upgrade pip --quiet
& $PIP install -r requirements.txt pyinstaller --quiet
Write-Host "  Done."

# ── 3. Run PyInstaller ─────────────────────────────────────────────────────────
Write-Host "`n[3/4] Running PyInstaller..." -ForegroundColor Cyan
& $PYINST pi_sd_backup.spec --clean --noconfirm

if (-Not (Test-Path "dist\pi_sd_backup\PiSdBackup.exe")) {
    Write-Error "PyInstaller failed – dist\pi_sd_backup\PiSdBackup.exe not found."
    exit 1
}
Write-Host "  Build output: dist\pi_sd_backup\" -ForegroundColor Green

# ── 4. Optional: Inno Setup ────────────────────────────────────────────────────
Write-Host "`n[4/4] Looking for Inno Setup..." -ForegroundColor Cyan

$INNO_PATHS = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)

$ISCC = $null
foreach ($p in $INNO_PATHS) {
    if (Test-Path $p) { $ISCC = $p; break }
}

if ($ISCC) {
    Write-Host "  Found Inno Setup at $ISCC"
    New-Item -ItemType Directory -Force -Path "installer_output" | Out-Null
    & $ISCC installer_windows.iss
    Write-Host "  Installer: installer_output\PiSdBackup_Setup.exe" -ForegroundColor Green
} else {
    Write-Host "  Inno Setup not found – skipping installer step." -ForegroundColor Yellow
    Write-Host "  Install from https://jrsoftware.org/isdl.php then re-run this script."
}

Write-Host "`nBuild complete." -ForegroundColor Green
