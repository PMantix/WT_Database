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
# Metrics used for the comparison radar: (column, label, lower_is_better)
RADAR_METRICS = [
    ("max_speed_kmh", "Top speed", False),
    ("climb_rate_ms", "Climb rate", False),
    ("turn_time_s", "Turn (fast)", True),
    ("wing_rip_kmh", "Structural", False),
    ("engine_power_hp", "Engine power", False),
]


@st.cache_data
def get_data() -> pd.DataFrame:
    df = load_dataframe()
    df["nation"] = df["nation"].str.upper()
    df["aircraft_class"] = df["aircraft_class"].str.replace("_", " ").str.title()
    df["Type"] = df["is_premium"].map({1: "Premium/Event", 0: "Tech tree"})
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


def performance_scatter(df: pd.DataFrame, mode_col: str) -> None:
    st.subheader("Performance map — speed vs turn")
    plot_df = df.dropna(subset=["max_speed_kmh", "turn_time_s"])
    if plot_df.empty:
        st.info("No aircraft with both speed and turn-time data in the current filter.")
        return
    fig = px.scatter(
        plot_df,
        x="turn_time_s",
        y="max_speed_kmh",
        color="nation",
        symbol="aircraft_class",
        size=plot_df[mode_col].fillna(1.0),
        hover_name="name",
        hover_data={
            mode_col: ":.1f",
            "aircraft_class": True,
            "climb_rate_ms": True,
            "turn_time_s": ":.1f",
            "max_speed_kmh": ":.0f",
        },
        labels={
            "turn_time_s": "Sustained turn time (s) — lower = better turner",
            "max_speed_kmh": "Top speed (km/h)",
            "nation": "Nation",
        },
        height=560,
    )
    fig.update_xaxes(autorange="reversed")  # better turners to the right
    fig.add_annotation(
        x=0.99, y=0.99, xref="paper", yref="paper", showarrow=False,
        text="↗ fast & agile (top-right)", font=dict(size=12, color="gray"),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Top-right = fast **and** turns well. Top-left = fast energy fighters / BnZ. "
        "Bottom-right = slow turnfighters. Bubble size = BR."
    )


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
    axis_labels = [label for _, label, _ in RADAR_METRICS]
    for _, row in sel.iterrows():
        vals = []
        for col, _label, lower_better in RADAR_METRICS:
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

    cols = ["name", "nation", "aircraft_class", "br_rb"] + [m[0] for m in RADAR_METRICS]
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

    performance_scatter(filtered, mode_col)
    st.divider()
    comparison_radar(filtered)
    st.divider()

    st.subheader("Aircraft table")
    table_cols = [
        "name", "nation", "aircraft_class", "rank", "br_ab", "br_rb", "br_sb",
        "max_speed_kmh", "climb_rate_ms", "turn_time_s", "armament", "notes",
    ]
    st.dataframe(
        filtered[table_cols].sort_values(mode_col).reset_index(drop=True),
        use_container_width=True,
        height=420,
    )
    st.caption(
        "Seed data is hand-entered and approximate — Phase 2 replaces it with exact "
        "datamine values. Edit `data/overrides/aircraft.yaml` and re-run the loader to update."
    )


main()
