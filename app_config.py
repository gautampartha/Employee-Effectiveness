from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

PM_RECORDS_PATH = BASE_DIR / "pm_records_clean.csv"
PM_AGG_PATH = BASE_DIR / "pm_compliance_agg.csv"
FAILURE_LOG_PATH = BASE_DIR / "css.csv"
ERROR_LOOKUP_PATH = BASE_DIR / "errors.csv"

COMPLIANCE_RED_THRESHOLD = 60.0
COMPLIANCE_AMBER_THRESHOLD = 85.0

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
