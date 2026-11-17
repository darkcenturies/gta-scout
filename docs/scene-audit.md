# Check the assembled scene

Discovery and a grounded bounding box do not establish correct placement.
Use `python scripts/asset_catalog_scene_audit.py --input contract.json --output report.json`
after exporting explicit measurements from the construction scene. The command
returns nonzero for failed measurements. It does not render or edit assets.

Schema 1 accepts `placements` and `surfaces` arrays. A placement has `id`,
`world_matrix` (row-major affine 4x4), `local_up`, `expected_world_up`, and
`evidence` explaining where the semantic up direction came from. Optional
`contacts` contain `local_point`, `support_world`, `support_normal`, and an
allowed signed `gap_range`. Sample the actual terrain under the footprint,
including corners and edges. Centre-only grounding misses unsupported edges.

A surface has `id`, `baseline` and `candidate`. Each includes
`texture_identity` (source/dictionary/name), decoded `texture_sha256`,
`geometry_surface` and `material_surface` (ambient/specular/diffuse triples).
Relocating identical texture pixels to a new dictionary is allowed. Matching
names alone is not pixel identity; matching pixels alone is not material parity.
See the synthetic fixture in `tests/test_asset_catalog_scene_audit.py`.

Obtain semantic up from reviewed original placements and visible features
(doors, roof, steps), not from the longest bounding-box axis. Some assets have
inverted local geometry and rely on their original placement rotation. A
180-degree rotation is not a negative scale. Check the target engine's frame
contract too: a hierarchy-preserving preview is not proof of a simple-atomic
runtime transform. Never globally discard DFF frames or flip all buildings.

The report hashes its input and explicitly leaves visual/runtime acceptance
false. The caller must validate that input against the actual exported files.
It cannot discover route connectivity, texture UV stretch, wall intersections,
fence placement, missing dependencies or visual resemblance. Inspect those in
the full city context, at ground level and from above, then in the native game.
Keep a correction record: observation, evidence, cause, change, measured result,
viewed result, runtime result and remaining limitations. Keep private assets
and paths out of public contributions.
