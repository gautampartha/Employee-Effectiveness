# DMRC Employee Effectiveness System — Module 1 Revision Sheet

## What is Module 1?
A **Preventive Maintenance (PM) Compliance Dashboard** that visualises whether
maintenance tasks across Delhi Metro's network are being completed on time.
Built for two audiences: managers (Overview tab) and engineers (Detailed Explorer tab).

---

## Data Source
Single file: `pm_datasheet.xlsx` — 4 sheets:

| Sheet | Rows | Role |
|---|---|---|
| `pm_summary` | 503,818 | Core fact table — one row per PM completion event |
| `eqplist` | 105,856 | Equipment master — station, system, sub-system, criticality |
| `pm_schedule` | 6 | Lookup — schedule name → interval days (Weekly=7, Monthly=30, etc.) |
| `pm_datasheet` | 76,611 | Checklist detail — not used in Module 1 |

---

## Data Pipeline (Module1_PM_Pipeline.ipynb → pipeline.py)

### Joins
```
pm_summary  --[schedule_id]-->  pm_schedule   (gets interval_days)
pm_summary  --[eqp_id]------->  eqplist       (gets station/system/subsystem)
```
- 1,537 equipment IDs in pm_summary had no match in eqplist (0.3%) → dropped

### Key Compliance Logic
For each equipment + schedule track, sorted by date:
```
prev_done_date   = previous completion date for same equipment+schedule
expected_due_date = prev_done_date + interval_days
days_late        = done_date - expected_due_date
```
**Status rules (GRACE_DAYS = 3):**
- `baseline` — first-ever record, no previous date to compare (excluded from all %)
- `on_time`  — days_late ≤ 3
- `late`     — days_late > 3

### Real numbers from data
| Metric | Value |
|---|---|
| Total trackable PM records | 368,189 |
| On-time | 221,022 (60.0%) |
| Late | 147,167 (40.0%) |
| Avg delay | ~0.2 days early (mean days_late) |
| Worst subsystem | Emergency Switch — 41.5% compliance, 1,122 tasks |

### Output files
- `pm_records_clean.csv` — 503,017 rows, full record-level detail
- `pm_compliance_agg.csv` — 7,028 rows, pre-aggregated by station+system+subsystem+schedule

---

## Dashboard (app.py + pipeline.py)

### Tab 1: Overview (for managers)
- Auto-generated insight sentence — worst subsystem by compliance (min 20 records threshold)
- 4 KPI cards: Total PM, Compliance %, Avg Delay, Late Count — computed live
- Ranked horizontal bar chart (worst 15) — toggle By Station / By Subsystem
- Traffic light coloring: 🔴 <60% / 🟠 60–85% / 🟢 >85%

### Tab 2: Detailed Explorer (for engineers)
- Sidebar filters: Station, System, Sub-System (cascading), Schedule Name, Date Range
- Heatmap: station × subsystem, colored by compliance_pct (Plotly)
- Monthly trend line chart
- Late records table, sortable, with CSV download

### Pipeline functions (pipeline.py)
- `load_records_clean()` — loads with usecols + category dtypes + @st.cache_data
- `load_compliance_agg()` — loads aggregation table
- `filter_records(df, station, system, subsystem, schedule_name, date_from, date_to)` — all optional
- `compute_compliance_summary(filtered_df)` — returns KPIs for current filter slice

---

## Key Design Decisions (know these for Q&A)

**Why 3-day grace period?**
Real-world PM scheduling has weekends, shift constraints — a strict 0-day window
would mark many genuinely on-time completions as late. Tunable constant in code.

**Why weighted mean for heatmap, not average of percentages?**
A station with 2 records (1 on-time = 50%) should not count equally to a station
with 200 records (100 on-time = 50%). Weighted mean = sum(on_time)/sum(total_pm)*100.

**Why station+system+subsystem granularity, not exact equipment?**
More statistically meaningful (avoids noise from assets with 1–2 records),
and aligns with how managers think ("CCTV at Rajiv Chowk" not a specific unit ID).

**Why two tabs?**
A heatmap with 300+ stations is unreadable to a manager. Overview tab answers
"what needs attention" in 30 seconds. Explorer tab is for investigation.

**Why pre-aggregate into pm_compliance_agg.csv?**
Filtering 503k rows on every dashboard interaction would be slow. The aggregation
table is 7,028 rows — 70x smaller, near-instant for all filter operations.

---

## Known Limitations (be honest about these)
- No failure/fault data in pm_datasheet.xlsx — Module 2/3 need css.csv (failure log)
- 1,537 equipment IDs unmatched between pm_summary and eqplist — unknown if decommissioned or data gap
- `done_by` field is messy free text — not used in Module 1, deferred to Module 3
- `pm_datasheet` sheet only 77% join coverage with pm_summary — excluded from pipeline
- Database connection is future work — currently reads static CSV files

---

## Tech Stack
| Layer | Tool |
|---|---|
| Data cleaning | Python, pandas, numpy |
| Development | Jupyter Notebook |
| Dashboard | Streamlit |
| Charts | Plotly |
| Data format | CSV (pipeline outputs), xlsx (raw source) |
