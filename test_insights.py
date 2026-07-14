import json
from pathlib import Path
import re

import pandas as pd

import insights_engine
from trend_analyzer import compute_rolling_correlation


def _base_summary(failure_slice=None, pm_slice=None):
    failure_slice = failure_slice if failure_slice is not None else pd.DataFrame()
    pm_slice = pm_slice if pm_slice is not None else pd.DataFrame()
    total_failures = len(failure_slice)
    return {
        "scope": {"label": "station TEST", "station": "TEST", "system": "All", "subsystem": "All"},
        "slice_pm": {"total_pm": len(pm_slice), "on_time": 0, "late": 0, "compliance_pct": 0.0, "avg_days_late": 0.0},
        "network_pm": {"total_pm": 100, "on_time": 80, "late": 20, "compliance_pct": 80.0, "avg_days_late": 1.0},
        "slice_fail": {
            "total_failures": total_failures,
            "resolved": total_failures,
            "unresolved": 0,
            "unique_assets": failure_slice["eqkey"].nunique() if "eqkey" in failure_slice else 0,
            "avg_resolution_hours": 1.0 if total_failures else 0.0,
        },
        "maintenance_gap_count": 0,
        "maintenance_gap_pct": 0.0,
        "top_failure_modes": pd.DataFrame(),
        "subsystem_health": pd.DataFrame(),
        "failure_slice": failure_slice,
        "pm_slice": pm_slice,
        "classified_slice": pd.DataFrame(),
        "trend_data": {
            "months": [],
            "compliance": [],
            "late_pm_count": [],
            "failure_count": [],
            "resolution_avg_hours": [],
            "gap_failure_pct": [],
            "trend_signals": [],
        },
        "thresholds": {
            "critical_compliance": 55.0,
            "network_compliance_gap": 10.0,
            "weak_subsystem_compliance": 60.0,
            "maintenance_gap_critical": 45.0,
            "slow_resolution_hours": 4.0,
            "dominant_failure_mode_pct": 25.0,
        },
    }


def test_dynamic_weight_normalization_always_sums_to_one():
    row = {
        "compliance_pct": 40.0,
        "failure_rate_per_100_pm": 25.0,
        "maintenance_gap_pct": 65.0,
        "avg_resolution_hours": 9.0,
    }
    benchmarks = {
        "compliance_pct": [40.0, 60.0, 80.0, 95.0],
        "failure_rate_per_100_pm": [1.0, 5.0, 15.0, 25.0],
        "resolution_mean": 3.0,
        "resolution_std": 2.0,
    }
    risk_score, breakdown = insights_engine.compute_dynamic_risk_score(
        row,
        benchmarks,
        {"active_recent_failures": True},
    )
    assert 0.0 <= risk_score <= 100.0
    assert sum(item["weight"] for item in breakdown.values()) == 1.0


def test_repeat_failure_rule_triggers_after_three_occurrences():
    failures = pd.DataFrame(
        {
            "eqkey": ["ASSET01"] * 4,
            "station": ["TEST"] * 4,
            "subsystem": ["AFC"] * 4,
        }
    )
    insights = insights_engine.generate_scope_insights(_base_summary(failure_slice=failures))
    repeat = next(item for item in insights if item["id"] == "repeat_failure")
    assert repeat["affected_assets"] == ["ASSET01"]
    assert "4 failures" in repeat["message"]


def test_dead_zone_rule_triggers_with_failures_and_no_pm():
    failures = pd.DataFrame(
        {
            "eqkey": ["ASSET01", "ASSET02"],
            "station": ["TEST", "TEST"],
            "subsystem": ["AFC", "AFC"],
        }
    )
    insights = insights_engine.generate_scope_insights(
        _base_summary(failure_slice=failures, pm_slice=pd.DataFrame())
    )
    dead_zone = next(item for item in insights if item["id"] == "dead_zone")
    assert "No PM activity" in dead_zone["message"]
    assert "2 reported failures" in dead_zone["message"]


def test_validate_insight_output_removes_unfilled_placeholders():
    valid = {
        "id": "valid",
        "priority": "info",
        "title": "Valid",
        "message": "There were 3 failures.",
        "recommendation": "Review all three.",
        "data_ref": "failure_count",
        "affected_assets": [],
        "confidence": 0.9,
    }
    invalid = {**valid, "id": "invalid", "message": "There were [N] failures."}
    result = insights_engine.validate_insight_output([invalid, valid])
    assert [item["id"] for item in result] == ["valid"]


def test_sanitize_scope_input_rejects_invalid_year_and_month(monkeypatch, tmp_path):
    monkeypatch.setattr(insights_engine, "SECURITY_LOG_PATH", tmp_path / "security_log.txt")
    valid_year, _, year_error = insights_engine.sanitize_scope_input(
        {"station": "All", "system": "All", "subsystem": "All", "year": 2099, "month": "All"}
    )
    valid_month, _, month_error = insights_engine.sanitize_scope_input(
        {"station": "All", "system": "All", "subsystem": "All", "year": 2025, "month": 13}
    )
    assert not valid_year and "2018" in year_error
    assert not valid_month and "1 and 12" in month_error


def test_no_f_string_query_pattern_in_insights_engine():
    source = Path(insights_engine.__file__).read_text(encoding="utf-8")
    unsafe_pattern = re.compile(r"\.query\s*\(\s*f[\"']")
    assert not unsafe_pattern.search(source)


def test_structured_ai_context_never_contains_raw_dataframe_rows():
    summary = _base_summary(
        pm_slice=pd.DataFrame(
            {
                "done_date": [pd.Timestamp("2025-01-01")],
                "private_raw_note": ["DO_NOT_EXPOSE_RAW_ROW"],
            }
        )
    )
    summary["slice_pm"]["total_pm"] = 1
    context = insights_engine.build_structured_ai_context(summary, [], summary["trend_data"])
    serialized = json.dumps(context)
    assert "DO_NOT_EXPOSE_RAW_ROW" not in serialized
    assert "private_raw_note" not in serialized


def test_rolling_lag_correlation_is_bounded():
    trend = {
        "late_pm_count": [1, 2, 4, 3, 7, 5],
        "failure_count": [0, 2, 4, 8, 6, 14],
    }
    result = compute_rolling_correlation(trend)
    assert -1.0 <= result["lag_correlation"] <= 1.0
