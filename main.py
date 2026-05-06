"""
main.py
-------
Entry point for the Pi SD Backup application.

Usage (Windows PowerShell / CMD):
    pip install -r requirements.txt
    python main.py
"""

import sys

from PySide6.QtWidgets import QApplication

from ui_main import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Pi SD Backup")
    app.setOrganizationName("PiBackupTool")

    # Apply a clean, cross-platform style.
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
