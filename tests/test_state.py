import json
import threading
import time
from pathlib import Path as PathType

from jutsu.state import JobState


def test_fresh_state_has_no_windows_done(tmp_path):
    state = JobState(tmp_path / "state.json", total_windows=5)
    assert state.is_window_done(0) is False


def test_mark_and_check_window_done(tmp_path):
    state = JobState(tmp_path / "state.json", total_windows=5)
    state.mark_window_done(2)
    assert state.is_window_done(2) is True
    assert state.is_window_done(3) is False


def test_state_persists_across_instances(tmp_path):
    path = tmp_path / "state.json"
    first = JobState(path, total_windows=5)
    first.mark_window_done(1)
    first.mark_window_done(4)

    second = JobState(path, total_windows=5)
    assert second.is_window_done(1) is True
    assert second.is_window_done(4) is True
    assert second.is_window_done(0) is False


def test_mark_window_done_thread_safe_under_concurrent_writes(tmp_path, monkeypatch):
    # Concurrent window processing (run_pipeline with max_workers>1) calls
    # mark_window_done from multiple threads at once. Each call does a
    # read-modify-write of the same on-disk JSON file; without synchronization,
    # interleaved writes can corrupt or clobber each other. Real OS thread
    # scheduling only exposes this intermittently (observed ~25% failure rate
    # on the unlocked code, not reliable enough as a regression test), so we
    # force reliable interleaving: every write_text call sleeps briefly first,
    # guaranteeing many threads are mid-write at the same time if unlocked.
    original_write_text = PathType.write_text

    def slow_write_text(self, *args, **kwargs):
        time.sleep(0.01)
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(PathType, "write_text", slow_write_text)

    path = tmp_path / "state.json"
    state = JobState(path, total_windows=50)

    threads = [threading.Thread(target=state.mark_window_done, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for i in range(50):
        assert state.is_window_done(i), f"window {i} missing from in-memory state after concurrent writes"

    # Reload from disk (not the in-memory instance) to catch a race that lost
    # a write to the file itself, even if the in-memory set looks complete.
    on_disk = json.loads(path.read_text())
    assert sorted(on_disk["done_windows"]) == list(range(50)), (
        f"expected all 50 windows persisted, got {sorted(on_disk['done_windows'])}"
    )
