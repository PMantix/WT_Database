"""War Thunder Aircraft Explorer — Streamlit MVP.

Run with:  uv run streamlit run app/app.py

One global filtered DataFrame drives every view. Add views by reading the same
`df` produced by the sidebar filters.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from wtdb.db import load_dataframe

st.set_page_config(page_title="WT Aircraft Explorer", page_icon="✈️", layout="wide")

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
    "Speed vs BR (fast for its BR?)": ("br_rb", "max_speed_kmh"),
    "Turn vs BR (best turner at each BR)": ("br_rb", "turn_time_s"),
    "Climb vs BR (best climber at each BR)": ("br_rb", "climb_rate_ms"),
    "Research cost vs BR (grind value)": ("br_rb", "rp_cost"),
    "Repair cost vs BR (SL drain)": ("br_rb", "repair_cost_rb"),
}

# Metrics shown on the comparison radar.
RADAR_COLS = [
    "max_speed_kmh", "climb_rate_ms", "turn_time_s", "roll_rate_deg_s", "wing_loading_kg_m2",
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


def _add_highlight_overlay(fig, axes: tuple[str, ...], highlight_rows: pd.DataFrame, is_3d: bool):
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
                marker=dict(size=9, color=color, line=dict(width=2, color="white")),
            ))
        else:
            fig.add_trace(go.Scatter(
                x=[r[x]], y=[r[y]], mode="markers+text",
                text=[r["name"]], textposition="top center", name=r["name"],
                marker=dict(size=18, color=color, line=dict(width=2, color="white")),
            ))


def _scatter(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str,
    size: str | None,
    z: str | None = None,
    highlight: list[str] | None = None,
) -> None:
    """2D or 3D (when ``z`` set) scatter with optional highlighting."""
    is_3d = z is not None
    axes = (x, y, z) if is_3d else (x, y)
    needed = [c for c in (x, y, z, size) if c]
    plot_df = df.dropna(subset=needed)

    full = get_data()
    highlight = highlight or []
    hi_rows = full[full["name"].isin(highlight)].drop_duplicates(subset="name")

    if plot_df.empty and hi_rows.empty:
        missing = " / ".join(_label(a) for a in axes)
        st.info(f"No aircraft in the current filter have data for {missing}.")
        return

    size_arg = plot_df[size].clip(lower=0.1) if size else None
    hover = {"nation": True, "aircraft_class": True, "br_rb": ":.1f"}
    common = dict(
        color=color,
        hover_name="name",
        hover_data=hover,
        labels={a: _label(a) for a in axes} | {"nation": "Nation"},
        height=640 if is_3d else 580,
    )
    if is_3d:
        fig = px.scatter_3d(plot_df, x=x, y=y, z=z, size=size_arg, **common)
        fig.update_traces(marker=dict(line=dict(width=0)))
        scene = {}
        for axis, col in (("xaxis", x), ("yaxis", y), ("zaxis", z)):
            ax = dict(title=_label(col))
            if METRICS.get(col, ("", False))[1]:
                ax["autorange"] = "reversed"
            scene[axis] = ax
        fig.update_layout(scene=scene)
    else:
        fig = px.scatter(
            plot_df, x=x, y=y, size=size_arg,
            symbol="aircraft_class" if color != "aircraft_class" else None,
            **common,
        )
        if METRICS.get(x, ("", False))[1]:
            fig.update_xaxes(autorange="reversed")
        if METRICS.get(y, ("", False))[1]:
            fig.update_yaxes(autorange="reversed")

    _add_highlight_overlay(fig, axes, hi_rows, is_3d)
    st.plotly_chart(fig, use_container_width=True)


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
    st.plotly_chart(fig, use_container_width=True)
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
    st.plotly_chart(fig, use_container_width=True)
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

    color_opts = {"nation": "Nation", "aircraft_class": "Class", "Type": "Tech/Premium", "rank": "Rank"}

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
            use_3d = st.checkbox("3D (add Z axis)", value=False, key="sc_3d")

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

        all_names = sorted(get_data()["name"].dropna().unique().tolist())
        highlight = st.multiselect(
            "🔍 Search & highlight aircraft (type to find; pick several to compare)",
            all_names, key="sc_hi", max_selections=8,
        )
        _scatter(df, x, y, color_by, None if size_by == "(none)" else size_by,
                 z=z, highlight=highlight)
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
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Each axis is percentile-normalized across the full roster (100 = best). Turn axis is inverted so outward = faster turn.")

    cols = ["name", "nation", "aircraft_class", "br_rb"] + RADAR_COLS
    st.dataframe(sel[cols].set_index("name"), use_container_width=True)


def main() -> None:
    st.title("✈️ War Thunder Aircraft Explorer")
    df = get_data()
    filtered, mode_col = sidebar_filters(df)

    c1, c2, c3 = st.columns(3)
    c1.metric("Aircraft shown", len(filtered))
    c2.metric("Nations", filtered["nation"].nunique())
    if not filtered[mode_col].dropna().empty:
        c3.metric(
            f"{MODE_LABELS[mode_col]} BR span",
            f"{filtered[mode_col].min():.1f}–{filtered[mode_col].max():.1f}",
        )

    explore_plots(filtered, mode_col)
    st.divider()
    comparison_radar(filtered)
    st.divider()

    st.subheader("Aircraft table")
    table_cols = [
        "name", "nation", "aircraft_class", "rank", "br_ab", "br_rb", "br_sb",
        "max_speed_kmh", "climb_rate_ms", "turn_time_s", "roll_rate_deg_s",
        "wing_loading_kg_m2", "rp_cost", "repair_cost_rb", "notes",
    ]
    st.dataframe(
        filtered[table_cols].sort_values(mode_col).reset_index(drop=True),
        use_container_width=True,
        height=440,
    )
    st.caption(
        f"Data from the War Thunder datamine (version "
        f"{df['game_version'].dropna().iloc[0] if df['game_version'].notna().any() else '?'}). "
        "Hand corrections/notes live in `data/overrides/aircraft.yaml`; "
        "re-run `uv run python -m wtdb.pipeline` after a patch."
    )


main()
