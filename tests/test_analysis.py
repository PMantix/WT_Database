"""Tests for the response-surface fitter."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from wtdb.analysis import response_surface


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


def test_too_few_points_returns_none():
    df = pd.DataFrame({"x": [1.0, 2.0], "y": [1.0, 2.0], "z": [1.0, 2.0]})
    assert response_surface(df, "x", "y", "z", degree=2) is None


def test_grid_shape_and_axes():
    df = pd.DataFrame({"x": np.arange(10.0), "y": np.arange(10.0), "z": np.arange(10.0)})
    gx, gy, gz, _ = response_surface(df, "x", "y", "z", degree=1, grid=20)
    assert gx.shape == (20,) and gy.shape == (20,)
    assert gz.shape == (20, 20)  # (len(gy), len(gx))
