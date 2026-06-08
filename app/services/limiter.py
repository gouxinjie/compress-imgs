from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta


class SimpleRateLimiter:
    def __init__(self, limit_per_minute: int) -> None:
        self.limit_per_minute = limit_per_minute
        self._records: dict[str, deque[datetime]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=1)
        records = self._records[key]

        while records and records[0] < window_start:
            records.popleft()

        if len(records) >= self.limit_per_minute:
            return False

        records.append(now)
        return True
