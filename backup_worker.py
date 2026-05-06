"""
backup_worker.py
----------------
QThread worker that handles all SSH/Paramiko logic for streaming the remote
SD card image to a local file.  All heavy I/O runs here so the UI stays
responsive.

Signals emitted to the UI:
  progress(int)        – 0-100 percentage
  log(str)             – human-readable status message
  finished(bool, str)  – success flag + final message
"""

import os
import shutil
import socket

import paramiko
from PySide6.QtCore import QThread, Signal


# ── Constants ──────────────────────────────────────────────────────────────────
CHUNK_SIZE = 1024 * 1024          # 1 MiB per read
FREE_SPACE_BUFFER = 2 * 1024 ** 3 # 2 GiB safety margin


class BackupWorker(QThread):
    """
    Streams /dev/mmcblk0 (or any remote block device / file) from a Raspberry
    Pi over SSH and writes the raw bytes to a local .img file.
    """

    # ── Signals ────────────────────────────────────────────────────────────────
    progress = Signal(int)          # 0-100
    log      = Signal(str)          # status text
    finished = Signal(bool, str)    # (success, message)

    # ── Constructor ────────────────────────────────────────────────────────────
    def __init__(
        self,
        host:        str,
        username:    str,
        key_path:    str,
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
        self.remote_dev = remote_dev   # e.g. /dev/mmcblk0
        self.dest_path  = dest_path    # local .img file
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
        self._ssh = paramiko.SSHClient()
        self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            self._ssh.connect(
                hostname     = self.host,
                port         = self.port,
                username     = self.username,
                key_filename = self.key_path,
                timeout      = 30,
                banner_timeout = 30,
                auth_timeout = 30,
            )
        except paramiko.AuthenticationException:
            self.finished.emit(False, "Authentication failed – check key path / username.")
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
        Query remote device size, validate free space, then stream bytes.
        """
        # 3. Determine remote device size ──────────────────────────────────────
        self.log.emit(f"Querying size of {self.remote_dev} …")
        size_cmd = f"sudo blockdev --getsize64 {self.remote_dev}"
        stdin, stdout, stderr = self._ssh.exec_command(size_cmd, timeout=15)
        err_output = stderr.read().decode().strip()
        size_output = stdout.read().decode().strip()

        if not size_output.isdigit():
            # Fallback: try /proc/partitions or stat
            self.log.emit(
                f"blockdev failed ({err_output}), trying wc -c fallback …"
            )
            # Note: this will read the whole device, so it may be slow/fail.
            size_cmd2 = f"sudo wc -c < {self.remote_dev}"
            _, stdout2, _ = self._ssh.exec_command(size_cmd2, timeout=15)
            size_output = stdout2.read().decode().strip()

        try:
            remote_size = int(size_output)
        except ValueError:
            self.finished.emit(
                False,
                f"Could not determine remote device size. Output: '{size_output}'"
            )
            return

        remote_size_gb = remote_size / 1024 ** 3
        self.log.emit(f"Remote device size: {remote_size_gb:.2f} GiB")

        # 4. Validate disk space ────────────────────────────────────────────────
        required = remote_size + FREE_SPACE_BUFFER
        if free_bytes < required:
            needed_gb  = required / 1024 ** 3
            free_gb    = free_bytes / 1024 ** 3
            self.finished.emit(
                False,
                f"Not enough disk space. Need {needed_gb:.1f} GiB, "
                f"have {free_gb:.1f} GiB."
            )
            return

        # 5. Open transport channel for the dd command ─────────────────────────
        dd_cmd = (
            f"sudo dd if={self.remote_dev} bs={CHUNK_SIZE} status=none"
        )
        self.log.emit(f"Starting stream: {dd_cmd}")

        transport = self._ssh.get_transport()
        self._channel = transport.open_session()
        self._channel.settimeout(60)          # seconds between chunks
        self._channel.exec_command(dd_cmd)

        # 6. Stream bytes to local file ─────────────────────────────────────────
        bytes_written = 0
        last_pct      = -1

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

                    pct = min(int(bytes_written * 100 / remote_size), 100)
                    if pct != last_pct:
                        self.progress.emit(pct)
                        last_pct = pct
                        mb = bytes_written / 1024 ** 2
                        self.log.emit(
                            f"Streamed {mb:.0f} MiB / {remote_size_gb:.1f} GiB  ({pct}%)"
                        )

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
