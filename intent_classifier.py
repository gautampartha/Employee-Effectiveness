from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Iterable

try:
    from rapidfuzz import fuzz, process
except ImportError:  # pragma: no cover - requirements.txt includes rapidfuzz.
    fuzz = None
    process = None


BLOCKED_PATTERNS = [
    r"\b(delete|drop|truncate|remove|wipe|clear)\b.*(data|record|table|database|csv|file)",
    r"(ignore|forget).*(previous|above|prior).*(instruction|rule|prompt)",
    r"you are now|act as|pretend (you are|to be)|jailbreak|DAN mode",
    r"<script|javascript:|SELECT .* FROM|INSERT INTO|UPDATE .* SET",
    r"\b(password|credentials|api.?key|token|secret)\b",
    r"show.*employee.*(number|phone|email|address|personal)",
]

MONTH_LOOKUP = {
    "JANUARY": 1,
    "JAN": 1,
    "FEBRUARY": 2,
    "FEB": 2,
    "MARCH": 3,
    "MAR": 3,
    "APRIL": 4,
    "APR": 4,
    "MAY": 5,
    "JUNE": 6,
    "JUN": 6,
    "JULY": 7,
    "JUL": 7,
    "AUGUST": 8,
    "AUG": 8,
    "SEPTEMBER": 9,
    "SEP": 9,
    "SEPT": 9,
    "OCTOBER": 10,
    "OCT": 10,
    "NOVEMBER": 11,
    "NOV": 11,
    "DECEMBER": 12,
    "DEC": 12,
}

INTENT_KEYWORDS = {
    "failure_classification_query": {
        "weight": 1.0,
        "terms": ["maintenance gap", "gap failure", "equipment failure", "no pm record", "classified failure"],
    },
    "urgent_query": {
        "weight": 0.95,
        "terms": ["urgent", "critical", "red", "risk", "priority", "attention", "need action"],
    },
    "comparison_query": {
        "weight": 0.9,
        "terms": ["compare", "comparison", "versus", " vs ", "better than", "worse than"],
    },
    "trend_query": {
        "weight": 0.85,
        "terms": ["trend", "monthly", "yearly", "month wise", "over time", "timeline", "history"],
    },
    "employee_query": {
        "weight": 0.85,
        "terms": ["employee", "staff", "technician", "done by", "done_by", "performer", "team", "workload"],
    },
    "failure_query": {
        "weight": 0.8,
        "terms": ["failure", "failures", "breakdown", "resolution", "fault", "outage", "failure mode"],
    },
    "compliance_query": {
        "weight": 0.8,
        "terms": ["compliance", "late pm", "on time", "on-time", "overdue", "pm rate", "pm percentage"],
    },
    "summary_query": {
        "weight": 0.75,
        "terms": ["summary", "brief", "overview", "insight", "executive", "status", "health"],
    },
    "station_query": {
        "weight": 0.65,
        "terms": ["station"],
    },
    "subsystem_query": {
        "weight": 0.65,
        "terms": ["subsystem", "system", "afc", "telecom", "cctv", "ohe", "signalling", "signal"],
    },
}

DMRC_CONTEXT_TERMS = {
    "dmrc",
    "metro",
    "maintenance",
    "pm",
    "station",
    "system",
    "subsystem",
    "equipment",
    "asset",
    "failure",
    "failures",
    "breakdown",
    "compliance",
    "late",
    "overdue",
    "urgent",
    "critical",
    "risk",
    "summary",
    "brief",
    "employee",
    "technician",
    "team",
    "trend",
    "compare",
}

OUT_OF_SCOPE_TERMS = {
    "weather",
    "sports",
    "movie",
    "recipe",
    "cricket",
    "football",
    "stock",
    "bitcoin",
    "news",
    "capital of",
}


def _sanitize_for_log(text: str) -> str:
    sanitized = re.sub(r"[\w\.-]+@[\w\.-]+", "[email]", text or "")
    sanitized = re.sub(r"\b\d{5,}\b", "[number]", sanitized)
    return sanitized[:500]


def _log_blocked_attempt(user_input: str, reason: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}\t{reason}\t{_sanitize_for_log(user_input)}\n"
    try:
        Path("security_log.txt").open("a", encoding="utf-8").write(line)
    except OSError:
        pass


def security_filter(user_input: str) -> tuple[bool, str | None]:
    text = user_input or ""
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            reason = (
                "I cannot help with destructive actions, prompt bypass attempts, secrets, or personal employee details. "
                "This assistant can only analyze DMRC maintenance data."
            )
            _log_blocked_attempt(text, reason)
            return False, reason
    return True, None


def _clean_values(values: Iterable[str] | None) -> list[str]:
    if not values:
        return []
    return sorted({str(value).strip().upper() for value in values if str(value).strip()})


def _exact_matches(text_upper: str, candidates: list[str]) -> list[str]:
    matches = []
    for value in sorted(candidates, key=len, reverse=True):
        if re.search(rf"(?<![A-Z0-9]){re.escape(value)}(?![A-Z0-9])", text_upper):
            matches.append(value)
    return matches


def _fuzzy_match_token(text_upper: str, candidates: list[str], min_score: int = 80) -> str | None:
    if not candidates or process is None or fuzz is None:
        return None
    tokens = re.findall(r"[A-Z0-9]{3,}", text_upper)
    best_value = None
    best_score = 0
    for token in tokens:
        result = process.extractOne(token, candidates, scorer=fuzz.ratio)
        if result and result[1] > best_score:
            best_value, best_score = result[0], result[1]
    return best_value if best_score >= min_score else None


def extract_entities(user_input: str, valid_stations: list, valid_subsystems: list) -> dict:
    text = user_input or ""
    text_upper = text.upper()
    whole_network_scope = bool(
        re.search(r"\b(?:WHOLE|FULL|ENTIRE|ALL)\s+NETWORK\b|\bNETWORK[- ]WIDE\b", text_upper)
    )
    stations = _clean_values(valid_stations)
    subsystems = _clean_values(valid_subsystems)

    station_matches = _exact_matches(text_upper, stations)
    subsystem_matches = _exact_matches(text_upper, subsystems)

    station = station_matches[0] if station_matches else _fuzzy_match_token(text_upper, stations)
    if whole_network_scope:
        subsystem = None
    else:
        subsystem = subsystem_matches[0] if subsystem_matches else _fuzzy_match_token(text_upper, subsystems)

    year_match = re.search(r"\b(20\d{2}|19\d{2})\b", text_upper)
    year = int(year_match.group(1)) if year_match else None

    month = None
    for month_name, month_num in MONTH_LOOKUP.items():
        if re.search(rf"(?<![A-Z]){month_name}(?![A-Z])", text_upper):
            month = month_num
            break
    if month is None:
        month_match = re.search(r"\b(?:MONTH|IN)\s+(1[0-2]|0?[1-9])\b", text_upper)
        month = int(month_match.group(1)) if month_match else None

    equipment = None
    equipment_match = re.search(r"\b(?:EQUIPMENT|ASSET|EQP|EQPID)\s*[:#-]?\s*([A-Z0-9][A-Z0-9_/\-]{3,})\b", text_upper)
    if equipment_match:
        equipment = equipment_match.group(1)

    comparison_targets = []
    if len(station_matches) >= 2:
        comparison_targets = station_matches[:2]
    elif len(subsystem_matches) >= 2:
        comparison_targets = subsystem_matches[:2]

    return {
        "station": station,
        "subsystem": subsystem,
        "year": year,
        "month": month,
        "equipment": equipment,
        "comparison_targets": comparison_targets,
    }


def _score_intents(text_lower: str, entities: dict) -> tuple[str, float]:
    scores = {}
    for intent, spec in INTENT_KEYWORDS.items():
        hits = sum(1 for term in spec["terms"] if term in text_lower)
        if hits:
            scores[intent] = min(0.99, spec["weight"] + (hits - 1) * 0.04)

    if entities.get("station") and "station_query" not in scores:
        scores["station_query"] = 0.75
    if entities.get("subsystem") and "subsystem_query" not in scores:
        scores["subsystem_query"] = 0.72
    if entities.get("comparison_targets"):
        scores["comparison_query"] = max(scores.get("comparison_query", 0.0), 0.92)
    if entities.get("year") or entities.get("month"):
        scores["trend_query"] = max(scores.get("trend_query", 0.0), 0.76)

    if not scores:
        return "unknown", 0.2

    intent, confidence = max(scores.items(), key=lambda item: item[1])
    return intent, float(confidence)


def classify_intent(
    user_input: str,
    valid_stations: list | None = None,
    valid_subsystems: list | None = None,
) -> dict:
    is_safe, rejection_reason = security_filter(user_input)
    if not is_safe:
        return {
            "intent": "unknown",
            "entities": {},
            "confidence": 1.0,
            "is_safe": False,
            "rejection_reason": rejection_reason,
        }

    text = (user_input or "").strip()
    text_lower = text.lower()
    entities = extract_entities(text, valid_stations or [], valid_subsystems or [])

    if any(term in text_lower for term in OUT_OF_SCOPE_TERMS) and not any(term in text_lower for term in DMRC_CONTEXT_TERMS):
        return {
            "intent": "unknown",
            "entities": entities,
            "confidence": 0.9,
            "is_safe": True,
            "rejection_reason": None,
        }

    intent, confidence = _score_intents(text_lower, entities)
    return {
        "intent": intent,
        "entities": entities,
        "confidence": confidence,
        "is_safe": True,
        "rejection_reason": None,
    }

