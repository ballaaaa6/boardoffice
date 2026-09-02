from __future__ import annotations

"""Project the Central presentation snapshot into a small render protocol.

This module deliberately contains no raster work.  It consumes the metadata
already resolved by :class:`CentralGameCore` and keeps the browser responsible
only for composing cached visual components.
"""

import copy
import json
from typing import Any, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from RUNTIME.central_core import CentralGameCore


class RuntimeRenderStateError(ValueError):
    """Raised when a lean render-state request cannot be projected."""


class RuntimeRenderStateProjector:
    """Build deterministic, image-free ``gds.runtime_render_state.v1`` data."""

    SCHEMA = "gds.runtime_render_state.v1"
    VERSION = "1.0.0"
    MANIFEST_REVISION = "floor02-component-manifest-v1"
    CHARACTER_ANCHOR_PX = [16, 31]
    _EVENT_KEYS = (
        "source",
        "type",
        "timestamp_ms",
        "event_index",
        "employee_id",
        "participants",
        "partner_id",
        "mode",
        "kind",
        "category",
        "speech_category",
        "request_id",
        "queue_position",
        "due_ms",
        "reason",
        "phase",
        "ground_xy",
        "progress_t",
        "emotion",
        "emotion_roll",
        "dialogue_lines",
    )
    _ACTOR_KEYS = (
        "employee_id",
        "floor_id",
        "visible",
        "visibility_alpha",
        "render_owner",
        "character_id",
        "presence",
        "activity",
        "stamina",
        "action",
        "resolved_action",
        "subaction",
        "resolved_subaction",
        "direction",
        "resolved_direction",
        "frame_index",
        "character_frame_index",
        "character_frame_count",
        "character_frame_ms",
        "ground_xy",
        "workstation_id",
        "assignment_order",
        "route_phase",
        "route_elapsed_ms",
        "route_duration_ms",
        "cumulative_distance_px",
        "pc_frame_index",
        "pc_frame_count",
        "pc_frame_ms",
        "speech_session_id",
        "speech_mode",
        "speech_category",
    )

    def __init__(self, core: "CentralGameCore") -> None:
        self.core = core

    @staticmethod
    def _json_safe(value: Any) -> Any:
        """Copy supported JSON values while rejecting renderer objects."""
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (list, tuple)):
            return [RuntimeRenderStateProjector._json_safe(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): RuntimeRenderStateProjector._json_safe(item)
                for key, item in value.items()
            }
        raise RuntimeRenderStateError(
            f"lean render state cannot contain {value.__class__.__name__}"
        )

    @classmethod
    def _compact_event(cls, event: Any) -> dict[str, Any]:
        if not isinstance(event, dict):
            return {"type": "unknown", "value": cls._json_safe(event)}
        return {
            key: cls._json_safe(event[key])
            for key in cls._EVENT_KEYS
            if key in event
        }

    def _frame_reference(self, row: dict[str, Any]) -> str | None:
        character_id = row.get("character_id")
        action = row.get("resolved_action")
        if not isinstance(character_id, str) or not isinstance(action, str):
            return None
        direction = row.get("resolved_direction")
        subaction = row.get("resolved_subaction")
        try:
            frame_ids = self.core.characters.resolve_frame_ids(
                character_id,
                action,
                direction,
                subaction,
            )
        except Exception as exc:
            raise RuntimeRenderStateError(
                f"{row.get('employee_id', '<actor>')}: cannot resolve frame metadata"
            ) from exc
        if not frame_ids:
            return None
        frame_index = int(row.get("character_frame_index", row.get("frame_index", 0)))
        return str(frame_ids[frame_index % len(frame_ids)])

    def _occluder_ids(
        self,
        floor_id: str,
        row: dict[str, Any],
    ) -> list[str]:
        if row.get("render_owner") != "walking_depth":
            return []
        ground = row.get("ground_xy")
        if not isinstance(ground, (list, tuple)) or len(ground) != 2:
            return []
        try:
            return [
                str(item["placement_id"])
                for item in self.core.walking_depth.occluders_in_front(floor_id, ground)
                if isinstance(item, dict) and item.get("placement_id")
            ]
        except Exception as exc:
            raise RuntimeRenderStateError(
                f"{row.get('employee_id', '<actor>')}: cannot resolve occluder metadata"
            ) from exc

    def _compact_actor(self, floor_id: str, row: dict[str, Any]) -> dict[str, Any]:
        compact = {
            key: self._json_safe(row[key])
            for key in self._ACTOR_KEYS
            if key in row
        }
        frame_index = int(row.get("character_frame_index", row.get("frame_index", 0)))
        compact["frame_index"] = frame_index
        compact["character_frame_index"] = frame_index
        compact["anchor_xy"] = list(self.CHARACTER_ANCHOR_PX)
        compact["frame_id"] = self._frame_reference(row)
        compact["animation_clock_ms"] = frame_index * int(row.get("character_frame_ms", 360))
        compact["occluder_placement_ids"] = self._occluder_ids(floor_id, row)
        channels = row.get("channels")
        compact_channels: dict[str, Any] = {}
        if isinstance(channels, dict):
            compact_channels.update(self._json_safe(channels))
        if row.get("pc_frame_count") is not None:
            compact_channels["pc"] = {
                "frame_index": int(row.get("pc_frame_index") or 0),
                "frame_count": int(row.get("pc_frame_count") or 1),
                "frame_ms": int(row.get("pc_frame_ms") or 720),
            }
        compact["channels"] = compact_channels
        compact["dialogue"] = {
            "visible": bool(row.get("dialogue_visible")),
            "opacity": float(row.get("dialogue_opacity", 0.0)),
            "phase": row.get("dialogue_phase"),
            "dialogue_id": row.get("dialogue_id"),
            "line_index": row.get("dialogue_line_index"),
            "text": row.get("dialogue_text"),
            "locale": row.get("dialogue_locale"),
            "bubble_id": row.get("dialogue_bubble_id"),
            "offset_xy": row.get("dialogue_bubble_offset_px", [0, 0]),
            "turn_index": int(row.get("turn_index", 0)),
            "speaker_id": row.get("speaker_id"),
        }
        compact["dialogue"] = self._json_safe(compact["dialogue"])
        return compact

    def project(
        self,
        runtime_snapshot: dict[str, Any],
        *,
        floor_id: str,
        sequence: int = 0,
        at_ms: int | None = None,
        events: Iterable[dict[str, Any]] = (),
        presentation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Project one validated runtime sample without materializing images."""
        if not isinstance(floor_id, str) or not floor_id.strip():
            raise RuntimeRenderStateError("floor_id must be non-empty text")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise RuntimeRenderStateError("sequence must be a non-negative integer")
        if at_ms is not None and (
            isinstance(at_ms, bool) or not isinstance(at_ms, int) or at_ms < 0
        ):
            raise RuntimeRenderStateError("at_ms must be a non-negative integer")
        if not isinstance(runtime_snapshot, dict):
            raise RuntimeRenderStateError("runtime_snapshot must be an object")
        if presentation is None:
            try:
                presentation = self.core.resolve_runtime_presentation(
                    runtime_snapshot,
                    at_ms=at_ms,
                    floor_id=floor_id,
                )
            except Exception as exc:
                raise RuntimeRenderStateError("cannot resolve runtime presentation") from exc
        if not isinstance(presentation, dict):
            raise RuntimeRenderStateError("presentation must be an object")
        rows = presentation.get("actors")
        if not isinstance(rows, dict):
            raise RuntimeRenderStateError("presentation actors must be an object")
        actor_rows = [
            self._compact_actor(floor_id, rows[employee_id])
            for employee_id in sorted(rows)
            if isinstance(rows[employee_id], dict)
        ]
        clock = presentation.get("clock")
        if not isinstance(clock, dict):
            clock = {}
        state = {
            "schema": self.SCHEMA,
            "version": self.VERSION,
            "floor_id": floor_id,
            "sequence": sequence,
            "clock_ms": int(clock.get("actor_clock_ms", 0)),
            "full": True,
            "manifest_revision": self.MANIFEST_REVISION,
            "static_scene_id": floor_id,
            "actors": actor_rows,
            "paint_order": {
                "characters": [
                    str(value)
                    for value in presentation.get("paint_order", {}).get("characters", [])
                ],
                "dialogue_bubbles": [
                    str(value)
                    for value in presentation.get("paint_order", {}).get("dialogue_bubbles", [])
                ],
            },
            "active_speech_sessions": self._json_safe(
                presentation.get("active_speech_sessions", [])
            ),
            "events": [self._compact_event(event) for event in list(events)],
        }
        try:
            json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise RuntimeRenderStateError("lean render state is not JSON-safe") from exc
        return copy.deepcopy(state)
