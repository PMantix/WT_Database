"""War Thunder Aircraft Explorer — Streamlit MVP.

Run with:  uv run streamlit run app/app.py

One global filtered DataFrame drives every view. Add views by reading the same
`df` produced by the sidebar filters.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the `wtdb` package importable when running from a fresh checkout that
# hasn't `pip install -e .`'d the project (e.g. Streamlit Community Cloud).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from wtdb.analysis import CATEGORIES, CATEGORY_ORDER, response_surface, threat_board
from wtdb.db import load_dataframe

st.set_page_config(
    page_title="WT Aircraft Explorer", page_icon="✈️", layout="wide",
    initial_sidebar_state="expanded",  # so filters are discoverable on mobile
)


def _show(fig, container=st, overlay_legend: bool = True):
    """Render a Plotly fig mobile-friendly: responsive, tight margins, and the
    legend floated transparently across the top so the plot fills the width."""
    if overlay_legend:
        fig.update_layout(legend=dict(
            orientation="h", yanchor="bottom", y=1.005, xanchor="left", x=0,
            bgcolor="rgba(0,0,0,0)", font=dict(size=10), title_text="",
        ))
    fig.update_layout(margin=dict(l=0, r=0, t=28, b=0), autosize=True)
    container.plotly_chart(fig, use_container_width=True,
                           config={"responsive": True, "displaylogo": False})

MODE_LABELS = {"br_ab": "Arcade", "br_rb": "Realistic", "br_sb": "Simulator"}

# Central metric registry. Each entry: column -> (label, lower_is_better).
# Drives the axis pickers, the ranking chart, the radar, and parallel coords.
# "lower_is_better" controls sort direction and radar inversion (e.g. turn time).
METRICS: dict[str, tuple[str, bool]] = {
    "max_speed_kmh": ("Top speed (km/h)", False),
    "climb_rate_ms": ("Climb rate (m/s)", False),
    "climb_time_s": ("Climb time to alt (s)", True),
    "turn_time_s": ("Turn time (s)", True),
    "roll_rate_deg_s": ("Roll rate (°/s)", False),
    "max_altitude_m": ("Service ceiling (m)", False),
    "wing_loading_kg_m2": ("Wing loading (kg/m²)", True),
    "power_to_weight_ratio": ("Power/thrust-to-weight", False),
    "burst_mass_kg_s": ("Firepower — burst mass (kg/s)", False),
    "cannon_burst_kg_s": ("Cannon burst (kg/s)", False),
    "mg_burst_kg_s": ("MG burst (kg/s)", False),
    "main_gun_velocity_ms": ("Main-gun velocity (m/s)", False),
    "main_gun_seconds": ("Main-gun fire time (s)", False),
    "max_caliber_mm": ("Max caliber (mm)", False),
    "gun_count": ("Gun count", False),
    "cannon_count": ("Cannon count", False),
    "total_ammo": ("Total ammo (rounds)", False),
    "rp_cost": ("Research cost (RP)", True),
    "sl_cost": ("Purchase cost (SL)", True),
    "repair_cost_rb": ("Repair cost RB (SL)", True),
    "br_ab": ("BR — Arcade", False),
    "br_rb": ("BR — Realistic", False),
    "br_sb": ("BR — Simulator", False),
}

# Curated 2-axis presets the user can pick in one click.
SCATTER_PRESETS: dict[str, tuple[str, str]] = {
    "Speed vs Turn (energy ↔ agility)": ("turn_time_s", "max_speed_kmh"),
    "Climb vs Speed (BnZ potential)": ("max_speed_kmh", "climb_rate_ms"),
    "Wing loading vs Turn (turn predictor)": ("wing_loading_kg_m2", "turn_time_s"),
    "Power-to-weight vs Climb": ("power_to_weight_ratio", "climb_rate_ms"),
    "Roll rate vs Speed": ("max_speed_kmh", "roll_rate_deg_s"),
    "Firepower vs BR (burst mass)": ("br_rb", "burst_mass_kg_s"),
    "Firepower vs Speed": ("max_speed_kmh", "burst_mass_kg_s"),
    "Cannon punch vs muzzle velocity": ("main_gun_velocity_ms", "cannon_burst_kg_s"),
    "Speed vs BR (fast for its BR?)": ("br_rb", "max_speed_kmh"),
    "Turn vs BR (best turner at each BR)": ("br_rb", "turn_time_s"),
    "Climb vs BR (best climber at each BR)": ("br_rb", "climb_rate_ms"),
    "Research cost vs BR (grind value)": ("br_rb", "rp_cost"),
    "Repair cost vs BR (SL drain)": ("br_rb", "repair_cost_rb"),
}

# Metrics shown on the comparison radar (a complete combat profile).
RADAR_COLS = [
    "max_speed_kmh", "climb_rate_ms", "turn_time_s", "roll_rate_deg_s",
    "wing_loading_kg_m2", "burst_mass_kg_s",
]


def _label(col: str) -> str:
    return METRICS.get(col, (col, False))[0]


@st.cache_data
def get_data() -> pd.DataFrame:
    df = load_dataframe()
    df["nation"] = df["nation"].str.upper()
    df["aircraft_class"] = df["aircraft_class"].str.replace("_", " ").str.title()
    df["Type"] = df["is_premium"].map({1: "Premium/Special", 0: "Tech tree"})
    return df


def sidebar_filters(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    st.sidebar.header("Filters")

    mode_col = st.sidebar.radio(
        "Battle Rating mode",
        options=list(MODE_LABELS.keys()),
        format_func=lambda c: MODE_LABELS[c],
        index=1,  # Realistic
        horizontal=True,
    )

    nations = sorted(df["nation"].unique())
    sel_nations = st.sidebar.multiselect("Nation", nations, default=nations)

    classes = sorted(df["aircraft_class"].unique())
    sel_classes = st.sidebar.multiselect("Class", classes, default=classes)

    br_series = df[mode_col].dropna()
    br_min, br_max = float(br_series.min()), float(br_series.max())
    sel_br = st.sidebar.slider(
        f"{MODE_LABELS[mode_col]} BR range",
        min_value=br_min,
        max_value=br_max,
        value=(br_min, br_max),
        step=0.3,
    )

    ranks = sorted(df["rank"].unique())
    sel_ranks = st.sidebar.multiselect("Rank", ranks, default=ranks)

    show_premium = st.sidebar.checkbox("Include premium/event", value=True)

    mask = (
        df["nation"].isin(sel_nations)
        & df["aircraft_class"].isin(sel_classes)
        & df["rank"].isin(sel_ranks)
        & df[mode_col].between(sel_br[0], sel_br[1])
    )
    if not show_premium:
        mask &= df["is_premium"] == 0

    return df[mask].copy(), mode_col


HIGHLIGHT_PALETTE = px.colors.qualitative.Bold


def _add_highlight_overlay(
    fig, axes: tuple[str, ...], highlight_rows: pd.DataFrame, is_3d: bool,
    marker_scale: float = 1.0,
):
    """Dim the base cloud and pop the highlighted aircraft with labels."""
    if highlight_rows.empty:
        return
    fig.update_traces(marker_opacity=0.18, selector=dict(mode="markers"))
    x, y = axes[0], axes[1]
    z = axes[2] if is_3d else None
    for i, (_, r) in enumerate(highlight_rows.iterrows()):
        color = HIGHLIGHT_PALETTE[i % len(HIGHLIGHT_PALETTE)]
        if any(pd.isna(r[a]) for a in axes):
            continue
        if is_3d:
            fig.add_trace(go.Scatter3d(
                x=[r[x]], y=[r[y]], z=[r[z]], mode="markers+text",
                text=[r["name"]], textposition="top center", name=r["name"],
                marker=dict(size=max(4, round(9 * marker_scale)), color=color,
                            line=dict(width=2, color="white")),
            ))
        else:
            fig.add_trace(go.Scatter(
                x=[r[x]], y=[r[y]], mode="markers+text",
                text=[r["name"]], textposition="top center", name=r["name"],
                marker=dict(size=max(5, round(18 * marker_scale)), color=color,
                            line=dict(width=max(1, round(2 * marker_scale)), color="white")),
            ))


def _scatter_fig(
    df: pd.DataFrame,
    axes: tuple[str, ...],
    color: str,
    size: str | None,
    hi_rows: pd.DataFrame,
    height: int,
    show_legend: bool = True,
    marker_scale: float = 1.0,
):
    """Build (don't render) a 2D or 3D scatter figure with highlight overlay.

    ``marker_scale`` shrinks both the bubble sizing and highlight markers — the
    small side-view panels pass ~1/3 so points don't overwhelm the plot.
    """
    is_3d = len(axes) == 3
    plot_df = df.dropna(subset=[c for c in (*axes, size) if c])
    size_arg = plot_df[size].clip(lower=0.1) if size else None
    size_max = max(4, round(18 * marker_scale))
    common = dict(
        color=color,
        hover_name="name",
        hover_data={"nation": True, "aircraft_class": True, "br_rb": ":.1f"},
        labels={a: _label(a) for a in axes} | {"nation": "Nation"},
        height=height,
    )
    if is_3d:
        x, y, z = axes
        fig = px.scatter_3d(plot_df, x=x, y=y, z=z, size=size_arg, size_max=size_max, **common)
        fig.update_traces(marker=dict(line=dict(width=0)))
        scene = {}
        for sax, col in (("xaxis", x), ("yaxis", y), ("zaxis", z)):
            a = dict(title=_label(col))
            if METRICS.get(col, ("", False))[1]:
                a["autorange"] = "reversed"
            scene[sax] = a
        # Tight margins maximize the plot area so axes stay visible while zooming.
        fig.update_layout(scene=scene, margin=dict(l=0, r=0, t=10, b=0))
    else:
        x, y = axes
        fig = px.scatter(
            plot_df, x=x, y=y, size=size_arg, size_max=size_max,
            symbol="aircraft_class" if color != "aircraft_class" else None,
            **common,
        )
        if size_arg is None:
            # No size dimension: px uses a fixed default; scale it for side views.
            fig.update_traces(marker_size=max(3, round(7 * marker_scale)),
                              selector=dict(mode="markers"))
        if METRICS.get(x, ("", False))[1]:
            fig.update_xaxes(autorange="reversed")
        if METRICS.get(y, ("", False))[1]:
            fig.update_yaxes(autorange="reversed")
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))

    _add_highlight_overlay(fig, axes, hi_rows, is_3d, marker_scale=marker_scale)
    if not show_legend:
        fig.update_layout(showlegend=False)
    return fig


def _scatter(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str,
    size: str | None,
    z: str | None = None,
    highlight: list[str] | None = None,
    side_views: bool = False,
    surface_degree: int | None = None,
) -> None:
    """Render a 2D or 3D (when ``z`` set) scatter, with optional 2D side views."""
    is_3d = z is not None
    axes = (x, y, z) if is_3d else (x, y)

    full = get_data()
    highlight = highlight or []
    hi_rows = full[full["name"].isin(highlight)].drop_duplicates(subset="name")

    if df.dropna(subset=list(axes)).empty and hi_rows.empty:
        missing = " / ".join(_label(a) for a in axes)
        st.info(f"No aircraft in the current filter have data for {missing}.")
        return

    main_height = 760 if is_3d else 620
    fig = _scatter_fig(df, axes, color, size, hi_rows, height=main_height)

    if is_3d and surface_degree:
        surf = response_surface(df, x, y, z, surface_degree)
        if surf is None:
            st.caption("Not enough points in the current filter to fit a surface.")
        else:
            gx, gy, gz, r2 = surf
            fig.add_trace(go.Surface(
                x=gx, y=gy, z=gz, opacity=0.45, showscale=False,
                colorscale="Blues", name="fit", hoverinfo="skip",
                contours={"z": {"show": True, "usecolormap": True, "project_z": True}},
            ))
            kind = {1: "best-fit plane", 2: "quadratic surface", 3: "cubic surface",
                    4: "quartic surface"}.get(surface_degree, f"degree-{surface_degree} surface")
            st.caption(
                f"Overlaid **{kind}** fit of {_label(z)} vs {_label(x)} & {_label(y)} "
                f"— R² = {r2:.2f} (how much of {_label(z)} the other two explain). "
                "Higher orders flex more but can over-fit a sparse filter."
            )

    _show(fig)

    if is_3d and side_views:
        st.caption("**2D side views** — the three orthogonal projections of the cube above.")
        pairs = [(x, y), (x, z), (y, z)]
        for (ax, ay), col in zip(pairs, st.columns(3)):
            sub = _scatter_fig(df, (ax, ay), color, size, hi_rows, height=340,
                               show_legend=False, marker_scale=1 / 3)
            _show(sub, container=col, overlay_legend=False)


def _ranking_bar(df: pd.DataFrame, metric: str, top_n: int, color: str) -> None:
    plot_df = df.dropna(subset=[metric])
    if plot_df.empty:
        st.info(f"No aircraft in the current filter have **{_label(metric)}** data.")
        return
    lower_better = METRICS.get(metric, ("", False))[1]
    plot_df = plot_df.sort_values(metric, ascending=lower_better).head(top_n)
    fig = px.bar(
        plot_df,
        x=metric,
        y="name",
        color=color,
        orientation="h",
        hover_data={"br_rb": ":.1f", "nation": True, "aircraft_class": True},
        labels={metric: _label(metric), "name": ""},
        height=max(320, 28 * len(plot_df)),
    )
    fig.update_yaxes(categoryorder="total ascending" if not lower_better else "total descending")
    _show(fig)
    st.caption(f"Top {len(plot_df)} by {_label(metric)} ({'lower' if lower_better else 'higher'} is better).")


def _parallel(df: pd.DataFrame, cols: list[str], color_metric: str) -> None:
    plot_df = df.dropna(subset=cols + [color_metric])
    if len(plot_df) < 2:
        st.info("Not enough aircraft with all selected metrics to draw parallel coordinates.")
        return
    fig = px.parallel_coordinates(
        plot_df,
        dimensions=cols,
        color=color_metric,
        labels={c: _label(c) for c in cols + [color_metric]},
        color_continuous_scale=px.colors.sequential.Viridis,
        height=480,
    )
    _show(fig)
    st.caption("Each vertical axis is one metric; each line is an aircraft. Drag along an axis to brush-filter.")


def _advantage(a, b, col: str, unit: str, threshold: float):
    """Return (winner_name, magnitude_str) for a metric, honoring lower-is-better."""
    va, vb = a[col], b[col]
    if pd.isna(va) or pd.isna(vb):
        return None
    diff = va - vb
    lower_better = METRICS.get(col, ("", False))[1]
    if abs(diff) < threshold:
        return None
    a_wins = (diff < 0) if lower_better else (diff > 0)
    return (a["name"] if a_wins else b["name"], f"{abs(diff):.1f}{unit}")


def _pairwise_matchup(a, b) -> str:
    """Rule-based counter advice between two aircraft, from each one's metrics."""
    lines: list[str] = []

    def edge(col, unit, thr, phrase):
        res = _advantage(a, b, col, unit, thr)
        if res:
            winner, mag = res
            lines.append(f"- **{winner}** {phrase} (by {mag}).")

    edge("max_speed_kmh", " km/h", 15, "is faster")
    edge("turn_time_s", " s", 1.0, "turns tighter")
    edge("climb_rate_ms", " m/s", 1.5, "climbs better")
    edge("roll_rate_deg_s", "°/s", 8, "rolls faster")
    edge("burst_mass_kg_s", " kg/s", 0.5, "hits harder (burst mass)")

    # Tactical synthesis from the deltas.
    plan: list[str] = []
    spd = _advantage(a, b, "max_speed_kmh", "", 15)
    trn = _advantage(a, b, "turn_time_s", "", 1.0)
    if spd and trn and spd[0] != trn[0]:
        faster, turner = spd[0], trn[0]
        plan.append(
            f"Classic energy-vs-agility matchup: **{faster}** should boom-and-zoom — "
            f"keep speed, fight vertically, never enter a flat turn. **{turner}** should "
            f"drag the fight low and slow to force a turning duel."
        )
    elif trn and spd and spd[0] == trn[0]:
        plan.append(
            f"**{spd[0]}** holds both the speed *and* turn edge — it dictates the fight; "
            f"the other should disengage, climb away, and only re-engage with altitude."
        )
    clb = _advantage(a, b, "climb_rate_ms", "", 1.5)
    if clb:
        plan.append(f"**{clb[0]}** wins the climb race — it takes the energy advantage off the merge.")

    br = ""
    if not pd.isna(a["br_rb"]) and not pd.isna(b["br_rb"]) and a["br_rb"] != b["br_rb"]:
        hi = a if a["br_rb"] > b["br_rb"] else b
        br = f"\n\n_BR gap: {a['name']} {a['br_rb']:.1f} vs {b['name']} {b['br_rb']:.1f} (RB) — {hi['name']} is the uptier._"

    out = "\n".join(lines) if lines else "- Performance is closely matched across the board."
    if plan:
        out += "\n\n**Game plan:** " + " ".join(plan)
    # Surface any hand-written strategy notes.
    for p in (a, b):
        if isinstance(p.get("notes"), str) and p["notes"].strip():
            out += f"\n\n📝 _{p['name']}_: {p['notes']}"
    return out + br


def matchup_notes(highlight: list[str]) -> None:
    full = get_data()
    # Display names can repeat across variants — take the first match per name.
    rows = [full[full["name"] == n].iloc[0] for n in highlight if (full["name"] == n).any()]
    if len(rows) < 2:
        return
    st.markdown("#### ⚔️ Matchup notes")
    st.caption("Derived from flight-model metrics — directional guidance, not gospel.")
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = rows[i], rows[j]
            with st.expander(f"{a['name']}  vs  {b['name']}"):
                st.markdown(_pairwise_matchup(a, b))


def explore_plots(df: pd.DataFrame, mode_col: str) -> None:
    st.subheader("📊 Explore")
    chart = st.radio(
        "Chart type",
        ["Scatter (compare 2 metrics)", "Ranking (top by 1 metric)", "Parallel (many metrics)"],
        horizontal=True,
        label_visibility="collapsed",
    )

    color_opts = {"nation": "Nation", "aircraft_class": "Class", "Type": "Tech/Premium",
                  "rank": "Rank", "gun_layout": "Gun layout"}

    if chart.startswith("Scatter"):
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            preset = st.selectbox(
                "Preset", ["— custom —", *SCATTER_PRESETS.keys()], index=1
            )
        with c2:
            color_by = st.selectbox(
                "Color by", list(color_opts), format_func=color_opts.get, key="sc_color"
            )
        with c3:
            use_3d = st.checkbox("3D (Z axis)", value=True, key="sc_3d")

        metric_cols = list(METRICS.keys())
        if preset != "— custom —":
            x_def, y_def = SCATTER_PRESETS[preset]
        else:
            x_def, y_def = "turn_time_s", "max_speed_kmh"

        cols = st.columns(4 if use_3d else 3)
        x = cols[0].selectbox("X axis", metric_cols, index=metric_cols.index(x_def),
                              format_func=_label, key="sc_x")
        y = cols[1].selectbox("Y axis", metric_cols, index=metric_cols.index(y_def),
                              format_func=_label, key="sc_y")
        side_views = False
        if use_3d:
            z_def = next((m for m in ("climb_rate_ms", "roll_rate_deg_s", "br_rb")
                          if m not in (x, y)), metric_cols[0])
            z = cols[2].selectbox("Z axis", metric_cols, index=metric_cols.index(z_def),
                                  format_func=_label, key="sc_z")
            size_slot = cols[3]
        else:
            z = None
            size_slot = cols[2]
        size_by = size_slot.selectbox(
            "Bubble size", ["(none)", *metric_cols],
            format_func=lambda c: "(none)" if c == "(none)" else _label(c),
            index=(metric_cols.index(mode_col) + 1), key="sc_size",
        )
        surface_degree = None
        if use_3d:
            sc1, sc2 = st.columns(2)
            side_views = sc1.checkbox(
                "Show 2D side views (X·Y, X·Z, Y·Z projections)", value=False, key="sc_sides"
            )
            fit_choice = sc2.selectbox(
                "Fit response surface",
                ["Off", "Plane (linear)", "Quadratic", "Cubic", "Quartic"],
                index=0, key="sc_surf",
            )
            surface_degree = {
                "Plane (linear)": 1, "Quadratic": 2, "Cubic": 3, "Quartic": 4,
            }.get(fit_choice)

        all_names = sorted(get_data()["name"].dropna().unique().tolist())
        highlight = st.multiselect(
            "🔍 Search & highlight aircraft (type to find; pick several to compare)",
            all_names, key="sc_hi", max_selections=8,
        )
        _scatter(df, x, y, color_by, None if size_by == "(none)" else size_by,
                 z=z, highlight=highlight, side_views=side_views,
                 surface_degree=surface_degree)
        matchup_notes(highlight)

    elif chart.startswith("Ranking"):
        c1, c2, c3 = st.columns(3)
        metric = c1.selectbox("Rank by", list(METRICS), index=list(METRICS).index("max_speed_kmh"),
                              format_func=_label, key="rk_metric")
        top_n = c2.slider("Show top", 3, 40, 15, key="rk_n")
        color_by = c3.selectbox("Color by", list(color_opts), format_func=color_opts.get, key="rk_color")
        _ranking_bar(df, metric, top_n, color_by)

    else:
        defaults = ["max_speed_kmh", "climb_rate_ms", "turn_time_s", "br_rb"]
        numeric = [c for c in METRICS if c in df.columns]
        cols = st.multiselect("Axes (pick 3–6)", numeric, default=defaults,
                              format_func=_label, max_selections=6, key="pc_cols")
        color_metric = st.selectbox("Color scale", numeric, index=numeric.index("br_rb"),
                                    format_func=_label, key="pc_color")
        if len(cols) >= 2:
            _parallel(df, cols, color_metric)
        else:
            st.info("Pick at least two metrics.")


def comparison_radar(df: pd.DataFrame) -> None:
    st.subheader("Compare aircraft")
    names = st.multiselect(
        "Pick 2–4 aircraft to compare",
        options=df.sort_values("name")["name"].tolist(),
        max_selections=4,
    )
    if len(names) < 2:
        st.info("Select at least two aircraft to draw the comparison radar.")
        return

    full = get_data()  # normalize against the whole roster, not just the filter
    sel = full[full["name"].isin(names)]

    fig = go.Figure()
    axis_labels = [_label(c) for c in RADAR_COLS]
    for _, row in sel.iterrows():
        vals = []
        for col in RADAR_COLS:
            lower_better = METRICS.get(col, ("", False))[1]
            series = full[col].dropna()
            v = row[col]
            if pd.isna(v) or series.empty or series.max() == series.min():
                vals.append(0.0)
                continue
            norm = (v - series.min()) / (series.max() - series.min())
            if lower_better:
                norm = 1 - norm
            vals.append(round(norm * 100, 1))
        fig.add_trace(go.Scatterpolar(
            r=vals + [vals[0]],
            theta=axis_labels + [axis_labels[0]],
            fill="toself",
            name=row["name"],
        ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        height=480,
        showlegend=True,
    )
    _show(fig)
    st.caption("Each axis is percentile-normalized across the full roster (100 = best). Turn axis is inverted so outward = faster turn.")

    cols = ["name", "nation", "aircraft_class", "br_rb"] + RADAR_COLS
    st.dataframe(sel[cols].set_index("name"), use_container_width=True)


CATEGORY_COLORS = {
    "prey": "#2ca02c", "out_energy": "#1f77b4", "out_turn": "#ff7f0e",
    "near_peer": "#d4a017", "threat": "#d62728",
}


def _quadrant_chart(board: pd.DataFrame, subject_name: str, highlight: list[str] | None = None) -> None:
    board = board.copy()
    board["Category"] = [f"{CATEGORIES[c][1]} {CATEGORIES[c][0]}" for c in board["category"]]
    board["fp"] = board["firepower_adv"].abs().clip(lower=0.05)
    cmap = {f"{CATEGORIES[c][1]} {CATEGORIES[c][0]}": CATEGORY_COLORS[c] for c in CATEGORY_ORDER}
    fig = px.scatter(
        board, x="maneuver_adv", y="energy_adv", color="Category",
        size="fp", color_discrete_map=cmap, hover_name="name",
        hover_data={"br_rb": ":.1f", "tactic": True, "maneuver_adv": ":.2f",
                    "energy_adv": ":.2f", "fp": False, "Category": False},
        labels={"maneuver_adv": "◀ they out-turn   ·   you out-turn ▶",
                "energy_adv": "▼ they out-energy   ·   you out-energy ▲"},
        height=560,
    )
    lim = max(1.0, float(board[["maneuver_adv", "energy_adv"]].abs().to_numpy().max()) * 1.15)
    fig.update_xaxes(range=[-lim, lim], zeroline=True, zerolinewidth=2)
    fig.update_yaxes(range=[-lim, lim], zeroline=True, zerolinewidth=2)

    # Highlighted adversaries: dim the cloud, then pop + label the selected ones.
    highlight = highlight or []
    hl = board[board["name"].isin(highlight)]
    if not hl.empty:
        fig.update_traces(marker_opacity=0.22, selector=dict(mode="markers"))
        for _, r in hl.iterrows():
            fig.add_trace(go.Scatter(
                x=[r["maneuver_adv"]], y=[r["energy_adv"]], mode="markers+text",
                text=[r["name"]], textposition="top center", name=r["name"],
                marker=dict(size=16, color=CATEGORY_COLORS[r["category"]],
                            line=dict(width=2, color="white")),
                showlegend=False,
            ))

    # Your plane sits at the origin.
    fig.add_trace(go.Scatter(
        x=[0], y=[0], mode="markers+text", text=[f"⭐ {subject_name}"],
        textposition="bottom center", marker=dict(size=16, color="white",
        line=dict(width=2, color="black")), name=subject_name, showlegend=False,
    ))
    for (xa, ya, txt) in [(0.55, 0.9, "PREY"), (-0.6, 0.9, "keep vertical"),
                          (0.5, -0.92, "drag to turnfight"), (-0.6, -0.92, "AVOID")]:
        fig.add_annotation(x=xa * lim, y=ya * lim, text=txt, showarrow=False,
                           font=dict(size=12, color="gray"))
    _show(fig)


def threat_board_tab(filtered: pd.DataFrame, mode_col: str) -> None:
    st.subheader("🎯 Threat Board")
    st.caption(
        "Pick your plane; every competitor is sorted by where your advantage lies. "
        "Model uses stat-card flight-model numbers — it won't capture missiles, "
        "radar, countermeasures or pilot skill (so treat top-tier as directional)."
    )
    full = get_data()
    names = sorted(full["name"].dropna().unique().tolist())

    # Auto-sync from the Explore highlight selection (when it changes): first pick
    # is "you", the rest become highlighted adversaries. Still editable below.
    explore_hi = list(st.session_state.get("sc_hi", []))
    if st.session_state.get("_tb_src") != explore_hi:
        st.session_state["_tb_src"] = explore_hi
        if explore_hi:
            st.session_state["tb_subject"] = explore_hi[0]
            st.session_state["tb_hi"] = explore_hi[1:]
    if explore_hi:
        extra = f" + {len(explore_hi) - 1} adversaries" if len(explore_hi) > 1 else ""
        st.caption(f"↪ Synced from Explore: **{explore_hi[0]}** as your plane{extra}. Adjust below anytime.")

    c1, c2, c3 = st.columns([2, 2, 1.3])
    subject_name = c1.selectbox("Your aircraft", names, key="tb_subject")
    pool_src = c2.selectbox(
        "Enemy pool", ["Sidebar filter", "BR bracket"], key="tb_pool",
        help="The set of enemies you're up against — independent of your plane. "
             "Change your aircraft to see how it fares against the SAME enemies.",
    )
    group_variants = c3.checkbox(
        "Group variants", value=False, key="tb_group",
        help="Collapse variants of the same model (same name) into one representative.",
    )

    subject = full[full["name"] == subject_name].iloc[0]
    if pool_src == "BR bracket":
        # A fixed bracket (all nations). Independent of the subject: the slider
        # keeps its own value, so swapping your plane doesn't move it.
        brs = full[mode_col].dropna()
        bmin, bmax = float(brs.min()), float(brs.max())
        lo_def = float(subject[mode_col]) if pd.notna(subject[mode_col]) else bmin
        default = (min(lo_def, bmax), min(bmax, lo_def + 1.0))
        rng = st.slider(f"Enemy BR bracket ({MODE_LABELS[mode_col]})", bmin, bmax,
                        default, step=0.3, key="tb_br")
        pool = full[full[mode_col].between(rng[0], rng[1])]
        pool_note = f"BR {rng[0]:.1f}–{rng[1]:.1f} ({MODE_LABELS[mode_col]}), all nations"
    else:
        pool = filtered
        pool_note = "current sidebar filter"
    st.caption("🔁 Lost your plane? Change **Your aircraft** above — the enemy pool stays "
               "put so you can see how a different plane handles the same fight.")

    if group_variants:
        pool = (pool.sort_values(["is_premium", "br_rb", "game_id"])
                    .drop_duplicates("name", keep="first"))

    board = threat_board(subject, pool)
    if group_variants and not board.empty:
        board = board[board["name"] != subject_name].reset_index(drop=True)
    if board.empty:
        st.info("No competitors in the pool. Widen the filter or enable the matchmaking spread.")
        return
    st.caption(f"Pool: {pool_note} — {len(board)} competitors"
               + (" (variants grouped)." if group_variants else "."))

    board_names = sorted(board["name"].unique().tolist())
    # Keep only highlights that exist in the current board (pool/grouping may change).
    st.session_state["tb_hi"] = [n for n in st.session_state.get("tb_hi", []) if n in board_names]
    highlight = st.multiselect(
        "🔍 Highlight adversaries (auto-filled from Explore; type to add/remove)",
        board_names, key="tb_hi", max_selections=12,
    )

    _quadrant_chart(board, subject_name, highlight=highlight)

    if highlight:
        st.markdown("#### Selected adversaries")
        for _, r in board[board["name"].isin(highlight)].drop_duplicates("name").iterrows():
            label, emoji, _stance = CATEGORIES[r["category"]]
            tac = f" — {r['tactic']}" if r["tactic"] else ""
            st.markdown(f"- {emoji} **{r['name']}** · {label} (BR {r['br_rb']:.1f}){tac}")

    st.markdown("### Breakdown")
    for cat in CATEGORY_ORDER:
        grp = board[board["category"] == cat]
        if grp.empty:
            continue
        label, emoji, stance = CATEGORIES[cat]
        with st.expander(f"{emoji} **{label}** — {len(grp)} aircraft", expanded=cat in ("prey", "threat")):
            st.caption(stance)
            for _, r in grp.iterrows():
                tac = f" — {r['tactic']}" if r["tactic"] else ""
                st.markdown(f"- **{r['name']}** ({r['nation']}, BR {r['br_rb']:.1f}){tac}")
    st.caption(
        "Energy = speed + climb + power/weight · Maneuver = turn + wing-loading + roll · "
        "bubble size = firepower gap. Advantages are relative to the spread of this pool."
    )


def aircraft_table(filtered: pd.DataFrame, mode_col: str, version: str) -> None:
    st.subheader("📋 Aircraft table")
    table_cols = [
        "name", "nation", "aircraft_class", "rank", "br_ab", "br_rb", "br_sb",
        "max_speed_kmh", "climb_rate_ms", "turn_time_s", "roll_rate_deg_s",
        "wing_loading_kg_m2", "burst_mass_kg_s", "cannon_burst_kg_s",
        "main_gun_velocity_ms", "max_caliber_mm", "gun_layout",
        "rp_cost", "repair_cost_rb", "notes",
    ]
    st.dataframe(
        filtered[table_cols].sort_values(mode_col).reset_index(drop=True),
        use_container_width=True, height=560,
    )
    st.caption(
        f"Data from the War Thunder datamine (version {version}). "
        "Hand corrections/notes live in `data/overrides/aircraft.yaml`; "
        "re-run `uv run python -m wtdb.pipeline` after a patch."
    )


def main() -> None:
    st.title("✈️ War Thunder Aircraft Explorer")
    st.caption("Filters are in the sidebar — on mobile, tap **❯** (top-left) to open it.")
    df = get_data()
    filtered, mode_col = sidebar_filters(df)
    version = df["game_version"].dropna().iloc[0] if df["game_version"].notna().any() else "?"

    c1, c2, c3 = st.columns(3)
    c1.metric("Aircraft shown", len(filtered))
    c2.metric("Nations", filtered["nation"].nunique())
    if not filtered[mode_col].dropna().empty:
        c3.metric(
            f"{MODE_LABELS[mode_col]} BR span",
            f"{filtered[mode_col].min():.1f}–{filtered[mode_col].max():.1f}",
        )

    tab_explore, tab_threat, tab_table = st.tabs(["📊 Explore", "🎯 Threat Board", "📋 Table"])
    with tab_explore:
        explore_plots(filtered, mode_col)
        st.divider()
        comparison_radar(filtered)
    with tab_threat:
        threat_board_tab(filtered, mode_col)
    with tab_table:
        aircraft_table(filtered, mode_col, version)


main()
