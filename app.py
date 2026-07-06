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
