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
