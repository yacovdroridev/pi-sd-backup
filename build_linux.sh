#!/usr/bin/env bash
# build_linux.sh
# ---------------
# Full Linux build script.  Run from the project root:
#
#   chmod +x build_linux.sh
#   ./build_linux.sh
#
# What it does:
#   1. Creates a Python venv in .venv/
#   2. Installs all dependencies (including PyInstaller)
#   3. Runs PyInstaller to produce dist/pi_sd_backup/
#   4. Packages the result into a self-contained tar.gz
#   5. Creates an install_linux.sh that end-users can run to install the app
#
# Requirements:
#   - Python 3.11+
#   - python3-venv package  (sudo apt install python3-venv)

set -euo pipefail

VENV_DIR=".venv"
DIST_DIR="dist/pi_sd_backup"
ARCHIVE="PiSdBackup_linux_x86_64.tar.gz"

# ── 1. Create / reuse venv ─────────────────────────────────────────────────────
echo ""
echo "[1/4] Setting up virtual environment..."

if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "  Creating new venv at $VENV_DIR"
    python3 -m venv "$VENV_DIR"
else
    echo "  Reusing existing venv at $VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ── 2. Install dependencies ────────────────────────────────────────────────────
echo ""
echo "[2/4] Installing dependencies..."
pip install --upgrade pip --quiet
pip install -r requirements.txt pyinstaller --quiet
echo "  Done."

# ── 3. Run PyInstaller ─────────────────────────────────────────────────────────
echo ""
echo "[3/4] Running PyInstaller..."
pyinstaller pi_sd_backup.spec --clean --noconfirm

if [ ! -f "$DIST_DIR/PiSdBackup" ]; then
    echo "ERROR: PyInstaller failed – $DIST_DIR/PiSdBackup not found." >&2
    exit 1
fi

# Copy .desktop file and uninstaller into the bundle
cp pi-sd-backup.desktop "$DIST_DIR/"
cp uninstall_linux.sh   "$DIST_DIR/"
[ -f "assets/icon.png" ] && cp assets/icon.png "$DIST_DIR/assets/" 2>/dev/null || true

echo "  Build output: $DIST_DIR/"

# ── 4. Package into tar.gz + generate user-facing install script ───────────────
echo ""
echo "[4/4] Packaging..."

# Create an installer script that will be included inside the archive
cat > "$DIST_DIR/install_linux.sh" << 'INSTALL_EOF'
#!/usr/bin/env bash
# install_linux.sh  –  run this on the TARGET machine to install Pi SD Backup
set -euo pipefail

INSTALL_DIR="/opt/pi-sd-backup"
DESKTOP_DIR="/usr/share/applications"

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root:  sudo bash install_linux.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing to $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR"/. "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/PiSdBackup"

# Desktop entry
if [ -d "$DESKTOP_DIR" ]; then
    # Patch the Exec path to the real install location
    sed "s|Exec=.*|Exec=$INSTALL_DIR/PiSdBackup|g" \
        "$INSTALL_DIR/pi-sd-backup.desktop" \
        > "$DESKTOP_DIR/pi-sd-backup.desktop"
    echo "Installed desktop entry to $DESKTOP_DIR"
fi

# Optional: symlink to /usr/local/bin so it's launchable from terminal
ln -sf "$INSTALL_DIR/PiSdBackup" /usr/local/bin/pi-sd-backup
echo "Symlink created: /usr/local/bin/pi-sd-backup"

echo ""
echo "Installation complete.  Launch with:  pi-sd-backup"
INSTALL_EOF

chmod +x "$DIST_DIR/install_linux.sh"

# Create the archive
tar -czf "$ARCHIVE" -C dist pi_sd_backup
echo "  Archive: $ARCHIVE"

deactivate

echo ""
echo "Build complete."
echo "  Standalone folder : $DIST_DIR/"
echo "  Distributable     : $ARCHIVE"
echo ""
echo "To install on this machine:"
echo "  tar -xzf $ARCHIVE"
echo "  sudo bash pi_sd_backup/install_linux.sh"
