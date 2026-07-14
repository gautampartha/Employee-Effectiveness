"""Decision-support engine for the DMRC Insights dashboard."""

from __future__ import annotations

from datetime import datetime
import math
from pathlib import Path
import re

import numpy as np
import pandas as pd

import pipeline
from app_config import MONTH_NAMES
from trend_analyzer import build_monthly_trend, compute_rolling_correlation


BASE_RISK_WEIGHTS = {
    "compliance_gap": 0.45,
    "failure_volume": 0.25,
    "maintenance_gap_share": 0.20,
    "resolution_time": 0.10,
}
SECURITY_LOG_PATH = Path(__file__).resolve().parent / "security_log.txt"
_SCOPE_WHITELISTS = {"station": set(), "system": set(), "subsystem": set()}


def _safe_pct(numerator, denominator):
    if denominator in (0, None) or pd.isna(denominator):
        return 0.0
    return round(float(numerator) / float(denominator) * 100, 1)


def _safe_mean(series):
    if series is None or len(series) == 0:
        return 0.0
    value = pd.to_numeric(series, errors="coerce").dropna().mean()
    return 0.0 if pd.isna(value) else round(float(value), 1)


def _month_index(month_value):
    if month_value in (None, "", "All"):
        return None
    if isinstance(month_value, (int, np.integer)) or str(month_value).isdigit():
        value = int(month_value)
        return value if 1 <= value <= 12 else None
    value = str(month_value).strip().title()
    return MONTH_NAMES.index(value) if value in MONTH_NAMES[1:] else None


def _scope_label(station="All", system="All", subsystem="All", year="All", month="All"):
    parts = []
    for label, value in [
        ("station", station),
        ("system", system),
        ("subsystem", subsystem),
        ("year", year),
        ("month", month),
    ]:
        if value not in (None, "", "All"):
            parts.append(f"{label} {value}")
    return "entire network" if not parts else ", ".join(parts)


def _sanitize_text(value) -> str:
    return re.sub(r"[^A-Za-z0-9 ]+", "", str(value)).strip()


def _log_security_warning(original: dict, sanitized: dict, reason: str) -> None:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    changed = {
        key: {"original": str(original.get(key)), "sanitized": str(sanitized.get(key))}
        for key in ["station", "system", "subsystem", "year", "month"]
        if original.get(key) != sanitized.get(key)
    }
    with SECURITY_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(f"{timestamp} scope_input_sanitized changed={changed} reason={reason}\n")


def _refresh_scope_whitelists(*dataframes) -> None:
    refreshed = {"station": set(), "system": set(), "subsystem": set()}
    candidates = {
        "station": ["station", "Station"],
        "system": ["system", "System"],
        "subsystem": ["subsystem", "SubSystem"],
    }
    for df in dataframes:
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            continue
        for key, column_names in candidates.items():
            column = next((name for name in column_names if name in df.columns), None)
            if column:
                refreshed[key].update(
                    _sanitize_text(value) for value in df[column].dropna().astype(str) if _sanitize_text(value)
                )
    for key, values in refreshed.items():
        if values:
            _SCOPE_WHITELISTS[key] = values


def sanitize_scope_input(scope: dict) -> tuple[bool, dict, str]:
    """Validate filter values before they are used to filter a DataFrame."""
    original = dict(scope or {})
    sanitized = {}
    changes = []

    for key in ["station", "system", "subsystem"]:
        value = original.get(key, "All")
        if value in (None, "", "All"):
            sanitized[key] = "All"
            continue
        cleaned = _sanitize_text(value)
        if cleaned != str(value).strip():
            changes.append(f"{key} contained non-alphanumeric characters")
        allowed = _SCOPE_WHITELISTS.get(key, set())
        if not cleaned or cleaned not in allowed:
            sanitized[key] = None
            changes.append(f"{key} was not in the loaded-data whitelist")
        else:
            sanitized[key] = cleaned

    year = original.get("year", "All")
    if year in (None, "", "All"):
        sanitized["year"] = "All"
    else:
        try:
            year_number = int(year)
        except (TypeError, ValueError):
            year_number = 0
        if not 2018 <= year_number <= 2030:
            sanitized["year"] = year_number
            message = "Year must be between 2018 and 2030."
            _log_security_warning(original, sanitized, message)
            return False, sanitized, message
        sanitized["year"] = str(year_number)

    month = original.get("month", "All")
    if month in (None, "", "All"):
        sanitized["month"] = "All"
    else:
        month_number = _month_index(month)
        if month_number is None:
            sanitized["month"] = month
            message = "Month must be between 1 and 12 or a valid month name."
            _log_security_warning(original, sanitized, message)
            return False, sanitized, message
        sanitized["month"] = MONTH_NAMES[month_number]

    if any(original.get(key, "All") != sanitized.get(key) for key in sanitized) or changes:
        _log_security_warning(original, sanitized, "; ".join(changes) or "scope values normalized")
    return True, sanitized, ""


def _safe_series_match(series: pd.Series, value) -> pd.Series:
    safe_value = _sanitize_text(value)
    return series.astype("string").fillna("").map(_sanitize_text) == safe_value


def _secure_filter(
    df,
    *,
    station="All",
    system="All",
    subsystem="All",
    year="All",
    month="All",
    is_failure=False,
):
    if df is None or df.empty:
        return pd.DataFrame()
    filtered = df
    candidates = {
        "station": ["station", "Station"],
        "system": ["system", "System"],
        "subsystem": ["subsystem", "SubSystem"],
    }
    for key, value in [("station", station), ("system", system), ("subsystem", subsystem)]:
        column = next((name for name in candidates[key] if name in filtered.columns), None)
        if value not in (None, "", "All") and column:
            filtered = filtered[_safe_series_match(filtered[column], value)]

    date_candidates = ["failure_date", "Date", "failure_event_at"] if is_failure else ["done_date", "Date"]
    date_column = next((name for name in date_candidates if name in filtered.columns), None)
    if date_column and year not in (None, "", "All"):
        dates = pd.to_datetime(filtered[date_column], errors="coerce")
        filtered = filtered[dates.dt.year == int(year)]
    month_number = _month_index(month)
    if date_column and month_number:
        dates = pd.to_datetime(filtered[date_column], errors="coerce")
        filtered = filtered[dates.dt.month == month_number]
    return filtered.copy()


def _filter_agg_df(df, station="All", system="All", subsystem="All"):
    return _secure_filter(df, station=station, system=system, subsystem=subsystem)


def _filter_classified_failures(df, station="All", system="All", subsystem="All", year="All", month="All"):
    return _secure_filter(
        df,
        station=station,
        system=system,
        subsystem=subsystem,
        year=year,
        month=month,
        is_failure=True,
    )


def _pm_summary_from_agg(agg_df):
    if agg_df is None or agg_df.empty:
        return {"total_pm": 0, "on_time": 0, "late": 0, "compliance_pct": 0.0, "avg_days_late": 0.0}
    total_pm = int(agg_df["total_pm"].sum())
    on_time = int(agg_df["on_time"].sum())
    late = int(agg_df["late"].sum()) if "late" in agg_df.columns else max(total_pm - on_time, 0)
    avg_days_late = 0.0
    if total_pm and "avg_days_late" in agg_df.columns:
        weights = pd.to_numeric(agg_df["total_pm"], errors="coerce").fillna(0).clip(lower=0)
        if weights.sum() > 0:
            avg_days_late = round(float(np.average(agg_df["avg_days_late"].fillna(0.0), weights=weights)), 1)
    return {
        "total_pm": total_pm,
        "on_time": on_time,
        "late": late,
        "compliance_pct": _safe_pct(on_time, total_pm),
        "avg_days_late": avg_days_late,
    }


def _empty_health_frame():
    return pd.DataFrame(
        columns=[
            "subsystem",
            "total_pm",
            "on_time",
            "late_pm",
            "avg_days_late",
            "compliance_pct",
            "total_failures",
            "avg_resolution_hours",
            "unique_assets",
            "top_failure_mode",
            "maintenance_gap_count",
            "equipment_failure_count",
            "no_pm_count",
        ]
    )


def _aggregate_subsystem_health(pm_records, agg_slice, failure_slice, classified_slice, *, use_agg_fallback):
    if pm_records is not None and not pm_records.empty and "subsystem" in pm_records.columns:
        trackable = pm_records
        if "compliance_status" in trackable.columns:
            trackable = trackable[trackable["compliance_status"] != "BASELINE"]
        pm_health = (
            trackable.groupby("subsystem", observed=True)
            .agg(
                total_pm=("subsystem", "size"),
                on_time=("compliance_status", lambda values: (values == "ON_TIME").sum()),
                late_pm=("compliance_status", lambda values: (values == "LATE").sum()),
                avg_days_late=("days_late", "mean"),
            )
            .reset_index()
        )
    elif use_agg_fallback and agg_slice is not None and not agg_slice.empty:
        pm_health = (
            agg_slice.groupby("subsystem", observed=True)
            .agg(
                total_pm=("total_pm", "sum"),
                on_time=("on_time", "sum"),
                late_pm=("late", "sum"),
                avg_days_late=("avg_days_late", "mean"),
            )
            .reset_index()
        )
    else:
        pm_health = _empty_health_frame().iloc[0:0][
            ["subsystem", "total_pm", "on_time", "late_pm", "avg_days_late"]
        ]
    if not pm_health.empty:
        pm_health["compliance_pct"] = (
            pm_health["on_time"] / pm_health["total_pm"].replace(0, np.nan) * 100
        ).round(1).fillna(0.0)

    if failure_slice is not None and not failure_slice.empty and "subsystem" in failure_slice.columns:
        mode_column = "error_description" if "error_description" in failure_slice.columns else None
        asset_column = next((name for name in ["eqkey", "equipment_no"] if name in failure_slice.columns), None)
        failure_rows = []
        for subsystem_name, group in failure_slice.groupby("subsystem", observed=True):
            modes = group[mode_column].dropna().astype(str).value_counts() if mode_column else pd.Series(dtype="int64")
            resolution = group["resolution_hours"] if "resolution_hours" in group.columns else pd.Series(dtype="float64")
            failure_rows.append(
                {
                    "subsystem": subsystem_name,
                    "total_failures": int(len(group)),
                    "avg_resolution_hours": _safe_mean(resolution),
                    "unique_assets": int(group[asset_column].dropna().nunique()) if asset_column else 0,
                    "top_failure_mode": modes.index[0] if not modes.empty else "UNKNOWN",
                }
            )
        failure_health = pd.DataFrame(failure_rows)
    else:
        failure_health = _empty_health_frame().iloc[0:0][
            ["subsystem", "total_failures", "avg_resolution_hours", "unique_assets", "top_failure_mode"]
        ]

    if classified_slice is not None and not classified_slice.empty:
        subsystem_column = next((name for name in ["SubSystem", "subsystem"] if name in classified_slice.columns), None)
        if subsystem_column and "failure_label" in classified_slice.columns:
            classified_health = (
                classified_slice.groupby(subsystem_column, observed=True)
                .agg(
                    maintenance_gap_count=("failure_label", lambda values: (values == "Maintenance Gap Failure").sum()),
                    equipment_failure_count=("failure_label", lambda values: (values == "Equipment Failure").sum()),
                    no_pm_count=("failure_label", lambda values: (values == "No PM Record").sum()),
                )
                .reset_index()
                .rename(columns={subsystem_column: "subsystem"})
            )
        else:
            classified_health = _empty_health_frame().iloc[0:0][
                ["subsystem", "maintenance_gap_count", "equipment_failure_count", "no_pm_count"]
            ]
    else:
        classified_health = _empty_health_frame().iloc[0:0][
            ["subsystem", "maintenance_gap_count", "equipment_failure_count", "no_pm_count"]
        ]

    health = pm_health.merge(failure_health, on="subsystem", how="outer")
    health = health.merge(classified_health, on="subsystem", how="left")
    if health.empty:
        return _empty_health_frame()
    numeric_columns = [
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
    for column in numeric_columns:
        if column not in health.columns:
            health[column] = 0
        health[column] = pd.to_numeric(health[column], errors="coerce").fillna(0)
    health["top_failure_mode"] = health.get("top_failure_mode", "UNKNOWN")
    health["top_failure_mode"] = health["top_failure_mode"].fillna("UNKNOWN")
    health["maintenance_gap_pct"] = health.apply(
        lambda row: _safe_pct(row["maintenance_gap_count"], row["total_failures"]), axis=1
    )
    health["equipment_failure_pct"] = health.apply(
        lambda row: _safe_pct(row["equipment_failure_count"], row["total_failures"]), axis=1
    )
    health["failure_rate_per_100_pm"] = health.apply(
        lambda row: round(row["total_failures"] / row["total_pm"] * 100, 2) if row["total_pm"] else (100.0 if row["total_failures"] else 0.0),
        axis=1,
    )
    health["failure_density"] = health["failure_rate_per_100_pm"] / 100
    return health


def _percentile_risk(value, distribution, *, higher_is_risk):
    values = pd.to_numeric(pd.Series(distribution), errors="coerce").dropna()
    if values.empty:
        return 50.0
    if higher_is_risk:
        return round(float((values <= float(value)).mean() * 100), 2)
    return round(float((values >= float(value)).mean() * 100), 2)


def compute_dynamic_risk_score(
    subsystem_row: dict,
    network_benchmarks: dict,
    scope_context: dict,
) -> tuple[float, dict]:
    """Return a normalized, explainable context-aware subsystem risk score."""
    row = dict(subsystem_row)
    weights = dict(BASE_RISK_WEIGHTS)
    if scope_context.get("active_recent_failures", False):
        weights["failure_volume"] = 0.40
        weights["compliance_gap"] = 0.30
    if float(row.get("maintenance_gap_pct", row.get("maintenance_gap_share", 0)) or 0) > 50:
        weights["maintenance_gap_share"] = 0.35
    if float(row.get("avg_resolution_hours", 0) or 0) > 6:
        weights["resolution_time"] = 0.20

    total_weight = sum(weights.values())
    normalized = {key: value / total_weight for key, value in weights.items()}
    last_key = list(normalized)[-1]
    normalized[last_key] = 1.0 - sum(normalized[key] for key in list(normalized)[:-1])

    compliance_score = row.get("compliance_percentile_risk")
    if compliance_score is None:
        compliance_score = _percentile_risk(
            row.get("compliance_pct", 0),
            network_benchmarks.get("compliance_pct", []),
            higher_is_risk=False,
        )
    failure_score = row.get("failure_rate_percentile_risk")
    if failure_score is None:
        failure_score = _percentile_risk(
            row.get("failure_rate_per_100_pm", 0),
            network_benchmarks.get("failure_rate_per_100_pm", []),
            higher_is_risk=True,
        )
    gap_score = float(np.clip(row.get("maintenance_gap_pct", row.get("maintenance_gap_share", 0)) or 0, 0, 100))

    network_resolution = float(network_benchmarks.get("resolution_mean", 0) or 0)
    resolution_std = float(network_benchmarks.get("resolution_std", 0) or 0)
    resolution_value = float(row.get("avg_resolution_hours", 0) or 0)
    z_score = (resolution_value - network_resolution) / resolution_std if resolution_std > 0 else 0.0
    resolution_score = 50.0 * (1.0 + math.erf(z_score / math.sqrt(2.0)))

    scores = {
        "compliance_gap": float(np.clip(compliance_score, 0, 100)),
        "failure_volume": float(np.clip(failure_score, 0, 100)),
        "maintenance_gap_share": gap_score,
        "resolution_time": float(np.clip(resolution_score, 0, 100)),
    }
    breakdown = {
        factor: {
            "weight": normalized[factor],
            "score": round(scores[factor], 2),
            "contribution": round(normalized[factor] * scores[factor], 2),
        }
        for factor in normalized
    }
    risk_score = round(sum(item["contribution"] for item in breakdown.values()), 1)
    return float(np.clip(risk_score, 0.0, 100.0)), breakdown


def _build_subsystem_health(
    pm_records,
    agg_slice,
    failure_slice,
    classified_slice,
    *,
    network_pm_records=None,
    network_agg=None,
    network_failures=None,
    network_classified=None,
    pm_records_available=True,
    active_recent_failures=False,
):
    health = _aggregate_subsystem_health(
        pm_records,
        agg_slice,
        failure_slice,
        classified_slice,
        use_agg_fallback=not pm_records_available,
    )
    if health.empty:
        return health
    network_health = _aggregate_subsystem_health(
        network_pm_records,
        network_agg,
        network_failures,
        network_classified,
        use_agg_fallback=network_pm_records is None,
    )
    if network_health.empty:
        network_health = health.copy()
    benchmarks = {
        "compliance_pct": network_health["compliance_pct"].tolist(),
        "failure_rate_per_100_pm": network_health["failure_rate_per_100_pm"].tolist(),
        "resolution_mean": _safe_mean(network_health["avg_resolution_hours"]),
        "resolution_std": float(pd.to_numeric(network_health["avg_resolution_hours"], errors="coerce").std(ddof=0) or 0),
    }
    health["compliance_percentile_risk"] = health["compliance_pct"].apply(
        lambda value: _percentile_risk(value, benchmarks["compliance_pct"], higher_is_risk=False)
    )
    health["failure_rate_percentile_risk"] = health["failure_rate_per_100_pm"].apply(
        lambda value: _percentile_risk(value, benchmarks["failure_rate_per_100_pm"], higher_is_risk=True)
    )
    scored = health.apply(
        lambda row: compute_dynamic_risk_score(
            row.to_dict(), benchmarks, {"active_recent_failures": active_recent_failures}
        ),
        axis=1,
    )
    health["risk_score"] = [result[0] for result in scored]
    health["weight_breakdown"] = [result[1] for result in scored]
    return health.sort_values(["risk_score", "total_failures"], ascending=[False, False]).reset_index(drop=True)


def _latest_date(df, candidates):
    if df is None or df.empty:
        return None
    column = next((name for name in candidates if name in df.columns), None)
    if not column:
        return None
    dates = pd.to_datetime(df[column], errors="coerce").dropna()
    return None if dates.empty else dates.max()


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
    _refresh_scope_whitelists(records_df, agg_df, failure_df, classified_failure_df)
    is_valid, scope, error_message = sanitize_scope_input(
        {"station": station, "system": system, "subsystem": subsystem, "year": year, "month": month}
    )
    if not is_valid:
        raise ValueError(error_message)
    scope["label"] = _scope_label(**scope)

    scope_filters = {
        "station": scope["station"],
        "system": scope["system"],
        "subsystem": scope["subsystem"],
        "year": scope["year"],
        "month": scope["month"],
    }

    pm_slice = _secure_filter(records_df, **scope_filters) if records_df is not None else pd.DataFrame()
    agg_slice = _filter_agg_df(agg_df, station=scope["station"], system=scope["system"], subsystem=scope["subsystem"])
    failure_slice = _secure_filter(failure_df, **scope_filters, is_failure=True) if failure_df is not None else pd.DataFrame()
    classified_slice = _filter_classified_failures(classified_failure_df, **scope_filters)

    network_pm = pipeline.compute_compliance_summary(records_df) if records_df is not None and not records_df.empty else _pm_summary_from_agg(agg_df)
    slice_pm = pipeline.compute_compliance_summary(pm_slice) if records_df is not None else _pm_summary_from_agg(agg_slice)
    network_fail = pipeline.compute_failure_summary(failure_df) if failure_df is not None and not failure_df.empty else {
        "total_failures": 0, "resolved": 0, "unresolved": 0, "unique_assets": 0, "avg_resolution_hours": 0.0
    }
    slice_fail = pipeline.compute_failure_summary(failure_slice) if failure_slice is not None and not failure_slice.empty else {
        "total_failures": 0, "resolved": 0, "unresolved": 0, "unique_assets": 0, "avg_resolution_hours": 0.0
    }

    maintenance_gap_count = int((classified_slice.get("failure_label", pd.Series(dtype="string")) == "Maintenance Gap Failure").sum())
    equipment_failure_count = int((classified_slice.get("failure_label", pd.Series(dtype="string")) == "Equipment Failure").sum())
    no_pm_count = int((classified_slice.get("failure_label", pd.Series(dtype="string")) == "No PM Record").sum())

    top_failure_modes = pd.DataFrame(columns=["error_description", "count", "share_pct"])
    if not failure_slice.empty and "error_description" in failure_slice.columns:
        top_failure_modes = failure_slice["error_description"].fillna("UNKNOWN").value_counts().head(5).rename_axis("error_description").reset_index(name="count")
        top_failure_modes["share_pct"] = top_failure_modes["count"].apply(lambda count: _safe_pct(count, slice_fail["total_failures"]))

    latest_failure = _latest_date(failure_df, ["failure_date", "Date", "failure_event_at"])
    slice_dates = pd.to_datetime(
        failure_slice[next((name for name in ["failure_date", "Date", "failure_event_at"] if name in failure_slice.columns), "failure_date")],
        errors="coerce",
    ) if not failure_slice.empty else pd.Series(dtype="datetime64[ns]")
    active_recent_failures = bool(
        latest_failure is not None and not slice_dates.empty and (slice_dates >= latest_failure - pd.Timedelta(days=30)).any()
    )
    subsystem_health = _build_subsystem_health(
        pm_slice,
        agg_slice,
        failure_slice,
        classified_slice,
        network_pm_records=records_df,
        network_agg=agg_df,
        network_failures=failure_df,
        network_classified=classified_failure_df,
        pm_records_available=records_df is not None,
        active_recent_failures=active_recent_failures,
    )
    trend_data = build_monthly_trend(records_df, failure_df, scope)

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
        "subsystem_health": subsystem_health,
        "trend_data": trend_data,
        "scope_context": {"active_recent_failures": active_recent_failures},
        "thresholds": {
            "critical_compliance": 55.0,
            "network_compliance_gap": 10.0,
            "weak_subsystem_compliance": 60.0,
            "maintenance_gap_critical": 45.0,
            "slow_resolution_hours": 4.0,
            "dominant_failure_mode_pct": 25.0,
        },
    }
    return summary


def _derive_rule_context(summary: dict) -> dict:
    context = dict(summary)
    health = summary.get("subsystem_health")
    health = health if isinstance(health, pd.DataFrame) else pd.DataFrame()
    failure_slice = summary.get("failure_slice")
    failure_slice = failure_slice if isinstance(failure_slice, pd.DataFrame) else pd.DataFrame()
    pm_slice = summary.get("pm_slice")
    pm_slice = pm_slice if isinstance(pm_slice, pd.DataFrame) else pd.DataFrame()
    trend = summary.get("trend_data") or {"months": [], "compliance": [], "resolution_avg_hours": []}

    context["worst_subsystem"] = None
    context["heavy_failure_subsystem"] = None
    context["equipment_risk_subsystem"] = None
    context["benchmark_subsystem"] = None
    context["subsystem_divergence"] = None
    if not health.empty:
        eligible = health[health["total_pm"] > 0]
        if not eligible.empty:
            context["worst_subsystem"] = eligible.sort_values("compliance_pct").iloc[0].to_dict()
            context["benchmark_subsystem"] = eligible.sort_values(["compliance_pct", "total_pm"], ascending=[False, False]).iloc[0].to_dict()
        context["heavy_failure_subsystem"] = health.sort_values(["total_failures", "maintenance_gap_pct"], ascending=[False, False]).iloc[0].to_dict()
        equipment_risk = health[(health["equipment_failure_pct"] >= 50) & (health["compliance_pct"] >= 75) & (health["total_failures"] >= 3)]
        if not equipment_risk.empty:
            context["equipment_risk_subsystem"] = equipment_risk.sort_values("total_failures", ascending=False).iloc[0].to_dict()
        ranked = eligible.sort_values("compliance_pct")
        if len(ranked) >= 2:
            gap = float(ranked.iloc[1]["compliance_pct"] - ranked.iloc[0]["compliance_pct"])
            if gap > 25:
                context["subsystem_divergence"] = {**ranked.iloc[0].to_dict(), "gap_to_next": round(gap, 1)}

    context["repeat_assets"] = []
    asset_column = next((name for name in ["eqkey", "equipment_no", "EquipmentNo"] if name in failure_slice.columns), None)
    if asset_column:
        repeated = failure_slice[asset_column].dropna().astype(str).value_counts()
        context["repeat_assets"] = [
            {"eqkey": asset, "count": int(count)} for asset, count in repeated[repeated > 3].items()
        ]

    context["pm_clustering"] = None
    if not pm_slice.empty and "done_date" in pm_slice.columns:
        dated = pm_slice.copy()
        dated["_date"] = pd.to_datetime(dated["done_date"], errors="coerce")
        dated = dated.dropna(subset=["_date"])
        if "compliance_status" in dated.columns:
            dated = dated[dated["compliance_status"] != "BASELINE"]
        if not dated.empty:
            dated["_period"] = dated["_date"].dt.to_period("M")
            dated["_last_five"] = dated["_date"].dt.day >= dated["_date"].dt.days_in_month - 4
            clustering = dated.groupby("_period")["_last_five"].agg(["mean", "size"]).reset_index()
            clustering["share_pct"] = clustering["mean"] * 100
            worst_cluster = clustering.sort_values("share_pct", ascending=False).iloc[0]
            context["pm_clustering"] = {
                "month": worst_cluster["_period"].strftime("%b %Y"),
                "share_pct": round(float(worst_cluster["share_pct"]), 1),
                "pm_count": int(worst_cluster["size"]),
            }

    context["resolution_spike"] = None
    resolutions = pd.Series(trend.get("resolution_avg_hours", []), dtype="float64")
    months = trend.get("months", [])
    focal_index = len(months) - 1
    selected_month = summary.get("scope", {}).get("month")
    selected_year = summary.get("scope", {}).get("year")
    selected_month_number = _month_index(selected_month)
    if selected_month_number and selected_year not in (None, "", "All"):
        focal_label = pd.Timestamp(year=int(selected_year), month=selected_month_number, day=1).strftime("%b %Y")
        if focal_label in months:
            focal_index = months.index(focal_label)
    if focal_index >= 3:
        prior_average = resolutions.iloc[focal_index - 3:focal_index].replace(0, np.nan).mean()
        current = resolutions.iloc[focal_index]
        if pd.notna(prior_average) and prior_average > 0 and current > 2 * prior_average:
            context["resolution_spike"] = {"month": months[focal_index], "current": float(current), "prior_average": round(float(prior_average), 1)}

    context["positive_trend"] = None
    compliance = pd.Series(trend.get("compliance", []), dtype="float64")
    if focal_index >= 2 and compliance.diff().iloc[focal_index - 1:focal_index + 1].ge(10).all():
        context["positive_trend"] = {
            "start": float(compliance.iloc[focal_index - 2]),
            "end": float(compliance.iloc[focal_index]),
            "months": months[focal_index - 2:focal_index + 1],
        }

    context["dead_zones"] = []
    if not failure_slice.empty:
        fail_station = next((name for name in ["station", "Station"] if name in failure_slice.columns), None)
        fail_subsystem = next((name for name in ["subsystem", "SubSystem"] if name in failure_slice.columns), None)
        pm_station = next((name for name in ["station", "Station"] if name in pm_slice.columns), None)
        pm_subsystem = next((name for name in ["subsystem", "SubSystem"] if name in pm_slice.columns), None)
        if fail_station and fail_subsystem:
            failure_groups = failure_slice.groupby([fail_station, fail_subsystem], observed=True).size()
            pm_keys = set()
            if not pm_slice.empty and pm_station and pm_subsystem:
                pm_keys = set(map(tuple, pm_slice[[pm_station, pm_subsystem]].drop_duplicates().to_numpy()))
            context["dead_zones"] = [
                {"station": str(key[0]), "subsystem": str(key[1]), "failure_count": int(count)}
                for key, count in failure_groups.items()
                if tuple(key) not in pm_keys and count > 0
            ]

    top_modes = summary.get("top_failure_modes")
    context["top_failure_mode"] = None if not isinstance(top_modes, pd.DataFrame) or top_modes.empty else top_modes.iloc[0].to_dict()
    anomalies = trend.get("trend_signals", [])
    context["stress_month"] = anomalies[0] if anomalies else None
    return context


def _confidence_from_count(count, full_confidence_at=20):
    return round(float(np.clip(0.45 + 0.5 * (float(count) / full_confidence_at), 0.45, 0.95)), 2)


INSIGHT_RULES = [
    {
        "id": "critical_compliance",
        "priority": "critical",
        "condition": lambda s: s["slice_pm"]["total_pm"] >= 20 and s["slice_pm"]["compliance_pct"] < s["thresholds"]["critical_compliance"],
        "title": "Critical PM Compliance Failure",
        "message_fn": lambda s: f"Compliance is {s['slice_pm']['compliance_pct']:.1f}% with {s['slice_pm']['late']:,} late PMs across {s['slice_pm']['total_pm']:,} trackable actions.",
        "recommendation": "Review overdue schedules immediately and escalate the recovery plan to the operations head.",
        "data_ref": "pm_compliance",
        "affected_assets_fn": lambda s: [],
        "confidence_fn": lambda s: _confidence_from_count(s["slice_pm"]["total_pm"]),
    },
    {
        "id": "compliance_below_network",
        "priority": "warning",
        "condition": lambda s: s["slice_pm"]["total_pm"] >= 20 and s["slice_pm"]["compliance_pct"] >= s["thresholds"]["critical_compliance"] and s["network_pm"]["compliance_pct"] - s["slice_pm"]["compliance_pct"] >= s["thresholds"]["network_compliance_gap"],
        "title": "PM Compliance Trails Network",
        "message_fn": lambda s: f"Scope compliance is {s['slice_pm']['compliance_pct']:.1f}%, {s['network_pm']['compliance_pct'] - s['slice_pm']['compliance_pct']:.1f} points below the {s['network_pm']['compliance_pct']:.1f}% network rate.",
        "recommendation": "Compare crew allocation and schedule execution with a higher-performing peer scope.",
        "data_ref": "pm_compliance",
        "affected_assets_fn": lambda s: [],
        "confidence_fn": lambda s: _confidence_from_count(s["slice_pm"]["total_pm"]),
    },
    {
        "id": "weakest_subsystem",
        "priority": "warning",
        "condition": lambda s: bool(s["worst_subsystem"]) and s["worst_subsystem"]["total_pm"] >= 10 and s["worst_subsystem"]["compliance_pct"] < s["thresholds"]["weak_subsystem_compliance"],
        "title": lambda s: f"{s['worst_subsystem']['subsystem']} Requires PM Recovery",
        "message_fn": lambda s: f"{s['worst_subsystem']['subsystem']} has {s['worst_subsystem']['compliance_pct']:.1f}% compliance, {int(s['worst_subsystem']['late_pm'])} late PMs and {int(s['worst_subsystem']['total_failures'])} failures.",
        "recommendation": lambda s: f"Audit {s['worst_subsystem']['subsystem']} schedules, manpower and recurring failure modes this week.",
        "data_ref": "pm_compliance",
        "affected_assets_fn": lambda s: [],
        "confidence_fn": lambda s: _confidence_from_count(s["worst_subsystem"]["total_pm"]),
    },
    {
        "id": "heavy_failure_load",
        "priority": "warning",
        "condition": lambda s: bool(s["heavy_failure_subsystem"]) and s["heavy_failure_subsystem"]["total_failures"] >= 5,
        "title": "Concentrated Subsystem Failure Load",
        "message_fn": lambda s: f"{s['heavy_failure_subsystem']['subsystem']} carries {int(s['heavy_failure_subsystem']['total_failures'])} failures at {s['heavy_failure_subsystem']['failure_rate_per_100_pm']:.1f} per 100 PM actions.",
        "recommendation": lambda s: f"Start the failure review with {s['heavy_failure_subsystem']['subsystem']} and its top mode: {s['heavy_failure_subsystem']['top_failure_mode']}.",
        "data_ref": "failure_count",
        "affected_assets_fn": lambda s: [],
        "confidence_fn": lambda s: _confidence_from_count(s["heavy_failure_subsystem"]["total_failures"], 10),
    },
    {
        "id": "maintenance_gap_failures",
        "priority": "critical",
        "condition": lambda s: s["slice_fail"]["total_failures"] > 0 and s["maintenance_gap_pct"] >= s["thresholds"]["maintenance_gap_critical"],
        "title": "Maintenance Gaps Drive Failures",
        "message_fn": lambda s: f"Maintenance-gap failures are {s['maintenance_gap_pct']:.1f}% ({s['maintenance_gap_count']} of {s['slice_fail']['total_failures']} failures) in {s['scope']['label']}.",
        "recommendation": "Recover missed PMs first, then review whether the same assets fail after overdue work.",
        "data_ref": "gap_failure_pct",
        "affected_assets_fn": lambda s: [],
        "confidence_fn": lambda s: _confidence_from_count(s["slice_fail"]["total_failures"], 15),
    },
    {
        "id": "slow_resolution",
        "priority": "warning",
        "condition": lambda s: s["slice_fail"]["total_failures"] > 0 and s["slice_fail"]["avg_resolution_hours"] > s["thresholds"]["slow_resolution_hours"],
        "title": "Failure Resolution Is Slow",
        "message_fn": lambda s: f"Average resolution time is {s['slice_fail']['avg_resolution_hours']:.1f} hours across {s['slice_fail']['resolved']} resolved failures in {s['scope']['label']}.",
        "recommendation": "Review crew response, escalation delay and spare availability for the longest cases.",
        "data_ref": "resolution_avg_hours",
        "affected_assets_fn": lambda s: [],
        "confidence_fn": lambda s: _confidence_from_count(s["slice_fail"]["resolved"], 15),
    },
    {
        "id": "dominant_failure_mode",
        "priority": "warning",
        "condition": lambda s: bool(s["top_failure_mode"]) and s["top_failure_mode"]["share_pct"] >= s["thresholds"]["dominant_failure_mode_pct"],
        "title": "One Failure Mode Dominates",
        "message_fn": lambda s: f"{s['top_failure_mode']['error_description']} occurred {int(s['top_failure_mode']['count'])} times and represents {s['top_failure_mode']['share_pct']:.1f}% of scope failures.",
        "recommendation": "Run a focused root-cause review on this mode before addressing lower-volume categories.",
        "data_ref": "failure_count",
        "affected_assets_fn": lambda s: [],
        "confidence_fn": lambda s: _confidence_from_count(s["top_failure_mode"]["count"], 10),
    },
    {
        "id": "equipment_stress",
        "priority": "warning",
        "condition": lambda s: bool(s["equipment_risk_subsystem"]),
        "title": "Equipment Stress Despite Compliant PM",
        "message_fn": lambda s: f"{s['equipment_risk_subsystem']['subsystem']} has {s['equipment_risk_subsystem']['equipment_failure_pct']:.1f}% equipment-side failures despite {s['equipment_risk_subsystem']['compliance_pct']:.1f}% PM compliance.",
        "recommendation": lambda s: f"Escalate {s['equipment_risk_subsystem']['subsystem']} for vendor, design or replacement review.",
        "data_ref": "failure_count",
        "affected_assets_fn": lambda s: [],
        "confidence_fn": lambda s: _confidence_from_count(s["equipment_risk_subsystem"]["total_failures"], 10),
    },
    {
        "id": "repeat_failure",
        "priority": "critical",
        "condition": lambda s: bool(s["repeat_assets"]),
        "title": lambda s: f"Repeat Failure on Asset {s['repeat_assets'][0]['eqkey']}",
        "message_fn": lambda s: f"Asset {s['repeat_assets'][0]['eqkey']} appears in {s['repeat_assets'][0]['count']} failures — possible systemic hardware issue or incorrect PM procedure.",
        "recommendation": "Quarantine the repeat asset for root-cause inspection and verify its last PM procedure and parts history.",
        "data_ref": "failure_count",
        "affected_assets_fn": lambda s: [item["eqkey"] for item in s["repeat_assets"]],
        "confidence_fn": lambda s: min(0.98, 0.7 + s["repeat_assets"][0]["count"] * 0.04),
    },
    {
        "id": "pm_clustering",
        "priority": "warning",
        "condition": lambda s: bool(s["pm_clustering"]) and s["pm_clustering"]["share_pct"] > 40,
        "title": "PM Bunching Detected",
        "message_fn": lambda s: f"{s['pm_clustering']['share_pct']:.1f}% of {s['pm_clustering']['pm_count']} PMs in {s['pm_clustering']['month']} fell in the last five days, indicating deferred then rushed work.",
        "recommendation": "Redistribute the affected month's PM plan across earlier weeks and track weekly completion.",
        "data_ref": "late_pm_count",
        "affected_assets_fn": lambda s: [],
        "confidence_fn": lambda s: _confidence_from_count(s["pm_clustering"]["pm_count"], 20),
    },
    {
        "id": "resolution_time_spike",
        "priority": "warning",
        "condition": lambda s: bool(s["resolution_spike"]),
        "title": "Resolution Time Spike",
        "message_fn": lambda s: f"Resolution time reached {s['resolution_spike']['current']:.1f} hours in {s['resolution_spike']['month']}, over twice the prior three-month average of {s['resolution_spike']['prior_average']:.1f} hours.",
        "recommendation": "Check crew availability, escalation queues and parts shortages for the spike month.",
        "data_ref": "resolution_avg_hours",
        "affected_assets_fn": lambda s: [],
        "confidence_fn": lambda s: 0.82,
    },
    {
        "id": "subsystem_divergence",
        "priority": "warning",
        "condition": lambda s: bool(s["subsystem_divergence"]),
        "title": "Subsystem Compliance Outlier",
        "message_fn": lambda s: f"{s['subsystem_divergence']['subsystem']} is {s['subsystem_divergence']['gap_to_next']:.1f} points below the next-worst subsystem and is pulling overall compliance down disproportionately.",
        "recommendation": lambda s: f"Create a subsystem-specific recovery owner and weekly target for {s['subsystem_divergence']['subsystem']}.",
        "data_ref": "pm_compliance",
        "affected_assets_fn": lambda s: [],
        "confidence_fn": lambda s: _confidence_from_count(s["subsystem_divergence"]["total_pm"]),
    },
    {
        "id": "monthly_stress_anomaly",
        "priority": "warning",
        "condition": lambda s: bool(s["stress_month"]),
        "title": "Monthly Stress Anomaly",
        "message_fn": lambda s: f"{s['stress_month']['month']}: {s['stress_month']['signal']}",
        "recommendation": "Use the flagged month as the first review window for backlog, crew constraints and repeated breakdowns.",
        "data_ref": "failure_count",
        "affected_assets_fn": lambda s: [],
        "confidence_fn": lambda s: 0.8,
    },
    {
        "id": "positive_trend",
        "priority": "positive",
        "condition": lambda s: bool(s["positive_trend"]),
        "title": "Sustained PM Improvement",
        "message_fn": lambda s: f"Compliance improved from {s['positive_trend']['start']:.1f}% to {s['positive_trend']['end']:.1f}% across {', '.join(s['positive_trend']['months'])}; scheduling changes are showing results.",
        "recommendation": "Document the scheduling change and sustain it for another quarter before scaling it.",
        "data_ref": "pm_compliance",
        "affected_assets_fn": lambda s: [],
        "confidence_fn": lambda s: 0.85,
    },
    {
        "id": "dead_zone",
        "priority": "critical",
        "condition": lambda s: bool(s["dead_zones"]),
        "title": "PM Dead Zone With Active Failures",
        "message_fn": lambda s: f"No PM activity was recorded for {s['dead_zones'][0]['subsystem']} at {s['dead_zones'][0]['station']} despite {s['dead_zones'][0]['failure_count']} reported failures.",
        "recommendation": lambda s: f"Verify the PM asset register for {s['dead_zones'][0]['subsystem']} at {s['dead_zones'][0]['station']} and schedule immediate coverage.",
        "data_ref": "failure_count",
        "affected_assets_fn": lambda s: [],
        "confidence_fn": lambda s: 0.9,
    },
    {
        "id": "benchmark_subsystem",
        "priority": "positive",
        "condition": lambda s: bool(s["benchmark_subsystem"]) and s["benchmark_subsystem"]["total_pm"] >= 20 and s["benchmark_subsystem"]["compliance_pct"] >= 85,
        "title": "Benchmark Subsystem Performance",
        "message_fn": lambda s: f"{s['benchmark_subsystem']['subsystem']} achieved {s['benchmark_subsystem']['compliance_pct']:.1f}% compliance across {int(s['benchmark_subsystem']['total_pm'])} PM actions with {int(s['benchmark_subsystem']['total_failures'])} failures.",
        "recommendation": lambda s: f"Document and reuse {s['benchmark_subsystem']['subsystem']} scheduling practices in weaker subsystems.",
        "data_ref": "pm_compliance",
        "affected_assets_fn": lambda s: [],
        "confidence_fn": lambda s: _confidence_from_count(s["benchmark_subsystem"]["total_pm"]),
    },
]


def validate_insight_output(insights: list) -> list:
    """Remove incomplete/duplicate rule outputs and cap messages at 200 characters."""
    validated = []
    seen = set()
    placeholder_pattern = re.compile(r"\[[A-Za-z0-9_]+\]")
    for insight in insights or []:
        insight_id = insight.get("id")
        message = str(insight.get("message", "")).strip()
        if not insight_id or insight_id in seen or not message or placeholder_pattern.search(message):
            continue
        cleaned = dict(insight)
        cleaned["message"] = message if len(message) <= 200 else message[:197].rstrip() + "..."
        cleaned["affected_assets"] = list(cleaned.get("affected_assets") or [])
        cleaned["confidence"] = float(np.clip(cleaned.get("confidence", 0.0), 0.0, 1.0))
        validated.append(cleaned)
        seen.add(insight_id)
    return validated


def generate_scope_insights(summary, trend_data=None):
    """Run the layered, data-grounded insight rule engine for one scope."""
    if trend_data is not None:
        summary = dict(summary)
        summary["trend_data"] = trend_data
    context = _derive_rule_context(summary)
    insights = []
    for rule in INSIGHT_RULES:
        try:
            if not rule["condition"](context):
                continue
            title = rule["title"](context) if callable(rule["title"]) else rule["title"]
            recommendation = rule["recommendation"](context) if callable(rule["recommendation"]) else rule["recommendation"]
            insights.append(
                {
                    "id": rule["id"],
                    "priority": rule["priority"],
                    "title": str(title),
                    "message": str(rule["message_fn"](context)),
                    "recommendation": str(recommendation),
                    "data_ref": rule["data_ref"],
                    "affected_assets": rule.get("affected_assets_fn", lambda _: [])(context),
                    "confidence": float(rule.get("confidence_fn", lambda _: 0.75)(context)),
                }
            )
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    priority_order = {"critical": 0, "warning": 1, "info": 2, "positive": 3}
    insights.sort(key=lambda item: priority_order.get(item["priority"], 9))
    return validate_insight_output(insights)[:10]


def _date_range_text(summary):
    dates = []
    for frame_key, candidates in [
        ("pm_slice", ["done_date", "Date"]),
        ("failure_slice", ["failure_date", "Date", "failure_event_at"]),
    ]:
        frame = summary.get(frame_key)
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            column = next((name for name in candidates if name in frame.columns), None)
            if column:
                dates.extend(pd.to_datetime(frame[column], errors="coerce").dropna().tolist())
    return "Unavailable" if not dates else f"{min(dates):%d %b %Y} to {max(dates):%d %b %Y}"


def build_structured_ai_context(slice_summary: dict, insights: list, trend_data: dict) -> dict:
    """Build the only structured, computed payload permitted in the AI brief."""
    priority_order = {"critical": 0, "warning": 1, "info": 2, "positive": 3}
    ranked_insights = sorted(insights, key=lambda item: priority_order.get(item.get("priority"), 9))
    top_insights = [
        {
            "title": str(item["title"]),
            "message": str(item["message"]),
            "recommendation": str(item["recommendation"]),
        }
        for item in ranked_insights[:3]
    ]

    health = slice_summary.get("subsystem_health")
    subsystem_ranking = []
    if isinstance(health, pd.DataFrame) and not health.empty:
        for _, row in health.head(5).iterrows():
            breakdown = row.get("weight_breakdown", {})
            subsystem_ranking.append(
                {
                    "subsystem": str(row.get("subsystem", "UNKNOWN")),
                    "risk_score": round(float(row.get("risk_score", 0)), 1),
                    "weight_breakdown": {
                        str(factor): {
                            "weight": round(float(values.get("weight", 0)), 4),
                            "score": round(float(values.get("score", 0)), 2),
                            "contribution": round(float(values.get("contribution", 0)), 2),
                        }
                        for factor, values in (breakdown or {}).items()
                    },
                }
            )

    months = list(trend_data.get("months", []))
    compliance = list(trend_data.get("compliance", []))
    failures = list(trend_data.get("failure_count", []))
    if months:
        trend_summary = f"Latest month {months[-1]}: compliance {compliance[-1]:.1f}% and {int(failures[-1])} failures."
        if len(months) >= 2:
            trend_summary += f" Compliance changed {compliance[-1] - compliance[-2]:+.1f} points from {months[-2]}."
    else:
        trend_summary = "No monthly trend is available for this scope."
    correlation = compute_rolling_correlation(trend_data)

    slice_fail = slice_summary.get("slice_fail", {})
    slice_pm = slice_summary.get("slice_pm", {})
    classified = slice_summary.get("classified_slice")
    return {
        "scope_label": str(slice_summary.get("scope", {}).get("label", "entire network")),
        "critical_count": sum(item.get("priority") == "critical" for item in insights),
        "warning_count": sum(item.get("priority") == "warning" for item in insights),
        "top_3_insights": top_insights,
        "subsystem_ranking": subsystem_ranking,
        "trend_summary": trend_summary,
        "lag_correlation_signal": correlation["interpretation"],
        "data_completeness": {
            "has_failure_data": bool(slice_fail.get("total_failures", 0)),
            "has_classified_data": isinstance(classified, pd.DataFrame) and not classified.empty,
            "pm_record_count": int(slice_pm.get("total_pm", 0)),
            "failure_record_count": int(slice_fail.get("total_failures", 0)),
            "date_range": _date_range_text(slice_summary),
        },
    }


def generate_insights(pm_agg_df, failure_summary_df):
    """Backward-compatible network-wide entry point used by older callers."""
    slice_failures = int(failure_summary_df["total_failures"].sum()) if isinstance(failure_summary_df, pd.DataFrame) and not failure_summary_df.empty else 0
    maintenance_gaps = int(failure_summary_df["maintenance_gap_count"].sum()) if isinstance(failure_summary_df, pd.DataFrame) and "maintenance_gap_count" in failure_summary_df else 0
    summary = {
        "scope": {"label": "entire network"},
        "slice_pm": _pm_summary_from_agg(pm_agg_df),
        "network_pm": _pm_summary_from_agg(pm_agg_df),
        "slice_fail": {"total_failures": slice_failures, "resolved": 0, "avg_resolution_hours": 0.0},
        "maintenance_gap_count": maintenance_gaps,
        "maintenance_gap_pct": _safe_pct(maintenance_gaps, slice_failures),
        "top_failure_modes": pd.DataFrame(),
        "subsystem_health": _aggregate_subsystem_health(None, pm_agg_df, None, None, use_agg_fallback=True),
        "failure_slice": pd.DataFrame(),
        "pm_slice": pd.DataFrame(),
        "classified_slice": pd.DataFrame(),
        "trend_data": {"months": [], "compliance": [], "late_pm_count": [], "failure_count": [], "resolution_avg_hours": [], "gap_failure_pct": [], "trend_signals": []},
        "thresholds": {
            "critical_compliance": 55.0,
            "network_compliance_gap": 10.0,
            "weak_subsystem_compliance": 60.0,
            "maintenance_gap_critical": 45.0,
            "slow_resolution_hours": 4.0,
            "dominant_failure_mode_pct": 25.0,
        },
    }
    return generate_scope_insights(summary)
