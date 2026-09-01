from __future__ import annotations

"""Local review host for the Phase 8E runtime presentation loop.

This is deliberately a review tool, not a second game runtime.  It owns a
``RuntimePresentationHostAdapter`` exactly like an external app would, exposes
explicit tick/command/save/load/replay endpoints, and serves a small HTML
dashboard so the author can watch the stamina-to-home boundary.
"""

import argparse
import base64
import copy
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from RUNTIME.central_core import CentralGameCore, CentralGameCoreError
from RUNTIME.runtime_persistence import RuntimePersistenceError
from RUNTIME.runtime_presentation_host import RuntimePresentationHostAdapter
from RUNTIME.runtime_presentation_renderer import RuntimePresentationLoop


DEFAULT_PORT = 8765
FLOOR_ID = "floor02"
HTML_PATH = PROJECT_ROOT / "WEB" / "runtime_review.html"


def _quiet_runtime(core: CentralGameCore) -> dict[str, Any]:
    runtime = core.resolve_runtime_snapshot(FLOOR_ID)
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
    return core.validate_runtime_snapshot(runtime)


class ReviewState:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.core = CentralGameCore(PROJECT_ROOT)
        self.floor_id = FLOOR_ID
        self.base_runtime = _quiet_runtime(self.core)
        self.initial_runtime = copy.deepcopy(self.base_runtime)
        self.replay_steps: list[dict[str, Any]] = []
        self._reset_loop()

    def _reset_loop(self, runtime: dict[str, Any] | None = None) -> None:
        source = copy.deepcopy(runtime if runtime is not None else self.initial_runtime)
        loop = RuntimePresentationLoop(
            self.core,
            runtime_snapshot=source,
            floor_id=self.floor_id,
        )
        self.adapter = RuntimePresentationHostAdapter(loop)
        self.adapter.render_current()

    @staticmethod
    def _ready_return_commands(runtime: dict[str, Any]) -> list[dict[str, Any]]:
        """Mirror an external app's ready-gated return policy for live review.

        The core intentionally requires an explicit ``request_return`` after
        home recovery.  The review host is the caller, so its live mode sends
        that command as soon as the deterministic ready timestamp is reached;
        this keeps the dashboard moving without hiding the core contract.
        """
        now_ms = int(runtime["actor_snapshot"]["clock"]["simulation_time_ms"])
        commands: list[dict[str, Any]] = []
        for employee_id, actor in sorted(runtime["actor_snapshot"]["actors"].items()):
            if actor.get("presence") != "home" or actor.get("activity") != "home_recovery":
                continue
            ready_at = actor.get("behavior", {}).get("activity_until_ms")
            if ready_at is not None and int(ready_at) <= now_ms:
                commands.append({"type": "request_return", "employee_id": employee_id})
        return commands

    def live_start(self) -> dict[str, Any]:
        """Start a self-running review scenario with one observable critical route.

        One actor begins at critical stamina so the finish-current-loop rule is
        visible immediately.  Other actors remain normal and receive staggered
        deterministic behavior/speech due times, allowing work, recovery,
        wander and conversation channels to emerge without manual clicks.
        """
        with self.lock:
            runtime = copy.deepcopy(self.base_runtime)
            actor_ids = sorted(runtime["actor_snapshot"]["actors"])
            if not actor_ids:
                raise CentralGameCoreError("floor02 has no actors for live review")
            critical_id = actor_ids[0]
            critical = runtime["actor_snapshot"]["actors"][critical_id]
            critical["stamina"].update({
                "current_milli": 5000,
                "threshold_band": "critical",
                "drain_remainder": 0,
            })
            critical["behavior"].update({
                "next_event_due_ms": 10**9,
                "active_event": None,
                "activity_started_ms": 0,
                "activity_until_ms": None,
                "work_loop_elapsed_ms": 0,
                "pending_home": False,
                "pending_home_due_ms": None,
            })
            critical["presence"] = "present"
            critical["activity"] = "working"
            critical["conversation_phase"] = None
            # Stagger normal actors so the floor develops into a readable
            # living scene instead of firing every behavior at once.
            for index, employee_id in enumerate(actor_ids[1:], start=1):
                actor = runtime["actor_snapshot"]["actors"][employee_id]
                actor["behavior"]["next_event_due_ms"] = 1200 + (index - 1) * 1200
            speech_actors = runtime["speech_snapshot"]["actors"]
            for actor in speech_actors.values():
                actor["greeting_due_ms"] = None
                actor["greeting_emitted"] = True
                actor["work_start_due_ms"] = None
                actor["work_start_emitted"] = True
                actor["solo_next_due_ms"] = None
                actor["pair_next_due_ms"] = None
            if len(actor_ids) > 1:
                # A first self-talk line makes the speech lane visible early;
                # the scheduler re-arms its normal intervals afterward.
                speech_actors[actor_ids[1]]["work_start_due_ms"] = 600
                speech_actors[actor_ids[1]]["work_start_emitted"] = False
            if len(actor_ids) > 2:
                speech_actors[actor_ids[2]]["pair_next_due_ms"] = 1800
            if len(actor_ids) > 3:
                speech_actors[actor_ids[3]]["solo_next_due_ms"] = 3000
            runtime = self.core.validate_runtime_snapshot(runtime)
            self.initial_runtime = copy.deepcopy(runtime)
            self.replay_steps = []
            self._reset_loop(runtime)
            # Kick the queue at a small boundary so the first render already
            # demonstrates that the critical actor is pending home.
            return self.tick(60, autopilot=True, note="live simulation started")

    @staticmethod
    def _image_data_url(image: Any) -> str:
        output = BytesIO()
        image.convert("RGBA").save(output, format="PNG", optimize=True)
        encoded = base64.b64encode(output.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    @staticmethod
    def _actor_rows(frame: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for employee_id, row in frame["presentation"].get("actors", {}).items():
            stamina = row.get("stamina") or {}
            rows.append({
                "employee_id": employee_id,
                "character_id": row.get("character_id"),
                "activity": row.get("activity"),
                "presence": row.get("presence"),
                "action": row.get("action"),
                "subaction": row.get("subaction"),
                "render_owner": row.get("render_owner"),
                "visible": row.get("visible"),
                "stamina": round(int(stamina.get("current_milli", 0)) / 1000, 3),
                "stamina_band": stamina.get("threshold_band"),
                "pending_home": bool(
                    frame["runtime_snapshot"]["actor_snapshot"]["actors"]
                    .get(employee_id, {}).get("behavior", {}).get("pending_home", False)
                ),
                "pending_home_due_ms": (
                    frame["runtime_snapshot"]["actor_snapshot"]["actors"]
                    .get(employee_id, {}).get("behavior", {}).get("pending_home_due_ms")
                ),
            })
        return sorted(rows, key=lambda row: row["employee_id"])

    def frame_payload(self, frame: dict[str, Any], *, note: str | None = None) -> dict[str, Any]:
        runtime = frame["runtime_snapshot"]
        actor_clock = runtime["actor_snapshot"]["clock"]["simulation_time_ms"]
        return {
            "floor_id": self.floor_id,
            "frame_count": self.adapter.frame_count,
            "clock_ms": actor_clock,
            "image_data_url": self._image_data_url(frame["image"]),
            "actors": self._actor_rows(frame),
            "presentation": frame["presentation"],
            "runtime_snapshot": runtime,
            "snapshot_json": self.core.serialize_runtime_snapshot(runtime),
            "events": frame.get("events", []),
            "actor_events": frame.get("actor_events", []),
            "speech_events": frame.get("speech_events", []),
            "replay_steps": copy.deepcopy(self.replay_steps),
            "note": note,
        }

    def current(self, *, note: str | None = None) -> dict[str, Any]:
        with self.lock:
            return self.frame_payload(self.adapter.last_frame or self.adapter.render_current(), note=note)

    def tick(
        self,
        elapsed_ms: int,
        *,
        actor_commands: list[dict[str, Any]] | None = None,
        speech_commands: list[dict[str, Any]] | None = None,
        autopilot: bool = False,
        note: str | None = None,
    ) -> dict[str, Any]:
        with self.lock:
            commands = copy.deepcopy(actor_commands or [])
            if autopilot:
                runtime = self.adapter.loop.runtime_snapshot
                existing_ids = {
                    str(command.get("employee_id"))
                    for command in commands
                    if isinstance(command, dict)
                }
                commands.extend(
                    command
                    for command in self._ready_return_commands(runtime)
                    if command["employee_id"] not in existing_ids
                )
            frame = self.adapter.tick(
                elapsed_ms,
                actor_commands=commands,
                speech_commands=speech_commands or [],
            )
            self.replay_steps.append({
                "elapsed_ms": int(elapsed_ms),
                "actor_commands": copy.deepcopy(commands),
                "speech_commands": copy.deepcopy(speech_commands or []),
                "dialogue_locale": "en",
                "dialogue_seed": "0",
            })
            return self.frame_payload(frame, note=note)

    def reset(self) -> dict[str, Any]:
        with self.lock:
            self.initial_runtime = copy.deepcopy(self.base_runtime)
            self.replay_steps = []
            self._reset_loop()
            return self.current(note="reset")

    def demo_critical(self, employee_id: str) -> dict[str, Any]:
        with self.lock:
            runtime = self.adapter.loop.runtime_snapshot
            actor = runtime["actor_snapshot"]["actors"].get(employee_id)
            if actor is None:
                raise CentralGameCoreError(f"Unknown floor02 employee: {employee_id}")
            actor["stamina"].update({
                "current_milli": 5000,
                "threshold_band": "critical",
                "drain_remainder": 0,
            })
            actor["behavior"].update({
                "next_event_due_ms": 10**9,
                "active_event": None,
                "activity_started_ms": runtime["actor_snapshot"]["clock"]["simulation_time_ms"],
                "activity_until_ms": None,
                "work_loop_elapsed_ms": 0,
                "pending_home": False,
                "pending_home_due_ms": None,
            })
            actor["presence"] = "present"
            actor["activity"] = "working"
            actor["conversation_phase"] = None
            runtime = self.core.validate_runtime_snapshot(runtime)
            self.initial_runtime = copy.deepcopy(runtime)
            self.replay_steps = []
            self._reset_loop(runtime)
            # One small tick makes the auto-queue observable while leaving a
            # full 720ms worknormal loop for the author to watch.
            return self.tick(60)

    def save(self) -> dict[str, Any]:
        with self.lock:
            runtime = self.adapter.loop.runtime_snapshot
            return {
                "runtime_snapshot": runtime,
                "snapshot_json": self.core.serialize_runtime_snapshot(runtime),
                "replay_json": self.core.serialize_runtime_replay(
                    self.initial_runtime, self.replay_steps
                ),
            }

    def load(self, runtime: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            validated = self.core.deserialize_runtime_snapshot(runtime)
            self.initial_runtime = copy.deepcopy(validated)
            self.replay_steps = []
            self._reset_loop(validated)
            return self.current(note="loaded snapshot")

    def replay(self, package: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            result = self.core.replay_runtime_package(package)
            self.replay_steps = copy.deepcopy(package.get("steps", []))
            self._reset_loop(result["snapshot"])
            frame = self.adapter.last_frame or self.adapter.render_current()
            payload = self.frame_payload(frame, note="deterministic replay complete")
            payload["replay_trace"] = result.get("trace", [])
            return payload


STATE = ReviewState()


class ReviewHandler(BaseHTTPRequestHandler):
    server_version = "GDSRuntimeReview/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        # Keep the terminal readable; failures are still returned as JSON.
        return

    def _send(self, status: int, payload: Any, *, content_type: str = "application/json") -> None:
        if isinstance(payload, str):
            body = payload.encode("utf-8")
        else:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, exc: Exception) -> None:
        self._send(status, {"error": str(exc), "type": exc.__class__.__name__})

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > 12 * 1024 * 1024:
            raise ValueError("request body is too large")
        value = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(value, dict):
            raise ValueError("request body must be an object")
        return value

    def do_GET(self) -> None:
        try:
            if self.path in {"/", "/index.html"}:
                self._send(200, HTML_PATH.read_text(encoding="utf-8"), content_type="text/html")
                return
            if self.path == "/api/state":
                self._send(200, STATE.current())
                return
            if self.path == "/api/policy":
                policy = STATE.core.employee_metadata.stamina_policy()
                self._send(200, {
                    "floor_id": FLOOR_ID,
                    "normal_work_loop_ms": STATE.core.actor_simulation.WORK_LOOP_MS,
                    "critical_threshold": STATE.core.actor_simulation.CRITICAL_THRESHOLD_MILLI / 1000,
                    "emotion_effects": policy.get("emotion_effects", {}),
                    "home_policy": policy.get("home_policy", {}),
                })
                return
            self._send(404, {"error": "not found"})
        except Exception as exc:
            self._error(500, exc)

    def do_POST(self) -> None:
        try:
            body = self._read_json()
            if self.path == "/api/reset":
                self._send(200, STATE.reset())
            elif self.path == "/api/live-start":
                self._send(200, STATE.live_start())
            elif self.path == "/api/tick":
                elapsed_ms = body.get("elapsed_ms", 60)
                if isinstance(elapsed_ms, bool) or not isinstance(elapsed_ms, int) or elapsed_ms < 0:
                    raise ValueError("elapsed_ms must be a non-negative integer")
                self._send(200, STATE.tick(
                    elapsed_ms,
                    actor_commands=body.get("actor_commands"),
                    speech_commands=body.get("speech_commands"),
                    autopilot=bool(body.get("autopilot", False)),
                ))
            elif self.path == "/api/demo-critical":
                employee_id = body.get("employee_id")
                if not isinstance(employee_id, str) or not employee_id:
                    raise ValueError("employee_id is required")
                self._send(200, STATE.demo_critical(employee_id))
            elif self.path == "/api/save":
                self._send(200, STATE.save())
            elif self.path == "/api/load":
                self._send(200, STATE.load(body.get("runtime_snapshot")))
            elif self.path == "/api/replay":
                self._send(200, STATE.replay(body))
            else:
                self._send(404, {"error": "not found"})
        except (CentralGameCoreError, RuntimePersistenceError, ValueError, KeyError) as exc:
            self._error(400, exc)
        except Exception as exc:
            self._error(500, exc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    if args.port <= 0 or args.port > 65535:
        raise SystemExit("--port must be between 1 and 65535")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), ReviewHandler)
    print(f"Runtime review host: http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
