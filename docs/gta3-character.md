# GTA III rigid character heads

Scout now supports a scoped GTA III character workflow. It imports a local,
classic rigid DFF with a named `Shead` atomic and one diffuse atlas, creates an
editable Blender scene, and compares the same head from fixed front, profile and
rear cameras. It does not generate anatomy or assume that a render matches a
reference. Inspect the supplied model, its UVs and reference screenshots first.

## Prepare and inspect

Use the installed Blender executable and your existing DragonFF checkout:

```sh
asset-catalog-character scene --dff /local/player.dff --texture /local/player.bmp \
  --out output/claude-original --blender /path/to/blender --dragonff /path/to/DragonFF
```

`head.json` records the original source hash, named frame, head geometry,
individual vertex indices, local positions, UVs and triangles. `character.blend`
contains all original rigid meshes, the head selected, other meshes locked for
selection, original texture and three fixed orthographic cameras. `scene-report.json`
records render hashes, Blender and DragonFF parser versions. Render axes are
explicitly the classic III head's local X height, Y front and Z lateral. These
are neutral Blender bind-pose inspections, not native animation or gameplay
validation. The source is read only and output must be a fresh path. An optional
`--head-texture /local/head.bmp` binds a separate diffuse only to the head.

Scout's static renderer supports the rigid model; skinned/shared head geometry,
multiple morph targets, native geometry and multiple source texture names are
rejected. The single atlas mapping is explicit and does not infer a TXD binding.

## Edit and export

Edit only the head's vertex positions in Blender. The `native_vertex` attribute
preserves the source vertex index for every UV seam. Keep duplicate seam vertices
coincident. Do not apply modifiers, change topology/UVs, move frames or touch the
body. Export the changed positions:

```sh
DRAGONFF_PATH=/path/to/DragonFF blender -b --factory-startup output/claude-original/character.blend \
  --python scripts/export_character_edits.py -- --out output/claude-edits.json
asset-catalog-character edit --dff /local/player.dff --edits output/claude-edits.json \
  --out output/player-refined.dff
```

The exporter checks the source hash, body vertices, UVs, vertex identities,
topology, object presence and prepared frame transforms. The patcher accepts only
the inspected source, rejects non-finite, repeated or out-of-range edits, limits
movement to 5 cm by default, and rejects flipped/collapsed triangles. It rotates
authored split normals with their local triangle fans and recalculates head
bounds. Every byte outside the head's sphere, positions and normals stays exact:
body, rig, UVs, triangles, materials and extensions are never reserialized. A
zero-edit roundtrip returns identical source bytes. Texture changes are a separate
art task and should use the native UV coordinates, not guessed feature positions.

Run `scene` on the patched DFF into a new directory and compare all three views
against the original and references before installation. Use `asset-catalog-character compare --before ORIGINAL/scene-report.json
--after EDITED/scene-report.json --references references.json --out output/comparison`
for a provenance-checked front/profile/rear contact sheet. The optional reference
JSON maps each of `front`, `profile`, `rear` to a local `path` and integer
`crop: [left, top, right, bottom]`. Changed render evidence is rejected.

A separate target-game
capture is still required to assess animation, lighting and the final appearance.

## GTA III source catalogues

```sh
asset-catalog-sources --game iii --game-root /local/GTAIII --out output/iii-source
asset-catalog --db output/iii.sqlite build --root output/iii-source --game iii
```

The adapter reads `data/gta3.dat`, IDE definitions, external IMG v1 DIR records,
IMG v2 and loose PC TXD names. `--game vc` uses `data/gta_vc.dat`; the existing
SA default stays compatible. Review `source-report.json` failures. An out-of-bounds
archive or invalid dictionary stays a reported failure; a successful catalogue
is not proof of complete asset coverage. Mod Loader priority and texture-only
player bitmap overrides remain explicit, local inputs. The existing SA shared
annotation pack is not evidence for a user-supplied III character.

Validation uses synthetic game-free parser/edit tests and separately documented
local Blender/native model checks. Do not publish any local model, texture,
reference screenshot, .blend file, catalogue or private review packet.
