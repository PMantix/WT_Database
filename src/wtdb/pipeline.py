"""Full ingest pipeline: datamine -> validate -> merge overrides -> rebuild DB.

Run with:  uv run python -m wtdb.pipeline

The datamine is the authoritative roster. Hand-curated overrides in
``data/overrides/aircraft.yaml`` are applied last (field-level, override wins);
override rows whose ``game_id`` isn't in the datamine are inserted as
hand-added aircraft and must carry the core identity fields.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from pydantic import ValidationError

from .config import AIRCRAFT_OVERRIDES, DATAMINE_DIR
from .datamine import iter_aircraft_records
from .db import engine, get_session, init_db
from .models import Aircraft
from .schemas import AircraftIn, AircraftOverride


def detect_game_version(datamine_dir: Path = DATAMINE_DIR) -> str | None:
    """Best-effort patch identifier: the datamine's git tag or short commit."""
    for cmd in (
        ["git", "-C", str(datamine_dir), "describe", "--tags", "--abbrev=0"],
        ["git", "-C", str(datamine_dir), "rev-parse", "--short", "HEAD"],
    ):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def _finalize(d: dict) -> dict:
    """Add the derived is_premium flag from the final acquisition value."""
    d["is_premium"] = 0 if d.get("acquisition", "tech_tree") == "tech_tree" else 1
    return d


def run(
    datamine_dir: Path = DATAMINE_DIR,
    overrides_path: Path = AIRCRAFT_OVERRIDES,
    verbose: bool = True,
) -> dict:
    """Rebuild the aircraft table from datamine + overrides. Returns a summary."""
    version = detect_game_version(datamine_dir)
    if verbose:
        print(f"Datamine version: {version or 'unknown'}")

    # 1. Datamine -> validated records keyed by game_id.
    records: dict[str, dict] = {}
    parse_failures: list[tuple[str, str]] = []
    for raw in iter_aircraft_records(datamine_dir, version):
        try:
            rec = AircraftIn.model_validate(raw)
        except ValidationError as e:
            parse_failures.append((raw.get("game_id", "?"), str(e).splitlines()[0]))
            continue
        records[rec.game_id] = rec.model_dump()
    if verbose:
        print(f"Datamine aircraft validated: {len(records)} "
              f"({len(parse_failures)} skipped)")

    # 2. Apply overrides.
    patched = added = 0
    override_errors: list[tuple[str, str]] = []
    if overrides_path.exists():
        rows = yaml.safe_load(overrides_path.read_text(encoding="utf-8")) or []
        for row in rows:
            gid = row.get("game_id") if isinstance(row, dict) else None
            if not gid:
                override_errors.append(("?", "missing game_id"))
                continue
            if gid in records:
                try:
                    ov = AircraftOverride.model_validate(row)
                except ValidationError as e:
                    override_errors.append((gid, str(e).splitlines()[0]))
                    continue
                patch = ov.model_dump(exclude_unset=True, exclude={"game_id"})
                if patch:
                    records[gid].update(patch)
                    records[gid]["data_source"] = "datamine+override"
                    patched += 1
            else:
                # Hand-added aircraft not in datamine — needs full identity.
                try:
                    rec = AircraftIn.model_validate(row)
                except ValidationError as e:
                    override_errors.append((gid, str(e).splitlines()[0]))
                    continue
                records[gid] = rec.model_dump()
                records[gid]["data_source"] = "override"
                added += 1
    if verbose:
        print(f"Overrides: {patched} patched, {added} hand-added, "
              f"{len(override_errors)} errors")

    # 3. Rebuild table.
    init_db()
    with get_session() as session:
        session.query(Aircraft).delete()
        session.bulk_insert_mappings(
            Aircraft.__mapper__, [_finalize(d) for d in records.values()]
        )
        session.commit()

    summary = {
        "version": version,
        "total": len(records),
        "datamine": len(records) - added,
        "patched": patched,
        "added": added,
        "parse_failures": parse_failures,
        "override_errors": override_errors,
    }
    if verbose:
        print(f"Rebuilt wt.db: {summary['total']} aircraft "
              f"(engine={engine.url}).")
        for gid, msg in (parse_failures + override_errors)[:10]:
            print(f"  ! {gid}: {msg}")
    return summary


if __name__ == "__main__":
    run()
