"""
In-memory storage for X-Ray API.

Simple Python dictionaries for demo purposes.
Production would use PostgreSQL or similar.

Data model:
- RUNS: dict mapping run_id -> run_data (with embedded steps)
- For queries, we iterate through the data structures
"""

from typing import Any, Dict, List, Optional, Tuple

# In-memory storage
RUNS: Dict[str, Dict[str, Any]] = {}


def insert_run(run_data: Dict[str, Any]) -> str:
    """Insert a new run with its steps."""
    run_id = run_data["run_id"]
    RUNS[run_id] = run_data
    return run_id


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Get a run by ID with all its steps."""
    return RUNS.get(run_id)


def list_runs(
    pipeline: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> Tuple[List[Dict[str, Any]], int]:
    """List runs with optional filters."""
    # Filter runs
    filtered = []
    for run in RUNS.values():
        if pipeline and run.get("pipeline") != pipeline:
            continue
        if status and run.get("status") != status:
            continue
        filtered.append(run)

    # Sort by run_id (newest first, assuming IDs are sortable)
    filtered.sort(key=lambda r: r.get("started_at", ""), reverse=True)

    total = len(filtered)

    # Paginate
    paginated = filtered[offset:offset + limit]

    # Return summaries
    summaries = []
    for run in paginated:
        summaries.append({
            "run_id": run["run_id"],
            "pipeline": run["pipeline"],
            "status": run.get("status", "completed"),
            "started_at": run.get("started_at"),
            "ended_at": run.get("ended_at"),
            "duration_ms": run.get("duration_ms"),
            "step_count": len(run.get("steps", []))
        })

    return summaries, total


def list_steps(
    step_type: Optional[str] = None,
    name: Optional[str] = None,
    rejection_rate_gt: Optional[float] = None,
    rejection_rate_lt: Optional[float] = None,
    limit: int = 100,
    offset: int = 0
) -> Tuple[List[Dict[str, Any]], int]:
    """List steps across all runs with optional filters."""
    # Collect all steps with their run info
    all_steps = []
    for run in RUNS.values():
        for step in run.get("steps", []):
            step_with_run = {
                "run_id": run["run_id"],
                "pipeline": run["pipeline"],
                "step_name": step["name"],
                "step_type": step.get("step_type"),
                "input_count": step.get("input_count"),
                "output_count": step.get("output_count"),
                "rejection_rate": step.get("rejection_rate"),
                "duration_ms": step.get("duration_ms")
            }
            all_steps.append(step_with_run)

    # Filter
    filtered = []
    for step in all_steps:
        if step_type and step.get("step_type") != step_type:
            continue
        if name and name.lower() not in step.get("step_name", "").lower():
            continue
        if rejection_rate_gt is not None:
            rate = step.get("rejection_rate")
            if rate is None or rate <= rejection_rate_gt:
                continue
        if rejection_rate_lt is not None:
            rate = step.get("rejection_rate")
            if rate is None or rate >= rejection_rate_lt:
                continue
        filtered.append(step)

    total = len(filtered)

    # Paginate
    paginated = filtered[offset:offset + limit]

    return paginated, total


def clear_all():
    """Clear all data. Useful for testing."""
    RUNS.clear()
