<<<<<<< HEAD
import pandas as pd
import numpy as np

def load_records_clean(filepath):
    """
    Loads the record-level PM data efficiently.
    Only loads the columns required for the dashboard and optimizes memory
    by using 'category' data types for low-cardinality string columns.
    """
    # Load only columns that we actually need to display or filter
    cols_to_use = [
        'EqpID', 'Eqp_Name', 'station', 'system', 'subsystem', 
        'schedule_name', 'done_date', 'expected_due_date', 
        'days_late', 'compliance_status'
    ]
    
    # Define memory-efficient data types
    dtypes = {
        'EqpID': 'category',
        'Eqp_Name': 'string',
        'station': 'category',
        'system': 'category',
        'subsystem': 'category',
        'schedule_name': 'category',
        'compliance_status': 'category',
        'days_late': 'float32'  # Float to handle missing values (NaN) for baseline rows
    }
    
    # Read the CSV with optimized settings
    df = pd.read_csv(filepath, usecols=cols_to_use, dtype=dtypes)
    
    # Parse dates explicitly
    df['done_date'] = pd.to_datetime(df['done_date'], errors='coerce')
    df['expected_due_date'] = pd.to_datetime(df['expected_due_date'], errors='coerce')
    
    return df

def load_compliance_agg(filepath):
    """
    Loads the pre-aggregated compliance rollup file.
    """
    dtypes = {
        'station': 'category',
        'system': 'category',
        'subsystem': 'category',
        'schedule_name': 'category',
        'total_pm': 'int32',
        'on_time': 'int32',
        'late': 'int32',
        'avg_days_late': 'float32',
        'compliance_pct': 'float32'
    }
    return pd.read_csv(filepath, dtype=dtypes)

def filter_records(df, station=None, system=None, subsystem=None, schedule_name=None, year=None, month=None):
    """
    Applies any combination of active filters to the PM records DataFrame.
    Filters are ignored if they are None, empty, or set to 'All'.
    """
    filtered_df = df
    
    # Apply category/string filters
    if station and station != "All":
        filtered_df = filtered_df[filtered_df['station'] == station]
        
    if system and system != "All":
        filtered_df = filtered_df[filtered_df['system'] == system]
        
    if subsystem and subsystem != "All":
        filtered_df = filtered_df[filtered_df['subsystem'] == subsystem]
        
    if schedule_name and schedule_name != "All":
        filtered_df = filtered_df[filtered_df['schedule_name'] == schedule_name]
        
    # Apply Year filter
    if year and year != "All":
        filtered_df = filtered_df[filtered_df['done_date'].dt.year == int(year)]
        
    # Apply Month filter
    if month and month != "All":
        months_list = ["January", "February", "March", "April", "May", "June", 
                       "July", "August", "September", "October", "November", "December"]
        month_idx = months_list.index(month) + 1
        filtered_df = filtered_df[filtered_df['done_date'].dt.month == month_idx]
        
    return filtered_df

def compute_compliance_summary(filtered_df):
    """
    Computes key performance indicators (KPIs) for the passed subset.
    Excludes 'baseline' records from all compliance calculations, as they
    do not have a prior record to compare expected due date against.
    """
    # Filter out baseline records for metric evaluation
    trackable_df = filtered_df[filtered_df['compliance_status'] != 'baseline']
    
    total_pm = len(trackable_df)
    
    if total_pm > 0:
        on_time = int((trackable_df['compliance_status'] == 'on_time').sum())
        late = int((trackable_df['compliance_status'] == 'late').sum())
        compliance_pct = float((on_time / total_pm) * 100)
        avg_days_late = float(trackable_df['days_late'].mean())
=======
from pathlib import Path

import numpy as np
import pandas as pd


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
>>>>>>> origin/main
    else:
        on_time = 0
        late = 0
        compliance_pct = 0.0
<<<<<<< HEAD
        # If there are no trackable records, average days late is N/A or 0.0
        avg_days_late = 0.0
        
    return {
        'total_pm': total_pm,
        'on_time': on_time,
        'late': late,
        'compliance_pct': round(compliance_pct, 1),
        'avg_days_late': round(avg_days_late, 1)
    }

=======
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


>>>>>>> origin/main
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

<<<<<<< HEAD
def answer_operations_question(question, records_df, failure_df):
    """
    Lightweight rule-based assistant for operational count questions.
    Adapted to work with enhanced failure data that includes error descriptions.
=======

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
    family_match = (
        css_df["subsystem"].fillna("").str.contains(css_df["mapped_eqp_type_norm"].fillna(""), regex=False)
        | css_df["mapped_eqp_type_norm"].fillna("").str.contains(css_df["subsystem"].fillna(""), regex=False)
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
    fail_slice = fail_slice.sort_values(["eqkey", "failure_event_at"])

    linked_parts = []
    for eqkey, pm_group in pm_slice.groupby("eqkey", observed=True):
        fail_group = fail_slice[fail_slice["eqkey"] == eqkey]
        if fail_group.empty:
            continue
        pm_group = pm_group.sort_values("done_date").copy()
        linked = pd.merge_asof(
            pm_group,
            fail_group[
                [
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
                    "eqkey",
                ]
            ].sort_values("failure_event_at"),
            left_on="done_date",
            right_on="failure_event_at",
            direction="forward",
        )
        linked_parts.append(linked)

    if not linked_parts:
        return pd.DataFrame()

    linked_df = pd.concat(linked_parts, ignore_index=True)
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


def answer_operations_question(question, records_df, failure_df):
    """
    Lightweight rule-based assistant for operational count questions.
>>>>>>> origin/main
    """
    q = (question or "").strip()
    if not q:
        return "Ask something like: how many failures were there at RJBH, what is the PM compliance for AFC GATE, or which subsystem has the most failures."

    q_norm = q.upper()
    pm_df = records_df if records_df is not None else pd.DataFrame()
    fail_df = failure_df if failure_df is not None else pd.DataFrame()

    def extract_value(values):
        for value in sorted([v for v in values if pd.notna(v)], key=len, reverse=True):
            if str(value) in q_norm:
                return str(value)
        return None

<<<<<<< HEAD
    # Extract filter values from question
=======
>>>>>>> origin/main
    station = extract_value(set(pm_df.get("station", pd.Series(dtype="string")).dropna().unique()) | set(fail_df.get("station", pd.Series(dtype="string")).dropna().unique()))
    section = extract_value(set(pm_df.get("section", pd.Series(dtype="string")).dropna().unique()) | set(fail_df.get("section", pd.Series(dtype="string")).dropna().unique()))
    system = extract_value(set(pm_df.get("system", pd.Series(dtype="string")).dropna().unique()) | set(fail_df.get("system", pd.Series(dtype="string")).dropna().unique()))
    subsystem = extract_value(set(pm_df.get("subsystem", pd.Series(dtype="string")).dropna().unique()) | set(fail_df.get("subsystem", pd.Series(dtype="string")).dropna().unique()))

<<<<<<< HEAD
    # Apply filters to both dataframes
    scoped_pm = pm_df.copy()
    scoped_fail = fail_df.copy()
=======
    scoped_pm = pm_df
    scoped_fail = fail_df
>>>>>>> origin/main
    for col, value in [("station", station), ("section", section), ("system", system), ("subsystem", subsystem)]:
        if value and col in scoped_pm.columns:
            scoped_pm = scoped_pm[scoped_pm[col] == value]
        if value and col in scoped_fail.columns:
            scoped_fail = scoped_fail[scoped_fail[col] == value]

<<<<<<< HEAD
    # Handle different question types
=======
>>>>>>> origin/main
    if "HOW MANY FAIL" in q_norm or "NUMBER OF FAIL" in q_norm or "FAILURES" in q_norm:
        return f"There were {len(scoped_fail):,} failures in the requested scope."

    if "HOW MANY PM" in q_norm or "NUMBER OF PM" in q_norm or "PM ACTION" in q_norm:
        pm_summary = compute_compliance_summary(scoped_pm) if not scoped_pm.empty else {"total_pm": 0}
        return f"There were {pm_summary['total_pm']:,} trackable PM actions in the requested scope."

    if "COMPLIANCE" in q_norm:
        pm_summary = compute_compliance_summary(scoped_pm) if not scoped_pm.empty else {"compliance_pct": 0.0, "total_pm": 0}
        return f"PM compliance is {pm_summary['compliance_pct']:.1f}% across {pm_summary['total_pm']:,} trackable PM actions in the requested scope."

    if "TOP FAILURE" in q_norm or "MOST FAILURE" in q_norm:
        if scoped_fail.empty:
            return "No failures were found in the requested scope."
<<<<<<< HEAD
        # Use error_description for failure modes
        error_col = "error_description" if "error_description" in scoped_fail.columns else "failure_detail"
        if error_col not in scoped_fail.columns:
            # Fallback to any available text column
            text_cols = [c for c in scoped_fail.columns if scoped_fail[c].dtype == 'object']
            if text_cols:
                error_col = text_cols[0]
            else:
                return "Failure reason data not available for analysis."
        top = scoped_fail[error_col].fillna("UNKNOWN").value_counts().head(3)
=======
        top = scoped_fail["error_description"].fillna("UNKNOWN").value_counts().head(3)
>>>>>>> origin/main
        parts = [f"{idx} ({val:,})" for idx, val in top.items()]
        return "Top failure modes are: " + ", ".join(parts) + "."

    if "WHICH SUBSYSTEM" in q_norm or "MOST FAILURE-PRONE" in q_norm:
        if scoped_fail.empty:
            return "No failures were found in the requested scope."
<<<<<<< HEAD
        if "subsystem" in scoped_fail.columns:
            top = scoped_fail["subsystem"].value_counts().head(1)
            return f"The most failure-prone subsystem is {top.index[0]} with {int(top.iloc[0]):,} failures."
        else:
            return "Subsystem data not available for analysis."
=======
        top = scoped_fail["subsystem"].value_counts().head(1)
        return f"The most failure-prone subsystem is {top.index[0]} with {int(top.iloc[0]):,} failures."
>>>>>>> origin/main

    return "I can answer count-style questions about failures, PM actions, compliance, and top failure modes by station, section, system, or subsystem."
