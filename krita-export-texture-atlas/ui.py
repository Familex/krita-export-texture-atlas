"""
The UI that displays configuration options to the user with a dialog window.
"""

from krita import Krita
from builtins import i18n
from PyQt6 import QtCore as QC, QtGui as QG, QtWidgets as QW

from pathlib import Path
from typing import Optional

DIALOG_TITLE = "Export Texture Atlas"


class MainSettings(QW.QFormLayout):
    change_dir_clicked = QC.pyqtSignal()
    reset_dir_clicked = QC.pyqtSignal()

    def __init__(self):
        super().__init__()
        ki = Krita.instance()

        self.name = QW.QLineEdit("atlas.png")
        self.name.setToolTip("Name of the exported atlas image")

        self.directory = QW.QLineEdit()
        self.directory.setToolTip("Directory to export the atlas to")

        change_dir = QW.QPushButton(ki.icon("folder"), None)
        change_dir.setToolTip("Open a file picker for the export directory")
        change_dir.clicked.connect(self.change_dir_clicked.emit)

        reset_dir = QW.QPushButton(ki.icon("view-refresh"), None)
        reset_dir.setToolTip(
            "Reset export directory to the current document's directory"
        )
        reset_dir.clicked.connect(self.reset_dir_clicked.emit)

        dir_layout = QW.QHBoxLayout()
        for w in (self.directory, change_dir, reset_dir):
            dir_layout.addWidget(w)

        self.addRow("Export name:", self.name)
        self.addRow("Export directory:", dir_layout)

    def values(self) -> Path:
        return Path(self.directory.text(), self.name.text())


class AtlasSettings(QW.QFormLayout):
    """Options controlling how the sprites are packed."""

    def __init__(self):
        super().__init__()

        self.spacing = QW.QSpinBox(value=2, minimum=0, maximum=64)
        self.spacing.setSuffix("px")
        self.spacing.setToolTip(
            "Minimum space between packed sprites, to avoid texture bleeding"
        )

        self.power_of_two = QW.QCheckBox("Power-of-two atlas size")
        self.power_of_two.setToolTip(
            "Round the atlas width and height up to powers of two"
        )

        self.clip_to_canvas = QW.QCheckBox("Clip sprites to canvas")
        self.clip_to_canvas.setToolTip(
            "Ignore layer content that lies outside the canvas bounds"
        )

        self.addRow("Sprite spacing:", self.spacing)
        self.addRow(self.power_of_two)
        self.addRow(self.clip_to_canvas)

    def values(self) -> tuple[int, bool, bool]:
        return (
            self.spacing.value(),
            self.power_of_two.isChecked(),
            self.clip_to_canvas.isChecked(),
        )


class ObjectList(QW.QListWidget):
    """A checkable list of top-level frames to include in the export."""

    def __init__(self):
        super().__init__()
        self.setToolTip("Uncheck frames to leave them out of the export")
        self.setSelectionMode(QW.QAbstractItemView.SelectionMode.NoSelection)

    def populate(self, entries: list[tuple[str, str]]):
        """
        Fills the list with (name, uid) entries, keeping the check state of
        entries that were already listed. New entries start checked.
        """

        previous = self._check_states()

        self.blockSignals(True)  # Don't spam itemChanged while rebuilding
        self.clear()

        for name, uid in entries:
            item = QW.QListWidgetItem(name)
            item.setFlags(item.flags() | QC.Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(QC.Qt.ItemDataRole.UserRole, uid)
            item.setCheckState(
                QC.Qt.CheckState.Checked
                if previous.get(uid, True)
                else QC.Qt.CheckState.Unchecked
            )
            self.addItem(item)

        self.blockSignals(False)

    def excluded(self) -> frozenset[str]:
        """The uids of all unchecked entries."""
        return frozenset(
            uid for uid, checked in self._check_states().items() if not checked
        )

    def _check_states(self) -> dict[str, bool]:
        states = {}

        for i in range(self.count()):
            item = self.item(i)
            states[item.data(QC.Qt.ItemDataRole.UserRole)] = (
                item.checkState() == QC.Qt.CheckState.Checked
            )

        return states


class AtlasPreview(QW.QGroupBox):
    """Shows the packed atlas image and its properties."""

    def __init__(self):
        super().__init__("Preview")
        self.setStyleSheet("QGroupBox::title { subcontrol-position: top center; }")

        self._pixmap: Optional[QG.QPixmap] = None

        self.image = QW.QLabel()
        self.image.setAlignment(QC.Qt.AlignmentFlag.AlignCenter)
        self.image.setWordWrap(True)
        self.image.setStyleSheet("background-color: #606060; color: #f0f0f0;")
        self.image.setMinimumSize(240, 240)
        # Ignore the pixmap's size so the label can freely shrink and grow
        self.image.setSizePolicy(
            QW.QSizePolicy.Policy.Ignored, QW.QSizePolicy.Policy.Ignored
        )

        self.info = QW.QLabel()
        self.info.setAlignment(QC.Qt.AlignmentFlag.AlignCenter)

        self.refresh = QW.QPushButton(
            Krita.instance().icon("view-refresh"), i18n("Refresh preview")
        )
        self.refresh.setToolTip("Repack the atlas and update the preview")

        layout = QW.QVBoxLayout(self)
        layout.addWidget(self.image, 1)
        layout.addWidget(self.info)
        layout.addWidget(self.refresh)

    def show_atlas(self, image: QG.QImage, info: str):
        # Draw a 2px outline along the image's edges so the atlas dimensions
        # are always visible against the preview background
        pen = QG.QPen(QG.QColor(0xB0, 0xB0, 0xB0), 2)
        pen.setCosmetic(True)  # keep the stroke width independent of scaling
        bordered = image.copy()
        painter = QG.QPainter(bordered)
        painter.setCompositionMode(
            QG.QPainter.CompositionMode.CompositionMode_SourceOver
        )
        painter.setPen(pen)
        painter.drawRect(0, 0, image.width() - 1, image.height() - 1)
        painter.end()

        self._pixmap = QG.QPixmap.fromImage(bordered)
        self.image.setText("")
        self.info.setText(info)
        self._update_scaled()

    def show_message(self, message: str):
        self._pixmap = None
        self.image.setPixmap(QG.QPixmap())
        self.image.setText(message)
        self.info.setText("")

    def _update_scaled(self):
        if self._pixmap is None:
            return

        size = self.image.contentsRect().size()
        pixmap = self._pixmap

        if pixmap.width() > size.width() or pixmap.height() > size.height():
            pixmap = pixmap.scaled(
                size,
                QC.Qt.AspectRatioMode.KeepAspectRatio,
                QC.Qt.TransformationMode.SmoothTransformation,
            )

        self.image.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scaled()


class Dialog(QW.QDialog):
    preview_invalidated = QC.pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(i18n(DIALOG_TITLE))
        self.setModal(False)  # Don't block input to other windows
        self.setMinimumSize(720, 460)
        self.setSizeGripEnabled(True)

        description = QW.QLabel(
            "Exports visible layers as a packed texture atlas. Group layers become "
            "objects of the JSON scene description, preserving the layer hierarchy."
        )
        description.setWordWrap(True)

        self.main_settings = MainSettings()
        self.atlas_settings = AtlasSettings()
        self.objects = ObjectList()
        self.preview = AtlasPreview()

        dialog_buttons = QW.QDialogButtonBox(
            QW.QDialogButtonBox.StandardButton.Ok
            | QW.QDialogButtonBox.StandardButton.Cancel
        )

        dialog_buttons.accepted.connect(self.accept)
        dialog_buttons.rejected.connect(self.reject)

        atlas_group = QW.QGroupBox("Atlas Packing")
        atlas_group.setLayout(self.atlas_settings)

        objects_group = QW.QGroupBox("Frames")
        objects_layout = QW.QVBoxLayout(objects_group)
        objects_layout.addWidget(self.objects)

        left_column = QW.QVBoxLayout()
        left_column.addLayout(self.main_settings)
        left_column.addWidget(atlas_group)
        left_column.addWidget(objects_group, 1)

        columns = QW.QHBoxLayout()
        columns.addLayout(left_column, 1)
        columns.addWidget(self.preview, 1)

        root_layout = QW.QVBoxLayout(self)  # the box holding everything
        root_layout.addWidget(description)
        root_layout.addSpacing(8)
        root_layout.addLayout(columns, 1)
        root_layout.addWidget(dialog_buttons)

        # Any change to these settings makes the preview stale
        self.atlas_settings.spacing.valueChanged.connect(self._invalidate_preview)
        self.atlas_settings.power_of_two.toggled.connect(self._invalidate_preview)
        self.atlas_settings.clip_to_canvas.toggled.connect(self._invalidate_preview)
        self.objects.itemChanged.connect(self._invalidate_preview)

    def _invalidate_preview(self, *_):
        self.preview_invalidated.emit()
