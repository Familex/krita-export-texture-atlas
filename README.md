# SpritesExporter

A Krita plugin that exports all layer groups as a packed texture atlas and a JSON scene description that preserves the layer hierarchy.

JSON follows [json_texture_atlas_schema.json](./json_texture_atlas_schema.json) schema.

> [!NOTE]
> This plugin requires Krita version **6.0** or later.

## Additional features

- Custom pivot points via child layers named "__pivot" containing one pixel at the object pivot point.
- Identical sprites are deduplicated.
- Layer and group opacity are baked into the exported pixels.
- Documents in any color space are converted to 8-bit RGBA on the fly (the original document is never modified).
- Layers to be skipped: invisible, with no explorable content, named "__pivot", filter layers.

## Installation

1. Go to `Tools > Scripts > Import Python Plugin from Web`, insert the URL to this repo, and restart Krita.
1. Check if the plugin is enabled in `Settings > Configure Krita > Python Plugin Manager`.
1. Plugin controls will be available in `Tools > Scripts > Export as Texture Atlas`.

## Acknowledgments

- The plugin is based on [https://github.com/mimvoid/spritesExporter](https://github.com/mimvoid/spritesExporter), which was based on [https://github.com/Falano/kritaSpritesheetManager](https://github.com/Falano/kritaSpritesheetManager).
