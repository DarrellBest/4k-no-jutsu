import json
import threading
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class JobState:
    path: Path
    total_windows: int
    _done: set[int] = field(default_factory=set, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text())
            self._done = set(data.get("done_windows", []))

    def is_window_done(self, index: int) -> bool:
        return index in self._done

    def mark_window_done(self, index: int) -> None:
        # Concurrent window processing (run_pipeline with max_workers>1) calls
        # this from multiple threads at once. Without the lock, interleaved
        # read-truncate-write of the same file can corrupt or clobber updates
        # (observed directly: ~40% failure rate on unlocked code under test).
        with self._lock:
            self._done.add(index)
            self._save()

    def _save(self) -> None:
        self.path.write_text(
            json.dumps({"total_windows": self.total_windows, "done_windows": sorted(self._done)})
        )
