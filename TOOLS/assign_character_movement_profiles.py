"""Assign and audit permanent per-character movement speed metadata.

The generated value is sampled once from the approved inclusive 225..250% range
using a new, documented seed and then stored in both character registries. Runtime
code reads the embedded value; it must never re-roll a character's speed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROFILE_SCHEMA = "gds.character_movement_profile.v1"
PROFILE_SEED = "gds-character-movement-speed-v4-225-250-reroll-20260831"
MIN_SPEED = 225
MAX_SPEED = 250


def _speed(character_id: str) -> int:
    digest = hashlib.sha256(f"{PROFILE_SEED}|{character_id}".encode("utf-8")).digest()
    return MIN_SPEED + int.from_bytes(digest[:8], "big") % (MAX_SPEED - MIN_SPEED + 1)


def _contract() -> dict[str, Any]:
    return {
        "schema": PROFILE_SCHEMA,
        "speed_range_percent": [MIN_SPEED, MAX_SPEED],
        "assignment_policy": "embedded_character_metadata",
        "profile_seed": PROFILE_SEED,
        "spawn_policy": "read_once_from_character_metadata",
    }


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def assign(*, write: bool) -> dict[str, Any]:
    technical_path = ROOT / "CHARACTER" / "CHARACTERS" / "characters.json"
    cards_path = ROOT / "CHARACTER" / "IDENTITY" / "CHARACTERS" / "identity_cards.json"
    technical = _load(technical_path)
    cards = _load(cards_path)

    technical["identity_model"] = "stable_id_plus_composition_plus_provenance"
    technical["movement_profile_contract"] = _contract()
    cards["movement_profile_contract"] = _contract()
    cards_by_id = {row["character_id"]: row for row in cards["characters"]}
    seen: dict[int, int] = {}
    for row in technical["characters"]:
        cid = row["character_id"]
        speed = _speed(cid)
        row["movement_profile"] = {"speed_percent": speed}
        seen[speed] = seen.get(speed, 0) + 1
        if cid not in cards_by_id:
            raise ValueError(f"Technical character missing from identity cards: {cid}")
        cards_by_id[cid]["movement_profile"] = {"speed_percent": speed}

    report = {
        "schema": "gds.character_movement_profile_assignment_audit.v1",
        "profile_contract": _contract(),
        "character_count": len(technical["characters"]),
        "speed_min": min(seen),
        "speed_max": max(seen),
        "distinct_speed_count": len(seen),
        "speed_histogram": {str(k): seen[k] for k in sorted(seen)},
        "all_identity_cards_synchronized": all(
            cards_by_id[row["character_id"]]["movement_profile"] == row["movement_profile"]
            for row in technical["characters"]
        ),
    }
    if not (MIN_SPEED <= report["speed_min"] <= report["speed_max"] <= MAX_SPEED):
        raise ValueError(f"Speed range audit failed: {report}")
    if not report["all_identity_cards_synchronized"]:
        raise ValueError("Technical and identity-card movement metadata diverged")
    if write:
        _write(technical_path, technical)
        _write(cards_path, cards)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write the generated profiles")
    args = parser.parse_args()
    report = assign(write=args.write)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
