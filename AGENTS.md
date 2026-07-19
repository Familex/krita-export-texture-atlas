# AGENTS.md — krita-export-texture-atlas

If you found issues in this document, you are free to fix them ASAP.

## Project
Krita plugin. Exports visible layers as packed PNG atlas + JSON scene.
Requires Krita 6.0+. PyQt6 API.

## Files (krita-export-texture-atlas/)
- `plugin.py` — Extension entry, menu item `Tools > Scripts > Export as Texture Atlas`
- `controller.py` — Mediates UI ↔ exporter, debounced preview updates
- `exporter.py` — Pipeline: color convert → scene build → pack → render atlas → write files
- `scene.py` — Traverses layer tree, extracts sprites, builds SceneObject hierarchy. **Most bugs live here.**
- `packer.py` — MaxRects bin-packing (Best Short Side Fit)
- `ui.py` — Qt dialog with settings, frame list, atlas preview

## JSON output schema (see json_texture_atlas_schema.json)
```json
{
  "meta": {"version":1, "image":"atlas.png", "atlas_size":{"w":W,"h":H}},
  "frames": {"key": {"x":ATLAS_X,"y":ATLAS_Y,"w":W,"h":H}, ...},
  "objects": [{
    "name":"...", "z":INT,
    "position":{"x":NUM,"y":NUM}, // pivot_canvas - parent_pivot
    "frame":"key", // absent on pure groups
    "pivot":{"x":NUM,"y":NUM}, // optional, only groups with __pivot child
    "children":[...]
  }, ...]
}
```

## Coordinate systems
- **Canvas/Document space**: Krita image coordinates, origin at top-left. `node.bounds()` returns QRect in this space.
- **Atlas space**: packed sprite rectangle within atlas.png. `frames[key]` x/y/w/h.
- **JSON position**: `pivot_canvas - parent_pivot`. Top-level parent_pivot=(0,0). Placing each frame so its pivot lands on position reproduces the document.
- **pivot_canvas**: SceneObject field, the node's pivot point in document space (before subtracting parent). For leaf nodes = visual_bounds.topLeft. For groups with __pivot = that pivot pixel's document position.
- **pivot_local**: offset from frame/visual-bounds top-left to pivot point. Only on groups with __pivot.

## Transform mask handling (scene.py)

### Core functions
- `_node_mask_transform(node)` → QTransform: multiplies `finalAffineTransform()` of all visible `child.type()=="transformmask"`. Used for both bounds calc and ancestor propagation.
- `_visual_bounds(node, device_bounds)` → QRect: `_node_mask_transform(node).mapRect(device_bounds)`. Returns axis-aligned bounding box of transformed content.
- `_document_position(bounds, acc_transform)` → (float,float): if acc_transform is identity returns bounds.topLeft; else `acc_transform.mapRect(bounds).topLeft()`.

### How transform propagation works
`_build_object(node, path, z, opacity, acc_transform)`:
1. `bounds = _visual_bounds(node, node.bounds())` — own mask applied to native bounds
2. `own_mask = _node_mask_transform(node)` — this node's own mask QTransform
3. `child_acc = acc_transform * own_mask` — composed: apply own_mask first, then acc_transform
4. Pass `child_acc` to children via `_build_children`
5. Position: `_document_position(bounds, acc_transform)` — applies ancestor transforms to visual bounds

### Leaf node image transformation (`_register_sprite`)
- Extract raw pixels via `node.projectionPixelData(bounds)` — **projectionPixelData does NOT include ancestor mask effects**, only own mask (already in `bounds` from step 1 above).
- Convert BGRA→RGBA, bake opacity: `_to_image(raw, w, h, opacity)`
- If acc_transform non-identity: `image.transformed(acc_transform * QTransform.fromTranslate(bounds.x(), bounds.y()))`
  - `to_canvas` translate is CRITICAL: without it, the transform is applied from image origin (0,0) instead of the image's actual canvas position (bounds.x(), bounds.y()). This causes shift errors when the mask has rotation or non-origin center.
  - Filter mode: `FastTransformation` (nearest neighbor, matches common mask filter). Not read from mask XML.
- Dedup key: `(image.width(), image.height(), round(opacity*1000), raw_bytes, tx_key_or_None)`. `tx_key` = 9 QTransform floats for identity check.

### Pivot handling with transforms
- `_find_pivot(node)` returns native canvas position of __pivot marker pixel.
- Pivot visual position: `(acc_transform * own_mask).map(QPointF(pivot_native))`
- pivot_canvas overridden to this visual position.
- pivot_local: `own_mask.map(pivot_native) - visual_bounds.topLeft` (in node's own visual space).

### Known limitations
- Group masks with scale/rotation: children's pixel data gets transformed via QImage.transformed(), but Krita renders with its own interpolation. Small sub-pixel differences possible.
- `projectionPixelData` on a child does NOT include parent group's mask — we compensate by applying acc_transform manually.

## Layer filtering
`is_exportable()` skips: invisible nodes, `__pivot` layers, `filterlayer` type, **all** `*.endswith("mask")` types. Pivot layers hidden from export but respected for group pivot calculation.

## Color space
`_rgba_u8_source()`: if doc not RGBA U8, clones and converts to sRGB RGBA U8. Clone closed in `finally`.

## Packing
MaxRects BSSF heuristic. Grows smaller atlas dimension until fits. Max 16384px. Supports power-of-two, configurable spacing.

## Deduplication
Identical sprites share a frame key. Key computed from pixel bytes + opacity + dimensions + transform. Duplicates get `#2`, `#3` suffix.

## UI exclusions
`excluded_top_level` frozenset of node uid strings. Unchecked items skipped by `SceneBuilder.build()`.

## Quick debug checklist
- Transform masks: check `_visual_bounds`, `_node_mask_transform`, `_document_position`, `_register_sprite` acc_transform + to_canvas.
- Wrong positions: `mapRect` vs `map` — use `mapRect` for axis-aligned bounding box positions.
- Missing sprites: `is_exportable` filtering, `bounds.isEmpty()` check.
- Double transform: ensure projectionPixelData doesn't include ancestor mask (it doesn't).
- Sub-pixel shifts: Qt `QImage.transformed` vs Krita rendering, filter mode mismatch.
