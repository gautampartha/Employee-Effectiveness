"""Monthly trend and predictive-signal utilities for the Insights dashboard."""

from __future__ import annotations

import numpy as np
import pandas as pd


MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def _scope_value(scope: dict, key: str):
    value = (scope or {}).get(key)
    return None if value in (None, "", "All") else value


def _filter_scope(df: pd.DataFrame | None, scope: dict, *, is_failure: bool) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    filtered = df.copy()
    column_candidates = {
        "station": ["station", "Station"],
        "system": ["system", "System"],
        "subsystem": ["subsystem", "SubSystem"],
    }
    for key, candidates in column_candidates.items():
        value = _scope_value(scope, key)
        column = next((name for name in candidates if name in filtered.columns), None)
        if value is not None and column is not None:
            filtered = filtered[filtered[column] == value]

    date_candidates = ["failure_date", "Date", "failure_event_at"] if is_failure else ["done_date", "Date"]
    date_column = next((name for name in date_candidates if name in filtered.columns), None)
    if date_column is None:
        return pd.DataFrame()
    filtered["_trend_date"] = pd.to_datetime(filtered[date_column], errors="coerce")
    filtered = filtered.dropna(subset=["_trend_date"])

    year = _scope_value(scope, "year")
    if year is not None:
        filtered = filtered[filtered["_trend_date"].dt.year == int(year)]

    # Month is deliberately not applied. The selected month is the focal point,
    # but retaining its neighbouring months is required for rolling comparisons.
    return filtered


def _monthly_pm(pm_slice: pd.DataFrame) -> pd.DataFrame:
    if pm_slice.empty:
        return pd.DataFrame(columns=["period", "total_pm", "on_time", "late_pm_count", "compliance"])

    trackable = pm_slice
    if "compliance_status" in trackable.columns:
        trackable = trackable[trackable["compliance_status"] != "BASELINE"].copy()
    if trackable.empty:
        return pd.DataFrame(columns=["period", "total_pm", "on_time", "late_pm_count", "compliance"])

    trackable["period"] = trackable["_trend_date"].dt.to_period("M")
    status_column = "compliance_status" if "compliance_status" in trackable.columns else None
    if status_column:
        monthly = (
            trackable.groupby("period", observed=True)
            .agg(
                total_pm=(status_column, "size"),
                on_time=(status_column, lambda values: (values == "ON_TIME").sum()),
                late_pm_count=(status_column, lambda values: (values == "LATE").sum()),
            )
            .reset_index()
        )
    else:
        monthly = trackable.groupby("period", observed=True).size().reset_index(name="total_pm")
        monthly["on_time"] = 0
        monthly["late_pm_count"] = 0
    monthly["compliance"] = (
        monthly["on_time"] / monthly["total_pm"].replace(0, np.nan) * 100
    ).fillna(0.0)
    return monthly


def _monthly_failures(failure_slice: pd.DataFrame) -> pd.DataFrame:
    columns = ["period", "failure_count", "resolution_avg_hours", "gap_failure_pct"]
    if failure_slice.empty:
        return pd.DataFrame(columns=columns)

    failure_slice = failure_slice.copy()
    failure_slice["period"] = failure_slice["_trend_date"].dt.to_period("M")
    resolution_column = next(
        (name for name in ["resolution_hours", "DurationHours", "duration_hours"] if name in failure_slice.columns),
        None,
    )
    label_column = next((name for name in ["failure_label", "FailureLabel"] if name in failure_slice.columns), None)

    grouped = failure_slice.groupby("period", observed=True)
    monthly = grouped.size().reset_index(name="failure_count")
    if resolution_column:
        resolution = grouped[resolution_column].mean().reset_index(name="resolution_avg_hours")
        monthly = monthly.merge(resolution, on="period", how="left")
    else:
        monthly["resolution_avg_hours"] = 0.0

    if label_column:
        gaps = grouped[label_column].agg(lambda values: (values == "Maintenance Gap Failure").sum()).reset_index(name="gap_count")
        monthly = monthly.merge(gaps, on="period", how="left")
        monthly["gap_failure_pct"] = (
            monthly["gap_count"] / monthly["failure_count"].replace(0, np.nan) * 100
        ).fillna(0.0)
    else:
        monthly["gap_failure_pct"] = 0.0
    return monthly[columns]


def build_monthly_trend(pm_df, failure_df, scope: dict) -> dict:
    """Build a complete monthly time series for a selected operational scope."""
    pm_slice = _filter_scope(pm_df, scope, is_failure=False)
    failure_slice = _filter_scope(failure_df, scope, is_failure=True)
    pm_monthly = _monthly_pm(pm_slice)
    failure_monthly = _monthly_failures(failure_slice)

    periods = []
    if not pm_monthly.empty:
        periods.extend(pm_monthly["period"].tolist())
    if not failure_monthly.empty:
        periods.extend(failure_monthly["period"].tolist())

    if not periods:
        empty = {
            "months": [],
            "compliance": [],
            "late_pm_count": [],
            "failure_count": [],
            "resolution_avg_hours": [],
            "gap_failure_pct": [],
            "trend_signals": [],
        }
        return empty

    period_index = pd.period_range(min(periods), max(periods), freq="M")
    monthly = pd.DataFrame({"period": period_index})
    monthly = monthly.merge(pm_monthly, on="period", how="left")
    monthly = monthly.merge(failure_monthly, on="period", how="left")
    for column in ["total_pm", "on_time", "late_pm_count", "failure_count"]:
        monthly[column] = monthly[column].fillna(0).astype(int)
    for column in ["compliance", "resolution_avg_hours", "gap_failure_pct"]:
        monthly[column] = pd.to_numeric(monthly[column], errors="coerce").fillna(0.0).round(1)

    trend_data = {
        "months": [period.strftime("%b %Y") for period in monthly["period"]],
        "compliance": monthly["compliance"].astype(float).tolist(),
        "late_pm_count": monthly["late_pm_count"].astype(int).tolist(),
        "failure_count": monthly["failure_count"].astype(int).tolist(),
        "resolution_avg_hours": monthly["resolution_avg_hours"].astype(float).tolist(),
        "gap_failure_pct": monthly["gap_failure_pct"].astype(float).tolist(),
        "trend_signals": [],
    }
    trend_data["trend_signals"] = detect_anomalous_months(trend_data)
    return trend_data


def detect_anomalous_months(trend_data: dict) -> list[dict]:
    """Flag material month-over-month and statistical anomalies."""
    months = list(trend_data.get("months", []))
    if not months:
        return []

    compliance = pd.Series(trend_data.get("compliance", []), dtype="float64")
    failures = pd.Series(trend_data.get("failure_count", []), dtype="float64")
    resolution = pd.Series(trend_data.get("resolution_avg_hours", []), dtype="float64")
    signals: list[dict] = []

    for index, change in compliance.diff().items():
        if pd.notna(change) and change < -15:
            signals.append(
                {
                    "month": months[index],
                    "signal": f"PM compliance dropped {abs(change):.1f} points month over month.",
                    "severity": "critical",
                }
            )

    failure_std = failures.std(ddof=0)
    failure_limit = failures.mean() + 2 * failure_std
    if failure_std > 0:
        for index in failures[failures > failure_limit].index:
            signals.append(
                {
                    "month": months[index],
                    "signal": f"Failure count reached {int(failures.iloc[index])}, above the two-standard-deviation limit.",
                    "severity": "critical",
                }
            )

    resolution_std = resolution.std(ddof=0)
    resolution_limit = resolution.mean() + 1.5 * resolution_std
    if resolution_std > 0:
        for index in resolution[resolution > resolution_limit].index:
            signals.append(
                {
                    "month": months[index],
                    "signal": f"Average resolution time reached {resolution.iloc[index]:.1f} hours.",
                    "severity": "warning",
                }
            )
    return signals


def compute_rolling_correlation(trend_data: dict) -> dict:
    """Correlate a month's late PM count with the following month's failures."""
    late_pm = pd.Series(trend_data.get("late_pm_count", []), dtype="float64")
    failures = pd.Series(trend_data.get("failure_count", []), dtype="float64")
    aligned = pd.DataFrame({"late_pm": late_pm, "next_month_failures": failures.shift(-1)}).dropna()

    if len(aligned) < 3 or aligned["late_pm"].nunique() < 2 or aligned["next_month_failures"].nunique() < 2:
        return {
            "lag_correlation": 0.0,
            "interpretation": "Insufficient month-to-month variation to establish a predictive relationship.",
        }

    # A rolling calculation supplies local three-month relationships; the full
    # aligned correlation remains the stable headline signal for the scope.
    rolling = aligned["late_pm"].rolling(3).corr(aligned["next_month_failures"])
    full_correlation = aligned["late_pm"].corr(aligned["next_month_failures"])
    correlation = full_correlation if pd.notna(full_correlation) else rolling.dropna().mean()
    correlation = 0.0 if pd.isna(correlation) else float(np.clip(correlation, -1.0, 1.0))

    magnitude = abs(correlation)
    if magnitude >= 0.6:
        strength = "strong"
    elif magnitude >= 0.4:
        strength = "moderate"
    else:
        strength = "weak"
    direction = "positive" if correlation >= 0 else "negative"
    return {
        "lag_correlation": round(correlation, 3),
        "interpretation": (
            f"{strength.capitalize()} {direction} one-month lag relationship (r={correlation:.2f}) between late PMs and following-month failures."
        ),
    }
