from __future__ import annotations

"""Render review-only samples from the live runtime presentation seam.

This tool deliberately drives the application-facing
``RuntimePresentationHostAdapter``.  That boundary calls
``RuntimePresentationLoop`` once per host frame, which advances
``CentralGameCore.advance_runtime_snapshot`` and then consumes
``CentralGameCore.resolve_runtime_presentation`` through
``RuntimePresentationRenderer``.  It is therefore a visual QA consumer of the
same independent actor/speech clocks used by the runtime, not a second
conversation-plan renderer.  Outputs are evidence under ``LOCAL_REVIEW`` and
are never canonical assets.
"""

import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from RUNTIME.central_core import CentralGameCore
from RUNTIME.runtime_presentation_host import RuntimePresentationHostAdapter
from RUNTIME.runtime_presentation_renderer import RuntimePresentationLoop


class RuntimePresentationQARenderer:
    FLOOR_ID = "floor02"
    MODES = ("ceo_front", "seated_host", "standing_pair")

    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    @staticmethod
    def _quiet_runtime(core: CentralGameCore) -> dict[str, Any]:
        runtime = core.resolve_runtime_snapshot(RuntimePresentationQARenderer.FLOOR_ID)
        for actor in runtime["speech_snapshot"]["actors"].values():
            actor.update({
                "greeting_due_ms": None,
                "greeting_emitted": True,
                "work_start_due_ms": None,
                "work_start_emitted": True,
                "solo_next_due_ms": None,
                "pair_next_due_ms": None,
            })
        for actor in runtime["actor_snapshot"]["actors"].values():
            actor["behavior"]["next_event_due_ms"] = 10**9
        return runtime

    @staticmethod
    def _actor_ids(core: CentralGameCore) -> tuple[str, str, str]:
        actors = core.resolve_actor_snapshot(RuntimePresentationQARenderer.FLOOR_ID)["actors"]
        rows = sorted(
            actors.values(),
            key=lambda item: (
                int(item["assignment"]["assignment_order"]),
                item["employee_id"],
            ),
        )
        ceo = next(
            row["employee_id"]
            for row in rows
            if row["assignment"]["workstation_id"] == "ceo"
        )
        employees = [
            row["employee_id"]
            for row in rows
            if row["assignment"]["workstation_id"] != "ceo"
        ]
        return employees[0], employees[1], ceo

    def _forced_runtime(
        self,
        mode: str,
    ) -> tuple[CentralGameCore, RuntimePresentationHostAdapter, dict[str, Any], dict[str, Any]]:
        core = CentralGameCore(self.root)
        runtime = self._quiet_runtime(core)
        first_employee, second_employee, ceo = self._actor_ids(core)
        initiator, partner = (
            (first_employee, ceo)
            if mode == "ceo_front"
            else (first_employee, second_employee)
        )

        def force_mode(_snapshot, initiator_id, *, counter):
            if initiator_id != initiator:
                return None
            return {
                "kind": "pair",
                "initiator_id": initiator,
                "partner_id": partner,
                "participants": [initiator, partner],
                "mode": mode,
                "category": "conversation_open",
                "dialogue_categories": ["conversation_open", "conversation_reply"],
            }

        core.speech_scheduler._mode_request = force_mode
        core.actor_simulation.choose_behavior_event = lambda *args, **kwargs: "talk"
        runtime["actor_snapshot"]["actors"][initiator]["behavior"]["next_event_due_ms"] = 0
        loop = RuntimePresentationLoop(
            core,
            runtime_snapshot=runtime,
            floor_id=self.FLOOR_ID,
        )
        # Keep the QA path identical to the application integration path:
        # one host call produces one frame.  The sink is intentionally
        # side-effect free; the tool consumes the returned frame below.
        host = RuntimePresentationHostAdapter(loop, frame_sink=lambda _frame: None)
        initial = host.render_current(at_ms=0)
        advanced = host.tick(60)
        started = next(
            event
            for event in advanced["speech_events"]
            if event["type"] == "speech_session_started" and event["kind"] == "pair"
        )
        return core, host, started, initial

    @staticmethod
    def _sample_times(started: dict[str, Any]) -> list[int]:
        bubble = int(started["bubble_start_ms"])
        plan = started.get("conversation_plan") or {}
        plan_end = max(
            (int(row.get("timestamp_ms", 0)) for row in plan.get("timeline", [])),
            default=bubble + 4300,
        )
        values = {
            int(started.get("movement_started_ms", 0)),
            int(started.get("movement_arrival_ms", bubble)),
            bubble,
            bubble + 500,
            bubble + 4000,
            bubble + 4300,
            int(plan.get("talk_end_ms", bubble + 4000)),
            plan_end,
        }
        if started.get("mode") == "standing_pair":
            values.add(bubble + 4300 + 1200)
        return sorted(value for value in values if value >= 0)

    @staticmethod
    def _labelled(image: Image.Image, label: str) -> Image.Image:
        result = image.convert("RGBA").copy()
        draw = ImageDraw.Draw(result, "RGBA")
        draw.rectangle((0, 0, result.width, 28), fill=(16, 20, 28, 225))
        draw.text((8, 7), label, fill=(255, 255, 255, 255))
        return result

    @staticmethod
    def _contact(images: list[Image.Image], *, columns: int = 2) -> Image.Image:
        if not images:
            raise RuntimeError("No QA images were rendered")
        width, height = images[0].size
        columns = max(1, min(columns, len(images)))
        rows = (len(images) + columns - 1) // columns
        contact = Image.new("RGBA", (width * columns, height * rows), (255, 255, 255, 255))
        for index, image in enumerate(images):
            contact.alpha_composite(image, ((index % columns) * width, (index // columns) * height))
        return contact

    def render_mode(self, mode: str, output_root: Path) -> dict[str, Any]:
        _core, host, started, initial = self._forced_runtime(mode)
        images: list[Image.Image] = []
        samples: list[dict[str, Any]] = []
        # Capture the initial working frame before the first forced actor tick.
        sample_frames = [(0, initial)]
        current_ms = int(host.loop.runtime_snapshot["actor_snapshot"]["clock"]["simulation_time_ms"])
        for timestamp_ms in self._sample_times(started):
            if timestamp_ms <= 0 or timestamp_ms < current_ms:
                continue
            frame = host.tick(timestamp_ms - current_ms)
            sample_frames.append((timestamp_ms, frame))
            current_ms = timestamp_ms
        for timestamp_ms, frame in sample_frames:
            image = frame["image"]
            presentation = frame["presentation"]
            participant_rows = {
                employee_id: {
                    "action": presentation["actors"][employee_id].get("action"),
                    "subaction": presentation["actors"][employee_id].get("subaction"),
                    "dialogue_visible": presentation["actors"][employee_id].get("dialogue_visible"),
                    "dialogue_opacity": presentation["actors"][employee_id].get("dialogue_opacity"),
                    "presentation_phase": presentation["actors"][employee_id].get("presentation_phase"),
                }
                for employee_id in started["participants"]
            }
            images.append(self._labelled(image, f"{mode}  t={timestamp_ms}ms"))
            samples.append({"timestamp_ms": timestamp_ms, "participants": participant_rows})
        output_root.mkdir(parents=True, exist_ok=True)
        contact_path = output_root / f"runtime_{mode}_contact.png"
        self._contact(images).save(contact_path)
        return {
            "mode": mode,
            "floor_id": self.FLOOR_ID,
            "participants": started["participants"],
            "bubble_start_ms": int(started["bubble_start_ms"]),
            "fade_end_ms": int(started["fade_end_ms"]),
            "plan_end_ms": max(
                int(row.get("timestamp_ms", 0))
                for row in (started.get("conversation_plan") or {}).get("timeline", [])
            ),
            "contact_sheet": str(contact_path),
            "samples": samples,
        }

    def render_home_return(self, output_root: Path) -> dict[str, Any]:
        core = CentralGameCore(self.root)
        runtime = self._quiet_runtime(core)
        employee_id = next(
            employee_id
            for employee_id, actor in runtime["actor_snapshot"]["actors"].items()
            if actor["assignment"]["workstation_id"] != "ceo"
        )
        loop = RuntimePresentationLoop(
            core,
            runtime_snapshot=runtime,
            floor_id=self.FLOOR_ID,
        )
        host = RuntimePresentationHostAdapter(loop, frame_sink=lambda _frame: None)
        requested = host.tick(
            0,
            actor_commands=[{"type": "request_home", "employee_id": employee_id}],
        )
        outbound_ms = int(
            requested["runtime_snapshot"]["actor_snapshot"]["actors"][employee_id]["position"]["route"]["duration_ms"]
        )
        exited = host.tick(outbound_ms + 240)
        ready_at = int(
            exited["runtime_snapshot"]["actor_snapshot"]["actors"][employee_id]["behavior"]["activity_until_ms"]
        )
        ready = exited
        remaining = ready_at - int(exited["runtime_snapshot"]["actor_snapshot"]["clock"]["simulation_time_ms"])
        if remaining > 0:
            ready = host.tick(remaining)
        returned = host.tick(
            0,
            actor_commands=[{"type": "request_return", "employee_id": employee_id}],
        )
        inbound_ms = int(
            returned["runtime_snapshot"]["actor_snapshot"]["actors"][employee_id]["position"]["route"]["duration_ms"]
        )
        completed = host.tick(inbound_ms + 20000)
        stages = [
            ("going_home", requested),
            ("home_recovery", exited),
            ("ready_to_return", ready),
            ("returning_to_work", returned),
            ("working_again", completed),
        ]
        images: list[Image.Image] = []
        rows: list[dict[str, Any]] = []
        for name, frame in stages:
            image = frame["image"]
            presentation = frame["presentation"]
            actor = presentation["actors"][employee_id]
            images.append(self._labelled(image, f"{name}  t={presentation['clock']['actor_sample_ms']}ms"))
            rows.append({
                "stage": name,
                "timestamp_ms": presentation["clock"]["actor_sample_ms"],
                "presence": actor.get("presence"),
                "activity": actor.get("activity"),
                "visible": actor.get("visible"),
                "render_owner": actor.get("render_owner"),
            })
        output_root.mkdir(parents=True, exist_ok=True)
        contact_path = output_root / "runtime_home_return_contact.png"
        self._contact(images, columns=3).save(contact_path)
        return {
            "employee_id": employee_id,
            "contact_sheet": str(contact_path),
            "samples": rows,
        }

    def render_all(self, output_root: Path) -> dict[str, Any]:
        modes = [self.render_mode(mode, output_root) for mode in self.MODES]
        home_return = self.render_home_return(output_root)
        manifest = {
            "schema": "gds.runtime_presentation_qa.v1",
            "status": "PASS",
            "source": "RuntimePresentationHostAdapter.tick + RuntimePresentationLoop + RuntimePresentationRenderer",
            "output_root": str(output_root),
            "modes": modes,
            "home_return": home_return,
        }
        manifest_path = output_root / "RUNTIME_PRESENTATION_QA.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest["manifest"] = str(manifest_path)
        return manifest


def main() -> int:
    output_root = PROJECT_ROOT / "LOCAL_REVIEW" / "PHASE8E_RUNTIME_PRESENTATION_QA_20260901"
    manifest = RuntimePresentationQARenderer(PROJECT_ROOT).render_all(output_root)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
