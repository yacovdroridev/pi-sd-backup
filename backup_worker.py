"""
backup_worker.py
----------------
QThread workers for SSH/Paramiko logic.

Classes:
  ScanWorker   – connects over SSH and returns available block devices via lsblk
  BackupWorker – streams a remote block device to a local .img file

Signals emitted to the UI:
  progress(int)              – 0-100 percentage  (-1 = indeterminate)
  log(str)                   – human-readable status message
  finished(bool, str)        – success flag + final message
  devices_found(list[str])   – (ScanWorker only) list of device paths
"""

import os
import shutil
import socket

import paramiko
from PySide6.QtCore import QThread, Signal


# ── Constants ──────────────────────────────────────────────────────────────────
CHUNK_SIZE        = 1024 * 1024          # 1 MiB per read
FREE_SPACE_BUFFER = 2 * 1024 ** 3        # 2 GiB safety margin


def _make_ssh(host, port, username, key_path, password) -> paramiko.SSHClient:
    """Helper: create and connect a Paramiko SSH client."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        hostname       = host,
        port           = port,
        username       = username,
        key_filename   = key_path or None,
        password       = password or None,
        timeout        = 30,
        banner_timeout = 30,
        auth_timeout   = 30,
    )
    return ssh


# ══════════════════════════════════════════════════════════════════════════════
class ScanWorker(QThread):
    """
    Connects via SSH and queries the remote host for block devices using lsblk.
    Reports results via devices_found(list[str]).
    Falls back to /proc/partitions if lsblk is not available.
    """

    log           = Signal(str)         # status text
    finished      = Signal(bool, str)   # (success, message)
    devices_found = Signal(list)        # list of '/dev/xxx' strings

    def __init__(self, host, port, username, key_path, password, parent=None):
        super().__init__(parent)
        self.host     = host
        self.port     = port
        self.username = username
        self.key_path = key_path
        self.password = password

    def run(self):
        self.log.emit(f"Connecting to {self.username}@{self.host}:{self.port} …")
        try:
            ssh = _make_ssh(
                self.host, self.port, self.username, self.key_path, self.password
            )
        except paramiko.AuthenticationException:
            self.finished.emit(False, "Authentication failed – check credentials.")
            return
        except Exception as e:
            self.finished.emit(False, f"Connection failed: {e}")
            return

        try:
            devices = self._list_block_devices(ssh)
        finally:
            ssh.close()

        if devices:
            self.log.emit(f"Found {len(devices)} block device(s): {', '.join(devices)}")
            self.devices_found.emit(devices)
            self.finished.emit(True, "Scan complete.")
        else:
            self.finished.emit(False, "No block devices found on remote host.")

    def _list_block_devices(self, ssh: paramiko.SSHClient) -> list[str]:
        """
        Try lsblk first (shows only whole disks, no partitions).
        Fall back to /proc/partitions if lsblk is absent.
        """
        # lsblk: list only disk-type devices (not partitions), output bare paths
        cmd = "lsblk -d -n -o NAME,TYPE 2>/dev/null | awk '$2==\"disk\"{print \"/dev/\"$1}'"
        _, stdout, _ = ssh.exec_command(cmd, timeout=15)
        devices = [l.strip() for l in stdout.read().decode().splitlines() if l.strip()]

        if not devices:
            self.log.emit("lsblk unavailable, falling back to /proc/partitions …")
            # /proc/partitions: major minor #blocks name
            # Keep only whole-disk entries (e.g. mmcblk0, sda) – exclude partitions
            cmd2 = (
                "awk 'NR>2 && $4!=\"\" && $4!~/[0-9]p?[0-9]+$/{print \"/dev/\"$4}'"
                " /proc/partitions"
            )
            _, stdout2, _ = ssh.exec_command(cmd2, timeout=15)
            devices = [l.strip() for l in stdout2.read().decode().splitlines() if l.strip()]

        return devices


# ══════════════════════════════════════════════════════════════════════════════
class BackupWorker(QThread):
    """
    Streams a remote block device from a Raspberry Pi over SSH and writes
    the raw bytes to a local .img file.
    """

    # ── Signals ────────────────────────────────────────────────────────────────
    progress = Signal(int)          # 0-100, or -1 for indeterminate
    log      = Signal(str)          # status text
    finished = Signal(bool, str)    # (success, message)

    # ── Constructor ────────────────────────────────────────────────────────────
    def __init__(
        self,
        host:        str,
        username:    str,
        key_path:    str | None,
        password:    str | None,
        remote_dev:  str,
        dest_path:   str,
        shrink:      bool = False,
        port:        int  = 22,
        parent=None,
    ):
        super().__init__(parent)
        self.host       = host
        self.username   = username
        self.key_path   = key_path
        self.password   = password
        self.remote_dev = remote_dev
        self.dest_path  = dest_path
        self.shrink     = shrink
        self.port       = port

        self._cancel_requested = False
        self._ssh:     paramiko.SSHClient | None = None
        self._channel: paramiko.Channel   | None = None

    # ── Public API ─────────────────────────────────────────────────────────────
    def request_cancel(self) -> None:
        """Signal the worker to abort cleanly.  Called from the UI thread."""
        self._cancel_requested = True
        self.log.emit("Cancel requested – closing SSH channel …")
        # Close the channel so the blocking read() wakes up immediately.
        if self._channel and not self._channel.closed:
            try:
                self._channel.close()
            except Exception:
                pass

    # ── Thread entry point ─────────────────────────────────────────────────────
    def run(self) -> None:
        try:
            self._backup()
        except Exception as exc:
            self.finished.emit(False, f"Unexpected error: {exc}")

    # ── Private helpers ────────────────────────────────────────────────────────
    def _backup(self) -> None:
        """Main backup flow – runs inside the worker thread."""

        # 1. Pre-flight: disk space check ──────────────────────────────────────
        self.log.emit("Checking available disk space …")
        dest_dir = os.path.dirname(os.path.abspath(self.dest_path)) or "."
        try:
            usage     = shutil.disk_usage(dest_dir)
            free_gb   = usage.free / 1024 ** 3
            self.log.emit(f"Free space on target drive: {free_gb:.1f} GiB")
        except OSError as e:
            self.finished.emit(False, f"Disk space check failed: {e}")
            return

        # 2. Connect via SSH ────────────────────────────────────────────────────
        self.log.emit(f"Connecting to {self.username}@{self.host}:{self.port} …")
        try:
            self._ssh = _make_ssh(
                self.host, self.port, self.username, self.key_path, self.password
            )
        except paramiko.AuthenticationException:
            self.finished.emit(False, "Authentication failed – check credentials.")
            return
        except (socket.timeout, paramiko.ssh_exception.NoValidConnectionsError) as e:
            self.finished.emit(False, f"Connection failed: {e}")
            return
        except Exception as e:
            self.finished.emit(False, f"SSH error: {e}")
            return

        self.log.emit("SSH connection established.")

        try:
            self._stream_image(usage.free)
        finally:
            # Always close the SSH session on exit (cancel or error).
            self._cleanup_ssh()

    def _stream_image(self, free_bytes: int) -> None:
        """
        Query remote device size (best-effort), validate free space if known,
        then stream bytes.  If size cannot be determined, streaming continues
        without a progress percentage.
        """
        # 3. Determine remote device size (best-effort) ────────────────────────
        self.log.emit(f"Querying size of {self.remote_dev} …")
        remote_size: int | None = None

        for cmd in (
            f"sudo blockdev --getsize64 {self.remote_dev}",
            f"sudo fdisk -s {self.remote_dev} 2>/dev/null | awk '{{print $1*512}}'",
        ):
            try:
                _, stdout, _ = self._ssh.exec_command(cmd, timeout=15)
                out = stdout.read().decode().strip()
                if out.isdigit() and int(out) > 0:
                    remote_size = int(out)
                    break
            except Exception:
                pass

        if remote_size:
            self.log.emit(f"Remote device size: {remote_size / 1024**3:.2f} GiB")
        else:
            self.log.emit(
                "Warning: could not determine remote device size – "
                "skipping disk space check, progress will show MiB written."
            )

        # 4. Validate disk space (only when size is known) ─────────────────────
        if remote_size:
            required = remote_size + FREE_SPACE_BUFFER
            if free_bytes < required:
                self.finished.emit(
                    False,
                    f"Not enough disk space. Need {required/1024**3:.1f} GiB, "
                    f"have {free_bytes/1024**3:.1f} GiB."
                )
                return

        # 5. Open transport channel for the dd command ─────────────────────────
        dd_cmd = f"sudo dd if={self.remote_dev} bs={CHUNK_SIZE} status=none"
        self.log.emit(f"Starting stream: {dd_cmd}")

        transport = self._ssh.get_transport()
        self._channel = transport.open_session()
        self._channel.settimeout(60)
        self._channel.exec_command(dd_cmd)

        # 6. Stream bytes to local file ─────────────────────────────────────────
        bytes_written = 0
        last_pct      = -1
        LOG_INTERVAL  = 100 * 1024 * 1024   # log every 100 MiB when size unknown

        try:
            with open(self.dest_path, "wb") as img_file:
                while True:
                    if self._cancel_requested:
                        self.log.emit("Backup cancelled by user.")
                        self.finished.emit(False, "Cancelled.")
                        return

                    try:
                        chunk = self._channel.recv(CHUNK_SIZE)
                    except socket.timeout:
                        self.log.emit("Warning: read timeout, retrying …")
                        continue
                    except Exception as e:
                        self.finished.emit(False, f"Read error: {e}")
                        return

                    if not chunk:
                        break  # remote end closed (dd finished)

                    img_file.write(chunk)
                    bytes_written += len(chunk)
                    mb = bytes_written / 1024 ** 2

                    if remote_size:
                        pct = min(int(bytes_written * 100 / remote_size), 100)
                        if pct != last_pct:
                            self.progress.emit(pct)
                            last_pct = pct
                            self.log.emit(
                                f"Streamed {mb:.0f} MiB / "
                                f"{remote_size/1024**3:.1f} GiB  ({pct}%)"
                            )
                    else:
                        # No size known: pulse the bar and log every 100 MiB
                        self.progress.emit(-1)   # -1 → caller sets indeterminate
                        prev_interval = (bytes_written - len(chunk)) // LOG_INTERVAL
                        curr_interval = bytes_written // LOG_INTERVAL
                        if curr_interval > prev_interval:
                            self.log.emit(f"Streamed {mb:.0f} MiB …")

        except PermissionError as e:
            self.finished.emit(False, f"Cannot write to destination: {e}")
            return
        except OSError as e:
            self.finished.emit(False, f"File system error: {e}")
            return

        if self._cancel_requested:
            self.finished.emit(False, "Cancelled.")
            return

        self.progress.emit(100)
        self.log.emit(
            f"Stream complete. {bytes_written / 1024**3:.2f} GiB written to "
            f"{self.dest_path}"
        )

        # 7. Optional: shrink the image ────────────────────────────────────────
        if self.shrink:
            self._shrink_image()
        else:
            self.finished.emit(True, "Backup completed successfully.")

    def _shrink_image(self) -> None:
        """
        Attempt to shrink the image using PiShrink (if available locally).
        Falls back gracefully if the tool is not found.
        """
        self.log.emit("Attempting to shrink image …")
        import subprocess

        shrink_tools = [
            ["pishrink.sh", self.dest_path],         # Linux/WSL helper
            ["bash", "pishrink.sh", self.dest_path],  # explicit bash
        ]

        for cmd in shrink_tools:
            try:
                result = subprocess.run(
                    cmd,
                    capture_output = True,
                    text           = True,
                    timeout        = 600,   # 10 min max
                )
                if result.returncode == 0:
                    self.log.emit("Image shrunk successfully.")
                    self.finished.emit(True, "Backup + shrink completed successfully.")
                    return
                else:
                    self.log.emit(f"Shrink tool returned error: {result.stderr.strip()}")
            except FileNotFoundError:
                continue  # try next tool
            except subprocess.TimeoutExpired:
                self.log.emit("Shrink operation timed out.")
                break
            except Exception as e:
                self.log.emit(f"Shrink error: {e}")
                break

        self.log.emit(
            "Shrink tool not found or failed. Image is saved but not shrunk. "
            "You can run PiShrink manually: https://github.com/Drewsif/PiShrink"
        )
        self.finished.emit(True, "Backup complete (shrink skipped – tool not found).")

    def _cleanup_ssh(self) -> None:
        """Close channel and SSH client safely."""
        try:
            if self._channel and not self._channel.closed:
                self._channel.close()
        except Exception:
            pass
        try:
            if self._ssh:
                self._ssh.close()
                self.log.emit("SSH session closed.")
        except Exception:
            pass
