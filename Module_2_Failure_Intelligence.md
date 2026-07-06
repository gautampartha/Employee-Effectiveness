# DMRC Employee Effectiveness System — Failure Intelligence Layer

## What has been added
- `css.csv` is now treated as the historical failure log.
- `errors.csv` is now treated as the error master / lookup table.
- The dashboard has been extended with a new **Failure Intelligence** tab.

## What the new layer does
- Enriches each failure event with a readable failure mode from `errors.csv`
- Normalizes key dimensions such as station, system, and subsystem
- Summarizes:
  - top repeated failure modes
  - failure category mix
  - monthly failure volume
  - frequent responders / attenders
- Prepares PM-vs-failure correlation views when record-level PM data is available

## PM relationship logic
When `pm_records_clean.csv` is present, the system can:
- restrict failure history to the same PM date window
- compare monthly PM compliance against monthly failure count
- show the nearest previous PM event before a failure in the same station/system/subsystem bucket
- expose who attended the failure and who last completed the PM event

## Current limitation
The extracted repository currently does **not** include `pm_records_clean.csv`.

Because of that:
- the Overview tab works
- aggregated PM Explorer still works
- Failure Intelligence works on failure data
- exact PM date locking and person-level PM-to-failure linking stay inactive until `pm_records_clean.csv` is added

## Required file for full interrelation
- `pm_records_clean.csv`

This file is expected to contain:
- `done_date`
- `done_by`
- `station`
- `system`
- `subsystem`
- `EqpID`
- `Eqp_Name`
- `schedule_name`
- `compliance_status`

## Recommended next step
Place `pm_records_clean.csv` in the project folder beside `app.py`.

Once it is available, the new dashboard flow will automatically:
- clip `css.csv` to the current PM system date range
- enable PM-to-failure relationship graphs
- enable nearest-PM-before-failure tables
