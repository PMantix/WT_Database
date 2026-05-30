"""Pure analysis helpers (no Streamlit) — kept importable for tests."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _n_terms(degree: int) -> int:
    """Number of bivariate monomials with total degree <= ``degree``."""
    return (degree + 1) * (degree + 2) // 2


def response_surface(
    pdf: pd.DataFrame, x: str, y: str, z: str, degree: int, grid: int = 36
):
    """Least-squares polynomial fit ``z = f(x, y)`` of arbitrary ``degree``.

    The model is the full bivariate polynomial — every monomial ``x^i · y^j``
    with ``i + j <= degree``. So degree 1 is the best-fit plane, 2 the classic
    quadratic response surface, 3 cubic, and so on. Inputs are standardized
    (centered & scaled) before fitting so high powers of large-magnitude metrics
    (e.g. speed⁴) stay numerically well-conditioned.

    Returns ``(gx, gy, GZ, r2)`` where ``gx``/``gy`` are 1-D grid axes, ``GZ`` is
    the 2-D fitted surface (shape ``(len(gy), len(gx))``), and ``r2`` is the
    coefficient of determination. Returns ``None`` if there are too few points
    to determine the fit.
    """
    d = pdf.dropna(subset=[x, y, z])
    if len(d) < _n_terms(degree):
        return None
    xv = d[x].to_numpy(float)
    yv = d[y].to_numpy(float)
    zv = d[z].to_numpy(float)

    # Standardize x, y for conditioning (guard against a constant column).
    xm, xs = xv.mean(), xv.std() or 1.0
    ym, ys = yv.mean(), yv.std() or 1.0

    def feats(a, b):
        a = (a - xm) / xs
        b = (b - ym) / ys
        cols = []
        for total in range(degree + 1):
            for i in range(total + 1):
                cols.append((a ** i) * (b ** (total - i)))
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
