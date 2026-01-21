"""
Performance timer utility for tracking operation durations.
"""

import time


class SearchTimer:
    """Simple timer for tracking search performance metrics."""

    def __init__(self) -> None:
        self.start = time.time()
        self.logs: dict[str, float] = {}
        self.last_mark = self.start

    def mark(self, step_name: str) -> None:
        """Record time elapsed since last mark in milliseconds."""
        now = time.time()
        self.logs[step_name] = round((now - self.last_mark) * 1000, 2)
        self.last_mark = now

    def total(self) -> float:
        """Get total elapsed time in milliseconds."""
        return round((time.time() - self.start) * 1000, 2)
