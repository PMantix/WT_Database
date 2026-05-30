"""Compute per-aircraft firepower from the datamine flight-model + weapon files.

Each aircraft FM file (``flightmodels/<game_id>.blkx``) lists its built-in guns
under ``commonWeapons.Weapon[]``; every entry references a gun definition
(``weapons/<gun>.blkx``) carrying ``shotFreq`` (rounds/sec) and a ``bullet`` list
whose first entry gives projectile ``mass`` (kg) and ``caliber`` (m).

The headline metric is **burst mass** — kilograms of projectile thrown per second
with all guns firing: ``Σ shotFreq × bullet_mass``. It captures count, fire rate,
and shell weight in one number, which is how the community compares firepower.

Forward-firing guns only: defensive turret mounts (``*_turret`` files / turret
triggers) are excluded.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .config import DATAMINE_DIR

FM_SUBPATH = "aces.vromfs.bin_u/gamedata/flightmodels"
WEAPONS_SUBPATH = "aces.vromfs.bin_u/gamedata/weapons"

CANNON_MIN_MM = 20.0  # >= this caliber counts as a cannon, else a machine gun


def _gun_filename(blk_ref: str) -> str:
    """'gameData/Weapons/cannonMG15120.blk' -> 'cannonmg15120.blkx'."""
    base = blk_ref.replace("\\", "/").rsplit("/", 1)[-1]
    base = base.lower()
    if base.endswith(".blk"):
        base = base[:-4] + ".blkx"
    return base


def _is_offensive_gun(blk_ref: str, trigger: str) -> bool:
    """True for forward-firing guns; excludes turrets, rockets, bombs, torpedoes."""
    p = blk_ref.replace("\\", "/").lower()
    if "weapons/" not in p:
        return False
    if any(s in p for s in ("rocketguns", "bombguns", "torpedo", "turret", "_aam", "missile")):
        return False
    trig = (trigger or "").lower()
    return "turret" not in trig and "gunner" not in trig


@lru_cache(maxsize=2048)
def _parse_gun(weapons_dir_str: str, filename: str) -> tuple[float, float, float] | None:
    """Return (caliber_mm, shot_freq_rps, bullet_mass_kg) for a gun file, or None."""
    path = Path(weapons_dir_str) / filename
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    shot_freq = d.get("shotFreq")
    bullet = d.get("bullet")
    if isinstance(bullet, list) and bullet:
        bullet = bullet[0]
    if not isinstance(bullet, dict) or not isinstance(shot_freq, (int, float)):
        return None
    caliber_m = bullet.get("caliber")
    mass = bullet.get("mass")
    if not isinstance(caliber_m, (int, float)) or not isinstance(mass, (int, float)):
        return None
    return (round(caliber_m * 1000, 1), float(shot_freq), float(mass))


def _as_list(x):
    if isinstance(x, list):
        return [e for e in x if isinstance(e, dict)]
    return [x] if isinstance(x, dict) else []


def _collect_named_presets(obj, out: dict):
    """Index every ``WeaponPreset`` block by name -> list of Weapon dicts."""
    if isinstance(obj, dict):
        wp = obj.get("WeaponPreset")
        if isinstance(wp, dict) and "name" in wp:
            out.setdefault(wp["name"], _as_list(wp.get("Weapon")))
        for v in obj.values():
            _collect_named_presets(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_named_presets(v, out)


def _common_weapon_refs(obj):
    """Yield the Weapon entries directly under any ``commonWeapons`` block."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "commonWeapons" and isinstance(v, dict):
                yield from _as_list(v.get("Weapon"))
            else:
                yield from _common_weapon_refs(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _common_weapon_refs(v)


def _resolve_guns(fm: dict):
    """Yield gun Weapon dicts, expanding ``preset`` references (e.g. default_common)."""
    presets: dict = {}
    _collect_named_presets(fm, presets)
    for ref in _common_weapon_refs(fm):
        if ref.get("blk"):
            yield ref
        elif ref.get("preset") in presets:
            yield from presets[ref["preset"]]


def firepower_for(game_id: str, datamine_dir: Path = DATAMINE_DIR) -> dict | None:
    """Compute firepower metrics for one aircraft, or None if no FM file."""
    fm_path = datamine_dir / FM_SUBPATH / f"{game_id}.blkx"
    if not fm_path.exists():
        return None
    try:
        fm = json.loads(fm_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    weapons_dir = str(datamine_dir / WEAPONS_SUBPATH)
    burst = 0.0
    total_ammo = 0
    cannons = mgs = 0
    max_cal = 0.0
    for w in _resolve_guns(fm):
        blk = w.get("blk", "")
        if not blk or not _is_offensive_gun(blk, w.get("trigger", "")):
            continue
        gun = _parse_gun(weapons_dir, _gun_filename(blk))
        if gun is None:
            continue
        caliber_mm, shot_freq, mass = gun
        burst += shot_freq * mass
        total_ammo += int(w.get("bullets") or 0)
        max_cal = max(max_cal, caliber_mm)
        if caliber_mm >= CANNON_MIN_MM:
            cannons += 1
        else:
            mgs += 1

    gun_count = cannons + mgs
    if gun_count == 0:
        return {
            "gun_count": 0, "cannon_count": 0, "mg_count": 0,
            "max_caliber_mm": None, "burst_mass_kg_s": None, "total_ammo": None,
        }
    return {
        "gun_count": gun_count,
        "cannon_count": cannons,
        "mg_count": mgs,
        "max_caliber_mm": round(max_cal, 1),
        "burst_mass_kg_s": round(burst, 3),
        "total_ammo": total_ammo or None,
    }


def load_firepower(game_ids, datamine_dir: Path = DATAMINE_DIR) -> dict[str, dict]:
    """Map game_id -> firepower dict for all given ids that have an FM file."""
    out: dict[str, dict] = {}
    for gid in game_ids:
        fp = firepower_for(gid, datamine_dir)
        if fp is not None:
            out[gid] = fp
    return out
