# X-Ray SDK

A debugging system for multi-step, non-deterministic pipelines.

**X-Ray answers:** *"Why did the system make this decision?"*

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Start the API server

```bash
cd api
uvicorn main:app --reload
```

API will be available at `http://localhost:8000`

### 3. Run the demo

```bash
python -m examples.demo
```

### 4. Query the results

```bash
# List all runs
curl http://localhost:8000/runs

# Get a specific run
curl http://localhost:8000/runs/{run_id}

# Find filter steps with high rejection rates
curl "http://localhost:8000/steps?step_type=filter&rejection_rate_gt=0.9"
```

## SDK Usage

### Minimal instrumentation (3 lines)

```python
from sdk import XRay

with XRay("my_pipeline").run(input={"product": "iPhone Case"}) as run:
    result = my_existing_pipeline()  # No changes needed
    run.set_output(result)
```

### Full instrumentation

```python
from sdk import XRay

xray = XRay("competitor_selection", api_url="http://localhost:8000")

with xray.run(input={"product": "iPhone Case"}) as run:

    # Step 1: Generate keywords
    with run.step("generate_keywords", step_type="generate") as step:
        step.set_input({"title": title})
        keywords = generate_keywords(title)
        step.set_output({"keywords": keywords})

    # Step 2: Filter candidates
    with run.step("filter_candidates", step_type="filter") as step:
        step.set_input_count(len(candidates))

        for item in candidates:
            if item.price > 100:
                step.reject(item.id, "price_too_high", {"price": item.price})
            else:
                step.accept(item.id)

        step.set_output_count(len(filtered))

    # Step 3: Select best
    with run.step("select_best", step_type="select") as step:
        best = select_best(filtered)
        step.decide(
            decision="select_competitor",
            selected=best.id,
            reason="highest_score",
            score=best.score
        )

    run.set_output({"selected": best.id})
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/runs` | Ingest a new run |
| GET | `/runs` | List runs (filter by `?pipeline=X&status=Y`) |
| GET | `/runs/{id}` | Get run with all steps |
| GET | `/steps` | Query steps across runs |

### Example queries

```bash
# Find all completed runs for a pipeline
curl "http://localhost:8000/runs?pipeline=competitor_selection&status=completed"

# Find filter steps that rejected >90% of items
curl "http://localhost:8000/steps?step_type=filter&rejection_rate_gt=0.9"

# Get full details of a run
curl "http://localhost:8000/runs/run_abc123"
```

## Project Structure

```
xray-assignment/
├── sdk/                    # Python SDK
│   ├── __init__.py
│   ├── xray.py            # Main XRay class
│   ├── run.py             # Run context manager
│   └── step.py            # Step context manager
├── api/                    # FastAPI server
│   ├── main.py            # Endpoints
│   ├── models.py          # Pydantic models
│   └── storage.py         # In-memory storage
├── examples/
│   └── demo.py            # Working demo
├── tests/
│   └── test_scale.py      # Scale and failure tests
├── ARCHITECTURE.md        # Design decisions
└── README.md
```

## Key Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Data Model | Relational (Run → Step → Event) | Cross-run queries need indexed lookups |
| SDK Pattern | Context managers | Clear scope, auto-cleanup on exceptions |
| Storage | Sampling (1% + aggregates) | 99.85% cost reduction |
| Offline Mode | Local buffer | Never break production |

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed reasoning.

## Offline Mode

If the API is unavailable, the SDK buffers data locally:

```python
xray = XRay("pipeline", offline_mode="buffer")  # Default

# Later, sync offline runs
xray.sync_offline()
```

Options:
- `buffer`: Save locally, sync later (default)
- `drop`: Silently ignore
- `strict`: Raise error

## Known Limitations

1. **In-memory storage** - Data lost on restart; production would use PostgreSQL
2. **Synchronous API calls** - Should be async in production (~2s per run currently)
3. **No authentication** - Would need API keys for real use
4. **No retention policies** - Data grows indefinitely

## Future Improvements

- Async ingestion (don't block pipeline)
- Request batching
- Data retention policies
- Run comparison (diff two runs)
- Alerting (notify on high rejection rates)
