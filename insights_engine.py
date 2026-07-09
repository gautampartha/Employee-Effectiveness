import numpy as np
import pandas as pd

import pipeline
from app_config import MONTH_NAMES


def _safe_pct(numerator, denominator):
    if denominator in (0, None) or pd.isna(denominator):
        return 0.0
    return round(float(numerator) / float(denominator) * 100, 1)


def _safe_mean(series):
    if series is None or len(series) == 0:
        return 0.0
    value = series.dropna().mean()
    return 0.0 if pd.isna(value) else round(float(value), 1)


def _month_index(month_name):
    if not month_name or month_name == "All":
        return None
    return MONTH_NAMES.index(month_name)


def _scope_label(station="All", system="All", subsystem="All", year="All", month="All"):
    parts = []
    if station and station != "All":
        parts.append(f"station {station}")
    if system and system != "All":
        parts.append(f"system {system}")
    if subsystem and subsystem != "All":
        parts.append(f"subsystem {subsystem}")
    if year and year != "All":
        parts.append(f"year {year}")
    if month and month != "All":
        parts.append(f"month {month}")
    return "entire network" if not parts else ", ".join(parts)


def _filter_agg_df(df, station="All", system="All", subsystem="All", schedule_name="All"):
    filtered_df = df
    if station and station != "All" and "station" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["station"] == station]
    if system and system != "All" and "system" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["system"] == system]
    if subsystem and subsystem != "All" and "subsystem" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["subsystem"] == subsystem]
    if schedule_name and schedule_name != "All" and "schedule_name" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["schedule_name"] == schedule_name]
    return filtered_df


def _filter_classified_failures(df, station="All", system="All", subsystem="All", year="All", month="All"):
    if df is None or df.empty:
        return pd.DataFrame()

    filtered_df = df
    if station and station != "All" and "Station" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Station"] == station]
    if system and system != "All" and "System" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["System"] == system]
    if subsystem and subsystem != "All" and "SubSystem" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["SubSystem"] == subsystem]
    if year and year != "All" and "Date" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Date"].dt.year == int(year)]
    month_idx = _month_index(month)
    if month_idx and "Date" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Date"].dt.month == month_idx]
    return filtered_df


def _pm_summary_from_agg(agg_df):
    if agg_df is None or agg_df.empty:
        return {
            "total_pm": 0,
            "on_time": 0,
            "late": 0,
            "compliance_pct": 0.0,
            "avg_days_late": 0.0,
        }

    total_pm = int(agg_df["total_pm"].sum())
    on_time = int(agg_df["on_time"].sum())
    late = int(agg_df["late"].sum()) if "late" in agg_df.columns else max(total_pm - on_time, 0)
    if total_pm > 0:
        compliance_pct = _safe_pct(on_time, total_pm)
        if "avg_days_late" in agg_df.columns:
            avg_days_late = np.average(
                agg_df["avg_days_late"].fillna(0.0),
                weights=agg_df["total_pm"].clip(lower=0),
            )
            avg_days_late = round(float(avg_days_late), 1)
        else:
            avg_days_late = 0.0
    else:
        compliance_pct = 0.0
        avg_days_late = 0.0
    return {
        "total_pm": total_pm,
        "on_time": on_time,
        "late": late,
        "compliance_pct": compliance_pct,
        "avg_days_late": avg_days_late,
    }


def _build_subsystem_health(pm_records, agg_slice, failure_slice, classified_slice):
    if pm_records is not None and not pm_records.empty:
        trackable_pm = pm_records[pm_records["compliance_status"] != "BASELINE"].copy()
        pm_health = (
            trackable_pm.groupby("subsystem", observed=True)
            .agg(
                total_pm=("compliance_status", "count"),
                on_time=("compliance_status", lambda x: (x == "ON_TIME").sum()),
                late_pm=("compliance_status", lambda x: (x == "LATE").sum()),
                avg_days_late=("days_late", "mean"),
            )
            .reset_index()
        )
    else:
        pm_health = (
            agg_slice.groupby("subsystem", observed=True)
            .agg(
                total_pm=("total_pm", "sum"),
                on_time=("on_time", "sum"),
                late_pm=("late", "sum"),
                avg_days_late=("avg_days_late", "mean"),
            )
            .reset_index()
            if agg_slice is not None and not agg_slice.empty
            else pd.DataFrame(columns=["subsystem", "total_pm", "on_time", "late_pm", "avg_days_late"])
        )

    if not pm_health.empty:
        pm_health["compliance_pct"] = (
            (pm_health["on_time"] / pm_health["total_pm"].replace(0, np.nan)) * 100
        ).round(1).fillna(0.0)

    if failure_slice is not None and not failure_slice.empty:
        failure_modes = (
            failure_slice.groupby("subsystem", observed=True)["error_description"]
            .agg(lambda x: x.fillna("UNKNOWN").value_counts().index[0] if not x.empty else "UNKNOWN")
            .reset_index(name="top_failure_mode")
        )
        failure_health = (
            failure_slice.groupby("subsystem", observed=True)
            .agg(
                total_failures=("failure_code", "size"),
                avg_resolution_hours=("resolution_hours", "mean"),
                unique_assets=("equipment_no", "nunique"),
            )
            .reset_index()
            .merge(failure_modes, on="subsystem", how="left")
        )
    else:
        failure_health = pd.DataFrame(
            columns=["subsystem", "total_failures", "avg_resolution_hours", "unique_assets", "top_failure_mode"]
        )

    if classified_slice is not None and not classified_slice.empty:
        classified_health = (
            classified_slice.groupby("SubSystem", observed=True)
            .agg(
                maintenance_gap_count=("failure_label", lambda x: (x == "Maintenance Gap Failure").sum()),
                equipment_failure_count=("failure_label", lambda x: (x == "Equipment Failure").sum()),
                no_pm_count=("failure_label", lambda x: (x == "No PM Record").sum()),
            )
            .reset_index()
            .rename(columns={"SubSystem": "subsystem"})
        )
    else:
        classified_health = pd.DataFrame(
            columns=["subsystem", "maintenance_gap_count", "equipment_failure_count", "no_pm_count"]
        )

    subsystem_health = pm_health.merge(failure_health, on="subsystem", how="outer")
    subsystem_health = subsystem_health.merge(classified_health, on="subsystem", how="left")
    if subsystem_health.empty:
        return subsystem_health

    numeric_fill_zero = [
        "total_pm",
        "on_time",
        "late_pm",
        "avg_days_late",
        "compliance_pct",
        "total_failures",
        "avg_resolution_hours",
        "unique_assets",
        "maintenance_gap_count",
        "equipment_failure_count",
        "no_pm_count",
    ]
    for col in numeric_fill_zero:
        if col in subsystem_health.columns:
            subsystem_health[col] = subsystem_health[col].fillna(0)

    if "top_failure_mode" in subsystem_health.columns:
        subsystem_health["top_failure_mode"] = subsystem_health["top_failure_mode"].fillna("UNKNOWN")

    subsystem_health["maintenance_gap_pct"] = subsystem_health.apply(
        lambda row: _safe_pct(row.get("maintenance_gap_count", 0), row.get("total_failures", 0)),
        axis=1,
    )
    subsystem_health["equipment_failure_pct"] = subsystem_health.apply(
        lambda row: _safe_pct(row.get("equipment_failure_count", 0), row.get("total_failures", 0)),
        axis=1,
    )
    subsystem_health["failure_density"] = subsystem_health.apply(
        lambda row: round(row["total_failures"] / row["total_pm"], 2) if row["total_pm"] else 0.0,
        axis=1,
    )

    max_failures = max(float(subsystem_health["total_failures"].max()), 1.0)
    max_resolution = max(float(subsystem_health["avg_resolution_hours"].max()), 1.0)
    subsystem_health["risk_score"] = (
        ((100 - subsystem_health["compliance_pct"].clip(upper=100)) * 0.45)
        + ((subsystem_health["total_failures"] / max_failures) * 25)
        + ((subsystem_health["maintenance_gap_pct"] / 100) * 20)
        + ((subsystem_health["avg_resolution_hours"] / max_resolution) * 10)
    ).round(1)

    return subsystem_health.sort_values(["risk_score", "total_failures"], ascending=[False, False]).reset_index(drop=True)


def build_filtered_scope_summary(
    records_df,
    agg_df,
    failure_df,
    classified_failure_df=None,
    station="All",
    system="All",
    subsystem="All",
    year="All",
    month="All",
):
    scope = {
        "station": station,
        "system": system,
        "subsystem": subsystem,
        "year": year,
        "month": month,
        "label": _scope_label(station=station, system=system, subsystem=subsystem, year=year, month=month),
    }

    pm_slice = (
        pipeline.filter_records(records_df, station=station, system=system, subsystem=subsystem, year=year, month=month)
        if records_df is not None
        else pd.DataFrame()
    )
    agg_slice = _filter_agg_df(agg_df, station=station, system=system, subsystem=subsystem)
    failure_slice = (
        pipeline.filter_failure_events(failure_df, station=station, system=system, subsystem=subsystem, year=year, month=month)
        if failure_df is not None
        else pd.DataFrame()
    )
    classified_slice = _filter_classified_failures(
        classified_failure_df,
        station=station,
        system=system,
        subsystem=subsystem,
        year=year,
        month=month,
    )

    network_pm = (
        pipeline.compute_compliance_summary(records_df)
        if records_df is not None and not records_df.empty
        else _pm_summary_from_agg(agg_df)
    )
    slice_pm = (
        pipeline.compute_compliance_summary(pm_slice)
        if pm_slice is not None and not pm_slice.empty
        else _pm_summary_from_agg(agg_slice)
    )
    network_fail = (
        pipeline.compute_failure_summary(failure_df)
        if failure_df is not None and not failure_df.empty
        else {"total_failures": 0, "resolved": 0, "unresolved": 0, "unique_assets": 0, "avg_resolution_hours": 0.0}
    )
    slice_fail = (
        pipeline.compute_failure_summary(failure_slice)
        if failure_slice is not None and not failure_slice.empty
        else {"total_failures": 0, "resolved": 0, "unresolved": 0, "unique_assets": 0, "avg_resolution_hours": 0.0}
    )

    maintenance_gap_count = 0
    equipment_failure_count = 0
    no_pm_count = 0
    if not classified_slice.empty:
        maintenance_gap_count = int((classified_slice["failure_label"] == "Maintenance Gap Failure").sum())
        equipment_failure_count = int((classified_slice["failure_label"] == "Equipment Failure").sum())
        no_pm_count = int((classified_slice["failure_label"] == "No PM Record").sum())

    top_failure_modes = pd.DataFrame(columns=["error_description", "count", "share_pct"])
    if failure_slice is not None and not failure_slice.empty:
        top_failure_modes = (
            failure_slice["error_description"]
            .fillna("UNKNOWN")
            .value_counts()
            .head(5)
            .reset_index()
        )
        top_failure_modes.columns = ["error_description", "count"]
        top_failure_modes["share_pct"] = top_failure_modes["count"].apply(
            lambda x: _safe_pct(x, slice_fail["total_failures"])
        )

    relation_df = pipeline.build_pm_failure_monthly(
        records_df,
        failure_df,
        station=station,
        system=system,
        subsystem=subsystem,
    )
    if not relation_df.empty:
        if year and year != "All":
            relation_df = relation_df[pd.to_datetime(relation_df["month"]).dt.year == int(year)]
        month_idx = _month_index(month)
        if month_idx:
            relation_df = relation_df[pd.to_datetime(relation_df["month"]).dt.month == month_idx]

    subsystem_health = _build_subsystem_health(pm_slice, agg_slice, failure_slice, classified_slice)

    summary = {
        "scope": scope,
        "pm_slice": pm_slice,
        "agg_slice": agg_slice,
        "failure_slice": failure_slice,
        "classified_slice": classified_slice,
        "network_pm": network_pm,
        "slice_pm": slice_pm,
        "network_fail": network_fail,
        "slice_fail": slice_fail,
        "maintenance_gap_count": maintenance_gap_count,
        "equipment_failure_count": equipment_failure_count,
        "no_pm_count": no_pm_count,
        "maintenance_gap_pct": _safe_pct(maintenance_gap_count, slice_fail["total_failures"]),
        "equipment_failure_pct": _safe_pct(equipment_failure_count, slice_fail["total_failures"]),
        "no_pm_pct": _safe_pct(no_pm_count, slice_fail["total_failures"]),
        "top_failure_modes": top_failure_modes,
        "relation_df": relation_df,
        "subsystem_health": subsystem_health,
    }
    return summary


def generate_scope_insights(summary):
    insights = []
    scope_label = summary["scope"]["label"]
    slice_pm = summary["slice_pm"]
    network_pm = summary["network_pm"]
    slice_fail = summary["slice_fail"]
    subsystem_health = summary["subsystem_health"]
    top_failure_modes = summary["top_failure_modes"]

    if slice_pm["total_pm"] >= 20:
        compliance_gap = round(slice_pm["compliance_pct"] - network_pm["compliance_pct"], 1)
        if slice_pm["compliance_pct"] < 55:
            insights.append(
                {
                    "priority": "critical",
                    "category": "Maintenance",
                    "title": f"PM compliance is critically weak in {scope_label}",
                    "detail": (
                        f"Compliance in this slice is {slice_pm['compliance_pct']:.1f}% across "
                        f"{slice_pm['total_pm']:,} trackable PM actions, which is {abs(compliance_gap):.1f} points "
                        f"{'below' if compliance_gap < 0 else 'above'} the network baseline of {network_pm['compliance_pct']:.1f}%."
                    ),
                    "action": "Prioritize overdue schedules and review crew allocation for the weakest subsystems first.",
                }
            )
        elif compliance_gap <= -10:
            insights.append(
                {
                    "priority": "warning",
                    "category": "Maintenance",
                    "title": f"PM compliance is trailing the network in {scope_label}",
                    "detail": (
                        f"This slice is running at {slice_pm['compliance_pct']:.1f}% compliance versus "
                        f"{network_pm['compliance_pct']:.1f}% network-wide."
                    ),
                    "action": "Compare schedule completion discipline here against the better-performing stations or systems.",
                }
            )

    if not subsystem_health.empty:
        worst = subsystem_health.iloc[0]
        if worst["total_pm"] >= 10 and worst["compliance_pct"] < 60:
            insights.append(
                {
                    "priority": "critical" if worst["compliance_pct"] < 50 else "warning",
                    "category": "Subsystem",
                    "title": f"{worst['subsystem']} is the weakest subsystem in this slice",
                    "detail": (
                        f"It is running at {worst['compliance_pct']:.1f}% PM compliance with "
                        f"{int(worst['late_pm']):,} late PM actions and {int(worst['total_failures']):,} failures."
                    ),
                    "action": f"Audit {worst['subsystem']} schedules, manpower, and recurring failure modes immediately.",
                }
            )

        heavy_failure = subsystem_health.sort_values(
            ["total_failures", "maintenance_gap_pct"], ascending=[False, False]
        ).iloc[0]
        if heavy_failure["total_failures"] >= 5:
            insights.append(
                {
                    "priority": "warning",
                    "category": "Failures",
                    "title": f"{heavy_failure['subsystem']} is carrying the heaviest failure load",
                    "detail": (
                        f"It contributes {int(heavy_failure['total_failures']):,} failures in this slice, "
                        f"with maintenance-gap share at {heavy_failure['maintenance_gap_pct']:.1f}%."
                    ),
                    "action": f"Start the failure review from {heavy_failure['subsystem']} and validate whether missed PM is driving the volume.",
                }
            )

        equipment_risk = subsystem_health[
            (subsystem_health["equipment_failure_pct"] >= 50)
            & (subsystem_health["compliance_pct"] >= 75)
            & (subsystem_health["total_failures"] >= 3)
        ]
        if not equipment_risk.empty:
            eq_row = equipment_risk.sort_values("total_failures", ascending=False).iloc[0]
            insights.append(
                {
                    "priority": "warning",
                    "category": "Equipment",
                    "title": f"{eq_row['subsystem']} shows hardware-side stress despite decent PM compliance",
                    "detail": (
                        f"{eq_row['equipment_failure_pct']:.1f}% of its classified failures are equipment-side while "
                        f"PM compliance is still {eq_row['compliance_pct']:.1f}%."
                    ),
                    "action": f"Escalate recurring {eq_row['subsystem']} assets for design, vendor, or replacement review.",
                }
            )

        best = subsystem_health.sort_values(["compliance_pct", "total_pm"], ascending=[False, False]).iloc[0]
        if best["total_pm"] >= 20 and best["compliance_pct"] >= 85:
            insights.append(
                {
                    "priority": "positive",
                    "category": "Maintenance",
                    "title": f"{best['subsystem']} is the benchmark subsystem in this slice",
                    "detail": (
                        f"It has {best['compliance_pct']:.1f}% compliance across {int(best['total_pm']):,} PM actions "
                        f"with only {int(best['total_failures']):,} failures logged here."
                    ),
                    "action": f"Reuse {best['subsystem']} scheduling and execution practices in weaker subsystems.",
                }
            )

    if slice_fail["total_failures"] > 0:
        maintenance_gap_pct = summary["maintenance_gap_pct"]
        if maintenance_gap_pct >= 45:
            insights.append(
                {
                    "priority": "critical",
                    "category": "Failures",
                    "title": f"Failures in {scope_label} are strongly linked to missed maintenance",
                    "detail": (
                        f"{maintenance_gap_pct:.1f}% of classified failures are maintenance-gap failures "
                        f"({summary['maintenance_gap_count']:,} out of {slice_fail['total_failures']:,})."
                    ),
                    "action": "Treat PM recovery as the fastest lever to reduce failure pressure in this slice.",
                }
            )

        if slice_fail["avg_resolution_hours"] > 4:
            insights.append(
                {
                    "priority": "warning",
                    "category": "Resolution",
                    "title": f"Failure resolution is taking too long in {scope_label}",
                    "detail": (
                        f"Average failure resolution time is {slice_fail['avg_resolution_hours']:.1f} hours across "
                        f"{slice_fail['resolved']:,} resolved cases."
                    ),
                    "action": "Review technician availability, spare readiness, and escalation timing for this slice.",
                }
            )

    if not top_failure_modes.empty:
        top_mode = top_failure_modes.iloc[0]
        if top_mode["share_pct"] >= 25:
            insights.append(
                {
                    "priority": "warning",
                    "category": "Failure Mode",
                    "title": f"A single failure mode is dominating in {scope_label}",
                    "detail": (
                        f"'{top_mode['error_description']}' appears {int(top_mode['count']):,} times and accounts for "
                        f"{top_mode['share_pct']:.1f}% of all failures in this slice."
                    ),
                    "action": "Investigate this failure mode first because concentrated repetition usually indicates a fixable root cause.",
                }
            )

    relation_df = summary["relation_df"]
    if relation_df is not None and not relation_df.empty and len(relation_df) >= 2:
        worst_month = relation_df.sort_values(["failure_count", "compliance_pct"], ascending=[False, True]).iloc[0]
        if int(worst_month["failure_count"]) > 0:
            insights.append(
                {
                    "priority": "warning",
                    "category": "Trend",
                    "title": "The PM-to-failure pattern shows a visible stress month",
                    "detail": (
                        f"{worst_month['month']} recorded {int(worst_month['failure_count']):,} failures while "
                        f"PM compliance sat at {worst_month['compliance_pct']:.1f}%."
                    ),
                    "action": "Use that month as the first review window for backlog, missed schedules, and repeated breakdowns.",
                }
            )

    priority_order = {"critical": 0, "warning": 1, "positive": 2}
    insights.sort(key=lambda item: priority_order[item["priority"]])
    return insights[:8]


def build_scope_ai_context(summary, insights):
    scope = summary["scope"]["label"]
    slice_pm = summary["slice_pm"]
    network_pm = summary["network_pm"]
    slice_fail = summary["slice_fail"]
    subsystem_health = summary["subsystem_health"].head(8).copy()
    top_failure_modes = summary["top_failure_modes"].copy()

    subsystem_lines = []
    if not subsystem_health.empty:
        for _, row in subsystem_health.iterrows():
            subsystem_lines.append(
                f"- {row['subsystem']}: compliance {row['compliance_pct']:.1f}%, "
                f"late PM {int(row['late_pm']):,}, failures {int(row['total_failures']):,}, "
                f"maintenance-gap {row['maintenance_gap_pct']:.1f}%, top failure mode {row['top_failure_mode']}"
            )

    failure_mode_lines = []
    if not top_failure_modes.empty:
        for _, row in top_failure_modes.iterrows():
            failure_mode_lines.append(
                f"- {row['error_description']}: {int(row['count']):,} failures ({row['share_pct']:.1f}%)"
            )

    rule_lines = []
    for insight in insights[:5]:
        rule_lines.append(f"- [{insight['priority'].upper()}] {insight['title']}: {insight['detail']}")

    return f"""
You are an operations intelligence assistant for Delhi Metro maintenance performance.
Write a sharp, manager-friendly insight brief for the selected slice only.
Stay grounded in the provided numbers. Do not invent metrics.

SELECTED SLICE:
- {scope}

PM SUMMARY:
- Trackable PM actions: {slice_pm['total_pm']:,}
- Slice PM compliance: {slice_pm['compliance_pct']:.1f}%
- Network PM compliance: {network_pm['compliance_pct']:.1f}%
- Late PM count in slice: {slice_pm['late']:,}
- Average PM delay: {slice_pm['avg_days_late']:.1f} days

FAILURE SUMMARY:
- Failures in slice: {slice_fail['total_failures']:,}
- Resolved failures: {slice_fail['resolved']:,}
- Average resolution time: {slice_fail['avg_resolution_hours']:.1f} hours
- Maintenance-gap share: {summary['maintenance_gap_pct']:.1f}%
- Equipment-failure share: {summary['equipment_failure_pct']:.1f}%

SUBSYSTEM HEALTH:
{chr(10).join(subsystem_lines) if subsystem_lines else "- No subsystem-level rows available"}

TOP FAILURE MODES:
{chr(10).join(failure_mode_lines) if failure_mode_lines else "- No failure modes available"}

RULE-BASED SIGNALS:
{chr(10).join(rule_lines) if rule_lines else "- No rule-based insights triggered"}

Please produce:
1. A 3-4 sentence executive summary.
2. Three priority observations.
3. Three recommended actions.
"""


def generate_insights(pm_agg_df, failure_summary_df):
    """
    Backward-compatible network-wide insights for the original overview.
    """
    summary = {
        "scope": {"label": "entire network"},
        "slice_pm": _pm_summary_from_agg(pm_agg_df),
        "network_pm": _pm_summary_from_agg(pm_agg_df),
        "slice_fail": {
            "total_failures": int(failure_summary_df["total_failures"].sum()) if failure_summary_df is not None and not failure_summary_df.empty else 0,
            "resolved": 0,
            "unresolved": 0,
            "unique_assets": 0,
            "avg_resolution_hours": _safe_mean(failure_summary_df["avg_resolution_hours"]) if failure_summary_df is not None and not failure_summary_df.empty and "avg_resolution_hours" in failure_summary_df.columns else 0.0,
        },
        "maintenance_gap_count": int(failure_summary_df["maintenance_gap_count"].sum()) if failure_summary_df is not None and not failure_summary_df.empty and "maintenance_gap_count" in failure_summary_df.columns else 0,
        "equipment_failure_count": int(failure_summary_df["equipment_failure_count"].sum()) if failure_summary_df is not None and not failure_summary_df.empty and "equipment_failure_count" in failure_summary_df.columns else 0,
        "top_failure_modes": pd.DataFrame(),
        "relation_df": pd.DataFrame(),
        "subsystem_health": pd.DataFrame(),
    }
    summary["maintenance_gap_pct"] = _safe_pct(summary["maintenance_gap_count"], summary["slice_fail"]["total_failures"])
    summary["equipment_failure_pct"] = _safe_pct(summary["equipment_failure_count"], summary["slice_fail"]["total_failures"])

    if pm_agg_df is not None and not pm_agg_df.empty:
        subsystem_health = (
            pm_agg_df.groupby("subsystem", observed=True)
            .agg(
                total_pm=("total_pm", "sum"),
                on_time=("on_time", "sum"),
                late_pm=("late", "sum"),
                avg_days_late=("avg_days_late", "mean"),
            )
            .reset_index()
        )
        subsystem_health["compliance_pct"] = (
            subsystem_health["on_time"] / subsystem_health["total_pm"].replace(0, np.nan) * 100
        ).round(1).fillna(0.0)
        if failure_summary_df is not None and not failure_summary_df.empty:
            failure_by_subsystem = (
                failure_summary_df.groupby("SubSystem", observed=True)
                .agg(
                    total_failures=("total_failures", "sum"),
                    maintenance_gap_count=("maintenance_gap_count", "sum"),
                    equipment_failure_count=("equipment_failure_count", "sum"),
                    avg_resolution_hours=("avg_resolution_hours", "mean"),
                )
                .reset_index()
                .rename(columns={"SubSystem": "subsystem"})
            )
            subsystem_health = subsystem_health.merge(failure_by_subsystem, on="subsystem", how="left")
        summary["subsystem_health"] = subsystem_health.fillna(0)

    return generate_scope_insights(summary)
