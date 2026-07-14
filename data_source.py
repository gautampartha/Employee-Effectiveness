from abc import ABC, abstractmethod

import pandas as pd

import failure_pipeline
import pipeline
from app_config import (
    DATA_SOURCE,
    ERROR_LOOKUP_PATH,
    FAILURE_LOG_PATH,
    MYSQL_ERROR_LOOKUP_QUERY,
    MYSQL_ERROR_LOOKUP_TABLE,
    MYSQL_FAILURE_LOG_QUERY,
    MYSQL_FAILURE_LOG_TABLE,
    MYSQL_PM_AGG_QUERY,
    MYSQL_PM_AGG_TABLE,
    MYSQL_PM_RECORDS_QUERY,
    MYSQL_PM_RECORDS_TABLE,
    MYSQL_URL,
    PM_AGG_PATH,
    PM_RECORDS_PATH,
)


CSS_COLUMNS = [
    "Date",
    "Line",
    "Sec",
    "Station",
    "System",
    "SubSystem",
    "EquipmentNo",
    "FailureTime",
    "FailureDescription",
    "Failure_Detail",
    "Status",
    "FailureCategory",
    "FailureType",
    "RectificationTime",
    "RectificationDate",
    "Duration",
    "ActionTaken",
    "Origin",
    "Attendedby",
    "Remarksby",
    "AttendedByName",
    "RemarksByName",
    "root_cause_analysis",
]

ERROR_COLUMNS = [
    "id",
    "eqp_type_name",
    "failure_cat",
    "code",
    "description",
    "ErrorGroup",
    "Status",
]


class DashboardDataSource(ABC):
    """Boundary between dashboard code and the physical data store."""

    label = "Unknown"

    @abstractmethod
    def load_pm_records(self):
        raise NotImplementedError

    @abstractmethod
    def load_pm_compliance_agg(self):
        raise NotImplementedError

    @abstractmethod
    def has_failure_sources(self):
        raise NotImplementedError

    @abstractmethod
    def load_failure_events(self, pm_date_range=None):
        raise NotImplementedError

    @abstractmethod
    def load_failures_for_classification(self):
        raise NotImplementedError

    @abstractmethod
    def load_pm_records_for_classification(self):
        raise NotImplementedError


class CsvDashboardDataSource(DashboardDataSource):
    label = "CSV files"

    def load_pm_records(self):
        if not PM_RECORDS_PATH.exists():
            return None
        return pipeline.load_records_clean(PM_RECORDS_PATH)

    def load_pm_compliance_agg(self):
        return pipeline.load_compliance_agg(PM_AGG_PATH)

    def has_failure_sources(self):
        return FAILURE_LOG_PATH.exists() and ERROR_LOOKUP_PATH.exists()

    def load_failure_events(self, pm_date_range=None):
        if not self.has_failure_sources():
            return None
        return pipeline.load_failure_events(
            FAILURE_LOG_PATH,
            ERROR_LOOKUP_PATH,
            pm_date_range=pm_date_range,
        )

    def load_failures_for_classification(self):
        if not self.has_failure_sources():
            return pd.DataFrame()
        return failure_pipeline.load_failures()

    def load_pm_records_for_classification(self):
        if not PM_RECORDS_PATH.exists():
            return pd.DataFrame()
        return failure_pipeline.load_pm_records()


class MySqlDashboardDataSource(DashboardDataSource):
    label = "MySQL database"

    def __init__(self):
        if not MYSQL_URL:
            raise ValueError(
                "DMRC_DATA_SOURCE is set to 'mysql', but DMRC_MYSQL_URL is empty."
            )
        try:
            from sqlalchemy import create_engine, text
        except ImportError as exc:
            raise ImportError(
                "MySQL mode needs SQLAlchemy and a MySQL driver. Install dependencies from requirements.txt."
            ) from exc

        self._create_engine = create_engine
        self._text = text
        self._engine = create_engine(MYSQL_URL, pool_pre_ping=True)

    def _read(self, table_name, query):
        with self._engine.connect() as conn:
            if query:
                return pd.read_sql_query(self._text(query), conn)
            return pd.read_sql_table(table_name, conn)

    def _read_pm_records_raw(self):
        return self._read(MYSQL_PM_RECORDS_TABLE, MYSQL_PM_RECORDS_QUERY)

    def _read_pm_agg_raw(self):
        return self._read(MYSQL_PM_AGG_TABLE, MYSQL_PM_AGG_QUERY)

    def _read_failure_log_raw(self):
        return self._read(MYSQL_FAILURE_LOG_TABLE, MYSQL_FAILURE_LOG_QUERY)

    def _read_error_lookup_raw(self):
        return self._read(MYSQL_ERROR_LOOKUP_TABLE, MYSQL_ERROR_LOOKUP_QUERY)

    def load_pm_records(self):
        df = self._read_pm_records_raw()
        return _normalize_pm_records(df)

    def load_pm_compliance_agg(self):
        df = self._read_pm_agg_raw()
        return _normalize_pm_agg(df)

    def has_failure_sources(self):
        return True

    def load_failure_events(self, pm_date_range=None):
        failure_df = self._read_failure_log_raw()
        error_df = self._read_error_lookup_raw()
        return _normalize_failure_events(failure_df, error_df, pm_date_range=pm_date_range)

    def load_failures_for_classification(self):
        failure_df = self.load_failure_events(pm_date_range=None)
        if failure_df.empty:
            return failure_df

        df = failure_df.copy()
        df = df[pd.to_numeric(df["status"], errors="coerce") == 2.0].copy()
        df["duration_raw"] = pd.to_numeric(df["duration_raw"], errors="coerce")
        df["duration_capped"] = df["duration_raw"].clip(upper=9999)
        df["Station"] = df["station"]
        df["SubSystem"] = df["subsystem"]
        df["System"] = df["system"]
        df["Date"] = df["failure_date"]
        df["Duration"] = df["duration_capped"]
        return df

    def load_pm_records_for_classification(self):
        df = self._read_pm_records_raw().copy()
        _require_columns(
            df,
            [
                "station",
                "system",
                "subsystem",
                "done_date",
                "compliance_status",
                "days_late",
            ],
            "PM records",
        )
        for col in ["station", "system", "subsystem"]:
            df[col] = df[col].astype("string").str.strip().str.upper()
        df["compliance_status"] = df["compliance_status"].astype("string").str.strip().str.lower()
        df["done_date"] = pd.to_datetime(df["done_date"], errors="coerce")
        df["days_late"] = pd.to_numeric(df["days_late"], errors="coerce")
        return df


def _require_columns(df, required_columns, source_name):
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(
            f"{source_name} is missing required column(s): {', '.join(missing)}"
        )


def _normalize_pm_records(df):
    df = df.copy()
    required_columns = [
        "EqpID",
        "Eqp_Name",
        "station",
        "section",
        "system",
        "subsystem",
        "schedule_name",
        "done_date",
        "done_by",
        "expected_due_date",
        "days_late",
        "compliance_status",
    ]
    _require_columns(df, required_columns, "PM records")
    df = df[required_columns].copy()

    string_columns = [
        "EqpID",
        "Eqp_Name",
        "station",
        "section",
        "system",
        "subsystem",
        "schedule_name",
        "done_by",
        "compliance_status",
    ]
    for col in string_columns:
        df[col] = df[col].astype("string")

    df["days_late"] = pd.to_numeric(df["days_late"], errors="coerce").astype("float32")
    df["done_date"] = pd.to_datetime(df["done_date"], errors="coerce")
    df["expected_due_date"] = pd.to_datetime(df["expected_due_date"], errors="coerce")

    for col in ["station", "section", "system", "subsystem", "schedule_name", "compliance_status"]:
        df[col] = df[col].map(pipeline._normalize_label)

    df["done_by"] = df["done_by"].map(pipeline._normalize_text)
    df["eqkey"] = df["EqpID"].map(pipeline._normalize_label).str.replace(r"[^A-Z0-9]+", "", regex=True)
    return df


def _normalize_pm_agg(df):
    df = df.copy()
    required_columns = [
        "station",
        "system",
        "subsystem",
        "schedule_name",
        "total_pm",
        "on_time",
        "late",
        "avg_days_late",
        "compliance_pct",
    ]
    _require_columns(df, required_columns, "PM compliance aggregate")
    df = df[required_columns].copy()

    for col in ["station", "system", "subsystem", "schedule_name"]:
        df[col] = df[col].astype("string").map(pipeline._normalize_label)

    for col in ["total_pm", "on_time", "late"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int32")

    for col in ["avg_days_late", "compliance_pct"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float32")

    return df


def _normalize_failure_events(css_df, errors_df, pm_date_range=None):
    css_df = css_df.copy()
    errors_df = errors_df.copy()
    _require_columns(css_df, CSS_COLUMNS, "Failure log")
    _require_columns(errors_df, ERROR_COLUMNS, "Error lookup")

    css_df = css_df[CSS_COLUMNS].copy()
    errors_df = errors_df[ERROR_COLUMNS].copy()

    css_df = css_df.rename(
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
        }
    )

    css_df["failure_date"] = pd.to_datetime(css_df["failure_date"], errors="coerce")
    css_df["failure_time"] = pd.to_datetime(css_df["failure_time"], errors="coerce")
    css_df["rectification_date"] = pd.to_datetime(css_df["rectification_date"], errors="coerce")
    css_df["rectification_time"] = pd.to_datetime(css_df["rectification_time"], errors="coerce")
    css_df["failure_code"] = pd.to_numeric(css_df["failure_code_raw"], errors="coerce").astype("Int64")

    for col in ["station", "system", "subsystem", "line", "section"]:
        css_df[col] = css_df[col].map(pipeline._normalize_label)

    for col in ["equipment_no", "failure_detail", "action_taken", "origin", "root_cause_analysis"]:
        css_df[col] = css_df[col].map(pipeline._normalize_text)

    css_df["attended_by_display"] = pipeline._normalize_person_series(
        css_df["attended_by_name"], css_df["attended_by"]
    )
    css_df["remarks_by_display"] = pipeline._normalize_person_series(
        css_df["remarks_by_name"], css_df["remarks_by"]
    )

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

    errors_df["failure_code"] = pd.to_numeric(errors_df["failure_code"], errors="coerce").astype("Int64")
    for col in ["mapped_eqp_type", "error_category_master", "error_description_master", "error_group"]:
        errors_df[col] = errors_df[col].map(pipeline._normalize_text)

    css_df = css_df.merge(errors_df, on="failure_code", how="left")
    css_df["mapped_eqp_type_norm"] = css_df["mapped_eqp_type"].map(pipeline._normalize_label)
    css_df["error_description"] = css_df["error_description_master"].fillna(css_df["failure_detail"])
    css_df["failure_category"] = css_df["error_category_master"].fillna(css_df["failure_category_raw"])
    css_df["failure_category"] = css_df["failure_category"].map(pipeline._normalize_text)

    css_df["mapping_confidence"] = "LOOKUP_ONLY"
    exact_match = css_df["subsystem"] == css_df["mapped_eqp_type_norm"]
    family_match = pd.Series(
        [
            bool(left and right and (right in left or left in right))
            for left, right in zip(
                css_df["subsystem"].fillna(""),
                css_df["mapped_eqp_type_norm"].fillna(""),
            )
        ],
        index=css_df.index,
    )
    system_level_match = (
        ((css_df["mapped_eqp_type_norm"] == "ALL AFC") & (css_df["system"] == "AFC"))
        | ((css_df["mapped_eqp_type_norm"] == "ALL TELECOM") & (css_df["system"] == "TELECOM"))
    )
    css_df.loc[exact_match, "mapping_confidence"] = "EXACT_SUBSYSTEM_MATCH"
    css_df.loc[~exact_match & family_match, "mapping_confidence"] = "FAMILY_MATCH"
    css_df.loc[~exact_match & ~family_match & system_level_match, "mapping_confidence"] = "SYSTEM_LEVEL_MATCH"
    css_df.loc[css_df["failure_code"].isna(), "mapping_confidence"] = "UNMAPPED"

    css_df["failure_event_at"] = css_df["failure_time"].fillna(css_df["failure_date"])
    css_df["resolved"] = css_df["rectification_date"].notna()
    css_df["eqkey"] = css_df["equipment_no"].map(pipeline._normalize_label).str.replace(r"[^A-Z0-9]+", "", regex=True)

    duration_hours = pd.to_numeric(css_df["duration_raw"], errors="coerce") / 3600.0
    timestamp_hours = (
        css_df["rectification_date"] - css_df["failure_event_at"]
    ).dt.total_seconds() / 3600.0
    css_df["resolution_hours"] = timestamp_hours.where(timestamp_hours > 0, duration_hours)

    if pm_date_range and pm_date_range[0] is not None and pm_date_range[1] is not None:
        start_date, end_date = pm_date_range
        css_df = css_df[
            css_df["failure_date"].between(start_date, end_date, inclusive="both")
        ].copy()
        css_df["pm_window_applied"] = True
    else:
        css_df["pm_window_applied"] = False

    css_df["month"] = css_df["failure_date"].dt.to_period("M").astype("string")
    return css_df


def get_dashboard_data_source():
    if DATA_SOURCE == "csv":
        return CsvDashboardDataSource()
    if DATA_SOURCE in {"mysql", "db", "database"}:
        return MySqlDashboardDataSource()
    raise ValueError(
        f"Unsupported DMRC_DATA_SOURCE '{DATA_SOURCE}'. Use 'csv' or 'mysql'."
    )
