# DMRC Employee Effectiveness

Streamlit dashboard for Delhi Metro maintenance performance, PM compliance, failure intelligence, and filtered insight generation.

## What This System Does

- Loads PM records and PM compliance aggregates.
- Loads failure logs and enriches them with `errors.csv`.
- Compares PM execution and failure history across station, system, subsystem, month, and equipment slices.
- Generates:
  - overview metrics,
  - detailed PM/failure analysis,
  - classified failure analysis,
  - rule-based slice insights,
  - optional Ollama-powered AI briefs.

## Main Modules

- [app.py](/Users/mittal/Documents/DMRC%20PROJECT/Employee-Effectiveness/app.py)
  Streamlit UI, lazy-loading flow, and tab orchestration.
- [pipeline.py](/Users/mittal/Documents/DMRC%20PROJECT/Employee-Effectiveness/pipeline.py)
  Core PM + failure data loading and analytical helpers used by the app.
- [failure_pipeline.py](/Users/mittal/Documents/DMRC%20PROJECT/Employee-Effectiveness/failure_pipeline.py)
  Failure classification pipeline that labels failures as maintenance-gap, equipment, or no-PM-record.
- [insights_engine.py](/Users/mittal/Documents/DMRC%20PROJECT/Employee-Effectiveness/insights_engine.py)
  Slice-aware rules engine and AI context builder for the Insights tab.
- [app_config.py](/Users/mittal/Documents/DMRC%20PROJECT/Employee-Effectiveness/app_config.py)
  Shared paths, thresholds, colors, month names, and Ollama config.

## Architecture

High-level system documentation lives in:

- [docs/ARCHITECTURE.md](/Users/mittal/Documents/DMRC%20PROJECT/Employee-Effectiveness/docs/ARCHITECTURE.md)
- [docs/DATA_CONTRACTS.md](/Users/mittal/Documents/DMRC%20PROJECT/Employee-Effectiveness/docs/DATA_CONTRACTS.md)
- [docs/DEVELOPMENT.md](/Users/mittal/Documents/DMRC%20PROJECT/Employee-Effectiveness/docs/DEVELOPMENT.md)

## Data Files

The app expects these files in the project root:

- `pm_records_clean.csv`
- `pm_compliance_agg.csv`
- `css.csv`
- `errors.csv`

Notes:

- `pm_records_clean.csv` is record-level PM history.
- `pm_compliance_agg.csv` is the pre-aggregated PM compliance rollup.
- `css.csv` is the failure master log.
- `errors.csv` maps failure codes to readable descriptions and groups.

## Running Locally

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the app:

```bash
streamlit run app.py
```

Default local URL:

- [http://localhost:8501](http://localhost:8501)

## AI Briefs

The `Ask Assistant` and `Generate AI Brief` flows call a local Ollama server.

Default config:

- URL: `http://localhost:11434/api/generate`
- Model: `llama3.2:1b`

If Ollama is not running, the dashboard still works, but AI summaries will not.

## Performance Notes

The app was reworked to reduce startup latency:

- core PM data loads first,
- heavy failure pipelines are triggered on demand,
- detailed intelligence, failure analysis, and slice insights do not fully compute on initial page load.

Large datasets still make some actions expensive. For future production hardening, move from raw CSV to Parquet, DuckDB, or SQLite.

## Current Limitations

- Some heavy analytics still depend on full CSV scans.
- The app uses two failure-processing paths:
  - `pipeline.load_failure_events(...)`
  - `failure_pipeline.load_failures(...)`
  These are now lazily triggered, but should eventually be unified.
- There are only lightweight test scripts today; this project would benefit from real unit tests around insight generation and failure classification.

## Recommended Next Steps

- Unify the failure-processing stack into one canonical model.
- Move large CSV inputs to a queryable local store.
- Add automated tests for:
  - PM KPI calculation,
  - failure classification,
  - slice insight generation,
  - AI context construction.
- Separate UI layout from data services further if the dashboard continues to grow.
