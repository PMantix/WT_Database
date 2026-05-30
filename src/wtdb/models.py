"""SQLAlchemy ORM models.

Phase 1 keeps a single, denormalized ``aircraft`` table: it is the fastest path
to a working, chartable app, and it maps cleanly onto a pandas DataFrame for the
Streamlit layer. Battle ratings are stored as three columns (AB/RB/SB) rather
than a child table for the same reason — filtering and plotting stay trivial.

When the datamine scraper lands (Phase 2) and we add weapons, modifications and
per-patch history, those become their own tables/junctions referencing
``aircraft.game_id``. The columns here are a deliberate subset of that fuller
schema, chosen so nothing has to be thrown away later.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# Controlled vocabularies — kept loose (validated in Pydantic) so the datamine
# can introduce values we haven't seen without a migration.
ACQUISITION_TYPES = ("tech_tree", "premium", "event", "squadron", "gift", "marketplace")
CLASSES = (
    "fighter",
    "interceptor",
    "heavy_fighter",
    "strike_fighter",
    "attacker",
    "dive_bomber",
    "bomber",
    "jet_fighter",
    "jet_bomber",
)


class Aircraft(Base):
    __tablename__ = "aircraft"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Identity --------------------------------------------------------------
    # game_id mirrors the datamine internal id (e.g. "p-51d-30"); it is the
    # universal join key once scraping lands. Unique and required.
    game_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    nation: Mapped[str] = mapped_column(String(32), index=True)
    aircraft_class: Mapped[str] = mapped_column(String(32), index=True)
    rank: Mapped[int] = mapped_column(Integer, index=True)  # 1..8 (tech-tree rank)
    acquisition: Mapped[str] = mapped_column(String(16), default="tech_tree")
    is_premium: Mapped[int] = mapped_column(Integer, default=0)  # 0/1 convenience flag
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)  # historical year

    # Battle ratings (denormalized per mode) --------------------------------
    br_ab: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    br_rb: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    br_sb: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)

    # Flight performance (from datamine Shop block / overrides) -------------
    max_speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_speed_alt_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    climb_rate_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    climb_time_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    turn_time_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    roll_rate_deg_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    wing_rip_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_altitude_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Datamine provides these ratios directly (raw mass/area live in FM files,
    # parsed in a later phase), so store them natively.
    wing_loading_kg_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    power_to_weight_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Airframe / engine constants (filled from FM files in a later phase) ----
    mass_empty_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    mass_takeoff_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    wing_area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    engine_power_hp: Mapped[float | None] = mapped_column(Float, nullable=True)
    engine_thrust_kgf: Mapped[float | None] = mapped_column(Float, nullable=True)  # jets
    engine_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crew: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Economy (from wpcost.blkx) --------------------------------------------
    rp_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)        # reqExp
    sl_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)        # value (purchase SL)
    repair_cost_ab: Mapped[int | None] = mapped_column(Integer, nullable=True)
    repair_cost_rb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    repair_cost_sb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crew_train_sl: Mapped[int | None] = mapped_column(Integer, nullable=True)  # trainCost
    expert_sl: Mapped[int | None] = mapped_column(Integer, nullable=True)      # train2Cost
    ace_ge: Mapped[int | None] = mapped_column(Integer, nullable=True)         # train3Cost_gold
    req_air: Mapped[str | None] = mapped_column(String(64), nullable=True)     # tech-tree prereq

    # Armament summary (free text; optional) --------------------------------
    armament: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Firepower (computed from FM commonWeapons + gun files) -----------------
    gun_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cannon_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mg_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_caliber_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    burst_mass_kg_s: Mapped[float | None] = mapped_column(Float, nullable=True)  # throw weight/sec
    total_ammo: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Personal layer --------------------------------------------------------
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Provenance ------------------------------------------------------------
    data_source: Mapped[str] = mapped_column(String(32), default="override")
    game_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        CheckConstraint("is_premium in (0,1)", name="ck_aircraft_is_premium_bool"),
        CheckConstraint("rank between 1 and 10", name="ck_aircraft_rank_range"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Aircraft {self.game_id!r} {self.name!r} {self.nation} BR(rb)={self.br_rb}>"
