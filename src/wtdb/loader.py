"""Load hand-curated aircraft from YAML into the database.

This is the Phase-1 ingest path. The same validate-then-upsert pattern will be
reused by the datamine pipeline in Phase 2; the override YAML always wins, so
anything hand-fixed here survives a re-scrape.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml
from sqlalchemy import select

from .config import AIRCRAFT_OVERRIDES
from .db import get_session, init_db
from .models import Aircraft
from .schemas import AircraftIn


def _to_columns(rec: AircraftIn) -> dict:
    data = rec.model_dump()
    data["is_premium"] = rec.is_premium
    return data


def load_aircraft_yaml(path: Path = AIRCRAFT_OVERRIDES) -> tuple[int, int]:
    """Validate and upsert every aircraft in ``path``.

    Returns ``(inserted, updated)`` counts. Raises if any record fails
    validation, so a single typo can't half-load the file.
    """
    if not path.exists():
        raise FileNotFoundError(f"No override file at {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(raw, list):
        raise ValueError(f"{path} must contain a YAML list of aircraft, got {type(raw)}")

    # Validate everything up front (fail fast, all-or-nothing).
    records = [AircraftIn.model_validate(row) for row in raw]

    seen: set[str] = set()
    for r in records:
        if r.game_id in seen:
            raise ValueError(f"Duplicate game_id in YAML: {r.game_id!r}")
        seen.add(r.game_id)

    inserted = updated = 0
    with get_session() as session:
        for rec in records:
            cols = _to_columns(rec)
            existing = session.scalar(select(Aircraft).where(Aircraft.game_id == rec.game_id))
            if existing is None:
                session.add(Aircraft(**cols))
                inserted += 1
            else:
                for k, v in cols.items():
                    setattr(existing, k, v)
                updated += 1
        session.commit()

    return inserted, updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Load aircraft YAML into wt.db")
    parser.add_argument("path", nargs="?", default=str(AIRCRAFT_OVERRIDES))
    args = parser.parse_args()

    init_db()
    ins, upd = load_aircraft_yaml(Path(args.path))
    print(f"Loaded aircraft: {ins} inserted, {upd} updated.")


if __name__ == "__main__":
    main()
