"""
The UI that displays configuration options to the user with a dialog window.
"""

from krita import Krita
from builtins import i18n

from typing import Optional
from pathlib import Path

from .exporter import (
    Edges,
    DEFAULT_SPACE,
    DEFAULT_TIME,
    FrameExport,
    FrameTimes,
)
from .utils import KRITA_QT_VERSION, QtCore as QC, QtWidgets as QW


class MainSettings(QW.QFormLayout):
    change_dir_clicked = QC.pyqtSignal()
    reset_dir_clicked = QC.pyqtSignal()

    def __init__(self):
        super().__init__()
        ki = Krita.instance()

        self.name = QW.QLineEdit("spritesheet.png")
        self.name.setToolTip("Name of the exported spritesheet file")

        self.directory = QW.QLineEdit()
        self.directory.setToolTip("Directory to export the spritesheet to")

        change_dir = QW.QPushButton(ki.icon("folder"), None)
        change_dir.setToolTip("Open a file picker for the export directory")
        change_dir.clicked.connect(self.change_dir_clicked.emit)

        reset_dir = QW.QPushButton(ki.icon("view-refresh"), None)
        reset_dir.setToolTip(
            "Reset export directory to the current document's directory"
        )
        reset_dir.clicked.connect(self.reset_dir_clicked.emit)

        self.unique_frames = QW.QCheckBox("Only unique frames")
        self.write_texture_atlas = QW.QCheckBox("Write JSON texture atlas")
        self.write_texture_atlas.setToolTip(
            "Write a JSON texture atlas that can be used in game frameworks (e.g. Phaser 3)"
        )

        dir_layout = QW.QHBoxLayout()
        for w in (self.directory, change_dir, reset_dir):
            dir_layout.addWidget(w)

        self.addRow("Export name:", self.name)
        self.addRow("Export directory:", dir_layout)
        self.addRow(self.unique_frames)
        self.addRow(self.write_texture_atlas)

    def values(self) -> tuple[Path, bool, bool]:
        return (
            Path(self.directory.text(), self.name.text()),
            self.unique_frames.isChecked(),
            self.write_texture_atlas.isChecked(),
        )


class FramesExport(QW.QGroupBox):
    """
    Controls configuration for exporting individual frames as an image sequence.
    """

    change_dir_clicked = QC.pyqtSignal()
    reset_dir_clicked = QC.pyqtSignal()

    def __init__(self):
        super().__init__("Export image sequence")
        self.setCheckable(True)
        self.setChecked(False)
        ki = Krita.instance()

        self.base_name = QW.QLineEdit("sprite")
        self.custom_dir = QW.QCheckBox("Custom directory")

        self.directory = QW.QLineEdit()
        self.directory.setToolTip("Directory the images will be exported to")

        change_dir = QW.QPushButton(ki.icon("folder"), None)
        change_dir.setToolTip("Open a file picker for the images directory")
        change_dir.clicked.connect(self.change_dir_clicked.emit)

        reset_dir = QW.QPushButton(ki.icon("view-refresh"), None)
        reset_dir.setToolTip("Reset images directory based on the export path")
        reset_dir.clicked.connect(self.reset_dir_clicked.emit)

        self.force_new = QW.QCheckBox("Force new folder")
        self.force_new.setToolTip(
            "If checked, create a new frames folder if one exists.\nOtherwise, write the sprites in the existing folder (may overwrite files)"
        )

        dir_layout = QW.QHBoxLayout()
        dir_layout.addWidget(self.custom_dir)

        for w in (self.directory, change_dir, reset_dir):
            w.setEnabled(False)
            self.custom_dir.toggled.connect(w.setEnabled)
            dir_layout.addWidget(w)

        layout = QW.QFormLayout(self)
        layout.addRow("Base name:", self.base_name)
        layout.addRow(dir_layout)
        layout.addRow(self.force_new)

    def get_settings(self) -> Optional[FrameExport]:
        if self.isChecked():
            return FrameExport(
                self.base_name.text(),
                Path(self.directory.text()) if self.custom_dir.isChecked() else None,
                self.force_new.isChecked(),
            )
        return None


class SpritePlacement(QW.QFormLayout):
    """
    Lets the user choose if they want the spreadsheet horizontally or vertically
    oriented, and how many cells to put in that direction.
    """

    def __init__(self):
        super().__init__()
        self.setFieldGrowthPolicy(QW.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.setHorizontalSpacing(12)

        self.h_dir = QW.QRadioButton("Horizontal")
        self.h_dir.setChecked(True)
        self.h_dir.setToolTip("Order sprites horizontally")

        v_dir = QW.QRadioButton("Vertical")
        v_dir.setToolTip("Order sprites vertically")

        self.size = QW.QSpinBox(value=DEFAULT_SPACE, minimum=DEFAULT_SPACE)
        self.size.setSpecialValueText("Auto")
        self.size.setToolTip("Number of columns or rows in the spritesheet")

        self.columns = QW.QRadioButton("Columns")
        self.columns.setChecked(True)
        rows = QW.QRadioButton("Rows")

        dirs = QW.QVBoxLayout()
        dirs.addWidget(self.h_dir)
        dirs.addWidget(v_dir)
        dirs_buttons = QW.QButtonGroup()
        dirs_buttons.addButton(self.h_dir)
        dirs_buttons.addButton(v_dir)

        sizes = QW.QHBoxLayout()

        size_buttons_box = QW.QVBoxLayout()
        size_buttons_box.addWidget(self.columns)
        size_buttons_box.addWidget(rows)
        size_buttons = QW.QButtonGroup(size_buttons_box)
        size_buttons.addButton(self.columns)
        size_buttons.addButton(rows)

        sizes.addLayout(size_buttons_box)
        sizes.addWidget(self.size)

        self.addRow("Sprite placement:", dirs)
        self.addRow("Spritesheet size:", sizes)

    def values(self) -> tuple[bool, int, int]:
        columns = self.size.value()
        rows = DEFAULT_SPACE
        if not self.columns.isChecked():
            columns, rows = rows, columns

        return (self.h_dir.isChecked(), columns, rows)


class SpinBoxes(QW.QFormLayout):
    def __init__(self):
        super().__init__()

        self.start = QW.QSpinBox(minimum=DEFAULT_TIME, maximum=9999)
        self.end = QW.QSpinBox(minimum=DEFAULT_TIME, maximum=9999)
        self.step = QW.QSpinBox(value=1, minimum=1)

        # It seems that if a negative value is set in the constructor, it reverts to 0,
        # so they're set afterward instead
        self.start.setValue(DEFAULT_TIME)
        self.end.setValue(DEFAULT_TIME)

        for spin_box in (self.start, self.end, self.step):
            spin_box.setSpecialValueText("Auto")

        self.start.setToolTip("First frame time of the animation (inclusive)")
        self.end.setToolTip("Last frame time of the animation (inclusive)")
        self.step.setToolTip(
            "Only export each 'step' numbered frame. Defaults to every frame"
        )

        self.start.valueChanged.connect(self._start_value_changed)
        self.end.valueChanged.connect(self._end_value_changed)

        self.addRow("Start:", self.start)
        self.addRow("End:", self.end)
        self.addRow("Step:", self.step)

    def _start_value_changed(self, value: int) -> None:
        if value > self.end.value():
            self.end.setValue(value)

    def _end_value_changed(self, value: int) -> None:
        if value < self.start.value():
            self.start.setValue(value)

    def values(self) -> FrameTimes:
        return FrameTimes(self.start.value(), self.end.value(), self.step.value())


class EdgePadding(QW.QFormLayout):
    """
    Sets the padding (or clipping) of sprites.
    """

    def __init__(self):
        super().__init__()

        self.left = self._add_spin_box("left")
        self.top = self._add_spin_box("top")
        self.right = self._add_spin_box("right")
        self.bottom = self._add_spin_box("bottom")

    def values(self) -> Edges:
        return Edges(
            self.left.value(), self.top.value(), self.right.value(), self.bottom.value()
        )

    def _add_spin_box(self, edge: str) -> QW.QSpinBox:
        spin_box = QW.QSpinBox(value=0, minimum=-99, maximum=99)
        spin_box.setSuffix("px")
        spin_box.setToolTip(
            f"Pad the {edge} edge of each sprite, or clip it if negative"
        )

        self.addRow(f"Padding {edge}:", spin_box)
        return spin_box


class Dialog(QW.QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(i18n("SpritesheetExporter"))
        self.setModal(False)  # Don't block input to other windows
        self.setMinimumSize(425, 480)
        self.setSizeGripEnabled(True)

        self.main_settings = MainSettings()
        self.frames = FramesExport()
        self.edges = EdgePadding()

        # Extra settings group
        self.layers_as_animation = QW.QCheckBox("Use layers as animation frames")
        self.layers_as_animation.setToolTip(
            "Treat each layer as a frame instead of using the animation timeline"
        )
        self.placement = SpritePlacement()
        self.frame_times = SpinBoxes()

        if KRITA_QT_VERSION == 6:
            dialog_buttons = QW.QDialogButtonBox(
                QW.QDialogButtonBox.StandardButton.Ok | QW.QDialogButtonBox.StandardButton.Cancel
            )
        else:
            dialog_buttons = QW.QDialogButtonBox(QW.QDialogButtonBox.Ok | QW.QDialogButtonBox.Cancel)

        dialog_buttons.accepted.connect(self.accept)
        dialog_buttons.rejected.connect(self.reject)

        # Setup layouts
        spin_boxes = QW.QHBoxLayout()
        spin_boxes.addLayout(self.frame_times)
        spin_boxes.addLayout(self.edges)

        extra_settings = QW.QGroupBox("Extra Settings")
        extra_settings.setCheckable(True)
        extra_settings.setChecked(False)

        extras = QW.QVBoxLayout(extra_settings)
        extras.addWidget(self.layers_as_animation)
        extras.addSpacing(10)
        extras.addLayout(self.placement)
        extras.addSpacing(10)
        extras.addLayout(spin_boxes)

        root_layout = QW.QVBoxLayout(self)  # the box holding everything
        root_layout.addLayout(self.main_settings)
        root_layout.addWidget(self.frames)
        root_layout.addWidget(extra_settings)
        root_layout.addWidget(dialog_buttons)
