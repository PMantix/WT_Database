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


@pytest.mark.skipif(not DB_PATH.exists(), reason="wt.db not built yet")
@pytest.mark.parametrize("chart_index", [0, 1, 2])  # Scatter, Ranking, Parallel
def test_app_each_chart_type_runs(chart_index):
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    # The chart-type radio is the one whose options start with "Scatter".
    chart_radio = next(
        (r for r in at.radio if r.options and r.options[0].startswith("Scatter")), None
    )
    assert chart_radio is not None, "chart-type radio not found"
    chart_radio.set_value(chart_radio.options[chart_index]).run()
    assert not at.exception, f"Chart '{chart_radio.options[chart_index]}' raised: {at.exception}"


@pytest.mark.skipif(not DB_PATH.exists(), reason="wt.db not built yet")
def test_app_3d_toggle_runs():
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    cb = next((c for c in at.checkbox if "3D" in (c.label or "")), None)
    assert cb is not None, "3D checkbox not found"
    cb.set_value(True).run()
    assert not at.exception, f"3D scatter raised: {at.exception}"


@pytest.mark.skipif(not DB_PATH.exists(), reason="wt.db not built yet")
def test_app_highlight_and_matchup_runs():
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    # The scatter highlight multiselect is the one whose label has the magnifier.
    hi = next((m for m in at.multiselect if "highlight" in (m.label or "").lower()), None)
    assert hi is not None, "highlight multiselect not found"
    if len(hi.options) >= 2:
        hi.set_value([hi.options[0], hi.options[1]]).run()  # triggers matchup notes
    assert not at.exception, f"Highlight/matchup raised: {at.exception}"
