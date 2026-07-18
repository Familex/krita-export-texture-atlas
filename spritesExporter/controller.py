"""
Connects the backend and the frontend.
"""

from krita import Krita
from builtins import i18n
from PyQt6 import QtWidgets

from functools import partial
import traceback
from typing import Optional
from pathlib import Path

from .exporter import ExportError, Exporter
from .ui import Dialog

DIALOG_TITLE = "Sprites Exporter"


def _current_directory() -> Optional[Path]:
    doc = Krita.instance().activeDocument()
    return Path(doc.fileName()).parent if doc and doc.fileName() else None


def _pick_directory_dialog(directory: str) -> str:
    file_dialog = QtWidgets.QFileDialog()
    file_dialog.setWindowTitle(i18n("Choose Export Directory"))
    file_dialog.setSizeGripEnabled(True)

    # QFileDialog already seems to handle invalid directories fine
    file_dialog.setDirectory(directory)

    return file_dialog.getExistingDirectory()


def _change_dir(input: QtWidgets.QLineEdit):
    # Grab the output path on directory changed
    path = _pick_directory_dialog(input.text())
    if path != "":
        input.setText(path)


class Controller:
    def __init__(self):
        self.dialog = Dialog()

        self.dialog.main_settings.change_dir_clicked.connect(
            partial(_change_dir, self.dialog.main_settings.directory)
        )
        self.dialog.main_settings.reset_dir_clicked.connect(self.reset_export_dir)
        self.dialog.accepted.connect(self.export)

    def show_dialog(self):
        if self.dialog.main_settings.directory.text() == "":
            self.reset_export_dir()

        self.dialog.show()
        self.dialog.activateWindow()

    def export(self):
        exporter = Exporter(
            self.dialog.main_settings.values(),
            *self.dialog.atlas_settings.values(),
        )

        try:
            image_path, json_path = exporter.export()
        except ExportError as error:
            QtWidgets.QMessageBox.warning(None, i18n(DIALOG_TITLE), str(error))
        except Exception:
            QtWidgets.QMessageBox.critical(
                None,
                i18n(DIALOG_TITLE),
                i18n("Export failed with an unexpected error:")
                + f"\n\n{traceback.format_exc()}",
            )
        else:
            QtWidgets.QMessageBox.information(
                None,
                i18n(DIALOG_TITLE),
                i18n("Export finished:") + f"\n{image_path}\n{json_path}",
            )

    def reset_export_dir(self):
        path = _current_directory()
        if path:
            self.dialog.main_settings.directory.setText(str(path))
