"""Pure analysis helpers (no Streamlit) — kept importable for tests."""

from __future__ import annotations

import numpy as np
import pandas as pd


def response_surface(
    pdf: pd.DataFrame, x: str, y: str, z: str, degree: int, grid: int = 36
):
    """Least-squares fit ``z = f(x, y)`` over the points in ``pdf``.

    ``degree`` 1 fits the best-fit plane; ``degree`` 2 fits the classic quadratic
    response surface (terms: 1, x, y, xy, x², y²).

    Returns ``(gx, gy, GZ, r2)`` where ``gx``/``gy`` are 1-D grid axes, ``GZ`` is
    the 2-D fitted surface (shape ``(len(gy), len(gx))``), and ``r2`` is the
    coefficient of determination. Returns ``None`` if there are too few points.
    """
    d = pdf.dropna(subset=[x, y, z])
    min_pts = 6 if degree >= 2 else 3
    if len(d) < min_pts:
        return None
    xv = d[x].to_numpy(float)
    yv = d[y].to_numpy(float)
    zv = d[z].to_numpy(float)

    def feats(a, b):
        cols = [np.ones_like(a), a, b]
        if degree >= 2:
            cols += [a * b, a**2, b**2]
        return np.column_stack(cols)

    coef, *_ = np.linalg.lstsq(feats(xv, yv), zv, rcond=None)
    pred = feats(xv, yv) @ coef
    ss_res = float(((zv - pred) ** 2).sum())
    ss_tot = float(((zv - zv.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    gx = np.linspace(xv.min(), xv.max(), grid)
    gy = np.linspace(yv.min(), yv.max(), grid)
    gxx, gyy = np.meshgrid(gx, gy)
    gz = (feats(gxx.ravel(), gyy.ravel()) @ coef).reshape(gxx.shape)
    return gx, gy, gz, r2
