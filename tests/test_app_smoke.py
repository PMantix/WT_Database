"""Headless smoke test: the Streamlit app runs end-to-end without exceptions.

Uses Streamlit's AppTest harness, which executes app/app.py in a simulated
runtime. Requires wt.db to exist (run `uv run python -m wtdb.loader` first).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from wtdb.config import DB_PATH

APP = Path(__file__).resolve().parents[1] / "app" / "app.py"


@pytest.mark.skipif(not DB_PATH.exists(), reason="wt.db not built yet")
def test_app_runs_without_exception():
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception, f"App raised: {at.exception}"
    # Title renders.
    assert any("War Thunder Aircraft Explorer" in (m.value or "") for m in at.title)


@pytest.mark.skipif(not DB_PATH.exists(), reason="wt.db not built yet")
def test_app_runs_with_radar_selection():
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    if at.multiselect:
        # Select two aircraft in the comparison radar (last multiselect on page).
        ms = at.multiselect[-1]
        opts = ms.options
        if len(opts) >= 2:
            ms.set_value([opts[0], opts[1]]).run()
    assert not at.exception, f"App raised on interaction: {at.exception}"
