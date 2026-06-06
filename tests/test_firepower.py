"""Tests for firepower computation against a fake datamine tree."""

from __future__ import annotations

import json

import pytest

from wtdb.firepower import (
    FM_SUBPATH,
    WEAPONS_SUBPATH,
    _gun_filename,
    _is_offensive_gun,
    firepower_for,
)


@pytest.mark.parametrize(
    "ref,expected",
    [
        ("gameData/Weapons/gunMG17.blk", "gunmg17.blkx"),
        ("gameData/Weapons/cannonMG15120.blk", "cannonmg15120.blkx"),
    ],
)
def test_gun_filename(ref, expected):
    assert _gun_filename(ref) == expected


def test_is_offensive_gun():
    assert _is_offensive_gun("gameData/Weapons/gunMG17.blk", "machine gun")
    assert not _is_offensive_gun("gameData/Weapons/gunMG17_turret.blk", "turret")
    assert not _is_offensive_gun("gameData/Weapons/rocketGuns/uk_hvar.blk", "rockets")
    assert not _is_offensive_gun("gameData/Weapons/bombGuns/us_500lb.blk", "")


def _fake_tree(root):
    fm = root / FM_SUBPATH
    wp = fm / "weaponPresets"
    wdir = root / WEAPONS_SUBPATH
    fm.mkdir(parents=True)
    wp.mkdir(parents=True)
    wdir.mkdir(parents=True)
    # A 12.7mm MG firing 13 rps, 0.04 kg, 880 m/s; and a 20mm cannon, 10 rps, 0.1 kg, 800 m/s.
    (wdir / "gunbrowning.blkx").write_text(json.dumps(
        {"shotFreq": 13.0, "bullet": [{"caliber": 0.0127, "mass": 0.04, "speed": 880.0}]}),
        encoding="utf-8")
    (wdir / "cannon20.blkx").write_text(json.dumps(
        {"shotFreq": 10.0, "bullet": [{"caliber": 0.020, "mass": 0.10, "speed": 800.0}]}),
        encoding="utf-8")
    return fm


def test_inline_common_weapons(tmp_path):
    fm = _fake_tree(tmp_path)
    (fm / "inline.blkx").write_text(json.dumps({
        "commonWeapons": {"Weapon": [
            {"trigger": "machine gun", "blk": "gameData/Weapons/gunBrowning.blk", "bullets": 500},
            {"trigger": "cannon", "blk": "gameData/Weapons/cannon20.blk", "bullets": 150},
        ]}
    }), encoding="utf-8")
    fp = firepower_for("inline", tmp_path)
    assert fp["gun_count"] == 2
    assert fp["cannon_count"] == 1 and fp["mg_count"] == 1
    assert fp["max_caliber_mm"] == 20.0
    assert fp["total_ammo"] == 650
    # burst = 13*0.04 + 10*0.10 = 0.52 + 1.0 = 1.52
    assert fp["burst_mass_kg_s"] == pytest.approx(1.52, abs=1e-6)
    # Quality split: cannon (20mm) vs MG (12.7mm).
    assert fp["cannon_burst_kg_s"] == pytest.approx(1.0, abs=1e-6)
    assert fp["mg_burst_kg_s"] == pytest.approx(0.52, abs=1e-6)
    # Main gun = the 20mm: velocity 800, fire time = 150 rds / 10 rps = 15 s.
    assert fp["main_gun_velocity_ms"] == 800
    assert fp["main_gun_seconds"] == pytest.approx(15.0, abs=1e-6)


def test_preset_reference_resolution(tmp_path):
    """commonWeapons -> {preset: 'default_common'} must expand to the named preset."""
    fm = _fake_tree(tmp_path)
    (fm / "preset.blkx").write_text(json.dumps({
        "commonWeapons": {"Weapon": {"slot": 0, "preset": "default_common"}},
        "weaponSlots": {"slot": [{"index": 0, "WeaponPreset": {
            "name": "default_common",
            "Weapon": [
                {"trigger": "machine gun", "blk": "gameData/Weapons/gunBrowning.blk", "bullets": 400},
                {"trigger": "machine gun", "blk": "gameData/Weapons/gunBrowning.blk", "bullets": 400},
            ],
        }}]},
    }), encoding="utf-8")
    fp = firepower_for("preset", tmp_path)
    assert fp["gun_count"] == 2 and fp["mg_count"] == 2
    assert fp["total_ammo"] == 800
    assert fp["burst_mass_kg_s"] == pytest.approx(2 * 13 * 0.04, abs=1e-6)


def test_turrets_excluded_and_no_fm(tmp_path):
    fm = _fake_tree(tmp_path)
    (fm / "bomber.blkx").write_text(json.dumps({
        "commonWeapons": {"Weapon": [
            {"trigger": "turret", "blk": "gameData/Weapons/gunBrowning_turret.blk", "bullets": 1000},
        ]}
    }), encoding="utf-8")
    fp = firepower_for("bomber", tmp_path)
    assert fp["gun_count"] == 0 and fp["burst_mass_kg_s"] is None
    assert firepower_for("does_not_exist", tmp_path) is None
