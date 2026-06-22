import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import pipeline

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

def get_compliance_tier(pct):
    if pct < COMPLIANCE_RED_THRESHOLD:
        return "Critical (<60%)"
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

# --- Page Config and Styling ---
st.set_page_config(
    page_title="DMRC PM Compliance Dashboard",
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
    records_df = pipeline.load_records_clean("pm_records_clean.csv")
    agg_df = pipeline.load_compliance_agg("pm_compliance_agg.csv")
    return records_df, agg_df

try:
    records_df, agg_df = load_all_data()
except Exception as e:
    st.error(f"Error loading data: {e}")
    st.info("Make sure 'pm_records_clean.csv' and 'pm_compliance_agg.csv' are in the dashboard directory.")
    st.stop()

# --- Create Navigation Tabs ---
tab1, tab2 = st.tabs(["📊 Overview", "🕵️ Detailed Explorer"])

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
        st.markdown(f"""
            <div style="background-color: #F4F6F9; border-left: 5px solid #0A3A60; padding: 15px; border-radius: 8px; box-shadow: 1px 1px 3px rgba(0,0,0,0.05); min-height: 120px;">
                <p style="margin: 0; font-size: 13px; color: #6c757d; font-weight: bold; text-transform: uppercase;">Total PM Actions</p>
                <p style="margin: 5px 0 0 0; font-size: 26px; color: #0A3A60; font-weight: bold;">{network_kpis['total_pm']:,}</p>
                <p style="margin: 5px 0 0 0; font-size: 11px; color: #6c757d; line-height: 1.2;">Total completed maintenance events (excluding baseline records).</p>
            </div>
        """, unsafe_allow_html=True)
        
    with kpi_col2:
        st.markdown(f"""
            <div style="background-color: #F4F6F9; border-left: 5px solid {comp_color}; padding: 15px; border-radius: 8px; box-shadow: 1px 1px 3px rgba(0,0,0,0.05); min-height: 120px;">
                <p style="margin: 0; font-size: 13px; color: #6c757d; font-weight: bold; text-transform: uppercase;">Compliance Rate</p>
                <p style="margin: 5px 0 0 0; font-size: 26px; color: {comp_color}; font-weight: bold;">{network_comp_pct:.1f}%</p>
                <p style="margin: 5px 0 0 0; font-size: 11px; color: #6c757d; line-height: 1.2;">% of maintenance completed on-time (within the 3-day grace period).</p>
            </div>
        """, unsafe_allow_html=True)
        
    with kpi_col3:
        avg_late = network_kpis['avg_days_late']
        avg_late_str = f"{abs(avg_late):.1f} days early" if avg_late < 0 else f"{avg_late:.1f} days late"
        st.markdown(f"""
            <div style="background-color: #F4F6F9; border-left: 5px solid #0A3A60; padding: 15px; border-radius: 8px; box-shadow: 1px 1px 3px rgba(0,0,0,0.05); min-height: 120px;">
                <p style="margin: 0; font-size: 13px; color: #6c757d; font-weight: bold; text-transform: uppercase;">Average Delay</p>
                <p style="margin: 5px 0 0 0; font-size: 26px; color: #0A3A60; font-weight: bold;">{avg_late_str}</p>
                <p style="margin: 5px 0 0 0; font-size: 11px; color: #6c757d; line-height: 1.2;">Average delay relative to expected due date (negative is early).</p>
            </div>
        """, unsafe_allow_html=True)
        
    with kpi_col4:
        st.markdown(f"""
            <div style="background-color: #F4F6F9; border-left: 5px solid #d9534f; padding: 15px; border-radius: 8px; box-shadow: 1px 1px 3px rgba(0,0,0,0.05); min-height: 120px;">
                <p style="margin: 0; font-size: 13px; color: #6c757d; font-weight: bold; text-transform: uppercase;">Late PM Count</p>
                <p style="margin: 5px 0 0 0; font-size: 26px; color: #d9534f; font-weight: bold;">{network_kpis['late']:,}</p>
                <p style="margin: 5px 0 0 0; font-size: 11px; color: #6c757d; line-height: 1.2;">Total number of maintenance actions that missed the on-time window.</p>
            </div>
        """, unsafe_allow_html=True)

    st.write("")
    st.write("")
    
    # 3. Ranked Horizontal Bar Chart
    st.subheader("🚨 Compliance Performance Rankings (Bottom 15)")
    st.markdown("Group data network-wide and identify components lagging behind compliance targets (minimum threshold: 20 records).")
    
    # Toggle to switch groupings
    groupby_option = st.radio("Group Rankings By:", ["Subsystem", "Station"], horizontal=True, key="rank_groupby")
    
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
        st.plotly_chart(fig_bar, use_container_width=True)


# ==============================================================================
# TAB 2: DETAILED EXPLORER (Engineer/Analyst view)
# ==============================================================================
with tab2:
    st.subheader("🕵️ Detailed Data Explorer")
    st.markdown("Use the control dropdowns below to filter the record dataset and generate localized heatmap, trend, and overdue reports.")
    
    # Dynamic controls row
    f_c1, f_c2, f_c3, f_c4, f_c5, f_c6 = st.columns(6)
    
    with f_c1:
        # Station Filter
        stations = ["All"] + sorted(list(records_df['station'].unique().dropna()))
        station_val = st.selectbox("Station Code", stations, index=0, key="exp_station")
    with f_c2:
        # System Filter
        systems = ["All"] + sorted(list(records_df['system'].unique().dropna()))
        system_val = st.selectbox("System", systems, index=0, key="exp_system")
    with f_c3:
        # Cascading Sub-System Filter
        if system_val != "All":
            available_subsystems = sorted(list(records_df[records_df['system'] == system_val]['subsystem'].unique().dropna()))
        else:
            available_subsystems = sorted(list(records_df['subsystem'].unique().dropna()))
        subsystem_val = st.selectbox("Sub-System", ["All"] + available_subsystems, index=0, key="exp_subsystem")
    with f_c4:
        # Schedule Filter (Frequency)
        schedules = ["All"] + sorted(list(records_df['schedule_name'].unique().dropna()))
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
        st.markdown("Displays weighted average compliance. Limit stations using the slider below to prevent clutter.")
        
        # Heatmap controls
        h_c1, h_c2 = st.columns(2)
        with h_c1:
            heatmap_system = st.selectbox(
                "Heatmap System Filter",
                options=["All"] + sorted(list(agg_df['system'].unique().dropna())),
                index=0 if system_val == "All" else sorted(list(agg_df['system'].unique().dropna())).index(system_val) + 1,
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
                agg_heatmap = trackable_records.groupby(['station', 'subsystem'], as_index=False, observed=True).agg(
                    total_pm=('compliance_status', 'count'),
                    on_time=('compliance_status', lambda x: (x == 'on_time').sum())
                )
                agg_heatmap = agg_heatmap[agg_heatmap['total_pm'] > 0]
                agg_heatmap['compliance_pct'] = (agg_heatmap['on_time'] / agg_heatmap['total_pm'] * 100).round(1)
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
                agg_heatmap = h_df.groupby(['station', 'subsystem'], as_index=False, observed=True).agg(
                    total_pm=('total_pm', 'sum'),
                    on_time=('on_time', 'sum')
                )
                agg_heatmap = agg_heatmap[agg_heatmap['total_pm'] > 0]
                agg_heatmap['compliance_pct'] = (agg_heatmap['on_time'] / agg_heatmap['total_pm'] * 100).round(1)
                
        if len(agg_heatmap) == 0:
            st.info("No active records found matching selections to display in heatmap.")
        else:
            # Filter to top N busiest stations
            station_totals = agg_heatmap.groupby('station', observed=True)['total_pm'].sum().reset_index()
            top_stations = station_totals.sort_values(by='total_pm', ascending=False).head(top_n)['station']
            agg_heatmap = agg_heatmap[agg_heatmap['station'].isin(top_stations)]
            
            if len(agg_heatmap) == 0:
                st.info("No active records to display in heatmap.")
            else:
                pivot_df = agg_heatmap.pivot(index='station', columns='subsystem', values='compliance_pct')
                pivot_df = pivot_df.sort_index(ascending=True) # Sort alphabetically
                
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
                st.plotly_chart(fig_heatmap, use_container_width=True)
                
    with vis_col2:
        st.subheader("📈 Monthly Compliance Trend")
        st.markdown("Chronological progression of the compliance rate over time (grouped by month).")
        
        # Compute trendline
        trend_df = filtered_df[filtered_df['compliance_status'] != 'baseline'].copy()
        
        if len(trend_df) == 0:
            st.info("No compliance events recorded inside this timeframe/filter selection.")
        else:
            trend_df['month'] = trend_df['done_date'].dt.to_period('M').astype(str)
            monthly_agg = trend_df.groupby('month', observed=True).agg(
                total_pm=('compliance_status', 'count'),
                on_time=('compliance_status', lambda x: (x == 'on_time').sum())
            ).reset_index()
            monthly_agg['compliance_pct'] = (monthly_agg['on_time'] / monthly_agg['total_pm'] * 100).round(1)
            
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
            st.plotly_chart(fig_trend, use_container_width=True)
            
    st.markdown("---")
    
    # Overdue Table
    st.subheader("⚠️ Late / Overdue Records Details")
    st.markdown("List of individual maintenance events completed late. Sort, search, or download the filtered list as a CSV.")
    
    late_df = filtered_df[filtered_df['compliance_status'] == 'late']
    
    if len(late_df) == 0:
        st.success("🎉 Excellent! All PM tasks in this selection were completed on time!")
    else:
        display_cols = [
            'EqpID', 'Eqp_Name', 'station', 'subsystem', 
            'schedule_name', 'done_date', 'expected_due_date', 'days_late'
        ]
        late_table = late_df[display_cols].sort_values(by='days_late', ascending=False)
        
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
            use_container_width=True,
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
