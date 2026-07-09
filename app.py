from pathlib import Path

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

import failure_pipeline
import insights_engine
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


def get_compliance_tier(pct):
    if pct < COMPLIANCE_RED_THRESHOLD:
        return "Critical (<60%)"
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


def build_data_context(pm_agg_df, failure_summary_df):
    if pm_agg_df is None or pm_agg_df.empty:
        return "No PM data available."

    total_pm = int(pm_agg_df["total_pm"].sum())
    overall_compliance = 0.0
    if total_pm > 0:
        overall_compliance = round(pm_agg_df["on_time"].sum() / total_pm * 100, 1)

    pm_agg_df_valid = pm_agg_df[pm_agg_df["total_pm"] >= 20].copy()
    worst_subsystem = "N/A"
    worst_subsystem_pct = 0.0
    if not pm_agg_df_valid.empty:
        pm_agg_df_valid["compliance_pct"] = (
            pm_agg_df_valid["on_time"] / pm_agg_df_valid["total_pm"] * 100
        ).round(1)
        worst_row = pm_agg_df_valid.loc[pm_agg_df_valid["compliance_pct"].idxmin()]
        worst_subsystem = worst_row["subsystem"]
        worst_subsystem_pct = worst_row["compliance_pct"]

    total_failures = 0
    maintenance_gap_pct = 0.0
    top5_failure_stations = {}
    top5_worst_compliance = {}

    if failure_summary_df is not None and not failure_summary_df.empty:
        total_failures = int(failure_summary_df["total_failures"].sum())
        if total_failures > 0:
            maintenance_gap_count = failure_summary_df["maintenance_gap_count"].sum()
            maintenance_gap_pct = round(maintenance_gap_count / total_failures * 100, 1)

            if "Station" in failure_summary_df.columns:
                station_totals = failure_summary_df.groupby("Station")["total_failures"].sum()
                top5_failure_stations = station_totals.nlargest(5).to_dict()

            if not pm_agg_df_valid.empty:
                worst_compliance = pm_agg_df_valid.nsmallest(5, "compliance_pct")
                top5_worst_compliance = dict(
                    zip(worst_compliance["subsystem"], worst_compliance["compliance_pct"])
                )

    return f"""
You are an AI assistant for Delhi Metro Rail Corporation (DMRC) maintenance operations.
You help managers and engineers understand maintenance performance data.
Answer questions concisely and practically. If you don't know something from
the data provided, say so and do not invent numbers.

CURRENT DATA SUMMARY:
- Total PM records: {total_pm:,}
- Overall PM compliance rate: {overall_compliance}%
- Worst performing subsystem: {worst_subsystem} at {worst_subsystem_pct}% compliance
- Total failures recorded: {total_failures:,}
- Failures caused by maintenance gaps: {maintenance_gap_pct}%
- Top 5 stations by failure count: {top5_failure_stations}
- Top 5 worst compliance subsystems: {top5_worst_compliance}
"""


def ask_ollama(question, context):
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.2:1b",
                "prompt": f"{context}\n\nQuestion: {question}\n\nAnswer:",
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 300},
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["response"].strip()
    except requests.exceptions.ConnectionError:
        return "Ollama is not running. Start it with `ollama serve` to use the local assistant."
    except requests.exceptions.Timeout:
        return "The local model timed out. Try a shorter question or retry once Ollama is responsive."
    except Exception as exc:
        return f"Error while querying Ollama: {exc}"


@st.cache_data(show_spinner=False)
def load_core_data():
    agg_df = pipeline.load_compliance_agg(PM_AGG_PATH)
    records_df = pipeline.load_records_clean(PM_RECORDS_PATH) if PM_RECORDS_PATH.exists() else None
    pm_date_range = pipeline.get_pm_date_bounds(records_df)
    return records_df, agg_df, pm_date_range


@st.cache_data(show_spinner=False)
def load_failure_data(pm_date_range):
    if not FAILURE_LOG_PATH.exists() or not ERROR_LOOKUP_PATH.exists():
        return None
    return pipeline.load_failure_events(
        FAILURE_LOG_PATH,
        ERROR_LOOKUP_PATH,
        pm_date_range=pm_date_range,
    )


@st.cache_data(show_spinner=False)
def load_failure_analysis_data():
    failures_raw = failure_pipeline.load_failures()
    pm_raw = failure_pipeline.load_pm_records()
    classified_df = failure_pipeline.classify_failures(failures_raw, pm_raw)
    summary_df = failure_pipeline.get_failure_summary(classified_df)
    return classified_df, summary_df


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
    records_df, agg_df, pm_date_range = load_core_data()
except Exception as exc:
    st.error(f"Error loading dashboard data: {exc}")
    st.stop()

if records_df is None:
    st.warning(
        "Record-level PM file `pm_records_clean.csv` is missing. Overview and failure analytics are available, "
        "but date-level PM drill-down and exact PM-to-failure linking will stay limited until that file is added."
    )

failure_files_available = FAILURE_LOG_PATH.exists() and ERROR_LOOKUP_PATH.exists()
classified_failure_df = None
failure_summary_df = pd.DataFrame()

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
        failure_df = load_failure_data(pm_date_range) if failure_files_available else None
        st.session_state.ops_chat_history.append({"role": "user", "content": sidebar_prompt})
        sidebar_answer = pipeline.answer_operations_question(sidebar_prompt, records_df, failure_df)
        st.session_state.ops_chat_history.append({"role": "assistant", "content": sidebar_answer})
        st.rerun()

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📊 Overview", "🧠 Detailed Intelligence", "🚨 Failure Analysis", "🤖 Ask Assistant", "💡 Insights"]
)


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

    if records_df is None or not failure_files_available:
        st.info("Detailed intelligence needs both record-level PM data and failure data.")
    else:
        if pm_date_range[0] is not None and pm_date_range[1] is not None:
            st.info(
                f"This combined view is aligned to the shared PM window: "
                f"{pm_date_range[0].date()} to {pm_date_range[1].date()}."
            )

        st.caption("Pick a slice and click Generate. Heavy PM-failure analysis is loaded only on demand to keep startup fast.")

        with st.form("detailed_intelligence_form"):
            f1, f2, f3, f4, f5 = st.columns(5)
            with f1:
                station_val = st.selectbox("Station", ["All"] + sorted(records_df["station"].dropna().unique()), key="d_station")
            with f2:
                system_val = st.selectbox("System", ["All"] + sorted(records_df["system"].dropna().unique()), key="d_system")
            with f3:
                equipment_val = st.text_input("Equipment ID (optional)", key="d_equipment_text", placeholder="Paste exact equipment ID")
            with f4:
                years = ["All"] + sorted(records_df["done_date"].dt.year.dropna().astype(int).astype(str).unique())
                year_val = st.selectbox("Year", years, key="d_year")
            with f5:
                month_val = st.selectbox("Month", MONTH_NAMES, key="d_month")
            run_detailed = st.form_submit_button("Generate Detailed Intelligence", use_container_width=True)

        if not run_detailed:
            st.info("Choose filters and click `Generate Detailed Intelligence` to run the heavy PM-failure analysis for that slice.")
        else:
            with st.spinner("Loading failure data and computing detailed intelligence..."):
                failure_df = load_failure_data(pm_date_range)

            if failure_df is None:
                st.info("Failure files were not found locally. Add `css.csv` and `errors.csv` beside the app to unlock fault analysis.")
                st.stop()

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

            equipment_val = equipment_val.strip()
            if equipment_val:
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
            if equipment_val:
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
            if equipment_val:
                linked_df = linked_df[linked_df["EqpID"] == equipment_val]

            if equipment_val:
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
            if equipment_val:
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


with tab3:
    st.subheader("Failure Analysis Dashboard")
    st.caption("This section classifies the full failure log against PM history, so it is loaded only when requested.")

    load_failure_analysis = st.button("Load Failure Analysis", key="load_failure_analysis")
    if not load_failure_analysis:
        st.info("Click `Load Failure Analysis` to run the expensive failure classification flow.")
    else:
        try:
            with st.spinner("Loading and classifying failure records..."):
                classified_failure_df, failure_summary_df = load_failure_analysis_data()
        except Exception as exc:
            st.warning(f"Advanced failure tabs could not be prepared: {exc}")
            classified_failure_df = None

    if classified_failure_df is not None and not classified_failure_df.empty:
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            failure_system = st.selectbox(
                "System",
                ["All"] + sorted(classified_failure_df["System"].dropna().unique()),
                key="fa_system",
            )
        filtered_classified = classified_failure_df
        if failure_system != "All":
            filtered_classified = filtered_classified[filtered_classified["System"] == failure_system]

        with f2:
            failure_subsystem = st.selectbox(
                "Sub-System",
                ["All"] + sorted(filtered_classified["SubSystem"].dropna().unique()),
                key="fa_subsystem",
            )
        if failure_subsystem != "All":
            filtered_classified = filtered_classified[filtered_classified["SubSystem"] == failure_subsystem]

        with f3:
            failure_station = st.selectbox(
                "Station",
                ["All"] + sorted(filtered_classified["Station"].dropna().unique()),
                key="fa_station",
            )
        if failure_station != "All":
            filtered_classified = filtered_classified[filtered_classified["Station"] == failure_station]

        with f4:
            date_min = filtered_classified["Date"].dropna().min()
            date_max = filtered_classified["Date"].dropna().max()
            if pd.notna(date_min) and pd.notna(date_max):
                failure_dates = st.date_input(
                    "Date Range",
                    value=(date_min.date(), date_max.date()),
                    min_value=date_min.date(),
                    max_value=date_max.date(),
                    key="fa_dates",
                )
                if len(failure_dates) == 2:
                    start_date, end_date = failure_dates
                    filtered_classified = filtered_classified[
                        (filtered_classified["Date"].dt.date >= start_date)
                        & (filtered_classified["Date"].dt.date <= end_date)
                    ]

        if filtered_classified.empty:
            st.warning("No failure records match the selected filters.")
        else:
            total_failures = len(filtered_classified)
            mg_count = int((filtered_classified["failure_label"] == "Maintenance Gap Failure").sum())
            eq_count = int((filtered_classified["failure_label"] == "Equipment Failure").sum())
            npm_count = int((filtered_classified["failure_label"] == "No PM Record").sum())
            valid_duration = filtered_classified[filtered_classified["Duration"] <= 9999]["Duration"]
            avg_hrs = float(valid_duration.mean() / 60) if not valid_duration.empty else 0.0

            k1, k2, k3, k4 = st.columns(4)
            with k1:
                st.metric("Total Failures", f"{total_failures:,}")
            with k2:
                st.metric("Maintenance Gap", f"{mg_count:,} ({(mg_count / total_failures * 100):.1f}%)")
            with k3:
                st.metric("Equipment Failure", f"{eq_count:,} ({(eq_count / total_failures * 100):.1f}%)")
            with k4:
                st.metric("Avg Resolution", f"{avg_hrs:.1f} hrs")

            c1, c2 = st.columns(2)
            with c1:
                fig_pie = px.pie(
                    filtered_classified,
                    names="failure_label",
                    hole=0.4,
                    color="failure_label",
                    color_discrete_map={
                        "Maintenance Gap Failure": COLOR_RED,
                        "Equipment Failure": COLOR_AMBER,
                        "No PM Record": "#6c757d",
                    },
                    title="Failure Classification Breakdown",
                )
                st.plotly_chart(fig_pie, use_container_width=True)

            with c2:
                station_stats = (
                    filtered_classified.groupby("Station")
                    .agg(total_failures=("failure_label", "size"))
                    .reset_index()
                    .sort_values("total_failures", ascending=False)
                    .head(10)
                )
                fig_station = px.bar(
                    station_stats.sort_values("total_failures", ascending=True),
                    x="total_failures",
                    y="Station",
                    orientation="h",
                    text="total_failures",
                    title="Top 10 Stations by Failure Count",
                    color="total_failures",
                    color_continuous_scale="OrRd",
                )
                fig_station.update_traces(textposition="outside")
                st.plotly_chart(fig_station, use_container_width=True)

            subsystem_stats = (
                filtered_classified.groupby("SubSystem")
                .agg(
                    total_failures=("failure_label", "size"),
                    mg_count=("failure_label", lambda x: (x == "Maintenance Gap Failure").sum()),
                    eq_count=("failure_label", lambda x: (x == "Equipment Failure").sum()),
                    npm_count=("failure_label", lambda x: (x == "No PM Record").sum()),
                )
                .reset_index()
                .sort_values("total_failures", ascending=False)
            )
            subsystem_stats["mg_pct"] = (subsystem_stats["mg_count"] / subsystem_stats["total_failures"] * 100).round(1)
            subsystem_stats["eq_pct"] = (subsystem_stats["eq_count"] / subsystem_stats["total_failures"] * 100).round(1)
            subsystem_stats["npm_pct"] = (subsystem_stats["npm_count"] / subsystem_stats["total_failures"] * 100).round(1)

            st.markdown("**Subsystem Failure Frequency**")
            st.dataframe(
                subsystem_stats[
                    ["SubSystem", "total_failures", "mg_pct", "eq_pct", "npm_pct"]
                ],
                use_container_width=True,
                hide_index=True,
            )

            trend_df = filtered_classified.copy()
            trend_df["Month"] = trend_df["Date"].dt.to_period("M").astype(str)
            trend_monthly = trend_df.groupby(["Month", "failure_label"]).size().reset_index(name="count")
            fig_trend = px.bar(
                trend_monthly,
                x="Month",
                y="count",
                color="failure_label",
                barmode="stack",
                color_discrete_map={
                    "Maintenance Gap Failure": COLOR_RED,
                    "Equipment Failure": COLOR_AMBER,
                    "No PM Record": "#6c757d",
                },
                title="Monthly Failure Trend",
            )
            st.plotly_chart(fig_trend, use_container_width=True)


with tab4:
    st.subheader("Ask Assistant")
    st.caption("Powered by a local Ollama model when available.")

    if "assistant_chat_history" not in st.session_state:
        st.session_state.assistant_chat_history = []

    for chat in st.session_state.assistant_chat_history:
        speaker = "You" if chat["role"] == "user" else "Assistant"
        st.markdown(f"**{speaker}:** {chat['content']}")

    q1, q2 = st.columns([4, 1])
    with q1:
        user_question = st.text_input(
            "Ask a question about maintenance performance",
            placeholder="Which stations need urgent attention?",
            key="assistant_input",
        )
    with q2:
        ask_button = st.button("Ask", type="primary", use_container_width=True)

    st.caption("Example prompts")
    e1, e2, e3 = st.columns(3)
    if e1.button("Which stations need urgent attention?", key="assistant_ex1"):
        user_question = "Which stations need urgent attention?"
        ask_button = True
    if e2.button("What percentage of failures are maintenance gaps?", key="assistant_ex2"):
        user_question = "What percentage of failures are maintenance gaps?"
        ask_button = True
    if e3.button("Which subsystem has the worst PM compliance?", key="assistant_ex3"):
        user_question = "Which subsystem has the worst PM compliance?"
        ask_button = True

    if ask_button and user_question.strip():
        st.session_state.assistant_chat_history.append({"role": "user", "content": user_question})
        with st.spinner("Thinking..."):
            context = build_data_context(agg_df, failure_summary_df)
            response = ask_ollama(user_question, context)
        st.session_state.assistant_chat_history.append({"role": "assistant", "content": response})
        st.rerun()

    if st.button("Clear Conversation", key="assistant_clear"):
        st.session_state.assistant_chat_history = []
        st.rerun()


with tab5:
    st.subheader("AI and Rule-Based Slice Insights")
    st.caption("Choose any station, system, subsystem, year, or month. The engine will explain that exact slice, not just the network average.")

    insight_station_options = ["All"]
    insight_system_options = ["All"]
    insight_subsystem_options = ["All"]
    insight_year_options = ["All"]

    if records_df is not None and not records_df.empty:
        insight_station_options += sorted(records_df["station"].dropna().unique())
        insight_system_options += sorted(records_df["system"].dropna().unique())
        insight_year_options += sorted(records_df["done_date"].dt.year.dropna().astype(int).astype(str).unique())
        if "i_station" not in st.session_state:
            st.session_state.i_station = "All"
        if "i_system" not in st.session_state:
            st.session_state.i_system = "All"
        if "i_subsystem" not in st.session_state:
            st.session_state.i_subsystem = "All"

        current_station = st.session_state.i_station
        current_system = st.session_state.i_system

        scoped_for_subsystems = records_df
        if current_station != "All":
            scoped_for_subsystems = scoped_for_subsystems[scoped_for_subsystems["station"] == current_station]
        if current_system != "All":
            scoped_for_subsystems = scoped_for_subsystems[scoped_for_subsystems["system"] == current_system]
        insight_subsystem_options += sorted(scoped_for_subsystems["subsystem"].dropna().unique())

    with st.form("insights_slice_form"):
        fi1, fi2, fi3, fi4, fi5 = st.columns(5)
        with fi1:
            insight_station = st.selectbox("Station", insight_station_options, key="i_station")
        with fi2:
            insight_system = st.selectbox("System", insight_system_options, key="i_system")
        with fi3:
            insight_subsystem = st.selectbox("Sub-System", insight_subsystem_options, key="i_subsystem")
        with fi4:
            insight_year = st.selectbox("Year", insight_year_options, key="i_year")
        with fi5:
            insight_month = st.selectbox("Month", MONTH_NAMES, key="i_month")
        generate_slice_insights = st.form_submit_button("Generate Slice Insights", use_container_width=True)

    if not generate_slice_insights:
        st.info("Choose filters and click `Generate Slice Insights` to run the insight engine for that slice.")
    else:
        with st.spinner("Loading slice data and preparing insights..."):
            failure_df = load_failure_data(pm_date_range) if failure_files_available else None
            classified_failure_df = None
            if failure_files_available:
                try:
                    classified_failure_df, failure_summary_df = load_failure_analysis_data()
                except Exception:
                    classified_failure_df = None

            slice_summary = insights_engine.build_filtered_scope_summary(
                records_df,
                agg_df,
                failure_df,
                classified_failure_df=classified_failure_df,
                station=insight_station,
                system=insight_system,
                subsystem=insight_subsystem,
                year=insight_year,
                month=insight_month,
            )
            insights = insights_engine.generate_scope_insights(slice_summary)

        st.info(f"Current insight scope: {slice_summary['scope']['label']}")

        pm_kpis = slice_summary["slice_pm"]
        failure_kpis = slice_summary["slice_fail"]
        k1, k2, k3, k4, k5 = st.columns(5)
        with k1:
            st.metric("Trackable PM", f"{pm_kpis['total_pm']:,}")
        with k2:
            st.metric("PM Compliance", f"{pm_kpis['compliance_pct']:.1f}%")
        with k3:
            st.metric("Late PM", f"{pm_kpis['late']:,}")
        with k4:
            st.metric("Failures", f"{failure_kpis['total_failures']:,}")
        with k5:
            st.metric("Maintenance-Gap Share", f"{slice_summary['maintenance_gap_pct']:.1f}%")

        ai_prompt = (
            "Give me the executive summary, the top three priority observations, and the top three recommended actions "
            "for this selected maintenance slice."
        )
        ai_col1, ai_col2 = st.columns([1, 3])
        with ai_col1:
            generate_ai_brief = st.button("Generate AI Brief", key="insight_ai_brief")
        with ai_col2:
            st.caption("This uses the selected filters and the computed subsystem ranking, not the raw CSV directly.")

        if generate_ai_brief:
            with st.spinner("Preparing AI brief..."):
                ai_context = insights_engine.build_scope_ai_context(slice_summary, insights)
                ai_response = ask_ollama(ai_prompt, ai_context)
            st.markdown("**AI Brief**")
            st.write(ai_response)

        subsystem_health = slice_summary["subsystem_health"]
        if subsystem_health is not None and not subsystem_health.empty:
            st.markdown("**Subsystem Risk Ranking For The Selected Slice**")
            ranking_display = subsystem_health.head(12).rename(
                columns={
                    "subsystem": "Sub-System",
                    "risk_score": "Risk Score",
                    "compliance_pct": "Compliance %",
                    "late_pm": "Late PM",
                    "total_failures": "Failures",
                    "maintenance_gap_pct": "Maintenance Gap %",
                    "equipment_failure_pct": "Equipment Failure %",
                    "avg_resolution_hours": "Avg Resolution Hours",
                    "top_failure_mode": "Top Failure Mode",
                }
            )
            st.dataframe(
                ranking_display[
                    [
                        "Sub-System",
                        "Risk Score",
                        "Compliance %",
                        "Late PM",
                        "Failures",
                        "Maintenance Gap %",
                        "Equipment Failure %",
                        "Avg Resolution Hours",
                        "Top Failure Mode",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

        if not insights:
            st.info("No insights were triggered for this slice. Try widening the scope or selecting a busier station/system.")
        else:
            critical_count = sum(1 for insight in insights if insight["priority"] == "critical")
            if critical_count > 0:
                st.error(f"{critical_count} critical issue(s) require immediate attention in this selected slice")
            else:
                st.success("No critical issues detected in this selected slice")

            for insight in insights:
                if insight["priority"] == "critical":
                    border_color = COLOR_RED
                    bg_color = "#FFF0F0"
                elif insight["priority"] == "warning":
                    border_color = COLOR_AMBER
                    bg_color = "#FFF9F0"
                else:
                    border_color = COLOR_GREEN
                    bg_color = "#F0FFF0"

                st.markdown(
                    f"""
                    <div style="
                        border-left: 4px solid {border_color};
                        background-color: {bg_color};
                        padding: 16px;
                        margin: 12px 0;
                        border-radius: 0 8px 8px 0;
                    ">
                        <strong>{insight['title']}</strong><br/>
                        <span style="font-size: 0.9em; color: #555;">{insight['category']} | {insight['priority'].upper()}</span>
                        <p style="margin: 8px 0 6px 0; color: #333;">{insight['detail']}</p>
                        <p style="margin: 0; color: #555;"><em>{insight['action']}</em></p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
