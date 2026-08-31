# GDS Central Game Core — Handoff

**Updated:** 2026-08-31 (Asia/Bangkok)
**Project root:** D:\antigravity\board office
**Status:** PHASE8C_CLOSED__CEO_DEPTH_CLOSED__PHASE8D_CLOSED__PHASE8E_DIALOGUE_PRESENTATION_AND_CATALOG_IMPLEMENTED__AUTHOR_ACCEPTANCE_PENDING__BEHAVIOR_DEFERRED
**Next engineering task:** PHASE8E_CONVERSATION_COORDINATION_SLICE
**Latest author-directed task:** Replace ambiguous WorkSeat turn labels with direction-named subactions for partner-facing behavior. `turn_side_<direction>` names are now explicit in the action registry and work-pose contract, validated at runtime, exposed through Central, and included in interaction-slot metadata; pair walking/locking/selection behavior remains pending. No static character art or world asset changed.
**Active handoff:** this file only. ROADMAP.md is the single active milestone plan.

## Accepted foundation and current runtime

- The unpacked root is authoritative. 00_STARTING_POINT/ is immutable. Its TV Studio Story files remain source evidence; runtime never reads them.
- Phase 8B world/navigation is approved and frozen. Phase 8C portal lifecycle, the narrow CEO-desk render-depth correction and Phase 8D single-actor WorkSeat lifecycle are implemented, author-approved and closed.
- The accepted release remains releases/GDS_CENTRAL_GAME_CORE_v1.8.5.zip (738 entries; fresh-extract 179 passed; required audits passed; release_clean=true). No new release or phase closeout occurred in this task.
- Employee metadata contains 604 instances (302 Wave 1, 302 Wave 2), 219 initial workstation owners, 83 unassigned Wave 1 and 302 unassigned Wave 2 employees. Stable movement/stamina profiles and employee bridges exist; temporary absence retains ownership and never auto-fills vacancies.
- Dialogue presentation uses fixed complete fukidashi_base crops: BB1/BB2/BB3/BB4/BB6, excluding BB5. It measures locale text at 9 px, rejects overflow, and follows visible face-center X, actor movement and frame bob with the frame-top-minus-20 vertical policy. Thai/ASCII runs share a baseline. The caller supplies the character/employee ID, frame, current actor position and dialogue ID/locale; Central returns the bubble image and placement. Presentation does not choose when or what an actor says.
- Pair approach, live participant locks, automatic category/random selection, mutable actor snapshots, stamina reduction/recovery and home/return composition remain unimplemented. Directional turn semantics are now named directly: `SE` and `NW` use `turn_side_sw=V+→SW` / `turn_side_ne=V-→NE`; `SW` uses `turn_side_se=U+→SE` / `turn_side_nw=U-→NW`. Dashboard UI/persistence, queues, auto-staffing and additional needs systems remain outside scope.
- Existing pre-task working-tree changes were preserved. No static world/character art, placement, navigation, action frames or reference hashes were edited.

## Completed editable catalog integration

- The author explicitly requested importing the prepared reference phrases and being able to edit/add them later. This authorizes development content integration; it is not final visual/behavior acceptance or release promotion.
- CHARACTER/DIALOGUE/dialogue.csv is the active editable content source: the original 204 imported phrase IDs plus 800 author-approved expansion IDs, each in EN/TH, plus the preserved hello_world_test/en row = 2,009 rows / 1,005 total IDs.
- Keep each dialogue_id stable while editing text; locale and line_index distinguish localized turns. New project-authored IDs/categories can be added without changing code.
- Optional columns category, usage_scope, enabled, full_text, source_id and source_text extend the original five-column CSV format compatibly. text is the actual display draft; full_text preserves the full locale text and source_text preserves exact original English.
- Before the expansion, imported office rows enabled initially were TH 136 and EN 102; including the legacy test there were 239 enabled rows. The approved expansion added 1,600 office rows: 1,108 fit the current locale renderer and are enabled, while 492 overflow rows remain stored with `enabled=false`. The current catalog therefore has 1,347 enabled rows; these are measured content counts, not hard-coded limits.
- CHARACTER/DIALOGUE/reference_import.json records source files/hashes, the original reference catalog hash, initial categories and import policy. It does not regenerate or overwrite later CSV edits, and is not a live count manifest.
- Central and CharacterSystem expose list_dialogue_lines(locale, category, usage_scope, enabled_only) with JSON-safe metadata. Listing without filters includes disabled rows; callers choosing office content must explicitly filter scope/category/enabled status.
- reload_dialogue_content() parses and checks a candidate catalog, validates all enabled text against the current renderer, then replaces the in-memory catalog. Duplicate IDs, ambiguous CSV columns, malformed enabled flags, enabled markup/placeholders and overflow reject the reload while preserving the old in-memory data. The disk file is not rolled back.
- All dialogue-ID render paths (CharacterSystem frame, Central character and Central employee) reject disabled rows. resolve_dialogue_line() can still inspect them, or enforce require_enabled=True. No automatic conversation/random/stamina behavior was added.
- CHARACTER/DIALOGUE/README.md explains edits, additions, UTF-8/CSV quoting, defaults, API usage and limitations. CONTRACTS/central_contract.json and ROADMAP.md describe this authorized extension.
- The earlier research catalog stays at LOCAL_REVIEW/TV_STUDIO_DIALOGUE_REFERENCE_20260831/. Its README now points to the active catalog. Long talk/notification/UI tables were not bulk-imported as ambient speech. Earlier detailed source/font/anchor research remains in docs/history/TV_STUDIO_REFERENCE_STATE_SNAPSHOT_20260831.md, not another handoff.

## Review-only dialogue expansion draft

- LOCAL_REVIEW/DIALOGUE_CATALOG_DRAFT_20260831/dialogue_draft.csv was the review source for 16 office categories × 50 new EN/TH pairs = 800 pairs / 1,600 rows. Its IDs were appended to the active catalog after author approval; the review folder remains a source snapshot and is not loaded by Central.
- The draft had no normalized exact duplicates within itself or against the pre-import active catalog. Its bubble-fit audit is intentionally separate: 1,108/1,600 localized rows fit, 384/800 pairs fit in both locales, and 416 imported pairs need shortening or review before both locales can be enabled.
- README_TH.md and bubble_fit_report.json in that folder describe the review workflow and exact overflow IDs. The import report and pre-import backup are in LOCAL_REVIEW/DIALOGUE_CATALOG_IMPORT_20260831/. No runtime code, release package or source asset changed.
- For easier author review, `outputs/01a0571c-f344-7b90-927f-ddb3389a1d36/dialogue_catalog_review.xlsx` is a presentation-only export with three visible columns (`mode`, `EN`, `TH`), one row per phrase pair, frozen headers and filters. It contains the same 800 pairs and does not replace the CSV source.

## Verification

- TDD: initial 11 focused catalog cases failed for missing behavior; implementation made them pass. Two additional ambiguous-CSV cases were observed failing before adding the parser guards.
- Fresh dialogue-readiness verification on 2026-08-31: `python -B -m pytest -q TESTS/test_dialogue_bubble.py TESTS/test_dialogue_catalog.py -p no:cacheprovider` — 24 passed in 2.21s. Coverage includes actor movement/frame-bob placement, pixel-fit selection, Central/employee rendering, metadata filtering/JSON, legacy CSV compatibility, malformed content rejection, edit/add/reload, failed reload preserving the old catalog, disabled-row rejection and rendering every enabled office localization.
- Presentation artifact verification on 2026-08-31: rendered and visually inspected `outputs/01a0571c-f344-7b90-927f-ddb3389a1d36/RND_F_004_character_sheet.png` at 1,232×2,034 px; all 47 requested frame labels and the action mapping are present. No source/static asset was changed.
- Presentation artifact verification on 2026-08-31: rendered and visually inspected `outputs/01a0571c-f344-7b90-927f-ddb3389a1d36/RND_F_004_action_direction_sheet.png` at 1,600×1,775 px; rows are action/subaction groups, columns are NE/SE/SW/NW, and directionless event poses are separated below. No source/static asset was changed.
- Direction-named action sheet verification on 2026-08-31: rendered and visually inspected `outputs/01a0571c-f344-7b90-927f-ddb3389a1d36/RND_F_004_action_direction_sheet_v2.png` at 1,600×1,772 px; WorkSeat rows are split by target idle direction (`turn_side_sw`, `turn_side_ne`, `turn_side_se`, `turn_side_nw`) and blank cells show unsupported direction/subaction combinations. No source/static asset was changed.
- Work-turn naming implementation verification on 2026-08-31: `gds_standard_v1.json` and `work_pose_profiles.json` now use `turn_side_<direction>` names (`sw`, `ne`, `se`, `nw`) with `U+/U-/V+/V-` axis conventions; `WorkSeatCore.resolve_turn_side_mapping()` validates the direction name, axis and UV delta; `resolve_turn_side_for_target()` selects the named turn from a known partner-relative idle direction; Central exposes both resolvers; every derived interaction slot carries the mapping. Focused WorkSeat profile/lifecycle/runtime suite passes 36/36, with the full regression at 212/212. No walking, participant lock or automatic facing-coordination loop was implemented.
- Latest full root regression on 2026-08-31: `python -B -m pytest -q -p no:cacheprovider` — 212 passed. No navigation/world change occurred.
- Central integrity: PASS; all 26 schemas pass, 502 referenced payloads have zero mismatches, all 25 floor PNG/RGBA checks pass, 302 character identities and 219 workstations resolve. `release_clean=false` because the development tree contains 199 Python cache paths; no package was promoted.
- Import verification: the approved expansion import appended all 800 EN/TH pairs and preserved existing rows exactly; 2,009 active CSV rows, 1,005 IDs, 1,347 enabled rows and 492 fit-gated disabled rows. Actual validated reload returns 2,009 rows / 1,005 IDs / locales en, th. The import report is `LOCAL_REVIEW/DIALOGUE_CATALOG_IMPORT_20260831/import_report.json`.
- Draft expansion verification: build_draft.py generated 800 unique phrase pairs / 1,600 rows across 16 office categories; normalized duplicate and active-catalog collision checks passed. validate_draft.py checked every localized row against the real renderer and wrote the review-required fit report.
- Earlier independent integration review, before the expansion: no actionable findings; the then-current 239 enabled rows rendered safely. The fresh focused run above covers the current enabled office catalog. Technical checks do not constitute visual/Thai author acceptance or release approval.
- Final source/static audit: all 3,388 extracted source files, 168 character asset files and 329 world asset files match the pre-task byte counts and tree hashes. Scoped git diff --check passes; no task-owned long-running process remains because none was started.
- Task-specific review/verification evidence is under LOCAL_REVIEW/DIALOGUE_CATALOG_INTEGRATION_20260831/. The before-code snapshot distinguishes this work from existing uncommitted Phase 8E changes.
- No navigation/world changes were made, so the navigation audit family was not rerun. Central's existing static-world and payload checks remain green. No development server or canonical release was started.

## Next task and open gates

1. Edit `CHARACTER/DIALOGUE/dialogue.csv` directly for future content changes. The 492 fit-gated rows from the approved expansion remain available by stable `draft_*` ID; shorten and re-enable them only after a renderer fit/reload check.
2. When explicitly requested, implement standing-pair conversation coordination using employee IDs, atomic participant locks, existing movement/crowd routing, directional idle facing and stored recovery policy. Add coherent turn selection/cooldowns/deduplication in that behavior slice; seated-listener variants remain follow-ups.
3. Continue the mutable actor snapshot/stamina reducer, then home/return while retaining workstation ownership. Never make text rendering mutate stamina.
4. Visual/behavior author acceptance, final content review and Thai shaping review remain open. Pillow has no RAQM; pixel fit is not a guarantee of glyph coverage for newly added characters or Unity-equivalent Thai shaping.
5. Temporary TV bubble/font development inputs must be replaced with project-owned artwork/font policy before canonical release promotion. Content import approval does not close that gate or certify a release.

No technical blocker for catalog use or editing. Do not mark Phase 8E closed from the CSV, tests or generated reports alone.
