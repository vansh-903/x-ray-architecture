"""
X-Ray API - FastAPI server for ingesting and querying pipeline runs.

Endpoints:
- POST /runs       - Ingest a new run
- GET  /runs       - List runs with filters
- GET  /runs/{id}  - Get a single run with all steps
- GET  /steps      - Query steps across runs
"""

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import storage as db
from .models import (
    ApiResponse,
    RunCreate,
    RunDetail,
    RunListResponse,
    RunSummary,
    StepListResponse,
    StepSummary,
)

app = FastAPI(
    title="X-Ray API",
    description="API for debugging non-deterministic, multi-step pipelines",
    version="1.0.0"
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "X-Ray API"}


@app.post("/runs", response_model=ApiResponse)
async def create_run(run: RunCreate):
    """
    Ingest a new pipeline run.

    The SDK sends run data here after a pipeline completes.
    """
    try:
        run_id = db.insert_run(run.model_dump())
        return ApiResponse(
            success=True,
            message=f"Run {run_id} created successfully",
            data={"run_id": run_id}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/runs", response_model=RunListResponse)
async def list_runs(
    pipeline: Optional[str] = Query(None, description="Filter by pipeline name"),
    status: Optional[str] = Query(None, description="Filter by status (completed, failed, running)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip")
):
    """
    List pipeline runs with optional filters.

    Returns a paginated list of run summaries.
    """
    runs, total = db.list_runs(
        pipeline=pipeline,
        status=status,
        limit=limit,
        offset=offset
    )

    return RunListResponse(
        runs=[RunSummary(**r) for r in runs],
        total=total,
        limit=limit,
        offset=offset
    )


@app.get("/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: str):
    """
    Get a single run with all its steps.

    Returns full details including steps, rejections, and decisions.
    """
    run = db.get_run(run_id)

    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return RunDetail(**run)


@app.get("/steps", response_model=StepListResponse)
async def list_steps(
    step_type: Optional[str] = Query(None, description="Filter by step type (filter, transform, select, generate, rank)"),
    name: Optional[str] = Query(None, description="Filter by step name (partial match)"),
    rejection_rate_gt: Optional[float] = Query(None, ge=0, le=1, description="Filter steps with rejection rate greater than this"),
    rejection_rate_lt: Optional[float] = Query(None, ge=0, le=1, description="Filter steps with rejection rate less than this"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip")
):
    """
    Query steps across all runs.

    Useful for finding patterns like "all filter steps with >90% rejection rate".
    """
    steps, total = db.list_steps(
        step_type=step_type,
        name=name,
        rejection_rate_gt=rejection_rate_gt,
        rejection_rate_lt=rejection_rate_lt,
        limit=limit,
        offset=offset
    )

    return StepListResponse(
        steps=[StepSummary(**s) for s in steps],
        total=total,
        limit=limit,
        offset=offset
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
