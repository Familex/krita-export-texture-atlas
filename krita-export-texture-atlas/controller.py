"""
Connects the backend and the frontend.
"""

from krita import Krita
from builtins import i18n
from PyQt6 import QtCore, QtWidgets

from functools import partial
import traceback
from typing import Optional
from pathlib import Path

from .exporter import ExportError, Exporter
from .scene import is_exportable, node_uid
from .ui import DIALOG_TITLE, Dialog


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


def _top_level_entries() -> list[tuple[str, str]]:
    """(name, uid) pairs for every exportable top-level node."""

    doc = Krita.instance().activeDocument()
    if doc is None:
        return []

    return [
        (node.name(), node_uid(node))
        for node in doc.rootNode().childNodes()
        if is_exportable(node)
    ]


class Controller:
    def __init__(self):
        self.dialog = Dialog()

        self.dialog.main_settings.change_dir_clicked.connect(
            partial(_change_dir, self.dialog.main_settings.directory)
        )
        self.dialog.main_settings.reset_dir_clicked.connect(self.reset_export_dir)
        self.dialog.accepted.connect(self.export)

        # Debounce automatic preview updates triggered by settings changes
        self._preview_timer = QtCore.QTimer(self.dialog, singleShot=True, interval=300)
        self._preview_timer.timeout.connect(self.refresh_preview)

        self.dialog.preview_invalidated.connect(self._preview_timer.start)
        self.dialog.preview.refresh.clicked.connect(self.refresh_preview)

    def show_dialog(self):
        if self.dialog.main_settings.directory.text() == "":
            self.reset_export_dir()

        self.dialog.objects.populate(_top_level_entries())

        self.dialog.show()
        self.dialog.activateWindow()
        self.refresh_preview()

    def refresh_preview(self):
        self._preview_timer.stop()

        try:
            atlas, data = self._make_exporter().build()
        except ExportError as error:
            self.dialog.preview.show_message(str(error))
        except Exception:
            self.dialog.preview.show_message(
                i18n("Preview failed, see the console output.")
            )
            traceback.print_exc()
        else:
            size = data["meta"]["atlas_size"]
            self.dialog.preview.show_atlas(
                atlas,
                f"{size['w']} \u00d7 {size['h']} px, {len(data['frames'])} frames",
            )

    def export(self):
        self._preview_timer.stop()

        try:
            image_path, json_path = self._make_exporter().export()
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

    def _make_exporter(self) -> Exporter:
        return Exporter(
            self.dialog.main_settings.values(),
            *self.dialog.atlas_settings.values(),
            self.dialog.objects.excluded(),
        )
