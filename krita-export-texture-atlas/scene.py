"""
Builds the scene graph from the Krita layer tree and extracts sprite images.

Group layers become objects that preserve the document hierarchy, and every
other visible layer with content becomes a leaf object with a packed frame.

Position and pivot semantics:
- An object's `pivot` is its anchor point, in pixels, relative to the top-left
  corner of its own bounds (and thus of its atlas frame). It comes from an
  optional child layer named "__pivot" (a single painted pixel) and is omitted
  when there is no pivot layer, in which case it defaults to (0, 0).
- An object's `position` is where its pivot point lies relative to its
  parent's pivot point (or to the document's top-left corner for top-level
  objects). Placing each frame so its pivot lands on the accumulated
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


def node_uid(node: Node) -> str:
    """A stable identifier for a node within the document."""
    return node.uniqueId().toString()


def is_exportable(node: Node) -> bool:
    """Whether the node can appear in the export at all."""
    return (
        node.visible()
        and node.name() != PIVOT_LAYER_NAME
        and node.type() not in _SKIPPED_TYPES
        and not node.type().endswith("mask")
    )


def _visual_bounds(node: Node, device_bounds: QtCore.QRect) -> QtCore.QRect:
    """
    Maps the node's device bounds through any direct transform-mask children,
    returning the region that the node actually occupies on the canvas.
    """

    transform = _node_mask_transform(node)

    if transform.isIdentity():
        return device_bounds

    return transform.mapRect(device_bounds)


def _node_mask_transform(node: Node) -> QtGui.QTransform:
    """Returns the combined affine transform from visible child transform masks."""
    transform = QtGui.QTransform()
    for child in node.childNodes():
        if child.type() == "transformmask" and child.visible():
            transform *= child.finalAffineTransform()
    return transform


def _document_position(
    bounds: QtCore.QRect, acc_transform: QtGui.QTransform
) -> tuple[float, float]:
    """
    Maps a node's visual bounds through ancestor transforms, returning the
    axis-aligned bounding-box top-left that the resulting sprite occupies in
    document coordinates.
    """
    if acc_transform.isIdentity():
        return float(bounds.x()), float(bounds.y())

    mapped = acc_transform.mapRect(bounds)
    return float(mapped.x()), float(mapped.y())


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
    pivot_canvas: tuple[int, int]
    pivot_local: Optional[tuple[int, int]] = None
    frame: Optional[str] = None
    children: list["SceneObject"] = field(default_factory=list)

    def to_dict(self, parent_pivot: tuple[int, int]) -> dict:
        """
        Serializes this object (and its children) for the JSON scene
        description, with positions relative to the parent's pivot point.
        """

        data = {
            "name": self.name,
            "position": {
                "x": self.pivot_canvas[0] - parent_pivot[0],
                "y": self.pivot_canvas[1] - parent_pivot[1],
            },
        }

        if self.frame is not None:
            data["frame"] = self.frame
        if self.pivot_local is not None:
            data["pivot"] = {"x": self.pivot_local[0], "y": self.pivot_local[1]}

        data["z"] = self.z
        data["children"] = [child.to_dict(self.pivot_canvas) for child in self.children]
        return data


class SceneBuilder:
    """
    Traverses a document's layer tree, collecting the object hierarchy and
    the sprite images to pack. Identical sprites are deduplicated and share
    a single frame.
    """

    def __init__(
        self,
        doc: Document,
        clip_to_canvas: bool = False,
        excluded_top_level: frozenset[str] = frozenset(),
    ):
        self._clip_rect = (
            QtCore.QRect(0, 0, doc.width(), doc.height()) if clip_to_canvas else None
        )
        self._root = doc.rootNode()
        self._excluded = excluded_top_level

        self.sprites: list[Sprite] = []
        self._frame_keys: set[str] = set()
        self._dedup: dict[tuple, str] = {}

    def build(self) -> list[SceneObject]:
        """
        Builds and returns the list of top-level scene objects, leaving out
        the excluded ones.
        """

        objects = []

        for child in self._root.childNodes():
            if node_uid(child) in self._excluded:
                continue

            obj = self._build_object(child, (), len(objects), 1.0, QtGui.QTransform())
            if obj is not None:
                objects.append(obj)

        return objects

    def _build_children(
        self,
        parent: Node,
        path: tuple[str, ...],
        opacity: float,
        acc_transform: QtGui.QTransform,
    ) -> list[SceneObject]:
        objects = []

        for child in parent.childNodes():
            obj = self._build_object(
                child, path, len(objects), opacity, acc_transform
            )
            if obj is not None:
                objects.append(obj)

        return objects

    def _build_object(
        self,
        node: Node,
        path: tuple[str, ...],
        z: int,
        opacity: float,
        acc_transform: QtGui.QTransform,
    ) -> Optional[SceneObject]:
        if not is_exportable(node):
            return None

        name = node.name()
        node_type = node.type()

        bounds = _visual_bounds(node, node.bounds())
        if self._clip_rect is not None:
            bounds = bounds.intersected(self._clip_rect)

        opacity *= node.opacity() / 255.0

        own_mask = _node_mask_transform(node)
        child_acc = acc_transform * own_mask

        if node_type == "grouplayer":
            children = self._build_children(
                node, path + (name,), opacity, child_acc
            )
            if not children:
                return None

            pos_x, pos_y = _document_position(bounds, acc_transform)
            obj = SceneObject(
                name, z, (round(pos_x), round(pos_y)), children=children,
            )

            pivot = self._find_pivot(node)
            if pivot is not None:
                pivot_own_visual = own_mask.map(
                    QtCore.QPointF(pivot[0], pivot[1])
                )
                pivot_acc_visual = acc_transform.map(pivot_own_visual)
                obj.pivot_canvas = (
                    round(pivot_acc_visual.x()),
                    round(pivot_acc_visual.y()),
                )
                obj.pivot_local = (
                    round(pivot_own_visual.x() - bounds.x()),
                    round(pivot_own_visual.y() - bounds.y()),
                )

            return obj

        if bounds.isEmpty():
            return None

        frame = self._register_sprite(
            node, bounds, path + (name,), opacity, acc_transform
        )
        pos_x, pos_y = _document_position(bounds, acc_transform)
        return SceneObject(
            name, z, (round(pos_x), round(pos_y)), frame=frame,
        )

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
        self,
        node: Node,
        bounds: QtCore.QRect,
        path: tuple[str, ...],
        opacity: float,
        acc_transform: QtGui.QTransform,
    ) -> str:
        """
        Extracts the node's composited image, applies ancestor transforms,
        and registers it for packing. Returns the frame key, reusing an
        existing one for identical images.
        """

        raw = bytes(
            node.projectionPixelData(
                bounds.x(), bounds.y(), bounds.width(), bounds.height()
            )
        )

        image = _to_image(raw, bounds.width(), bounds.height(), opacity)

        if not acc_transform.isIdentity():
            image = image.transformed(
                acc_transform, QtCore.Qt.TransformationMode.SmoothTransformation
            )
            tx_key = (
                acc_transform.m11(), acc_transform.m12(), acc_transform.m13(),
                acc_transform.m21(), acc_transform.m22(), acc_transform.m23(),
                acc_transform.m31(), acc_transform.m32(), acc_transform.m33(),
            )
        else:
            tx_key = None

        dedup_key = (
            image.width(),
            image.height(),
            round(opacity * 1000),
            raw,
            tx_key,
        )
        existing = self._dedup.get(dedup_key)
        if existing is not None:
            return existing

        key = self._unique_key("/".join(path))

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
