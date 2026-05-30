"""Parse the War Thunder datamine (.blkx = JSON) into aircraft records.

Ground-truth source: gszabi99/War-Thunder-Datamine, cloned (sparse) into
``data/datamine``. Two files carry everything we need for the roster:

* ``unittags.blkx`` — per-unit ``type``, country/role tags, historical year,
  and a ``Shop`` block holding the in-game stat card (speed, turn, climb, ...).
* ``wpcost.blkx``   — economy (RP/SL/repair/crew costs), tech rank, the three
  ``economicRank*`` values (→ BR), country, and ``reqAir`` (tree prerequisite).

This module is pure parsing/mapping — no DB access. The pipeline validates the
dicts it returns and upserts them.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .config import DATAMINE_DIR

CONFIG_SUBPATH = "char.vromfs.bin_u/config"
LANG_SUBPATH = "lang.vromfs.bin_u/lang"

# Leading decoration glyphs (premium/squadron/event markers) + zero-width space
# that appear in localized names and should be stripped for display.
_NAME_JUNK = "◔◐●○◓◑★☆​ "

# --- vocab mappings ---------------------------------------------------------

COUNTRY_MAP = {
    "country_usa": "usa",
    "country_germany": "germany",
    "country_ussr": "ussr",
    "country_britain": "britain",
    "country_japan": "japan",
    "country_italy": "italy",
    "country_france": "france",
    "country_china": "china",
    "country_sweden": "sweden",
    "country_israel": "israel",
}

# Datamine ``type_*`` tags → our class vocabulary, most specific first.
CLASS_PRIORITY: list[tuple[str, str]] = [
    ("type_jet_bomber", "jet_bomber"),
    ("type_jet_fighter", "jet_fighter"),
    ("type_interceptor", "interceptor"),
    ("type_dive_bomber", "dive_bomber"),
    ("type_torpedo", "bomber"),
    ("type_longrange_bomber", "bomber"),
    ("type_frontline_bomber", "bomber"),
    ("type_light_bomber", "bomber"),
    ("type_bomber", "bomber"),
    ("type_strike_ucav", "attacker"),
    ("type_strike_aircraft", "attacker"),
    ("type_assault", "attacker"),
    ("type_aa_fighter", "fighter"),
    ("type_fighter", "fighter"),
]


def econ_to_br(economic_rank: int) -> float:
    """Convert a datamine economic rank (0-based int) to a display BR.

    BR steps go 1.0, 1.3, 1.7, 2.0, ... — three sub-steps per integer rank.
    Verified against known values (e.g. econ 12 -> 5.0).
    """
    base = 1.0 + (economic_rank // 3)
    frac = (0.0, 0.3, 0.7)[economic_rank % 3]
    return round(base + frac, 1)


def map_class(tags: dict) -> str:
    for tag, cls in CLASS_PRIORITY:
        if tags.get(tag):
            return cls
    return "fighter"  # sensible default; rare untagged units


def detect_acquisition(econ: dict) -> str:
    """Classify how a vehicle is obtained, from wpcost markers (priority order)."""
    if "openCostGold" in econ or "minOpenCostGold" in econ:
        return "squadron"
    if "event" in econ:
        return "event"
    if "gift" in econ or "purchaseTrophyGiftOnce" in econ:
        return "gift"
    if "costGold" in econ:
        return "premium"
    if "purchaseTrophyGift" in econ:
        return "marketplace"
    return "tech_tree"


def _shop_year(unit: dict) -> int | None:
    """Earliest ``yearNNNN`` key under years_active, if present."""
    ya = unit.get("years_active")
    if not isinstance(ya, dict):
        return None
    years = []
    for k in ya:
        if k.startswith("year") and k[4:].isdigit():
            years.append(int(k[4:]))
    return min(years) if years else None


def _clean_name(s: str) -> str:
    # Normalize the various non-breaking / zero-width spaces WT uses to plain
    # spaces, drop leading premium/squadron decoration glyphs, collapse runs.
    for ch in (" ", " ", " ", "​"):
        s = s.replace(ch, " " if ch != "​" else "")
    s = s.strip().strip(_NAME_JUNK)
    return " ".join(s.split())


def load_unit_names(datamine_dir: Path = DATAMINE_DIR) -> dict[str, str]:
    """Map ``game_id -> English display name`` from units.csv.

    Each unit has several keys (``<id>_0`` full name, ``<id>_shop`` short,
    ``<id>_1/_2`` abbreviations). We prefer the full ``_0`` name and fall back
    to ``_shop``. English is column index 1.
    """
    path = datamine_dir / LANG_SUBPATH / "units.csv"
    if not path.exists():
        return {}
    full: dict[str, str] = {}
    shop: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter=";", quotechar='"')
        next(reader, None)  # header
        for row in reader:
            if len(row) < 2:
                continue
            key, english = row[0], _clean_name(row[1])
            if not english:
                continue
            if key.endswith("_0"):
                full[key[:-2]] = english
            elif key.endswith("_shop"):
                shop[key[:-5]] = english
    return {**shop, **full}  # full (_0) wins over shop


def load_blkx(name: str, datamine_dir: Path = DATAMINE_DIR) -> dict:
    path = datamine_dir / CONFIG_SUBPATH / name
    if not path.exists():
        raise FileNotFoundError(
            f"Datamine file missing: {path}. Clone the repo into {datamine_dir} "
            "(see README / Phase 2)."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _f(x):
    """Coerce to float or None."""
    return float(x) if isinstance(x, (int, float)) else None


def _i(x):
    return int(x) if isinstance(x, (int, float)) else None


def _prettify_id(game_id: str) -> str:
    """Fallback display name when no localized name exists."""
    return game_id.replace("_", " ").replace("-", " ").upper()


def build_record(
    game_id: str, unit: dict, econ: dict, game_version: str | None, name: str | None = None
) -> dict:
    """Map one aircraft's datamine entries to an AircraftIn-shaped dict."""
    shop = unit.get("Shop", {}) if isinstance(unit.get("Shop"), dict) else {}
    tags = unit.get("tags", {}) if isinstance(unit.get("tags"), dict) else {}

    country = econ.get("country") or next(
        (t for t in tags if t in COUNTRY_MAP), None
    )
    nation = COUNTRY_MAP.get(country, "other")

    max_speed_ms = _f(shop.get("maxSpeed"))

    return {
        "game_id": game_id,
        "name": name or _prettify_id(game_id),
        "nation": nation,
        "aircraft_class": map_class(tags),
        "rank": int(econ.get("rank", 1)) or 1,
        "acquisition": detect_acquisition(econ),
        "year": _shop_year(unit),
        "br_ab": econ_to_br(econ["economicRankArcade"]) if "economicRankArcade" in econ else None,
        "br_rb": econ_to_br(econ["economicRankHistorical"]) if "economicRankHistorical" in econ else None,
        "br_sb": econ_to_br(econ["economicRankSimulation"]) if "economicRankSimulation" in econ else None,
        "max_speed_kmh": round(max_speed_ms * 3.6, 1) if max_speed_ms else None,
        "max_speed_alt_m": _f(shop.get("maxSpeedAlt")),
        "climb_rate_ms": _f(shop.get("climbSpeed")),
        "climb_time_s": _f(shop.get("climbTime")),
        "turn_time_s": _f(shop.get("turnTime")),
        "roll_rate_deg_s": _f(shop.get("rollRate")),
        "max_altitude_m": _f(shop.get("maxAltitude")),
        "wing_loading_kg_m2": _f(shop.get("wingLoading")),
        "power_to_weight_ratio": _f(shop.get("powerToWeightRatio")),
        "rp_cost": _i(econ.get("reqExp")),
        "sl_cost": _i(econ.get("value")),
        "repair_cost_ab": _i(econ.get("repairCostArcade")),
        "repair_cost_rb": _i(econ.get("repairCostHistorical")),
        "repair_cost_sb": _i(econ.get("repairCostSimulation")),
        "crew_train_sl": _i(econ.get("trainCost")),
        "expert_sl": _i(econ.get("train2Cost")),
        "ace_ge": _i(econ.get("train3Cost_gold")),
        "req_air": econ.get("reqAir"),
        "data_source": "datamine",
        "game_version": game_version,
    }


def iter_aircraft_records(
    datamine_dir: Path = DATAMINE_DIR, game_version: str | None = None
):
    """Yield AircraftIn-shaped dicts for every aircraft in the datamine."""
    unittags = load_blkx("unittags.blkx", datamine_dir)
    wpcost = load_blkx("wpcost.blkx", datamine_dir)
    names = load_unit_names(datamine_dir)

    for game_id, econ in wpcost.items():
        if not isinstance(econ, dict):
            continue
        if econ.get("unitMoveType") != "air":
            continue
        if game_id.startswith("dummy"):
            continue
        unit = unittags.get(game_id)
        if not isinstance(unit, dict):
            continue
        yield build_record(game_id, unit, econ, game_version, names.get(game_id))
