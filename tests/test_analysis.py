"""Tests for the response-surface fitter."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from wtdb.analysis import CATEGORY_ORDER, categorize, response_surface, threat_board


def test_plane_fit_recovers_exact_plane():
    # z = 2x + 3y + 1 exactly -> plane fit should be perfect.
    rng = [(a, b) for a in range(6) for b in range(6)]
    df = pd.DataFrame(rng, columns=["x", "y"])
    df["z"] = 2 * df["x"] + 3 * df["y"] + 1
    res = response_surface(df, "x", "y", "z", degree=1, grid=10)
    assert res is not None
    gx, gy, gz, r2 = res
    assert r2 == pytest.approx(1.0, abs=1e-9)
    # Surface value at (x=5, y=5) ~ 2*5+3*5+1 = 26
    assert gz[-1, -1] == pytest.approx(26.0, abs=1e-6)


def test_quadratic_fit_beats_plane_on_curved_data():
    rng = [(a, b) for a in range(7) for b in range(7)]
    df = pd.DataFrame(rng, columns=["x", "y"])
    df["z"] = df["x"] ** 2 + df["y"] ** 2  # bowl
    plane = response_surface(df, "x", "y", "z", degree=1)
    quad = response_surface(df, "x", "y", "z", degree=2)
    assert quad[3] > plane[3]          # higher R²
    assert quad[3] == pytest.approx(1.0, abs=1e-6)


def test_cubic_recovers_cubic_data():
    rng = [(a, b) for a in range(8) for b in range(8)]
    df = pd.DataFrame(rng, columns=["x", "y"])
    df["z"] = df["x"] ** 3 - 2 * df["y"] ** 2 + df["x"] * df["y"]
    cubic = response_surface(df, "x", "y", "z", degree=3)
    quad = response_surface(df, "x", "y", "z", degree=2)
    assert cubic[3] == pytest.approx(1.0, abs=1e-6)  # cubic fits exactly
    assert cubic[3] > quad[3]


def test_high_degree_well_conditioned_on_large_values():
    # Speed-like magnitudes (~2000) with a quartic must not blow up numerically.
    rng = [(200 * a, 50 * b) for a in range(10) for b in range(10)]
    df = pd.DataFrame(rng, columns=["x", "y"])
    df["z"] = 1e-6 * df["x"] ** 2 + df["y"]
    res = response_surface(df, "x", "y", "z", degree=4)
    assert res is not None
    assert np.isfinite(res[2]).all()       # surface grid is all finite
    assert res[3] == pytest.approx(1.0, abs=1e-3)


def test_too_few_points_returns_none():
    df = pd.DataFrame({"x": [1.0, 2.0], "y": [1.0, 2.0], "z": [1.0, 2.0]})
    assert response_surface(df, "x", "y", "z", degree=2) is None  # needs >= 6 terms
    assert response_surface(df, "x", "y", "z", degree=1) is None  # 2 pts < 3 terms
    # Exactly enough points for a plane (3 terms) fits.
    df3 = pd.DataFrame({"x": [0.0, 1.0, 0.0], "y": [0.0, 0.0, 1.0], "z": [1.0, 3.0, 4.0]})
    assert response_surface(df3, "x", "y", "z", degree=1) is not None



def test_grid_shape_and_axes():
    df = pd.DataFrame({"x": np.arange(10.0), "y": np.arange(10.0), "z": np.arange(10.0)})
    gx, gy, gz, _ = response_surface(df, "x", "y", "z", degree=1, grid=20)
    assert gx.shape == (20,) and gy.shape == (20,)
    assert gz.shape == (20, 20)  # (len(gy), len(gx))


# --- Threat Board -----------------------------------------------------------

@pytest.mark.parametrize("e,m,expected", [
    (1.0, 1.0, "prey"),
    (1.0, 0.0, "out_energy"),
    (1.0, -1.0, "out_energy"),
    (0.0, 1.0, "out_turn"),
    (-1.0, 1.0, "out_turn"),
    (0.0, 0.0, "near_peer"),
    (-1.0, -1.0, "threat"),
    (0.0, -1.0, "threat"),
    (-1.0, 0.0, "threat"),
])
def test_categorize_quadrants(e, m, expected):
    assert categorize(e, m, threshold=0.33) == expected


def _pool():
    # subject is a fast, hard-climbing, poor-turning energy fighter.
    return pd.DataFrame([
        {"game_id": "subject", "name": "Subject", "nation": "germany",
         "aircraft_class": "fighter", "br_rb": 4.0, "max_speed_kmh": 650,
         "climb_rate_ms": 20, "power_to_weight_ratio": 0.4, "turn_time_s": 22,
         "wing_loading_kg_m2": 200, "roll_rate_deg_s": 90, "burst_mass_kg_s": 2.0},
        # slow, floaty turnfighter: subject out-energies, loses the turn -> out_energy
        {"game_id": "turner", "name": "Turner", "nation": "japan",
         "aircraft_class": "fighter", "br_rb": 4.0, "max_speed_kmh": 540,
         "climb_rate_ms": 14, "power_to_weight_ratio": 0.3, "turn_time_s": 16,
         "wing_loading_kg_m2": 110, "roll_rate_deg_s": 70, "burst_mass_kg_s": 1.2},
        # strictly worse everywhere -> prey
        {"game_id": "weak", "name": "Weakling", "nation": "usa",
         "aircraft_class": "fighter", "br_rb": 3.7, "max_speed_kmh": 520,
         "climb_rate_ms": 12, "power_to_weight_ratio": 0.28, "turn_time_s": 24,
         "wing_loading_kg_m2": 230, "roll_rate_deg_s": 60, "burst_mass_kg_s": 1.0},
        # strictly better everywhere -> threat
        {"game_id": "uber", "name": "Uber", "nation": "ussr",
         "aircraft_class": "fighter", "br_rb": 5.0, "max_speed_kmh": 720,
         "climb_rate_ms": 25, "power_to_weight_ratio": 0.5, "turn_time_s": 18,
         "wing_loading_kg_m2": 150, "roll_rate_deg_s": 110, "burst_mass_kg_s": 3.5},
    ])


def test_threat_board_categories_and_exclusion():
    df = _pool()
    subject = df[df.game_id == "subject"].iloc[0]
    board = threat_board(subject, df, threshold=0.33)
    assert "subject" not in set(board.game_id)  # subject excluded
    cats = dict(zip(board.name, board.category))
    assert cats["Weakling"] == "prey"
    assert cats["Uber"] == "threat"
    assert cats["Turner"] == "out_energy"  # win energy, lose turn


def test_threat_board_same_nation_kept():
    df = _pool()
    df.loc[df.game_id == "weak", "nation"] = "germany"  # same as subject
    subject = df[df.game_id == "subject"].iloc[0]
    board = threat_board(subject, df)
    assert "Weakling" in set(board.name)  # same-nation competitor retained


def test_threat_board_is_sorted_by_category():
    df = _pool()
    subject = df[df.game_id == "subject"].iloc[0]
    board = threat_board(subject, df)
    order = [CATEGORY_ORDER.index(c) for c in board.category]
    assert order == sorted(order)


def test_threat_board_empty_pool():
    df = _pool()
    subject = df[df.game_id == "subject"].iloc[0]
    board = threat_board(subject, df[df.game_id == "subject"])  # only subject
    assert board.empty
