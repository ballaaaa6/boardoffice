from __future__ import annotations

"""Storage-neutral save/load and deterministic replay for runtime snapshots.

The simulation remains a pure reducer: callers own where JSON is stored.  This
module supplies the missing boundary that turns a validated runtime snapshot
into a canonical string and replays an ordered list of explicit host steps.
It is intentionally usable by a browser/localStorage host, a file-backed
dashboard, or a test without introducing a database or hidden process state.
"""

import copy
import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .central_core import CentralGameCore


class RuntimePersistenceError(ValueError):
    """Raised when a save payload or replay step is malformed."""


class RuntimePersistence:
    SCHEMA = "gds.runtime_replay.v1"
    VERSION = "1.0.0"

    def __init__(self, core: "CentralGameCore") -> None:
        self.core = core

    @staticmethod
    def _copy(value: Any) -> Any:
        return copy.deepcopy(value)

    @staticmethod
    def canonical_json(value: Any) -> str:
        try:
            return json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as exc:
            raise RuntimePersistenceError("value must be JSON-safe") from exc

    def canonical_runtime_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.core.validate_runtime_snapshot(snapshot)
        except Exception as exc:
            raise RuntimePersistenceError("runtime snapshot failed validation") from exc

    def snapshot_to_json(self, snapshot: dict[str, Any]) -> str:
        """Return canonical JSON suitable for localStorage or a save file."""
        return self.canonical_json(self.canonical_runtime_snapshot(snapshot))

    def snapshot_from_json(self, payload: str | bytes | bytearray | dict[str, Any]) -> dict[str, Any]:
        """Parse and validate a previously saved runtime snapshot."""
        if isinstance(payload, (bytes, bytearray)):
            try:
                payload = bytes(payload).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise RuntimePersistenceError("snapshot payload must be UTF-8 JSON") from exc
        if isinstance(payload, str):
            try:
                value = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise RuntimePersistenceError("snapshot payload is not valid JSON") from exc
        elif isinstance(payload, dict):
            value = self._copy(payload)
        else:
            raise RuntimePersistenceError("snapshot payload must be JSON text or an object")
        if not isinstance(value, dict):
            raise RuntimePersistenceError("snapshot payload must decode to an object")
        return self.canonical_runtime_snapshot(value)

    @staticmethod
    def _commands(value: Any, name: str) -> list[dict[str, Any]]:
        if value is None:
            return []
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise RuntimePersistenceError(f"{name} must be a list of objects")
        return copy.deepcopy(value)

    @staticmethod
    def _step(step: Any, index: int) -> dict[str, Any]:
        if not isinstance(step, dict):
            raise RuntimePersistenceError(f"replay step {index} must be an object")
        elapsed_ms = step.get("elapsed_ms")
        if isinstance(elapsed_ms, bool) or not isinstance(elapsed_ms, int) or elapsed_ms < 0:
            raise RuntimePersistenceError(f"replay step {index}.elapsed_ms must be >= 0")
        locale = step.get("dialogue_locale", "en")
        if not isinstance(locale, str) or not locale:
            raise RuntimePersistenceError(f"replay step {index}.dialogue_locale must be text")
        seed = step.get("dialogue_seed", "0")
        if isinstance(seed, bool) or not isinstance(seed, (str, int)):
            raise RuntimePersistenceError(
                f"replay step {index}.dialogue_seed must be text or integer"
            )
        return {
            "elapsed_ms": int(elapsed_ms),
            "actor_commands": RuntimePersistence._commands(
                step.get("actor_commands"), f"replay step {index}.actor_commands"
            ),
            "speech_commands": RuntimePersistence._commands(
                step.get("speech_commands"), f"replay step {index}.speech_commands"
            ),
            "dialogue_locale": locale,
            "dialogue_seed": seed,
        }

    def build_replay(
        self,
        initial_snapshot: dict[str, Any],
        steps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build a validated replay package from a snapshot and host steps."""
        initial = self.canonical_runtime_snapshot(initial_snapshot)
        if not isinstance(steps, list):
            raise RuntimePersistenceError("replay steps must be a list")
        normalized = [self._step(step, index) for index, step in enumerate(steps)]
        return {
            "schema": self.SCHEMA,
            "version": self.VERSION,
            "initial_runtime_snapshot": initial,
            "steps": normalized,
        }

    def replay_to_json(
        self,
        initial_snapshot: dict[str, Any],
        steps: list[dict[str, Any]],
    ) -> str:
        return self.canonical_json(self.build_replay(initial_snapshot, steps))

    def replay_package_from_json(self, payload: str | bytes | dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload, (bytes, bytearray)):
            try:
                payload = bytes(payload).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise RuntimePersistenceError("replay payload must be UTF-8 JSON") from exc
        if isinstance(payload, str):
            try:
                package = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise RuntimePersistenceError("replay payload is not valid JSON") from exc
        elif isinstance(payload, dict):
            package = self._copy(payload)
        else:
            raise RuntimePersistenceError("replay payload must be JSON text or an object")
        if not isinstance(package, dict):
            raise RuntimePersistenceError("replay payload must decode to an object")
        if package.get("schema") != self.SCHEMA or package.get("version") != self.VERSION:
            raise RuntimePersistenceError("unsupported runtime replay schema/version")
        return self.build_replay(
            package.get("initial_runtime_snapshot"),
            package.get("steps", []),
        )

    def replay(
        self,
        initial_snapshot: dict[str, Any],
        steps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Replay explicit host steps and return the final snapshot/event trace."""
        package = self.build_replay(initial_snapshot, steps)
        current = package["initial_runtime_snapshot"]
        trace: list[dict[str, Any]] = []
        for index, step in enumerate(package["steps"]):
            result = self.core.advance_runtime_snapshot(
                current,
                step["elapsed_ms"],
                actor_commands=step["actor_commands"],
                speech_commands=step["speech_commands"],
                dialogue_locale=step["dialogue_locale"],
                dialogue_seed=step["dialogue_seed"],
            )
            current = self.canonical_runtime_snapshot(result)
            trace.append({
                "step_index": index,
                "elapsed_ms": step["elapsed_ms"],
                "events": copy.deepcopy(result.get("events", [])),
            })
        return {
            "schema": self.SCHEMA,
            "version": self.VERSION,
            "snapshot": current,
            "trace": trace,
        }

    def replay_package(self, payload: str | bytes | dict[str, Any]) -> dict[str, Any]:
        package = self.replay_package_from_json(payload)
        return self.replay(package["initial_runtime_snapshot"], package["steps"])

    def save_snapshot_file(self, path: str | Path, snapshot: dict[str, Any]) -> Path:
        """Optional convenience for a host that elects to use a local file."""
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.snapshot_to_json(snapshot) + "\n", encoding="utf-8")
        return target

    def load_snapshot_file(self, path: str | Path) -> dict[str, Any]:
        target = Path(path).resolve()
        try:
            payload = target.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimePersistenceError(f"unable to read snapshot file: {target}") from exc
        return self.snapshot_from_json(payload)
