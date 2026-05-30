# WT Database — War Thunder Aircraft Stats & Analysis

A portable, local, single-user database and interactive app for War Thunder
aircraft. Built to answer three questions while you play:

- **What should I fly?** — match aircraft to your playstyle at a chosen BR.
- **What should I grind toward?** — research/economy efficiency and "hidden gems".
- **What changed this patch?** — BR, flight-model, and economy diffs over time.

No servers, no cloud — just a folder, a SQLite file, and a Streamlit app.

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.12 (via [`uv`](https://docs.astral.sh/uv/)) |
| Database | SQLite (WAL, foreign keys on) |
| Models / validation | SQLAlchemy 2.0 + Pydantic v2 |
| App / charts | Streamlit + Plotly |
| Ground-truth data (Phase 2) | `gszabi99/War-Thunder-Datamine` (`.blkx` = JSON, git-tagged per patch) |

## Quick start

```bash
uv sync                              # install deps + the wtdb package (editable)
uv run python -m wtdb.loader         # build wt.db and load seed aircraft
uv run streamlit run app/app.py      # open http://localhost:8501
uv run pytest -q                     # run the test suite
```

> **Note:** the system `python` on this machine is an ancient 3.4. Always use
> `uv run …` — never bare `python`.

## Layout

```
src/wtdb/          # the package
  config.py        #   paths + central config
  models.py        #   SQLAlchemy ORM (aircraft table)
  schemas.py       #   Pydantic ingest validation
  db.py            #   engine, sessions, PRAGMAs, DataFrame helper
  loader.py        #   YAML -> validate -> upsert
app/app.py         # Streamlit explorer (filters, scatter, radar, table)
data/overrides/    # hand-curated / corrected data (always wins over scrape)
data/raw/          # cached scraper output (gitignored)
tests/             # pytest (loader, schema, headless app smoke test)
wt.db              # the database (gitignored — rebuild with the loader)
```

## Data sources & legality

The Phase-2 pipeline reads the community datamine (reverse-engineered game
files). Use is **personal/research only** — do not republish as official Gaijin
data or redistribute game assets. `data/overrides/aircraft.yaml` is merged last
and authoritative, so anything you hand-correct survives a re-scrape.

## Roadmap

- **Phase 0** ✅ environment + skeleton
- **Phase 1** ✅ schema + seed data + working app (filters, speed-vs-turn scatter, compare radar)
- **Phase 2** datamine scraper → full roster (no UI change)
- **Phase 3** per-patch versioning + change-diff page
- **Phase 4** gameplay analysis: playstyle archetype classifier, BR recommender,
  uptier briefing, matchup advisor, hidden-gem & economy scores
