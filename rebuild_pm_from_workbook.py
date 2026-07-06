from pathlib import Path

import numpy as np
import pandas as pd


GRACE_DAYS = 3


def main():
    base_dir = Path(__file__).resolve().parent
    workbook_path = Path("/Users/mittal/Downloads/pm_datasheet.xlsx")
    if not workbook_path.exists():
        raise FileNotFoundError(f"Workbook not found: {workbook_path}")

    pm_summary = pd.read_excel(
        workbook_path,
        sheet_name="pm_summary",
        usecols=["eqpRef", "Schedule", "Done", "done by"],
    ).rename(
        columns={
            "eqpRef": "eqp_id",
            "Schedule": "schedule_id",
            "Done": "done_date",
            "done by": "done_by",
        }
    )
    pm_summary["done_date"] = pd.to_datetime(pm_summary["done_date"], errors="coerce")

    eqplist = pd.read_excel(
        workbook_path,
        sheet_name="eqplist",
        usecols=[
            "id",
            "line",
            "Section",
            "Station",
            "System",
            "SubSystem",
            "station_zone",
            "Eqp_Name",
            "EqpID",
            "critical",
        ],
    ).rename(
        columns={
            "id": "eqp_id",
            "Section": "section",
            "Station": "station",
            "System": "system",
            "SubSystem": "subsystem",
        }
    )

    pm_schedule = pd.read_excel(
        workbook_path,
        sheet_name="pm_schedule",
        usecols=["id", "PM_Schedule_Name", "Interval_In_Days"],
    ).rename(
        columns={
            "id": "schedule_id",
            "PM_Schedule_Name": "schedule_name",
            "Interval_In_Days": "interval_days",
        }
    )

    merged = pm_summary.merge(pm_schedule, on="schedule_id", how="left")
    merged = merged.merge(eqplist, on="eqp_id", how="left")
    merged = merged.dropna(subset=["done_date", "station", "system", "subsystem"]).copy()

    merged = merged.sort_values(["eqp_id", "schedule_id", "done_date"])
    merged["prev_done_date"] = merged.groupby(["eqp_id", "schedule_id"])["done_date"].shift(1)
    merged["expected_due_date"] = merged["prev_done_date"] + pd.to_timedelta(
        merged["interval_days"], unit="D"
    )
    merged["days_late"] = (merged["done_date"] - merged["expected_due_date"]).dt.days

    conditions = [merged["prev_done_date"].isna(), merged["days_late"] <= GRACE_DAYS]
    choices = ["baseline", "on_time"]
    merged["compliance_status"] = np.select(conditions, choices, default="late")

    output_cols = [
        "eqp_id",
        "EqpID",
        "Eqp_Name",
        "line",
        "section",
        "station",
        "system",
        "subsystem",
        "station_zone",
        "critical",
        "schedule_name",
        "interval_days",
        "done_date",
        "done_by",
        "expected_due_date",
        "days_late",
        "compliance_status",
    ]
    records = merged[output_cols].copy()

    agg = (
        records.groupby(
            ["station", "system", "subsystem", "schedule_name"], observed=True, as_index=False
        )
        .agg(
            total_pm=("compliance_status", lambda x: (x != "baseline").sum()),
            on_time=("compliance_status", lambda x: (x == "on_time").sum()),
            late=("compliance_status", lambda x: (x == "late").sum()),
            avg_days_late=("days_late", "mean"),
        )
    )
    agg = agg[agg["total_pm"] > 0].copy()
    agg["compliance_pct"] = (agg["on_time"] / agg["total_pm"] * 100).round(1)
    agg["avg_days_late"] = agg["avg_days_late"].round(1)

    records.to_csv(base_dir / "pm_records_clean.csv", index=False)
    agg.to_csv(base_dir / "pm_compliance_agg.csv", index=False)

    print(f"Exported {len(records):,} PM records")
    print(f"Exported {len(agg):,} PM aggregate rows")
    print(f"Date range: {records['done_date'].min().date()} to {records['done_date'].max().date()}")


if __name__ == "__main__":
    main()
