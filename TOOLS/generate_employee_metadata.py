"""Generate the persistent employee metadata and initial Wave 1 roster.

The canonical character_id remains the visual/template identity already used
by the renderer.  This generator adds a separate employee_id for each actor
instance, so later gameplay can change assignment or stamina without
mutating the character asset registries.

The output is deterministic.  It intentionally materializes only Wave 1 and
Wave 2 metadata; Wave 2 is pre-generated but starts unassigned.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "CHARACTER" / "EMPLOYEES" / "employee_metadata.json"

SCHEMA = "gds.employee_metadata.v1"
VERSION = "1.0.0"
GENERATOR_VERSION = "1.0.0"
GENERATION_DATE = "2026-08-31"

WAVE1_SIZE = 302
WAVE2_SIZE = 302

WAVE2_TEMPLATE_SEED = "gds-employee-wave2-template-order-v1"
WAVE2_NAME_SEED = "gds-employee-wave2-english-name-v1"
WAVE2_MOVEMENT_SEED = "gds-employee-wave2-movement-speed-v1"
STAMINA_PROFILE_SEED = "gds-employee-stamina-profile-v1"
ASSIGNMENT_SEED = "gds-employee-wave1-floor-assignment-v1"

MIN_MOVE_SPEED = 225
MAX_MOVE_SPEED = 250
MIN_DRAIN_MILLI = 600
MAX_DRAIN_MILLI = 850


# These are deliberately ordinary English/UK-style given names.  Existing
# names are filtered out before Wave 2 is generated, so the output remains
# new even when the canonical identity roster grows later.
MALE_FIRST_NAMES = (
    "Aaron", "Adrian", "Alaric", "Alfred", "Alton", "Ambrose", "Andrew",
    "Angus", "Archer", "Archie", "Arthur", "Ashton", "Atticus", "August",
    "Barrett", "Barry", "Beau", "Benedict", "Bradley", "Brent", "Brody",
    "Byron", "Caleb", "Callan", "Callum", "Camden", "Cason", "Channing",
    "Chase", "Chester", "Ciaran", "Cillian", "Clifford", "Clive", "Cody",
    "Cole", "Connor", "Cooper", "Cormac", "Craig", "Cyrus", "Dalton",
    "Dane", "Daniel", "Darius", "Darian", "Declan", "Derek", "Dexter",
    "Duncan", "Dustin", "Earl", "Easton", "Edmund", "Edward", "Elijah",
    "Emile", "Ernest", "Ezra", "Fabian", "Finn", "Fletcher", "Flynn",
    "Ford", "Forrest", "Foster", "Garrett", "George", "Gideon", "Graham",
    "Grant", "Grayson", "Hamish", "Harrison", "Harvey", "Heath", "Holden",
    "Hudson", "Hunter", "Ian", "Isaac", "Isaiah", "Ivan", "Jace", "Jackson",
    "Jared", "Jaxon", "Jay", "Jayden", "Jensen", "Jerome", "Jett", "Jonas",
    "Julian", "Julius", "Kade", "Kellan", "Kieran", "Kingston", "Knox",
    "Lachlan", "Lance", "Lawson", "Leighton", "Lennox", "Lincoln", "Louis",
    "Maddox", "Malcolm", "Marley", "Marshall", "Maverick", "Miles", "Milo",
    "Montgomery", "Nash", "Nolan", "Oliver", "Orion", "Orson", "Otis",
    "Paxton", "Pierce", "Quentin", "Rafe", "Rafael", "Reid", "Rhys", "Rio",
    "Ronan", "Royce", "Ryder", "Shane", "Soren", "Stefan", "Sullivan",
    "Tanner", "Tate", "Thatcher", "Travis", "Trent", "Troy", "Vaughn",
    "Vincent", "Wade", "Walker", "Weston", "Xander", "Zachary",
)

FEMALE_FIRST_NAMES = (
    "Aaliyah", "Adelaide", "Adeline", "Alana", "Alexandra", "Alice", "Alina",
    "Alyssa", "Amber", "Anastasia", "Angelina", "Annelise", "Arabella",
    "Ariella", "Ashleigh", "Athena", "Autumn", "Beatrice", "Bella",
    "Bethany", "Bonnie", "Brielle", "Camille", "Camilla", "Celeste", "Chloe",
    "Colette", "Coralie", "Delaney", "Elise", "Eliza", "Eloise", "Esme",
    "Esther", "Eva", "Fiona", "Francesca", "Freya", "Gabrielle", "Gemma",
    "Grace", "Gracie", "Harriet", "Hazel", "Imogen", "Iris", "Isla", "Ivy",
    "Jade", "Joy", "Kelsey", "Kiara", "Lacey", "Leah", "Leona", "Lexi",
    "Lydia", "Mackenzie", "Maisie", "Mallory", "Marnie", "Matilda", "Maya",
    "Melody", "Mia", "Millie", "Nina", "Opal", "Olivia", "Phoebe", "Pippa",
    "Piper", "Rachel", "Rebecca", "Rhiannon", "Rosalie", "Sadie", "Sabrina",
    "Selena", "Sophie", "Summer", "Tessa", "Thea", "Valerie", "Willow",
    "Zara", "Annalise", "Beatrix", "Beth", "Celine", "Elodie", "Elora",
    "Emilia", "Flora", "Isabelle", "Juliette", "Keira", "Lillian", "Lucy",
    "Lyra", "Marissa", "Mavis", "Nell", "Odette", "Pearl", "Poppy",
    "Priya", "Sienna", "Susannah", "Talia", "Tallulah", "Vera", "Victoria",
    "Violet", "Willa", "Winnie", "Yasmin", "Yvette",
)

NEUTRAL_FIRST_NAMES = (
    "Addison", "Alexi", "Ainsley", "Aspen", "Blaise", "Bowie", "Briar",
    "Brook", "Campbell", "Chandler", "Charlie", "Clancy", "Clement", "Clover",
    "Emerson", "Fallon", "Finley", "Gray", "Harper", "Haven", "Indigo",
    "Jaden", "Justice", "Lennon", "Linden", "London", "Lyric", "Milan",
    "Ocean", "Onyx", "Rain", "Reagan", "Sasha", "Scout", "Sidney", "Sky",
    "Sloan", "Sonny", "Storm", "Sunny", "Teal", "Tegan", "True", "Vale",
    "Zephyr", "Zenith", "Bellamy", "Brighton", "Lake", "Nova", "Salem",
    "Shea", "Skye", "Sterling", "Wynn", "Aubrey", "Bailey", "Blair",
    "Casey", "Cory", "Dylan", "Elliott", "Frankie", "Jules", "Kendall",
    "Kennedy", "Kerry", "Lesley", "Lior", "Marlowe", "Merritt", "Reed",
    "Shawn", "Shay", "Tracy", "Whitney", "Winslow", "Waverly", "Briar",
)

FIRST_NAME_POOLS = {
    "male": MALE_FIRST_NAMES,
    "female": FEMALE_FIRST_NAMES,
    "neutral": NEUTRAL_FIRST_NAMES,
}

SURNAME_PREFIXES = (
    "Ash", "Alder", "Bell", "Birch", "Black", "Blythe", "Bracken", "Bright",
    "Brook", "Calder", "Cedar", "Clay", "Clear", "Clover", "Crest", "Dale",
    "East", "Fair", "Falcon", "Finch", "Fox", "Frost", "Glen", "Green",
    "Hart", "Hawthorn", "Hazel", "Heath", "Hill", "Hollow", "Ivy", "Kings",
    "Lake", "Lang", "Linden", "Long", "Maple", "Meadow", "Merritt", "North",
    "Oak", "Park", "Pine", "Reed", "River", "Rose", "Rowan", "Silver",
    "Stone", "Summer", "Thorn", "Vale", "Waverly", "West", "Whit", "Willow",
    "Wind", "Wood", "Crown", "Dover", "Eden", "Elm", "Field", "Grove",
)

SURNAME_SUFFIXES = (
    "bank", "bell", "bourne", "brook", "bury", "by", "croft", "dale", "field",
    "ford", "gate", "ham", "hill", "land", "ley", "lock", "man", "mont",
    "more", "ridge", "side", "son", "stone", "ton", "vale", "ward", "well",
    "wick", "wood", "worth", "wright", "shaw", "mere", "hurst", "court",
)

NICKNAME_PREFIXES = (
    "Ace", "Arrow", "Atlas", "Aura", "Beacon", "Bex", "Birdie", "Blaze",
    "Blue", "Bolt", "Breezy", "Brick", "Buddy", "Clover", "Comet", "Copper",
    "Cricket", "Dash", "Echo", "Ember", "Fable", "Falcon", "Fern", "Finch",
    "Flint", "Fox", "Halo", "Harbor", "Hawk", "Indie", "Jazz", "Jett",
    "Kestrel", "Kite", "Lucky", "Maple", "Midnight", "Mint", "Moss", "Nova",
    "Orbit", "Pebble", "Pixel", "Poppy", "Quest", "Quill", "Raven", "Rebel",
    "Rook", "Sailor", "Scout", "Shadow", "Skipper", "Sol", "Sparrow", "Spark",
    "Sprout", "Star", "Sunny", "Swift", "Tiger", "Toast", "Vega", "Vesper",
    "Willow", "Wink", "Wolf", "Zephyr",
)

NICKNAME_SUFFIXES = (
    "Bay", "Bird", "Bloom", "Blue", "Brook", "Cloud", "Cove", "Dawn", "Field",
    "Finch", "Fox", "Glow", "Grove", "Hawk", "Leaf", "Light", "Moon", "Moss",
    "Peak", "Pine", "Rain", "Reed", "Ridge", "River", "Sky", "Stone", "Storm",
    "Tide", "Trail", "Vale", "Wave", "Wood",
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(seed: str, value: str) -> bytes:
    return hashlib.sha256(f"{seed}|{value}".encode("utf-8")).digest()


def _hash_int(seed: str, value: str, lower: int, upper: int) -> int:
    if lower > upper:
        raise ValueError(f"Invalid integer range: {lower}..{upper}")
    digest = _digest(seed, value)
    return lower + int.from_bytes(digest[:8], "big") % (upper - lower + 1)


def _ranked(values: Iterable[str], seed: str) -> list[str]:
    unique = list(dict.fromkeys(str(value) for value in values))
    return sorted(unique, key=lambda value: (_digest(seed, value), value.casefold()))


def _normalized_set(values: Iterable[str]) -> set[str]:
    return {str(value).strip().casefold() for value in values}


def _pick_unique(
    candidates: Iterable[str],
    count: int,
    *,
    seed: str,
    reserved: Iterable[str] = (),
) -> list[str]:
    if count < 0:
        raise ValueError("count must be non-negative")
    used = _normalized_set(reserved)
    picked: list[str] = []
    for candidate in _ranked(candidates, seed):
        normalized = candidate.strip().casefold()
        if not normalized or normalized in used:
            continue
        picked.append(candidate)
        used.add(normalized)
        if len(picked) == count:
            return picked
    raise ValueError(
        f"Could not generate {count} unique values for {seed}; "
        f"only generated {len(picked)}"
    )


def _first_names_for_wave2(
    cards: list[dict[str, Any]],
    existing_names: set[str],
) -> dict[str, list[str]]:
    counts: dict[str, int] = {"neutral": 0, "male": 0, "female": 0}
    for card in cards:
        pool = card["name_profile"]["pool"]
        if pool not in counts:
            raise ValueError(f"Unsupported name pool in identity cards: {pool}")
        counts[pool] += 1

    used = set(existing_names)
    result: dict[str, list[str]] = {}
    for pool in ("neutral", "male", "female"):
        result[pool] = _pick_unique(
            FIRST_NAME_POOLS[pool],
            counts[pool],
            seed=f"{WAVE2_NAME_SEED}|first|{pool}",
            reserved=used,
        )
        used.update(_normalized_set(result[pool]))
    return result


def _surname_candidates() -> list[str]:
    return [
        f"{prefix}{suffix}"
        for prefix in SURNAME_PREFIXES
        for suffix in SURNAME_SUFFIXES
        if prefix.casefold() != suffix.casefold()
    ]


def _nickname_candidates() -> list[str]:
    return [
        f"{prefix} {suffix}"
        for prefix in NICKNAME_PREFIXES
        for suffix in NICKNAME_SUFFIXES
        if prefix.casefold() != suffix.casefold()
    ]


def _floor_sort_key(floor_id: str) -> tuple[int, int, str]:
    match = re.fullmatch(r"floor([0-9]+)", floor_id)
    if match:
        return (0, int(match.group(1)), floor_id)
    return (1, 0, floor_id)


def _workstation_sort_key(workstation_id: str) -> tuple[int, int, str]:
    if workstation_id == "ceo":
        return (0, 0, workstation_id)
    if workstation_id.startswith("ws") and workstation_id[2:].isdigit():
        return (1, int(workstation_id[2:]), workstation_id)
    return (2, 0, workstation_id)


def _build_workstation_slots(root: Path) -> list[dict[str, Any]]:
    floors_path = root / "WORLD" / "REGISTRY" / "floors.json"
    layouts_path = root / "WORLD" / "REGISTRY" / "layouts.json"
    direction_path = root / "WORLD" / "REGISTRY" / "workstation_directions.json"
    floors = _load(floors_path)["floors"]
    layouts = _load(layouts_path)["layouts"]
    directions = _load(direction_path)["layout_directions"]

    slots: list[dict[str, Any]] = []
    for floor_id in sorted(floors, key=_floor_sort_key):
        floor = floors[floor_id]
        layout_id = floor["layout_id"]
        layout = layouts[layout_id]
        direction_profile = directions[layout_id]["workstations"]
        workstation_ids = [
            workstation_id
            for workstation_id, group in layout["workstation_groups"].items()
            if group.get("group_type") == "workstation"
            and group.get("component_slots", {}).get("pc") is not None
        ]
        for workstation_id in sorted(workstation_ids, key=_workstation_sort_key):
            slots.append(
                {
                    "assignment_order": len(slots),
                    "floor_id": floor_id,
                    "workstation_id": workstation_id,
                    "slot_id": f"workseat:{floor_id}:{workstation_id}:primary",
                    "capacity": 1,
                    "facing": direction_profile[workstation_id]["interaction_direction"],
                    "seat_transition_ready": True,
                }
            )
    return slots


def _stamina_profile(employee_id: str) -> dict[str, Any]:
    lower = _hash_int(STAMINA_PROFILE_SEED, f"{employee_id}|drain", MIN_DRAIN_MILLI, 760)
    upper = _hash_int(STAMINA_PROFILE_SEED, f"{employee_id}|drain_bias", 0, 90)
    drain = min(MAX_DRAIN_MILLI, lower + upper)
    return {
        "stamina_max": 100,
        "work_drain_milli_per_second": drain,
        "event_timing_multiplier_percent": _hash_int(
            STAMINA_PROFILE_SEED, f"{employee_id}|timing", 90, 115
        ),
        "home_delay_seconds_range": [
            _hash_int(STAMINA_PROFILE_SEED, f"{employee_id}|home_low", 8, 12),
            _hash_int(STAMINA_PROFILE_SEED, f"{employee_id}|home_high", 17, 24),
        ],
        "profile_seed": STAMINA_PROFILE_SEED,
    }


def _employee_speed(employee_id: str) -> int:
    return _hash_int(WAVE2_MOVEMENT_SEED, employee_id, MIN_MOVE_SPEED, MAX_MOVE_SPEED)


def _wave2_name_profile(card: dict[str, Any]) -> dict[str, Any]:
    source_label = card["name_profile"].get("source_label")
    return {
        "pool": card["name_profile"]["pool"],
        "basis": "wave2_seeded_gender_pool",
        "source_label": source_label,
        "generation": WAVE2_NAME_SEED,
    }


def _employee_row_from_card(
    card: dict[str, Any],
    technical_by_id: dict[str, dict[str, Any]],
    employee_id: str,
) -> dict[str, Any]:
    character_id = card["character_id"]
    technical = technical_by_id[character_id]
    origin = copy.deepcopy(card["origin"])
    pool = "original" if origin["type"] == "original" else "custom"
    canonical_speed = int(technical["movement_profile"]["speed_percent"])
    card_speed = int(card["movement_profile"]["speed_percent"])
    if canonical_speed != card_speed:
        raise ValueError(f"Movement metadata mismatch for {character_id}")
    return {
        "employee_id": employee_id,
        "generation_wave": 1,
        "character_id": character_id,
        "character_pool": pool,
        "template_character_no": card["character_no"],
        "template_character_code": card["character_code"],
        "first_name": card["first_name"],
        "last_name": card["last_name"],
        "full_name": card["full_name"],
        "nickname": card["nickname"],
        "name_profile": copy.deepcopy(card["name_profile"]),
        "template_origin": origin,
        "movement_profile": {
            "speed_percent": card_speed,
            "source": "canonical_character_metadata",
        },
        "stamina_profile": _stamina_profile(employee_id),
        "assignment": None,
    }


def _build_stamina_policy(effect_ids: list[str], humanball_ids: list[str]) -> dict[str, Any]:
    return {
        "schema": "gds.stamina_policy.v1",
        "time_unit": "simulation_seconds",
        "stamina_max": 100,
        "critical_threshold": 10,
        "target_work_cycle_seconds_range": [120, 300],
        "work_drain_unit": "milli_stamina_per_second",
        "per_employee_work_drain_range": [MIN_DRAIN_MILLI, MAX_DRAIN_MILLI],
        "recovery_operation": "add_then_clamp_to_stamina_max",
        "recovery_events": {
            "talk": {
                "interval_seconds_range": [45, 75],
                "recovery_amount_range": [5, 9],
                "activity_duration_seconds_range": [5, 8],
                "selection_weight": 45,
                "runtime_status": "pending_conversation_system",
                "visual_channel": "idle_conversation",
            },
            "background_effect": {
                "interval_seconds_range": [30, 50],
                "recovery_amount_range": [1, 3],
                "activity_duration_seconds_range": [2, 4],
                "selection_weight": 20,
                "runtime_status": "existing_effect_registry_pending_behavior_binding",
                "visual_channel": "effect_registry",
            },
            "popup": {
                "interval_seconds_range": [25, 45],
                "recovery_amount_range": [1, 2],
                "activity_duration_seconds_range": [2, 4],
                "selection_weight": 15,
                "runtime_status": "existing_popup_assets_pending_behavior_binding",
                "visual_channel": "humanball_or_effect_registry",
            },
            "wander": {
                "interval_seconds_range": [60, 100],
                "recovery_amount_range": [1, 4],
                "activity_duration_seconds_range": [4, 7],
                "selection_weight": 20,
                "runtime_status": "existing_movement_primitive_pending_stamina_binding",
                "visual_channel": "move",
            },
        },
        "home_policy": {
            "trigger": "stamina_lte_critical_threshold",
            "delay_seconds_range": [8, 20],
            "restore_policy": "full_on_home",
            "retain_assignment": True,
            "return_target": "same_owned_workstation",
            "runtime_status": "pending_home_return_system",
        },
        "visual_recovery_references": {
            "effect_ids": effect_ids,
            "humanball_ids": humanball_ids,
        },
    }


def build_metadata(root: str | Path = ROOT) -> dict[str, Any]:
    root = Path(root).resolve()
    technical_path = root / "CHARACTER" / "CHARACTERS" / "characters.json"
    cards_path = root / "CHARACTER" / "IDENTITY" / "CHARACTERS" / "identity_cards.json"
    floors_path = root / "WORLD" / "REGISTRY" / "floors.json"
    layouts_path = root / "WORLD" / "REGISTRY" / "layouts.json"
    directions_path = root / "WORLD" / "REGISTRY" / "workstation_directions.json"
    effects_path = root / "CHARACTER" / "EFFECTS" / "gds_effects_v1.json"
    event_presets_path = root / "CHARACTER" / "EFFECTS" / "event_presets.json"
    humanballs_path = root / "CHARACTER" / "EFFECTS" / "humanball_v1.json"

    technical = _load(technical_path)
    cards_data = _load(cards_path)
    cards = list(cards_data["characters"])
    technical_rows = list(technical["characters"])
    if len(cards) != WAVE1_SIZE or len(technical_rows) != WAVE1_SIZE:
        raise ValueError("The employee generator expects the current 302-character roster")
    technical_by_id = {row["character_id"]: row for row in technical_rows}
    cards_by_id = {row["character_id"]: row for row in cards}
    if set(technical_by_id) != set(cards_by_id):
        raise ValueError("Technical and identity character registries do not contain the same IDs")

    wave1: list[dict[str, Any]] = []
    for index, card in enumerate(cards, start=1):
        employee_id = f"EMP_W1_{index:04d}"
        wave1.append(_employee_row_from_card(card, technical_by_id, employee_id))

    existing_first_names = _normalized_set(card["first_name"] for card in cards)
    existing_last_names = _normalized_set(card["last_name"] for card in cards)
    existing_nicknames = _normalized_set(card["nickname"] for card in cards)
    wave2_first_names = _first_names_for_wave2(cards, existing_first_names)
    wave2_templates = _ranked(cards_by_id, WAVE2_TEMPLATE_SEED)
    wave2_surnames = _pick_unique(
        _surname_candidates(),
        WAVE2_SIZE,
        seed=f"{WAVE2_NAME_SEED}|surname",
        reserved=existing_last_names,
    )
    wave2_first_name_values = [name for names in wave2_first_names.values() for name in names]
    wave2_nicknames = _pick_unique(
        _nickname_candidates(),
        WAVE2_SIZE,
        seed=f"{WAVE2_NAME_SEED}|nickname",
        reserved=(
            set(existing_nicknames)
            | _normalized_set(wave2_first_name_values)
            | _normalized_set(wave2_surnames)
        ),
    )
    first_name_offsets = {"neutral": 0, "male": 0, "female": 0}
    wave2: list[dict[str, Any]] = []
    for index, character_id in enumerate(wave2_templates, start=1):
        card = cards_by_id[character_id]
        pool = card["name_profile"]["pool"]
        first_name = wave2_first_names[pool][first_name_offsets[pool]]
        first_name_offsets[pool] += 1
        last_name = wave2_surnames[index - 1]
        employee_id = f"EMP_W2_{index:04d}"
        wave2.append(
            {
                "employee_id": employee_id,
                "generation_wave": 2,
                "character_id": character_id,
                "character_pool": "original"
                if card["origin"]["type"] == "original"
                else "custom",
                "template_character_no": card["character_no"],
                "template_character_code": card["character_code"],
                "first_name": first_name,
                "last_name": last_name,
                "full_name": f"{first_name} {last_name}",
                "nickname": wave2_nicknames[index - 1],
                "name_profile": _wave2_name_profile(card),
                "template_origin": copy.deepcopy(card["origin"]),
                "movement_profile": {
                    "speed_percent": _employee_speed(employee_id),
                    "source": "wave2_employee_seeded_metadata",
                },
                "stamina_profile": _stamina_profile(employee_id),
                "assignment": None,
            }
        )

    slots = _build_workstation_slots(root)
    wave1_original = _ranked(
        (row["employee_id"] for row in wave1 if row["character_pool"] == "original"),
        f"{ASSIGNMENT_SEED}|original",
    )
    wave1_custom = _ranked(
        (row["employee_id"] for row in wave1 if row["character_pool"] == "custom"),
        f"{ASSIGNMENT_SEED}|custom",
    )
    assignment_order = wave1_original + wave1_custom
    if len(slots) > len(assignment_order):
        raise ValueError("There are more computer slots than Wave 1 employees")
    employees_by_id = {row["employee_id"]: row for row in wave1 + wave2}
    for slot, employee_id in zip(slots, assignment_order):
        employees_by_id[employee_id]["assignment"] = {
            "status": "assigned",
            "snapshot": "wave1_initial",
            "assignment_order": slot["assignment_order"],
            "floor_id": slot["floor_id"],
            "workstation_id": slot["workstation_id"],
            "slot_id": slot["slot_id"],
            "capacity": slot["capacity"],
            "facing": slot["facing"],
            "seat_transition_ready": slot["seat_transition_ready"],
        }

    effects = _load(effects_path)
    event_presets = _load(event_presets_path)
    humanballs = _load(humanballs_path)
    effect_ids = list(effects["effect_order"])
    positive_effect_ids = [
        effect_id
        for effect_id in effect_ids
        if effects["effects"][effect_id].get("mood") == "positive"
    ]
    humanball_ids = list(humanballs["humanball_order"])
    positive_preset_keys = [
        key
        for key, effect_id in event_presets["presets"].items()
        if effect_id in positive_effect_ids
    ]

    floor_count = len(_load(floors_path)["floors"])
    assigned_count = len(slots)
    custom_assigned_count = sum(
        1
        for row in wave1
        if row["character_pool"] == "custom" and row["assignment"] is not None
    )
    original_assigned_count = assigned_count - custom_assigned_count
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "identity_binding": {
            "character_id_role": "canonical_visual_template_id",
            "employee_id_role": "persistent_actor_instance_id",
            "wave2_reuses_character_art": True,
            "runtime_state_policy": "stamina_presence_activity_are_not_static_metadata",
        },
        "generation": {
            "generator": "TOOLS/generate_employee_metadata.py",
            "generator_version": GENERATOR_VERSION,
            "generated_date": GENERATION_DATE,
            "wave1_policy": "one_employee_per_canonical_character_in_identity_card_order",
            "wave2_policy": "sha256_rank_all_canonical_templates_once",
            "wave2_template_seed": WAVE2_TEMPLATE_SEED,
            "wave2_name_seed": WAVE2_NAME_SEED,
            "wave2_movement_seed": WAVE2_MOVEMENT_SEED,
            "stamina_profile_seed": STAMINA_PROFILE_SEED,
            "initial_assignment_seed": ASSIGNMENT_SEED,
            "source_hashes": {
                "technical_character_registry_sha256": _sha256(technical_path),
                "identity_cards_sha256": _sha256(cards_path),
                "floor_registry_sha256": _sha256(floors_path),
                "layout_registry_sha256": _sha256(layouts_path),
                "direction_registry_sha256": _sha256(directions_path),
            },
        },
        "source_registries": {
            "technical_characters": "CHARACTER/CHARACTERS/characters.json",
            "identity_cards": "CHARACTER/IDENTITY/CHARACTERS/identity_cards.json",
            "floors": "WORLD/REGISTRY/floors.json",
            "layouts": "WORLD/REGISTRY/layouts.json",
            "workstation_directions": "WORLD/REGISTRY/workstation_directions.json",
            "effects": "CHARACTER/EFFECTS/gds_effects_v1.json",
            "event_presets": "CHARACTER/EFFECTS/event_presets.json",
            "humanballs": "CHARACTER/EFFECTS/humanball_v1.json",
        },
        "wave_counts": {
            "wave1": len(wave1),
            "wave2": len(wave2),
            "total": len(wave1) + len(wave2),
        },
        "roster_policy": {
            "floor_count": floor_count,
            "workstation_capacity": 1,
            "floor_order": "numeric_floor_suffix_ascending_then_lexical",
            "workstation_order": "ceo_then_numeric_ws_then_lexical",
            "initial_assignment_order": "wave1_original_then_wave1_custom",
            "initial_assignment_count": assigned_count,
            "initial_original_assignment_count": original_assigned_count,
            "initial_custom_assignment_count": custom_assigned_count,
            "wave1_unassigned_count": len(wave1) - assigned_count,
            "wave2_initial_assignment": "null_unassigned",
            "unassignment_policy": "explicit_vacancy_only_no_auto_fill",
            "home_return_policy": "retain_the_same_owned_workstation",
        },
        "stamina_policy": _build_stamina_policy(positive_effect_ids, humanball_ids),
        "visual_channels": {
            "effect_registry": {
                "path": "CHARACTER/EFFECTS/gds_effects_v1.json",
                "recovery_effect_ids": positive_effect_ids,
                "fatigue_effect_id": "low_battery_drain",
            },
            "event_presets": {
                "path": "CHARACTER/EFFECTS/event_presets.json",
                "positive_event_keys": positive_preset_keys,
            },
            "humanball_registry": {
                "path": "CHARACTER/EFFECTS/humanball_v1.json",
                "popup_humanball_ids": humanball_ids,
            },
            "binding_policy": "metadata_references_existing_visual_registries_without_copying_assets",
        },
        "employees": wave1 + wave2,
    }


def write_metadata(root: str | Path = ROOT, output: str | Path | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    output_path = Path(output).resolve() if output is not None else root / OUTPUT_PATH.relative_to(ROOT)
    payload = build_metadata(root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the canonical metadata file")
    parser.add_argument("--output", type=Path, help="write to this path instead of the canonical output")
    args = parser.parse_args()
    payload = build_metadata(ROOT)
    if args.write or args.output is not None:
        output_path = args.output or OUTPUT_PATH
        output_path = output_path if output_path.is_absolute() else ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {output_path}")
    print(
        json.dumps(
            {
                "schema": payload["schema"],
                "wave_counts": payload["wave_counts"],
                "initial_assignment_count": payload["roster_policy"]["initial_assignment_count"],
                "wave1_unassigned_count": payload["roster_policy"]["wave1_unassigned_count"],
                "wave2_unassigned_count": sum(
                    1
                    for row in payload["employees"]
                    if row["generation_wave"] == 2 and row["assignment"] is None
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
