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
