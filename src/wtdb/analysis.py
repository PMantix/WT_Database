"""Pure analysis helpers (no Streamlit) — kept importable for tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

# --- Threat Board: one-vs-all competitor categorization ---------------------

# Metrics that make up each combat regime: (column, higher_is_better).
ENERGY_METRICS = [("max_speed_kmh", True), ("climb_rate_ms", True),
                  ("power_to_weight_ratio", True)]
MANEUVER_METRICS = [("turn_time_s", False), ("wing_loading_kg_m2", False),
                    ("roll_rate_deg_s", True)]
FIREPOWER_METRICS = [("burst_mass_kg_s", True)]

# Category keys -> (label, emoji, one-line stance).
CATEGORIES = {
    "prey": ("Prey", "🟢", "You dominate both regimes — hunt freely, pick your method."),
    "out_energy": ("Out-energy them", "🔵", "Win the energy game — stay fast and vertical, never flat-turn."),
    "out_turn": ("Out-turn them", "🟠", "Win the turnfight — drag them low and slow, bait the turn."),
    "near_peer": ("Near-peer", "🟡", "Closely matched — positioning, teamwork and first shot decide it."),
    "threat": ("Threat", "🔴", "They hold the edge — avoid 1v1, use altitude/team, disengage."),
}
CATEGORY_ORDER = ["prey", "out_energy", "out_turn", "near_peer", "threat"]


def _regime_adv(subject, competitor, metrics, stds) -> float | None:
    """Mean standardized advantage of subject over competitor across metrics.

    Each metric's advantage is (direction × (subject − competitor)) / pool_std,
    so it's expressed relative to the spread of the pool you actually face.
    Metrics missing on either plane (or with zero spread) are skipped.
    """
    advs = []
    for col, higher_better in metrics:
        s, c, sd = subject.get(col), competitor.get(col), stds.get(col, 0.0)
        if pd.isna(s) or pd.isna(c) or not sd:
            continue
        direction = 1.0 if higher_better else -1.0
        advs.append(direction * (s - c) / sd)
    return float(np.mean(advs)) if advs else None


def categorize(energy_adv: float, maneuver_adv: float, threshold: float = 0.33) -> str:
    """Map the two regime scores to a tactical category.

    Win both -> prey; win exactly one regime -> the matching conditional bucket;
    win neither (and lose at least one) -> threat; otherwise near-peer.
    """
    def bucket(v):
        return 1 if v >= threshold else (-1 if v <= -threshold else 0)

    e, m = bucket(energy_adv), bucket(maneuver_adv)
    table = {
        (1, 1): "prey",
        (1, 0): "out_energy", (1, -1): "out_energy",
        (0, 1): "out_turn", (-1, 1): "out_turn",
        (0, 0): "near_peer",
        (-1, -1): "threat", (0, -1): "threat", (-1, 0): "threat",
    }
    return table[(e, m)]


def _tactic_line(subject, comp, category, energy_adv, maneuver_adv) -> str:
    """A concrete one-liner citing the strongest relevant delta + firepower."""
    bits = []
    sp = (subject.get("max_speed_kmh"), comp.get("max_speed_kmh"))
    cl = (subject.get("climb_rate_ms"), comp.get("climb_rate_ms"))
    tn = (subject.get("turn_time_s"), comp.get("turn_time_s"))
    if category in ("prey", "out_energy"):
        if None not in cl and not any(pd.isna(v) for v in cl) and cl[0] - cl[1] > 0.5:
            bits.append(f"out-climb +{cl[0] - cl[1]:.0f} m/s")
        if None not in sp and not any(pd.isna(v) for v in sp) and sp[0] - sp[1] > 5:
            bits.append(f"+{sp[0] - sp[1]:.0f} km/h")
    if category in ("prey", "out_turn"):
        if None not in tn and not any(pd.isna(v) for v in tn) and tn[1] - tn[0] > 0.3:
            bits.append(f"out-turn by {tn[1] - tn[0]:.1f} s")
    if category == "threat":
        if None not in sp and not any(pd.isna(v) for v in sp) and sp[1] - sp[0] > 5:
            bits.append(f"they're +{sp[1] - sp[0]:.0f} km/h")
        if None not in tn and not any(pd.isna(v) for v in tn) and tn[0] - tn[1] > 0.3:
            bits.append(f"they out-turn by {tn[0] - tn[1]:.1f} s")
    bm = (subject.get("burst_mass_kg_s"), comp.get("burst_mass_kg_s"))
    if None not in bm and not any(pd.isna(v) for v in bm) and abs(bm[0] - bm[1]) > 0.5:
        who = "you" if bm[0] > bm[1] else "they"
        bits.append(f"{who} hit harder")
    return ", ".join(bits)


def threat_board(subject: pd.Series, pool: pd.DataFrame, threshold: float = 0.33) -> pd.DataFrame:
    """Categorize every competitor in ``pool`` relative to ``subject``.

    Returns a DataFrame (one row per competitor, subject excluded) with
    energy_adv, maneuver_adv, firepower_adv, category, tactic and br deltas.
    """
    comp = pool[pool["game_id"] != subject["game_id"]].copy()
    if comp.empty:
        return comp.assign(energy_adv=[], maneuver_adv=[], firepower_adv=[],
                           category=[], tactic=[])

    all_cols = {c for c, _ in ENERGY_METRICS + MANEUVER_METRICS + FIREPOWER_METRICS}
    stds = {c: float(pool[c].std()) if c in pool else 0.0 for c in all_cols}

    rows = []
    for _, c in comp.iterrows():
        e = _regime_adv(subject, c, ENERGY_METRICS, stds) or 0.0
        m = _regime_adv(subject, c, MANEUVER_METRICS, stds) or 0.0
        f = _regime_adv(subject, c, FIREPOWER_METRICS, stds) or 0.0
        cat = categorize(e, m, threshold)
        rows.append({
            "game_id": c["game_id"], "name": c["name"], "nation": c.get("nation"),
            "aircraft_class": c.get("aircraft_class"), "br_rb": c.get("br_rb"),
            "energy_adv": round(e, 3), "maneuver_adv": round(m, 3),
            "firepower_adv": round(f, 3), "category": cat,
            "tactic": _tactic_line(subject, c, cat, e, m),
        })
    out = pd.DataFrame(rows)
    out["category"] = pd.Categorical(out["category"], categories=CATEGORY_ORDER, ordered=True)
    return out.sort_values(["category", "name"]).reset_index(drop=True)


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
