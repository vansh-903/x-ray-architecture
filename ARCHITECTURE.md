# X-Ray Architecture

## The Problem

Modern pipelines have multiple steps. When output is wrong, you don't know which step failed.

```
Product → Keywords → Search → Filter → Rank → Select → Wrong Result
                                                        ↑
                                               Which step broke?
```

Traditional logs tell you "Pipeline completed in 2.5s". That's useless.

**X-Ray captures WHY each step made its decision.**

---

## How X-Ray Works

```
Our Code           X-Ray SDK         X-Ray API         Storage
    │                  │                 │                │
    │  with run()      │                 │                │
    ├─────────────────>│                 │                │
    │  with step()     │                 │                │
    ├─────────────────>│  (captures)     │                │
    │  step.reject()   │                 │                │
    ├─────────────────>│                 │                │
    │  (run ends)      │    POST /runs   │                │
    │                  ├────────────────>│    (stores)    │
    │                  │                 ├───────────────>│
```

---

## 1. Data Model

**Run** = One complete pipeline execution

**Step** = One stage inside a run (filter, rank, select, etc.)

```
Run: "Find competitor for iPhone Case"
├── run_id: "run_abc123"
├── status: "completed" or "failed"
├── error: null or "Error message"
├── input: {"product": "iPhone Case"}
├── output: {"selected": "Phone Case X"}
│
└── Steps:
    ├── Step 1: generate_keywords
    │   ├── input_count: 1
    │   ├── output_count: 4
    │   └── output: ["case", "cover", "stand"]
    │
    ├── Step 2: filter_candidates
    │   ├── input_count: 500
    │   ├── output_count: 30
    │   ├── rejection_counts: {"price_too_high": 200, "wrong_category": 270}
    │   └── sampled_rejections: [{id: "prod_1", reason: "price_too_high", details: {price: 150}}]
    │
    └── Step 3: select_best
        ├── decision: "best_match"
        ├── selected: "phone_case_x"
        └── score: 0.87
```

**Why this structure?**
- Runs group everything for one execution → easy to debug end-to-end
- Steps are separate → can query "all filter steps with >90% rejection" across ALL pipelines
- Errors captured at both run and step level → know exactly where it broke

**Alternatives I rejected:**
- Flat logs: Can't query across pipelines
- One big JSON per run: Can't search steps across runs
- Separate tables for everything: Overcomplicated for this use case

---

## 2. Debugging Walkthrough

**Scenario:** User searched for "iPhone Case" but system selected "Laptop Stand"

### Without X-Ray

You only see the final output: "laptop_stand". No idea which step failed. You start guessing, add print statements, re-run, repeat.

### With X-Ray

X-Ray stored every step's decision. Trace backwards:

**Check the final selection:**
- Selected "laptop_stand" with score 0.87
- Question: Why was laptop stand even in the final candidates?

**Check the filter step:**
- Input: 500 products → Output: 30 products
- Rejected 470 items for "wrong_category" and "price_too_high"
- But laptop_stand passed through
- Question: Why didn't the category filter catch it?

**Check the search step:**
- Found 500 products matching the keywords
- Laptop stands were in the results
- Question: Why did search return laptop stands?

**Check the keyword generation step:**
- Input: "iPhone Case"
- Output keywords: "case", "cover", "stand"
- **BUG FOUND:** Generated "stand" as a keyword

### Root Cause

Keyword generation incorrectly produced "stand" from "iPhone Case". This pulled laptop stands into search results. The filter didn't catch it because "laptop stand" wasn't in the blocked category list.

### The Fix

Fix keyword generation logic to not produce generic words like "stand".

**Without X-Ray:** Looks like a ranking problem—you debug the wrong step.
**With X-Ray:** Trace backwards and find the actual source.

---

## 3. Queryability Across Pipelines

**Problem:** Teams name steps differently:
- Team A: `filter_products`
- Team B: `filter_candidates`
- Team C: `remove_bad_items`

**Solution:** Enforce `step_type`:

| step_type | What it does |
|-----------|--------------|
| `generate` | Creates data (LLM, algorithms) |
| `filter` | Removes candidates |
| `rank` | Scores candidates |
| `select` | Picks final answer |

**Now I can query across ALL pipelines:**
```
GET /steps?step_type=filter&rejection_rate_gt=0.9
```
→ Returns all filter steps (any name) with >90% rejection rate.

**Trade-off:** Developers must specify step_type. Small effort, big payoff.

---

## 4. Performance & Scale

**Problem:** Filter step rejects 5,000 items. Storing all = 10MB per step.

**Solution:** Don't store everything. Store smart.

| What | Store? | Size |
|------|--------|------|
| Counts per reason | Always | 500 bytes |
| 20 samples per reason | Always | 10KB |
| All rejections | Only if needed | 10MB |

**Result:** 15KB instead of 10MB.

**Who decides?** Developer chooses capture level:
- `sample` (default) → counts + samples
- `full` → everything
- `minimal` → counts only

---

## 5. Developer Experience

**Minimal instrumentation:**
- Wrap the entire pipeline in a `run()` context
- Set input and output
- Get: run_id, duration, status, errors automatically captured

**Full instrumentation:**
- Wrap each decision point in a `step()` context
- Record rejections with `reject(id, reason, details)`
- Record acceptances and final decisions
- Get: complete decision trail for every item

**If API is down:**
- SDK buffers data locally, syncs when API recovers
- Pipeline continues to run normally
- Observability failure ≠ system failure

---

## 6. Real-World Application

In a previous LLM content pipeline, bad outputs required manually adding print statements everywhere to find the issue.

With X-Ray:
- Query: "Show runs where quality score < 0.5"
- See exactly which step produced bad intermediate output
- Trace root cause directly

**Retrofitting:** Wrap existing code in `run()` and `step()` contexts. No refactor needed.

---

## 7. What's Next

| Priority | Feature | Why |
|----------|---------|-----|
| High | Async ingestion | Don't block pipelines |
| High | PostgreSQL storage | Persist data |
| Medium | Alerting | "Filter rejecting >95% - investigate" |
| Low | Visual timeline | UI for non-engineers |

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/runs` | Save run with all steps |
| GET | `/runs` | List runs (filter by pipeline, status) |
| GET | `/runs/{id}` | Get full run details |
| GET | `/steps` | Search steps across all runs |

**Example:**
```
GET /steps?step_type=filter&rejection_rate_gt=0.9
```
→ Find all filter steps rejecting >90% of candidates.
