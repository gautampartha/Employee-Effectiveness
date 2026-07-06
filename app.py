<<<<<<< HEAD
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import pipeline
import failure_pipeline
import insights_engine
import requests
import json

# --- Constants for performance bands ---
COMPLIANCE_RED_THRESHOLD = 60.0
COMPLIANCE_AMBER_THRESHOLD = 85.0

COLOR_RED = "#d9534f"      # Red for critical (< 60%)
COLOR_AMBER = "#f0ad4e"    # Amber for needs attention (60% - 85%)
COLOR_GREEN = "#2E7D32"    # Dark Green for on target (> 85%)

# Helper functions for color mapping
def get_compliance_color(pct):
    if pct < COMPLIANCE_RED_THRESHOLD:
        return COLOR_RED
    elif pct < COMPLIANCE_AMBER_THRESHOLD:
        return COLOR_AMBER
    else:
        return COLOR_GREEN
=======
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

import pipeline


COMPLIANCE_RED_THRESHOLD = 60.0
COMPLIANCE_AMBER_THRESHOLD = 85.0

COLOR_RED = "#d9534f"
COLOR_AMBER = "#f0ad4e"
COLOR_GREEN = "#2E7D32"

BASE_DIR = Path(__file__).resolve().parent
PM_RECORDS_PATH = BASE_DIR / "pm_records_clean.csv"
PM_AGG_PATH = BASE_DIR / "pm_compliance_agg.csv"
FAILURE_LOG_PATH = BASE_DIR / "css.csv"
ERROR_LOOKUP_PATH = BASE_DIR / "errors.csv"


def get_compliance_color(pct):
    if pct < COMPLIANCE_RED_THRESHOLD:
        return COLOR_RED
    if pct < COMPLIANCE_AMBER_THRESHOLD:
        return COLOR_AMBER
    return COLOR_GREEN

>>>>>>> origin/main

def get_compliance_tier(pct):
    if pct < COMPLIANCE_RED_THRESHOLD:
        return "Critical (<60%)"
<<<<<<< HEAD
    elif pct < COMPLIANCE_AMBER_THRESHOLD:
        return "Needs Attention (60-85%)"
    else:
        return "On Target (>85%)"

def generate_insight_sentence(agg_df):
    """
    Finds the subsystem with the lowest compliance rate (minimum 20 records)
    and returns a natural English insight sentence.
    """
    # Group by subsystem and sum columns to find weighted compliance
    sub_agg = agg_df.groupby('subsystem', observed=True).agg(
        total_pm=('total_pm', 'sum'),
        on_time=('on_time', 'sum')
    ).reset_index()

    # Filter out small samples to avoid noise
    sub_agg = sub_agg[sub_agg['total_pm'] >= 20]

    if len(sub_agg) == 0:
        return "ℹ️ All metro subsystems are currently performing within standard compliance thresholds."

    sub_agg['compliance_pct'] = (sub_agg['on_time'] / sub_agg['total_pm'] * 100).round(1)
    worst_row = sub_agg.sort_values(by='compliance_pct', ascending=True).iloc[0]

    subsystem_name = worst_row['subsystem']
    compliance_val = worst_row['compliance_pct']
    total_val = worst_row['total_pm']

    return f"⚠️ **{subsystem_name}** maintenance is critically behind schedule network-wide, with only **{compliance_val:.1f}%** of its {total_val:,} trackable tasks completed on-time."

# Ollama integration for Ask Assistant
def build_data_context(pm_agg_df, failure_summary_df):
    """Build context string from aggregated data for Ollama prompting."""
    if pm_agg_df is None or pm_agg_df.empty:
        return "No PM data available."

    # Calculate overall metrics
    total_pm = int(pm_agg_df['total_pm'].sum())
    overall_compliance = 0.0
    if total_pm > 0:
        overall_compliance = round(pm_agg_df['on_time'].sum() / total_pm * 100, 1)

    # Worst performing subsystem (min 20 records)
    pm_agg_df_valid = pm_agg_df[pm_agg_df['total_pm'] >= 20].copy()
    worst_subsystem = "N/A"
    worst_subsystem_pct = 0.0
    if not pm_agg_df_valid.empty:
        pm_agg_df_valid['compliance_pct'] = (
            pm_agg_df_valid['on_time'] / pm_agg_df_valid['total_pm'] * 100
        ).round(1)
        worst_row = pm_agg_df_valid.loc[pm_agg_df_valid['compliance_pct'].idxmin()]
        worst_subsystem = worst_row['subsystem']
        worst_subsystem_pct = worst_row['compliance_pct']

    # Failure metrics
    total_failures = 0
    maintenance_gap_pct = 0.0
    top5_failure_stations = {}
    top5_worst_compliance = {}

    if failure_summary_df is not None and not failure_summary_df.empty:
        total_failures = int(failure_summary_df['total_failures'].sum())
        if total_failures > 0:
            maintenance_gap_count = failure_summary_df['maintenance_gap_count'].sum()
            maintenance_gap_pct = round(maintenance_gap_count / total_failures * 100, 1)

            # Top 5 stations by failure count
            if 'Station' in failure_summary_df.columns:
                station_totals = failure_summary_df.groupby('Station')['total_failures'].sum()
                top5_failure_stations = station_totals.nlargest(5).to_dict()

            # Top 5 worst compliance subsystems (from PM data, min 20 records)
            if not pm_agg_df_valid.empty:
                pm_agg_df_valid['compliance_pct'] = (
                    pm_agg_df_valid['on_time'] / pm_agg_df_valid['total_pm'] * 100
                ).round(1)
                worst_compliance = pm_agg_df_valid.nsmallest(5, 'compliance_pct')
                top5_worst_compliance = dict(zip(worst_compliance['subsystem'], worst_compliance['compliance_pct']))

    context = f"""
You are an AI assistant for Delhi Metro Rail Corporation (DMRC) maintenance operations.
You help managers and engineers understand maintenance performance data.
Answer questions concisely and practically. If you don't know something from
the data provided, say so — don't make up numbers.

CURRENT DATA SUMMARY:
- Total PM (maintenance) records: {total_pm:,}
- Overall PM compliance rate: {overall_compliance}% (% completed on time)
- Worst performing subsystem: {worst_subsystem} at {worst_subsystem_pct}% compliance
- Total failures recorded: {total_failures:,}
- Failures caused by maintenance gaps: {maintenance_gap_pct}%
- Top 5 stations by failure count: {top5_failure_stations}
- Top 5 worst compliance subsystems: {top5_worst_compliance}
"""
    return context

def ask_ollama(question: str, context: str) -> str:
    """Query Ollama API with context and question."""
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.2:1b",
                "prompt": f"{context}\n\nQuestion: {question}\n\nAnswer:",
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 300
                }
            },
            timeout=60
        )
        response.raise_for_status()
        return response.json()['response'].strip()
    except requests.exceptions.ConnectionError:
        return "❌ Ollama is not running. Please start it with: ollama serve"
    except requests.exceptions.Timeout:
        return "⏱️ Response timed out. The model is slow on this machine — try a shorter question."
    except Exception as e:
        return f"❌ Error: {str(e)}"

# --- Page Config and Styling ---
st.set_page_config(
    page_title="DMRC Employee Effectiveness System",
    page_icon="🚇",
    layout="wide"
)

# Custom DMRC sapphire blue styling banner
st.markdown("""
    <div style='background-color:#0A3A60; padding:20px; border-radius:10px; margin-bottom:25px; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);'>
        <h1 style='color:white; margin:0; font-family:sans-serif;'>Delhi Metro Rail Corporation</h1>
        <h3 style='color:#A6D1FF; margin:5px 0 0 0; font-family:sans-serif; font-weight:normal;'>Employee Effectiveness System — PM Compliance Dashboard</h3>
    </div>
""", unsafe_allow_html=True)

# --- Data Loading ---
@st.cache_data
def load_all_data():
    import pandas as pd
    from pathlib import Path

    BASE_DIR = Path(__file__).resolve().parent
    PM_RECORDS_PATH = BASE_DIR / "pm_records_clean.csv"
    PM_AGG_PATH = BASE_DIR / "pm_compliance_agg.csv"
    FAILURE_LOG_PATH = BASE_DIR / "css.csv"
    ERROR_LOOKUP_PATH = BASE_DIR / "errors.csv"

    records_df = pipeline.load_records_clean(PM_RECORDS_PATH) if PM_RECORDS_PATH.exists() else None
    agg_df = pipeline.load_compliance_agg(PM_AGG_PATH)

    # Load failure data if files exist
    failure_df = None
    pm_date_range = None
    if records_df is not None:
        pm_date_range = pipeline.get_pm_date_bounds(records_df)

    if FAILURE_LOG_PATH.exists() and ERROR_LOOKUP_PATH.exists():
        failure_df = failure_pipeline.load_failures()
        # Apply PM date range filtering if available (similar to teammate's approach)
        if (
            failure_df is not None
            and pm_date_range
            and pm_date_range[0] is not None
            and pm_date_range[1] is not None
        ):
            start_date, end_date = (
                pd.to_datetime(pm_date_range[0]),
                pd.to_datetime(pm_date_range[1]),
            )
            failure_df = failure_df[
                (failure_df["Date"] >= start_date)
                & (failure_df["Date"] <= end_date)
            ].copy()

    return records_df, agg_df, failure_df, pm_date_range

failure_df = None
try:
    result = load_all_data()
    if len(result) == 4:
        records_df, agg_df, failure_df, pm_date_range = result
    else:
        # Backward compatibility
        records_df, agg_df = result
        failure_df, pm_date_range = None, None
except Exception as e:
    st.error(f"Error loading data: {e}")
    st.info(
        "Make sure 'pm_records_clean.csv' and 'pm_compliance_agg.csv' are in the dashboard directory."
    )
    st.stop()

# Compute failure summary for insights and context
if failure_df is not None and not failure_df.empty:
    failure_summary_df = failure_pipeline.get_failure_summary(failure_df)
else:
    failure_summary_df = pd.DataFrame()

# --- Create Navigation Tabs (5 tabs now) ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📊 Overview", "🕵️ Detailed Explorer", "🚨 Failure Analysis", "🤖 Ask Assistant", "💡 Insights"]
)

# ==============================================================================
# TAB 1: OVERVIEW (Managerial view)
# ==============================================================================
with tab1:
    st.subheader("Network-wide Summary Insight")

    # 1. Insight Sentence at the very top
    insight = generate_insight_sentence(agg_df)
    st.info(insight)

    st.write("")

    # 2. KPI Summary Cards (computed unfiltered for network-wide view)
    network_kpis = pipeline.compute_compliance_summary(records_df)
    network_comp_pct = network_kpis['compliance_pct']
    comp_color = get_compliance_color(network_comp_pct)

    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)

    # Render custom HTML cards to display English explanations and apply color bands
    with kpi_col1:
        st.markdown(
            f"""
            <div style="background-color: #F4F6F9; border-left: 5px solid #0A3A60; padding: 15px; border-radius: 8px; box-shadow: 1px 1px 3px rgba(0,0,0,0.05); min-height: 120px;">
                <p style="margin: 0; font-size: 13px; color: #6c757d; font-weight: bold; text-transform: uppercase;">Total PM Actions</p>
                <p style="margin: 5px 0 0 0; font-size: 26px; color: #0A3A60; font-weight: bold;">{network_kpis['total_pm']:,}</p>
                <p style="margin: 5px 0 0 0; font-size: 11px; color: #6c757d; line-height: 1.2;">Total completed maintenance events (excluding baseline records).</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with kpi_col2:
        st.markdown(
            f"""
            <div style="background-color: #F4F6F9; border-left: 5px solid {comp_color}; padding: 15px; border-radius: 8px; box-shadow: 1px 1px 3px rgba(0,0,0,0.05); min-height: 120px;">
                <p style="margin: 0; font-size: 13px; color: #6c757d; font-weight: bold; text-transform: uppercase;">Compliance Rate</p>
                <p style="margin: 5px 0 0 0; font-size: 26px; color: {comp_color}; font-weight: bold;">{network_comp_pct:.1f}%</p>
                <p style="margin: 5px 0 0 0; font-size: 11px; color: #6c757d; line-height: 1.2;">% of maintenance completed on-time (within the 3-day grace period).</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with kpi_col3:
        avg_late = network_kpis['avg_days_late']
        avg_late_str = f"{abs(avg_late):.1f} days early" if avg_late < 0 else f"{avg_late:.1f} days late"
        st.markdown(
            f"""
            <div style="background-color: #F4F6F9; border-left: 5px solid #0A3A60; padding: 15px; border-radius: 8px; box-shadow: 1px 1px 3px rgba(0,0,0,0.05); min-height: 120px;">
                <p style="margin: 0; font-size: 13px; color: #6c757d; font-weight: bold; text-transform: uppercase;">Average Delay</p>
                <p style="margin: 5px 0 0 0; font-size: 26px; color: #0A3A60; font-weight: bold;">{avg_late_str}</p>
                <p style="margin: 5px 0 0 0; font-size: 11px; color: #6c757d; line-height: 1.2;">Average delay relative to expected due date (negative is early).</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with kpi_col4:
        st.markdown(
            f"""
            <div style="background-color: #F4F6F9; border-left: 5px solid #d9534f; padding: 15px; border-radius: 8px; box-shadow: 1px 1px 3px rgba(0,0,0,0.05); min-height: 120px;">
                <p style="margin: 0; font-size: 13px; color: #6c757d; font-weight: bold; text-transform: uppercase;">Late PM Count</p>
                <p style="margin: 5px 0 0 0; font-size: 26px; color: #d9534f; font-weight: bold;">{network_kpis['late']:,}</p>
                <p style="margin: 5px 0 0 0; font-size: 11px; color: #6c757d; line-height: 1.2;">Total number of maintenance actions that missed the on-time window.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")
    st.write("")

    # 3. Ranked Horizontal Bar Chart
    st.subheader("🚨 Compliance Performance Rankings (Bottom 15)")
    st.markdown(
        "Group data network-wide and identify components lagging behind compliance targets (minimum threshold: 20 records)."
    )

    # Toggle to switch groupings
    groupby_option = st.radio(
        "Group Rankings By:", ["Subsystem", "Station"], horizontal=True, key="rank_groupby"
    )

    if groupby_option == "Subsystem":
        group_cols = ['subsystem']
        label_name = 'Sub-System'
    else:
        group_cols = ['station']
        label_name = 'Station Code'

    # Group the agg_df to get correct weighted mean
    ranked_df = agg_df.groupby(group_cols, observed=True).agg(
        total_pm=('total_pm', 'sum'),
        on_time=('on_time', 'sum')
    ).reset_index()

    # Apply minimum sample threshold of 20 to avoid noise
    ranked_df = ranked_df[ranked_df['total_pm'] >= 20]

    if len(ranked_df) == 0:
        st.info("No records meet the minimum threshold of 20 total PMs to display.")
    else:
        ranked_df['compliance_pct'] = (ranked_df['on_time'] / ranked_df['total_pm'] * 100).round(1)

        # Sort worst-to-best (lowest compliance first)
        ranked_df = ranked_df.sort_values(by='compliance_pct', ascending=True).head(15)

        # Apply color categorization
        ranked_df['Performance'] = ranked_df['compliance_pct'].apply(get_compliance_tier)

        # Render horizontal bar chart
        fig_bar = px.bar(
            ranked_df,
            x='compliance_pct',
            y=group_cols[0],
            color='Performance',
            color_discrete_map={
                "Critical (<60%)": COLOR_RED,
                "Needs Attention (60-85%)": COLOR_AMBER,
                "On Target (>85%)": COLOR_GREEN
            },
            orientation='h',
            labels={'compliance_pct': 'Compliance Rate (%)', group_cols[0]: label_name},
            text='compliance_pct'
        )

        # Format layout
        fig_bar.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
        fig_bar.update_xaxes(range=[0, 110])
        fig_bar.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            height=450,
            yaxis={'categoryorder': 'total descending'},  # Show worst performing on top
            legend_title_text="Performance Tier"
        )
        st.plotly_chart(fig_bar, width='stretch')


# ==============================================================================
# TAB 2: DETAILED EXPLORER (Engineer/Analyst view)
# ==============================================================================
with tab2:
    st.subheader("🕵️ Detailed Data Explorer")
    st.markdown(
        "Use the control dropdowns below to filter the record dataset and generate localized heatmap, trend, and overdue reports."
    )

    # Dynamic controls row
    f_c1, f_c2, f_c3, f_c4, f_c5, f_c6 = st.columns(6)

    with f_c1:
        # Station Filter
        stations = ["All"] + sorted(list(records_df['station'].dropna().unique()))
        station_val = st.selectbox("Station Code", stations, index=0, key="exp_station")
    with f_c2:
        # System Filter
        systems = ["All"] + sorted(list(records_df['system'].dropna().unique()))
        system_val = st.selectbox("System", systems, index=0, key="exp_system")
    with f_c3:
        # Cascading Sub-System Filter
        if system_val != "All":
            available_subsystems = sorted(list(records_df[records_df['system'] == system_val]['subsystem'].dropna().unique()))
        else:
            available_subsystems = sorted(list(records_df['subsystem'].dropna().unique()))
        subsystem_val = st.selectbox("Sub-System", ["All"] + available_subsystems, index=0, key="exp_subsystem")
    with f_c4:
        # Schedule Filter (Frequency)
        schedules = ["All"] + sorted(list(records_df['schedule_name'].dropna().unique()))
        schedule_val = st.selectbox("Schedule Frequency", schedules, index=0, key="exp_schedule")
    with f_c5:
        # Simplified Date Filters - Year
        years = ["All"] + sorted(list(records_df['done_date'].dt.year.dropna().unique().astype(str)))
        year_val = st.selectbox("Year", years, index=0, key="exp_year")
    with f_c6:
        # Simplified Date Filters - Month
        months_names = ["All", "January", "February", "March", "April", "May", "June",
                        "July", "August", "September", "October", "November", "December"]
        month_val = st.selectbox("Month", months_names, index=0, key="exp_month")

    # Apply dropdown filters to records
    filtered_df = pipeline.filter_records(
        records_df,
        station=station_val,
        system=system_val,
        subsystem=subsystem_val,
        schedule_name=schedule_val,
        year=year_val,
        month=month_val
    )

    # Recompute live KPIs
    kpis = pipeline.compute_compliance_summary(filtered_df)
    comp_pct_val = kpis['compliance_pct']
    comp_col_val = get_compliance_color(comp_pct_val)

    # Live KPI Metric display row
    st.write("")
    k_col1, k_col2, k_col3, k_col4 = st.columns(4)
    with k_col1:
        st.metric(label="Total PM Actions (Trackable)", value=f"{kpis['total_pm']:,}")
    with k_col2:
        st.metric(label="PM Compliance Rate", value=f"{comp_pct_val:.1f}%")
    with k_col3:
        avg_late = kpis['avg_days_late']
        avg_late_str = f"{abs(avg_late):.1f} days early" if avg_late < 0 else f"{avg_late:.1f} days late"
        st.metric(label="Average Delay", value=avg_late_str)
    with k_col4:
        st.metric(label="Late PM Count", value=f"{kpis['late']:,}")

    st.markdown("---")

    # Tab 2 Visualizations (Heatmap & Trendline)
    vis_col1, vis_col2 = st.columns([1, 1])

    with vis_col1:
        st.subheader("🗺️ Station vs Subsystem Compliance Heatmap")
        st.markdown(
            "Displays weighted average compliance. Limit stations using the slider below to prevent clutter."
        )

        # Heatmap controls
        h_c1, h_c2 = st.columns(2)
        with h_c1:
            heatmap_system = st.selectbox(
                "Heatmap System Filter",
                options=["All"] + sorted(list(agg_df['system'].dropna().unique())),
                index=0 if system_val == "All" else sorted(list(agg_df['system'].dropna().unique())).index(system_val) + 1,
                key="heatmap_sys_select"
            )
        with h_c2:
            top_n = st.slider("Display Busiest Stations Limit", min_value=5, max_value=50, value=25, key="heatmap_top_n")

        # Select data dynamically based on whether Year/Month filters are active
        if year_val != "All" or month_val != "All":
            h_records = filtered_df
            if heatmap_system != "All":
                h_records = h_records[h_records['system'] == heatmap_system]

            trackable_records = h_records[h_records['compliance_status'] != 'baseline']

            if len(trackable_records) == 0:
                agg_heatmap = pd.DataFrame(columns=['station', 'subsystem', 'total_pm', 'on_time', 'compliance_pct'])
            else:
                agg_heatmap = (
                    trackable_records.groupby(
                        ['station', 'subsystem'], as_index=False, observed=True
                    ).agg(
                        total_pm=('compliance_status', 'count'),
                        on_time=('compliance_status', lambda x: (x == 'on_time').sum())
                    )
                )
                agg_heatmap = agg_heatmap[agg_heatmap['total_pm'] > 0]
                agg_heatmap['compliance_pct'] = (
                    (agg_heatmap['on_time'] / agg_heatmap['total_pm'] * 100).round(1)
                )
        else:
            h_df = agg_df
            if station_val != "All":
                h_df = h_df[h_df['station'] == station_val]
            if heatmap_system != "All":
                h_df = h_df[h_df['system'] == heatmap_system]
            if subsystem_val != "All":
                h_df = h_df[h_df['subsystem'] == subsystem_val]
            if schedule_val != "All":
                h_df = h_df[h_df['schedule_name'] == schedule_val]

            if len(h_df) == 0:
                agg_heatmap = pd.DataFrame(columns=['station', 'subsystem', 'total_pm', 'on_time', 'compliance_pct'])
            else:
                agg_heatmap = (
                    h_df.groupby(
                        ['station', 'subsystem'], as_index=False, observed=True
                    ).agg(
                        total_pm=('total_pm', 'sum'),
                        on_time=('on_time', 'sum')
                    )
                )
                agg_heatmap = agg_heatmap[agg_heatmap['total_pm'] > 0]
                agg_heatmap['compliance_pct'] = (
                    (agg_heatmap['on_time'] / agg_heatmap['total_pm'] * 100).round(1)
                )

        if len(agg_heatmap) == 0:
            st.info("No active records found matching selections to display in heatmap.")
        else:
            # Filter to top N busiest stations
            station_totals = (
                agg_heatmap.groupby('station', observed=True)['total_pm'].sum().reset_index()
            )
            top_stations = (
                station_totals.sort_values(by='total_pm', ascending=False).head(top_n)['station']
            )
            agg_heatmap = agg_heatmap[agg_heatmap['station'].isin(top_stations)]

            if len(agg_heatmap) == 0:
                st.info("No active records to display in heatmap.")
            else:
                pivot_df = agg_heatmap.pivot(
                    index='station', columns='subsystem', values='compliance_pct'
                )
                pivot_df = pivot_df.sort_index(ascending=True)  # Sort alphabetically

                fig_heatmap = px.imshow(
                    pivot_df,
                    labels=dict(x="Subsystem", y="Station Code", color="Compliance %"),
                    x=pivot_df.columns,
                    y=pivot_df.index,
                    color_continuous_scale="RdYlGn",
                    color_continuous_midpoint=75.0,
                    aspect="auto"
                )
                fig_heatmap.update_layout(
                    margin=dict(l=10, r=10, t=10, b=10),
                    height=350,
                    coloraxis_colorbar=dict(title="Compliance %")
                )
                st.plotly_chart(fig_heatmap, width='stretch')

    with vis_col2:
        st.subheader("📈 Monthly Compliance Trend")
        st.markdown(
            "Chronological progression of the compliance rate over time (grouped by month)."
        )

        # Compute trendline
        trend_df = filtered_df[filtered_df['compliance_status'] != 'baseline'].copy()

        if len(trend_df) == 0:
            st.info("No compliance events recorded inside this timeframe/filter selection.")
        else:
            trend_df['month'] = trend_df['done_date'].dt.to_period('M').astype(str)
            monthly_agg = (
                trend_df.groupby('month', observed=True).agg(
                    total_pm=('compliance_status', 'count'),
                    on_time=('compliance_status', lambda x: (x == 'on_time').sum())
                ).reset_index()
            )
            monthly_agg['compliance_pct'] = (
                (monthly_agg['on_time'] / monthly_agg['total_pm'] * 100).round(1)
            )

            fig_trend = px.line(
                monthly_agg,
                x='month',
                y='compliance_pct',
                labels={'month': 'Month of PM Completion', 'compliance_pct': 'Compliance %'},
                markers=True,
                color_discrete_sequence=['#0A3A60']
            )
            fig_trend.update_yaxes(range=[0, 105])
            fig_trend.update_layout(
                margin=dict(l=10, r=10, t=20, b=10),
                height=350,
                hovermode="x unified"
            )
            st.plotly_chart(fig_trend, width='stretch')

    st.markdown("---")

    # Overdue Table
    st.subheader("⚠️ Late / Overdue Records Details")
    st.markdown(
        "List of individual maintenance events completed late. Sort, search, or download the filtered list as a CSV."
    )

    late_df = filtered_df[filtered_df['compliance_status'] == 'late']

    if len(late_df) == 0:
        st.success("🎉 Excellent! All PM tasks in this selection were completed on time!")
    else:
        display_cols = [
            'EqpID', 'Eqp_Name', 'station', 'subsystem',
            'schedule_name', 'done_date', 'expected_due_date', 'days_late'
        ]
        late_table = (
            late_df[display_cols].sort_values(by='days_late', ascending=False)
        )

        st.dataframe(
            late_table,
            column_config={
                "EqpID": st.column_config.TextColumn("Equipment ID"),
                "Eqp_Name": st.column_config.TextColumn("Equipment Name"),
                "station": st.column_config.TextColumn("Station"),
                "subsystem": st.column_config.TextColumn("Sub-System"),
                "schedule_name": st.column_config.TextColumn("Frequency"),
                "done_date": st.column_config.DateColumn("Done Date", format="YYYY-MM-DD"),
                "expected_due_date": st.column_config.DateColumn("Expected Due Date", format="YYYY-MM-DD"),
                "days_late": st.column_config.NumberColumn("Days Late", format="%d")
            },
            width='stretch',
            hide_index=True
        )

        csv_bytes = late_table.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Filtered Late Records as CSV",
            data=csv_bytes,
            file_name=f"dmrc_late_records_{station_val}_{system_val}.csv",
            mime="text/csv",
            key="dl_btn_tab2"
        )

# ==============================================================================
# TAB 3: FAILURE ANALYSIS (Existing tab)
# ==============================================================================
with tab3:
    st.subheader("🚨 Failure Analysis Dashboard")
    st.markdown(
        "Analyze failures classified as Maintenance Gap or Equipment Failure based on PM compliance."
    )

    # Load failure and PM data
    @st.cache_data
    def load_failure_data():
        failures_df = failure_pipeline.load_failures()
        pm_df = failure_pipeline.load_pm_records()
        return failures_df, pm_df

    failures_raw, pm_raw = load_failure_data()

    # Classify failures
    with st.spinner("Classifying failures..."):
        classified_df = failure_pipeline.classify_failures(failures_raw, pm_raw)

    # Sidebar filters for this tab
    st.sidebar.header("Failure Analysis Filters")

    # System dropdown
    system_options = ["All"] + sorted(list(classified_df['System'].dropna().unique()))
    system_selected = st.sidebar.selectbox("System", system_options, key="fa_system")

    # Filter by system
    if system_selected != "All":
        filtered = classified_df[classified_df['System'] == system_selected]
    else:
        filtered = classified_df.copy()

    # Subsystem dropdown (cascading)
    subsystem_options = ["All"] + sorted(list(filtered['SubSystem'].dropna().unique()))
    subsystem_selected = st.sidebar.selectbox("Sub-System", subsystem_options, key="fa_subsystem")

    if subsystem_selected != "All":
        filtered = filtered[filtered['SubSystem'] == subsystem_selected]

    # Station dropdown
    station_options = ["All"] + sorted(list(filtered['Station'].dropna().unique()))
    station_selected = st.sidebar.selectbox("Station", station_options, key="fa_station")

    if station_selected != "All":
        filtered = filtered[filtered['Station'] == station_selected]

    # Date range filter
    min_date = (
        filtered['Date'].min().date()
        if not filtered['Date'].isnull().all()
        else None
    )
    max_date = (
        filtered['Date'].max().date()
        if not filtered['Date'].isnull().all()
        else None
    )
    if min_date and max_date:
        date_range = st.sidebar.date_input(
            "Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            key="fa_date_range"
        )
        if len(date_range) == 2:
            start_date, end_date = date_range
            filtered = filtered[
                (filtered['Date'].dt.date >= start_date)
                & (filtered['Date'].dt.date <= end_date)
            ]

    # If filtered is empty, show warning
    if filtered.empty:
        st.warning("No data matches the selected filters.")
        st.stop()

    # KPI Row
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)

    total_failures = len(filtered)
    mg_count = (filtered['failure_label'] == 'Maintenance Gap Failure').sum()
    eq_count = (filtered['failure_label'] == 'Equipment Failure').sum()
    npm_count = (filtered['failure_label'] == 'No PM Record').sum()

    mg_pct = (mg_count / total_failures * 100) if total_failures > 0 else 0
    eq_pct = (eq_count / total_failures * 100) if total_failures > 0 else 0

    # Average resolution time (hours), excluding Duration > 9999
    valid_dur = filtered[filtered['Duration'] <= 9999]['Duration']
    avg_hrs = (valid_dur.mean() / 60) if not valid_dur.empty else 0

    with kpi1:
        st.metric("Total Failures (Resolved)", f"{total_failures:,}")
    with kpi2:
        st.metric(
            "Maintenance Gap Failures",
            f"{mg_count:,} ({mg_pct:.1f}%)",
            delta_color="inverse"
        )
    with kpi3:
        st.metric(
            "Equipment Failures",
            f"{eq_count:,} ({eq_pct:.1f}%)",
        )
    with kpi4:
        st.metric("Avg Resolution Time (hrs)", f"{avg_hrs:.1f}")

    st.markdown("---")

    # Failure Classification Breakdown (pie/donut chart)
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("Failure Classification Breakdown")
        fig_pie = px.pie(
            filtered,
            names='failure_label',
            title='Failure Classification Distribution',
            color='failure_label',
            color_discrete_map={
                'Maintenance Gap Failure': COLOR_RED,
                'Equipment Failure': COLOR_AMBER,
                'No PM Record': '#6c757d'  # gray
            },
            hole=0.4
        )
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_pie, width='stretch')

    # Top 10 Worst Stations by Failure Count
    with col2:
        st.subheader("Top 10 Worst Stations by Failure Count")
        # Compute per-station stats
        station_stats = (
            filtered.groupby("Station")
            .agg(
                total_failures=("failure_label", "size"),
                mg_count=(
                    "failure_label",
                    lambda x: (x == "Maintenance Gap Failure").sum()
                )
            )
            .reset_index()
        )
        station_stats["mg_pct"] = (
            (station_stats["mg_count"] / station_stats["total_failures"] * 100)
            .fillna(0)
        )
        # Determine dominant label color: red if >50% MG, else amber
        station_scores = (
            station_stats["mg_pct"].apply(
                lambda x: COLOR_RED if x > 50 else COLOR_AMBER
            )
        )
        # Top 10 by total failures
        top_stations = (
            station_stats.sort_values("total_failures", ascending=False).head(10)
        )
        # Get colors only for the top stations
        top_station_scores = station_scores.loc[top_stations.index]
        fig_bar = px.bar(
            top_stations,
            x="total_failures",
            y="Station",
            orientation="h",
            color=top_station_scores,
            color_discrete_map={c: c for c in [COLOR_RED, COLOR_AMBER]},
            labels={"total_failures": "Failure Count", "Station": "Station Code"},
            text="total_failures"
        )
        fig_bar.update_traces(texttemplate="%{text}", textposition="outside")
        fig_bar.update_layout(
            showlegend=False,
            xaxis_title="Failure Count",
            yaxis_title="",
            yaxis={"categoryorder": "total ascending"}
        )
        st.plotly_chart(fig_bar, width="stretch")

    st.markdown("---")

    # Subsystem Failure Frequency Table
    st.subheader("Subsystem Failure Frequency")
    subsystem_stats = (
        filtered.groupby("SubSystem")
        .agg(
            total_failures=("failure_label", "size"),
            mg_count=(
                "failure_label",
                lambda x: (x == "Maintenance Gap Failure").sum()
            ),
            eq_count=(
                "failure_label",
                lambda x: (x == "Equipment Failure").sum()
            ),
            npm_count=(
                "failure_label",
                lambda x: (x == "No PM Record").sum()
            ),
            avg_duration=(
                "Duration",
                lambda x: (x[x <= 9999].mean() if not x[x <= 9999].empty else 0)
            )
        )
        .reset_index()
    )
    subsystem_stats["mg_pct"] = (
        (subsystem_stats["mg_count"] / subsystem_stats["total_failures"] * 100)
        .round(1)
    )
    subsystem_stats["eq_pct"] = (
        (subsystem_stats["eq_count"] / subsystem_stats["total_failures"] * 100)
        .round(1)
    )
    subsystem_stats["npm_pct"] = (
        (subsystem_stats["npm_count"] / subsystem_stats["total_failures"] * 100)
        .round(1)
    )
    subsystem_stats["avg_duration_hrs"] = (
        (subsystem_stats["avg_duration"] / 60).round(1)
    )

    # Sort by total failures descending
    subsystem_stats = (
        subsystem_stats.sort_values("total_failures", ascending=False)
    )

    # Display table
    st.dataframe(
        subsystem_stats[
            [
                "SubSystem",
                "total_failures",
                "mg_pct",
                "eq_pct",
                "npm_pct",
                "avg_duration_hrs"
            ]
        ],
        column_config={
            "SubSystem": st.column_config.TextColumn("Sub-System"),
            "total_failures": st.column_config.NumberColumn("Total Failures", format="%d"),
            "mg_pct": st.column_config.NumberColumn("MG %", format="%.1f%%"),
            "eq_pct": st.column_config.NumberColumn("EQ %", format="%.1f%%"),
            "npm_pct": st.column_config.NumberColumn("No PM %", format="%.1f%%"),
            "avg_duration_hrs": st.column_config.NumberColumn("Avg Res (hrs)", format="%.1f")
        },
        width="stretch",
        hide_index=True
    )

    st.markdown("---")

    # Trend chart: monthly failure count stacked by failure_label
    st.subheader("Monthly Failure Trend (Stacked by Cause)")
    # Ensure we have Date column
    trend_df = filtered.copy()
    trend_df["Month"] = (
        trend_df["Date"].dt.to_period("M").astype(str)
    )
    trend_monthly = (
        trend_df.groupby(["Month", "failure_label"])
        .size()
        .reset_index(name="count")
    )
    fig_trend = px.bar(
        trend_monthly,
        x="Month",
        y="count",
        color="failure_label",
        color_discrete_map={
            "Maintenance Gap Failure": COLOR_RED,
            "Equipment Failure": COLOR_AMBER,
            "No PM Record": "#6c757d"
        },
        labels={"Month": "Month", "count": "Failure Count", "failure_label": "Failure Cause"},
        title="Monthly Failure Count by Cause"
    )
    fig_trend.update_layout(
        xaxis_tickangle=-45,
        legend_title_text="Failure Cause",
        barmode="stack"
    )
    st.plotly_chart(fig_trend, width="stretch")

# ==============================================================================
# TAB 4: ASK ASSISTANT (New tab with Ollama integration)
# ==============================================================================
with tab4:
    st.subheader("🤖 Ask Assistant")
    st.caption("Powered by Llama 3.2 (local) — responses take 15-30 seconds on this machine")

    # Initialize chat history for this tab
    if "assistant_chat_history" not in st.session_state:
        st.session_state.assistant_chat_history = []

    # Display chat history
    for chat in st.session_state.assistant_chat_history:
        if chat["role"] == "user":
            st.markdown(f"**You:** {chat['content']}")
        else:
            st.markdown(f"**Assistant:** {chat['content']}")

    # Input area
    col1, col2 = st.columns([4, 1])
    with col1:
        user_question = st.text_input(
            "Ask a question about maintenance performance:",
            placeholder="e.g., Which stations need urgent attention?",
            key="assistant_input"
        )
    with col2:
        ask_button = st.button("Ask", type="primary", use_container_width=True)

    # Example questions as buttons
    st.caption("Try these example questions:")
    col1, col2, col3 = st.columns(3)
    example_questions = [
        "Which stations need urgent attention?",
        "What is causing most failures at GATE subsystem?",
        "Which subsystem has the worst maintenance compliance?",
        "What percentage of failures are due to maintenance gaps?",
        "Which stations have the most equipment failures?"
    ]

    # Handle example button clicks
    if col1.button(example_questions[0], key="ex1"):
        user_question = example_questions[0]
        ask_button = True
    if col2.button(example_questions[1], key="ex2"):
        user_question = example_questions[1]
        ask_button = True
    if col3.button(example_questions[2], key="ex3"):
        user_question = example_questions[2]
        ask_button = True
    # Add more examples in a second row if needed
    col4, col5, col6 = st.columns(3)
    if col4.button(example_questions[3], key="ex4"):
        user_question = example_questions[3]
        ask_button = True
    if col5.button(example_questions[4], key="ex5"):
        user_question = example_questions[4]
        ask_button = True

    # Process question
    if ask_button and user_question.strip():
        # Add user message to history
        st.session_state.assistant_chat_history.append({"role": "user", "content": user_question})

        # Build context and get response
        with st.spinner("Thinking..."):
            context = build_data_context(agg_df, failure_summary_df)
            response = ask_ollama(user_question, context)

        # Add assistant response to history
        st.session_state.assistant_chat_history.append({"role": "assistant", "content": response})

        # Rerun to update display
        st.rerun()

    # Clear chat button
    if st.button("Clear Conversation", type="secondary"):
        st.session_state.assistant_chat_history = []
        st.rerun()

# ==============================================================================
# TAB 5: INSIGHTS (New tab with rule-based insights)
# ==============================================================================
with tab5:
    st.subheader("💡 Auto-Generated Maintenance Insights")
    st.caption("Updated each time the dashboard loads — based on current data")

    # Generate insights
    insights = insights_engine.generate_insights(agg_df, failure_summary_df)

    if not insights:
        st.info("No insights generated. Please check that data is loaded correctly.")
    else:
        # Count critical issues
        critical_count = sum(1 for i in insights if i["priority"] == "critical")
        if critical_count > 0:
            st.error(f"🔴 {critical_count} critical issue(s) require immediate attention")
        else:
            st.success("✅ No critical issues detected")

        # Display each insight as a card
        for insight in insights:
            # Determine styling based on priority
            if insight["priority"] == "critical":
                border_color = COLOR_RED
                icon = "🔴"
                bg_color = "#FFF0F0"  # Light red background
            elif insight["priority"] == "warning":
                border_color = COLOR_AMBER
                icon = "🟡"
                bg_color = "#FFF9F0"  # Light amber background
            else:  # positive
                border_color = COLOR_GREEN
                icon = "🟢"
                bg_color = "#F0FFF0"  # Light green background

            st.markdown(
                f"""
                <div style="
                    border-left: 4px solid {border_color};
                    background-color: {bg_color};
                    padding: 16px;
                    margin: 12px 0;
                    border-radius: 0 8px 8px 0;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                ">
                    <div style="display: flex; align-items: flex-start; margin-bottom: 8px;">
                        <span style="font-size: 1.2em; margin-right: 8px;">{icon}</span>
                        <div>
                            <span style="
                                background-color: {border_color};
                                color: white;
                                padding: 2px 8px;
                                border-radius: 12px;
                                font-size: 0.8em;
                                font-weight: bold;
                                margin-right: 8px;
                            ">
                                {insight['priority'].upper()}
                            </span>
                            <span style="
                                background-color: #E0E0E0;
                                color: #333;
                                padding: 2px 8px;
                                border-radius: 12px;
                                font-size: 0.8em;
                            ">
                                {insight['category']}
                            </span>
                        </div>
                    </div>
                    <h4 style="margin: 0 0 8px 0; color: #333; font-size: 1.1em;">
                        {insight['title']}
                    </h4>
                    <p style="margin: 0 0 8px 0; color: #555; line-height: 1.4;">
                        {insight['detail']}
                    </p>
                    <p style="margin: 0; color: #555; font-style: italic; line-height: 1.4;">
                        {insight['action']}
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
=======
    if pct < COMPLIANCE_AMBER_THRESHOLD:
        return "Needs Attention (60-85%)"
    return "On Target (>85%)"


def format_avg_delay(avg_late):
    return f"{abs(avg_late):.1f} days early" if avg_late < 0 else f"{avg_late:.1f} days late"


def filter_agg_df(df, station=None, system=None, subsystem=None, schedule_name=None):
    filtered_df = df
    if station and station != "All":
        filtered_df = filtered_df[filtered_df["station"] == station]
    if system and system != "All":
        filtered_df = filtered_df[filtered_df["system"] == system]
    if subsystem and subsystem != "All":
        filtered_df = filtered_df[filtered_df["subsystem"] == subsystem]
    if schedule_name and schedule_name != "All":
        filtered_df = filtered_df[filtered_df["schedule_name"] == schedule_name]
    return filtered_df


def generate_pm_insight_sentence(agg_df):
    sub_agg = (
        agg_df.groupby("subsystem", observed=True)
        .agg(total_pm=("total_pm", "sum"), on_time=("on_time", "sum"))
        .reset_index()
    )
    sub_agg = sub_agg[sub_agg["total_pm"] >= 20]

    if sub_agg.empty:
        return "All metro subsystems are currently performing within standard compliance thresholds."

    sub_agg["compliance_pct"] = (sub_agg["on_time"] / sub_agg["total_pm"] * 100).round(1)
    worst_row = sub_agg.sort_values("compliance_pct", ascending=True).iloc[0]
    return (
        f"{worst_row['subsystem']} is the weakest PM pocket right now with "
        f"{worst_row['compliance_pct']:.1f}% on-time completion across "
        f"{int(worst_row['total_pm']):,} trackable tasks."
    )


def generate_failure_insight_sentence(failure_df):
    if failure_df.empty:
        return "No failure events are available for the selected scope."

    top_subsystem = failure_df["subsystem"].value_counts(dropna=True).head(1)
    top_error = failure_df["error_description"].value_counts(dropna=True).head(1)

    if top_subsystem.empty or top_error.empty:
        return "Failure history is loaded, but the selected slice has limited categorical detail."

    subsystem = top_subsystem.index[0]
    subsystem_count = int(top_subsystem.iloc[0])
    error_name = top_error.index[0]
    error_count = int(top_error.iloc[0])

    return (
        f"{subsystem} is the most failure-prone subsystem in this slice "
        f"({subsystem_count:,} events), and the most repeated issue is "
        f"'{error_name}' ({error_count:,} times)."
    )


def generate_relation_insight_sentence(monthly_df):
    if monthly_df.empty:
        return "PM and failure history do not overlap enough in this selection to infer a monthly relationship."

    worst_failure_month = monthly_df.sort_values("failure_count", ascending=False).iloc[0]
    worst_pm_month = monthly_df.sort_values("compliance_pct", ascending=True).iloc[0]

    return (
        f"Peak failure load appears in {worst_failure_month['month']} "
        f"({int(worst_failure_month['failure_count']):,} failures), while the weakest PM month is "
        f"{worst_pm_month['month']} ({worst_pm_month['compliance_pct']:.1f}% compliance)."
    )


@st.cache_data(show_spinner=False)
def load_all_data():
    agg_df = pipeline.load_compliance_agg(PM_AGG_PATH)
    records_df = pipeline.load_records_clean(PM_RECORDS_PATH) if PM_RECORDS_PATH.exists() else None
    pm_date_range = pipeline.get_pm_date_bounds(records_df)
    failure_df = None
    if FAILURE_LOG_PATH.exists() and ERROR_LOOKUP_PATH.exists():
        failure_df = pipeline.load_failure_events(
            FAILURE_LOG_PATH,
            ERROR_LOOKUP_PATH,
            pm_date_range=pm_date_range,
        )
    return records_df, agg_df, failure_df, pm_date_range


st.set_page_config(
    page_title="DMRC PM and Failure Intelligence Dashboard",
    page_icon="🚇",
    layout="wide",
)

st.markdown(
    """
    <div style='background-color:#0A3A60; padding:20px; border-radius:10px; margin-bottom:25px; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);'>
        <h1 style='color:white; margin:0; font-family:sans-serif;'>Delhi Metro Rail Corporation</h1>
        <h3 style='color:#A6D1FF; margin:5px 0 0 0; font-family:sans-serif; font-weight:normal;'>Employee Effectiveness System — PM Compliance and Failure Intelligence</h3>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    records_df, agg_df, failure_df, pm_date_range = load_all_data()
except Exception as exc:
    st.error(f"Error loading dashboard data: {exc}")
    st.stop()

if records_df is None:
    st.warning(
        "Record-level PM file `pm_records_clean.csv` is missing. Overview and failure analytics are available, "
        "but date-level PM drill-down and exact PM-to-failure linking will stay limited until that file is added."
    )

if failure_df is None:
    st.info(
        "Failure files were not found locally. Add `css.csv` and `errors.csv` beside the app to unlock fault analysis."
    )

MONTH_NAMES = ["All", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

with st.sidebar:
    st.markdown("## Ask Assistant")
    st.caption("Ask about failures, PM counts, compliance, stations, systems, or equipment.")

    if "ops_chat_history" not in st.session_state:
        st.session_state.ops_chat_history = []

    for turn in st.session_state.ops_chat_history[-6:]:
        speaker = "You" if turn["role"] == "user" else "Assistant"
        st.markdown(f"**{speaker}:** {turn['content']}")

    sidebar_prompt = st.text_input(
        "Ask a question",
        placeholder="How many failures were there at RJBH?",
        key="sidebar_prompt",
    )
    if st.button("Send", key="sidebar_send") and sidebar_prompt.strip():
        st.session_state.ops_chat_history.append({"role": "user", "content": sidebar_prompt})
        sidebar_answer = pipeline.answer_operations_question(sidebar_prompt, records_df, failure_df)
        st.session_state.ops_chat_history.append({"role": "assistant", "content": sidebar_answer})
        st.rerun()

tab1, tab2 = st.tabs(["📊 Overview", "🧠 Detailed Intelligence"])


with tab1:
    st.subheader("Network-wide PM Snapshot")
    st.info(generate_pm_insight_sentence(agg_df))

    network_kpis = (
        pipeline.compute_compliance_summary(records_df)
        if records_df is not None
        else pipeline.compute_compliance_summary_from_agg(agg_df)
    )
    comp_color = get_compliance_color(network_kpis["compliance_pct"])

    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
    with kpi_col1:
        st.metric("Total PM Actions", f"{network_kpis['total_pm']:,}")
    with kpi_col2:
        st.metric("Compliance Rate", f"{network_kpis['compliance_pct']:.1f}%")
    with kpi_col3:
        st.metric("Average Delay", format_avg_delay(network_kpis["avg_days_late"]))
    with kpi_col4:
        st.metric("Late PM Count", f"{network_kpis['late']:,}")

    st.write("")
    st.subheader("Compliance Performance Rankings")
    groupby_option = st.radio("Group Rankings By:", ["Subsystem", "Station"], horizontal=True, key="rank_groupby")

    group_cols = ["subsystem"] if groupby_option == "Subsystem" else ["station"]
    label_name = "Sub-System" if groupby_option == "Subsystem" else "Station Code"

    ranked_df = (
        agg_df.groupby(group_cols, observed=True)
        .agg(total_pm=("total_pm", "sum"), on_time=("on_time", "sum"))
        .reset_index()
    )
    ranked_df = ranked_df[ranked_df["total_pm"] >= 20]

    if ranked_df.empty:
        st.info("No records meet the minimum threshold of 20 total PMs to display.")
    else:
        ranked_df["compliance_pct"] = (ranked_df["on_time"] / ranked_df["total_pm"] * 100).round(1)
        ranked_df = ranked_df.sort_values("compliance_pct", ascending=True).head(15)
        ranked_df["Performance"] = ranked_df["compliance_pct"].apply(get_compliance_tier)

        fig_bar = px.bar(
            ranked_df,
            x="compliance_pct",
            y=group_cols[0],
            color="Performance",
            color_discrete_map={
                "Critical (<60%)": COLOR_RED,
                "Needs Attention (60-85%)": COLOR_AMBER,
                "On Target (>85%)": COLOR_GREEN,
            },
            orientation="h",
            labels={"compliance_pct": "Compliance Rate (%)", group_cols[0]: label_name},
            text="compliance_pct",
        )
        fig_bar.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig_bar.update_xaxes(range=[0, 110])
        fig_bar.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=450)
        st.plotly_chart(fig_bar, use_container_width=True)


with tab2:
    st.subheader("Detailed Intelligence")

    if records_df is None or failure_df is None:
        st.info("Detailed intelligence needs both record-level PM data and failure data.")
    else:
        if pm_date_range[0] is not None and pm_date_range[1] is not None:
            st.info(
                f"This combined view is aligned to the shared PM window: "
                f"{pm_date_range[0].date()} to {pm_date_range[1].date()}."
            )

        st.caption("Compliance means: out of all scheduled PM tasks, how many were completed on time.")

        f1, f2, f3, f4, f5 = st.columns(5)
        with f1:
            station_val = st.selectbox("Station", ["All"] + sorted(records_df["station"].dropna().unique()), key="d_station")
        with f2:
            system_val = st.selectbox("System", ["All"] + sorted(records_df["system"].dropna().unique()), key="d_system")
        with f3:
            equipment_options = pipeline.get_common_equipment_options(
                records_df,
                failure_df,
                station=station_val,
                system=system_val,
            )
            equipment_val = st.selectbox("Equipment ID", ["All"] + equipment_options, key="d_equipment")
        with f4:
            years = ["All"] + sorted(records_df["done_date"].dt.year.dropna().astype(int).astype(str).unique())
            year_val = st.selectbox("Year", years, key="d_year")
        with f5:
            month_val = st.selectbox("Month", MONTH_NAMES, key="d_month")

        filtered_pm = pipeline.filter_records(
            records_df,
            station=station_val,
            system=system_val,
            year=year_val,
            month=month_val,
        )
        filtered_failure = pipeline.filter_failure_events(
            failure_df,
            station=station_val,
            system=system_val,
            year=year_val,
            month=month_val,
        )

        if equipment_val != "All":
            eqkey = equipment_val.upper().replace("-", "").replace(" ", "").replace("/", "").replace("_", "")
            filtered_pm = filtered_pm[filtered_pm["eqkey"] == eqkey]
            filtered_failure = filtered_failure[filtered_failure["eqkey"] == eqkey]

        pm_kpis = pipeline.compute_compliance_summary(filtered_pm)
        failure_kpis = pipeline.compute_failure_summary(filtered_failure)

        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.metric("Trackable PM", f"{pm_kpis['total_pm']:,}")
        with k2:
            st.metric("PM Compliance", f"{pm_kpis['compliance_pct']:.1f}%")
        with k3:
            st.metric("Failures", f"{failure_kpis['total_failures']:,}")
        with k4:
            st.metric("Avg Resolution", f"{failure_kpis['avg_resolution_hours']:.1f} hrs")

        relation_df = pipeline.build_pm_failure_monthly(
            records_df,
            failure_df,
            station=station_val,
            system=system_val,
        )
        if equipment_val != "All":
            relation_df = pd.DataFrame()
        if not relation_df.empty:
            relation_df["month_dt"] = pd.to_datetime(relation_df["month"])
            if year_val != "All":
                relation_df = relation_df[relation_df["month_dt"].dt.year == int(year_val)]
            if month_val != "All":
                month_idx = MONTH_NAMES.index(month_val)
                relation_df = relation_df[relation_df["month_dt"].dt.month == month_idx]

        linked_df = pipeline.build_equipment_pm_failure_links(
            records_df,
            failure_df,
            station=station_val,
            system=system_val,
            limit=200,
        )
        if equipment_val != "All":
            linked_df = linked_df[linked_df["EqpID"] == equipment_val]

        if equipment_val != "All":
            equipment_history = pipeline.build_equipment_history(records_df, failure_df, equipment_val, limit=200)
            if year_val != "All":
                equipment_history = equipment_history[equipment_history["event_at"].dt.year == int(year_val)]
            if month_val != "All":
                equipment_history = equipment_history[equipment_history["event_at"].dt.month == MONTH_NAMES.index(month_val)]
            if equipment_history.empty:
                st.info("No combined PM and failure history was found for this equipment in the selected date window.")
            else:
                latest_pm = equipment_history[equipment_history["event_type"] == "PM"].head(1)
                latest_failure = equipment_history[equipment_history["event_type"] == "FAILURE"].head(1)
                pm_text = "No recent PM record"
                if not latest_pm.empty:
                    pm_row = latest_pm.iloc[0]
                    pm_text = f"Latest PM was on {pm_row['event_at'].date()} under {pm_row['detail']}."
                failure_text = "No recent failure record"
                if not latest_failure.empty:
                    fail_row = latest_failure.iloc[0]
                    failure_text = f"Latest failure was on {fail_row['event_at'].date()} with mode '{fail_row['detail']}'."
                st.info(f"{pm_text} {failure_text}")

                st.markdown("**Equipment Journey**")
                timeline_display = equipment_history.rename(
                    columns={
                        "event_at": "Event Time",
                        "event_type": "Event",
                        "station": "Station",
                        "section": "Section",
                        "system": "System",
                        "subsystem": "Sub-System",
                        "equipment_id": "Equipment",
                        "detail": "Detail",
                        "status": "Status",
                        "days_late": "PM Days Late",
                        "resolution_hours": "Resolution Hours",
                    }
                )
                timeline_display = timeline_display.drop(columns=["owner", "secondary_owner"], errors="ignore")
                st.dataframe(timeline_display, use_container_width=True, hide_index=True)

        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            if relation_df.empty:
                st.info("Monthly PM-vs-failure relation is not available for this slice.")
            else:
                fig_relation = px.scatter(
                    relation_df,
                    x="compliance_pct",
                    y="failure_count",
                    size="total_pm",
                    hover_name="month",
                    color="failure_count",
                    color_continuous_scale="Turbo",
                    title="Does Lower PM Compliance Come With More Failures?",
                    labels={"compliance_pct": "PM Compliance %", "failure_count": "Failure Count"},
                )
                fig_relation.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=380)
                st.plotly_chart(fig_relation, use_container_width=True)

        with chart_col2:
            if linked_df.empty:
                st.info("No PM-to-next-failure links were found for this slice.")
            else:
                fig_link = px.histogram(
                    linked_df.head(200),
                    x="days_to_next_failure",
                    nbins=25,
                    y="days_to_next_failure",
                    histfunc="count",
                    title="How Soon Failure Comes After PM",
                    labels={"days_to_next_failure": "Days from PM to Next Failure", "count": "Number of Cases"},
                )
                fig_link.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=380)
                st.plotly_chart(fig_link, use_container_width=True)

        chart_col3, chart_col4 = st.columns(2)
        with chart_col3:
            top_failures = filtered_failure["error_description"].fillna("UNKNOWN").value_counts().head(10).reset_index()
            top_failures.columns = ["error_description", "count"]
            if top_failures.empty:
                st.info("No repeated failure modes found in this slice.")
            else:
                fig_failures = px.bar(
                    top_failures.sort_values("count", ascending=True),
                    x="count",
                    y="error_description",
                    orientation="h",
                    color="count",
                    color_continuous_scale="Blues",
                    title="Top Failure Modes in This Slice",
                )
                fig_failures.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=380)
                st.plotly_chart(fig_failures, use_container_width=True)

        with chart_col4:
            if relation_df.empty:
                st.info("No month-wise relation view is available for this slice.")
            else:
                melted = relation_df[["month", "compliance_pct", "failure_count"]].melt(
                    id_vars="month",
                    value_vars=["compliance_pct", "failure_count"],
                    var_name="metric",
                    value_name="value",
                )
                fig_month = px.line(
                    melted,
                    x="month",
                    y="value",
                    color="metric",
                    markers=True,
                    title="Month-by-Month PM vs Failure Trend",
                    color_discrete_map={"compliance_pct": "#0A3A60", "failure_count": "#8B1E3F"},
                )
                fig_month.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=380, hovermode="x unified")
                st.plotly_chart(fig_month, use_container_width=True)

        st.markdown("---")
        insight_parts = []
        if not linked_df.empty:
            fastest = linked_df.iloc[0]
            insight_parts.append(
                f"The quickest PM-to-failure recurrence in this slice is {fastest['EqpID']} with the next failure after {fastest['days_to_next_failure']:.1f} days."
            )
        if not filtered_failure.empty:
            insight_parts.append(generate_failure_insight_sentence(filtered_failure))
        if not relation_df.empty:
            insight_parts.append(generate_relation_insight_sentence(relation_df))
        if insight_parts:
            st.info(" ".join(insight_parts))

        st.markdown("**Failure With Previous PM Context**")
        aligned_df = pipeline.build_failure_pm_alignment(
            records_df,
            filtered_failure,
            station=station_val,
            system=system_val,
            limit=200,
        )
        if equipment_val != "All":
            aligned_df = aligned_df[aligned_df["EqpID"] == equipment_val]

        if aligned_df.empty:
            st.info("No failure-to-PM alignment rows available.")
        else:
            aligned_display = aligned_df.rename(
                columns={
                    "failure_date": "Failure Date",
                    "station": "Station",
                    "system": "System",
                    "subsystem": "Sub-System",
                    "equipment_no": "Failure Equipment ID",
                    "error_description": "Failure Mode",
                    "done_date": "Last PM Date",
                    "schedule_name": "PM Schedule",
                    "EqpID": "PM Equipment ID",
                    "compliance_status": "PM Status",
                }
            )
            st.dataframe(aligned_display, use_container_width=True, hide_index=True)
>>>>>>> origin/main
