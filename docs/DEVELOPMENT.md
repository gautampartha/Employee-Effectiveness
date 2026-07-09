# Development Notes

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Design Principles In Current Codebase

- Keep core startup light.
- Load heavy failure analytics only on demand.
- Build insights from structured summaries rather than from raw CSV prompting.
- Prefer deterministic rules before adding AI narration.

## Where To Add New Work

### UI changes

Edit:

- `app.py`

### PM/failure calculations

Edit:

- `pipeline.py`

### Failure classification logic

Edit:

- `failure_pipeline.py`

### Insight generation logic

Edit:

- `insights_engine.py`

### Shared paths/constants

Edit:

- `app_config.py`

## Good Next Refactors

- Introduce a single `failure_service.py`
- Introduce a reusable `scope_summary` service
- Move AI interaction into a dedicated module
- Add real tests under a `tests/` directory

## Testing Gaps

The repository currently has script-style tests:

- `test_duration.py`
- `test_failure.py`

These are helpful for manual checks, but not enough for regression safety.

Recommended automated coverage:

- PM KPI calculations
- failure classification output
- risk ranking math
- insight rule triggering
- AI context builder formatting
