"""
XRay SDK - Main entry point for pipeline instrumentation.

Usage:
    from sdk import XRay

    xray = XRay("my_pipeline")
    with xray.run(input={"product": "iPhone Case"}) as run:
        result = my_pipeline()
        run.set_output(result)
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from .run import Run


class XRay:
    """
    Main X-Ray client for instrumenting pipelines.

    Attributes:
        pipeline: Name of the pipeline being instrumented
        api_url: URL of the X-Ray API server
        offline_mode: What to do when API is unavailable
            - "buffer": Save locally, sync later (default)
            - "drop": Silently drop data
            - "strict": Raise error
    """

    def __init__(
        self,
        pipeline: str,
        api_url: str = "http://localhost:8000",
        offline_mode: str = "buffer"
    ):
        self.pipeline = pipeline
        self.api_url = api_url.rstrip("/")
        self.offline_mode = offline_mode
        self._offline_dir = Path.home() / ".xray" / "offline"

    def run(self, input: Dict[str, Any], run_id: Optional[str] = None) -> Run:
        """
        Start a new pipeline run.

        Args:
            input: The input data for this run
            run_id: Optional custom run ID (auto-generated if not provided)

        Returns:
            Run context manager
        """
        if run_id is None:
            run_id = f"run_{uuid.uuid4().hex[:12]}"

        return Run(
            run_id=run_id,
            pipeline=self.pipeline,
            input=input,
            xray=self
        )

    def _send_run(self, run_data: Dict[str, Any]) -> bool:
        """
        Send run data to the API.

        Returns True if successful, False otherwise.
        """
        try:
            response = requests.post(
                f"{self.api_url}/runs",
                json=run_data,
                timeout=5
            )
            return response.status_code == 200 or response.status_code == 201
        except requests.exceptions.RequestException:
            return False

    def _save_offline(self, run_data: Dict[str, Any]) -> None:
        """Save run data to local file for later sync."""
        self._offline_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{run_data['run_id']}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self._offline_dir / filename

        with open(filepath, "w") as f:
            json.dump(run_data, f, indent=2, default=str)

    def sync_offline(self) -> Dict[str, int]:
        """
        Sync offline runs to the API.

        Returns:
            Dict with counts: {"synced": N, "failed": M}
        """
        if not self._offline_dir.exists():
            return {"synced": 0, "failed": 0}

        synced = 0
        failed = 0

        for filepath in self._offline_dir.glob("*.json"):
            try:
                with open(filepath) as f:
                    run_data = json.load(f)

                if self._send_run(run_data):
                    filepath.unlink()  # Delete after successful sync
                    synced += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

        return {"synced": synced, "failed": failed}
