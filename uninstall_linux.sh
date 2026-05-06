#!/usr/bin/env bash
# uninstall_linux.sh
# -------------------
# Removes Pi SD Backup from the system.
# Must be run as root:  sudo bash uninstall_linux.sh

set -euo pipefail

INSTALL_DIR="/opt/pi-sd-backup"
DESKTOP_FILE="/usr/share/applications/pi-sd-backup.desktop"
SYMLINK="/usr/local/bin/pi-sd-backup"
SETTINGS_DIRS=(
    "/root/.config/PiBackupTool"
    "/home/*/.config/PiBackupTool"
)

# ── Root check ─────────────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root:  sudo bash uninstall_linux.sh"
    exit 1
fi

echo ""
echo "Pi SD Backup – Uninstaller"
echo "──────────────────────────"

# ── Confirm ────────────────────────────────────────────────────────────────────
read -r -p "This will remove Pi SD Backup from your system. Continue? [y/N] " CONFIRM
case "$CONFIRM" in
    [yY][eE][sS]|[yY]) ;;
    *)
        echo "Aborted."
        exit 0
        ;;
esac

# ── Remove symlink ─────────────────────────────────────────────────────────────
if [ -L "$SYMLINK" ]; then
    rm -f "$SYMLINK"
    echo "Removed symlink:      $SYMLINK"
else
    echo "Symlink not found, skipping: $SYMLINK"
fi

# ── Remove desktop entry ───────────────────────────────────────────────────────
if [ -f "$DESKTOP_FILE" ]; then
    rm -f "$DESKTOP_FILE"
    echo "Removed desktop entry: $DESKTOP_FILE"
    # Refresh the desktop database if available
    command -v update-desktop-database &>/dev/null \
        && update-desktop-database /usr/share/applications 2>/dev/null || true
else
    echo "Desktop entry not found, skipping: $DESKTOP_FILE"
fi

# ── Remove install directory ───────────────────────────────────────────────────
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo "Removed install dir:  $INSTALL_DIR"
else
    echo "Install dir not found, skipping: $INSTALL_DIR"
fi

# ── Optionally remove user settings ───────────────────────────────────────────
echo ""
read -r -p "Also remove saved settings for all users? [y/N] " REMOVE_SETTINGS
case "$REMOVE_SETTINGS" in
    [yY][eE][sS]|[yY])
        # Expand globs manually to handle /home/* safely
        for PATTERN in "${SETTINGS_DIRS[@]}"; do
            for DIR in $PATTERN; do
                if [ -d "$DIR" ]; then
                    rm -rf "$DIR"
                    echo "Removed settings:     $DIR"
                fi
            done
        done
        ;;
    *)
        echo "Settings left in place."
        ;;
esac

echo ""
echo "Uninstall complete."
