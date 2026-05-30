"""Tests for the datamine parsing/mapping layer (pure functions + fake dir)."""

from __future__ import annotations

import json

import pytest

from wtdb.datamine import (
    CONFIG_SUBPATH,
    LANG_SUBPATH,
    _clean_name,
    build_record,
    detect_acquisition,
    econ_to_br,
    iter_aircraft_records,
    map_class,
)
from wtdb.schemas import AircraftIn


@pytest.mark.parametrize(
    "econ_rank,expected",
    [(0, 1.0), (1, 1.3), (2, 1.7), (3, 2.0), (11, 4.7), (12, 5.0), (13, 5.3), (39, 14.0)],
)
def test_econ_to_br(econ_rank, expected):
    assert econ_to_br(econ_rank) == expected


def test_map_class_priority():
    # jet_fighter must win over plain fighter when both tags present.
    assert map_class({"type_fighter": True, "type_jet_fighter": True}) == "jet_fighter"
    assert map_class({"type_assault": True}) == "attacker"
    assert map_class({"type_longrange_bomber": True}) == "bomber"
    assert map_class({"type_dive_bomber": True, "type_bomber": True}) == "dive_bomber"
    assert map_class({}) == "fighter"  # default


@pytest.mark.parametrize(
    "econ,expected",
    [
        ({}, "tech_tree"),
        ({"costGold": 1000}, "premium"),
        ({"gift": True}, "gift"),
        ({"event": "foo"}, "event"),
        ({"openCostGold": 500}, "squadron"),
        ({"purchaseTrophyGift": True}, "marketplace"),
        # priority: squadron beats premium when both present.
        ({"openCostGold": 1, "costGold": 1}, "squadron"),
    ],
)
def test_detect_acquisition(econ, expected):
    assert detect_acquisition(econ) == expected


def test_clean_name_strips_nbsp_and_decoration():
    assert _clean_name("Bf 109 F-4") == "Bf 109 F-4"
    assert _clean_name("◔Bf 109 F-4") == "Bf 109 F-4"
    assert _clean_name("P-51D-30​") == "P-51D-30"


def test_build_record_units_and_mapping():
    unit = {
        "tags": {"type_fighter": True, "country_usa": True},
        "Shop": {"maxSpeed": 200.0, "turnTime": 20.0, "climbSpeed": 22.0,
                 "wingLoading": 180.0, "powerToWeightRatio": 0.4, "rollRate": 100.0},
        "years_active": {"year1944": {}, "year1945": {}},
    }
    econ = {
        "rank": 4, "economicRankArcade": 11, "economicRankHistorical": 12,
        "economicRankSimulation": 13, "country": "country_usa", "reqExp": 46000,
        "value": 155000, "repairCostHistorical": 4606, "reqAir": "p-47d-28",
    }
    rec = build_record("p-51d-30", unit, econ, "2.55.1", name="P-51D-30 Mustang")
    assert rec["name"] == "P-51D-30 Mustang"
    assert rec["nation"] == "usa"
    assert rec["aircraft_class"] == "fighter"
    assert rec["max_speed_kmh"] == 720.0  # 200 m/s * 3.6
    assert rec["br_rb"] == 5.0
    assert rec["br_ab"] == 4.7
    assert rec["year"] == 1944  # earliest
    assert rec["rp_cost"] == 46000
    assert rec["req_air"] == "p-47d-28"
    # And it must validate.
    AircraftIn.model_validate(rec)


def _write_fake_datamine(root):
    cfg = root / CONFIG_SUBPATH
    lang = root / LANG_SUBPATH
    cfg.mkdir(parents=True)
    lang.mkdir(parents=True)
    unittags = {
        "bf-109f-4": {
            "tags": {"type_fighter": True, "country_germany": True},
            "Shop": {"maxSpeed": 184.7, "turnTime": 19.0, "climbSpeed": 20.0},
        },
        "tank_should_be_ignored": {"tags": {}},
    }
    wpcost = {
        "bf-109f-4": {"unitMoveType": "air", "rank": 3, "economicRankHistorical": 9,
                      "country": "country_germany"},
        "dummy_plane": {"unitMoveType": "air", "rank": 1},  # filtered by name
        "tank_should_be_ignored": {"unitMoveType": "tank", "rank": 1},
    }
    (cfg / "unittags.blkx").write_text(json.dumps(unittags), encoding="utf-8")
    (cfg / "wpcost.blkx").write_text(json.dumps(wpcost), encoding="utf-8")
    (lang / "units.csv").write_text(
        '"<ID>";"<English>"\n"bf-109f-4_0";"Bf 109 F-4"\n', encoding="utf-8"
    )


def test_iter_aircraft_records_filters_and_parses(tmp_path):
    _write_fake_datamine(tmp_path)
    recs = list(iter_aircraft_records(tmp_path, game_version="test"))
    assert len(recs) == 1  # tank + dummy filtered out
    r = recs[0]
    assert r["game_id"] == "bf-109f-4"
    assert r["name"] == "Bf 109 F-4"
    assert r["nation"] == "germany"
    assert r["br_rb"] == econ_to_br(9)
    assert r["data_source"] == "datamine"
    assert r["game_version"] == "test"
