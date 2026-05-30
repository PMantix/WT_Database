"""Pydantic v2 validation at the ingest boundary.

Every record — whether hand-entered YAML or scraped datamine JSON — passes
through ``AircraftIn`` before it touches the database. This keeps messy or
partial source data from silently corrupting the DB.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import ACQUISITION_TYPES, CLASSES


class AircraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    game_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    nation: str = Field(min_length=1, max_length=32)
    aircraft_class: str = Field(max_length=32)
    rank: int = Field(ge=1, le=10)
    acquisition: str = "tech_tree"
    year: int | None = Field(default=None, ge=1914, le=2100)

    br_ab: float | None = Field(default=None, ge=1.0, le=14.0)
    br_rb: float | None = Field(default=None, ge=1.0, le=14.0)
    br_sb: float | None = Field(default=None, ge=1.0, le=14.0)

    max_speed_kmh: float | None = Field(default=None, ge=0, le=4000)
    max_speed_alt_m: float | None = Field(default=None, ge=0, le=30000)
    climb_rate_ms: float | None = Field(default=None, ge=0, le=400)
    turn_time_s: float | None = Field(default=None, ge=0, le=120)
    wing_rip_kmh: float | None = Field(default=None, ge=0, le=2000)
    max_altitude_m: float | None = Field(default=None, ge=0, le=30000)

    mass_empty_kg: float | None = Field(default=None, ge=0, le=200000)
    mass_takeoff_kg: float | None = Field(default=None, ge=0, le=400000)
    wing_area_m2: float | None = Field(default=None, ge=0, le=1000)
    engine_power_hp: float | None = Field(default=None, ge=0, le=20000)
    engine_thrust_kgf: float | None = Field(default=None, ge=0, le=50000)
    engine_count: int | None = Field(default=None, ge=1, le=12)
    crew: int | None = Field(default=None, ge=1, le=20)

    armament: str | None = None
    notes: str | None = None

    data_source: str = "override"
    game_version: str | None = None

    @field_validator("nation")
    @classmethod
    def _norm_nation(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("aircraft_class")
    @classmethod
    def _check_class(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in CLASSES:
            raise ValueError(f"aircraft_class {v!r} not in {CLASSES}")
        return v

    @field_validator("acquisition")
    @classmethod
    def _check_acq(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ACQUISITION_TYPES:
            raise ValueError(f"acquisition {v!r} not in {ACQUISITION_TYPES}")
        return v

    @property
    def is_premium(self) -> int:
        return 1 if self.acquisition in ("premium", "marketplace", "gift") else 0
