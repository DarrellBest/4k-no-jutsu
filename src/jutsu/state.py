import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class JobState:
    path: Path
    total_windows: int
    _done: set[int] = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text())
            self._done = set(data.get("done_windows", []))

    def is_window_done(self, index: int) -> bool:
        return index in self._done

    def mark_window_done(self, index: int) -> None:
        self._done.add(index)
        self._save()

    def _save(self) -> None:
        self.path.write_text(
            json.dumps({"total_windows": self.total_windows, "done_windows": sorted(self._done)})
        )
