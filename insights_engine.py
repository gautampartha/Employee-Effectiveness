import pandas as pd
import numpy as np

def generate_insights(pm_agg_df, failure_summary_df):
    """
    Generate actionable insights from PM and failure data.

    Args:
        pm_agg_df: DataFrame from pm_compliance_agg.csv with columns:
            - subsystem, total_pm, on_time, etc.
        failure_summary_df: DataFrame from failure_pipeline.get_failure_summary() with columns:
            - Station, SubSystem, total_failures, maintenance_gap_count,
              equipment_failure_count, avg_resolution_hours, etc.

    Returns:
        List of insight dicts with keys: priority, category, title, detail, action
    """
    insights = []

    # Handle empty dataframes
    if pm_agg_df is None or pm_agg_df.empty:
        return insights
    if failure_summary_df is None or failure_summary_df.empty:
        failure_summary_df = pd.DataFrame()

    # 1. CRITICAL if any subsystem compliance < 50%
    if not pm_agg_df.empty and 'total_pm' in pm_agg_df.columns and 'on_time' in pm_agg_df.columns:
        # Filter subsystems with at least 20 total_pm to avoid noise
        pm_agg_df_valid = pm_agg_df[pm_agg_df['total_pm'] >= 20].copy()
        if not pm_agg_df_valid.empty:
            pm_agg_df_valid['compliance_pct'] = (
                pm_agg_df_valid['on_time'] / pm_agg_df_valid['total_pm'] * 100
            ).round(1)
            min_compliance = pm_agg_df_valid['compliance_pct'].min()
            if min_compliance < 50:
                worst_row = pm_agg_df_valid.loc[pm_agg_df_valid['compliance_pct'].idxmin()]
                subsystem = worst_row['subsystem']
                compliance = worst_row['compliance_pct']
                total_pm = int(worst_row['total_pm'])
                insights.append({
                    "priority": "critical",
                    "category": "Maintenance",
                    "title": f"{subsystem} maintenance critically behind schedule",
                    "detail": f"Only {compliance}% of {subsystem} maintenance tasks completed on time across {total_pm:,} trackable records network-wide.",
                    "action": f"Increase maintenance frequency or reassign teams to {subsystem}."
                })

    # 2. WARNING if overall compliance < 70%
    if not pm_agg_df.empty and 'total_pm' in pm_agg_df.columns and 'on_time' in pm_agg_df.columns:
        total_pm = pm_agg_df['total_pm'].sum()
        on_time = pm_agg_df['on_time'].sum()
        if total_pm > 0:
            overall_compliance = round(on_time / total_pm * 100, 1)
            if overall_compliance < 70:
                late_pm = total_pm - on_time
                insights.append({
                    "priority": "warning",
                    "category": "Maintenance",
                    "title": "Network-wide PM compliance below target",
                    "detail": f"Overall compliance is {overall_compliance}% — {int(late_pm):,} of {total_pm:,} PM tasks were late.",
                    "action": "Review scheduling across all lines — prioritize overdue equipment."
                })

    # 3. CRITICAL if maintenance_gap_pct > 40%
    if not failure_summary_df.empty and 'total_failures' in failure_summary_df.columns and 'maintenance_gap_count' in failure_summary_df.columns:
        total_failures = failure_summary_df['total_failures'].sum()
        maintenance_gap_count = failure_summary_df['maintenance_gap_count'].sum()
        if total_failures > 0:
            maintenance_gap_pct = round(maintenance_gap_count / total_failures * 100, 1)
            if maintenance_gap_pct > 40:
                insights.append({
                    "priority": "critical",
                    "category": "Failures",
                    "title": "Majority of failures linked to missed maintenance",
                    "detail": f"{maintenance_gap_pct}% of all recorded failures occurred on equipment with overdue PM — {int(maintenance_gap_count):,} total maintenance-gap failures.",
                    "action": "Improving PM compliance could prevent over {maintenance_gap_pct}% of current failures."
                })

    # 4. WARNING for top failure station
    if not failure_summary_df.empty and 'Station' in failure_summary_df.columns and 'total_failures' in failure_summary_df.columns:
        station_totals = failure_summary_df.groupby('Station')['total_failures'].sum().reset_index()
        if not station_totals.empty:
            top_station_row = station_totals.loc[station_totals['total_failures'].idxmax()]
            station = top_station_row['Station']
            total_failures_at_station = int(top_station_row['total_failures'])
            network_avg = failure_summary_df['total_failures'].mean()
            if network_avg > 0:
                pct_above_avg = round((total_failures_at_station - network_avg) / network_avg * 100, 1)
                insights.append({
                    "priority": "warning",
                    "category": "Failures",
                    "title": f"{station} has highest failure rate in network",
                    "detail": f"{station} recorded {total_failures_at_station:,} failures — {pct_above_avg}% above network average.",
                    "action": f"Conduct urgent maintenance audit at {station}."
                })

    # 5. WARNING if any subsystem avg_resolution_hours > 4
    if not failure_summary_df.empty and 'SubSystem' in failure_summary_df.columns and 'avg_resolution_hours' in failure_summary_df.columns:
        # Filter out NaN or infinite values
        valid_hours = failure_summary_df[failure_summary_df['avg_resolution_hours'].notna() & (failure_summary_df['avg_resolution_hours'] != np.inf)]
        if not valid_hours.empty:
            max_row = valid_hours.loc[valid_hours['avg_resolution_hours'].idxmax()]
            subsystem = max_row['SubSystem']
            avg_hours = round(max_row['avg_resolution_hours'], 1)
            if avg_hours > 4:
                insights.append({
                    "priority": "warning",
                    "category": "Equipment",
                    "title": f"{subsystem} failures taking too long to resolve",
                    "detail": f"Average resolution time for {subsystem} is {avg_hours} hours — above the 4-hour target.",
                    "action": f"Review technician assignment process for {subsystem} failures."
                })

    # 6. CRITICAL for worst compliance station (min 50 total_pm)
    # Note: This requires station-level PM data, which we don't have in pm_agg_df (it's aggregated by subsystem)
    # We'll skip this insight for now as the required data isn't available in the current dataframes.
    # The user's description mentions "station" but pm_agg_df is by subsystem.
    # We'll leave a placeholder or skip.
    pass

    # 7. POSITIVE if any subsystem compliance > 85%
    if not pm_agg_df.empty and 'total_pm' in pm_agg_df.columns and 'on_time' in pm_agg_df.columns:
        pm_agg_df_valid = pm_agg_df[pm_agg_df['total_pm'] >= 20].copy()
        if not pm_agg_df_valid.empty:
            pm_agg_df_valid['compliance_pct'] = (
                pm_agg_df_valid['on_time'] / pm_agg_df_valid['total_pm'] * 100
            ).round(1)
            max_compliance = pm_agg_df_valid['compliance_pct'].max()
            if max_compliance > 85:
                best_row = pm_agg_df_valid.loc[pm_agg_df_valid['compliance_pct'].idxmax()]
                subsystem = best_row['subsystem']
                compliance = best_row['compliance_pct']
                total_pm = int(best_row['total_pm'])
                insights.append({
                    "priority": "positive",
                    "category": "Maintenance",
                    "title": f"{subsystem} maintaining excellent compliance",
                    "detail": f"{subsystem} achieved {compliance}% on-time completion — best in network.",
                    "action": f"Use {subsystem} team's scheduling practices as a model for others."
                })

    # 8. WARNING if equipment_failure_pct > 30%
    if not failure_summary_df.empty and 'total_failures' in failure_summary_df.columns and 'equipment_failure_count' in failure_summary_df.columns:
        total_failures = failure_summary_df['total_failures'].sum()
        equipment_failure_count = failure_summary_df['equipment_failure_count'].sum()
        if total_failures > 0:
            equipment_failure_pct = round(equipment_failure_count / total_failures * 100, 1)
            if equipment_failure_pct > 30:
                insights.append({
                    "priority": "warning",
                    "category": "Equipment",
                    "title": "High rate of equipment-side failures detected",
                    "detail": f"{equipment_failure_pct}% of classified failures occurred despite timely maintenance — {int(equipment_failure_count):,} equipment-side failures, suggesting hardware/vendor issues.",
                    "action": "Flag recurring equipment-failure subsystems for vendor review."
                })

    # Sort insights by priority: critical > warning > positive
    priority_order = {"critical": 0, "warning": 1, "positive": 2}
    insights.sort(key=lambda x: priority_order[x["priority"]])

    return insights