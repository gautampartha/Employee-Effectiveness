# Database Setup

The dashboard now reads through `data_source.py`.

By default it uses the existing CSV files:

```bash
DMRC_DATA_SOURCE=csv
```

To switch the dashboard to MySQL later, install the requirements and start the app with:

```bash
export DMRC_DATA_SOURCE=mysql
export DMRC_MYSQL_URL='mysql+pymysql://user:password@host:3306/database_name'
streamlit run app.py
```

The default MySQL table names match the current CSV file names:

```bash
export DMRC_MYSQL_PM_RECORDS_TABLE=pm_records_clean
export DMRC_MYSQL_PM_AGG_TABLE=pm_compliance_agg
export DMRC_MYSQL_FAILURE_LOG_TABLE=css
export DMRC_MYSQL_ERROR_LOOKUP_TABLE=errors
```

If the live database has different table or column names, use SQL queries that alias the output columns to the dashboard schema:

```bash
export DMRC_MYSQL_PM_RECORDS_QUERY='SELECT equipment_id AS EqpID, equipment_name AS Eqp_Name, station, section, system, subsystem, schedule_name, done_date, done_by, expected_due_date, days_late, compliance_status FROM live_pm_records'
export DMRC_MYSQL_PM_AGG_QUERY='SELECT station, system, subsystem, schedule_name, total_pm, on_time, late, avg_days_late, compliance_pct FROM live_pm_compliance'
export DMRC_MYSQL_FAILURE_LOG_QUERY='SELECT Date, Line, Sec, Station, System, SubSystem, EquipmentNo, FailureTime, FailureDescription, Failure_Detail, Status, FailureCategory, FailureType, RectificationTime, RectificationDate, Duration, ActionTaken, Origin, Attendedby, Remarksby, AttendedByName, RemarksByName, root_cause_analysis FROM live_failures'
export DMRC_MYSQL_ERROR_LOOKUP_QUERY='SELECT id, eqp_type_name, failure_cat, code, description, ErrorGroup, Status FROM live_error_lookup'
```

## Required Schemas

PM records must provide:

```text
EqpID, Eqp_Name, station, section, system, subsystem, schedule_name,
done_date, done_by, expected_due_date, days_late, compliance_status
```

PM aggregate must provide:

```text
station, system, subsystem, schedule_name, total_pm, on_time, late,
avg_days_late, compliance_pct
```

Failure log must provide:

```text
Date, Line, Sec, Station, System, SubSystem, EquipmentNo, FailureTime,
FailureDescription, Failure_Detail, Status, FailureCategory, FailureType,
RectificationTime, RectificationDate, Duration, ActionTaken, Origin,
Attendedby, Remarksby, AttendedByName, RemarksByName, root_cause_analysis
```

Error lookup must provide:

```text
id, eqp_type_name, failure_cat, code, description, ErrorGroup, Status
```

## Practical Notes

- Keep CSV mode for local development and demos.
- Use MySQL mode for live dashboards.
- Prefer read-only database credentials for the dashboard.
- For near real-time behavior, reduce or clear Streamlit cache intervals after the database is connected. The source switch is ready, but cache timing should be decided based on database load.
