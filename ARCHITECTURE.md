# X-Ray Architecture

## What is X-Ray?

X-Ray helps you debug multi-step pipelines. It answers: **"Why did the system make this decision?"**

**Example:**
- Normal log: `"Filter completed in 250ms"`
- X-Ray: `"Filter rejected Product A because price was $150 (threshold: $100)"`

```
Your Pipeline  ──>  X-Ray SDK  ──>  X-Ray API  ──>  Storage
     │                  │               │              │
  (your code)    (captures data)   (stores it)   (query later)
```

---

## 1. Data Model Rationale

### The Questions I Need to Answer

| Question | Requirement |
|----------|-------------|
| "Show me run X" | Group data by run |
| "Find all filter steps with >90% rejection" | Search across runs |
| "Why was item Y rejected?" | Store rejection details |

### My Structure

```
Run (one pipeline execution)
  └── Step (one stage like "filter" or "select")
        ├── Rejections (why items were removed)
        ├── Acceptances (what passed through)
        └── Decisions (what was chosen and why)
```

### Alternatives I Considered

| Option | Why I Rejected It |
|--------|-------------------|
| **Flat logs** | Can't efficiently query "all filter steps with >90% rejection" - would need full scan |
| **One JSON blob per run** | Can't search across runs without loading all data into memory |
| **Graph database** | Overkill - my queries are hierarchical (run → step → event), not graph traversals |
| **Event sourcing** | Adds complexity without benefit - I don't need to replay events, just query them |

### Why Steps and Runs Are First-Class Entities

**Runs** are first-class because:
- Each pipeline execution is independent
- Users debug one run at a time
- Need to track run-level metadata (status, duration, error)

**Steps** are first-class because:
- Different pipelines have different steps
- Need to query across runs by step type
- Each step has its own input/output counts and rejection reasons

If I embedded steps inside runs as nested JSON, I couldn't efficiently query "all filter steps across all runs."

---

## 2. Debugging Walkthrough

### Scenario: Bad Match Detected

**Problem:** System selected a laptop stand when user searched for "iPhone 15 Case."

### Step-by-Step Debug Process

**Step 1: Find the problematic run**
```bash
curl "http://localhost:8000/runs?pipeline=competitor_selection&status=completed"
```

**Response:**
```json
{
  "runs": [
    {"run_id": "run_abc123", "status": "completed", "output": {"selected": "laptop_stand_42"}}
  ]
}
```

**Step 2: Get full run details**
```bash
curl "http://localhost:8000/runs/run_abc123"
```

**Response:**
```json
{
  "run_id": "run_abc123",
  "input": {"product_title": "iPhone 15 Case"},
  "steps": [
    {
      "name": "generate_keywords",
      "step_type": "generate",
      "output": {"keywords": ["case", "stand", "holder", "cover"]}
    },
    {
      "name": "filter_candidates",
      "step_type": "filter",
      "input_count": 127,
      "output_count": 23,
      "rejections": {
        "category_mismatch": {"count": 45, "samples": [...]},
        "price_too_high": {"count": 32, "samples": [...]}
      }
    },
    {
      "name": "select_best",
      "step_type": "select",
      "decision": {"selected": "laptop_stand_42", "score": 0.87}
    }
  ]
}
```

**Step 3: Trace the bug backwards**

| Step | Observation | Question |
|------|-------------|----------|
| select_best | Selected laptop_stand_42 | Why was it in the candidate pool? |
| filter_candidates | 45 items rejected for "category_mismatch" but laptop stand passed | Bug in category filter? |
| search_products | Found 127 products | Why did "laptop stand" match? |
| generate_keywords | Keywords: ["case", "stand", ...] | **BUG FOUND:** "stand" shouldn't be a keyword |

**Root Cause:** The keyword generation step produced "stand" as a keyword, which pulled laptop stands into the search results.

---

## 3. Queryability Across Pipelines

### The Problem

Different teams name steps differently:
- Team A: `filter_products`
- Team B: `filter_candidates`
- Team C: `apply_filters`

Without standardization, I can't query "all filter steps" across pipelines.

### My Solution: Standard Step Types

Every step must declare a `step_type` from this taxonomy:

| step_type | Purpose | Example |
|-----------|---------|---------|
| `generate` | Create new data (LLM, algorithms) | Keyword generation |
| `retrieve` | Fetch from external source | Product search |
| `filter` | Remove items based on criteria | Price/rating filters |
| `rank` | Order items by score | Relevance ranking |
| `select` | Choose final output | Best match selection |
| `transform` | Modify data format | Normalization |

### Convention Developers Must Follow

```python
# Wrong - no step_type
with run.step("filter_products") as step:
    ...

# Correct - includes step_type
with run.step("filter_products", step_type="filter") as step:
    ...
```

### Cross-Pipeline Queries

```bash
# Find all filter steps with >90% rejection rate
curl "http://localhost:8000/steps?step_type=filter&rejection_rate_gt=0.9"

# Find all LLM generation steps that took >5 seconds
curl "http://localhost:8000/steps?step_type=generate&duration_gt=5000"
```

### Trade-off

| Approach | Pros | Cons |
|----------|------|------|
| Enforce step_type | Enables cross-pipeline queries | Requires developer discipline |
| Free-form names only | Maximum flexibility | Can't query across pipelines |

I chose to enforce `step_type` because cross-pipeline visibility is the core value of X-Ray.

---

## 4. Performance & Scale

### The Problem

A filter step might reject 5,000 items. Storing full details for each:
- 5,000 items × 2KB = 10MB per step
- 100 steps/day × 10MB = 1GB/day
- 1 year = 365GB

### My Solution: Tiered Capture

| Data | Always Stored | Size |
|------|---------------|------|
| Counts (input, output, by reason) | Yes | ~500 bytes |
| Accepted items (full details) | Yes | ~3KB |
| Rejected samples (50 per reason) | Yes | ~10KB |
| All rejected items | Only on request | ~10MB |

**Result:** 15KB instead of 10MB (99.8% reduction)

### Who Controls Capture Level?

**Developer decides** at instrumentation time:

```python
# Default: counts + samples (recommended)
with run.step("filter", step_type="filter") as step:
    ...

# Debug mode: capture everything
with run.step("filter", step_type="filter", capture="full") as step:
    ...

# Minimal: counts only (for high-volume steps)
with run.step("filter", step_type="filter", capture="minimal") as step:
    ...
```

### Trade-off Analysis

| Capture Level | Storage | Debug Quality | Use Case |
|---------------|---------|---------------|----------|
| `minimal` | Lowest | Counts only | High-volume production |
| `sample` (default) | Medium | Usually sufficient | Most use cases |
| `full` | Highest | Complete visibility | Debugging specific issues |

---

## 5. Developer Experience

### Minimal Instrumentation (3 lines)

```python
from sdk import XRay

with XRay("my_pipeline").run(input=data) as run:
    result = my_existing_code()  # unchanged
    run.set_output(result)
```

**What you get:** Run ID, status, duration, input/output, errors captured.

### Full Instrumentation

```python
with xray.run(input=data) as run:

    with run.step("filter", step_type="filter") as step:
        step.set_input_count(len(candidates))

        for item in candidates:
            if item.price > threshold:
                step.reject(item.id, "price_too_high", {"price": item.price})
            else:
                step.accept(item.id)

        step.set_output_count(len(filtered))
```

### When X-Ray Backend is Unavailable

**X-Ray never breaks your pipeline.**

```python
xray = XRay("pipeline", offline_mode="buffer")
```

| Mode | Behavior |
|------|----------|
| `fail` | Raise exception if API unavailable (for testing) |
| `silent` | Silently drop data if API unavailable |
| `buffer` | Save locally, sync when API recovers (default) |

---

## 6. Real-World Application

### System: LLM Content Pipeline

In a previous project, I built a pipeline that generated and validated content using LLMs. When outputs were poor, I couldn't tell which step failed.

**Without X-Ray:**
- Logs: "Pipeline completed"
- No visibility into intermediate decisions
- Hours of adding print statements to debug

**With X-Ray:**
```bash
# Find all runs with low quality scores
curl "/steps?step_type=select&score_lt=0.5"

# Trace back through each step
curl "/runs/{run_id}"
```

**Time Savings:** Hours → Minutes

### Retrofitting X-Ray

To add X-Ray to an existing pipeline:

1. **Wrap the pipeline** (5 min) - Add `with xray.run()` wrapper
2. **Add step tracking** (30 min) - Wrap key decision points
3. **Add rejection tracking** (1-2 hours) - Add `step.reject()` calls

---

## 7. What's Next

### High Priority

| Feature | Why |
|---------|-----|
| **Async ingestion** | SDK should never block the pipeline |
| **Persistent storage** | PostgreSQL with data retention policies |
| **Request batching** | Combine multiple updates into single API call |

### Medium Priority

| Feature | Why |
|---------|-----|
| **Alerting** | Notify when rejection rate exceeds threshold |
| **Visual timeline UI** | Interactive run visualization |
| **Correlation IDs** | Link to external request tracing |

### Nice to Have

| Feature | Why |
|---------|-----|
| **Diff comparison** | Compare two runs side-by-side |
| **Replay mode** | Re-run step with captured inputs |
| **Multi-language SDKs** | TypeScript, Go, Java |

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/runs` | Save a new run |
| GET | `/runs` | List runs (filter by pipeline, status) |
| GET | `/runs/{id}` | Get run with all steps |
| GET | `/steps` | Search steps across all runs |

### Example Queries

```bash
# All runs for a pipeline
curl "http://localhost:8000/runs?pipeline=competitor_selection"

# Failed runs only
curl "http://localhost:8000/runs?status=failed"

# Filter steps with >90% rejection
curl "http://localhost:8000/steps?step_type=filter&rejection_rate_gt=0.9"
```

---

## Summary

X-Ray provides visibility into multi-step pipeline decisions by:

1. **Structured data model** - Runs contain Steps contain Events
2. **Standard step types** - Enables cross-pipeline queries
3. **Sampled storage** - 99% smaller than full capture
4. **Developer-friendly SDK** - Context managers with automatic error handling
5. **Offline resilience** - Never breaks your pipeline

The goal: When something goes wrong, trace from output to root cause in minutes, not hours.
