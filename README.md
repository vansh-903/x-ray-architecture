# X-Ray SDK

A debugging system for multi-step, non-deterministic pipelines.

**X-Ray answers:** *"Why did the system make this decision?"*

---

## My Approach

**Problem:** Multi-step pipelines are hard to debug. When output is wrong, you don't know which step failed.

**Solution:** Capture decision context at each step - not just what happened, but why.

**Key ideas:**
- **Context managers** - `with run.step()` auto-captures timing and errors
- **Structured rejections** - `step.reject(id, reason, details)` tracks why items were removed
- **Sampling** - Store counts always, sample 1% of rejected items to save storage
- **Offline mode** - Buffer locally if API is down, never break the pipeline

---

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Start API server
python -m uvicorn api.main:app --reload --port 8000

# Run demo
python -m examples.demo
```

---

## Usage

**Minimal (3 lines):**
```python
from sdk import XRay

with XRay("my_pipeline").run(input=data) as run:
    result = my_existing_code()
    run.set_output(result)
```

**Full instrumentation:**
```python
with xray.run(input=data) as run:
    with run.step("filter", step_type="filter") as step:
        step.set_input_count(100)
        for item in items:
            if item.price > 100:
                step.reject(item.id, "price_too_high", {"price": item.price})
        step.set_output_count(len(filtered))
```

---

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/runs` | Save a run |
| GET | `/runs` | List runs |
| GET | `/runs/{id}` | Get run details |
| GET | `/steps` | Search steps across runs |

**Example:**
```bash
curl "http://localhost:8000/steps?step_type=filter&rejection_rate_gt=0.9"
```

---

## Known Limitations

- **In-memory storage** - Data lost on restart (use PostgreSQL in production)
- **Synchronous calls** - Should be async in production
- **No authentication** - Would need API keys for real use

## Future Improvements

- Async ingestion
- Request batching
- Persistent storage
- Alerting on high rejection rates

---

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design reasoning.
