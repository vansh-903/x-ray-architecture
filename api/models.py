"""
Pydantic models for the X-Ray API.

These define the shape of data for requests and responses.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# --- Request Models ---

class StepCreate(BaseModel):
    """A step within a run."""
    name: str
    step_type: Optional[str] = None
    input: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None
    input_count: Optional[int] = None
    output_count: Optional[int] = None
    rejection_rate: Optional[float] = None
    rejection_counts: Dict[str, int] = Field(default_factory=dict)
    sampled_rejections: List[Dict[str, Any]] = Field(default_factory=list)
    acceptances: List[Dict[str, Any]] = Field(default_factory=list)
    decisions: List[Dict[str, Any]] = Field(default_factory=list)
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RunCreate(BaseModel):
    """Request body for creating a run."""
    run_id: str
    pipeline: str
    input: Dict[str, Any]
    output: Optional[Any] = None
    status: str = "completed"
    error: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_ms: Optional[int] = None
    steps: List[StepCreate] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


# --- Response Models ---

class RunSummary(BaseModel):
    """Summary of a run (for list views)."""
    run_id: str
    pipeline: str
    status: str
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_ms: Optional[int] = None
    step_count: int = 0


class StepSummary(BaseModel):
    """Summary of a step (for cross-run queries)."""
    run_id: str
    pipeline: str
    step_name: str
    step_type: Optional[str] = None
    input_count: Optional[int] = None
    output_count: Optional[int] = None
    rejection_rate: Optional[float] = None
    duration_ms: Optional[int] = None


class RunDetail(BaseModel):
    """Full details of a run."""
    run_id: str
    pipeline: str
    input: Dict[str, Any]
    output: Optional[Any] = None
    status: str
    error: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_ms: Optional[int] = None
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ApiResponse(BaseModel):
    """Standard API response wrapper."""
    success: bool
    message: Optional[str] = None
    data: Optional[Any] = None


class RunListResponse(BaseModel):
    """Response for listing runs."""
    runs: List[RunSummary]
    total: int
    limit: int
    offset: int


class StepListResponse(BaseModel):
    """Response for listing steps."""
    steps: List[StepSummary]
    total: int
    limit: int
    offset: int
