"""
Step - Represents a single stage in a pipeline run.

A Step tracks inputs, outputs, rejections, acceptances, and decisions.
"""

import random
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .run import Run


class Step:
    """
    Context manager for a pipeline step.

    Usage:
        with run.step("filter_candidates", step_type="filter") as step:
            step.set_input_count(len(candidates))
            for item in candidates:
                if not passes_filter(item):
                    step.reject(item.id, "low_score", {"score": item.score})
            step.set_output_count(len(filtered))
    """

    # Default sample rate for rejected items (1%)
    DEFAULT_SAMPLE_RATE = 0.01
    # Minimum samples per rejection reason
    MIN_SAMPLES_PER_REASON = 5
    # Maximum samples per rejection reason
    MAX_SAMPLES_PER_REASON = 20

    def __init__(
        self,
        name: str,
        step_type: Optional[str],
        capture: str,
        run: "Run"
    ):
        self.name = name
        self.step_type = step_type
        self.capture = capture
        self._run = run

        self._input: Optional[Dict[str, Any]] = None
        self._output: Optional[Dict[str, Any]] = None
        self._input_count: Optional[int] = None
        self._output_count: Optional[int] = None

        # Rejections: stored with sampling
        self._rejections: List[Dict[str, Any]] = []
        self._rejection_counts: Dict[str, int] = {}
        self._rejection_samples: Dict[str, List[Dict[str, Any]]] = {}

        # Acceptances: always stored (smaller set)
        self._acceptances: List[Dict[str, Any]] = []

        # Decisions: always stored
        self._decisions: List[Dict[str, Any]] = []

        self._started_at = datetime.utcnow()
        self._ended_at: Optional[datetime] = None
        self._error: Optional[str] = None
        self._metadata: Dict[str, Any] = {}

    def __enter__(self) -> "Step":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._ended_at = datetime.utcnow()

        if exc_type is not None:
            self._error = str(exc_val)

        # Register this step with the parent run
        self._run._add_step(self._to_dict())

        # Don't suppress exceptions
        return False

    def set_input(self, input_data: Dict[str, Any]) -> None:
        """Set the input for this step."""
        self._input = input_data

    def set_output(self, output_data: Dict[str, Any]) -> None:
        """Set the output for this step."""
        self._output = output_data

    def set_input_count(self, count: int) -> None:
        """Set the number of items entering this step."""
        self._input_count = count

    def set_output_count(self, count: int) -> None:
        """Set the number of items leaving this step."""
        self._output_count = count

    def reject(
        self,
        item_id: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record that an item was rejected.

        Args:
            item_id: Unique identifier for the rejected item
            reason: Reason code for rejection (e.g., "price_too_high")
            details: Optional additional details about the rejection
        """
        # Always update counts
        self._rejection_counts[reason] = self._rejection_counts.get(reason, 0) + 1

        # Sample based on capture mode
        if self.capture == "full":
            should_sample = True
        elif self.capture == "none":
            should_sample = False
        else:  # "sample" mode
            should_sample = self._should_sample(reason)

        if should_sample:
            rejection = {
                "item_id": item_id,
                "reason": reason,
                "details": details or {},
                "timestamp": datetime.utcnow().isoformat()
            }

            if reason not in self._rejection_samples:
                self._rejection_samples[reason] = []

            # Only keep up to MAX_SAMPLES_PER_REASON
            if len(self._rejection_samples[reason]) < self.MAX_SAMPLES_PER_REASON:
                self._rejection_samples[reason].append(rejection)

    def accept(
        self,
        item_id: str,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record that an item was accepted.

        Args:
            item_id: Unique identifier for the accepted item
            reason: Optional reason for acceptance
            details: Optional additional details
        """
        acceptance = {
            "item_id": item_id,
            "reason": reason,
            "details": details or {},
            "timestamp": datetime.utcnow().isoformat()
        }
        self._acceptances.append(acceptance)

    def decide(
        self,
        decision: str,
        selected: Optional[str] = None,
        reason: Optional[str] = None,
        score: Optional[float] = None,
        alternatives: Optional[List[Dict[str, Any]]] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record a decision made in this step.

        Args:
            decision: What was decided (e.g., "select_best", "rank", "categorize")
            selected: ID of the selected item (if applicable)
            reason: Why this decision was made
            score: Score or confidence of the decision
            alternatives: Other options that were considered
            details: Additional details about the decision
        """
        decision_data = {
            "decision": decision,
            "selected": selected,
            "reason": reason,
            "score": score,
            "alternatives": alternatives,
            "details": details or {},
            "timestamp": datetime.utcnow().isoformat()
        }
        self._decisions.append(decision_data)

    def set_metadata(self, key: str, value: Any) -> None:
        """Add metadata to this step."""
        self._metadata[key] = value

    def _should_sample(self, reason: str) -> bool:
        """
        Determine if a rejection should be sampled.

        Ensures minimum samples per reason while respecting overall sample rate.
        """
        current_samples = len(self._rejection_samples.get(reason, []))
        current_count = self._rejection_counts.get(reason, 0)

        # Always sample if below minimum
        if current_samples < self.MIN_SAMPLES_PER_REASON:
            return True

        # Don't exceed maximum
        if current_samples >= self.MAX_SAMPLES_PER_REASON:
            return False

        # Random sampling based on rate
        return random.random() < self.DEFAULT_SAMPLE_RATE

    def _calculate_rejection_rate(self) -> Optional[float]:
        """Calculate the rejection rate for this step."""
        if self._input_count is None or self._output_count is None:
            return None
        if self._input_count == 0:
            return 0.0
        return 1 - (self._output_count / self._input_count)

    def _to_dict(self) -> Dict[str, Any]:
        """Convert step to dictionary for storage."""
        # Flatten sampled rejections
        sampled_rejections = []
        for reason, samples in self._rejection_samples.items():
            sampled_rejections.extend(samples)

        return {
            "name": self.name,
            "step_type": self.step_type,
            "input": self._input,
            "output": self._output,
            "input_count": self._input_count,
            "output_count": self._output_count,
            "rejection_rate": self._calculate_rejection_rate(),
            "rejection_counts": self._rejection_counts,
            "sampled_rejections": sampled_rejections,
            "acceptances": self._acceptances,
            "decisions": self._decisions,
            "started_at": self._started_at.isoformat(),
            "ended_at": self._ended_at.isoformat() if self._ended_at else None,
            "duration_ms": self._calculate_duration(),
            "error": self._error,
            "metadata": self._metadata
        }

    def _calculate_duration(self) -> Optional[int]:
        """Calculate step duration in milliseconds."""
        if self._ended_at is None:
            return None
        delta = self._ended_at - self._started_at
        return int(delta.total_seconds() * 1000)
