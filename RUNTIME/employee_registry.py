from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


class EmployeeMetadataError(ValueError):
    """Raised when employee metadata is missing, ambiguous or inconsistent."""


class EmployeeMetadataRegistry:
    """Read-only lookup for persistent employee instances.

    character_id continues to resolve the canonical render/template identity.
    employee_id is the durable actor-instance key used by future roster,
    stamina and behavior systems. Runtime state is never mutated here.
    """

    SCHEMA = "gds.employee_metadata.v1"
    MIN_SPEED_PERCENT = 225
    MAX_SPEED_PERCENT = 250

    def __init__(self, root: str | Path):
        supplied_root = Path(root).resolve()
        self.project_root = (
            supplied_root.parent
            if supplied_root.name.casefold() == "character"
            else supplied_root
        )
        self.path = self.project_root / "CHARACTER" / "EMPLOYEES" / "employee_metadata.json"
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EmployeeMetadataError(
                f"Unable to load employee metadata: {self.path}"
            ) from exc
        if payload.get("schema") != self.SCHEMA:
            raise EmployeeMetadataError(
                f"Unsupported employee metadata schema: {payload.get('schema')!r}"
            )

        rows = payload.get("employees")
        if not isinstance(rows, list) or not rows:
            raise EmployeeMetadataError("Employee metadata must contain a non-empty employees list")
        self.payload = payload
        self.employees = [copy.deepcopy(row) for row in rows]
        self._by_id: dict[str, dict[str, Any]] = {}
        self._by_wave: dict[int, list[dict[str, Any]]] = {1: [], 2: []}
        self._by_character: dict[str, list[dict[str, Any]]] = {}
        self._validate_source_bindings()
        self._index_rows()

    def _validate_source_bindings(self) -> None:
        identity_path = self.project_root / "CHARACTER" / "IDENTITY" / "CHARACTERS" / "identity_cards.json"
        character_path = self.project_root / "CHARACTER" / "CHARACTERS" / "characters.json"
        try:
            identity = json.loads(identity_path.read_text(encoding="utf-8"))
            technical = json.loads(character_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EmployeeMetadataError(
                "Canonical character registries are required for employee metadata"
            ) from exc
        identity_by_id = {row["character_id"]: row for row in identity.get("characters", [])}
        technical_by_id = {row["character_id"]: row for row in technical.get("characters", [])}
        if not identity_by_id or set(identity_by_id) != set(technical_by_id):
            raise EmployeeMetadataError("Canonical technical and identity registries are inconsistent")

        for row in self.employees:
            character_id = row.get("character_id")
            card = identity_by_id.get(character_id)
            technical_row = technical_by_id.get(character_id)
            if card is None or technical_row is None:
                raise EmployeeMetadataError(
                    f"Employee {row.get('employee_id')!r} references unknown character_id {character_id!r}"
                )
            if row.get("template_character_no") != card.get("character_no"):
                raise EmployeeMetadataError(
                    f"Employee {row.get('employee_id')!r} has a stale template_character_no"
                )
            if row.get("template_character_code") != card.get("character_code"):
                raise EmployeeMetadataError(
                    f"Employee {row.get('employee_id')!r} has a stale template_character_code"
                )
            if row.get("character_pool") != (
                "original" if card["origin"]["type"] == "original" else "custom"
            ):
                raise EmployeeMetadataError(
                    f"Employee {row.get('employee_id')!r} has a stale character_pool"
                )
            name_profile = row.get("name_profile")
            if (
                not isinstance(name_profile, dict)
                or name_profile.get("pool") != card["name_profile"].get("pool")
            ):
                raise EmployeeMetadataError(
                    f"Employee {row.get('employee_id')!r} has a name-pool mismatch"
                )
            if row.get("template_origin") != card.get("origin"):
                raise EmployeeMetadataError(
                    f"Employee {row.get('employee_id')!r} has stale template provenance"
                )
            movement = row.get("movement_profile")
            speed = movement.get("speed_percent") if isinstance(movement, dict) else None
            if isinstance(speed, bool) or not isinstance(speed, int):
                raise EmployeeMetadataError(
                    f"Employee {row.get('employee_id')!r} has an invalid movement speed"
                )
            if not self.MIN_SPEED_PERCENT <= speed <= self.MAX_SPEED_PERCENT:
                raise EmployeeMetadataError(
                    f"Employee {row.get('employee_id')!r} has an out-of-range movement speed"
                )
            if row.get("generation_wave") == 1 and speed != technical_row["movement_profile"].get(
                "speed_percent"
            ):
                raise EmployeeMetadataError(
                    f"Employee {row.get('employee_id')!r} has a stale Wave 1 movement speed"
                )
            if row.get("generation_wave") == 1:
                for field in ("first_name", "last_name", "full_name", "nickname"):
                    if row.get(field) != card.get(field):
                        raise EmployeeMetadataError(
                            f"Employee {row.get('employee_id')!r} has stale Wave 1 {field}"
                        )
            stamina = row.get("stamina_profile")
            if not isinstance(stamina, dict) or stamina.get("stamina_max") != 100:
                raise EmployeeMetadataError(
                    f"Employee {row.get('employee_id')!r} must have stamina_max=100"
                )
            assignment = row.get("assignment")
            if assignment is not None and not isinstance(assignment, dict):
                raise EmployeeMetadataError(
                    f"Employee {row.get('employee_id')!r} has an invalid assignment"
                )

    def _index_rows(self) -> None:
        assigned_slots: dict[str, str] = {}
        assigned_orders: dict[int, str] = {}
        for row in self.employees:
            employee_id = row.get("employee_id")
            if not isinstance(employee_id, str) or not employee_id:
                raise EmployeeMetadataError("Every employee must have a non-empty employee_id")
            if employee_id in self._by_id:
                raise EmployeeMetadataError(f"Duplicate employee_id: {employee_id}")
            wave = row.get("generation_wave")
            if wave not in (1, 2):
                raise EmployeeMetadataError(
                    f"{employee_id}: generation_wave must be 1 or 2"
                )
            self._by_id[employee_id] = row
            self._by_wave[wave].append(row)
            character_id = row["character_id"]
            self._by_character.setdefault(character_id, []).append(row)

            assignment = row.get("assignment")
            if assignment is None:
                continue
            if wave == 2:
                raise EmployeeMetadataError(
                    f"{employee_id}: Wave 2 metadata must remain unassigned"
                )
            if assignment.get("status") != "assigned":
                raise EmployeeMetadataError(f"{employee_id}: assignment status must be assigned")
            slot_id = assignment.get("slot_id")
            if not isinstance(slot_id, str) or not slot_id:
                raise EmployeeMetadataError(f"{employee_id}: assignment slot_id is required")
            prior = assigned_slots.get(slot_id)
            if prior is not None:
                raise EmployeeMetadataError(
                    f"Duplicate workstation slot assignment: {slot_id} ({prior}, {employee_id})"
                )
            assigned_slots[slot_id] = employee_id
            assignment_order = assignment.get("assignment_order")
            if not isinstance(assignment_order, int) or assignment_order < 0:
                raise EmployeeMetadataError(
                    f"{employee_id}: assignment_order must be a non-negative integer"
                )
            prior_order = assigned_orders.get(assignment_order)
            if prior_order is not None:
                raise EmployeeMetadataError(
                    f"Duplicate assignment_order: {assignment_order} ({prior_order}, {employee_id})"
                )
            assigned_orders[assignment_order] = employee_id

        expected_counts = self.payload.get("wave_counts", {})
        for wave in (1, 2):
            if expected_counts.get(f"wave{wave}") != len(self._by_wave[wave]):
                raise EmployeeMetadataError(
                    f"Wave {wave} count does not match employee metadata"
                )
        if expected_counts.get("total") != len(self.employees):
            raise EmployeeMetadataError("Total employee count does not match employee metadata")
        for wave in (1, 2):
            character_ids = [row["character_id"] for row in self._by_wave[wave]]
            if len(set(character_ids)) != len(character_ids):
                raise EmployeeMetadataError(
                    f"Wave {wave} contains duplicate character template bindings"
                )

    @staticmethod
    def _copy(row: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(row)

    def get(self, employee_id: str) -> dict[str, Any]:
        if not isinstance(employee_id, str) or not employee_id.strip():
            raise EmployeeMetadataError("employee_id must be a non-empty string")
        try:
            return self._copy(self._by_id[employee_id.strip()])
        except KeyError as exc:
            raise EmployeeMetadataError(f"Unknown employee_id: {employee_id!r}") from exc

    def resolve(self, employee_id: str) -> dict[str, Any]:
        return self.get(employee_id)

    def list(
        self,
        *,
        wave: int | None = None,
        assigned: bool | None = None,
        character_pool: str | None = None,
    ) -> list[dict[str, Any]]:
        if wave is not None and wave not in (1, 2):
            raise EmployeeMetadataError("wave must be 1, 2 or None")
        if assigned is not None and not isinstance(assigned, bool):
            raise EmployeeMetadataError("assigned must be a boolean or None")
        if character_pool is not None and character_pool not in {"original", "custom"}:
            raise EmployeeMetadataError("character_pool must be original, custom or None")
        rows = self._by_wave[wave] if wave is not None else self.employees
        return [
            self._copy(row)
            for row in rows
            if (assigned is None or (row.get("assignment") is not None) == assigned)
            and (character_pool is None or row.get("character_pool") == character_pool)
        ]

    def employees_for_character(
        self,
        character_id: str,
        *,
        wave: int | None = None,
    ) -> list[dict[str, Any]]:
        if not isinstance(character_id, str) or not character_id.strip():
            raise EmployeeMetadataError("character_id must be a non-empty string")
        if wave is not None and wave not in (1, 2):
            raise EmployeeMetadataError("wave must be 1, 2 or None")
        rows = self._by_character.get(character_id.strip(), [])
        return [
            self._copy(row)
            for row in rows
            if wave is None or row["generation_wave"] == wave
        ]

    def initial_roster(self, floor_id: str | None = None) -> list[dict[str, Any]]:
        if floor_id is not None and (not isinstance(floor_id, str) or not floor_id.strip()):
            raise EmployeeMetadataError("floor_id must be a non-empty string or None")
        result: list[dict[str, Any]] = []
        for row in self._by_wave[1]:
            assignment = row.get("assignment")
            if assignment is None:
                continue
            if floor_id is not None and assignment["floor_id"] != floor_id.strip():
                continue
            result.append(
                {
                    "employee_id": row["employee_id"],
                    "character_id": row["character_id"],
                    "character_pool": row["character_pool"],
                    "full_name": row["full_name"],
                    "nickname": row["nickname"],
                    **self._copy(assignment),
                }
            )
        return sorted(result, key=lambda row: int(row["assignment_order"]))

    def resolve_initial_roster(self, floor_id: str | None = None) -> list[dict[str, Any]]:
        return self.initial_roster(floor_id)

    def stamina_policy(self) -> dict[str, Any]:
        return self._copy(self.payload["stamina_policy"])

    def movement_profile(self, employee_id: str) -> dict[str, Any]:
        row = self.get(employee_id)
        profile = self._copy(row["movement_profile"])
        speed = profile["speed_percent"]
        profile.update(
            {
                "employee_id": row["employee_id"],
                "character_id": row["character_id"],
                "speed_multiplier": speed / 100.0,
                "speed_range_percent": [self.MIN_SPEED_PERCENT, self.MAX_SPEED_PERCENT],
            }
        )
        return profile
