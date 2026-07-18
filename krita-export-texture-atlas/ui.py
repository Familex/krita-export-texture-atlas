"""
The UI that displays configuration options to the user with a dialog window.
"""

from krita import Krita
from builtins import i18n
from PyQt6 import QtCore as QC, QtWidgets as QW

from pathlib import Path


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


class Dialog(QW.QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(i18n("Sprites Exporter"))
        self.setModal(False)  # Don't block input to other windows
        self.setMinimumWidth(425)
        self.setSizeGripEnabled(True)

        description = QW.QLabel(
            "Exports visible layers as a packed texture atlas.\n"
            "Group layers become objects of the JSON scene description,\n"
            "preserving the layer hierarchy."
        )
        description.setWordWrap(True)

        self.main_settings = MainSettings()
        self.atlas_settings = AtlasSettings()

        dialog_buttons = QW.QDialogButtonBox(
            QW.QDialogButtonBox.StandardButton.Ok
            | QW.QDialogButtonBox.StandardButton.Cancel
        )

        dialog_buttons.accepted.connect(self.accept)
        dialog_buttons.rejected.connect(self.reject)

        atlas_group = QW.QGroupBox("Atlas Packing")
        atlas_group.setLayout(self.atlas_settings)

        root_layout = QW.QVBoxLayout(self)  # the box holding everything
        root_layout.addWidget(description)
        root_layout.addSpacing(8)
        root_layout.addLayout(self.main_settings)
        root_layout.addWidget(atlas_group)
        root_layout.addStretch()
        root_layout.addWidget(dialog_buttons)
