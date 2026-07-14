"""Shared presentation helpers for the DMRC operations dashboard."""

from __future__ import annotations

import html

import streamlit as st


NAVY = "#082F49"
BLUE = "#0B6E99"
SKY = "#EAF5FA"
INK = "#172033"
MUTED = "#5E6B7A"
BORDER = "#D9E2EC"


def inject_styles() -> None:
    """Install the app-wide control-room visual language once per rerun."""
    st.markdown(
        """
        <style>
        .stApp { background: #F6F8FB; color: #172033; }
        .block-container { max-width: 1500px; padding-top: 1.35rem; padding-bottom: 3rem; }
        h1, h2, h3 { color: #082F49; letter-spacing: -0.02em; }
        [data-testid="stMetric"] {
            background: #FFFFFF; border: 1px solid #D9E2EC; border-radius: 14px;
            padding: 1rem 1.1rem; box-shadow: 0 3px 10px rgba(15, 42, 61, .05);
        }
        [data-testid="stMetricLabel"] { color: #5E6B7A; font-size: .82rem; font-weight: 650; }
        [data-testid="stMetricValue"] { color: #082F49; font-weight: 720; }
        .stTabs [data-baseweb="tab-list"] { gap: .45rem; border-bottom: 1px solid #D9E2EC; }
        .stTabs [data-baseweb="tab"] { height: 48px; border-radius: 9px 9px 0 0; padding: 0 1rem; color: #334E68; font-weight: 700; }
        .stTabs [aria-selected="true"] { background: #D9F1FA; color: #082F49; }
        label, [data-testid="stWidgetLabel"] p, [data-testid="stCaptionContainer"] { color: #334E68 !important; font-weight: 600; }
        [data-baseweb="select"] > div, [data-testid="stTextInput"] input { color: #172033 !important; background: #FFFFFF !important; border-color: #9FB3C8 !important; }
        [data-baseweb="select"] span { color: #172033 !important; }
        [data-testid="stAlert"] { border-radius: 10px; }
        div[data-testid="stForm"] { border: 1px solid #D9E2EC; background: #FFFFFF; border-radius: 14px; padding: 1rem; }
        .stButton > button, .stFormSubmitButton > button { border-radius: 9px; font-weight: 650; }
        .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] { background: #0B6E99; border-color: #0B6E99; color: #FFFFFF; }
        div[data-testid="stButton"] > button[kind="secondary"],
div[data-testid="stFormSubmitButton"] > button[kind="secondary"] {
            background: #FFFFFF;
            color: #334E68;
            border: 1px solid #0B6E99;
            box-shadow: inset 0 0 0 1px rgba(11, 110, 153, .12);
        }
        div[data-testid="stButton"] > button[kind="secondary"]:hover,
        div[data-testid="stFormSubmitButton"] > button[kind="secondary"]:hover {
            background: #EAF5FA;
            color: #000000;
            border-color: #0B6E99;
        }
        [data-testid="stDataFrame"] { border: 1px solid #D9E2EC; border-radius: 10px; overflow: hidden; }
        .dmrc-hero { background: linear-gradient(115deg, #082F49 0%, #0B5E89 100%); border-radius: 18px; padding: 1.5rem 1.7rem; margin-bottom: 1rem; box-shadow: 0 12px 26px rgba(8,47,73,.18); }
        .dmrc-hero h1 { color: #FFFFFF; font-size: 1.75rem; margin: 0; }
        .dmrc-hero p { color: #C7E7F5; margin: .38rem 0 0; font-size: .98rem; }
        .dmrc-eyebrow { color: #76D4F5; font-size: .73rem; font-weight: 750; letter-spacing: .09em; text-transform: uppercase; }
        .dmrc-topbar { display: flex; justify-content: space-between; align-items: center; gap: 1rem; background: #031E30; color: #FFFFFF; border-radius: 12px; padding: .65rem 1.05rem; margin-bottom: .65rem; font-size: .84rem; }
        .dmrc-topbar strong { letter-spacing: .025em; }
        .dmrc-topbar span { color: #A8DDEF; font-weight: 650; }
        .dmrc-section { margin: 1.25rem 0 .35rem; }
        .dmrc-section h2 { font-size: 1.25rem; margin: 0; }
        .dmrc-section p { color: #5E6B7A; margin: .22rem 0 0; }
        .dmrc-workspace { border-radius: 14px; padding: 1.05rem 1.25rem; margin: .25rem 0 1.1rem; background: linear-gradient(100deg, #FFFFFF 0%, #EAF5FA 100%); border: 1px solid #B8D8E8; border-left: 6px solid #0B6E99; box-shadow: 0 4px 12px rgba(15, 42, 61, .06); }
        .dmrc-workspace h2 { margin: 0; color: #082F49; font-size: 1.4rem; }
        .dmrc-workspace p { margin: .28rem 0 0; color: #334E68; font-weight: 520; }
        .dmrc-workspace-tag { color: #0B6E99; font-size: .72rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
        .dmrc-scope { background: #FFFFFF; border: 1px solid #D9E2EC; border-left: 4px solid #0B6E99; border-radius: 10px; padding: .6rem .85rem; color: #334E68; font-size: .9rem; margin: .75rem 0; }
        .dmrc-priority { background: #FFF7E8; border: 1px solid #F7D99B; border-radius: 12px; padding: .8rem 1rem; color: #714C00; margin: .75rem 0 1rem; }
        @media (max-width: 850px) { .block-container { padding-left: .85rem; padding-right: .85rem; } .dmrc-hero { padding: 1.1rem; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(data_source_label: str) -> None:
    st.markdown(
        f"""
        <header class="dmrc-topbar">
          <strong>DELHI METRO RAIL CORPORATION</strong>
          <span>Employee Effectiveness System · {html.escape(data_source_label)}</span>
        </header>
        <section class="dmrc-hero">
          <div class="dmrc-eyebrow">DMRC operations intelligence</div>
          <h1>Maintenance control room</h1>
          <p>Preventive-maintenance compliance, failure intelligence, and decision support in one workspace.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_section(title: str, description: str | None = None) -> None:
    safe_title = html.escape(title)
    safe_description = html.escape(description or "")
    st.markdown(
        f"<section class='dmrc-section'><h2>{safe_title}</h2><p>{safe_description}</p></section>",
        unsafe_allow_html=True,
    )


def render_workspace_title(title: str, description: str, tag: str) -> None:
    """Render the tab heading without competing with the global title bar."""
    render_section(title, description)


def scope_label(scope: dict) -> str:
    labels = []
    for name, value in (("Station", scope["station"]), ("System", scope["system"]), ("Sub-system", scope["subsystem"]), ("Year", scope["year"]), ("Month", scope["month"])):
        if value != "All":
            labels.append(f"{name}: {value}")
    return " · ".join(labels) if labels else "Network-wide view"


def render_scope_bar(records_df, month_names: list[str]) -> dict:
    """Render and persist the scope used throughout the operational tabs."""
    defaults = {"station": "All", "system": "All", "subsystem": "All", "year": "All", "month": "All"}
    if "applied_scope" not in st.session_state:
        st.session_state.applied_scope = defaults.copy()

    scope = st.session_state.applied_scope
    stations = ["All"]
    systems = ["All"]
    subsystems = ["All"]
    years = ["All"]
    if records_df is not None and not records_df.empty:
        stations += sorted(records_df["station"].dropna().unique().tolist())
        systems += sorted(records_df["system"].dropna().unique().tolist())
        filtered = records_df
        if scope["station"] != "All":
            filtered = filtered[filtered["station"] == scope["station"]]
        if scope["system"] != "All":
            filtered = filtered[filtered["system"] == scope["system"]]
        subsystems += sorted(filtered["subsystem"].dropna().unique().tolist())
        years += sorted(records_df["done_date"].dt.year.dropna().astype(int).astype(str).unique().tolist())

    # Handle selections that no longer exist after a parent scope changes.
    for key, options in (("station", stations), ("system", systems), ("subsystem", subsystems), ("year", years), ("month", month_names)):
        if scope[key] not in options:
            scope[key] = "All"

    with st.form("global_scope_form", border=False):
        st.caption("Applied operating scope")
        c1, c2, c3, c4, c5, c6, c7 = st.columns([1.2, 1.2, 1.2, .85, 1.05, .9, .8])
        with c1:
            station = st.selectbox("Station", stations, index=stations.index(scope["station"]))
        with c2:
            system = st.selectbox("System", systems, index=systems.index(scope["system"]))
        with c3:
            subsystem = st.selectbox("Sub-system", subsystems, index=subsystems.index(scope["subsystem"]))
        with c4:
            year = st.selectbox("Year", years, index=years.index(scope["year"]))
        with c5:
            month = st.selectbox("Month", month_names, index=month_names.index(scope["month"]))
        with c6:
            apply = st.form_submit_button("Apply scope", type="primary", width="stretch")
        with c7:
            reset = st.form_submit_button("Reset", type="secondary", width="stretch")

    if apply:
        st.session_state.applied_scope = {"station": station, "system": system, "subsystem": subsystem, "year": year, "month": month}
        st.session_state.pop("insight_result", None)
        st.rerun()
    if reset:
        st.session_state.applied_scope = defaults.copy()
        st.session_state.pop("insight_result", None)
        st.rerun()

    scope = st.session_state.applied_scope
    st.markdown(f"<div class='dmrc-scope'><strong>Viewing:</strong> {html.escape(scope_label(scope))}</div>", unsafe_allow_html=True)
    return scope


def style_chart(figure, *, height: int = 360):
    """Apply one visual treatment to every operational chart."""
    figure.update_layout(
        height=height,
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font=dict(color=INK, family="Inter, ui-sans-serif, system-ui, sans-serif"),
        margin=dict(l=16, r=16, t=48, b=16),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        title=dict(font=dict(size=16, color=NAVY)),
        coloraxis_colorbar=dict(thickness=12),
        colorway=["#0B6E99", "#7C3AED", "#D97706", "#C2410C", "#15803D", "#BE123C"],
        hoverlabel=dict(bgcolor="#082F49", bordercolor="#082F49", font=dict(color="#FFFFFF", size=13)),
    )
    figure.update_xaxes(gridcolor="#D9E2EC", zerolinecolor="#9FB3C8", tickfont=dict(color="#334E68"), title_font=dict(color="#172033"))
    figure.update_yaxes(gridcolor="#D9E2EC", zerolinecolor="#9FB3C8", tickfont=dict(color="#334E68"), title_font=dict(color="#172033"))
    return figure
