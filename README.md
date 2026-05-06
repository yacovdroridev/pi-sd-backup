# Pi SD Backup

A professional, open-source Windows & Linux desktop application for streaming a Raspberry Pi SD card image over SSH directly to your local machine — without removing the card.

Built with **Python**, **PySide6**, and **Paramiko**.

---

## Features

| Feature | Detail |
|---|---|
| **Binary streaming** | Raw `dd` stream over SSH — no intermediate temp files on the Pi |
| **Block device scanner** | Connects and auto-discovers all disk devices (`lsblk` / `/proc/partitions`) |
| **Password or key auth** | SSH password, SSH key, or both |
| **Disk space pre-flight** | Checks local free space before starting (device size + 2 GiB buffer) |
| **Transfer speed & ETA** | Live MB/s and time remaining displayed in the UI |
| **SHA256 verification** | Optional: hashes local image and remote device, compares digests |
| **Shrink image** | Optional: runs [PiShrink](https://github.com/Drewsif/PiShrink) after backup |
| **Cancel at any time** | Cleanly closes the SSH channel and stops writing |
| **Async UI** | `QThread` worker keeps the interface fully responsive during backup |
| **Persistent settings** | Host, port, user, key path and options saved across sessions |
| **Windows + Linux** | Runs natively on both; includes build & installer scripts for both |

---

## Screenshots

> _Add screenshots here once the app is running._

---

## Requirements

- Python 3.11+
- A Raspberry Pi (or any Linux host) accessible over SSH or [Tailscale](https://tailscale.com/)
- The SSH user must be able to run `sudo dd` and `sudo sha256sum` on the remote host

### Python dependencies

```
PySide6>=6.6.0
paramiko>=3.4.0
```

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/yacovdroridev/pi-sd-backup.git
cd pi-sd-backup

# 2. Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Run
python main.py
```

---

## Building an Installer

### Windows

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\build_windows.ps1
```

- Creates `.venv\`, installs deps, runs PyInstaller
- If [Inno Setup 6](https://jrsoftware.org/isdl.php) is installed, also produces `installer_output\PiSdBackup_Setup.exe`

### Linux

```bash
chmod +x build_linux.sh
./build_linux.sh
```

- Creates `.venv\`, installs deps, runs PyInstaller
- Packages everything into `PiSdBackup_linux_x86_64.tar.gz`

**Install on a target Linux machine:**

```bash
tar -xzf PiSdBackup_linux_x86_64.tar.gz
sudo bash pi_sd_backup/install_linux.sh
```

Installs to `/opt/pi-sd-backup/`, creates a `.desktop` launcher entry and a `/usr/local/bin/pi-sd-backup` symlink.

**Uninstall:**

```bash
sudo bash /opt/pi-sd-backup/uninstall_linux.sh
```

---

## Raspberry Pi Setup

The SSH user needs passwordless (or password-based) `sudo` access to `dd` and `sha256sum`.

### Option A — provide your sudo password in the app

Enter your Pi user password in the **Password** field. The app uses `sudo -S` to pass it via stdin. No Pi configuration needed.

### Option B — passwordless sudo for dd only (more secure)

Add the following to `/etc/sudoers` on the Pi (replace `pi` with your username):

```
pi ALL=(ALL) NOPASSWD: /bin/dd, /usr/bin/sha256sum, /sbin/blockdev
```

Edit safely with:

```bash
sudo visudo
```

---

## How It Works

```
┌──────────────────────┐        SSH (Paramiko)        ┌─────────────────────┐
│   Windows / Linux PC │ ◄──────────────────────────  │   Raspberry Pi      │
│                      │   sudo dd if=/dev/sdX | ...  │                     │
│  BackupWorker        │                              │  block device       │
│  (QThread)           │   raw binary stream          │  /dev/mmcblk0       │
│  → writes .img file  │ ◄──────────────────────────  │  /dev/sda  etc.     │
└──────────────────────┘                              └─────────────────────┘
```

1. **Pre-flight** — checks local disk space (requires device size + 2 GiB free)
2. **Scan** — SSH in, run `lsblk` to list block devices, populate dropdown
3. **Stream** — open SSH channel, run `sudo -S dd`, stream raw bytes to a local `.img` file in 1 MiB chunks
4. **Verify** _(optional)_ — SHA256 hash of local image vs. `sudo sha256sum /dev/sdX` on the Pi
5. **Shrink** _(optional)_ — run [PiShrink](https://github.com/Drewsif/PiShrink) locally to reduce image size

---

## Project Structure

```
pi-sd-backup/
├── main.py                 ← entry point
├── ui_main.py              ← MainWindow (PySide6)
├── backup_worker.py        ← QThread workers (ScanWorker, BackupWorker)
├── requirements.txt
├── pi_sd_backup.spec       ← PyInstaller spec
├── build_windows.ps1       ← Windows build script (venv + PyInstaller + Inno Setup)
├── build_linux.sh          ← Linux build script (venv + PyInstaller + tar.gz)
├── installer_windows.iss   ← Inno Setup 6 script → PiSdBackup_Setup.exe
├── pi-sd-backup.desktop    ← Linux desktop entry
└── uninstall_linux.sh      ← Linux uninstaller
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `sudo: a terminal is required` | App uses `sudo -S` automatically — ensure the Password field is filled |
| `dd produced no output` | Check the device path is correct; verify sudo permissions |
| `Authentication failed` | Check username, password, and/or SSH key path |
| Size query returns empty | `blockdev` may need sudo — the app falls back to `fdisk -s` automatically |
| Verification fails | The stream may have been interrupted; retry the backup |
| PiShrink not found | Install from [github.com/Drewsif/PiShrink](https://github.com/Drewsif/PiShrink) and ensure it's in `PATH` |

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

## Contributing

Pull requests are welcome. Please open an issue first to discuss significant changes.
