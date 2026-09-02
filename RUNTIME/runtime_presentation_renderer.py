from __future__ import annotations

"""Consume the Central runtime-presentation snapshot in a real image renderer.

``CentralGameCore`` deliberately remains renderer-agnostic: it resolves actor,
speech and conversation state into a JSON-safe presentation snapshot.  This
module is the thin image-side consumer of that snapshot.  It keeps the
composition rules in one place for the live participant renderer and for the
review-only visual QA tools:

* work-seat rows are sent through the existing WorkSeat compositor;
* walking/emotion rows are depth-masked and painted in Central's order;
* dialogue bubbles are painted last in the scheduler's turn order, with no
  collision displacement or connector;
* character, VFX, HumanBall and PC frame indices are read per assignment.

No simulation snapshot is mutated by this renderer.
"""

import copy
from pathlib import Path
from typing import Any, TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from RUNTIME.central_core import CentralGameCore


class RuntimePresentationRenderError(ValueError):
    """Raised when a runtime presentation row cannot be rendered."""


class RuntimePresentationRenderer:
    """Render one read-only ``gds.runtime_presentation_snapshot.v1`` sample."""

    CHARACTER_ANCHOR_PX = (16, 31)

    def __init__(self, core: "CentralGameCore"):
        self.core = core
        self._sprite_cache: dict[tuple[str, str, str | None, str | None], Any] = {}
        # Live review samples usually reuse the same seated/PC frame for
        # several ticks. Keep the expensive world + WorkSeat composition
        # around and let the overlay pass paint onto a fresh copy.
        self._base_floor_cache: dict[tuple[Any, ...], Image.Image] = {}
        self._base_floor_cache_order: list[tuple[Any, ...]] = []
        self._base_floor_cache_limit = 12

    @staticmethod
    def _as_direction(row: dict[str, Any]) -> str | None:
        direction = row.get("direction")
        if direction is None:
            return None
        return str(direction).upper()

    @staticmethod
    def _event_action(action: str | None) -> bool:
        return action in {"sad", "happy"}

    def _action_result(self, row: dict[str, Any]):
        character_id = row.get("character_id")
        action = row.get("action")
        if not isinstance(character_id, str) or not isinstance(action, str):
            raise RuntimePresentationRenderError(
                f"{row.get('employee_id', '<actor>')}: visible row lacks character/action"
            )
        if self._event_action(action):
            # Emotion actions are directionless in the canonical character
            # registry even though the overlay row may retain the actor's
            # previous facing for sorting/debugging.
            direction = None
            subaction = None
        else:
            direction = self._as_direction(row)
            # The runtime vocabulary labels walking/standing rows with an
            # ``idle`` subaction for state/debug purposes, but the character
            # action registry exposes those groups without subactions.  Pass
            # ``None`` to the action resolver for those two groups.
            if action in {"idle", "move"}:
                subaction = None
            else:
                subaction = row.get("subaction")
                if subaction is not None:
                    subaction = str(subaction)
        key = (character_id, action, direction, subaction)
        result = self._sprite_cache.get(key)
        if result is None:
            try:
                result = self.core.characters.render(
                    character_id,
                    action,
                    direction,
                    subaction,
                )
            except Exception as exc:  # renderer boundary gives one stable error type
                raise RuntimePresentationRenderError(
                    f"{row.get('employee_id', '<actor>')}: cannot render "
                    f"{character_id}/{action}/{direction}/{subaction}"
                ) from exc
            if not getattr(result, "frames", None):
                raise RuntimePresentationRenderError(
                    f"{row.get('employee_id', '<actor>')}: action produced no frames"
                )
            self._sprite_cache[key] = result
        return result

    def _sprite(self, row: dict[str, Any]) -> Image.Image:
        result = self._action_result(row)
        frame_index = int(row.get("frame_index", row.get("character_frame_index", 0)))
        if frame_index < 0:
            raise RuntimePresentationRenderError(
                f"{row.get('employee_id', '<actor>')}: frame index must be >= 0"
            )
        frame = result.frames[frame_index % len(result.frames)]
        return frame if frame.mode == "RGBA" else frame.convert("RGBA")

    def _work_assignment(self, row: dict[str, Any]) -> dict[str, Any]:
        assignment: dict[str, Any] = {
            "workstation_id": row["workstation_id"],
            "character_id": row["character_id"],
            "subaction": row.get("subaction") or "normal_work",
            # WorkSeatCore accepts these per-assignment indices so every
            # actor retains its independent presentation clock.
            "character_frame_index": int(
                row.get("frame_index", row.get("character_frame_index", 0))
            ),
            "pc_frame_index": row.get("pc_frame_index"),
        }
        channels = row.get("channels")
        if isinstance(channels, dict) and assignment["subaction"] == "normal_work":
            vfx = channels.get("vfx")
            if isinstance(vfx, dict) and vfx.get("asset_id"):
                assignment["effect_id"] = str(vfx["asset_id"])
                assignment["effect_frame_index"] = int(
                    vfx.get("effect_frame_index", 0)
                )
            humanball = channels.get("humanball")
            if isinstance(humanball, dict) and humanball.get("asset_id"):
                assignment["humanball_id"] = str(humanball["asset_id"])
                assignment["humanball_frame_index"] = int(
                    humanball.get("humanball_frame_index", 0)
                )
        return assignment

    def _base_floor(self, floor_id: str, actors: dict[str, dict[str, Any]]) -> Image.Image:
        assignments = [
            self._work_assignment(row)
            for row in actors.values()
            if row.get("visible")
            and row.get("render_owner") == "work_seat"
            and row.get("action") == "work"
        ]
        assignment_key = tuple(
            (
                str(assignment.get("workstation_id")),
                str(assignment.get("character_id")),
                str(assignment.get("subaction") or "normal_work"),
                int(assignment.get("character_frame_index", 0)),
                (
                    None
                    if assignment.get("pc_frame_index") is None
                    else int(assignment["pc_frame_index"])
                ),
                assignment.get("effect_id"),
                int(assignment.get("effect_frame_index", 0)),
                assignment.get("humanball_id"),
                int(assignment.get("humanball_frame_index", 0)),
            )
            for assignment in sorted(
                assignments,
                key=lambda item: str(item.get("workstation_id")),
            )
        )
        cache_key = (str(floor_id), assignment_key)
        cached = self._base_floor_cache.get(cache_key)
        if cached is not None:
            return cached.copy()
        has_channel = any(
            "effect_id" in assignment or "humanball_id" in assignment
            for assignment in assignments
        )
        try:
            if has_channel:
                canvas = self.core.render_floor_with_work_effects(
                    floor_id,
                    assignments,
                    frame_index=0,
                    character_frame_index=0,
                    effect_frame_index=0,
                    humanball_frame_index=0,
                ).convert("RGBA")
            else:
                canvas = self.core.render_floor_with_work(
                    floor_id,
                    assignments,
                    frame_index=0,
                    character_frame_index=0,
                ).convert("RGBA")
        except Exception as exc:
            raise RuntimePresentationRenderError(
                f"{floor_id}: cannot compose work-seat presentation"
            ) from exc
        self._base_floor_cache[cache_key] = canvas.copy()
        self._base_floor_cache_order.append(cache_key)
        while len(self._base_floor_cache_order) > self._base_floor_cache_limit:
            evicted = self._base_floor_cache_order.pop(0)
            self._base_floor_cache.pop(evicted, None)
        return canvas

    def _paint_walking_actor(
        self,
        canvas: Image.Image,
        floor_id: str,
        row: dict[str, Any],
    ) -> None:
        if not row.get("visible") or row.get("render_owner") != "walking_depth":
            return
        ground = row.get("ground_xy")
        if not isinstance(ground, (list, tuple)) or len(ground) != 2:
            return
        sprite = self._sprite(row)
        alpha = max(0.0, min(1.0, float(row.get("visibility_alpha", 1.0))))
        if alpha < 1.0:
            sprite = sprite.copy()
            channel = sprite.getchannel("A").point(
                lambda value: int(round(value * alpha))
            )
            sprite.putalpha(channel)
        try:
            sprite = self.core.walking_depth._mask_character_by_world_occluders(
                floor_id,
                sprite,
                (float(ground[0]), float(ground[1])),
                ground_anchor_px=self.CHARACTER_ANCHOR_PX,
            )
        except Exception as exc:
            raise RuntimePresentationRenderError(
                f"{row.get('employee_id', '<actor>')}: walking-depth mask failed"
            ) from exc
        x = int(round(float(ground[0]) - self.CHARACTER_ANCHOR_PX[0]))
        y = int(round(float(ground[1]) - self.CHARACTER_ANCHOR_PX[1]))
        canvas.alpha_composite(sprite, (x, y))

    def _bubble_actor_top_left(self, row: dict[str, Any]) -> tuple[int, int]:
        ground = row.get("ground_xy")
        if isinstance(ground, (list, tuple)) and len(ground) == 2:
            return (
                int(round(float(ground[0]) - self.CHARACTER_ANCHOR_PX[0])),
                int(round(float(ground[1]) - self.CHARACTER_ANCHOR_PX[1])),
            )
        if row.get("render_owner") != "work_seat":
            raise RuntimePresentationRenderError(
                f"{row.get('employee_id', '<actor>')}: seated bubble has no seat owner"
            )
        employee_id = row.get("employee_id")
        floor_id = row.get("floor_id")
        workstation_id = row.get("workstation_id")
        if not all(isinstance(value, str) for value in (employee_id, floor_id, workstation_id)):
            raise RuntimePresentationRenderError("seated bubble row lacks assignment identity")
        try:
            seat = self.core.work_seats.resolve_workstation_seat(floor_id, workstation_id)
            character = self.core.characters.render(
                row["character_id"],
                "work",
                seat["direction"],
                row.get("subaction") or "normal_work",
            )
            chair = self.core.world.load_asset(seat["chair_asset_id"]).convert("RGBA")
            offset = self.core.work_seats.resolve_world_offset(
                seat["direction"],
                chair_size=chair.size,
                human_size=character.frames[0].size,
            )
        except Exception as exc:
            raise RuntimePresentationRenderError(
                f"{employee_id}: cannot resolve seated bubble anchor"
            ) from exc
        return (
            int(seat["chair_x_px"]) + int(offset[0]),
            int(seat["chair_y_px"]) + int(offset[1]),
        )

    def _paint_bubble(self, canvas: Image.Image, row: dict[str, Any]) -> None:
        if not row.get("dialogue_visible"):
            return
        employee_id = row.get("employee_id")
        if not isinstance(employee_id, str):
            raise RuntimePresentationRenderError("dialogue row lacks employee_id")
        text = row.get("dialogue_text")
        if not isinstance(text, str) or not text:
            raise RuntimePresentationRenderError(
                f"{employee_id}: visible dialogue row lacks text"
            )
        action_result = self._action_result(row)
        frame_index = int(row.get("frame_index", row.get("character_frame_index", 0)))
        frame_id = action_result.frame_ids[frame_index % len(action_result.frame_ids)]
        try:
            bubble = self.core.render_employee_dialogue_bubble(
                employee_id,
                frame_id,
                text,
                actor_top_left=self._bubble_actor_top_left(row),
                locale=str(row.get("dialogue_locale") or "en"),
                preferred_bubble_id=(
                    str(row.get("dialogue_bubble_id"))
                    if row.get("dialogue_bubble_id") else None
                ),
            )
        except Exception as exc:
            raise RuntimePresentationRenderError(
                f"{employee_id}: dialogue bubble render failed"
            ) from exc
        image = bubble.image.convert("RGBA")
        opacity = max(0.0, min(1.0, float(row.get("dialogue_opacity", 1.0))))
        if opacity < 1.0:
            image = image.copy()
            alpha = image.getchannel("A").point(
                lambda value: int(round(value * opacity))
            )
            image.putalpha(alpha)
        canvas.alpha_composite(
            image,
            (
                int(bubble.bubble_top_left[0]),
                int(bubble.bubble_top_left[1]),
            ),
        )

    def render_presentation(
        self,
        presentation: dict[str, Any],
        *,
        floor_id: str | None = None,
    ) -> Image.Image:
        """Render a validated presentation snapshot without mutating it."""
        if not isinstance(presentation, dict):
            raise RuntimePresentationRenderError("presentation must be an object")
        if presentation.get("schema") != "gds.runtime_presentation_snapshot.v1":
            raise RuntimePresentationRenderError("unsupported runtime presentation schema")
        actors_source = presentation.get("actors")
        if not isinstance(actors_source, dict):
            raise RuntimePresentationRenderError("presentation.actors must be an object")
        actors = {
            str(employee_id): copy.deepcopy(row)
            for employee_id, row in actors_source.items()
            if isinstance(row, dict)
            and (floor_id is None or row.get("floor_id") == str(floor_id))
        }
        floors = {str(row.get("floor_id")) for row in actors.values() if row.get("floor_id")}
        if floor_id is None:
            if len(floors) != 1:
                raise RuntimePresentationRenderError(
                    "render_presentation requires floor_id for a multi-floor snapshot"
                )
            floor_key = next(iter(floors))
        else:
            floor_key = str(floor_id)
        canvas = self._base_floor(floor_key, actors)
        order = presentation.get("paint_order", {}).get("characters", [])
        ordered_ids = [employee_id for employee_id in order if employee_id in actors]
        ordered_ids.extend(employee_id for employee_id in sorted(actors) if employee_id not in ordered_ids)
        for employee_id in ordered_ids:
            self._paint_walking_actor(canvas, floor_key, actors[employee_id])
        bubble_order = presentation.get("paint_order", {}).get("dialogue_bubbles", [])
        ordered_bubbles = [employee_id for employee_id in bubble_order if employee_id in actors]
        ordered_bubbles.extend(
            employee_id
            for employee_id in sorted(actors)
            if actors[employee_id].get("dialogue_visible") and employee_id not in ordered_bubbles
        )
        for employee_id in ordered_bubbles:
            self._paint_bubble(canvas, actors[employee_id])
        return canvas

    def render_runtime_snapshot(
        self,
        runtime_snapshot: dict[str, Any],
        *,
        at_ms: int | None = None,
        floor_id: str | None = None,
        validate: bool = True,
    ) -> tuple[Image.Image, dict[str, Any]]:
        """Resolve and render one runtime sample, returning image + snapshot."""
        presentation = self.core.resolve_runtime_presentation(
            runtime_snapshot,
            at_ms=at_ms,
            floor_id=floor_id,
            validate=validate,
        )
        return self.render_presentation(presentation, floor_id=floor_id), presentation


class RuntimePresentationLoop:
    """Small host-side loop that advances Central and renders one floor.

    ``CentralGameCore`` remains the owner of simulation state and timing.  The
    loop owns only the host's current immutable-by-convention snapshot copy;
    each ``tick`` replaces that copy with Central's returned snapshot and then
    consumes it through :class:`RuntimePresentationRenderer`.  This is the
    integration seam a game/update loop can call once per frame without
    accidentally sharing pose, speech or stamina clocks.  Review hosts that
    already own and serialize the lifecycle may opt out of the per-frame
    defensive copy with ``copy_runtime_snapshot_each_frame=False``.
    """

    def __init__(
        self,
        core: "CentralGameCore",
        *,
        runtime_snapshot: dict[str, Any] | None = None,
        floor_id: str | None = None,
        simulation_seed: str = "gds-speech-scheduler-v1",
        dialogue_locale: str = "en",
        dialogue_seed: str | int = "0",
        validate_runtime_each_frame: bool = True,
        copy_runtime_snapshot_each_frame: bool = True,
    ) -> None:
        self.core = core
        self.renderer = RuntimePresentationRenderer(core)
        if runtime_snapshot is None:
            runtime_snapshot = core.resolve_runtime_snapshot(
                floor_id,
                simulation_seed=simulation_seed,
            )
        try:
            self._runtime_snapshot = core.validate_runtime_snapshot(runtime_snapshot)
        except Exception as exc:
            raise RuntimePresentationRenderError(
                "runtime loop requires a valid composed runtime snapshot"
            ) from exc
        self.floor_id = str(floor_id) if floor_id is not None else None
        if self.floor_id is None:
            floors = {
                str(actor.get("assignment", {}).get("floor_id"))
                for actor in self._runtime_snapshot["actor_snapshot"].get("actors", {}).values()
                if actor.get("assignment", {}).get("floor_id") is not None
            }
            if len(floors) != 1:
                raise RuntimePresentationRenderError(
                    "runtime loop requires floor_id for a multi-floor snapshot"
                )
            self.floor_id = next(iter(floors))
        self.dialogue_locale = str(dialogue_locale)
        self.dialogue_seed = dialogue_seed
        self.validate_runtime_each_frame = bool(validate_runtime_each_frame)
        self.copy_runtime_snapshot_each_frame = bool(copy_runtime_snapshot_each_frame)

    @property
    def runtime_snapshot(self) -> dict[str, Any]:
        """Return the current snapshot; copy it by default for isolation."""
        if self.copy_runtime_snapshot_each_frame:
            return copy.deepcopy(self._runtime_snapshot)
        return self._runtime_snapshot

    def _frame(
        self,
        *,
        runtime_snapshot: dict[str, Any] | None = None,
        events: list[dict[str, Any]] | None = None,
        actor_events: list[dict[str, Any]] | None = None,
        speech_events: list[dict[str, Any]] | None = None,
        at_ms: int | None = None,
    ) -> dict[str, Any]:
        source = self._runtime_snapshot if runtime_snapshot is None else runtime_snapshot
        image, presentation = self.renderer.render_runtime_snapshot(
            source,
            at_ms=at_ms,
            floor_id=self.floor_id,
            validate=self.validate_runtime_each_frame,
        )
        return {
            "image": image,
            "presentation": presentation,
            "runtime_snapshot": (
                copy.deepcopy(source)
                if self.copy_runtime_snapshot_each_frame else source
            ),
            "events": (
                copy.deepcopy(events or [])
                if self.copy_runtime_snapshot_each_frame else (events or [])
            ),
            "actor_events": (
                copy.deepcopy(actor_events or [])
                if self.copy_runtime_snapshot_each_frame else (actor_events or [])
            ),
            "speech_events": (
                copy.deepcopy(speech_events or [])
                if self.copy_runtime_snapshot_each_frame else (speech_events or [])
            ),
        }

    def render_current(self, *, at_ms: int | None = None) -> dict[str, Any]:
        """Render the current host snapshot without advancing simulation time."""
        return self._frame(at_ms=at_ms)

    def tick(
        self,
        elapsed_ms: int,
        *,
        actor_commands=None,
        speech_commands=None,
        at_ms: int | None = None,
    ) -> dict[str, Any]:
        """Advance Central once and return the newly rendered host frame.

        ``elapsed_ms`` is passed unchanged to Central, which validates the
        integer and advances both independent channels.  If ``at_ms`` is not
        supplied, the renderer samples the resulting runtime clocks.
        """
        try:
            advanced = self.core.advance_runtime_snapshot(
                self._runtime_snapshot,
                elapsed_ms,
                actor_commands=actor_commands,
                speech_commands=speech_commands,
                dialogue_locale=self.dialogue_locale,
                dialogue_seed=self.dialogue_seed,
                validate=self.validate_runtime_each_frame,
            )
            next_snapshot = (
                self.core.validate_runtime_snapshot(advanced)
                if self.validate_runtime_each_frame else advanced
            )
            frame = self._frame(
                runtime_snapshot=next_snapshot,
                events=advanced.get("events", []),
                actor_events=advanced.get("actor_events", []),
                speech_events=advanced.get("speech_events", []),
                at_ms=at_ms,
            )
        except Exception as exc:
            raise RuntimePresentationRenderError(
                "runtime loop could not advance the composed snapshot"
            ) from exc
        self._runtime_snapshot = next_snapshot
        return frame

    def advance_and_render(
        self,
        elapsed_ms: int,
        *,
        actor_commands=None,
        speech_commands=None,
        at_ms: int | None = None,
    ) -> dict[str, Any]:
        """Descriptive alias for hosts that prefer an explicit method name."""
        return self.tick(
            elapsed_ms,
            actor_commands=actor_commands,
            speech_commands=speech_commands,
            at_ms=at_ms,
        )
