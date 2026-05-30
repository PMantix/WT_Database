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

    br_ab: float | None = Field(default=None, ge=1.0, le=15.0)
    br_rb: float | None = Field(default=None, ge=1.0, le=15.0)
    br_sb: float | None = Field(default=None, ge=1.0, le=15.0)

    max_speed_kmh: float | None = Field(default=None, ge=0, le=4000)
    max_speed_alt_m: float | None = Field(default=None, ge=0, le=30000)
    climb_rate_ms: float | None = Field(default=None, ge=0, le=400)
    climb_time_s: float | None = Field(default=None, ge=0, le=12000)
    turn_time_s: float | None = Field(default=None, ge=0, le=300)
    roll_rate_deg_s: float | None = Field(default=None, ge=0, le=1000)
    wing_rip_kmh: float | None = Field(default=None, ge=0, le=2000)
    max_altitude_m: float | None = Field(default=None, ge=0, le=40000)
    wing_loading_kg_m2: float | None = Field(default=None, ge=0, le=2000)
    power_to_weight_ratio: float | None = Field(default=None, ge=0, le=10)

    mass_empty_kg: float | None = Field(default=None, ge=0, le=400000)
    mass_takeoff_kg: float | None = Field(default=None, ge=0, le=600000)
    wing_area_m2: float | None = Field(default=None, ge=0, le=2000)
    engine_power_hp: float | None = Field(default=None, ge=0, le=40000)
    engine_thrust_kgf: float | None = Field(default=None, ge=0, le=100000)
    engine_count: int | None = Field(default=None, ge=1, le=12)
    crew: int | None = Field(default=None, ge=1, le=20)

    rp_cost: int | None = Field(default=None, ge=0)
    sl_cost: int | None = Field(default=None, ge=0)
    repair_cost_ab: int | None = Field(default=None, ge=0)
    repair_cost_rb: int | None = Field(default=None, ge=0)
    repair_cost_sb: int | None = Field(default=None, ge=0)
    crew_train_sl: int | None = Field(default=None, ge=0)
    expert_sl: int | None = Field(default=None, ge=0)
    ace_ge: int | None = Field(default=None, ge=0)
    req_air: str | None = None

    armament: str | None = None

    gun_count: int | None = Field(default=None, ge=0, le=60)
    cannon_count: int | None = Field(default=None, ge=0, le=60)
    mg_count: int | None = Field(default=None, ge=0, le=60)
    max_caliber_mm: float | None = Field(default=None, ge=0, le=500)
    burst_mass_kg_s: float | None = Field(default=None, ge=0, le=500)
    total_ammo: int | None = Field(default=None, ge=0)

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
        # Any non-tech-tree acquisition counts as "special" for filtering.
        return 0 if self.acquisition == "tech_tree" else 1


class AircraftOverride(BaseModel):
    """Field-level correction/annotation keyed by datamine ``game_id``.

    Everything except ``game_id`` is optional; only the fields you set are
    applied on top of the datamine record (use ``model_dump(exclude_unset=True)``
    so unset fields don't blank out scraped values). For hand-added aircraft not
    in the datamine, you must supply the core identity fields too.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    game_id: str = Field(min_length=1, max_length=64)
    name: str | None = None
    nation: str | None = None
    aircraft_class: str | None = None
    rank: int | None = Field(default=None, ge=1, le=10)
    acquisition: str | None = None
    year: int | None = Field(default=None, ge=1914, le=2100)

    br_ab: float | None = Field(default=None, ge=1.0, le=15.0)
    br_rb: float | None = Field(default=None, ge=1.0, le=15.0)
    br_sb: float | None = Field(default=None, ge=1.0, le=15.0)

    max_speed_kmh: float | None = Field(default=None, ge=0, le=4000)
    max_speed_alt_m: float | None = Field(default=None, ge=0, le=30000)
    climb_rate_ms: float | None = Field(default=None, ge=0, le=400)
    turn_time_s: float | None = Field(default=None, ge=0, le=300)
    wing_rip_kmh: float | None = Field(default=None, ge=0, le=2000)

    armament: str | None = None
    notes: str | None = None

    @field_validator("nation")
    @classmethod
    def _norm_nation(cls, v: str | None) -> str | None:
        return v.strip().lower() if v else v

    @field_validator("aircraft_class")
    @classmethod
    def _check_class(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in CLASSES:
            raise ValueError(f"aircraft_class {v!r} not in {CLASSES}")
        return v

    @field_validator("acquisition")
    @classmethod
    def _check_acq(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in ACQUISITION_TYPES:
            raise ValueError(f"acquisition {v!r} not in {ACQUISITION_TYPES}")
        return v
