"""
ui_main.py
----------
Main application window built with PySide6.

Layout (top → bottom):
  ┌─ SSH Configuration (QGroupBox) ──────────────────────────────────────────┐
  │  Host / Port / Username / SSH Key / Remote Device / Destination File      │
  └──────────────────────────────────────────────────────────────────────────┘
  ┌─ Options ─────────────────────────────────────────────────────────────────┐
  │  [x] Shrink image after backup                                            │
  └──────────────────────────────────────────────────────────────────────────┘
  ┌─ Progress ─────────────────────────────────────────────────────────────────┐
  │  [████████░░░░░░░░]  42%                                                  │
  └──────────────────────────────────────────────────────────────────────────┘
  ┌─ Log ──────────────────────────────────────────────────────────────────────┐
  │  (scrolling QTextEdit, read-only)                                          │
  └──────────────────────────────────────────────────────────────────────────┘
  [ Start Backup ]   [ Cancel ]
"""

import os

from PySide6.QtCore    import Qt, QSettings
from PySide6.QtGui     import QFont, QTextCursor, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QLineEdit, QPushButton,
    QProgressBar, QTextEdit, QCheckBox, QFileDialog,
    QSpinBox, QStatusBar, QSizePolicy, QMessageBox,
    QComboBox,
)

from backup_worker import BackupWorker, ScanWorker


APP_NAME    = "Pi SD Backup"
ORG_NAME    = "PiBackupTool"
SETTINGS_FILE = "settings.ini"


class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(700, 620)
        self._worker: BackupWorker | None = None
        self._scan_worker: ScanWorker | None = None

        self._settings = QSettings(SETTINGS_FILE, QSettings.Format.IniFormat)

        self._build_ui()
        self._load_settings()

    # ── UI Construction ────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(10)
        root.setContentsMargins(14, 14, 14, 14)

        root.addWidget(self._build_ssh_group())
        root.addWidget(self._build_options_group())
        root.addWidget(self._build_progress_group())
        root.addWidget(self._build_log_group())
        root.addLayout(self._build_button_row())

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready.")

    # ── SSH Configuration group ────────────────────────────────────────────────
    def _build_ssh_group(self) -> QGroupBox:
        box = QGroupBox("SSH Configuration")
        form = QVBoxLayout(box)
        form.setSpacing(8)

        # Row helper
        def row(label_text: str, widget: QWidget) -> QHBoxLayout:
            lbl = QLabel(label_text)
            lbl.setFixedWidth(130)
            h = QHBoxLayout()
            h.addWidget(lbl)
            h.addWidget(widget)
            return h

        # Host
        self.inp_host = QLineEdit()
        self.inp_host.setPlaceholderText("e.g. 100.x.x.x  or  raspberrypi.local")
        form.addLayout(row("Host / IP:", self.inp_host))

        # Port
        self.inp_port = QSpinBox()
        self.inp_port.setRange(1, 65535)
        self.inp_port.setValue(22)
        form.addLayout(row("SSH Port:", self.inp_port))

        # Username
        self.inp_user = QLineEdit()
        self.inp_user.setPlaceholderText("e.g. pi")
        form.addLayout(row("Username:", self.inp_user))

        # SSH Key
        self.inp_key = QLineEdit()
        self.inp_key.setPlaceholderText("Path to private key file (id_rsa / id_ed25519)  [optional if password set]")
        btn_browse_key = QPushButton("Browse …")
        btn_browse_key.setFixedWidth(90)
        btn_browse_key.clicked.connect(self._browse_key)
        lbl_key = QLabel("SSH Key:")
        lbl_key.setFixedWidth(130)
        h_key = QHBoxLayout()
        h_key.addWidget(lbl_key)
        h_key.addWidget(self.inp_key)
        h_key.addWidget(btn_browse_key)
        form.addLayout(h_key)

        # Password (optional fallback / key passphrase)
        self.inp_password = QLineEdit()
        self.inp_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_password.setPlaceholderText("SSH password or key passphrase  [leave blank if not needed]")
        form.addLayout(row("Password:", self.inp_password))

        # Remote device – combobox populated by Scan
        dev_lbl = QLabel("Remote Device:")
        dev_lbl.setFixedWidth(130)
        self.cmb_remote = QComboBox()
        self.cmb_remote.setEditable(True)           # allow typing manually too
        self.cmb_remote.setMinimumWidth(160)
        self.cmb_remote.addItem("/dev/mmcblk0")     # sensible default
        self.btn_scan = QPushButton("Scan")
        self.btn_scan.setFixedWidth(90)
        self.btn_scan.setToolTip("Connect and list available block devices on the remote host")
        self.btn_scan.clicked.connect(self._on_scan)
        h_dev = QHBoxLayout()
        h_dev.addWidget(dev_lbl)
        h_dev.addWidget(self.cmb_remote)
        h_dev.addWidget(self.btn_scan)
        form.addLayout(h_dev)

        # Destination file
        dest_lbl = QLabel("Destination File:")
        dest_lbl.setFixedWidth(130)
        self.inp_dest = QLineEdit()
        self.inp_dest.setPlaceholderText("C:\\Backups\\pi_backup.img")
        btn_browse_dest = QPushButton("Browse …")
        btn_browse_dest.setFixedWidth(90)
        btn_browse_dest.clicked.connect(self._browse_dest)
        h_dest = QHBoxLayout()
        h_dest.addWidget(dest_lbl)
        h_dest.addWidget(self.inp_dest)
        h_dest.addWidget(btn_browse_dest)
        form.addLayout(h_dest)

        return box

    # ── Options group ──────────────────────────────────────────────────────────
    def _build_options_group(self) -> QGroupBox:
        box = QGroupBox("Options")
        h = QHBoxLayout(box)
        self.chk_shrink = QCheckBox(
            "Shrink image after backup  "
            "(requires PiShrink in PATH)"
        )
        self.chk_verify = QCheckBox(
            "Verify after backup  "
            "(SHA256 remote vs local)"
        )
        h.addWidget(self.chk_shrink)
        h.addSpacing(20)
        h.addWidget(self.chk_verify)
        h.addStretch()
        return box

    # ── Progress group ─────────────────────────────────────────────────────────
    def _build_progress_group(self) -> QGroupBox:
        box = QGroupBox("Progress")
        v = QVBoxLayout(box)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(26)
        v.addWidget(self.progress_bar)

        self.lbl_speed = QLabel("Speed: —    ETA: —")
        self.lbl_speed.setAlignment(Qt.AlignmentFlag.AlignRight)
        font = self.lbl_speed.font()
        font.setPointSize(font.pointSize() - 1)
        self.lbl_speed.setFont(font)
        v.addWidget(self.lbl_speed)
        return box

    # ── Log group ──────────────────────────────────────────────────────────────
    def _build_log_group(self) -> QGroupBox:
        box = QGroupBox("Log")
        v = QVBoxLayout(box)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 9))
        self.log_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        v.addWidget(self.log_view)
        return box

    # ── Button row ─────────────────────────────────────────────────────────────
    def _build_button_row(self) -> QHBoxLayout:
        h = QHBoxLayout()
        h.addStretch()

        self.btn_start = QPushButton("Start Backup")
        self.btn_start.setFixedHeight(36)
        self.btn_start.setMinimumWidth(140)
        self.btn_start.setDefault(True)
        self.btn_start.clicked.connect(self._on_start)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.setMinimumWidth(100)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._on_cancel)

        h.addWidget(self.btn_start)
        h.addWidget(self.btn_cancel)
        return h

    # ── Slots – UI interactions ────────────────────────────────────────────────
    def _on_scan(self) -> None:
        """Launch ScanWorker to discover block devices on the remote host."""
        host = self.inp_host.text().strip()
        user = self.inp_user.text().strip()
        if not host or not user:
            QMessageBox.warning(self, "Missing Input", "Enter Host and Username before scanning.")
            return

        self.btn_scan.setEnabled(False)
        self.btn_scan.setText("Scanning…")
        self._append_log(f"Scanning block devices on {host} …")

        self._scan_worker = ScanWorker(
            host     = host,
            port     = self.inp_port.value(),
            username = user,
            key_path = self.inp_key.text().strip() or None,
            password = self.inp_password.text() or None,
        )
        self._scan_worker.log.connect(self._append_log)
        self._scan_worker.devices_found.connect(self._on_devices_found)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.start()

    def _on_devices_found(self, devices: list) -> None:
        current = self.cmb_remote.currentText()
        self.cmb_remote.clear()
        for dev in devices:
            self.cmb_remote.addItem(dev)
        # Restore previous selection if still present, else pick first
        idx = self.cmb_remote.findText(current)
        self.cmb_remote.setCurrentIndex(idx if idx >= 0 else 0)

    def _on_scan_finished(self, success: bool, message: str) -> None:
        self.btn_scan.setEnabled(True)
        self.btn_scan.setText("Scan")
        if not success:
            QMessageBox.warning(self, "Scan Failed", message)

    def _browse_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select SSH Private Key", os.path.expanduser("~/.ssh"),
            "All Files (*)"
        )
        if path:
            self.inp_key.setText(path)

    def _browse_dest(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Choose Destination File",
            os.path.expanduser("~"),
            "Disk Images (*.img);;All Files (*)"
        )
        if path:
            self.inp_dest.setText(path)

    def _on_start(self) -> None:
        """Validate inputs then launch the worker thread."""
        if not self._validate_inputs():
            return

        self._save_settings()
        self._reset_ui_for_backup()

        self._worker = BackupWorker(
            host       = self.inp_host.text().strip(),
            username   = self.inp_user.text().strip(),
            key_path   = self.inp_key.text().strip() or None,
            password   = self.inp_password.text() or None,
            remote_dev = self.cmb_remote.currentText().strip(),
            dest_path  = self.inp_dest.text().strip(),
            shrink     = self.chk_shrink.isChecked(),
            verify     = self.chk_verify.isChecked(),
            port       = self.inp_port.value(),
        )

        # Connect signals
        self._worker.log.connect(self._append_log)
        self._worker.progress.connect(self._on_progress)
        self._worker.speed_update.connect(self._on_speed_update)
        self._worker.finished.connect(self._on_backup_finished)

        self._worker.start()

    def _on_cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.request_cancel()
            self.btn_cancel.setEnabled(False)
            self.statusBar().showMessage("Cancelling …")

    # ── Slots – worker signals ─────────────────────────────────────────────────
    def _on_progress(self, value: int) -> None:
        if value == -1:
            self.progress_bar.setRange(0, 0)
        else:
            if self.progress_bar.maximum() == 0:
                self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(value)

    def _on_speed_update(self, speed_mbs: float, eta_sec: float) -> None:
        if eta_sec >= 0:
            h   = int(eta_sec) // 3600
            m   = (int(eta_sec) % 3600) // 60
            s   = int(eta_sec) % 60
            if h > 0:
                eta_str = f"{h}h {m:02d}m {s:02d}s"
            elif m > 0:
                eta_str = f"{m}m {s:02d}s"
            else:
                eta_str = f"{s}s"
        else:
            eta_str = "—"

        text = f"Speed: {speed_mbs:.1f} MB/s    ETA: {eta_str}"
        self.lbl_speed.setText(text)
        self.statusBar().showMessage(text)

    def _append_log(self, message: str) -> None:
        self.log_view.append(message)
        # Auto-scroll to bottom
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_view.setTextCursor(cursor)
        self.statusBar().showMessage(message)

    def _on_backup_finished(self, success: bool, message: str) -> None:
        self._reset_ui_idle()
        if success:
            self.progress_bar.setValue(100)
            self._append_log(f"DONE: {message}")
            QMessageBox.information(self, "Backup Complete", message)
        else:
            self._append_log(f"ERROR: {message}")
            QMessageBox.critical(self, "Backup Failed", message)

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _validate_inputs(self) -> bool:
        errors = []
        if not self.inp_host.text().strip():
            errors.append("• Host / IP is required.")
        if not self.inp_user.text().strip():
            errors.append("• Username is required.")
        key      = self.inp_key.text().strip()
        password = self.inp_password.text()
        if not key and not password:
            errors.append("• Provide either an SSH Key path or a Password (or both).")
        elif key and not os.path.isfile(key):
            errors.append(f"• SSH Key file not found: {key}")
        if not self.cmb_remote.currentText().strip():
            errors.append("• Remote device path is required (use Scan or type manually).")
        if not self.inp_dest.text().strip():
            errors.append("• Destination file path is required.")

        if errors:
            QMessageBox.warning(
                self, "Missing / Invalid Input",
                "Please fix the following before starting:\n\n" + "\n".join(errors)
            )
            return False
        return True

    def _reset_ui_for_backup(self) -> None:
        self.log_view.clear()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.lbl_speed.setText("Speed: —    ETA: —")
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.statusBar().showMessage("Starting backup …")

    def _reset_ui_idle(self) -> None:
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.lbl_speed.setText("Speed: —    ETA: —")
        self.statusBar().showMessage("Idle.")

    # ── Settings persistence ───────────────────────────────────────────────────
    def _save_settings(self) -> None:
        s = self._settings
        s.setValue("host",    self.inp_host.text())
        s.setValue("port",    self.inp_port.value())
        s.setValue("user",    self.inp_user.text())
        s.setValue("key",     self.inp_key.text())
        # NOTE: password is intentionally NOT saved to disk for security.
        s.setValue("remote",  self.cmb_remote.currentText())
        s.setValue("dest",    self.inp_dest.text())
        s.setValue("shrink",  self.chk_shrink.isChecked())
        s.setValue("verify",  self.chk_verify.isChecked())

    def _load_settings(self) -> None:
        s = self._settings
        self.inp_host.setText(s.value("host",   ""))
        self.inp_port.setValue(int(s.value("port", 22)))
        self.inp_user.setText(s.value("user",   "pi"))
        self.inp_key.setText(s.value("key",     ""))
        # Password is never persisted; always starts blank.
        saved_remote = s.value("remote", "/dev/mmcblk0")
        if self.cmb_remote.findText(saved_remote) == -1:
            self.cmb_remote.addItem(saved_remote)
        self.cmb_remote.setCurrentText(saved_remote)
        self.inp_dest.setText(s.value("dest",   ""))
        shrink = s.value("shrink", False)
        if isinstance(shrink, str):
            shrink = shrink.lower() == "true"
        self.chk_shrink.setChecked(bool(shrink))

        verify = s.value("verify", False)
        if isinstance(verify, str):
            verify = verify.lower() == "true"
        self.chk_verify.setChecked(bool(verify))

    # ── Window close ──────────────────────────────────────────────────────────
    def closeEvent(self, event) -> None:
        if self._worker and self._worker.isRunning():
            reply = QMessageBox.question(
                self, "Backup in Progress",
                "A backup is currently running. Cancel it and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._worker.request_cancel()
                self._worker.wait(5000)  # give it 5 s to clean up
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
