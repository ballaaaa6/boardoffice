# HumanBall Popup System Integration Guide

This guide covers the production integration step **after** a HumanBall popup
has been drawn and visually approved. It is separate from the pixel-art
construction guide:

- [`HUMANBALL_POPUP_CREATION_GUIDE.md`](HUMANBALL_POPUP_CREATION_GUIDE.md)
  covers how to draw and review the artwork.
- This guide covers how to register the artwork, rebuild the zero-API browser
  bundle, validate it, and review it at `http://127.0.0.1:8000/`.

The project root is the source of truth. Files under `WEB/` are generated
runtime outputs and must be rebuilt from the canonical registries.

## 1. Integration pipeline

Every production popup follows this chain:

```text
approved 18x18 PNG
    -> CHARACTER/ASSETS/asset_registry.json
    -> CHARACTER/EFFECTS/*humanball*.json
    -> CHARACTER/EMPLOYEES/employee_metadata.json
    -> WEB/runtime_assets/ and WEB/*/bootstrap.json
    -> Python tests + Browser tests + parity trace
    -> live review on port 8000
```

Do not make a popup visible by editing JavaScript, HTML, or a generated bundle
only. The runtime catalog is derived from the canonical registries.

## 2. Runtime contract to preserve

The current HumanBall implementation uses one static native PNG for each
popup. The animation is movement of that PNG through shared offsets; it is not
a separate image sheet for every logical frame.

The locked presentation contract is:

| Field | Required value |
| --- | ---: |
| Native cell | `18x18` pixels |
| Logical frames | `12` |
| Visible frames | `10` |
| Hidden frames | `2` |
| Frame duration | `240ms` |
| Anchor | `character_work_origin` |
| Layer | `work_popup_overlay` |

The browser and Python presentation paths treat the first ten offsets as
visible and hold the first hidden state after that. They must not wrap a long
popup back to frame `0`. Do not add `% total_frames` logic or change the
timing contract when adding a normal popup.

The automatic popup pool currently contains:

- six canonical items from `CHARACTER/EFFECTS/humanball_v1.json`;
- 38 office items from `CHARACTER/EFFECTS/office_humanball_v1.json`;
- 44 items total in the default `humanball` shuffle bag.

## 3. Choose the correct registry

Use exactly one registry for a new item.

### Canonical HumanBall

Use `CHARACTER/EFFECTS/humanball_v1.json` only when the item is intended to
belong to the locked canonical six-item set. That registry is currently fixed
at six entries by its schema and runtime loader. Adding a seventh canonical
item is a contract change, not a normal asset-only addition.

### Office HumanBall

Use `CHARACTER/EFFECTS/office_humanball_v1.json` for a normal new office popup.
Its IDs use the stable office namespace:

```text
humanball_id = office.<category_slug>.<item_slug>
asset_id     = humanball.office.<category_slug>.<item_slug>
```

For example:

```text
humanball_id = office.stationery.stapler
asset_id     = humanball.office.stationery.stapler
```

Use lowercase letters, digits and underscores for category and item slugs.
Once an ID is published, do not rename it to fix a label or filename; an ID
change creates a new catalog entry and changes the deterministic catalog
profile.

## 4. Add the approved PNG

Keep the editable Aseprite source, native PNG and review preview in
`LOCAL_REVIEW/` until visual approval. Only the approved native PNG enters the
runtime asset tree. Never package a GIF, sprite sheet or labeled review sheet
as a runtime HumanBall asset.

For an office item, copy the PNG to:

```text
CHARACTER/ASSETS/effects/humanball/office/<category_slug>/<item_slug>.png
```

For a canonical item, use:

```text
CHARACTER/ASSETS/effects/humanball/<item_slug>.png
```

Run this basic check from the project root before registering the file:

```powershell
$popup = 'CHARACTER/ASSETS/effects/humanball/office/stationery/stapler.png'
python -c "from PIL import Image; import sys; p=sys.argv[1]; im=Image.open(p); alpha=set(im.getchannel('A').getdata()); assert im.size == (18,18), im.size; assert im.mode == 'RGBA', im.mode; assert alpha <= {0,255}, sorted(alpha); print('PNG OK:', p)" $popup
python -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" $popup
```

The hash printed by the second command is the value stored in the asset
registry. Do not type a guessed hash.

## 5. Register the asset identity

Add one object to the `assets` array in
`CHARACTER/ASSETS/asset_registry.json`. An office record follows this shape:

```json
{
  "asset_id": "humanball.office.stationery.stapler",
  "domain": "effect",
  "kind": "humanball_office_popup",
  "humanball_id": "office.stationery.stapler",
  "category_id": "02_stationery",
  "item_id": "stapler",
  "path": "effects/humanball/office/stationery/stapler.png",
  "sha256": "<64 lowercase hex characters>",
  "dimensions": [18, 18],
  "mode": "RGBA",
  "provenance": {
    "source": "<approved source package>",
    "source_type": "<approval or selection record>"
  }
}
```

Keep these identity rules aligned:

```text
asset.asset_id       == popup.asset_id
asset.humanball_id   == popup.humanball_id
asset.path           -> an existing file under CHARACTER/ASSETS/
asset.sha256         == SHA-256 of that exact file
asset.dimensions     == [18, 18]
asset.mode           == "RGBA"
```

Update `asset_count` and `effect_asset_count` in the unified asset registry
when adding an asset. Do not alter the hashes of existing assets.

## 6. Register the popup in the logical pool

For an office popup, update
`CHARACTER/EFFECTS/office_humanball_v1.json` in all three places:

1. Add the new ID once to `office_humanball_order`.
2. Add a record with the same key to `office_humanballs`.
3. Add the item slug to the correct category's `item_ids` list.

The record must have this shape:

```json
"office.stationery.stapler": {
  "humanball_id": "office.stationery.stapler",
  "asset_id": "humanball.office.stationery.stapler",
  "category_id": "02_stationery",
  "item_id": "stapler",
  "label": "Stapler",
  "source_index": 38
}
```

The `source_index` must be unique within the selected pool. For the current
38-item office contract, valid indices are `0..37`; index `38` is valid only
after the pool contract has been deliberately expanded as described below.

Leave the shared `animation`, `direction_rules`, motion offsets, `render` and
`style_contract` blocks unchanged for an ordinary new popup. The new item uses
the existing NW/SE offsets and the derived SW/NE relation.

## 7. Expanding a fixed pool safely

The current registry versions intentionally lock their sizes. Adding the
39th office item, or a seventh canonical item, cannot be done by appending one
JSON record. The contract must be changed as one coordinated task.

For the 39th office item, review and update together:

```text
CHARACTER/EFFECTS/office_humanball_v1.json
SCHEMA/CHARACTER/office_humanball_registry.schema.json
CHARACTER/RUNTIME/office_humanball_registry.py
RUNTIME/visual_selection_core.py
CHARACTER/RUNTIME/character_system.py       # count wording/docstring
TESTS/test_office_humanball_pool.py
TESTS/test_visual_selection.py
```

The expected changes are:

- office count/order/record bounds: `38 -> 39`;
- office `source_index` maximum: `37 -> 38`;
- office loader `COUNT`: `38 -> 39`;
- default mixed popup size: `44 -> 45` (`6 + 39`);
- exact test expectations and bag-boundary assertions.

`RUNTIME/browser_bundle_contract.py` currently checks minimum catalog sizes,
but it must still be reviewed when the contract changes. The generated bundle
revision and visual catalog profile will change automatically. Existing saved
bag state or replay data carrying the old catalog profile must be migrated or
reset; do not edit the profile by hand.

If the new item fits an existing office pool without changing the pool size,
follow the ordinary registration flow. If the pool has reached its locked
capacity, stop and treat expansion as a separate implementation task.

## 8. Regenerate generated metadata and browser outputs

After the canonical PNG, asset registry and logical registry are correct, run
these commands from the project root:

```powershell
python TOOLS/generate_employee_metadata.py
python TOOLS/build_runtime_simulation_bundle.py --floor-id floor02
python TOOLS/build_all_floors.py
```

These commands update the generated data used by the zero-API viewer,
including:

- `CHARACTER/EMPLOYEES/employee_metadata.json`;
- `WEB/runtime_simulation_bootstrap.json`;
- `WEB/floors/*/bootstrap.json`;
- `WEB/floors/*/manifest.json` and `WEB/floors/index.json`;
- `WEB/runtime_render_manifest.json`;
- shared files under `WEB/runtime_assets/`.

Do not edit any of those generated files manually. If a generated file does
not contain the new popup after the build, fix the canonical registry or asset
record and rebuild; do not patch the generated output.

## 9. Required validation

Run the focused HumanBall and selection tests first:

```powershell
python -m pytest -q `
  TESTS/test_office_humanball_pool.py `
  TESTS/test_humanball_popup_channel.py `
  TESTS/test_humanball_floor_integration.py `
  TESTS/test_runtime_presentation_renderer.py `
  TESTS/test_visual_selection.py `
  TESTS/test_actor_simulation_core.py
```

Then run the browser and parity checks:

```powershell
node --test TESTS/browser_runtime_test.mjs
python -m pytest -q TESTS/test_browser_bundle_contract.py TESTS/test_browser_parity_trace.py
```

Finally run the full project suite:

```powershell
python -m pytest -q
git diff --check
```

A new popup must not introduce a new failure. As of 2026-09-10, the recorded
baseline has one unrelated pre-existing Floor 06 WorkSeat expectation failure;
compare future results with `HANDOFF.md` and investigate any additional
failure rather than accepting it as a baseline.

## 10. Live review on port 8000

Inspect listeners before starting anything. Reuse the healthy project server
if it is already running:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'TOOLS[\\/]static_web_server\.py' } |
  Select-Object ProcessId, CommandLine
```

If there is no healthy project listener, start the static viewer with its
fixed project port:

```powershell
python TOOLS/static_web_server.py
```

Review the popup at:

```text
http://127.0.0.1:8000/?reload=<cache-buster>
```

Confirm all of the following in the live page:

- the new popup appears during normal work;
- NW, SE, SW and NE placement is correct;
- the icon remains sharp at native pixel scale;
- the popup disappears after its one-shot timeline;
- it does not reappear as frame `0` after the hidden frames;
- repeated events do not create two active bindings for one actor;
- the browser Network panel shows no `/api/*` request.

Port `8765` is retired for this viewer. Do not start a second review server or
use an automatic fallback port.

## 11. Troubleshooting

| Symptom | Likely cause | Correct action |
| --- | --- | --- |
| `Unknown HumanBall` | Registry order and record keys disagree | Make the ID appear exactly once in both places |
| `unresolved asset` | Asset ID, path or registry record is missing | Fix `asset_registry.json`, then rebuild |
| Registry count mismatch | A fixed-size pool was extended partially | Update the schema, loader, default pool and tests together |
| New icon absent from browser | Stale generated manifest or bundle | Regenerate metadata and all browser outputs |
| `catalog profile mismatch` | Old state/replay uses the previous catalog | Reset or migrate the state; do not edit the profile |
| Icon reappears after finishing | Timeline was changed to wrap or loop | Preserve ten visible frames and the one-shot clamp |
| Two identical popups at once | Two admissions or stale active binding | Check admission/active-binding tests before changing selection |

## 12. Definition of done

The integration is complete only when every item below is true:

- [ ] Visual artwork was explicitly approved.
- [ ] Native PNG is `18x18` RGBA with binary alpha and a verified SHA-256.
- [ ] `humanball_id` and `asset_id` are unique, stable and cross-referenced.
- [ ] Asset registry counts and record are correct.
- [ ] The correct HumanBall registry order, record and category are correct.
- [ ] Fixed pool counts were updated coherently if the pool was expanded.
- [ ] Employee metadata and all browser outputs were regenerated by builders.
- [ ] Focused Python tests, browser tests, parity checks and full pytest pass
      without a new failure.
- [ ] Live review passed at `http://127.0.0.1:8000/` with no `/api/*` request.
- [ ] Generated files were not manually patched.
- [ ] The change is recorded in Git with the validation result.
