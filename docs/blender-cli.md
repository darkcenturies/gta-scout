# Render local assets with Blender CLI

For assembled placements and exported material parity, also use the explicit
[scene audit](scene-audit.md). A preview alone does not validate runtime transforms.

This bridge prepares **static DFF** previews. It does not replace your scene-building scripts or import a whole map. Install Blender separately (tested with the local Blender version in validation.md), Node.js 20+ for TXD extraction, and DragonFF separately:

```sh
npm ci --ignore-scripts
git clone https://github.com/Parik27/DragonFF.git references/DragonFF
git -C references/DragonFF checkout 5a7c2f18d6ff9ac4e3424d552cfe404c931d039d
```

`references/` is ignored and not bundled. DragonFF is GPL-3.0-or-later; see THIRD_PARTY_NOTICES.md. You may instead set `DRAGONFF_PATH` to your existing checkout containing `gtaLib/dff.py`. Future upstream changes may affect the parser; record its version/hash in your local build evidence. The renderer hashes the parser used.

Starting with the README's local SA source snapshot, replace model ID 1714 with a desired ID from your own search results:

```sh
node scripts/prepare-asset-catalog-views.mjs '/path/to/GTA San Andreas' \
  output/chair-batch --catalog-root output/my-sa-source 1714
blender -b -t 2 --python scripts/render-asset-catalog-views.py -- \
  --input output/chair-batch/input.json --output output/chair-batch/render \
  --size 384 --samples 12
```

On macOS the executable may be `/Applications/Blender.app/Contents/MacOS/Blender`. On Windows quote the full installed Blender executable path. No hardcoded executable is required; chunk runner defaults to `blender` on PATH and accepts `--blender`.

Extraction is read-only on the game and writes local DFF/TXD/PNG cache files only to the chosen output. These files are ignored and must not be committed. `--archive FILE` supplies extra IMG sources; ambiguous sources fail instead of silently using an arbitrary duplicate. The adapter is SA-oriented and does not resolve every parent dictionary or mod loader configuration.

The renderer emits four azimuths, a manifest, source and recipe digests, cache status, missing-texture status, and low-signal diagnostics. It preserves static frame transforms and rejects skinned meshes. A magenta surface means missing texture, not a material description. A render failure is not evidence that an asset is irrelevant.

Convert the ready manifest to local overrides using the tested helper:

```sh
python - <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from asset_catalog_run_chunks import evidence_overrides
root = Path('output/chair-batch')
report = json.loads((root/'render/manifest.json').read_text())
overrides = evidence_overrides(report)
(root/'keys.json').write_text(json.dumps(list(overrides)))
(root/'overrides.json').write_text(json.dumps(overrides))
PY
asset-catalog-visual --db output/my-sa.sqlite prepare \
  --keys output/chair-batch/keys.json --overrides output/chair-batch/overrides.json \
  --out output/chair-batch/packets
```

Inspect the packet images using your agent's image viewer and import actual reviews. Renders alone do not populate semantic descriptions.

For multiple chunks, put an `input.json` in each chunk directory and run `scripts/asset_catalog_run_chunks.py --help`. Each chunk writes an append-only journal and revalidates cache evidence on resume. The default 2 GiB free-space reserve prevents a new batch from starting under that threshold; it is not a full-corpus storage estimate. Keep expensive rendering bounded while other Blender jobs run.

Advanced diagnostics: `scripts/asset_catalog_uv_context.py --help` overlays actual DFF material UVs on a texture. It reports geometric references, not a proven runtime dictionary binding. `scripts/prepare-asset-catalog-textures.mjs` and `asset_catalog_transfer_pixels.py` consume explicit audit manifests; the original private global-audit generator/data are not bundled. Their full source-to-audit automation remains roadmap work.
