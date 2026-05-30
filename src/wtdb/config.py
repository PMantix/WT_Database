"""Project paths and central configuration.

Everything is resolved relative to the project root so the whole thing stays a
portable folder — clone it anywhere and it just works.
"""

from __future__ import annotations

from pathlib import Path

# src/wtdb/config.py -> project root is three parents up.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

DATA_DIR: Path = PROJECT_ROOT / "data"
OVERRIDES_DIR: Path = DATA_DIR / "overrides"
RAW_DIR: Path = DATA_DIR / "raw"
DATAMINE_DIR: Path = DATA_DIR / "datamine"

# SQLite lives at the project root as a single portable file.
DB_PATH: Path = PROJECT_ROOT / "wt.db"
DB_URL: str = f"sqlite:///{DB_PATH}"

# Hand-curated seed / override data.
AIRCRAFT_OVERRIDES: Path = OVERRIDES_DIR / "aircraft.yaml"

# Game-mode keys used consistently across the codebase.
MODES = ("ab", "rb", "sb")  # Arcade, Realistic, Simulator


def ensure_dirs() -> None:
    """Create the data directories if they don't exist yet."""
    for d in (DATA_DIR, OVERRIDES_DIR, RAW_DIR, DATAMINE_DIR):
        d.mkdir(parents=True, exist_ok=True)
