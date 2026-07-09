# Data Contracts

## PM Records: `pm_records_clean.csv`

Used by `pipeline.load_records_clean(...)`.

Expected fields include:

- `EqpID`
- `Eqp_Name`
- `station`
- `section`
- `system`
- `subsystem`
- `schedule_name`
- `done_date`
- `done_by`
- `expected_due_date`
- `days_late`
- `compliance_status`

Derived fields:

- `eqkey`

## PM Aggregate: `pm_compliance_agg.csv`

Used by `pipeline.load_compliance_agg(...)`.

Expected fields include:

- `station`
- `system`
- `subsystem`
- `schedule_name`
- `total_pm`
- `on_time`
- `late`
- `avg_days_late`
- `compliance_pct`

## Failure Master: `css.csv`

Used by both:

- `pipeline.load_failure_events(...)`
- `failure_pipeline.load_failures(...)`

Commonly expected raw fields include:

- `Date`
- `Line`
- `Sec`
- `Station`
- `System`
- `SubSystem`
- `EquipmentNo`
- `FailureTime`
- `FailureDescription`
- `Failure_Detail`
- `Status`
- `FailureCategory`
- `FailureType`
- `RectificationTime`
- `RectificationDate`
- `Duration`
- `ActionTaken`
- `Origin`
- `Attendedby`
- `Remarksby`
- `AttendedByName`
- `RemarksByName`
- `root_cause_analysis`

## Error Lookup: `errors.csv`

Expected fields include:

- `id`
- `eqp_type_name`
- `failure_cat`
- `code`
- `description`
- `ErrorGroup`
- `Status`

## Important Model Conventions

- text labels are normalized to uppercase in the PM/failure analytics path
- `eqkey` is the normalized equipment join key
- `BASELINE` PM rows are excluded from compliance KPI calculation
- resolved failure filtering is driven from `Status == 2`

## Caution

If upstream CSV structure changes, the app may still start but some tabs can silently degrade. The first things to verify are:

- date parsing
- `Status`
- `Duration`
- subsystem labels
- equipment IDs used for `eqkey`
