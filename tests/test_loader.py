"""Loader + schema validation tests against an isolated temp database."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from wtdb.models import Aircraft, Base
from wtdb.schemas import AircraftIn


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(engine)
    Sess = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    with Sess() as s:
        yield s


def test_schema_accepts_minimal_valid():
    rec = AircraftIn(
        game_id="test-1", name="Test", nation="USA",
        aircraft_class="fighter", rank=3, br_rb=4.0,
    )
    assert rec.nation == "usa"  # normalized lowercase
    assert rec.is_premium == 0


def test_schema_premium_flag_derived():
    rec = AircraftIn(
        game_id="p-1", name="Prem", nation="germany",
        aircraft_class="fighter", rank=4, acquisition="premium",
    )
    assert rec.is_premium == 1


def test_schema_rejects_bad_class():
    with pytest.raises(ValidationError):
        AircraftIn(game_id="x", name="X", nation="usa", aircraft_class="spaceship", rank=1)


def test_schema_gun_layout_validation():
    ok = AircraftIn(game_id="x", name="X", nation="usa", aircraft_class="fighter",
                    rank=1, gun_layout="Nose")
    assert ok.gun_layout == "nose"  # normalized
    with pytest.raises(ValidationError):
        AircraftIn(game_id="x", name="X", nation="usa", aircraft_class="fighter",
                   rank=1, gun_layout="turret")


def test_schema_rejects_out_of_range_br():
    with pytest.raises(ValidationError):
        AircraftIn(game_id="x", name="X", nation="usa", aircraft_class="fighter", rank=1, br_rb=99)


def test_schema_forbids_unknown_field():
    with pytest.raises(ValidationError):
        AircraftIn(
            game_id="x", name="X", nation="usa", aircraft_class="fighter",
            rank=1, typo_field=123,
        )


def test_load_and_upsert(tmp_path, monkeypatch, session):
    # Point the loader at our temp session.
    import wtdb.loader as loader

    monkeypatch.setattr(loader, "get_session", lambda: session)

    yaml_path = Path(tmp_path) / "a.yaml"
    yaml_path.write_text(textwrap.dedent("""
        - game_id: bf-109f-4
          name: "Bf 109 F-4"
          nation: germany
          aircraft_class: fighter
          rank: 3
          br_rb: 4.0
          max_speed_kmh: 634
          turn_time_s: 19.0
        - game_id: spitfire-mk9
          name: "Spitfire F Mk IX"
          nation: britain
          aircraft_class: fighter
          rank: 3
          br_rb: 5.0
    """), encoding="utf-8")

    ins, upd = loader.load_aircraft_yaml(yaml_path)
    assert (ins, upd) == (2, 0)
    assert session.scalar(select(func.count()).select_from(Aircraft)) == 2

    # Re-loading the same file updates, never duplicates.
    ins2, upd2 = loader.load_aircraft_yaml(yaml_path)
    assert (ins2, upd2) == (0, 2)
    assert session.scalar(select(func.count()).select_from(Aircraft)) == 2


def test_duplicate_game_id_rejected(tmp_path, monkeypatch, session):
    import wtdb.loader as loader

    monkeypatch.setattr(loader, "get_session", lambda: session)
    yaml_path = Path(tmp_path) / "dup.yaml"
    yaml_path.write_text(textwrap.dedent("""
        - {game_id: dup, name: A, nation: usa, aircraft_class: fighter, rank: 1}
        - {game_id: dup, name: B, nation: usa, aircraft_class: fighter, rank: 1}
    """), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate game_id"):
        loader.load_aircraft_yaml(yaml_path)
