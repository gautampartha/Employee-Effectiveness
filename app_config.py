import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

PM_RECORDS_PATH = BASE_DIR / "pm_records_clean.csv"
PM_AGG_PATH = BASE_DIR / "pm_compliance_agg.csv"
FAILURE_LOG_PATH = BASE_DIR / "css.csv"
ERROR_LOOKUP_PATH = BASE_DIR / "errors.csv"

DATA_SOURCE = os.getenv("DMRC_DATA_SOURCE", "csv").strip().lower()

MYSQL_URL = os.getenv("DMRC_MYSQL_URL", "").strip()
MYSQL_PM_RECORDS_TABLE = os.getenv("DMRC_MYSQL_PM_RECORDS_TABLE", "pm_records_clean").strip()
MYSQL_PM_AGG_TABLE = os.getenv("DMRC_MYSQL_PM_AGG_TABLE", "pm_compliance_agg").strip()
MYSQL_FAILURE_LOG_TABLE = os.getenv("DMRC_MYSQL_FAILURE_LOG_TABLE", "css").strip()
MYSQL_ERROR_LOOKUP_TABLE = os.getenv("DMRC_MYSQL_ERROR_LOOKUP_TABLE", "errors").strip()

MYSQL_PM_RECORDS_QUERY = os.getenv("DMRC_MYSQL_PM_RECORDS_QUERY", "").strip()
MYSQL_PM_AGG_QUERY = os.getenv("DMRC_MYSQL_PM_AGG_QUERY", "").strip()
MYSQL_FAILURE_LOG_QUERY = os.getenv("DMRC_MYSQL_FAILURE_LOG_QUERY", "").strip()
MYSQL_ERROR_LOOKUP_QUERY = os.getenv("DMRC_MYSQL_ERROR_LOOKUP_QUERY", "").strip()

COMPLIANCE_RED_THRESHOLD = 60.0
COMPLIANCE_AMBER_THRESHOLD = 85.0
RISK_SCORE_AMBER_THRESHOLD = 40.0
RISK_SCORE_RED_THRESHOLD = 70.0

COLOR_RED = "#d9534f"
COLOR_AMBER = "#f0ad4e"
COLOR_GREEN = "#2E7D32"

MONTH_NAMES = [
    "All",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:1b"
