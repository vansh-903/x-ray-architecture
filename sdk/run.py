"""
Run - Represents a single pipeline execution.

A Run contains multiple Steps and tracks the overall input/output of the pipeline.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .step import Step

if TYPE_CHECKING:
    from .xray import XRay


class Run:
    """
    Context manager for a pipeline run.

    Usage:
        with xray.run(input={"product": "iPhone"}) as run:
            # pipeline code here
            run.set_output(result)
    """

    def __init__(
        self,
        run_id: str,
        pipeline: str,
        input: Dict[str, Any],
        xray: "XRay"
    ):
        self.run_id = run_id
        self.pipeline = pipeline
        self.input = input
        self._xray = xray

        self._output: Optional[Dict[str, Any]] = None
        self._status = "running"
        self._steps: List[Dict[str, Any]] = []
        self._started_at = datetime.utcnow()
        self._ended_at: Optional[datetime] = None
        self._error: Optional[str] = None
        self._metadata: Dict[str, Any] = {}

    def __enter__(self) -> "Run":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._ended_at = datetime.utcnow()

        if exc_type is not None:
            self._status = "failed"
            self._error = str(exc_val)
        else:
            self._status = "completed"

        self._send()

        # Don't suppress exceptions
        return False

    def step(
        self,
        name: str,
        step_type: Optional[str] = None,
        capture: str = "sample"
    ) -> Step:
        """
        Create a new step within this run.

        Args:
            name: Name of the step (e.g., "filter_candidates")
            step_type: Type of step for cross-pipeline queries
                      Options: "filter", "transform", "select", "generate", "rank"
            capture: Capture mode for rejected items
                    Options: "sample" (default), "full", "none"

        Returns:
            Step context manager
        """
        step = Step(
            name=name,
            step_type=step_type,
            capture=capture,
            run=self
        )
        return step

    def set_output(self, output: Any) -> None:
        """Set the final output of this run."""
        self._output = output

    def set_metadata(self, key: str, value: Any) -> None:
        """Add metadata to this run."""
        self._metadata[key] = value

    def _add_step(self, step_data: Dict[str, Any]) -> None:
        """Called by Step when it completes."""
        self._steps.append(step_data)

    def _send(self) -> None:
        """Send run data to the API."""
        run_data = {
            "run_id": self.run_id,
            "pipeline": self.pipeline,
            "input": self.input,
            "output": self._output,
            "status": self._status,
            "error": self._error,
            "started_at": self._started_at.isoformat(),
            "ended_at": self._ended_at.isoformat() if self._ended_at else None,
            "duration_ms": self._calculate_duration(),
            "steps": self._steps,
            "metadata": self._metadata
        }

        success = self._xray._send_run(run_data)

        if not success:
            if self._xray.offline_mode == "buffer":
                self._xray._save_offline(run_data)
            elif self._xray.offline_mode == "strict":
                raise ConnectionError(f"Failed to send run data to {self._xray.api_url}")
            # "drop" mode: silently ignore

    def _calculate_duration(self) -> Optional[int]:
        """Calculate run duration in milliseconds."""
        if self._ended_at is None:
            return None
        delta = self._ended_at - self._started_at
        return int(delta.total_seconds() * 1000)

    def to_dict(self) -> Dict[str, Any]:
        """Convert run to dictionary."""
        return {
            "run_id": self.run_id,
            "pipeline": self.pipeline,
            "input": self.input,
            "output": self._output,
            "status": self._status,
            "steps": self._steps,
            "metadata": self._metadata
        }
