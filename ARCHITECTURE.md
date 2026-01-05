# X-Ray Architecture

## What is X-Ray?

X-Ray helps you debug multi-step pipelines. It answers: **"Why did the system make this decision?"**

**Example:**
- Normal log: `"Filter completed in 250ms"`
- X-Ray: `"Filter rejected Product A because price was $150 (threshold: $100)"`

---

## How It Works

```
Your Pipeline  ──>  X-Ray SDK  ──>  X-Ray API  ──>  Storage
     │                  │               │              │
  (your code)    (captures data)   (stores it)   (query later)
```

**Tech choices:**
- Python SDK - because ML teams use Python
- FastAPI - fast, simple, auto-generates docs
- In-memory storage - simple for demo (use PostgreSQL in production)

---

## 1. Why This Data Model?

I need to answer 3 questions:
1. "Show me run X" → need to group by run
2. "Show all filter steps with >90% rejection" → need to search across runs
3. "Why was item Y rejected?" → need rejection details

**My structure:**
```
Run (one pipeline execution)
  └── Step (one stage like "filter" or "select")
        └── Events (rejections, acceptances, decisions)
```

**Why not other options?**

| Option | Problem |
|--------|---------|
| Flat log | Too slow to search at scale |
| One big JSON per run | Can't search across runs |
| Graph database | Too complex for this use case |

---

## 2. How to Debug a Problem

**Problem:** System selected a laptop stand when user searched for phone case.

**How to find the bug:**

```
Step 1: Find the run
GET /runs?pipeline=competitor_selection
→ Found run_abc123

Step 2: Look at each step (work backwards)

Step 4 - select_best:
  selected: "laptop_stand"
  → Why was laptop stand in the options?

Step 3 - filter_candidates:
  rejected 105 items for "wrong category"
  but laptop_stand passed through
  → Why was it in search results?

Step 2 - search_products:
  keywords used: ["case", "stand", "holder"]
  → "stand" is wrong!

Step 1 - generate_keywords:
  input: "iPhone 15 Case"
  output: ["case", "stand", "holder"]
  → BUG FOUND: System generated "stand" as keyword
```

**Root cause:** Keyword generation created wrong keyword "stand".

---

## 3. How to Search Across Pipelines

**Problem:** Different pipelines name steps differently:
- Pipeline A: `filter_products`
- Pipeline B: `filter_candidates`
- Pipeline C: `filter_items`

**Solution:** Use `step_type` field.

Every step has:
```python
{
  "name": "filter_products",     # can be anything
  "step_type": "filter",         # must be: filter, transform, select, generate, rank
  "input_count": 100,
  "output_count": 30
}
```

Now I can search:
```
GET /steps?step_type=filter&rejection_rate_gt=0.9
```
This finds all filter steps (any name) with >90% rejection.

---

## 4. How to Handle Scale

**Problem:**
- 5000 items rejected per filter step
- 5000 × 2KB = 10MB per step
- 1000 runs/day = 30GB/day

**Solution:** Don't store everything. Store smart.

| What | Store? | Size |
|------|--------|------|
| Counts (how many rejected) | Always | 500 bytes |
| Accepted items | Always | 3KB |
| Sample of rejected (50 items) | Always | 10KB |
| All rejected items | Only when needed | 10MB |

**Result:** 15KB instead of 10MB (99% smaller)

**How to use:**
```python
# Normal: stores samples only
with run.step("filter") as step:
    ...

# Debug mode: stores everything
with run.step("filter", capture="full") as step:
    ...
```

---

## 5. Easy to Use

**Minimum code (3 lines):**
```python
from sdk import XRay

with XRay("my_pipeline").run(input=data) as run:
    result = my_existing_code()  # no changes needed
    run.set_output(result)
```

**Full tracking:**
```python
with run.step("filter", step_type="filter") as step:
    step.set_input_count(100)

    for item in items:
        if item.price > 100:
            step.reject(item.id, "price_too_high", {"price": item.price})
        else:
            step.accept(item.id)

    step.set_output_count(len(filtered))
```

**If API is down:**
```python
xray = XRay("pipeline", offline_mode="buffer")  # saves locally, syncs later
```

X-Ray never breaks your pipeline. If API fails, data is saved locally.

---

## 6. Real Example

**System:** Content moderation (checks if posts are appropriate)

**Without X-Ray:**
- User: "My post was rejected but it's fine"
- Support: "Log says rejected by moderation"
- Nobody knows which step or why

**With X-Ray:**
```
Run: post_abc123
├── spam_check: passed (score: 0.12)
├── toxicity_check: {insult: 0.65, threat: 0.08}
└── policy_check: REJECTED
    reason: "insult score too high"
    score: 0.65, threshold: 0.50
```

Now I know exactly what happened and can fix it.

---

## 7. Test Results

| Test | Result |
|------|--------|
| 100 runs created | All stored correctly |
| 20 failed runs | Error messages captured |
| Query by pipeline | Works |
| Query by status | Works |
| Query filter steps | Found 62 with >50% rejection |

---

## 8. What's Next

| Feature | Why |
|---------|-----|
| Async calls | Don't slow down pipeline |
| Persistent storage | Keep data after restart |
| Batch requests | Send multiple runs at once |
| Alerts | Notify when rejection rate is too high |

---

## API Reference

| Method | Endpoint | What it does |
|--------|----------|--------------|
| POST | `/runs` | Save a new run |
| GET | `/runs` | List all runs |
| GET | `/runs/{id}` | Get one run with all details |
| GET | `/steps` | Search steps across all runs |

**Example queries:**
```bash
# All runs for a pipeline
curl "http://localhost:8000/runs?pipeline=my_pipeline"

# Failed runs only
curl "http://localhost:8000/runs?status=failed"

# Filter steps with high rejection
curl "http://localhost:8000/steps?step_type=filter&rejection_rate_gt=0.9"
```
