"""JSONL dataset recorder: one record per Laya inference, for external labeling.

Each record is appended with an open/write/close cycle under a lock so external
tools can tail or edit the file at any time. Write failures never break the
pipeline; they are logged and reported via the return value.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


class Recorder:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def append(self, record: dict) -> bool:
        try:
            line = json.dumps(record, ensure_ascii=False)
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            return True
        except OSError as exc:
            logger.error("dataset write failed (%s): %s", self.path, exc)
            return False
