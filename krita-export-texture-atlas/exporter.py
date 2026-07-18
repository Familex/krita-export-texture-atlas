"""
The backend that exports the document as a packed texture atlas with a JSON
scene description.
"""

from krita import Krita, Document
from PyQt6 import QtCore, QtGui

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Optional

from .packer import PackError, Placement, pack_rects
from .scene import SceneBuilder, Sprite

SCHEMA_VERSION = 1


class ExportError(Exception):
    """Raised when the export cannot be completed, with a user-facing message."""


@dataclass
class Exporter:
    export_path: Path
    spacing: int
    power_of_two: bool
    clip_to_canvas: bool
    excluded_top_level: frozenset[str] = frozenset()

    def __post_init__(self):
        if self.export_path.suffix.lower() != ".png":
            self.export_path = self.export_path.with_suffix(
                self.export_path.suffix + ".png"
            )

    def build(self) -> tuple[QtGui.QImage, dict]:
        """
        Builds the packed atlas image and the JSON scene data in memory,
        without writing any files. Used for both previewing and exporting.
        """

        doc = Krita.instance().activeDocument()
        if doc is None:
            raise ExportError("No active document. Open a document to export.")

        source, temp = _rgba_u8_source(doc)
        try:
            builder = SceneBuilder(source, self.clip_to_canvas, self.excluded_top_level)
            objects = builder.build()

            if not builder.sprites:
                raise ExportError("No visible layers with content to export.")

            sizes = [(s.key, s.image.width(), s.image.height()) for s in builder.sprites]
            try:
                placements, atlas_w, atlas_h = pack_rects(
                    sizes, self.spacing, self.power_of_two
                )
            except PackError as error:
                raise ExportError(str(error)) from error

            atlas = _render_atlas(builder.sprites, placements, atlas_w, atlas_h)

            data = {
                "meta": {
                    "version": SCHEMA_VERSION,
                    "image": self.export_path.name,
                    "atlas_size": {"w": atlas_w, "h": atlas_h},
                },
                "frames": {
                    key: {"x": p.x, "y": p.y, "w": p.w, "h": p.h}
                    for key, p in sorted(placements.items())
                },
                "objects": [obj.to_dict((0, 0)) for obj in objects],
            }

            return atlas, data
        finally:
            if temp is not None:
                temp.close()

    def export(self) -> tuple[Path, Path]:
        """
        Exports the active document. Returns the written (image, json) paths.
        """

        atlas, data = self.build()

        self.export_path.parent.mkdir(parents=True, exist_ok=True)
        if not atlas.save(str(self.export_path), "PNG"):
            raise ExportError(f"Could not save the atlas image to {self.export_path}")

        json_path = self.export_path.with_suffix(".json")
        with json_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)

        return self.export_path, json_path


def _rgba_u8_source(doc: Document) -> tuple[Document, Optional[Document]]:
    """
    Returns a document guaranteed to be 8-bit RGBA to read pixel data from.

    If the active document uses another color space, a temporary converted
    clone is returned as (source, clone); the caller must close the clone.
    """

    if doc.colorModel() == "RGBA" and doc.colorDepth() == "U8":
        return doc, None

    temp = doc.clone()
    temp.setBatchmode(True)
    temp.setColorSpace("RGBA", "U8", _srgb_profile())
    temp.refreshProjection()
    temp.waitForDone()
    return temp, temp


def _srgb_profile() -> str:
    profiles = Krita.instance().profiles("RGBA", "U8")

    for profile in profiles:
        if "srgb" in profile.lower():
            return profile

    return profiles[0] if profiles else ""


def _render_atlas(
    sprites: list[Sprite], placements: dict[str, Placement], width: int, height: int
) -> QtGui.QImage:
    """Draws every packed sprite into the final atlas image."""

    atlas = QtGui.QImage(width, height, QtGui.QImage.Format.Format_RGBA8888)
    atlas.fill(0)

    painter = QtGui.QPainter(atlas)
    # Copy pixels exactly instead of alpha-blending onto the transparent canvas
    painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Source)

    for sprite in sprites:
        placement = placements[sprite.key]
        painter.drawImage(QtCore.QPoint(placement.x, placement.y), sprite.image)

    painter.end()
    return atlas
