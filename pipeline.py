from pathlib import Path
import difflib
import re

import numpy as np
import pandas as pd

from intent_classifier import classify_intent, security_filter


NULL_TOKENS = {"", "NULL", "NAN", "NONE", "NA", "N/A"}


def _normalize_text(value):
    if pd.isna(value):
        return pd.NA
    text = str(value).strip()
    if text.upper() in NULL_TOKENS:
        return pd.NA
    return text


def _normalize_label(value):
    text = _normalize_text(value)
    if pd.isna(text):
        return pd.NA
    return text.upper()


def _normalize_person_series(primary_series, fallback_series=None):
    primary = primary_series.map(_normalize_text)
    if fallback_series is None:
        return primary.fillna("Unassigned")

    fallback = fallback_series.map(_normalize_text)
    return primary.fillna(fallback).fillna("Unassigned")


def load_records_clean(filepath):
    """
    Load the record-level PM data used for drill-down analysis.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"PM record file not found: {path}")

    cols_to_use = [
        "EqpID",
        "Eqp_Name",
        "station",
        "section",
        "system",
        "subsystem",
        "schedule_name",
        "done_date",
        "done_by",
        "expected_due_date",
        "days_late",
        "compliance_status",
    ]

    dtypes = {
        "EqpID": "string",
        "Eqp_Name": "string",
        "station": "string",
        "section": "string",
        "system": "string",
        "subsystem": "string",
        "schedule_name": "string",
        "done_by": "string",
        "compliance_status": "string",
        "days_late": "float32",
    }

    df = pd.read_csv(path, usecols=cols_to_use, dtype=dtypes, low_memory=False)
    df["done_date"] = pd.to_datetime(df["done_date"], errors="coerce")
    df["expected_due_date"] = pd.to_datetime(df["expected_due_date"], errors="coerce")

    for col in ["station", "section", "system", "subsystem", "schedule_name", "compliance_status"]:
        df[col] = df[col].map(_normalize_label)

    df["done_by"] = df["done_by"].map(_normalize_text)
    df["eqkey"] = df["EqpID"].map(_normalize_label).str.replace(r"[^A-Z0-9]+", "", regex=True)
    return df


def load_compliance_agg(filepath):
    """
    Load the pre-aggregated compliance rollup file.
    """
    path = Path(filepath)
    dtypes = {
        "station": "string",
        "system": "string",
        "subsystem": "string",
        "schedule_name": "string",
        "total_pm": "int32",
        "on_time": "int32",
        "late": "int32",
        "avg_days_late": "float32",
        "compliance_pct": "float32",
    }
    df = pd.read_csv(path, dtype=dtypes, low_memory=False)

    for col in ["station", "system", "subsystem", "schedule_name"]:
        df[col] = df[col].map(_normalize_label)

    return df


def filter_records(
    df,
    station=None,
    system=None,
    subsystem=None,
    schedule_name=None,
    year=None,
    month=None,
):
    """
    Apply optional filters to PM records.
    """
    filtered_df = df

    if station and station != "All":
        filtered_df = filtered_df[filtered_df["station"] == station]

    if system and system != "All":
        filtered_df = filtered_df[filtered_df["system"] == system]

    if subsystem and subsystem != "All":
        filtered_df = filtered_df[filtered_df["subsystem"] == subsystem]

    if schedule_name and schedule_name != "All":
        filtered_df = filtered_df[filtered_df["schedule_name"] == schedule_name]

    if year and year != "All":
        filtered_df = filtered_df[filtered_df["done_date"].dt.year == int(year)]

    if month and month != "All":
        months_list = [
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
        month_idx = months_list.index(month) + 1
        filtered_df = filtered_df[filtered_df["done_date"].dt.month == month_idx]

    return filtered_df


def compute_compliance_summary(filtered_df):
    """
    Compute PM KPIs from the record-level dataset.
    """
    trackable_df = filtered_df[filtered_df["compliance_status"] != "BASELINE"]
    total_pm = len(trackable_df)

    if total_pm > 0:
        on_time = int((trackable_df["compliance_status"] == "ON_TIME").sum())
        late = int((trackable_df["compliance_status"] == "LATE").sum())
        compliance_pct = float((on_time / total_pm) * 100)
        avg_days_late = float(trackable_df["days_late"].mean())
    else:
        on_time = 0
        late = 0
        compliance_pct = 0.0
        avg_days_late = 0.0

    return {
        "total_pm": total_pm,
        "on_time": on_time,
        "late": late,
        "compliance_pct": round(compliance_pct, 1),
        "avg_days_late": round(avg_days_late, 1),
    }


def compute_compliance_summary_from_agg(agg_df):
    """
    Compute PM KPIs from the aggregated dataset when record-level PM data is absent.
    """
    total_pm = int(agg_df["total_pm"].sum())
    on_time = int(agg_df["on_time"].sum())
    late = int(agg_df["late"].sum())

    if total_pm > 0:
        compliance_pct = (on_time / total_pm) * 100
        avg_days_late = np.average(agg_df["avg_days_late"], weights=agg_df["total_pm"])
    else:
        compliance_pct = 0.0
        avg_days_late = 0.0

    return {
        "total_pm": total_pm,
        "on_time": on_time,
        "late": late,
        "compliance_pct": round(float(compliance_pct), 1),
        "avg_days_late": round(float(avg_days_late), 1),
    }


def get_pm_date_bounds(records_df):
    """
    Return the min/max PM completion dates available in the current system.
    """
    if records_df is None or records_df.empty:
        return None, None

    valid_dates = records_df["done_date"].dropna()
    if valid_dates.empty:
        return None, None

    return valid_dates.min().normalize(), valid_dates.max().normalize()


def load_failure_events(filepath, lookup_path, pm_date_range=None):
    """
    Load the CSS failure log and enrich it with the error master from errors.csv.
    """
    path = Path(filepath)
    lookup = Path(lookup_path)
    if not path.exists():
        raise FileNotFoundError(f"Failure log not found: {path}")
    if not lookup.exists():
        raise FileNotFoundError(f"Error lookup not found: {lookup}")

    css_cols = [
        "Date",
        "Line",
        "Sec",
        "Station",
        "System",
        "SubSystem",
        "EquipmentNo",
        "FailureTime",
        "FailureDescription",
        "Failure_Detail",
        "Status",
        "FailureCategory",
        "FailureType",
        "RectificationTime",
        "RectificationDate",
        "Duration",
        "ActionTaken",
        "Origin",
        "Attendedby",
        "Remarksby",
        "AttendedByName",
        "RemarksByName",
        "root_cause_analysis",
    ]

    css_df = pd.read_csv(path, usecols=css_cols, dtype="string", low_memory=False)
    errors_df = pd.read_csv(
        lookup,
        dtype={
            "id": "Int64",
            "eqp_type_name": "string",
            "failure_cat": "string",
            "code": "string",
            "description": "string",
            "ErrorGroup": "string",
            "Status": "string",
        },
        low_memory=False,
    )

    css_df = css_df.rename(
        columns={
            "Date": "failure_date",
            "Line": "line",
            "Sec": "section",
            "Station": "station",
            "System": "system",
            "SubSystem": "subsystem",
            "EquipmentNo": "equipment_no",
            "FailureTime": "failure_time",
            "FailureDescription": "failure_code_raw",
            "Failure_Detail": "failure_detail",
            "Status": "status",
            "FailureCategory": "failure_category_raw",
            "FailureType": "failure_type_raw",
            "RectificationTime": "rectification_time",
            "RectificationDate": "rectification_date",
            "Duration": "duration_raw",
            "ActionTaken": "action_taken",
            "Origin": "origin",
            "Attendedby": "attended_by",
            "Remarksby": "remarks_by",
            "AttendedByName": "attended_by_name",
            "RemarksByName": "remarks_by_name",
            "root_cause_analysis": "root_cause_analysis",
        }
    )

    css_df["failure_date"] = pd.to_datetime(css_df["failure_date"], errors="coerce")
    css_df["failure_time"] = pd.to_datetime(css_df["failure_time"], errors="coerce")
    css_df["rectification_date"] = pd.to_datetime(css_df["rectification_date"], errors="coerce")
    css_df["rectification_time"] = pd.to_datetime(css_df["rectification_time"], errors="coerce")
    css_df["failure_code"] = pd.to_numeric(css_df["failure_code_raw"], errors="coerce").astype("Int64")

    for col in ["station", "system", "subsystem", "line", "section"]:
        css_df[col] = css_df[col].map(_normalize_label)

    for col in ["equipment_no", "failure_detail", "action_taken", "origin", "root_cause_analysis"]:
        css_df[col] = css_df[col].map(_normalize_text)

    css_df["attended_by_display"] = _normalize_person_series(
        css_df["attended_by_name"], css_df["attended_by"]
    )
    css_df["remarks_by_display"] = _normalize_person_series(
        css_df["remarks_by_name"], css_df["remarks_by"]
    )

    errors_df = errors_df.rename(
        columns={
            "id": "failure_code",
            "eqp_type_name": "mapped_eqp_type",
            "failure_cat": "error_category_master",
            "description": "error_description_master",
            "ErrorGroup": "error_group",
            "Status": "error_status",
        }
    )

    for col in ["mapped_eqp_type", "error_category_master", "error_description_master", "error_group"]:
        errors_df[col] = errors_df[col].map(_normalize_text)

    css_df = css_df.merge(errors_df, on="failure_code", how="left")

    css_df["mapped_eqp_type_norm"] = css_df["mapped_eqp_type"].map(_normalize_label)
    css_df["error_description"] = css_df["error_description_master"].fillna(css_df["failure_detail"])
    css_df["failure_category"] = css_df["error_category_master"].fillna(css_df["failure_category_raw"])
    css_df["failure_category"] = css_df["failure_category"].map(_normalize_text)

    css_df["mapping_confidence"] = "LOOKUP_ONLY"
    exact_match = css_df["subsystem"] == css_df["mapped_eqp_type_norm"]
    # pandas string accessors accept one pattern, not a different pattern for
    # every row. Compare the two normalized labels pairwise instead.
    family_match = pd.Series(
        [
            bool(subsystem and mapped_type and (mapped_type in subsystem or subsystem in mapped_type))
            for subsystem, mapped_type in zip(
                css_df["subsystem"].fillna(""),
                css_df["mapped_eqp_type_norm"].fillna(""),
            )
        ],
        index=css_df.index,
    )
    system_level_match = (
        ((css_df["mapped_eqp_type_norm"] == "ALL AFC") & (css_df["system"] == "AFC"))
        | ((css_df["mapped_eqp_type_norm"] == "ALL TELECOM") & (css_df["system"] == "TELECOM"))
    )
    css_df.loc[exact_match, "mapping_confidence"] = "EXACT_SUBSYSTEM_MATCH"
    css_df.loc[~exact_match & family_match, "mapping_confidence"] = "FAMILY_MATCH"
    css_df.loc[~exact_match & ~family_match & system_level_match, "mapping_confidence"] = "SYSTEM_LEVEL_MATCH"
    css_df.loc[css_df["failure_code"].isna(), "mapping_confidence"] = "UNMAPPED"

    css_df["failure_event_at"] = css_df["failure_time"].fillna(css_df["failure_date"])
    css_df["resolved"] = css_df["rectification_date"].notna()
    css_df["eqkey"] = css_df["equipment_no"].map(_normalize_label).str.replace(r"[^A-Z0-9]+", "", regex=True)

    duration_hours = pd.to_numeric(css_df["duration_raw"], errors="coerce") / 3600.0
    timestamp_hours = (
        css_df["rectification_date"] - css_df["failure_event_at"]
    ).dt.total_seconds() / 3600.0
    css_df["resolution_hours"] = timestamp_hours.where(timestamp_hours > 0, duration_hours)

    if pm_date_range and pm_date_range[0] is not None and pm_date_range[1] is not None:
        start_date, end_date = pm_date_range
        css_df = css_df[
            css_df["failure_date"].between(start_date, end_date, inclusive="both")
        ].copy()
        css_df["pm_window_applied"] = True
    else:
        css_df["pm_window_applied"] = False

    css_df["month"] = css_df["failure_date"].dt.to_period("M").astype("string")
    return css_df


def filter_failure_events(df, station=None, system=None, subsystem=None, year=None, month=None):
    """
    Apply optional filters to failure records.
    """
    filtered_df = df

    if station and station != "All":
        filtered_df = filtered_df[filtered_df["station"] == station]

    if system and system != "All":
        filtered_df = filtered_df[filtered_df["system"] == system]

    if subsystem and subsystem != "All":
        filtered_df = filtered_df[filtered_df["subsystem"] == subsystem]

    if year and year != "All":
        filtered_df = filtered_df[filtered_df["failure_date"].dt.year == int(year)]

    if month and month != "All":
        month_idx = [
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
        ].index(month) + 1
        filtered_df = filtered_df[filtered_df["failure_date"].dt.month == month_idx]

    return filtered_df


def get_common_equipment_options(records_df, failure_df, station=None, system=None, subsystem=None, limit=500):
    """
    Return equipment IDs present in both PM and failure data for the active slice.
    """
    if records_df is None or failure_df is None:
        return []

    pm_slice = filter_records(records_df, station=station, system=system, subsystem=subsystem)
    fail_slice = filter_failure_events(failure_df, station=station, system=system, subsystem=subsystem)

    pm_assets = (
        pm_slice.dropna(subset=["EqpID", "eqkey"])[["EqpID", "eqkey"]]
        .drop_duplicates()
        .sort_values("EqpID")
    )
    fail_keys = set(fail_slice["eqkey"].dropna().unique())
    common = pm_assets[pm_assets["eqkey"].isin(fail_keys)]["EqpID"].dropna().tolist()
    return common[:limit]


def compute_failure_summary(filtered_df):
    """
    Compute operational KPIs for the failure dataset.
    """
    total_failures = len(filtered_df)
    resolved = int(filtered_df["resolved"].sum())
    unresolved = int(total_failures - resolved)
    unique_assets = int(filtered_df["equipment_no"].dropna().nunique())

    avg_resolution_hours = filtered_df["resolution_hours"].dropna().mean()
    avg_resolution_hours = 0.0 if pd.isna(avg_resolution_hours) else float(avg_resolution_hours)

    return {
        "total_failures": total_failures,
        "resolved": resolved,
        "unresolved": unresolved,
        "unique_assets": unique_assets,
        "avg_resolution_hours": round(avg_resolution_hours, 1),
    }


def build_pm_failure_monthly(records_df, failure_df, station=None, system=None, subsystem=None):
    """
    Align PM compliance and failure counts on a monthly grain.
    """
    if records_df is None or records_df.empty or failure_df is None or failure_df.empty:
        return pd.DataFrame()

    pm_slice = filter_records(records_df, station=station, system=system, subsystem=subsystem)
    pm_slice = pm_slice[pm_slice["compliance_status"] != "BASELINE"].copy()
    if pm_slice.empty:
        return pd.DataFrame()

    pm_slice["month"] = pm_slice["done_date"].dt.to_period("M").astype("string")
    pm_monthly = (
        pm_slice.groupby("month", observed=True)
        .agg(
            total_pm=("compliance_status", "count"),
            on_time=("compliance_status", lambda x: (x == "ON_TIME").sum()),
            late_pm=("compliance_status", lambda x: (x == "LATE").sum()),
        )
        .reset_index()
    )
    pm_monthly["compliance_pct"] = (pm_monthly["on_time"] / pm_monthly["total_pm"] * 100).round(1)

    failure_slice = filter_failure_events(failure_df, station=station, system=system, subsystem=subsystem)
    if failure_slice.empty:
        pm_monthly["failure_count"] = 0
        pm_monthly["resolved_failures"] = 0
        pm_monthly["avg_resolution_hours"] = np.nan
        return pm_monthly

    failure_monthly = (
        failure_slice.groupby("month", observed=True)
        .agg(
            failure_count=("failure_code", "size"),
            resolved_failures=("resolved", "sum"),
            avg_resolution_hours=("resolution_hours", "mean"),
        )
        .reset_index()
    )

    monthly = pm_monthly.merge(failure_monthly, on="month", how="left")
    monthly["failure_count"] = monthly["failure_count"].fillna(0).astype(int)
    monthly["resolved_failures"] = monthly["resolved_failures"].fillna(0).astype(int)
    return monthly.sort_values("month")


def build_failure_pm_alignment(records_df, failure_df, station=None, system=None, subsystem=None, limit=250):
    """
    For each failure, find the most recent PM event for the exact same equipment ID.
    """
    if records_df is None or records_df.empty or failure_df is None or failure_df.empty:
        return pd.DataFrame()

    pm_slice = filter_records(records_df, station=station, system=system, subsystem=subsystem).copy()
    pm_slice = pm_slice.dropna(subset=["done_date", "eqkey"])
    if pm_slice.empty:
        return pd.DataFrame()

    failure_slice = filter_failure_events(failure_df, station=station, system=system, subsystem=subsystem).copy()
    failure_slice = failure_slice.dropna(subset=["failure_event_at", "eqkey"])
    if failure_slice.empty:
        return pd.DataFrame()

    if limit:
        failure_slice = failure_slice.sort_values("failure_event_at", ascending=False).head(limit).copy()

    pm_slice = pm_slice.sort_values(["eqkey", "done_date"]).copy()
    failure_slice = failure_slice.sort_values(["eqkey", "failure_event_at"]).copy()

    join_col = "eqkey"
    pm_cols = ["eqkey", "done_date", "schedule_name", "EqpID"]
    pm_cols = ["eqkey", "done_date", "schedule_name", "EqpID", "compliance_status"]

    aligned_parts = []
    for key, failure_group in failure_slice.groupby(join_col, observed=True, dropna=False):
        pm_group = pm_slice[pm_slice["eqkey"] == key][pm_cols]

        failure_group = failure_group.sort_values("failure_event_at")
        if pm_group.empty:
            for col in ["done_date", "schedule_name", "EqpID", "compliance_status"]:
                failure_group[col] = pd.NA
            aligned_parts.append(failure_group)
            continue

        pm_group = pm_group.sort_values("done_date")
        aligned_group = pd.merge_asof(
            failure_group,
            pm_group,
            left_on="failure_event_at",
            right_on="done_date",
            direction="backward",
        )
        aligned_parts.append(aligned_group)

    aligned = pd.concat(aligned_parts, ignore_index=True) if aligned_parts else pd.DataFrame()

    display_cols = [
        "failure_date",
        "station",
        "system",
        "subsystem",
        "equipment_no",
        "error_description",
        "failure_category",
        "done_date",
        "schedule_name",
        "EqpID",
        "compliance_status",
    ]

    aligned = aligned[display_cols].sort_values("failure_date", ascending=False)
    return aligned


def build_equipment_history(records_df, failure_df, equipment_id, limit=200):
    """
    Build a combined PM + failure event timeline for a single equipment ID.
    """
    if records_df is None or records_df.empty or failure_df is None or failure_df.empty or not equipment_id:
        return pd.DataFrame()

    eqkey = _normalize_label(equipment_id)
    if pd.isna(eqkey):
        return pd.DataFrame()
    eqkey = eqkey.replace("-", "").replace(" ", "").replace("/", "").replace("_", "")

    pm_slice = records_df[records_df["eqkey"] == eqkey].copy()
    fail_slice = failure_df[failure_df["eqkey"] == eqkey].copy()

    pm_events = pd.DataFrame(
        {
            "event_at": pm_slice["done_date"],
            "event_type": "PM",
            "station": pm_slice["station"],
            "section": pm_slice["section"],
            "system": pm_slice["system"],
            "subsystem": pm_slice["subsystem"],
            "equipment_id": pm_slice["EqpID"],
            "detail": pm_slice["schedule_name"],
            "status": pm_slice["compliance_status"],
            "owner": pm_slice["done_by"].fillna("Unassigned"),
            "secondary_owner": pd.NA,
            "days_late": pm_slice["days_late"],
            "resolution_hours": pd.NA,
        }
    )

    fail_events = pd.DataFrame(
        {
            "event_at": fail_slice["failure_event_at"],
            "event_type": "FAILURE",
            "station": fail_slice["station"],
            "section": fail_slice["section"],
            "system": fail_slice["system"],
            "subsystem": fail_slice["subsystem"],
            "equipment_id": fail_slice["equipment_no"],
            "detail": fail_slice["error_description"],
            "status": fail_slice["failure_category"],
            "owner": fail_slice["attended_by_display"],
            "secondary_owner": fail_slice["remarks_by_display"],
            "days_late": pd.NA,
            "resolution_hours": fail_slice["resolution_hours"],
        }
    )

    timeline = pd.concat([pm_events, fail_events], ignore_index=True)
    timeline = timeline.dropna(subset=["event_at"]).sort_values("event_at", ascending=False)
    if limit:
        timeline = timeline.head(limit)
    return timeline


def build_equipment_pm_failure_links(records_df, failure_df, station=None, system=None, subsystem=None, limit=200):
    """
    Link each PM event to the next failure on the same equipment where possible.
    """
    if records_df is None or records_df.empty or failure_df is None or failure_df.empty:
        return pd.DataFrame()

    pm_slice = filter_records(records_df, station=station, system=system, subsystem=subsystem).copy()
    fail_slice = filter_failure_events(failure_df, station=station, system=system, subsystem=subsystem).copy()

    pm_slice = pm_slice.dropna(subset=["eqkey", "done_date"])
    fail_slice = fail_slice.dropna(subset=["eqkey", "failure_event_at"])
    common_keys = set(pm_slice["eqkey"].unique()) & set(fail_slice["eqkey"].unique())
    if not common_keys:
        return pd.DataFrame()

    pm_slice = pm_slice[pm_slice["eqkey"].isin(common_keys)].copy()
    fail_slice = fail_slice[fail_slice["eqkey"].isin(common_keys)].copy()
    failure_cols = [
        "eqkey",
        "failure_event_at",
        "equipment_no",
        "error_description",
        "failure_category",
        "attended_by_display",
        "resolution_hours",
        "station",
        "section",
        "system",
        "subsystem",
    ]
    # A single grouped as-of join replaces one full failure-log scan per
    # equipment ID. This keeps the detailed view responsive for large CSS logs.
    linked_df = pd.merge_asof(
        pm_slice.sort_values(["done_date", "eqkey"]),
        fail_slice[failure_cols].sort_values(["failure_event_at", "eqkey"]),
        left_on="done_date",
        right_on="failure_event_at",
        by="eqkey",
        direction="forward",
    )
    linked_df["days_to_next_failure"] = (
        linked_df["failure_event_at"] - linked_df["done_date"]
    ).dt.total_seconds() / 86400.0
    linked_df = linked_df[linked_df["failure_event_at"].notna()].copy()
    linked_df = linked_df.sort_values("days_to_next_failure", ascending=True)

    display_cols = [
        "done_date",
        "EqpID",
        "Eqp_Name",
        "station_x",
        "section_x",
        "system_x",
        "subsystem_x",
        "schedule_name",
        "done_by",
        "failure_event_at",
        "equipment_no",
        "error_description",
        "failure_category",
        "attended_by_display",
        "resolution_hours",
        "days_to_next_failure",
    ]
    linked_df = linked_df[display_cols].rename(
        columns={
            "station_x": "station",
            "section_x": "section",
            "system_x": "system",
            "subsystem_x": "subsystem",
        }
    )
    if limit:
        linked_df = linked_df.head(limit)
    return linked_df


def _safe_pct(numerator, denominator):
    return round(float(numerator) / float(denominator) * 100, 1) if denominator else 0.0


def _extract_question_scope(question_text, pm_df, fail_df):
    q_norm = question_text.upper()

    def extract_value(values):
        cleaned = [str(v).upper() for v in values if pd.notna(v)]
        for value in sorted(set(cleaned), key=len, reverse=True):
            pattern = rf"(?<![A-Z0-9]){re.escape(value)}(?![A-Z0-9])"
            if value and re.search(pattern, q_norm):
                return value
        return None

    scope = {}
    for col in ["station", "section", "system", "subsystem"]:
        pm_values = pm_df[col].dropna().unique() if col in pm_df.columns else []
        fail_values = fail_df[col].dropna().unique() if col in fail_df.columns else []
        scope[col] = extract_value(set(pm_values) | set(fail_values))
    return scope


def _apply_scope(df, scope, column_map=None):
    if df is None or df.empty:
        return pd.DataFrame()

    filtered_df = df
    column_map = column_map or {}
    for key, value in scope.items():
        col = column_map.get(key, key)
        if value and col in filtered_df.columns:
            filtered_df = filtered_df[filtered_df[col].astype("string").str.upper() == value]
    return filtered_df


def _scope_label(scope):
    parts = []
    for label in ["station", "section", "system", "subsystem"]:
        if scope.get(label):
            parts.append(f"{label} {scope[label]}")
    return ", ".join(parts) if parts else "the full network"


def _pm_compliance_by_group(pm_df, group_col, min_pm=20):
    if pm_df is None or pm_df.empty or group_col not in pm_df.columns:
        return pd.DataFrame()

    trackable_df = pm_df[pm_df["compliance_status"] != "BASELINE"].copy()
    if trackable_df.empty:
        return pd.DataFrame()

    grouped = (
        trackable_df.groupby(group_col, observed=True)
        .agg(
            total_pm=("compliance_status", "size"),
            on_time=("compliance_status", lambda x: int((x == "ON_TIME").sum())),
            late=("compliance_status", lambda x: int((x == "LATE").sum())),
            avg_days_late=("days_late", "mean"),
        )
        .reset_index()
    )
    grouped = grouped[grouped["total_pm"] >= min_pm].copy()
    if grouped.empty:
        return grouped

    grouped["compliance_pct"] = grouped.apply(
        lambda row: _safe_pct(row["on_time"], row["total_pm"]),
        axis=1,
    )
    grouped["avg_days_late"] = grouped["avg_days_late"].fillna(0).round(1)
    return grouped


def _failure_by_group(fail_df, group_col):
    if fail_df is None or fail_df.empty or group_col not in fail_df.columns:
        return pd.DataFrame(columns=[group_col, "total_failures", "unresolved", "avg_resolution_hours", "unique_assets"])

    agg_spec = {"total_failures": ("status", "size")}
    if "resolved" in fail_df.columns:
        agg_spec["resolved"] = ("resolved", "sum")
    if "resolution_hours" in fail_df.columns:
        agg_spec["avg_resolution_hours"] = ("resolution_hours", "mean")
    if "equipment_no" in fail_df.columns:
        agg_spec["unique_assets"] = ("equipment_no", "nunique")

    grouped = fail_df.groupby(group_col, observed=True).agg(**agg_spec).reset_index()
    if "resolved" in grouped.columns:
        grouped["unresolved"] = grouped["total_failures"] - grouped["resolved"]
    else:
        grouped["unresolved"] = 0
    if "avg_resolution_hours" not in grouped.columns:
        grouped["avg_resolution_hours"] = 0.0
    if "unique_assets" not in grouped.columns:
        grouped["unique_assets"] = 0
    grouped["avg_resolution_hours"] = grouped["avg_resolution_hours"].fillna(0).round(1)
    return grouped[[group_col, "total_failures", "unresolved", "avg_resolution_hours", "unique_assets"]]


def _format_ranked_rows(df, label_col, fields, limit=5):
    lines = []
    for idx, row in df.head(limit).iterrows():
        details = ", ".join(field(row) for field in fields)
        lines.append(f"{idx + 1}. {row[label_col]}: {details}")
    return "\n".join(lines)


def _safe_person_label(value):
    text = str(value).strip()
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 5:
        return f"Employee ID ending {digits[-4:]}"
    return " ".join(part.capitalize() for part in text.split())


def _employee_key(value):
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _employee_display_name(series):
    labels = series.dropna().astype(str).str.strip()
    if labels.empty:
        return "Unassigned"
    return _safe_person_label(labels.mode().iloc[0])


def _find_employee_match(question_text, employee_keys):
    stop_words = {
        "how",
        "many",
        "late",
        "pm",
        "pms",
        "employee",
        "best",
        "worst",
        "have",
        "has",
        "is",
        "the",
        "for",
        "show",
        "tell",
        "me",
        "performance",
        "effectiveness",
    }
    query_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", (question_text or "").lower())
        if token not in stop_words and len(token) >= 2
    }
    if not query_tokens:
        return None

    best_key = None
    best_overlap = 0
    for key in employee_keys:
        key_tokens = set(str(key).split())
        overlap = len(query_tokens & key_tokens)
        if overlap > best_overlap and overlap >= min(2, len(query_tokens)):
            best_key = key
            best_overlap = overlap
    return best_key


def _urgent_station_answer(pm_df, fail_df):
    pm_station = _pm_compliance_by_group(pm_df, "station", min_pm=20)
    fail_station = _failure_by_group(fail_df, "station")

    if pm_station.empty and fail_station.empty:
        return "I do not have enough station-level PM or failure data loaded to rank urgent stations."

    station_health = pm_station.merge(fail_station, on="station", how="outer").fillna(
        {
            "total_pm": 0,
            "on_time": 0,
            "late": 0,
            "avg_days_late": 0,
            "compliance_pct": 100,
            "total_failures": 0,
            "unresolved": 0,
            "avg_resolution_hours": 0,
            "unique_assets": 0,
        }
    )
    for col in ["total_pm", "on_time", "late", "total_failures", "unresolved", "unique_assets"]:
        station_health[col] = station_health[col].astype(int)

    max_failures = max(float(station_health["total_failures"].max()), 1.0)
    max_unresolved = max(float(station_health["unresolved"].max()), 1.0)
    max_resolution = max(float(station_health["avg_resolution_hours"].max()), 1.0)
    station_health["risk_score"] = (
        (100 - station_health["compliance_pct"].clip(upper=100)) * 0.45
        + (station_health["total_failures"] / max_failures * 35)
        + (station_health["unresolved"] / max_unresolved * 10)
        + (station_health["avg_resolution_hours"] / max_resolution * 10)
    ).round(1)
    station_health = station_health.sort_values(
        ["risk_score", "total_failures", "late"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    lines = _format_ranked_rows(
        station_health,
        "station",
        [
            lambda r: f"risk {r['risk_score']:.1f}",
            lambda r: f"PM compliance {r['compliance_pct']:.1f}% across {int(r['total_pm']):,} PMs",
            lambda r: f"{int(r['late']):,} late PMs",
            lambda r: f"{int(r['total_failures']):,} failures",
        ],
    )
    return (
        "Stations needing urgent attention, ranked by low PM compliance plus failure pressure:\n"
        f"{lines}\n\nRecommended action: start with the first station, then drill into its weakest subsystem and repeated equipment IDs before assigning recovery work."
    )


def _worst_compliance_answer(pm_df, group_col, scope):
    scoped_pm = _apply_scope(pm_df, scope)
    ranked = _pm_compliance_by_group(scoped_pm, group_col, min_pm=20)
    if ranked.empty:
        return f"I do not have enough PM records to rank {group_col} compliance for {_scope_label(scope)}."

    ranked = ranked.sort_values(["compliance_pct", "late"], ascending=[True, False]).reset_index(drop=True)
    lines = _format_ranked_rows(
        ranked,
        group_col,
        [
            lambda r: f"{r['compliance_pct']:.1f}% compliance",
            lambda r: f"{int(r['late']):,} late out of {int(r['total_pm']):,} PMs",
            lambda r: f"average delay {r['avg_days_late']:.1f} days",
        ],
    )
    return f"Worst PM compliance by {group_col} for {_scope_label(scope)}:\n{lines}"


def _failure_hotspot_answer(fail_df, group_col, scope):
    scoped_fail = _apply_scope(fail_df, scope)
    ranked = _failure_by_group(scoped_fail, group_col)
    if ranked.empty:
        return f"No failure records were found for {_scope_label(scope)}."

    ranked = ranked.sort_values(["total_failures", "avg_resolution_hours"], ascending=[False, False]).reset_index(drop=True)
    lines = _format_ranked_rows(
        ranked,
        group_col,
        [
            lambda r: f"{int(r['total_failures']):,} failures",
            lambda r: f"{int(r['unique_assets']):,} affected assets",
            lambda r: f"avg resolution {r['avg_resolution_hours']:.1f} hours",
        ],
    )
    return f"Failure hotspots by {group_col} for {_scope_label(scope)}:\n{lines}"


def _maintenance_gap_answer(classified_failure_df, scope):
    if classified_failure_df is None or classified_failure_df.empty:
        return (
            "Maintenance-gap classification is not loaded yet. Open or run the Failure Analysis data once, "
            "then I can calculate maintenance-gap versus equipment-side failures accurately."
        )

    scoped = _apply_scope(
        classified_failure_df,
        scope,
        column_map={"station": "Station", "system": "System", "subsystem": "SubSystem"},
    )
    if scoped.empty or "failure_label" not in scoped.columns:
        return f"No classified failure records were found for {_scope_label(scope)}."

    total = len(scoped)
    gap = int((scoped["failure_label"] == "Maintenance Gap Failure").sum())
    equipment = int((scoped["failure_label"] == "Equipment Failure").sum())
    no_pm = int((scoped["failure_label"] == "No PM Record").sum())
    return (
        f"For {_scope_label(scope)}, {gap:,} of {total:,} classified failures are maintenance-gap failures "
        f"({_safe_pct(gap, total):.1f}%). Equipment-side failures are {equipment:,} "
        f"({_safe_pct(equipment, total):.1f}%), and {no_pm:,} failures have no prior PM record "
        f"({_safe_pct(no_pm, total):.1f}%)."
    )


FAILURE_REASON_TERMS = (
    "reason",
    "reasons",
    "cause",
    "causes",
    "why",
    "failure mode",
    "failure modes",
    "fault type",
    "error",
    "errors",
    "category",
    "categories",
)

FAILURE_RESOLUTION_TERMS = (
    "resolution",
    "resolve",
    "resolved",
    "repair time",
    "downtime",
    "duration",
    "hours",
)


def _is_failure_reason_question(question_text):
    q_lower = (question_text or "").lower()
    return any(term in q_lower for term in FAILURE_REASON_TERMS) or "top" in q_lower or "most" in q_lower


def _is_failure_resolution_question(question_text):
    q_lower = (question_text or "").lower()
    return any(term in q_lower for term in FAILURE_RESOLUTION_TERMS)


def _failure_reason_answer(fail_df, scope, limit=5):
    scoped_fail = _apply_scope(fail_df, scope)
    if scoped_fail.empty:
        return f"No failures were found for {_scope_label(scope)}."
    if "error_description" not in scoped_fail.columns:
        return "Failure records are loaded, but the error-description lookup is not available."

    total = len(scoped_fail)
    reasons = (
        scoped_fail["error_description"]
        .fillna("UNKNOWN")
        .astype("string")
        .str.strip()
        .replace("", "UNKNOWN")
        .value_counts()
        .head(limit)
    )
    reason_text = ", ".join(
        f"{reason} ({count:,}, {_safe_pct(count, total):.1f}%)"
        for reason, count in reasons.items()
    )

    category_text = ""
    if "failure_category" in scoped_fail.columns:
        categories = (
            scoped_fail["failure_category"]
            .fillna("UNKNOWN")
            .astype("string")
            .str.strip()
            .replace("", "UNKNOWN")
            .value_counts()
            .head(3)
        )
        if not categories.empty:
            category_text = " Main categories: " + ", ".join(
                f"{category} ({count:,}, {_safe_pct(count, total):.1f}%)"
                for category, count in categories.items()
            ) + "."

    return (
        f"Top failure reasons for {_scope_label(scope)} are: {reason_text}."
        f"{category_text}"
    )


def _employee_effectiveness_answer(pm_df, scope, question_text=None):
    scoped_pm = _apply_scope(pm_df, scope)
    if scoped_pm.empty or "done_by" not in scoped_pm.columns:
        return f"I do not have employee-level PM completion data for {_scope_label(scope)}."

    trackable = scoped_pm[(scoped_pm["compliance_status"] != "BASELINE") & scoped_pm["done_by"].notna()].copy()
    trackable = trackable[trackable["done_by"].astype(str).str.upper() != "UNASSIGNED"]
    if trackable.empty:
        return f"No named employee PM records were found for {_scope_label(scope)}."

    trackable["employee_key"] = trackable["done_by"].map(_employee_key)
    trackable = trackable[trackable["employee_key"] != ""]
    if trackable.empty:
        return f"No named employee PM records were found for {_scope_label(scope)}."

    people = (
        trackable.groupby("employee_key", observed=True)
        .agg(
            total_pm=("compliance_status", "size"),
            on_time=("compliance_status", lambda x: int((x == "ON_TIME").sum())),
            late=("compliance_status", lambda x: int((x == "LATE").sum())),
            avg_days_late=("days_late", "mean"),
            display_name=("done_by", _employee_display_name),
        )
        .reset_index()
    )
    people["on_time_pct"] = people.apply(lambda row: _safe_pct(row["on_time"], row["total_pm"]), axis=1)
    people["avg_days_late"] = people["avg_days_late"].fillna(0).round(1)

    matched_employee = _find_employee_match(question_text, people["employee_key"].tolist())
    if matched_employee:
        row = people[people["employee_key"] == matched_employee].iloc[0]
        return (
            f"{row['display_name']} has {int(row['total_pm']):,} trackable PM actions for {_scope_label(scope)}: "
            f"{int(row['on_time']):,} on time and {int(row['late']):,} late. "
            f"On-time rate is {row['on_time_pct']:.1f}%, with average delay {row['avg_days_late']:.1f} days. "
            "This combines spelling and capitalization variants of the same name."
        )

    people = people[people["total_pm"] >= 10].copy()
    if people.empty:
        return "There are employee records, but no employee has at least 10 trackable PM actions in this scope."

    strongest = people.sort_values(["on_time_pct", "total_pm"], ascending=[False, False]).head(3).reset_index(drop=True)
    needs_support = people.sort_values(["on_time_pct", "late"], ascending=[True, False]).head(3).reset_index(drop=True)

    strong_lines = _format_ranked_rows(
        strongest,
        "display_name",
        [lambda r: f"{r['on_time_pct']:.1f}% on-time", lambda r: f"{int(r['total_pm']):,} PMs"],
        limit=3,
    )
    support_lines = _format_ranked_rows(
        needs_support,
        "display_name",
        [lambda r: f"{r['on_time_pct']:.1f}% on-time", lambda r: f"{int(r['late']):,} late PMs"],
        limit=3,
    )
    return (
        f"Employee PM effectiveness for {_scope_label(scope)}:\n"
        f"Strong performers:\n{strong_lines}\n\n"
        f"Needs support or workload review:\n{support_lines}\n\n"
        "Safety note: treat this as an operational workload signal, not a disciplinary score, unless shift allocation, task difficulty, and data quality are reviewed."
    )


def _scope_brief_answer(pm_df, fail_df, scope):
    scoped_pm = _apply_scope(pm_df, scope)
    scoped_fail = _apply_scope(fail_df, scope)
    if scoped_pm.empty and scoped_fail.empty:
        return f"I found {_scope_label(scope)}, but there is not enough PM or failure data loaded for that scope."

    pm_summary = (
        compute_compliance_summary(scoped_pm)
        if not scoped_pm.empty
        else {"total_pm": 0, "compliance_pct": 0.0, "late": 0, "avg_days_late": 0.0}
    )
    fail_summary = (
        compute_failure_summary(scoped_fail)
        if not scoped_fail.empty
        else {"total_failures": 0, "unique_assets": 0, "avg_resolution_hours": 0.0}
    )

    top_failure_text = "No failure mode is available."
    if not scoped_fail.empty and "error_description" in scoped_fail.columns:
        top_modes = scoped_fail["error_description"].fillna("UNKNOWN").value_counts().head(3)
        if not top_modes.empty:
            top_failure_text = ", ".join(f"{name} ({count:,})" for name, count in top_modes.items())

    return (
        f"For {_scope_label(scope)}: PM compliance is {pm_summary['compliance_pct']:.1f}% "
        f"across {pm_summary['total_pm']:,} trackable PMs, with {pm_summary.get('late', 0):,} late PMs. "
        f"There are {fail_summary['total_failures']:,} failures across {fail_summary['unique_assets']:,} assets, "
        f"with average resolution time of {fail_summary['avg_resolution_hours']:.1f} hours. "
        f"Top failure modes: {top_failure_text}."
    )


def _suggest_known_value(question_text, pm_df, fail_df):
    stop_words = {
        "WHAT",
        "ABOUT",
        "WHICH",
        "SHOW",
        "TELL",
        "GIVE",
        "BRIEF",
        "SUMMARY",
        "FAILURE",
        "FAILURES",
        "COMPLIANCE",
        "STATION",
        "SYSTEM",
        "SUBSYSTEM",
        "THE",
        "FOR",
        "IS",
        "ARE",
        "AND",
    }
    tokens = [
        token
        for token in re.findall(r"[A-Z0-9]{3,}", question_text.upper())
        if token not in stop_words
    ]
    if not tokens:
        return None

    candidates = []
    for col in ["station", "section", "system", "subsystem"]:
        values = set()
        if col in pm_df.columns:
            values.update(str(v).upper() for v in pm_df[col].dropna().unique())
        if col in fail_df.columns:
            values.update(str(v).upper() for v in fail_df[col].dropna().unique())
        candidates.extend((value, col) for value in values if value)

    candidate_values = sorted({value for value, _ in candidates})
    for token in tokens:
        matches = difflib.get_close_matches(token, candidate_values, n=1, cutoff=0.74)
        if matches and matches[0] != token:
            match = matches[0]
            match_col = next((col for value, col in candidates if value == match), "item")
            return token, match_col, match
    return None


def _month_name(month_num):
    months = [
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
    return months[month_num - 1] if month_num else None


def _collect_valid_values(*dfs, column):
    values = set()
    for df in dfs:
        if df is not None and not df.empty and column in df.columns:
            values.update(str(value).upper() for value in df[column].dropna().unique())
    return sorted(values)


def resolve_context(current_entities, chat_history):
    resolved = dict(current_entities or {})
    for turn in reversed(chat_history or []):
        previous = turn.get("entities") or {}
        for key in ["station", "subsystem", "year", "month", "equipment"]:
            if resolved.get(key) is None and previous.get(key) is not None:
                resolved[key] = previous[key]
        if resolved.get("comparison_targets") in (None, []):
            previous_targets = previous.get("comparison_targets")
            if previous_targets:
                resolved["comparison_targets"] = previous_targets
        if resolved.get("station") and resolved.get("subsystem"):
            break
    return resolved


def _entities_to_scope(entities):
    return {
        "station": entities.get("station"),
        "section": None,
        "system": None,
        "subsystem": entities.get("subsystem"),
    }


def _with_time_filters(pm_df, fail_df, entities):
    month_name = _month_name(entities.get("month"))
    year = str(entities["year"]) if entities.get("year") else None
    station = entities.get("station")
    subsystem = entities.get("subsystem")
    pm_slice = (
        filter_records(pm_df, station=station, subsystem=subsystem, year=year, month=month_name)
        if pm_df is not None and not pm_df.empty
        else pd.DataFrame()
    )
    fail_slice = (
        filter_failure_events(fail_df, station=station, subsystem=subsystem, year=year, month=month_name)
        if fail_df is not None and not fail_df.empty
        else pd.DataFrame()
    )
    return pm_slice, fail_slice


def _unknown_answer():
    return (
        "I can only answer questions grounded in this DMRC maintenance dashboard. "
        "Try asking about PM compliance, late PMs, failures, maintenance-gap failures, urgent stations, trends, or a station/subsystem summary."
    )


def _trend_answer(pm_df, fail_df, entities):
    month_name = _month_name(entities.get("month"))
    year = str(entities["year"]) if entities.get("year") else None
    relation = build_pm_failure_monthly(
        pm_df,
        fail_df,
        station=entities.get("station"),
        subsystem=entities.get("subsystem"),
    )
    if relation.empty:
        return "No trend data available for that scope.", None
    relation["month_dt"] = pd.to_datetime(relation["month"])
    if year:
        relation = relation[relation["month_dt"].dt.year == int(year)]
    if month_name:
        relation = relation[relation["month_dt"].dt.month == entities["month"]]
    if relation.empty:
        return "No trend data available for that time period.", None

    weakest_pm = relation.sort_values("compliance_pct", ascending=True).iloc[0]
    peak_failures = relation.sort_values("failure_count", ascending=False).iloc[0]
    answer = (
        f"Trend for {_scope_label(_entities_to_scope(entities))}: weakest PM month was {weakest_pm['month']} "
        f"at {weakest_pm['compliance_pct']:.1f}% compliance across {int(weakest_pm['total_pm']):,} PMs. "
        f"Peak failure month was {peak_failures['month']} with {int(peak_failures['failure_count']):,} failures."
    )
    chart_data = {
        "type": "pm_failure_monthly",
        "rows": relation[["month", "compliance_pct", "failure_count", "total_pm"]].to_dict("records"),
    }
    return answer, chart_data


def _comparison_answer(pm_df, fail_df, entities):
    targets = entities.get("comparison_targets") or []
    if len(targets) < 2:
        return "I need two valid stations or two valid subsystems to compare.", None

    target_type = "station" if all(target in set(pm_df.get("station", pd.Series(dtype="string")).dropna().astype(str).str.upper()) for target in targets[:2]) else "subsystem"
    rows = []
    for target in targets[:2]:
        scope = {"station": None, "section": None, "system": None, "subsystem": None}
        scope[target_type] = target
        pm_summary = compute_compliance_summary(_apply_scope(pm_df, scope))
        fail_summary = compute_failure_summary(_apply_scope(fail_df, scope)) if fail_df is not None and not fail_df.empty else {
            "total_failures": 0,
            "avg_resolution_hours": 0.0,
            "unique_assets": 0,
        }
        rows.append((target, pm_summary, fail_summary))

    answer_lines = [
        f"{target}: PM compliance {pm['compliance_pct']:.1f}% across {pm['total_pm']:,} PMs, "
        f"{fail['total_failures']:,} failures, avg resolution {fail['avg_resolution_hours']:.1f} hours."
        for target, pm, fail in rows
    ]
    return "Comparison:\n" + "\n".join(answer_lines), {
        "type": "comparison",
        "target_type": target_type,
        "rows": [
            {
                "target": target,
                "compliance_pct": pm["compliance_pct"],
                "total_pm": pm["total_pm"],
                "total_failures": fail["total_failures"],
            }
            for target, pm, fail in rows
        ],
    }


def _make_answer_result(answer, data_used, intent_info, entities, chart_data=None):
    return {
        "answer": answer,
        "data_used": data_used,
        "intent": intent_info["intent"],
        "entities": entities,
        "confidence": intent_info.get("confidence", 0.0),
        "chart_data": chart_data,
        "is_safe": intent_info.get("is_safe", True),
        "rejection_reason": intent_info.get("rejection_reason"),
    }


def answer_operations_question(
    user_input,
    pm_df,
    pm_agg_df=None,
    failure_df=None,
    classified_df=None,
    chat_history=None,
    classified_failure_df=None,
):
    """
    Data-grounded assistant for operational PM, failure, and employee-effectiveness questions.
    """
    if classified_df is None and classified_failure_df is not None:
        classified_df = classified_failure_df

    q = (user_input or "").strip()
    if not q:
        intent_info = {"intent": "unknown", "confidence": 0.2, "is_safe": True, "rejection_reason": None}
        return _make_answer_result(_unknown_answer(), "none", intent_info, {})

    is_safe, rejection_reason = security_filter(q)
    if not is_safe:
        intent_info = {
            "intent": "unknown",
            "confidence": 1.0,
            "is_safe": False,
            "rejection_reason": rejection_reason,
            "entities": {},
        }
        return _make_answer_result(rejection_reason, "security_filter", intent_info, {})

    pm_df = pm_df if pm_df is not None else pd.DataFrame()
    fail_df = failure_df if failure_df is not None else pd.DataFrame()
    agg_df = pm_agg_df if pm_agg_df is not None else pd.DataFrame()
    valid_stations = _collect_valid_values(pm_df, agg_df, fail_df, column="station")
    valid_subsystems = _collect_valid_values(pm_df, agg_df, fail_df, column="subsystem")
    intent_info = classify_intent(q, valid_stations=valid_stations, valid_subsystems=valid_subsystems)
    employee_keys = []
    if not pm_df.empty and "done_by" in pm_df.columns:
        employee_keys = sorted({_employee_key(value) for value in pm_df["done_by"].dropna().unique() if _employee_key(value)})
    if _find_employee_match(q, employee_keys):
        intent_info["intent"] = "employee_query"
        intent_info["confidence"] = max(intent_info.get("confidence", 0.0), 0.88)

    if not intent_info["is_safe"]:
        return _make_answer_result(
            intent_info["rejection_reason"],
            "security_filter",
            intent_info,
            intent_info.get("entities", {}),
        )

    entities = resolve_context(intent_info.get("entities", {}), chat_history)
    scope = _entities_to_scope(entities)
    intent = intent_info["intent"]

    if intent == "unknown":
        return _make_answer_result(_unknown_answer(), "intent_classifier", intent_info, entities)

    if intent == "urgent_query":
        return _make_answer_result(_urgent_station_answer(pm_df, fail_df), "pm_df + failure_df station risk", intent_info, entities)

    if intent == "employee_query":
        return _make_answer_result(_employee_effectiveness_answer(pm_df, scope, q), "pm_df done_by", intent_info, entities)

    if intent == "failure_classification_query":
        return _make_answer_result(_maintenance_gap_answer(classified_df, scope), "classified_df failure_label", intent_info, entities)

    if intent == "comparison_query":
        answer, chart_data = _comparison_answer(pm_df, fail_df, entities)
        return _make_answer_result(answer, "pm_df + failure_df comparison", intent_info, entities, chart_data)

    if intent == "trend_query":
        answer, chart_data = _trend_answer(pm_df, fail_df, entities)
        return _make_answer_result(answer, "monthly PM/failure trend", intent_info, entities, chart_data)

    if intent == "failure_query":
        scoped_pm, scoped_fail = _with_time_filters(pm_df, fail_df, entities)
        scope_for_label = _entities_to_scope(entities)
        if scoped_fail.empty:
            answer = f"No failures were found for {_scope_label(scope_for_label)}."
        elif _is_failure_reason_question(q):
            answer = _failure_reason_answer(scoped_fail, scope_for_label)
        elif _is_failure_resolution_question(q):
            fail_summary = compute_failure_summary(scoped_fail)
            answer = (
                f"Average resolution time for {_scope_label(scope_for_label)} is "
                f"{fail_summary['avg_resolution_hours']:.1f} hours across "
                f"{fail_summary['total_failures']:,} failures."
            )
        else:
            fail_summary = compute_failure_summary(scoped_fail)
            answer = (
                f"There were {fail_summary['total_failures']:,} failures for {_scope_label(scope_for_label)}, "
                f"across {fail_summary['unique_assets']:,} assets, with average resolution time "
                f"{fail_summary['avg_resolution_hours']:.1f} hours."
            )
        return _make_answer_result(answer, "failure_df from css.csv + errors.csv", intent_info, entities)

    if intent == "compliance_query":
        scoped_pm, _ = _with_time_filters(pm_df, fail_df, entities)
        pm_summary = compute_compliance_summary(scoped_pm) if not scoped_pm.empty else {"compliance_pct": 0.0, "total_pm": 0, "late": 0}
        answer = (
            f"PM compliance is {pm_summary['compliance_pct']:.1f}% across "
            f"{pm_summary['total_pm']:,} trackable PM actions for {_scope_label(scope)}. "
            f"Late PM count is {pm_summary.get('late', 0):,}."
        )
        return _make_answer_result(answer, "pm_df compliance_status", intent_info, entities)

    if intent == "station_query" or intent == "subsystem_query" or intent == "summary_query":
        return _make_answer_result(_scope_brief_answer(pm_df, fail_df, scope), "pm_df + failure_df summary", intent_info, entities)

    return _make_answer_result(_unknown_answer(), "intent_classifier", intent_info, entities)
