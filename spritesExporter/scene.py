"""
Builds the scene graph from the Krita layer tree and extracts sprite images.

Group layers become objects that preserve the document hierarchy, and every
other visible layer with content becomes a leaf object with a packed frame.

Position and origin semantics:
- An object's `origin` is its pivot point, in pixels, relative to the top-left
  corner of its own bounds (and thus of its atlas frame). It comes from an
  optional child layer named "__pivot" (a single painted pixel) and is omitted
  when there is no pivot, in which case it defaults to (0, 0).
- An object's `position` is where its origin point lies relative to its
  parent's origin point (or to the document's top-left corner for top-level
  objects). Placing each frame so its origin lands on the accumulated
  position reproduces the original document exactly.
"""

from krita import Document, Node
from PyQt6 import QtCore, QtGui

from dataclasses import dataclass, field
from typing import Optional

PIVOT_LAYER_NAME = "__pivot"

# Filter (adjustment) layers only make sense composited with what is below
# them, so they cannot be exported as standalone sprites.
_SKIPPED_TYPES = {"filterlayer"}


@dataclass
class Sprite:
    """An extracted image to pack, identified by its frame key."""

    key: str
    image: QtGui.QImage


@dataclass
class SceneObject:
    """A node of the exported hierarchy."""

    name: str
    z: int
    origin_canvas: tuple[int, int]
    origin_local: Optional[tuple[int, int]] = None
    frame: Optional[str] = None
    children: list["SceneObject"] = field(default_factory=list)

    def to_dict(self, parent_origin: tuple[int, int]) -> dict:
        """
        Serializes this object (and its children) for the JSON scene
        description, with positions relative to the parent's origin point.
        """

        data = {
            "name": self.name,
            "position": {
                "x": self.origin_canvas[0] - parent_origin[0],
                "y": self.origin_canvas[1] - parent_origin[1],
            },
        }

        if self.frame is not None:
            data["frame"] = self.frame
        if self.origin_local is not None:
            data["origin"] = {"x": self.origin_local[0], "y": self.origin_local[1]}

        data["z"] = self.z
        data["children"] = [child.to_dict(self.origin_canvas) for child in self.children]
        return data


class SceneBuilder:
    """
    Traverses a document's layer tree, collecting the object hierarchy and
    the sprite images to pack. Identical sprites are deduplicated and share
    a single frame.
    """

    def __init__(self, doc: Document, clip_to_canvas: bool = False):
        self._clip_rect = (
            QtCore.QRect(0, 0, doc.width(), doc.height()) if clip_to_canvas else None
        )
        self._root = doc.rootNode()

        self.sprites: list[Sprite] = []
        self._frame_keys: set[str] = set()
        self._dedup: dict[tuple, str] = {}

    def build(self) -> list[SceneObject]:
        """Builds and returns the list of top-level scene objects."""
        return self._build_children(self._root, (), 1.0)

    def _build_children(
        self, parent: Node, path: tuple[str, ...], opacity: float
    ) -> list[SceneObject]:
        objects = []

        for child in parent.childNodes():
            obj = self._build_object(child, path, len(objects), opacity)
            if obj is not None:
                objects.append(obj)

        return objects

    def _build_object(
        self, node: Node, path: tuple[str, ...], z: int, opacity: float
    ) -> Optional[SceneObject]:
        name = node.name()
        if name == PIVOT_LAYER_NAME or not node.visible():
            return None

        node_type = node.type()
        if node_type in _SKIPPED_TYPES or node_type.endswith("mask"):
            return None

        bounds = node.bounds()
        if self._clip_rect is not None:
            bounds = bounds.intersected(self._clip_rect)

        opacity *= node.opacity() / 255.0

        if node_type == "grouplayer":
            children = self._build_children(node, path + (name,), opacity)
            if not children:
                return None

            obj = SceneObject(name, z, (bounds.x(), bounds.y()), children=children)

            pivot = self._find_pivot(node)
            if pivot is not None:
                obj.origin_canvas = pivot
                obj.origin_local = (pivot[0] - bounds.x(), pivot[1] - bounds.y())

            return obj

        if bounds.isEmpty():
            return None

        frame = self._register_sprite(node, bounds, path + (name,), opacity)
        return SceneObject(name, z, (bounds.x(), bounds.y()), frame=frame)

    def _find_pivot(self, group: Node) -> Optional[tuple[int, int]]:
        """
        Looks for a direct child layer named "__pivot" and returns the canvas
        position of its painted pixel. Pivot layers are expected to hold a
        single pixel of data; for larger marks, the center of their bounds is
        used. Hidden pivot layers are respected as well.
        """

        for child in group.childNodes():
            if child.name() != PIVOT_LAYER_NAME:
                continue

            bounds = child.bounds()
            if bounds.isEmpty():
                return None
            return (
                bounds.x() + (bounds.width() - 1) // 2,
                bounds.y() + (bounds.height() - 1) // 2,
            )

        return None

    def _register_sprite(
        self, node: Node, bounds: QtCore.QRect, path: tuple[str, ...], opacity: float
    ) -> str:
        """
        Extracts the node's composited image and registers it for packing.
        Returns the frame key, reusing an existing one for identical images.
        """

        raw = bytes(
            node.projectionPixelData(
                bounds.x(), bounds.y(), bounds.width(), bounds.height()
            )
        )

        dedup_key = (bounds.width(), bounds.height(), round(opacity * 1000), raw)
        existing = self._dedup.get(dedup_key)
        if existing is not None:
            return existing

        key = self._unique_key("/".join(path))
        image = _to_image(raw, bounds.width(), bounds.height(), opacity)

        self.sprites.append(Sprite(key, image))
        self._frame_keys.add(key)
        self._dedup[dedup_key] = key
        return key

    def _unique_key(self, base: str) -> str:
        key = base
        suffix = 2

        while key in self._frame_keys:
            key = f"{base}#{suffix}"
            suffix += 1

        return key


def _to_image(raw: bytes, width: int, height: int, opacity: float) -> QtGui.QImage:
    """
    Converts Krita's raw BGRA pixel buffer to an RGBA QImage, baking the
    layer's effective opacity into the alpha channel.
    """

    image = QtGui.QImage(
        raw, width, height, width * 4, QtGui.QImage.Format.Format_RGBA8888
    ).rgbSwapped()  # rgbSwapped() also copies the data out of the raw buffer

    if opacity >= 1.0:
        return image

    faded = QtGui.QImage(width, height, QtGui.QImage.Format.Format_RGBA8888)
    faded.fill(0)

    painter = QtGui.QPainter(faded)
    painter.setOpacity(opacity)
    painter.drawImage(0, 0, image)
    painter.end()

    return faded
