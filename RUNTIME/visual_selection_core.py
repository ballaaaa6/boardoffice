from __future__ import annotations

"""Deterministic, replayable selection for runtime visual channels."""

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from RUNTIME.asset_utils import file_sha256


class VisualSelectionError(ValueError):
    """Raised when a visual catalog or compact bag state is invalid."""


class VisualSelectionCore:
    """Own the canonical visual catalog and per-actor shuffle-bag algorithm."""

    PROFILE_ID = "gds.visual_catalog.v1"
    DEFAULT_HUMANBALL_POOL_SIZE = 44
    LEGACY_VFX_IDS = frozenset({
        "fire_original",
        "speed_wind",
        "idea_overclock",
        "coffee_energy",
        "sunshine_bloom",
        "heart_burst",
        "cherry_blossom_swirl",
        "thunder_cloud",
        "stock_crash",
        "low_battery_drain",
        "static_noise_field",
    })
    CHANNEL_TO_REGISTRY = {
        "vfx": ("CHARACTER/EFFECTS/gds_effects_v1.json", "effect_order", "gds_effect_registry_v1"),
        "humanball": (
            "CHARACTER/EFFECTS/humanball_v1.json",
            "humanball_order",
            "gds_humanball_registry_v1",
        ),
        "office_humanball": (
            "CHARACTER/EFFECTS/office_humanball_v1.json",
            "office_humanball_order",
            "gds_office_humanball_registry_v1",
        ),
    }
    CHANNEL_RECORD_KEYS = {
        "vfx": "effects",
        "humanball": "humanballs",
        "office_humanball": "office_humanballs",
    }

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self._registries: dict[str, dict[str, Any]] = {}
        self._ids: dict[str, tuple[str, ...]] = {}
        self._registry_hashes: dict[str, str] = {}
        for channel, (relative, order_key, expected_schema) in self.CHANNEL_TO_REGISTRY.items():
            path = self.root / relative
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise VisualSelectionError(f"visual registry cannot be loaded: {relative}") from exc
            if not isinstance(payload, dict) or payload.get("schema") != expected_schema:
                raise VisualSelectionError(f"visual registry schema is invalid: {relative}")
            ids = payload.get(order_key)
            if not isinstance(ids, list) or not ids:
                raise VisualSelectionError(f"{channel} registry order must be a non-empty list")
            if any(not isinstance(asset_id, str) or not asset_id for asset_id in ids):
                raise VisualSelectionError(f"{channel} registry IDs must be non-empty strings")
            if len(set(ids)) != len(ids):
                raise VisualSelectionError(f"{channel} registry must contain unique IDs")
            records_key = self.CHANNEL_RECORD_KEYS[channel]
            records = payload.get(records_key)
            if not isinstance(records, dict) or any(asset_id not in records for asset_id in ids):
                raise VisualSelectionError(f"{channel} registry order contains an unknown ID")
            self._registries[channel] = payload
            self._ids[channel] = tuple(ids)
            self._registry_hashes[channel] = file_sha256(path)

        # The automatic popup event keeps its existing ``humanball`` channel,
        # but its bag now contains the six locked canonical HumanBalls plus
        # the 38 approved office items.  Keep the office channel as a separate
        # explicit catalog as well so callers can still target that subset.
        canonical_ids = self._ids["humanball"]
        office_ids = self._ids["office_humanball"]
        self._ids["humanball"] = tuple((*canonical_ids, *office_ids))
        self._registry_hashes["humanball"] = hashlib.sha256(
            "\x1f".join(
                (
                    "mixed_default_popup_pool_v1",
                    self._registry_hashes["humanball"],
                    self._registry_hashes["office_humanball"],
                    ",".join(self._ids["humanball"]),
                )
            ).encode("utf-8")
        ).hexdigest()
        if len(self._ids["humanball"]) != self.DEFAULT_HUMANBALL_POOL_SIZE:
            raise VisualSelectionError(
                "default HumanBall popup pool must contain 44 unique IDs"
            )
        self._profile_hash = hashlib.sha256(
            "\x1f".join(
                [
                    self.PROFILE_ID,
                    *(
                        f"{channel}:{self._registry_hashes[channel]}:{','.join(self._ids[channel])}"
                        for channel in self.CHANNEL_TO_REGISTRY
                    ),
                ]
            ).encode("utf-8")
        ).hexdigest()
        self._catalog_profile = f"{self.PROFILE_ID}:{self._profile_hash}"

    @staticmethod
    def _stable_hash(*parts: Any) -> int:
        material = "\x1f".join(str(part) for part in parts).encode("utf-8")
        return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")

    @property
    def catalog_profile(self) -> str:
        return self._catalog_profile

    def catalog(self) -> dict[str, Any]:
        """Return a JSON-safe catalog derived from the canonical registries."""
        result: dict[str, Any] = {
            "profile_id": self.PROFILE_ID,
            "profile_hash": self._profile_hash,
            "catalog_profile": self._catalog_profile,
        }
        for channel in self.CHANNEL_TO_REGISTRY:
            result[channel] = {
                "ids": list(self._ids[channel]),
                "registry_schema": self.CHANNEL_TO_REGISTRY[channel][2],
                "registry_hash": self._registry_hashes[channel],
            }
        result["humanball"].update({
            "pool_mode": "canonical_plus_office",
            "pool_size": len(self._ids["humanball"]),
            "source_channels": ["humanball", "office_humanball"],
        })
        return result

    def _require_channel(self, channel: str) -> str:
        if channel not in self._ids:
            raise VisualSelectionError(f"unknown visual channel: {channel!r}")
        return channel

    def initial_channel_state(self, channel: str) -> dict[str, Any]:
        channel = self._require_channel(channel)
        return {
            "catalog_profile": self._catalog_profile,
            "generation": 0,
            "cursor": 0,
            "active_binding": None,
        }

    def migrate_channel_state(self, state: dict[str, Any], channel: str) -> dict[str, Any]:
        """Migrate a saved VFX bag after the additive catalog expansion.

        The old eleven VFX IDs remain in the new catalog, so an in-flight
        binding can safely remain visible.  The consumed bag cursor cannot be
        continued deterministically after the pool changes; restart only that
        channel's bag while preserving the rest of the actor snapshot.
        """
        channel = self._require_channel(channel)
        if not isinstance(state, dict) or state.get("catalog_profile") == self._catalog_profile:
            return state
        if channel != "vfx":
            return state
        old_profile = state.get("catalog_profile")
        if not isinstance(old_profile, str) or not old_profile.startswith(f"{self.PROFILE_ID}:"):
            return state
        generation = state.get("generation")
        cursor = state.get("cursor")
        if (
            isinstance(generation, bool)
            or not isinstance(generation, int)
            or generation < 0
            or isinstance(cursor, bool)
            or not isinstance(cursor, int)
            or cursor < 0
            or cursor > len(self.LEGACY_VFX_IDS)
        ):
            return state
        active = state.get("active_binding")
        if active is not None:
            if not isinstance(active, dict):
                return state
            asset_id = active.get("asset_id")
            if asset_id not in self.LEGACY_VFX_IDS or asset_id not in self._ids[channel]:
                return state
        migrated = self.initial_channel_state(channel)
        if active is not None:
            migrated["active_binding"] = copy.deepcopy(active)
        return migrated

    def validate_channel_state(self, state: dict[str, Any], channel: str) -> dict[str, Any]:
        """Validate and return an isolated compact channel state."""
        return self._validated_state(state, channel)

    def _validated_state(self, state: dict[str, Any], channel: str) -> dict[str, Any]:
        channel = self._require_channel(channel)
        if not isinstance(state, dict):
            raise VisualSelectionError("visual channel state must be an object")
        if state.get("catalog_profile") != self._catalog_profile:
            raise VisualSelectionError("visual channel catalog profile mismatch")
        generation = state.get("generation")
        cursor = state.get("cursor")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
            raise VisualSelectionError("visual channel generation must be a non-negative integer")
        if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
            raise VisualSelectionError("visual channel cursor must be a non-negative integer")
        if cursor > len(self._ids[channel]):
            raise VisualSelectionError("visual channel cursor exceeds bag length")
        active = state.get("active_binding")
        if active is not None:
            if not isinstance(active, dict) or active.get("channel") != channel:
                raise VisualSelectionError("visual channel active binding is invalid")
            if not isinstance(active.get("event_id"), str) or not active["event_id"]:
                raise VisualSelectionError("visual channel active binding event is invalid")
            if active.get("asset_id") not in self._ids[channel]:
                raise VisualSelectionError("visual channel active binding asset is invalid")
        return copy.deepcopy(state)

    def _permutation(
        self,
        *,
        channel: str,
        simulation_seed: str,
        employee_id: str,
        generation: int,
    ) -> list[str]:
        permutation = sorted(
            self._ids[channel],
            key=lambda asset_id: (
                self._stable_hash(
                    simulation_seed,
                    "visual-bag",
                    employee_id,
                    channel,
                    generation,
                    asset_id,
                ),
                asset_id,
            ),
        )
        if channel == "humanball" and generation > 0 and len(permutation) > 1:
            previous_permutation = sorted(
                self._ids[channel],
                key=lambda asset_id: (
                    self._stable_hash(
                        simulation_seed,
                        "visual-bag",
                        employee_id,
                        channel,
                        generation - 1,
                        asset_id,
                    ),
                    asset_id,
                ),
            )
            if permutation[0] == previous_permutation[-1]:
                # Keep the next generation a full permutation while preventing
                # an identical HumanBall at the boundary between bag cycles.
                permutation[0], permutation[1] = permutation[1], permutation[0]
        return permutation

    def select(
        self,
        state: dict[str, Any],
        *,
        channel: str,
        simulation_seed: str,
        employee_id: str,
        event_id: str,
        started_at_ms: int,
        ends_at_ms: int,
        bag_employee_id: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Consume one item and bind it to the event before rendering."""
        channel = self._require_channel(channel)
        if not isinstance(simulation_seed, str) or not simulation_seed:
            raise VisualSelectionError("simulation_seed must be a non-empty string")
        if not isinstance(employee_id, str) or not employee_id:
            raise VisualSelectionError("employee_id must be a non-empty string")
        bag_owner = employee_id if bag_employee_id is None else bag_employee_id
        if not isinstance(bag_owner, str) or not bag_owner:
            raise VisualSelectionError("bag_employee_id must be a non-empty string")
        if not isinstance(event_id, str) or not event_id:
            raise VisualSelectionError("event_id must be a non-empty string")
        for value, name in ((started_at_ms, "started_at_ms"), (ends_at_ms, "ends_at_ms")):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise VisualSelectionError(f"{name} must be a non-negative integer")
        if ends_at_ms < started_at_ms:
            raise VisualSelectionError("ends_at_ms must not precede started_at_ms")
        current = self._validated_state(state, channel)
        generation = int(current["generation"])
        cursor = int(current["cursor"])
        ids = self._ids[channel]
        if cursor == len(ids):
            generation += 1
            cursor = 0
        permutation = self._permutation(
            channel=channel,
            simulation_seed=simulation_seed,
            employee_id=bag_owner,
            generation=generation,
        )
        asset_id = permutation[cursor]
        cursor_after = cursor + 1
        binding = {
            "channel": channel,
            "asset_id": asset_id,
            "event_id": event_id,
            "employee_id": employee_id,
            "started_at_ms": started_at_ms,
            "ends_at_ms": ends_at_ms,
            "generation": generation,
            "cursor_after": cursor_after,
        }
        current.update({
            "generation": generation,
            "cursor": cursor_after,
            "active_binding": binding,
        })
        return current, copy.deepcopy(binding)

    def clear_active(
        self,
        state: dict[str, Any],
        *,
        channel: str = "vfx",
        event_id: str | None = None,
    ) -> dict[str, Any]:
        """Clear an active event binding without rewinding bag consumption."""
        current = self._validated_state(state, channel)
        active = current.get("active_binding")
        if active is not None and event_id is not None and active.get("event_id") != event_id:
            raise VisualSelectionError(
                f"active binding belongs to event {active.get('event_id')!r}"
            )
        current["active_binding"] = None
        return current


__all__ = ["VisualSelectionCore", "VisualSelectionError"]
