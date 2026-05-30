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


def _scatter(df: pd.DataFrame, x: str, y: str, color: str, size: str | None) -> None:
    needed = [c for c in (x, y, size) if c]
    plot_df = df.dropna(subset=needed)
    if plot_df.empty:
        st.info(
            f"No aircraft in the current filter have data for both "
            f"**{_label(x)}** and **{_label(y)}**."
        )
        return

    size_arg = plot_df[size].clip(lower=0.1) if size else None
    fig = px.scatter(
        plot_df,
        x=x,
        y=y,
        color=color,
        symbol="aircraft_class" if color != "aircraft_class" else None,
        size=size_arg,
        hover_name="name",
        hover_data={
            "nation": True,
            "aircraft_class": True,
            "br_rb": ":.1f",
            x: ":.1f",
            y: ":.1f",
        },
        labels={x: _label(x), y: _label(y), "nation": "Nation"},
        height=580,
    )
    # For "lower is better" axes, reverse so "good" is up/right.
    if METRICS.get(x, ("", False))[1]:
        fig.update_xaxes(autorange="reversed")
    if METRICS.get(y, ("", False))[1]:
        fig.update_yaxes(autorange="reversed")
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
        c1, c2 = st.columns([2, 1])
        with c1:
            preset = st.selectbox(
                "Preset", ["— custom —", *SCATTER_PRESETS.keys()], index=1
            )
        with c2:
            color_by = st.selectbox(
                "Color by", list(color_opts), format_func=color_opts.get, key="sc_color"
            )

        metric_cols = list(METRICS.keys())
        if preset != "— custom —":
            x_def, y_def = SCATTER_PRESETS[preset]
        else:
            x_def, y_def = "turn_time_s", "max_speed_kmh"
        cc1, cc2, cc3 = st.columns(3)
        x = cc1.selectbox("X axis", metric_cols, index=metric_cols.index(x_def),
                          format_func=_label, key="sc_x")
        y = cc2.selectbox("Y axis", metric_cols, index=metric_cols.index(y_def),
                          format_func=_label, key="sc_y")
        size_by = cc3.selectbox(
            "Bubble size", ["(none)", *metric_cols], format_func=lambda c: "(none)" if c == "(none)" else _label(c),
            index=(metric_cols.index(mode_col) + 1), key="sc_size",
        )
        _scatter(df, x, y, color_by, None if size_by == "(none)" else size_by)

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
