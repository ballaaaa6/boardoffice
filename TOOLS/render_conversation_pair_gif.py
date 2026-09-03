from __future__ import annotations

"""Render author-review GIFs for the approved conversation presentation.

The generated files are review evidence only.  The runtime plan itself owns
the one-loop timing: the first bubble starts the four-second visible window,
the partner follows after the short gap, both bubbles fade, and visitors then
walk back to their work seats.
"""

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

try:
    from TOOLS._bootstrap import ensure_project_root
except ModuleNotFoundError:
    from _bootstrap import ensure_project_root

PROJECT_ROOT = ensure_project_root(__file__)

from RUNTIME.central_core import CentralGameCore


class ConversationPairGifRenderer:
    # Keep review playback on the same 60 ms simulation tick as the runtime;
    # this makes the 4,000 ms visible window read as four seconds in the GIF.
    FRAME_MS = 60
    TALK_FRAMES = 12  # retained only for callers comparing the legacy seam
    PREVIEW_TEXT = "Quick check-in!"

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.core = CentralGameCore(self.root)
        self._sprite_cache: dict[tuple[str, str, str], list[Image.Image]] = {}
        enabled = self.core.list_dialogue_lines(locale="en", enabled_only=True)
        if enabled:
            self.PREVIEW_TEXT = str(enabled[0]["text"])

    def _sprite(self, character_id: str, action: str, direction: str, frame_index: int = 0) -> Image.Image:
        key = (character_id, action, direction)
        if key not in self._sprite_cache:
            self._sprite_cache[key] = self.core.characters.render(
                character_id, action, direction
            ).frames
        frames = self._sprite_cache[key]
        return frames[int(frame_index) % len(frames)].convert("RGBA")

    def _base_assignments(self, floor_id: str, timeline_row: dict[str, Any]) -> list[dict[str, Any]]:
        assignments = []
        for employee_id, actor_state in timeline_row["actors"].items():
            if actor_state.get("render_owner") != "work_seat":
                continue
            actor = self.core.employee_metadata.get(employee_id)
            assignment = actor.get("assignment") or {}
            if assignment.get("floor_id") != floor_id:
                continue
            assignment_row = {
                "workstation_id": assignment["workstation_id"],
                "character_id": actor["character_id"],
            }
            if actor_state.get("action") == "work":
                assignment_row["subaction"] = actor_state.get("subaction", "normal_work")
            assignments.append(assignment_row)
        return assignments

    def _composite(self, floor_id: str, base: Image.Image, dynamic: list[dict[str, Any]]) -> Image.Image:
        canvas = base.convert("RGBA").copy()
        normalized = []
        for index, actor in enumerate(dynamic):
            ground = actor.get("ground_xy")
            if ground is None:
                continue
            sprite = actor["sprite"]
            normalized.append((float(ground[1]), index, actor, (float(ground[0]), float(ground[1]))))
        for _y, _index, actor, ground_xy in sorted(normalized, key=lambda row: (row[0], row[1])):
            sprite = self.core.walking_depth._mask_character_by_world_occluders(
                floor_id,
                actor["sprite"],
                ground_xy,
                ground_anchor_px=(16, 31),
            )
            x = int(round(ground_xy[0] - 16))
            y = int(round(ground_xy[1] - 31))
            canvas.alpha_composite(sprite, (x, y))
        return canvas

    def _bubble_payload(
        self,
        employee_id: str,
        actor_state: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not actor_state.get("dialogue_visible"):
            return None
        character_id = actor_state["character_id"]
        direction = str(actor_state.get("direction") or "SE").upper()
        action = "idle" if actor_state.get("render_owner") == "walking_depth" else "work"
        subaction = actor_state.get("subaction", "normal_work") if action == "work" else None
        frame_ids = self.core.characters.resolve_frame_ids(
            character_id,
            action,
            direction,
            subaction,
        )
        frame_id = frame_ids[int(actor_state.get("frame_index", 0)) % len(frame_ids)]
        ground = actor_state.get("ground_xy")
        if ground is None:
            # A seated WorkSeat has no navigation coordinate.  Use the actual
            # composed human top-left, not the chair origin: WorkSeat places
            # the human with a direction-specific visual offset.
            seat = self.core.work_seats.resolve_workstation_seat(
                actor_state["floor_id"],
                (self.core.employee_metadata.get(employee_id).get("assignment") or {})["workstation_id"],
            )
            work = self.core.characters.render(
                character_id,
                "work",
                seat["direction"],
                subaction or "normal_work",
            )
            chair = self.core.world.load_asset(seat["chair_asset_id"]).convert("RGBA")
            human_offset = self.core.work_seats.resolve_world_offset(
                seat["direction"],
                chair_size=chair.size,
                human_size=work.frames[0].size,
            )
            actor_top_left = (
                int(seat["chair_x_px"]) + int(human_offset[0]),
                int(seat["chair_y_px"]) + int(human_offset[1]),
            )
        else:
            actor_top_left = (
                int(round(float(ground[0]) - 16)),
                int(round(float(ground[1]) - 31)),
            )
        bubble = self.core.render_employee_dialogue_bubble(
            employee_id,
            frame_id,
            str(actor_state.get("dialogue_text") or self.PREVIEW_TEXT),
            actor_top_left=actor_top_left,
            locale=str(actor_state.get("dialogue_locale") or "en"),
            bubble_offset_px=actor_state.get("dialogue_bubble_offset_px", (0, 0)),
        )
        opacity = max(0.0, min(1.0, float(actor_state.get("dialogue_opacity", 1.0))))
        return {
            "employee_id": employee_id,
            "bubble": bubble,
            "image": bubble.image.convert("RGBA"),
            "anchor": tuple(bubble.head_anchor),
            "opacity": opacity,
            # ``turn_index`` is the authored speaker order.  It is used only
            # for the overlay paint order: a later speaker is composited last
            # and therefore naturally paints over an earlier bubble.
            "turn_index": int(actor_state.get("turn_index", 0)),
        }

    def _draw_bubble(
        self,
        canvas: Image.Image,
        payload: dict[str, Any],
    ) -> None:
        """Paint a bubble at the renderer's exact head anchor.

        The dialogue renderer already returns a whole-crop bubble whose tail
        is positioned from the supplied head anchor.  This layer deliberately
        performs no collision search, displacement, connector drawing or
        depth sorting: each image is composited at that exact position and the
        next image may paint over it.
        """
        bubble_image = payload["image"].copy()
        opacity = float(payload.get("opacity", 1.0))
        if opacity < 1.0:
            alpha = bubble_image.getchannel("A").point(lambda value: int(round(value * opacity)))
            bubble_image.putalpha(alpha)
        canvas.alpha_composite(
            bubble_image,
            (
                int(payload["bubble"].bubble_top_left[0]),
                int(payload["bubble"].bubble_top_left[1]),
            ),
        )

    def _bubble(self, canvas: Image.Image, employee_id: str, actor_state: dict[str, Any]) -> None:
        payload = self._bubble_payload(employee_id, actor_state)
        if payload is None:
            return
        self._draw_bubble(canvas, payload)

    @staticmethod
    def _overlay(canvas: Image.Image, title: str, timestamp_ms: int, timeline_row: dict[str, Any]) -> None:
        draw = ImageDraw.Draw(canvas, "RGBA")
        lines = [title, f"t={timestamp_ms}ms (one loop / 4s bubble / fade)"]
        for employee_id, state in sorted(timeline_row["actors"].items()):
            uv = state.get("current_uv")
            speaker = state.get("speaker_id") if state.get("dialogue_visible") else "listen"
            opacity = state.get("dialogue_opacity", 0.0)
            lines.append(
                f"{employee_id}: {state.get('phase')} / {state.get('direction')} / UV={uv or 'seat'} / {speaker} / α={opacity}"
            )
        width = max(380, max(len(line) for line in lines) * 7 + 18)
        height = 16 * len(lines) + 8
        draw.rectangle((0, 0, width, height), fill=(20, 25, 35, 210))
        for index, line in enumerate(lines):
            draw.text((8, 4 + index * 16), line, fill=(255, 255, 255, 255))

    def render_plan(self, name: str, plan: dict[str, Any], output_root: Path) -> dict[str, Any]:
        if not plan.get("ready"):
            raise RuntimeError(f"{name}: conversation plan is not ready: {plan.get('reason')}")
        floor_id = str(plan["floor_id"])
        frames: list[Image.Image] = []
        timeline = plan.get("timeline", [])
        for timeline_row in timeline:
            base = self.core.render_floor_with_work(
                floor_id,
                self._base_assignments(floor_id, timeline_row),
            )
            dynamic: list[dict[str, Any]] = []
            for employee_id, actor_state in timeline_row["actors"].items():
                if actor_state.get("render_owner") != "walking_depth":
                    continue
                direction = str(actor_state.get("direction") or "SE").upper()
                action = "move" if actor_state.get("action") == "move" else "idle"
                dynamic.append({
                    "sprite": self._sprite(
                        actor_state["character_id"],
                        action,
                        direction,
                        int(actor_state.get("frame_index", 0)),
                    ),
                    "ground_xy": actor_state.get("ground_xy"),
                    "employee_id": employee_id,
                })
            frame = self._composite(floor_id, base, dynamic)
            # A line remains visible after its speaker starts.  Once the
            # partner begins, paint the second bubble after the first at the
            # exact head-derived position.  There is intentionally no
            # collision resolver or y-sort for this overlay layer.
            payloads = [
                payload
                for employee_id, actor_state in timeline_row["actors"].items()
                if (payload := self._bubble_payload(employee_id, actor_state)) is not None
            ]
            payloads.sort(key=lambda payload: (int(payload.get("turn_index", 0)), str(payload["employee_id"])))
            for payload in payloads:
                self._draw_bubble(frame, payload)
            self._overlay(frame, f"Conversation QA — {name} — {plan['mode']}", int(timeline_row["timestamp_ms"]), timeline_row)
            frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=256))
        if not frames:
            raise RuntimeError(f"{name}: plan produced no frames")
        output_root.mkdir(parents=True, exist_ok=True)
        gif_path = output_root / f"{name}.gif"
        frames[0].save(
            gif_path,
            save_all=True,
            append_images=frames[1:],
            duration=self.FRAME_MS,
            loop=0,
            disposal=2,
            optimize=False,
        )
        timeline_timestamps = [int(row["timestamp_ms"]) for row in timeline]

        def index_at_or_after(timestamp_ms: int) -> int:
            for index, value in enumerate(timeline_timestamps):
                if value >= int(timestamp_ms):
                    return index
            return len(timeline_timestamps) - 1

        talk_start_index = index_at_or_after(int(plan.get("talk_start_ms", 0)))
        talk_end_index = index_at_or_after(int(plan.get("talk_end_ms", 0)))
        turn_indices = {
            index_at_or_after(int(value))
            for segment in plan.get("speaker_schedule", [])
            for value in (
                segment.get("bubble_start_ms", segment.get("start_ms")),
                segment.get("fade_start_ms", segment.get("end_ms")),
            )
            if value is not None
        }
        contact_indices = sorted({0, talk_start_index, talk_end_index, len(frames) - 1, *turn_indices})
        contact = Image.new("RGBA", (frames[0].width * len(contact_indices), frames[0].height), (255, 255, 255, 255))
        for column, index in enumerate(contact_indices):
            contact.alpha_composite(frames[index].convert("RGBA"), (column * frames[0].width, 0))
        contact_path = output_root / f"{name}_contact.png"
        contact.save(contact_path)
        return {
            "name": name,
            "floor_id": floor_id,
            "mode": plan["mode"],
            "conversation_id": plan["conversation_id"],
            "gif": str(gif_path),
            "contact_sheet": str(contact_path),
            "frame_count": len(frames),
            "frame_ms": self.FRAME_MS,
            "timeline_end_ms": int(timeline[-1]["timestamp_ms"]),
            "talk_start_ms": int(plan.get("talk_start_ms", 0)),
            "talk_end_ms": int(plan.get("talk_end_ms", 0)),
            "loop_count": int(plan.get("loop_count", 1)),
            "speaker_schedule": plan.get("speaker_schedule", []),
            "spot": plan.get("spot"),
            "endpoint_by_actor": plan.get("endpoint_by_actor"),
            "facing_by_actor": plan.get("facing_by_actor"),
            "crowd_audit": plan.get("crowd_audit"),
            "preview_only_timing": bool(plan.get("preview_only_timing", True)),
        }

    def _floor_employees(self, floor_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        snapshot = self.core.resolve_conversation_snapshot(floor_id)
        ordered = sorted(
            snapshot["actors"].values(),
            key=lambda actor: (int(actor["assignment_order"]), actor["employee_id"]),
        )
        ceo = next(actor for actor in ordered if actor["role"] == "ceo")
        employees = [actor for actor in ordered if actor["role"] == "employee"]
        return snapshot, ceo, employees[0]

    def render_examples(self, output_root: Path) -> dict[str, Any]:
        examples: list[dict[str, Any]] = []
        snapshot, ceo, first_employee = self._floor_employees("floor02")
        floor02_ids = sorted(snapshot["actors"], key=lambda employee_id: (snapshot["actors"][employee_id]["assignment_order"], employee_id))
        employees = [employee_id for employee_id in floor02_ids if snapshot["actors"][employee_id]["role"] == "employee"]
        pair = self.core.resolve_conversation_plan(
            employees[0],
            partner_id=employees[1],
            mode="standing_pair",
            snapshot=snapshot,
            origin_uvs=[],
        )
        examples.append(self.render_plan("floor02_employee_pair", pair, output_root))
        ceo_plan = self.core.resolve_conversation_plan(
            first_employee["employee_id"],
            partner_id=ceo["employee_id"],
            mode="ceo_front",
            snapshot=snapshot,
        )
        examples.append(self.render_plan("floor02_employee_to_ceo", ceo_plan, output_root))
        seated_host_plan = self.core.resolve_conversation_plan(
            employees[0],
            partner_id=employees[1],
            mode="seated_host",
            snapshot=snapshot,
        )
        examples.append(self.render_plan("floor02_employee_to_seated_host", seated_host_plan, output_root))

        f01_snapshot = self.core.resolve_conversation_snapshot("floor01")
        f01_ids = sorted(f01_snapshot["actors"], key=lambda employee_id: (f01_snapshot["actors"][employee_id]["assignment_order"], employee_id))
        f01_employees = [employee_id for employee_id in f01_ids if f01_snapshot["actors"][employee_id]["role"] == "employee"]
        f01_plan = self.core.resolve_conversation_plan(
            f01_employees[0],
            partner_id=f01_employees[1],
            mode="standing_pair",
            snapshot=f01_snapshot,
            origin_uvs=[],
        )
        examples.append(self.render_plan("floor01_employee_pair", f01_plan, output_root))
        manifest = {
            "schema": "gds.conversation_pair_gif_qa.v1",
            "status": "PASS",
            "source": "ConversationBehaviorCore + existing WorkSeat/WalkingDepth/Dialogue renderers",
            "preview_only_timing": False,
            "loop_policy": "infinite_gif_playback_only",
            "examples": examples,
        }
        path = output_root / "CONVERSATION_PAIR_GIF_QA.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest["manifest"] = str(path)
        return manifest


def main() -> int:
    output_root = PROJECT_ROOT / "LOCAL_REVIEW" / "PHASE8E_CONVERSATION_QA_20260901"
    manifest = ConversationPairGifRenderer(PROJECT_ROOT).render_examples(output_root)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
