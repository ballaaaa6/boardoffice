from __future__ import annotations

"""Local review host for the Phase 8E runtime presentation loop.

This is deliberately a review tool, not a second game runtime.  It owns a
``RuntimePresentationHostAdapter`` exactly like an external app would, exposes
explicit tick/command/save/load/replay endpoints plus deterministic Talk,
Effects, Wander and Critical demos, and serves a small HTML dashboard for
author review.
"""

import argparse
import base64
import copy
import json
import mimetypes
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from RUNTIME.central_core import CentralGameCore, CentralGameCoreError
from RUNTIME.runtime_persistence import RuntimePersistenceError
from RUNTIME.runtime_presentation_host import RuntimePresentationHostAdapter
from RUNTIME.runtime_presentation_renderer import (
    RuntimePresentationLoop,
    RuntimePresentationRenderer,
)
from RUNTIME.runtime_render_state import RuntimeRenderStateProjector


DEFAULT_PORT = 8765
FLOOR_ID = "floor02"
HTML_PATH = PROJECT_ROOT / "WEB" / "runtime_review.html"
WEB_ROOT = PROJECT_ROOT / "WEB"
API_VERSION = "v2"


def _quiet_runtime(core: CentralGameCore, floor_id: str = FLOOR_ID) -> dict[str, Any]:
    runtime = core.resolve_runtime_snapshot(floor_id)
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
    def __init__(self, floor_id: str = FLOOR_ID) -> None:
        self.lock = threading.RLock()
        self.core = CentralGameCore(PROJECT_ROOT)
        self.available_floors = tuple(sorted(str(value) for value in self.core.world.floors))
        if floor_id not in self.available_floors:
            raise ValueError(f"Unknown floor: {floor_id}")
        self.floor_id = str(floor_id)
        self.base_runtime = _quiet_runtime(self.core, self.floor_id)
        self.initial_runtime = copy.deepcopy(self.base_runtime)
        self.replay_steps: list[dict[str, Any]] = []
        self._live_spawn_due_ms: dict[str, int] = {}
        self._live_behavior_armed: set[str] = set()
        self._behavior_arming_enabled = True
        self._talk_demo_session_id: str | None = None
        self._talk_demo_initiator_id: str | None = None
        self._effects_demo_ids: set[str] = set()
        self._wander_demo_actor_id: str | None = None
        self._critical_demo_actor_id: str | None = None
        self._demo_kind: str | None = None
        self._demo_complete = False
        self.dialogue_locale = "en"
        self.dialogue_seed: str | int = "0"
        self._raster_renderer: RuntimePresentationRenderer | None = None
        self.render_state_projector = RuntimeRenderStateProjector(self.core)
        self._last_tick_metrics: dict[str, Any] = {
            "tick_compute_ms": 0.0,
            "render_ms": 0.0,
            "encode_ms": 0.0,
            "frame_sequence": 0,
        }
        self._dialogue_pool_count_cache: dict[tuple[str, str], int] = {}
        self._reset_loop()

    def _validate_floor_id(self, floor_id: str) -> str:
        value = str(floor_id).strip()
        if value not in self.available_floors:
            raise ValueError(f"Unknown floor: {floor_id}")
        return value

    def _select_floor(self, floor_id: str | None) -> None:
        """Switch the review host to one authoritative floor runtime."""
        if floor_id is None:
            return
        selected = self._validate_floor_id(floor_id)
        if selected == self.floor_id:
            return
        self.floor_id = selected
        self.base_runtime = _quiet_runtime(self.core, self.floor_id)
        self.initial_runtime = copy.deepcopy(self.base_runtime)
        self.replay_steps = []
        self._live_spawn_due_ms = {}
        self._live_behavior_armed = set()
        self._behavior_arming_enabled = True
        self._talk_demo_session_id = None
        self._talk_demo_initiator_id = None
        self._effects_demo_ids = set()
        self._wander_demo_actor_id = None
        self._critical_demo_actor_id = None
        self._demo_kind = None
        self._demo_complete = False
        self._dialogue_pool_count_cache = {}
        self._reset_loop()

    def floors(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for floor_id in self.available_floors:
            record = self.core.world.floor_record(floor_id)
            layout = self.core.world.floor_layout(floor_id)
            roster = self.core.employee_metadata.initial_roster(floor_id)
            rows.append({
                "floor_id": floor_id,
                "layout_id": record.get("layout_id"),
                "skin_id": record.get("skin_id"),
                "layout_family": record.get("layout_id"),
                "actor_count": len(roster),
                "workstation_count": len(layout.get("workstation_groups", {})),
                "has_ceo": any(
                    item.get("workstation_id") == "ceo" for item in roster
                ),
            })
        return rows

    def capabilities(self) -> dict[str, Any]:
        return {
            "api": API_VERSION,
            "floor_count": len(self.available_floors),
            "floors": list(self.available_floors),
            "scenarios": ["live", "full", "talk", "effects", "critical", "wander"],
            "channels": [
                "actor", "movement", "workseat", "pc", "speech", "bubble",
                "vfx", "humanball", "stamina", "portal", "persistence", "replay",
            ],
            "locales": ["en", "th"],
            "timing_ms": {
                "simulation_tick": self.core.actor_simulation.TICK_MS,
                "character_frame": 360,
                "effect_frame": 240,
                "humanball_frame": 240,
                "normal_work_loop": self.core.actor_simulation.WORK_LOOP_MS,
            },
            "roster_policy": {
                "assigned_wave1_active": True,
                "unassigned_inactive": True,
                "multi_floor_mode": "one_selected_floor_per_review_host",
            },
        }

    def _reset_loop(self, runtime: dict[str, Any] | None = None) -> None:
        source = copy.deepcopy(runtime if runtime is not None else self.initial_runtime)
        loop = RuntimePresentationLoop(
            self.core,
            runtime_snapshot=source,
            floor_id=self.floor_id,
            dialogue_locale=self.dialogue_locale,
            dialogue_seed=self.dialogue_seed,
            # The host snapshot is validated on construction and each Central
            # channel validates its own output. Skip the duplicate composed
            # schema walk for this review-only high-frequency preview.
            validate_runtime_each_frame=False,
            copy_runtime_snapshot_each_frame=False,
            render_mode="headless",
        )
        self.adapter = RuntimePresentationHostAdapter(loop, copy_frames=False)
        self.adapter.render_current()

    @staticmethod
    def _validate_renderer(renderer: str | None) -> str:
        value = "raster" if renderer is None else str(renderer).strip().casefold()
        if value not in {"raster", "canvas"}:
            raise ValueError("renderer must be raster or canvas")
        return value

    def _raster_image(self, frame: dict[str, Any]) -> Any:
        image = frame.get("image")
        if image is not None:
            return image
        if self._raster_renderer is None:
            self._raster_renderer = RuntimePresentationRenderer(self.core)
        image, _presentation = self._raster_renderer.render_runtime_snapshot(
            frame["runtime_snapshot"],
            floor_id=self.floor_id,
            validate=False,
        )
        return image

    def _ready_return_commands(self, runtime: dict[str, Any]) -> list[dict[str, Any]]:
        """Mirror an external app's ready-gated return policy for live review.

        The core intentionally requires an explicit ``request_return`` after
        home recovery.  The review host is the caller, so its live mode sends
        that command as soon as the deterministic ready timestamp is reached;
        this keeps the dashboard moving without hiding the core contract.
        """
        now_ms = int(runtime["actor_snapshot"]["clock"]["simulation_time_ms"])
        commands: list[dict[str, Any]] = []
        for employee_id, actor in sorted(runtime["actor_snapshot"]["actors"].items()):
            initial_due = self._live_spawn_due_ms.get(employee_id)
            if initial_due is not None and now_ms < initial_due:
                continue
            if actor.get("presence") != "home" or actor.get("activity") != "home_recovery":
                continue
            ready_at = actor.get("behavior", {}).get("activity_until_ms")
            if ready_at is not None and int(ready_at) <= now_ms:
                commands.append({"type": "request_return", "employee_id": employee_id})
                if initial_due is not None:
                    del self._live_spawn_due_ms[employee_id]
        return commands

    def _arm_live_behavior_timers(self) -> None:
        """Shorten only the review host's wait between visible behaviors.

        Production actor timing remains the metadata-owned 120–300 second
        initial tuning.  The local review host accelerates the first/subsequent
        due times after an actor reaches its seat so VFX, popup and talk
        states can be inspected in one browser session.  Idle wander is a
        retired legacy route and is never armed here.
        """
        if not self._behavior_arming_enabled:
            return
        runtime = self.adapter.loop._runtime_snapshot
        now_ms = int(runtime["actor_snapshot"]["clock"]["simulation_time_ms"])
        changed = False
        actor_ids = sorted(runtime["actor_snapshot"]["actors"])
        for index, employee_id in enumerate(actor_ids):
            actor = runtime["actor_snapshot"]["actors"][employee_id]
            if (
                actor.get("presence") != "present"
                or actor.get("activity") != "working"
                or actor.get("stamina", {}).get("threshold_band") == "critical"
            ):
                continue
            behavior = actor["behavior"]
            # A seated host/participant can own a presentation-only talk
            # overlay without owning an actor recovery window.  Do not arm a
            # new weighted event over that speech clock: the next event due
            # field is intentionally null until the overlay completes.
            if behavior.get("active_event") is not None or behavior.get("talk") is not None:
                continue
            due = behavior.get("next_event_due_ms")
            if employee_id not in self._live_behavior_armed:
                behavior["next_event_due_ms"] = now_ms + 3600 + (index % 5) * 1200
                self._live_behavior_armed.add(employee_id)
                changed = True
            elif due is None or int(due) - now_ms > 12000:
                behavior["next_event_due_ms"] = now_ms + 6000 + (index % 5) * 1200
                changed = True
        if changed:
            # The review-only timer edit changes only an integer due field on
            # an already validated host snapshot.  The fast review loop keeps
            # this trusted copy directly; production callers still validate
            # at every Central/render boundary.
            self.adapter.loop._runtime_snapshot = runtime

    def live_start(
        self,
        *,
        floor_id: str | None = None,
        include_runtime: bool = True,
        dialogue_locale: str | None = None,
        dialogue_seed: str | int | None = None,
        renderer: str = "raster",
        _force_critical: bool = True,
        _demo_kind: str | None = None,
    ) -> dict[str, Any]:
        """Start a self-running review scenario.

        All actors begin off-map at the portal and enter in a deterministic
        stagger, so the review starts with the authored spawn -> walk -> seat
        sequence.  The default review run gives the first actor critical
        stamina so the finish-current-loop rule is visible.  The normal full
        run disables that one forced condition while retaining every live
        behavior timer and channel.
        """
        with self.lock:
            self._select_floor(floor_id)
            if dialogue_locale is not None:
                locale = str(dialogue_locale).strip().lower()
                if locale not in {"en", "th"}:
                    raise ValueError("dialogue_locale must be en or th")
                self.dialogue_locale = locale
            if dialogue_seed is not None:
                self.dialogue_seed = dialogue_seed
            runtime = copy.deepcopy(self.base_runtime)
            actor_ids = sorted(runtime["actor_snapshot"]["actors"])
            if not actor_ids:
                raise CentralGameCoreError(f"{self.floor_id} has no actors for live review")
            critical_id = actor_ids[0] if _force_critical else None
            critical = runtime["actor_snapshot"]["actors"][critical_id] if critical_id else None
            # Every actor starts off-map at the portal, ready to enter.  The
            # stagger keeps the portal readable instead of stacking nine
            # sprites on one entry cell at time zero.
            self._live_spawn_due_ms = {
                employee_id: index * 1200
                for index, employee_id in enumerate(actor_ids)
            }
            self._live_behavior_armed = set()
            self._behavior_arming_enabled = True
            self._talk_demo_session_id = None
            self._talk_demo_initiator_id = None
            self._effects_demo_ids = set()
            self._wander_demo_actor_id = None
            self._critical_demo_actor_id = None
            self._demo_kind = _demo_kind
            self._demo_complete = False
            for actor in runtime["actor_snapshot"]["actors"].values():
                actor.update({
                    "presence": "home",
                    "activity": "home_recovery",
                    "position": {
                        "floor_id": None,
                        "uv": None,
                        "ground_xy": None,
                        "route": None,
                    },
                    "conversation_phase": None,
                })
                actor["behavior"].update({
                    "next_event_due_ms": None,
                    "active_event": None,
                    "activity_started_ms": 0,
                    "activity_until_ms": 0,
                    "work_loop_elapsed_ms": 0,
                    "work_loop_count": 0,
                    "pending_home": False,
                    "pending_home_due_ms": None,
                })
                actor["stamina"].update({
                    "current_milli": 100000,
                    "threshold_band": "normal",
                    "drain_remainder": 0,
                })
            if critical is not None:
                critical["stamina"].update({
                    "current_milli": 5000,
                    "threshold_band": "critical",
                    "drain_remainder": 0,
                })
                critical["behavior"].update({
                    "next_event_due_ms": None,
                    "active_event": None,
                    "activity_started_ms": 0,
                    "activity_until_ms": 0,
                    "work_loop_elapsed_ms": 0,
                    "work_loop_count": 0,
                    "pending_home": False,
                    "pending_home_due_ms": None,
                })
            # Keep every actor in the same off-map state.  The first
            # request_return below starts the real portal entry route; the
            # speech bridge will arm greeting/work-start when the actor
            # actually re-enters the floor and reaches its owned WorkSeat.
            speech_actors = runtime["speech_snapshot"]["actors"]
            for actor in speech_actors.values():
                actor["greeting_due_ms"] = None
                actor["greeting_emitted"] = False
                actor["work_start_due_ms"] = None
                actor["work_start_emitted"] = False
                actor["solo_next_due_ms"] = None
                actor["pair_next_due_ms"] = None
            runtime = self.core.validate_runtime_snapshot(runtime)
            self.initial_runtime = copy.deepcopy(runtime)
            self.replay_steps = []
            self._reset_loop(runtime)
            # Kick the queue at a small boundary so the first render already
            # demonstrates the real portal-entry route.
            return self.tick(
                60,
                autopilot=True,
                note=(
                    "full normal system run started"
                    if _demo_kind == "full"
                    else "live simulation started"
                ),
                include_runtime=include_runtime,
                renderer=renderer,
            )

    def full_demo(
        self,
        *,
        floor_id: str | None = None,
        include_runtime: bool = True,
        dialogue_locale: str | None = None,
        dialogue_seed: str | int | None = None,
        renderer: str = "raster",
    ) -> dict[str, Any]:
        """Start the complete live system with normal stamina for every actor."""
        return self.live_start(
            floor_id=floor_id,
            include_runtime=include_runtime,
            dialogue_locale=dialogue_locale,
            dialogue_seed=dialogue_seed,
            renderer=renderer,
            _force_critical=False,
            _demo_kind="full",
        )

    def demo_talk(
        self,
        employee_id: str | None = None,
        *,
        floor_id: str | None = None,
        mode: str | None = None,
        partner_id: str | None = None,
        dialogue_locale: str | None = None,
        dialogue_seed: str | int | None = None,
        include_runtime: bool = True,
        renderer: str = "raster",
    ) -> dict[str, Any]:
        """Start one deterministic employee conversation for visual review.

        The normal live scenario intentionally waits for each actor's seeded
        behavior timer.  That is useful for a long-running smoke test but
        makes a talk review dependent on wall-clock timing.  This command
        starts exactly one employee request at t=0, leaves every other actor
        seated/quiet and then lets the regular actor-owned route advance.
        """
        with self.lock:
            self._select_floor(floor_id)
            if dialogue_locale is not None:
                self.dialogue_locale = str(dialogue_locale).strip().lower() or "en"
                if self.dialogue_locale not in {"en", "th"}:
                    raise ValueError("dialogue_locale must be en or th")
            if dialogue_seed is not None:
                self.dialogue_seed = dialogue_seed
            runtime = copy.deepcopy(self.base_runtime)
            actor_ids = sorted(runtime["actor_snapshot"]["actors"])
            candidates = [
                actor_key
                for actor_key in actor_ids
                if runtime["actor_snapshot"]["actors"][actor_key]
                .get("assignment", {})
                .get("workstation_id")
                != "ceo"
            ]
            if not candidates:
                raise CentralGameCoreError(f"{self.floor_id} has no employee actor for talk demo")
            initiator_id = str(employee_id) if employee_id in candidates else candidates[0]
            now_ms = int(runtime["actor_snapshot"]["clock"]["simulation_time_ms"])
            for actor_key, actor in runtime["actor_snapshot"]["actors"].items():
                actor["presence"] = "present"
                actor["activity"] = "working"
                actor["conversation_phase"] = None
                actor["position"].update({
                    "floor_id": self.floor_id,
                    "uv": None,
                    "ground_xy": None,
                    "route": None,
                })
                actor["behavior"].update({
                    "next_event_due_ms": now_ms if actor_key == initiator_id else 10**9,
                    "active_event": None,
                    "activity_started_ms": now_ms,
                    "activity_until_ms": None,
                    "work_loop_elapsed_ms": 0,
                    "work_loop_count": 0,
                    "pending_home": False,
                    "pending_home_due_ms": None,
                })
            for actor in runtime["speech_snapshot"]["actors"].values():
                actor.update({
                    "last_activity": "working",
                    "speech_phase": "idle",
                    "greeting_due_ms": None,
                    "greeting_emitted": True,
                    "work_start_due_ms": None,
                    "work_start_emitted": True,
                    "solo_next_due_ms": None,
                    "pair_next_due_ms": None,
                })
            runtime = self.core.validate_runtime_snapshot(runtime)
            self.initial_runtime = copy.deepcopy(runtime)
            self.replay_steps = []
            self._live_spawn_due_ms = {}
            self._live_behavior_armed = set(runtime["actor_snapshot"]["actors"])
            # Keep the demo focused on one conversation; no unrelated seeded
            # recovery event should interrupt the talk route while it is being
            # inspected.  Restart/live-start turns this back on.
            self._behavior_arming_enabled = False
            self._talk_demo_session_id = None
            self._talk_demo_initiator_id = initiator_id
            self._effects_demo_ids = set()
            self._wander_demo_actor_id = None
            self._critical_demo_actor_id = None
            self._demo_kind = "talk"
            self._demo_complete = False
            self._reset_loop(runtime)
            chooser = self.core.actor_simulation.choose_behavior_event
            original_mode_request = self.core.speech_scheduler._mode_request

            requested_mode = (
                str(mode).strip().casefold() if mode is not None else None
            )
            if requested_mode is not None and requested_mode not in {
                "self_talk", "ceo_front", "seated_host", "standing_pair",
            }:
                raise ValueError(
                    "mode must be self_talk, ceo_front, seated_host or standing_pair"
                )

            def forced_mode_request(snapshot, employee_key, *, counter):
                if str(employee_key) != initiator_id or requested_mode is None:
                    return original_mode_request(snapshot, employee_key, counter=counter)
                if requested_mode == "self_talk":
                    return {
                        "kind": "solo",
                        "initiator_id": initiator_id,
                        "participants": [initiator_id],
                        "mode": "self_talk",
                        # ``None`` selects the authored general self-talk pool.
                        # ``solo`` is a scheduler priority label, not a
                        # dialogue-catalog category, and would yield no plan.
                        "category": None,
                        "dialogue_categories": [],
                        "available_modes": ["self_talk"],
                    }
                candidates_for_mode = self.core.speech_scheduler._mode_requests(
                    snapshot,
                    employee_key,
                    counter=counter,
                )
                for candidate in candidates_for_mode:
                    if candidate.get("mode") != requested_mode:
                        continue
                    if partner_id is None or candidate.get("partner_id") == partner_id:
                        return candidate
                return None

            def forced_talk(employee_key, *args, **kwargs):
                simulation_time = kwargs.get("simulation_time_ms")
                if simulation_time is None and args:
                    simulation_time = args[0]
                if (
                    str(employee_key) == initiator_id
                    and simulation_time is not None
                    and int(simulation_time) == now_ms
                ):
                    return "talk"
                return chooser(employee_key, *args, **kwargs)

            self.core.actor_simulation.choose_behavior_event = forced_talk
            self.core.speech_scheduler._mode_request = forced_mode_request
            try:
                result = self.tick(
                    60,
                    autopilot=False,
                    note=f"talk demo: {initiator_id} (live advances route and bubbles)",
                    include_runtime=include_runtime,
                    renderer=renderer,
                )
                self._talk_demo_session_id = next(
                    (
                        str(event.get("session_id"))
                        for event in result.get("events", [])
                        if event.get("type") == "talk_session_accepted"
                        and event.get("session_id")
                    ),
                    None,
                )
                result["demo_session_id"] = self._talk_demo_session_id
                result["demo_complete"] = False
                return result
            finally:
                self.core.actor_simulation.choose_behavior_event = chooser
                self.core.speech_scheduler._mode_request = original_mode_request

    def demo_effects(
        self,
        *,
        floor_id: str | None = None,
        dialogue_locale: str | None = None,
        dialogue_seed: str | int | None = None,
        include_runtime: bool = True,
        renderer: str = "raster",
    ) -> dict[str, Any]:
        """Start a deterministic HumanBall + VFX review side by side."""
        with self.lock:
            self._select_floor(floor_id)
            if dialogue_locale is not None:
                self.dialogue_locale = str(dialogue_locale).strip().lower() or "en"
                if self.dialogue_locale not in {"en", "th"}:
                    raise ValueError("dialogue_locale must be en or th")
            if dialogue_seed is not None:
                self.dialogue_seed = dialogue_seed
            runtime = copy.deepcopy(self.base_runtime)
            actor_ids = sorted(runtime["actor_snapshot"]["actors"])
            candidates = [
                actor_key
                for actor_key in actor_ids
                if runtime["actor_snapshot"]["actors"][actor_key]
                .get("assignment", {})
                .get("workstation_id")
                != "ceo"
            ]
            if len(candidates) < 2:
                raise CentralGameCoreError(f"{self.floor_id} needs two employee actors for effects demo")
            forced = {
                candidates[0]: "popup",
                candidates[1]: "background_effect",
            }
            now_ms = int(runtime["actor_snapshot"]["clock"]["simulation_time_ms"])
            for actor_key, actor in runtime["actor_snapshot"]["actors"].items():
                actor["presence"] = "present"
                actor["activity"] = "working"
                actor["conversation_phase"] = None
                actor["position"].update({
                    "floor_id": self.floor_id,
                    "uv": None,
                    "ground_xy": None,
                    "route": None,
                })
                actor["behavior"].update({
                    "next_event_due_ms": now_ms if actor_key in forced else 10**9,
                    "active_event": None,
                    "activity_started_ms": now_ms,
                    "activity_until_ms": None,
                    "work_loop_elapsed_ms": 0,
                    "work_loop_count": 0,
                    "pending_home": False,
                    "pending_home_due_ms": None,
                })
            for actor in runtime["speech_snapshot"]["actors"].values():
                actor.update({
                    "last_activity": "working",
                    "speech_phase": "idle",
                    "greeting_due_ms": None,
                    "greeting_emitted": True,
                    "work_start_due_ms": None,
                    "work_start_emitted": True,
                    "solo_next_due_ms": None,
                    "pair_next_due_ms": None,
                })
            runtime = self.core.validate_runtime_snapshot(runtime)
            self.initial_runtime = copy.deepcopy(runtime)
            self.replay_steps = []
            self._live_spawn_due_ms = {}
            self._live_behavior_armed = set(runtime["actor_snapshot"]["actors"])
            self._behavior_arming_enabled = False
            self._talk_demo_session_id = None
            self._talk_demo_initiator_id = None
            self._effects_demo_ids = set(forced)
            self._wander_demo_actor_id = None
            self._critical_demo_actor_id = None
            self._demo_kind = "effects"
            self._demo_complete = False
            self._reset_loop(runtime)
            chooser = self.core.actor_simulation.choose_behavior_event

            def forced_effect(employee_key, *args, **kwargs):
                simulation_time = kwargs.get("simulation_time_ms")
                if simulation_time is None and args:
                    simulation_time = args[0]
                if (
                    str(employee_key) in forced
                    and simulation_time is not None
                    and int(simulation_time) == now_ms
                ):
                    return forced[str(employee_key)]
                return chooser(employee_key, *args, **kwargs)

            self.core.actor_simulation.choose_behavior_event = forced_effect
            try:
                result = self.tick(
                    60,
                    autopilot=False,
                    note="effects demo: HumanBall + VFX (live advances channels)",
                    include_runtime=include_runtime,
                    renderer=renderer,
                )
                result["demo_complete"] = False
                return result
            finally:
                self.core.actor_simulation.choose_behavior_event = chooser

    def demo_wander(
        self,
        employee_id: str | None = None,
        *,
        floor_id: str | None = None,
        include_runtime: bool = True,
        renderer: str = "raster",
    ) -> dict[str, Any]:
        """Start one deterministic outbound/return wander route for review."""
        with self.lock:
            self._select_floor(floor_id)
            runtime = copy.deepcopy(self.base_runtime)
            actor_ids = sorted(runtime["actor_snapshot"]["actors"])
            candidates = [
                actor_key for actor_key in actor_ids
                if runtime["actor_snapshot"]["actors"][actor_key]
                .get("assignment", {}).get("workstation_id") != "ceo"
            ]
            if not candidates:
                raise CentralGameCoreError(f"{self.floor_id} has no employee actor for wander demo")
            target_id = str(employee_id) if employee_id in candidates else candidates[0]
            now_ms = int(runtime["actor_snapshot"]["clock"]["simulation_time_ms"])
            for actor_key, actor in runtime["actor_snapshot"]["actors"].items():
                actor["presence"] = "present"
                actor["activity"] = "working"
                actor["conversation_phase"] = None
                actor["position"].update({
                    "floor_id": self.floor_id,
                    "uv": None,
                    "ground_xy": None,
                    "route": None,
                })
                actor["behavior"].update({
                    "next_event_due_ms": now_ms if actor_key == target_id else 10**9,
                    "active_event": None,
                    "activity_started_ms": now_ms,
                    "activity_until_ms": None,
                    "work_loop_elapsed_ms": 0,
                    "work_loop_count": 0,
                    "pending_home": False,
                    "pending_home_due_ms": None,
                })
            for actor in runtime["speech_snapshot"]["actors"].values():
                actor.update({
                    "last_activity": "working",
                    "speech_phase": "idle",
                    "greeting_due_ms": None,
                    "greeting_emitted": True,
                    "work_start_due_ms": None,
                    "work_start_emitted": True,
                    "solo_next_due_ms": None,
                    "pair_next_due_ms": None,
                })
            runtime = self.core.validate_runtime_snapshot(runtime)
            self.initial_runtime = copy.deepcopy(runtime)
            self.replay_steps = []
            self._live_spawn_due_ms = {}
            self._live_behavior_armed = set(runtime["actor_snapshot"]["actors"])
            self._behavior_arming_enabled = False
            self._talk_demo_session_id = None
            self._talk_demo_initiator_id = None
            self._effects_demo_ids = set()
            self._wander_demo_actor_id = target_id
            self._critical_demo_actor_id = None
            self._demo_kind = "wander"
            self._demo_complete = False
            self._reset_loop(runtime)
            chooser = self.core.actor_simulation.choose_behavior_event

            def forced_wander(employee_key, *args, **kwargs):
                simulation_time = kwargs.get("simulation_time_ms")
                if simulation_time is None and args:
                    simulation_time = args[0]
                if (
                    str(employee_key) == target_id
                    and simulation_time is not None
                    and int(simulation_time) == now_ms
                ):
                    return "wander"
                return chooser(employee_key, *args, **kwargs)

            self.core.actor_simulation.choose_behavior_event = forced_wander
            try:
                result = self.tick(
                    60,
                    autopilot=False,
                    note=f"wander demo: {target_id} (live advances outbound and return route)",
                    include_runtime=include_runtime,
                    renderer=renderer,
                )
                result["demo_employee_id"] = target_id
                return result
            finally:
                self.core.actor_simulation.choose_behavior_event = chooser

    @staticmethod
    def _image_data_url(image: Any, *, compact: bool = False) -> str:
        output = BytesIO()
        if compact:
            # A high-quality WebP preview keeps the authored composition while
            # cutting the live frame to roughly half the PNG transfer. Faster
            # encoding and a smaller response leave the browser enough
            # headroom for a continuous preview; full save/replay payloads
            # remain lossless PNG.
            try:
                image.convert("RGB").save(output, format="WEBP", quality=80, method=0)
                mime = "image/webp"
            except (OSError, ValueError):
                image.convert("RGBA").save(output, format="PNG", optimize=False)
                mime = "image/png"
        else:
            image.convert("RGBA").save(output, format="PNG", optimize=False)
            mime = "image/png"
        encoded = base64.b64encode(output.getvalue()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    @staticmethod
    def _review_event(event: dict[str, Any]) -> dict[str, Any]:
        """Keep live event payloads useful without shipping full route plans."""
        common = (
            "source", "event_index", "timestamp_ms", "employee_id", "type",
            "session_id", "behavior", "activity", "phase", "mode", "role",
            "partner_id", "category", "kind", "reason", "participants",
            "emotion", "emotion_roll", "effect_milli", "stamina_milli", "route_committed",
            "talk_start_at_ms", "talk_end_at_ms", "return_start_at_ms",
            "assignment_retained", "work_loop_completed",
        )
        compact = {
            key: event[key]
            for key in common
            if key in event
        }
        if event.get("type") == "actor_route_sample":
            for key in (
                "phase", "ground_xy", "current_uv", "direction", "raw_direction",
                "progress_t", "visibility_alpha", "route_elapsed_ms",
                "route_duration_ms", "render_owner", "action", "subaction",
            ):
                if key in event:
                    compact[key] = event[key]
        if event.get("type") == "speech_session_started":
            dialogue = event.get("dialogue")
            if not isinstance(dialogue, dict):
                plan = event.get("conversation_plan")
                if isinstance(plan, dict):
                    dialogue = plan.get("dialogue")
            if isinstance(dialogue, dict):
                lines = []
                for line in dialogue.get("speaker_lines", []):
                    if not isinstance(line, dict):
                        continue
                    lines.append({
                        key: line[key]
                        for key in ("employee_id", "dialogue_id", "category", "text", "locale")
                        if key in line
                    })
                if lines:
                    compact["dialogue_lines"] = lines
            schedule = event.get("bubble_schedule")
            if isinstance(schedule, list):
                compact["bubble_ids"] = [
                    item.get("preferred_bubble_id")
                    for item in schedule
                    if isinstance(item, dict) and item.get("preferred_bubble_id")
                ]
            for key in ("numeric_effect_policy", "stamina_effect_milli", "score_delta", "bubble_selection_policy"):
                if key in event:
                    compact[key] = event[key]
            for key in ("bubble_start_ms", "fade_end_ms", "movement_arrival_ms"):
                if key in event:
                    compact[key] = event[key]
        return compact

    @classmethod
    def _compact_events(cls, events: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if not events:
            return []
        latest_routes: dict[str, dict[str, Any]] = {}
        kept: list[dict[str, Any]] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            compact = cls._review_event(event)
            if event.get("type") == "actor_route_sample":
                employee_id = str(event.get("employee_id") or "<actor>")
                latest_routes[employee_id] = compact
            else:
                kept.append(compact)
        kept.extend(latest_routes.values())
        return sorted(
            kept,
            key=lambda event: (
                int(event.get("timestamp_ms", 0)),
                str(event.get("source", "")),
                int(event.get("event_index", 0)),
            ),
        )

    def _suppress_demo_routine_speech(self, frame: dict[str, Any]) -> None:
        """Keep review demos focused on their authored event, not timer chatter.

        Returning a talk visitor changes its activity back to ``working`` in
        the same Central slice.  The speech lane quite correctly treats that
        as a fresh work-start opportunity, but that unrelated bubble would
        obscure the talk return the dashboard is meant to review.  Remove only
        those newly-created routine sessions from the review host snapshot;
        production Central behavior is unchanged.
        """
        if self._demo_kind != "talk" or not self._talk_demo_session_id:
            return
        speech_events = frame.get("speech_events", [])
        routine_ids = {
            str(event.get("session_id"))
            for event in speech_events
            if isinstance(event, dict)
            and event.get("type") == "speech_session_started"
            and event.get("session_id")
            and str(event.get("session_id")) != self._talk_demo_session_id
        }
        if not routine_ids:
            return
        runtime = frame.get("runtime_snapshot")
        speech_snapshot = runtime.get("speech_snapshot") if isinstance(runtime, dict) else None
        actor_snapshot = runtime.get("actor_snapshot") if isinstance(runtime, dict) else None
        if isinstance(speech_snapshot, dict):
            for key in ("active_sessions", "completed_sessions"):
                sessions = speech_snapshot.get(key)
                if isinstance(sessions, dict):
                    for session_id in routine_ids:
                        sessions.pop(session_id, None)
            lanes = speech_snapshot.get("lanes")
            if isinstance(lanes, dict):
                for lane in lanes.values():
                    if not isinstance(lane, dict):
                        continue
                    if str(lane.get("active_session_id")) in routine_ids:
                        lane["active_session_id"] = None
                        lane["active_until_ms"] = None
                    if str(lane.get("last_completed_session_id")) in routine_ids:
                        lane["last_completed_session_id"] = None
                    queued = lane.get("queued_session_ids")
                    if isinstance(queued, list):
                        lane["queued_session_ids"] = [
                            session_id
                            for session_id in queued
                            if str(session_id) not in routine_ids
                        ]
            speech_actors = speech_snapshot.get("actors", {})
            actor_rows = actor_snapshot.get("actors", {}) if isinstance(actor_snapshot, dict) else {}
            if isinstance(speech_actors, dict):
                for employee_id, speech_actor in speech_actors.items():
                    if not isinstance(speech_actor, dict):
                        continue
                    if str(speech_actor.get("last_session_id")) not in routine_ids:
                        continue
                    actor_row = actor_rows.get(employee_id, {}) if isinstance(actor_rows, dict) else {}
                    speech_actor.update({
                        "speech_phase": "idle",
                        "last_session_id": None,
                        "work_start_due_ms": None,
                        "work_start_emitted": True,
                        "solo_next_due_ms": None,
                        "pair_next_due_ms": None,
                        "solo_pending": False,
                        "pair_pending": False,
                        "last_activity": actor_row.get("activity", "working"),
                    })
        for key in ("events", "speech_events"):
            events = frame.get(key)
            if isinstance(events, list):
                frame[key] = [
                    event
                    for event in events
                    if not isinstance(event, dict)
                    or str(event.get("session_id")) not in routine_ids
                ]
        redraw = self.adapter.loop.render_current()
        frame["image"] = redraw["image"]
        frame["presentation"] = redraw["presentation"]
        frame["runtime_snapshot"] = redraw["runtime_snapshot"]

    def _talk_demo_has_reached_workseat(self, frame: dict[str, Any]) -> bool:
        """Return true only after every talk participant owns a normal-work pose.

        ``talk_returned`` is emitted when an actor reaches the WorkSeat
        transition gate, before the 240ms visual ``seat_entry`` bridge has
        completed.  The review host must not pause its demo at that seam or it
        presents a seated-looking actor without the canonical
        ``work/normal_work`` pose.
        """
        if self._talk_demo_session_id is None or self._talk_demo_initiator_id is None:
            return False
        runtime = frame.get("runtime_snapshot")
        if not isinstance(runtime, dict):
            return False
        speech = runtime.get("speech_snapshot")
        actor_snapshot = runtime.get("actor_snapshot")
        if not isinstance(speech, dict) or not isinstance(actor_snapshot, dict):
            return False
        completed_sessions = speech.get("completed_sessions")
        session = (
            completed_sessions.get(self._talk_demo_session_id)
            if isinstance(completed_sessions, dict)
            else None
        )
        participants = session.get("participants") if isinstance(session, dict) else None
        if not isinstance(participants, list) or not participants:
            participants = [self._talk_demo_initiator_id]
        actors = actor_snapshot.get("actors")
        presentation_actors = frame.get("presentation", {}).get("actors")
        if not isinstance(actors, dict) or not isinstance(presentation_actors, dict):
            return False
        for employee_id in participants:
            actor = actors.get(employee_id)
            row = presentation_actors.get(employee_id)
            if not isinstance(actor, dict) or not isinstance(row, dict):
                return False
            position = actor.get("position") or {}
            if (
                actor.get("activity") != "working"
                or position.get("route") is not None
                or position.get("seat_transition") is not None
                or row.get("render_owner") != "work_seat"
                or row.get("action") != "work"
                or row.get("subaction") != "normal_work"
                or row.get("presentation_transition") is not None
            ):
                return False
        return True

    @staticmethod
    def _actor_rows(frame: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        runtime = frame["runtime_snapshot"]
        runtime_actors = runtime["actor_snapshot"]["actors"]
        speech_snapshot = runtime.get("speech_snapshot") or {}
        queued_by_actor: dict[str, dict[str, Any]] = {}
        for lane in (speech_snapshot.get("lanes") or {}).values():
            if not isinstance(lane, dict):
                continue
            for position, request in enumerate(lane.get("queued_requests") or [], start=1):
                if not isinstance(request, dict):
                    continue
                employee_id = request.get("initiator_id")
                if isinstance(employee_id, str):
                    queued_by_actor[employee_id] = {
                        "position": position,
                        "request": request,
                    }
        for employee_id, row in frame["presentation"].get("actors", {}).items():
            stamina = row.get("stamina") or {}
            channels = row.get("channels") or {}
            runtime_actor = runtime_actors.get(employee_id, {})
            behavior = runtime_actor.get("behavior") or {}
            talk = behavior.get("talk") or {}
            position = runtime_actor.get("position") or {}
            route = position.get("route") or {}
            queued = queued_by_actor.get(employee_id) or {}
            queued_request = queued.get("request") or {}
            overlay = None
            for channel_name in ("vfx", "humanball", "conversation"):
                channel = channels.get(channel_name)
                if not isinstance(channel, dict):
                    continue
                asset_id = channel.get("asset_id")
                overlay = (
                    f"{channel_name}:{asset_id}"
                    if isinstance(asset_id, str) and asset_id
                    else channel_name
                )
                break
            channel_rows = {
                channel_name: {
                    key: channel[key]
                    for key in (
                        "asset_id", "effect_id", "humanball_id", "effect_frame_index",
                        "humanball_frame_index", "effect_frame_count", "humanball_frame_count",
                        "effect_frame_ms", "humanball_frame_ms",
                    )
                    if key in channel
                }
                for channel_name, channel in channels.items()
                if isinstance(channel, dict)
            }
            rows.append({
                "employee_id": employee_id,
                "character_id": row.get("character_id"),
                "activity": row.get("activity"),
                "presence": row.get("presence"),
                "action": row.get("action"),
                "subaction": row.get("subaction"),
                "direction": row.get("direction"),
                "resolved_action": row.get("resolved_action"),
                "resolved_direction": row.get("resolved_direction"),
                "resolved_subaction": row.get("resolved_subaction"),
                "workstation_id": row.get("workstation_id"),
                "render_owner": row.get("render_owner"),
                "visible": row.get("visible"),
                "pc_frame_index": row.get("pc_frame_index"),
                "pc_frame_count": row.get("pc_frame_count"),
                "pc_frame_ms": row.get("pc_frame_ms"),
                "presentation_phase": row.get("presentation_phase"),
                "route_phase": row.get("route_phase") or route.get("phase"),
                "route_elapsed_ms": row.get("route_elapsed_ms", route.get("elapsed_ms")),
                "route_duration_ms": row.get("route_duration_ms", route.get("duration_ms")),
                "ground_xy": row.get("ground_xy"),
                "current_uv": row.get("current_uv"),
                "presentation_transition": row.get("presentation_transition"),
                "cumulative_distance_px": row.get("cumulative_distance_px", 0),
                "frame_index": row.get("frame_index"),
                "character_frame_index": row.get("character_frame_index"),
                "character_frame_count": row.get("character_frame_count"),
                "character_frame_ms": row.get("character_frame_ms"),
                "overlay": overlay,
                "channels": channel_rows,
                "dialogue_visible": bool(row.get("dialogue_visible")),
                "dialogue_text": row.get("dialogue_text"),
                "dialogue_id": row.get("dialogue_id"),
                "dialogue_line_index": row.get("dialogue_line_index"),
                "dialogue_locale": row.get("dialogue_locale"),
                "dialogue_bubble_id": row.get("dialogue_bubble_id"),
                "dialogue_opacity": row.get("dialogue_opacity"),
                "dialogue_phase": row.get("dialogue_phase"),
                "speech_mode": row.get("speech_mode"),
                "speech_category": row.get("speech_category"),
                "speech_session_id": row.get("speech_session_id"),
                "speech_queue_position": queued.get("position"),
                "speech_queue_request_id": queued_request.get("request_id"),
                "speech_queue_kind": queued_request.get("kind"),
                "speech_queue_category": queued_request.get("category"),
                "speech_queue_due_ms": queued_request.get("due_ms"),
                "speech_queue_external": (
                    bool(queued_request.get("external", False))
                    if queued_request else False
                ),
                "talk_role": talk.get("role"),
                "talk_partner_id": talk.get("partner_id"),
                "stamina": round(int(stamina.get("current_milli", 0)) / 1000, 3),
                "stamina_milli": int(stamina.get("current_milli", 0)),
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

    def _dialogue_coverage(self, runtime: dict[str, Any]) -> dict[str, Any]:
        """Expose authored-line usage without making the browser inspect bags."""
        locale = str(self.dialogue_locale).strip().casefold().split("-", 1)[0]
        speech = runtime.get("speech_snapshot", {}) if isinstance(runtime, dict) else {}
        bags = speech.get("dialogue_bags", {}) if isinstance(speech, dict) else {}
        categories = tuple(self.core.speech_scheduler.IN_WORK_CATEGORIES)
        rows: dict[str, dict[str, Any]] = {}
        for category in categories:
            cache_key = (locale, category)
            pool_count = self._dialogue_pool_count_cache.get(cache_key)
            if pool_count is None:
                pool_count = len(self.core.list_dialogue_lines(
                    locale=locale,
                    category=category,
                    usage_scope="office",
                    enabled_only=True,
                ))
                self._dialogue_pool_count_cache[cache_key] = pool_count
            bag = bags.get(f"{locale}|{category}", {}) if isinstance(bags, dict) else {}
            remaining = bag.get("remaining", []) if isinstance(bag, dict) else []
            rows[category] = {
                "pool_count": int(pool_count),
                "used_count": int(bag.get("used_count", 0)) if isinstance(bag, dict) else 0,
                "generation": int(bag.get("generation", 0)) if isinstance(bag, dict) else 0,
                "remaining_count": len(remaining) if isinstance(remaining, list) else int(pool_count),
            }
        return {
            "locale": locale,
            "categories": list(categories),
            "selection_policy": "persistent_shuffle_bag_no_repeat_then_refill",
            "bubble_selection": "smallest_allowed_fit",
            "allowed_bubbles": ["BB1", "BB2", "BB3", "BB4", "BB6"],
            "in_work": rows,
        }

    def frame_payload(
        self,
        frame: dict[str, Any],
        *,
        note: str | None = None,
        include_runtime: bool = True,
        renderer: str = "raster",
    ) -> dict[str, Any]:
        renderer_key = self._validate_renderer(renderer)
        runtime = frame["runtime_snapshot"]
        actor_clock = runtime["actor_snapshot"]["clock"]["simulation_time_ms"]
        compact_events = not include_runtime
        metrics = copy.deepcopy(self._last_tick_metrics)
        render_state = None
        image_data_url = None
        if renderer_key == "canvas":
            render_state = self.render_state_projector.project(
                runtime,
                floor_id=self.floor_id,
                sequence=int(self.adapter.frame_count),
                events=frame.get("events", []),
                presentation=frame["presentation"],
            )
            metrics["encode_ms"] = 0.0
        else:
            encode_started = time.perf_counter()
            image_data_url = self._image_data_url(
                self._raster_image(frame),
                compact=not include_runtime,
            )
            metrics["encode_ms"] = round((time.perf_counter() - encode_started) * 1000.0, 3)
        payload = {
            "renderer": renderer_key,
            "floor_id": self.floor_id,
            "frame_count": self.adapter.frame_count,
            "clock_ms": actor_clock,
            "frame_sequence": int(self.adapter.frame_count),
            "metrics": metrics,
            "actors": self._actor_rows(frame),
            "events": (
                self._compact_events(frame.get("events"))
                if compact_events else frame.get("events", [])
            ),
            "actor_events": (
                self._compact_events(frame.get("actor_events"))
                if compact_events else frame.get("actor_events", [])
            ),
            "speech_events": (
                self._compact_events(frame.get("speech_events"))
                if compact_events else frame.get("speech_events", [])
            ),
            "note": note,
            "demo_session_id": self._talk_demo_session_id,
            "demo_employee_id": (
                self._talk_demo_initiator_id
                or self._wander_demo_actor_id
                or self._critical_demo_actor_id
            ),
            "demo_kind": self._demo_kind,
            "demo_complete": self._demo_complete,
            "dialogue_coverage": self._dialogue_coverage(runtime),
        }
        if renderer_key == "canvas":
            payload["render_state"] = render_state
        else:
            payload["image_data_url"] = image_data_url
        # Save/load/replay callers need the complete JSON-safe state. Live
        # frames do not: sending the composed snapshot on every 120ms tick
        # made the browser transfer and parse nearly 2MB per frame.
        if include_runtime:
            payload.update({
                "presentation": frame["presentation"],
                "runtime_snapshot": runtime,
                "snapshot_json": self.core.serialize_runtime_snapshot(runtime),
                "replay_steps": copy.deepcopy(self.replay_steps),
            })
        return payload

    def current(
        self,
        *,
        note: str | None = None,
        include_runtime: bool = True,
        renderer: str = "raster",
    ) -> dict[str, Any]:
        with self.lock:
            return self.frame_payload(
                self.adapter.last_frame or self.adapter.render_current(),
                note=note,
                include_runtime=include_runtime,
                renderer=renderer,
            )

    def tick(
        self,
        elapsed_ms: int,
        *,
        actor_commands: list[dict[str, Any]] | None = None,
        speech_commands: list[dict[str, Any]] | None = None,
        autopilot: bool = False,
        note: str | None = None,
        include_runtime: bool = True,
        dialogue_locale: str | None = None,
        dialogue_seed: str | int | None = None,
        renderer: str = "raster",
    ) -> dict[str, Any]:
        with self.lock:
            tick_started = time.perf_counter()
            if dialogue_locale is not None:
                locale = str(dialogue_locale).strip().lower()
                if locale not in {"en", "th"}:
                    raise ValueError("dialogue_locale must be en or th")
                self.dialogue_locale = locale
                self.adapter.loop.dialogue_locale = locale
            if dialogue_seed is not None:
                self.dialogue_seed = dialogue_seed
                self.adapter.loop.dialogue_seed = dialogue_seed
            commands = copy.deepcopy(actor_commands or [])
            if autopilot:
                self._arm_live_behavior_timers()
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
            render_started = time.perf_counter()
            frame = self.adapter.tick(
                elapsed_ms,
                actor_commands=commands,
                speech_commands=speech_commands or [],
            )
            render_ms = (time.perf_counter() - render_started) * 1000.0
            self._suppress_demo_routine_speech(frame)
            if self._talk_demo_has_reached_workseat(frame):
                self._demo_complete = True
            if self._effects_demo_ids:
                finished = {
                    str(event.get("employee_id"))
                    for event in frame.get("events", [])
                    if event.get("type") == "stamina_recovery"
                    and event.get("behavior") in {"popup", "background_effect"}
                }
                self._effects_demo_ids.difference_update(finished)
                if not self._effects_demo_ids:
                    self._demo_complete = True
            if self._wander_demo_actor_id is not None and any(
                event.get("type") == "wander_returned"
                and str(event.get("employee_id")) == self._wander_demo_actor_id
                for event in frame.get("events", [])
            ):
                self._demo_complete = True
            if self._critical_demo_actor_id is not None and any(
                event.get("type") == "portal_exited"
                and str(event.get("employee_id")) == self._critical_demo_actor_id
                for event in frame.get("events", [])
            ):
                self._demo_complete = True
            tick_compute_ms = (time.perf_counter() - tick_started) * 1000.0
            self._last_tick_metrics = {
                "tick_compute_ms": round(tick_compute_ms, 3),
                "render_ms": round(render_ms, 3),
                "encode_ms": None,
                "frame_sequence": int(self.adapter.frame_count),
            }
            self.replay_steps.append({
                "elapsed_ms": int(elapsed_ms),
                "actor_commands": copy.deepcopy(commands),
                "speech_commands": copy.deepcopy(speech_commands or []),
                "dialogue_locale": self.dialogue_locale,
                "dialogue_seed": self.dialogue_seed,
            })
            payload_started = time.perf_counter()
            payload = self.frame_payload(
                frame,
                note=note,
                include_runtime=include_runtime,
                renderer=renderer,
            )
            payload["metrics"]["payload_build_ms"] = round(
                (time.perf_counter() - payload_started) * 1000.0,
                3,
            )
            return payload

    def reset(
        self,
        *,
        floor_id: str | None = None,
        include_runtime: bool = True,
        renderer: str = "raster",
    ) -> dict[str, Any]:
        with self.lock:
            self._select_floor(floor_id)
            self._behavior_arming_enabled = True
            self._talk_demo_session_id = None
            self._talk_demo_initiator_id = None
            self._effects_demo_ids = set()
            self._wander_demo_actor_id = None
            self._critical_demo_actor_id = None
            self._demo_kind = None
            self._demo_complete = False
            self.initial_runtime = copy.deepcopy(self.base_runtime)
            self.replay_steps = []
            self._reset_loop()
            return self.current(
                note="reset",
                include_runtime=include_runtime,
                renderer=renderer,
            )

    def demo_critical(
        self,
        employee_id: str,
        *,
        floor_id: str | None = None,
        include_runtime: bool = True,
        renderer: str = "raster",
    ) -> dict[str, Any]:
        with self.lock:
            self._select_floor(floor_id)
            # Always build the critical scenario from the authoritative base
            # snapshot.  Using the currently displayed live frame can leave
            # the selected actor halfway through an inbound/outbound route;
            # changing only its stamina then violates the route/activity
            # contract and makes the button look stuck.
            runtime = copy.deepcopy(self.base_runtime)
            actor_ids = sorted(runtime["actor_snapshot"]["actors"])
            if not actor_ids:
                raise CentralGameCoreError(f"{self.floor_id} has no actors for critical demo")
            target_id = str(employee_id) if employee_id in actor_ids else actor_ids[0]
            now_ms = int(runtime["actor_snapshot"]["clock"]["simulation_time_ms"])
            for actor_key, actor in runtime["actor_snapshot"]["actors"].items():
                actor["presence"] = "present"
                actor["activity"] = "working"
                actor["conversation_phase"] = None
                actor["position"].update({
                    "floor_id": self.floor_id,
                    "uv": None,
                    "ground_xy": None,
                    "route": None,
                })
                actor["behavior"].update({
                    "next_event_due_ms": now_ms if actor_key == target_id else 10**9,
                    "active_event": None,
                    "activity_started_ms": now_ms,
                    "activity_until_ms": None,
                    "work_loop_elapsed_ms": 0,
                    "work_loop_count": 0,
                    "pending_home": False,
                    "pending_home_due_ms": None,
                })
            for speech_actor in runtime["speech_snapshot"]["actors"].values():
                speech_actor.update({
                    "last_activity": "working",
                    "speech_phase": "idle",
                    "greeting_due_ms": None,
                    "greeting_emitted": True,
                    "work_start_due_ms": None,
                    "work_start_emitted": True,
                    "solo_next_due_ms": None,
                    "pair_next_due_ms": None,
                })
            actor = runtime["actor_snapshot"]["actors"][target_id]
            actor["stamina"].update({
                "current_milli": 5000,
                "threshold_band": "critical",
                "drain_remainder": 0,
            })
            actor["behavior"].update({
                "next_event_due_ms": now_ms,
                "active_event": None,
                "activity_started_ms": now_ms,
                "activity_until_ms": None,
                "work_loop_elapsed_ms": 0,
                "work_loop_count": 0,
                "pending_home": False,
                "pending_home_due_ms": None,
            })
            runtime = self.core.validate_runtime_snapshot(runtime)
            self.initial_runtime = copy.deepcopy(runtime)
            self.replay_steps = []
            self._live_spawn_due_ms = {}
            self._live_behavior_armed = set(runtime["actor_snapshot"]["actors"])
            # Keep this demo focused on the critical actor.  The actor itself
            # still follows the real work-loop boundary, seat-exit tween and
            # portal route; unrelated recovery timers stay disabled.
            self._behavior_arming_enabled = False
            self._talk_demo_session_id = None
            self._talk_demo_initiator_id = None
            self._effects_demo_ids = set()
            self._wander_demo_actor_id = None
            self._critical_demo_actor_id = target_id
            self._demo_kind = "critical"
            self._demo_complete = False
            self._reset_loop(runtime)
            # Start at the first 60ms boundary so the queue is immediately
            # visible, then let the web host continue automatically.
            result = self.tick(
                60,
                autopilot=False,
                note=f"critical demo: {target_id} (finishes work loop then returns home)",
                include_runtime=include_runtime,
                renderer=renderer,
            )
            result["demo_employee_id"] = target_id
            return result

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

    def load(self, runtime: dict[str, Any], *, renderer: str = "raster") -> dict[str, Any]:
        with self.lock:
            validated = self.core.deserialize_runtime_snapshot(runtime)
            assignment_floors = {
                str(actor.get("assignment", {}).get("floor_id"))
                for actor in validated.get("actor_snapshot", {}).get("actors", {}).values()
                if isinstance(actor, dict) and actor.get("assignment", {}).get("floor_id")
            }
            if len(assignment_floors) == 1:
                self._select_floor(next(iter(assignment_floors)))
            self._behavior_arming_enabled = True
            self._talk_demo_session_id = None
            self._talk_demo_initiator_id = None
            self._effects_demo_ids = set()
            self._wander_demo_actor_id = None
            self._critical_demo_actor_id = None
            self._demo_kind = None
            self._demo_complete = False
            self.initial_runtime = copy.deepcopy(validated)
            self.replay_steps = []
            self._reset_loop(validated)
            return self.current(note="loaded snapshot", renderer=renderer)

    def replay(self, package: dict[str, Any], *, renderer: str = "raster") -> dict[str, Any]:
        with self.lock:
            initial = package.get("initial_runtime_snapshot") if isinstance(package, dict) else None
            assignment_floors = {
                str(actor.get("assignment", {}).get("floor_id"))
                for actor in (initial or {}).get("actor_snapshot", {}).get("actors", {}).values()
                if isinstance(actor, dict) and actor.get("assignment", {}).get("floor_id")
            }
            if len(assignment_floors) == 1:
                self._select_floor(next(iter(assignment_floors)))
            result = self.core.replay_runtime_package(package)
            self._behavior_arming_enabled = True
            self._talk_demo_session_id = None
            self._talk_demo_initiator_id = None
            self._effects_demo_ids = set()
            self._wander_demo_actor_id = None
            self._critical_demo_actor_id = None
            self._demo_kind = None
            self._demo_complete = False
            self.replay_steps = copy.deepcopy(package.get("steps", []))
            self._reset_loop(result["snapshot"])
            frame = self.adapter.last_frame or self.adapter.render_current()
            payload = self.frame_payload(
                frame,
                note="deterministic replay complete",
                renderer=renderer,
            )
            payload["replay_trace"] = result.get("trace", [])
            return payload


STATE = ReviewState()


class ReviewHandler(BaseHTTPRequestHandler):
    server_version = "GDSRuntimeReview/1.0"
    protocol_version = "HTTP/1.1"

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
        # The review HTML is also useful when opened directly from the project
        # folder in a normal browser (file://).  Keep the API bound to
        # localhost, but allow that local file origin to call the review host.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(
        self,
        status: int,
        body: bytes,
        *,
        content_type: str,
        cache_control: str = "no-store",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _web_static_path(path: str) -> Path | None:
        """Resolve only the review page's explicit WEB assets.

        The review host is intentionally not a general-purpose file server.
        Canvas can request its generated manifest/bundle and its two modules;
        every other path remains an API/404 route.
        """
        decoded = unquote(path)
        if decoded in {
            "/runtime_render_manifest.json",
            "/runtime_canvas_renderer.js",
            "/runtime_render_client.js",
        }:
            relative = decoded.lstrip("/")
        elif decoded.startswith("/runtime_assets/"):
            relative = decoded.removeprefix("/runtime_assets/")
        else:
            return None
        if any(part in {"", ".", ".."} for part in Path(relative).parts):
            return None
        relative_path = (
            Path("runtime_assets") / Path(relative)
            if decoded.startswith("/runtime_assets/")
            else Path(relative)
        )
        candidate = (WEB_ROOT / relative_path).resolve()
        web_root = WEB_ROOT.resolve()
        if candidate != web_root and web_root not in candidate.parents:
            return None
        return candidate

    def _serve_web_static(self, path: str) -> bool:
        target = self._web_static_path(path)
        if target is None:
            return False
        if not target.is_file():
            self._send(404, {"error": "not found"})
            return True
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        cache_control = (
            "public, max-age=31536000, immutable"
            if WEB_ROOT.joinpath("runtime_assets") in target.parents
            else "no-store"
        )
        self._send_bytes(
            200,
            target.read_bytes(),
            content_type=content_type,
            cache_control=cache_control,
        )
        return True

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
            parsed = urlsplit(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            renderer = query.get("renderer", [None])[0]
            if path in {"/", "/index.html"}:
                self._send(200, HTML_PATH.read_text(encoding="utf-8"), content_type="text/html")
                return
            if self._serve_web_static(path):
                return
            if path == "/api/state":
                self._send(200, STATE.current(include_runtime=False, renderer=renderer or "raster"))
                return
            if path == "/api/floors":
                self._send(200, {
                    "api": API_VERSION,
                    "selected_floor_id": STATE.floor_id,
                    "floors": STATE.floors(),
                })
                return
            if path in {"/api/capabilities", "/api/manifest"}:
                self._send(200, STATE.capabilities())
                return
            if path == "/api/health":
                self._send(200, {
                    "ok": True,
                    "server": "gds-runtime-review",
                    "floor_id": STATE.floor_id,
                    "api": API_VERSION,
                    "floor_count": len(STATE.available_floors),
                })
                return
            if path == "/api/policy":
                policy = STATE.core.employee_metadata.stamina_policy()
                self._send(200, {
                    "floor_id": STATE.floor_id,
                    "normal_work_loop_ms": STATE.core.actor_simulation.WORK_LOOP_MS,
                    "critical_threshold": STATE.core.actor_simulation.CRITICAL_THRESHOLD_MILLI / 1000,
                    "emotion_effects": policy.get("emotion_effects", {}),
                    "home_policy": policy.get("home_policy", {}),
                })
                return
            self._send(404, {"error": "not found"})
        except Exception as exc:
            self._error(500, exc)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def do_POST(self) -> None:
        try:
            body = self._read_json()
            path = urlsplit(self.path).path
            renderer = body.get("renderer", "raster")
            if path == "/api/reset":
                self._send(200, STATE.reset(
                    floor_id=body.get("floor_id"),
                    include_runtime=not bool(body.get("compact", False)),
                    renderer=renderer,
                ))
            elif path == "/api/live-start":
                self._send(200, STATE.live_start(
                    floor_id=body.get("floor_id"),
                    include_runtime=not bool(body.get("compact", False)),
                    dialogue_locale=body.get("dialogue_locale"),
                    dialogue_seed=body.get("dialogue_seed"),
                    renderer=renderer,
                ))
            elif path == "/api/demo-full":
                self._send(200, STATE.full_demo(
                    floor_id=body.get("floor_id"),
                    include_runtime=not bool(body.get("compact", False)),
                    dialogue_locale=body.get("dialogue_locale"),
                    dialogue_seed=body.get("dialogue_seed"),
                    renderer=renderer,
                ))
            elif path == "/api/demo-talk":
                employee_id = body.get("employee_id")
                if employee_id is not None and not isinstance(employee_id, str):
                    raise ValueError("employee_id must be text when supplied")
                self._send(200, STATE.demo_talk(
                    employee_id,
                    floor_id=body.get("floor_id"),
                    mode=body.get("mode"),
                    partner_id=body.get("partner_id"),
                    dialogue_locale=body.get("dialogue_locale"),
                    dialogue_seed=body.get("dialogue_seed"),
                    include_runtime=not bool(body.get("compact", False)),
                    renderer=renderer,
                ))
            elif path == "/api/demo-effects":
                self._send(200, STATE.demo_effects(
                    floor_id=body.get("floor_id"),
                    dialogue_locale=body.get("dialogue_locale"),
                    dialogue_seed=body.get("dialogue_seed"),
                    include_runtime=not bool(body.get("compact", False)),
                    renderer=renderer,
                ))
            elif path == "/api/demo-wander":
                employee_id = body.get("employee_id")
                if employee_id is not None and not isinstance(employee_id, str):
                    raise ValueError("employee_id must be text when supplied")
                self._send(200, STATE.demo_wander(
                    employee_id,
                    floor_id=body.get("floor_id"),
                    include_runtime=not bool(body.get("compact", False)),
                    renderer=renderer,
                ))
            elif path == "/api/tick":
                elapsed_ms = body.get("elapsed_ms", 60)
                if isinstance(elapsed_ms, bool) or not isinstance(elapsed_ms, int) or elapsed_ms < 0:
                    raise ValueError("elapsed_ms must be a non-negative integer")
                self._send(200, STATE.tick(
                    elapsed_ms,
                    actor_commands=body.get("actor_commands"),
                    speech_commands=body.get("speech_commands"),
                    autopilot=bool(body.get("autopilot", False)),
                    include_runtime=not bool(body.get("compact", False)),
                    dialogue_locale=body.get("dialogue_locale"),
                    dialogue_seed=body.get("dialogue_seed"),
                    renderer=renderer,
                ))
            elif path == "/api/demo-critical":
                employee_id = body.get("employee_id")
                if not isinstance(employee_id, str) or not employee_id:
                    raise ValueError("employee_id is required")
                self._send(200, STATE.demo_critical(
                    employee_id,
                    floor_id=body.get("floor_id"),
                    include_runtime=not bool(body.get("compact", False)),
                    renderer=renderer,
                ))
            elif path == "/api/save":
                self._send(200, STATE.save())
            elif path == "/api/load":
                self._send(200, STATE.load(body.get("runtime_snapshot"), renderer=renderer))
            elif path == "/api/replay":
                self._send(200, STATE.replay(body, renderer=renderer))
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
