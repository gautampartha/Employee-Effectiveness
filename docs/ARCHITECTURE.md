# Architecture

## Overview

The system is a Streamlit-based analytics application built around four layers:

1. Data sources
2. Data services
3. Insight engines
4. UI orchestration

## Layers

### 1. Data Sources

Files in the project root:

- `pm_records_clean.csv`
- `pm_compliance_agg.csv`
- `css.csv`
- `errors.csv`

These are treated as local analytical datasets rather than operational databases.

### 2. Data Services

#### `pipeline.py`

Owns the main PM-oriented analytics path:

- PM record loading
- PM aggregate loading
- failure enrichment for the app
- filter helpers
- KPI builders
- PM/failure monthly joins
- equipment history and PM-to-failure linking

#### `failure_pipeline.py`

Owns the classified failure-analysis path:

- failure master loading
- normalized failure model
- PM record loading for classification
- classification into:
  - maintenance-gap failure
  - equipment failure
  - no PM record
- failure summary generation

## 3. Insight Engines

#### `insights_engine.py`

Provides:

- filtered scope summary generation
- subsystem risk ranking
- rule-based insight cards
- AI prompt context for slice-specific briefs

This is the current intelligence layer of the system.

## 4. UI Orchestration

#### `app.py`

Owns:

- page layout
- lazy-load strategy
- tab orchestration
- user filters
- chart rendering
- AI interactions via Ollama

## Architectural Improvements Already Applied

- Shared constants moved into `app_config.py`
- expensive failure analysis deferred until requested
- expensive slice insights deferred until requested
- startup reduced to core PM data path

## Architectural Debt

### Dual failure pipelines

Today the system still uses:

- `pipeline.load_failure_events(...)`
- `failure_pipeline.load_failures(...)`

This makes the model understandable, but not ideal. The best next architecture step is to unify these into one canonical failure service with:

- one normalized schema
- one enrichment path
- one classification path
- optional lightweight views for different tabs

### App logic concentration

`app.py` still contains significant analytical orchestration. Over time, move more slice assembly logic into service modules so the UI becomes thinner.

## Target Future Architecture

Recommended direction:

1. `app_config.py`
2. `data_access.py`
3. `pm_service.py`
4. `failure_service.py`
5. `insight_service.py`
6. `ai_service.py`
7. `app.py`

That split would improve testability and reduce coupling between UI and data logic.
