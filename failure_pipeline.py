import pandas as pd
import numpy as np
import streamlit as st
from pathlib import Path

# --- Helper functions for normalization (based on teammate's version) ---
def _normalize_text(value):
    """Normalize text for consistent matching."""
    if pd.isna(value):
        return ""
    return str(value).strip().upper()

def _normalize_label(value):
    """Normalize label/text for consistent matching."""
    if pd.isna(value):
        return ""
    return str(value).strip()

def _normalize_person_series(primary_series, fallback_series=None):
    """Normalize person names, using fallback if primary is missing."""
    if primary_series is not None:
        primary = primary_series.fillna("").astype(str).str.strip()
        if fallback_series is not None:
            fallback = fallback_series.fillna("").astype(str).str.strip()
            return primary.where(primary != "", fallback)
        return primary
    elif fallback_series is not None:
        return fallback_series.fillna("").astype(str).str.strip()
    else:
        return pd.Series("", index=primary_series.index if primary_series is not None else None)

@st.cache_data
def load_failures():
    """
    Load the failure log from css.csv, enrich with error descriptions from errors.csv,
    normalize System/SubSystem, parse dates, filter for resolved failures (Status==2.0),
    and cap Duration at 9999 for display (but keep original for filtering).
    """
    # Define paths
    BASE_DIR = Path(__file__).resolve().parent
    FAILURE_LOG_PATH = BASE_DIR / "css.csv"
    ERROR_LOOKUP_PATH = BASE_DIR / "errors.csv"
    
    # Check if files exist
    if not FAILURE_LOG_PATH.exists():
        raise FileNotFoundError(f"Failure log not found: {FAILURE_LOG_PATH}")
    if not ERROR_LOOKUP_PATH.exists():
        # If errors.csv doesn't exist, fall back to original behavior but standardize column names
        df = pd.read_csv(FAILURE_LOG_PATH, on_bad_lines='skip', engine='python')
        # Rename columns to match the expected names used downstream
        df = df.rename(columns={
            "Date": "failure_date",
            "Line": "line",
            "Sec": "section",
            "Station": "station",
            "LocationGroup": "location_group",
            "System": "system",
            "SubSystem": "subsystem",
            "EquipmentNo": "equipment_no",
            "otherEqptNo": "other_eqpt_no",
            "SubEquipment": "sub_equipment",
            "Make": "make",
            "SwVersion": "sw_version",
            "Direction": "direction",
            "FailureTime": "failure_time",
            "FailureDescription": "failure_code_raw",
            "Failure_Detail": "failure_detail",
            "Status": "status",
            "FailureCategory": "failure_category_raw",
            "FailureType": "failure_type_raw",
            "RectificationTime": "rectification_time",
            "RectificationDate": "rectification_date",
            "Duration": "duration_raw",
            "UploadPic": "upload_pic",
            "ActionTaken": "action_taken",
            "Remarks": "remarks",
            "Remark_Status": "remark_status",
            "Origin": "origin",
            "Attendedby": "attended_by",
            "Remarksby": "remarks_by",
            "root_cause_analysis": "root_cause_analysis",
            "sendSms": "send_sms",
            "Send_Whatsapp": "send_whatsapp",
            "RemarksByName": "remarks_by_name",
            "AttendedByName": "attended_by_name",
            "CreatedBy": "created_by",
            "AddDate": "add_date",
            "UpdateDate": "update_date",
            "UpdateBy": "update_by",
            "UpdateIP": "update_ip",
            "Log": "log"
        })
        # Convert date and time columns
        df["failure_date"] = pd.to_datetime(df["failure_date"], errors="coerce")
        df["failure_time"] = pd.to_datetime(df["failure_time"], errors="coerce")
        df["rectification_date"] = pd.to_datetime(df["rectification_date"], errors="coerce")
        df["rectification_time"] = pd.to_datetime(df["rectification_time"], errors="coerce")
        # Convert failure code to numeric
        df["failure_code"] = pd.to_numeric(df["failure_code_raw"], errors="coerce").astype("Int64")
    else:
        # Load with specific columns as in teammate's version
        css_cols = [
            "Date",
            "Line",
            "Sec",
            "Station",
            "LocationGroup",
            "System",
            "SubSystem",
            "EquipmentNo",
            "otherEqptNo",
            "SubEquipment",
            "Make",
            "SwVersion",
            "Direction",
            "FailureTime",
            "FailureDescription",
            "Failure_Detail",
            "Status",
            "FailureCategory",
            "FailureType",
            "RectificationTime",
            "RectificationDate",
            "Duration",
            "UploadPic",
            "ActionTaken",
            "Remarks",
            "Remark_Status",
            "Origin",
            "Attendedby",
            "Remarksby",
            "root_cause_analysis",
            "sendSms",
            "Send_Whatsapp",
            "RemarksByName",
            "AttendedByName",
            "CreatedBy",
            "AddDate",
            "UpdateDate",
            "UpdateBy",
            "UpdateIP",
            "Log"
        ]
        
        df = pd.read_csv(
            FAILURE_LOG_PATH,
            usecols=css_cols,
            on_bad_lines='skip',
            engine='python',
            dtype="string",
        )
        
        # Load error lookup
        errors_df = pd.read_csv(
            ERROR_LOOKUP_PATH,
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
        
        # Rename columns to match teammate's convention for easier processing
        df = df.rename(
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
                "sendSms": "send_sms",
                "Send_Whatsapp": "send_whatsapp",
                "CreatedBy": "created_by",
                "AddDate": "add_date",
                "UpdateDate": "update_date",
                "UpdateBy": "update_by",
                "UpdateIP": "update_ip",
                "Log": "log"
            }
        )
        
        # Convert date and time columns
        df["failure_date"] = pd.to_datetime(df["failure_date"], errors="coerce")
        df["failure_time"] = pd.to_datetime(df["failure_time"], errors="coerce")
        df["rectification_date"] = pd.to_datetime(df["rectification_date"], errors="coerce")
        df["rectification_time"] = pd.to_datetime(df["rectification_time"], errors="coerce")
        
        # Convert failure code to numeric
        df["failure_code"] = pd.to_numeric(df["failure_code_raw"], errors="coerce").astype("Int64")
        
        # Normalize text columns (similar to teammate's approach)
        for col in ["station", "system", "subsystem", "line", "section"]:
            df[col] = df[col].map(_normalize_label)
        
        for col in ["equipment_no", "failure_detail", "action_taken", "origin", "root_cause_analysis",
                   "failure_code_raw"]:
            df[col] = df[col].map(_normalize_text)
        
        # Normalize person names
        df["attended_by_display"] = _normalize_person_series(
            df["attended_by_name"], df["attended_by"]
        )
        df["remarks_by_display"] = _normalize_person_series(
            df["remarks_by_name"], df["remarks_by"]
        )
        
        # Process error lookup similar to teammate's version
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
        
        # Merge with error lookup
        df = df.merge(errors_df, on="failure_code", how="left")
        
        # Create normalized versions for mapping confidence calculation
        df["mapped_eqp_type_norm"] = df["mapped_eqp_type"].map(_normalize_label)
        
        # Create error_description (prefer master description, fallback to detail)
        df["error_description"] = df["error_description_master"].fillna(df["failure_detail"])
        
        # Create failure_category (prefer master category, fallback to raw)
        df["failure_category"] = df["error_category_master"].fillna(df["failure_category_raw"])
        df["failure_category"] = df["failure_category"].map(_normalize_text)
        
        # Calculate mapping confidence (simplified version)
        df["mapping_confidence"] = "LOOKUP_ONLY"
        exact_match = df["subsystem"] == df["mapped_eqp_type_norm"]
        family_match = (
            df["subsystem"].fillna("").str.contains(df["mapped_eqp_type_norm"].fillna(""), regex=False)
            | df["mapped_eqp_type_norm"].fillna("").str.contains(df["subsystem"].fillna(""), regex=False)
        )
        system_level_match = (
            ((df["mapped_eqp_type_norm"] == "ALL AFC") & (df["system"] == "AFC"))
            | ((df["mapped_eqp_type_norm"] == "ALL TELECOM") & (df["system"] == "TELECOM"))
        )
        df.loc[exact_match, "mapping_confidence"] = "EXACT_SUBSYSTEM_MATCH"
        df.loc[~exact_match & family_match, "mapping_confidence"] = "FAMILY_MATCH"
        df.loc[~exact_match & ~family_match & system_level_match, "mapping_confidence"] = "SYSTEM_LEVEL_MATCH"
        df.loc[df["failure_code"].isna(), "mapping_confidence"] = "UNMAPPED"
        
        # Create failure_event_at and resolved flags
        df["failure_event_at"] = df["failure_time"].fillna(df["failure_date"])
        df["resolved"] = df["rectification_date"].notna()
        
        # Create eqkey for equipment matching (similar to teammate's version)
        df["eqkey"] = df["equipment_no"].map(_normalize_label).str.replace(r"[^A-Z0-9]+", "", regex=True)
        
        # Calculate resolution hours
        duration_hours = pd.to_numeric(df["duration_raw"], errors="coerce") / 3600.0
        timestamp_hours = (
            df["rectification_date"] - df["failure_event_at"]
        ).dt.total_seconds() / 3600.0
        df["resolution_hours"] = timestamp_hours.where(timestamp_hours > 0, duration_hours)

    # Ensure we have a 'status' column (standardized)
    if 'Status' in df.columns:
        df = df.rename(columns={'Status': 'status'})
    # Keep only resolved failures (Status == 2) - ORIGINAL BEHAVIOR
    # Status may be numeric or string; convert to numeric for comparison
    df = df[pd.to_numeric(df['status'], errors='coerce') == 2.0].copy()
    
    # Normalize duration once so all downstream comparisons/aggregations stay numeric.
    df["duration_raw"] = pd.to_numeric(df["duration_raw"], errors="coerce")

    # Cap Duration at 9999 for display - ORIGINAL BEHAVIOR
    df['duration_capped'] = df['duration_raw'].clip(upper=9999)
    
    # NOW RESTORE THE ORIGINAL COLUMN NAMES THAT THE USER'S CODE EXPECTS
    # The user's existing code expects: System, SubSystem, Station, Date, etc. (with specific casing)
    df['System'] = df['system']
    df['SubSystem'] = df['subsystem']
    df['Station'] = df['station']
    df['Date'] = df['failure_date']
    # Also restore the original Duration column for compatibility with app.py
    df['Duration'] = df['duration_capped']
    # Keep original column names from css.csv as well for compatibility
    # The user's code references columns like 'FailureDescription' - let's keep the originals

    # Ensure date columns are datetime (important for merge_asof)
    for col in ["failure_date", "failure_time", "rectification_date", "rectification_time"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    return df

@st.cache_data
def load_pm_records():
    """
    Load PM records from pm_records_clean.csv and normalize station/system/subsystem.
    """
    df = pd.read_csv('pm_records_clean.csv')

    # Normalize station, system, subsystem
    df['station'] = df['station'].astype(str).str.strip().str.upper()
    df['system'] = df['system'].astype(str).str.strip().str.upper()
    df['subsystem'] = df['subsystem'].astype(str).str.strip().str.upper()

    # Parse done_date
    df['done_date'] = pd.to_datetime(df['done_date'], errors='coerce')

    return df

def classify_failures(failures_df, pm_df):
    """
    For each failure record, find the most recent PM record for the same
    station+subsystem where done_date <= failure Date.

    Returns failures_df with two new columns added:
      - failure_label: "Maintenance Gap Failure", "Equipment Failure", or "No PM Record"
      - last_pm_compliance: compliance_status of the most recent PM before this failure
    """
    # Work on a copy to avoid modifying the original
    failures_df = failures_df.copy()
    # Add a column to preserve original index (which may have gaps after filtering)
    failures_df['_orig_idx'] = failures_df.index

    # Prepare failures dataframe for merge_asof: we need station, subsystem, Date, and _orig_idx
    failures_for_merge = failures_df[['Station', 'SubSystem', 'Date', '_orig_idx']].copy()
    failures_for_merge = failures_for_merge.rename(
        columns={'Station': 'station', 'SubSystem': 'subsystem', 'Date': 'failure_date'}
    )
    failures_for_merge = failures_for_merge.sort_values('failure_date')

    # Prepare PM dataframe for merge_asof: we need station, subsystem, done_date, compliance_status, days_late
    pm_for_merge = pm_df[['station', 'subsystem', 'done_date', 'compliance_status', 'days_late']].copy()
    pm_for_merge = pm_for_merge.sort_values('done_date')

    # Perform merge_asof on station+subsystem and done_date <= failure_date
    merged = pd.merge_asof(
        failures_for_merge,
        pm_for_merge,
        by=['station', 'subsystem'],
        left_on='failure_date',
        right_on='done_date',
        direction='backward'
    )

    # Initialize new columns with default values
    failures_df['failure_label'] = 'No PM Record'
    failures_df['last_pm_compliance'] = None  # This sets dtype to object

    # Identify rows where we found a PM record (i.e., done_date is not NaN)
    has_pm = merged['done_date'].notna()
    if has_pm.any():
        # Get the original indices for rows with a PM match
        idx_with_pm = merged.loc[has_pm, '_orig_idx']
        # Get compliance_status and days_late for those rows
        pm_compliance = merged.loc[has_pm, 'compliance_status']
        pm_days_late = merged.loc[has_pm, 'days_late']

        # Determine which are Maintenance Gap Failure: compliance_status == 'late' OR days_late > 3
        maintenance_gap_condition = (pm_compliance == 'late') | (pm_days_late > 3)

        # Assign failure_label based on condition
        # Where condition is True -> Maintenance Gap Failure, else -> Equipment Failure
        failure_label_values = np.where(
            maintenance_gap_condition,
            'Maintenance Gap Failure',
            'Equipment Failure'
        )
        # Assign to the original dataframe using the original indices
        failures_df.loc[idx_with_pm, 'failure_label'] = failure_label_values
        # Assign last_pm_compliance
        failures_df.loc[idx_with_pm, 'last_pm_compliance'] = pm_compliance.values

    # Drop the helper column
    failures_df = failures_df.drop(columns=['_orig_idx'])

    return failures_df

def get_failure_summary(classified_df):
    """
    Aggregate by station+subsystem to get summary statistics.

    Returns a DataFrame with columns:
      - Station
      - SubSystem
      - total_failures
      - maintenance_gap_count
      - maintenance_gap_pct
      - equipment_failure_count
      - equipment_failure_pct
      - no_pm_record_count
      - avg_resolution_minutes (mean Duration where Duration <= 9999)
      - avg_resolution_hours (avg_resolution_minutes / 60)
    """
    # We'll work with a copy to avoid SettingWithCopyWarning
    df = classified_df.copy()

    # For average resolution time, we want to exclude Duration > 9999
    # Note: In the enhanced version, we have 'duration_raw' and 'duration_capped'
    # Use duration_capped for consistency with original behavior
    valid_duration_mask = df['duration_capped'] <= 9999

    # Group by station and subsystem
    grouped = df.groupby(['Station', 'SubSystem'])

    # Aggregate
    summary = grouped.agg(
        total_failures=('failure_label', 'size'),  # count of rows
        maintenance_gap_count=('failure_label', lambda x: (x == 'Maintenance Gap Failure').sum()),
        equipment_failure_count=('failure_label', lambda x: (x == 'Equipment Failure').sum()),
        no_pm_record_count=('failure_label', lambda x: (x == 'No PM Record').sum()),
        # For average resolution time, we take the mean of Duration where valid, else NaN
        avg_resolution_minutes=('duration_capped', lambda x: x[valid_duration_mask.loc[x.index]].mean() if valid_duration_mask.loc[x.index].any() else None)
    ).reset_index()

    # Calculate percentages
    total = summary['total_failures']
    # Avoid division by zero
    summary['maintenance_gap_pct'] = (summary['maintenance_gap_count'] / total * 100).fillna(0).round(1)
    summary['equipment_failure_pct'] = (summary['equipment_failure_count'] / total * 100).fillna(0).round(1)

    # Convert avg_resolution_minutes to hours and round to 1 decimal for display later
    summary['avg_resolution_hours'] = (summary['avg_resolution_minutes'] / 60).round(1)

    # Reorder columns for clarity
    summary = summary[[
        'Station', 'SubSystem',
        'total_failures',
        'maintenance_gap_count', 'maintenance_gap_pct',
        'equipment_failure_count', 'equipment_failure_pct',
        'no_pm_record_count',
        'avg_resolution_minutes', 'avg_resolution_hours'
    ]]

    return summary
