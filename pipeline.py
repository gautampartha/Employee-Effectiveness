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
    else:
        on_time = 0
        late = 0
        compliance_pct = 0.0
        # If there are no trackable records, average days late is N/A or 0.0
        avg_days_late = 0.0
        
    return {
        'total_pm': total_pm,
        'on_time': on_time,
        'late': late,
        'compliance_pct': round(compliance_pct, 1),
        'avg_days_late': round(avg_days_late, 1)
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

def answer_operations_question(question, records_df, failure_df):
    """
    Lightweight rule-based assistant for operational count questions.
    Adapted to work with enhanced failure data that includes error descriptions.
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

    # Extract filter values from question
    station = extract_value(set(pm_df.get("station", pd.Series(dtype="string")).dropna().unique()) | set(fail_df.get("station", pd.Series(dtype="string")).dropna().unique()))
    section = extract_value(set(pm_df.get("section", pd.Series(dtype="string")).dropna().unique()) | set(fail_df.get("section", pd.Series(dtype="string")).dropna().unique()))
    system = extract_value(set(pm_df.get("system", pd.Series(dtype="string")).dropna().unique()) | set(fail_df.get("system", pd.Series(dtype="string")).dropna().unique()))
    subsystem = extract_value(set(pm_df.get("subsystem", pd.Series(dtype="string")).dropna().unique()) | set(fail_df.get("subsystem", pd.Series(dtype="string")).dropna().unique()))

    # Apply filters to both dataframes
    scoped_pm = pm_df.copy()
    scoped_fail = fail_df.copy()
    for col, value in [("station", station), ("section", section), ("system", system), ("subsystem", subsystem)]:
        if value and col in scoped_pm.columns:
            scoped_pm = scoped_pm[scoped_pm[col] == value]
        if value and col in scoped_fail.columns:
            scoped_fail = scoped_fail[scoped_fail[col] == value]

    # Handle different question types
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
        parts = [f"{idx} ({val:,})" for idx, val in top.items()]
        return "Top failure modes are: " + ", ".join(parts) + "."

    if "WHICH SUBSYSTEM" in q_norm or "MOST FAILURE-PRONE" in q_norm:
        if scoped_fail.empty:
            return "No failures were found in the requested scope."
        if "subsystem" in scoped_fail.columns:
            top = scoped_fail["subsystem"].value_counts().head(1)
            return f"The most failure-prone subsystem is {top.index[0]} with {int(top.iloc[0]):,} failures."
        else:
            return "Subsystem data not available for analysis."

    return "I can answer count-style questions about failures, PM actions, compliance, and top failure modes by station, section, system, or subsystem."
