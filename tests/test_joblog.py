from jutsu import joblog


def test_log_subprocess_writes_command_exit_and_output(tmp_path):
    log_path = tmp_path / "job.log"
    joblog.set_log_path(log_path)

    joblog.log_subprocess(["ffmpeg", "-i", "in.mp4", "out.mp4"], 0, "some stdout", "some stderr")

    content = log_path.read_text()
    assert "ffmpeg -i in.mp4 out.mp4" in content
    assert "exit: 0" in content
    assert "some stdout" in content
    assert "some stderr" in content


def test_log_subprocess_appends_across_multiple_calls(tmp_path):
    log_path = tmp_path / "job.log"
    joblog.set_log_path(log_path)

    joblog.log_subprocess(["cmd1"], 0, "", "")
    joblog.log_subprocess(["cmd2"], 0, "", "")

    content = log_path.read_text()
    assert "cmd1" in content
    assert "cmd2" in content


def test_log_subprocess_is_noop_when_no_path_set(tmp_path):
    joblog.set_log_path(None)
    # Must not raise even though there's nowhere to write.
    joblog.log_subprocess(["cmd"], 0, "stdout", "stderr")


def test_log_subprocess_redacts_args_and_output_in_secure_mode(tmp_path):
    log_path = tmp_path / "job.log"
    joblog.set_log_path(log_path, redact=True)

    joblog.log_subprocess(
        ["ffmpeg", "-i", "/secret/vault/private_video.mp4", "out.mp4"],
        0, "sensitive stdout content", "sensitive stderr content",
    )

    content = log_path.read_text()
    assert "ffmpeg" in content
    assert "exit: 0" in content
    assert "/secret/vault/private_video.mp4" not in content
    assert "sensitive stdout content" not in content
    assert "sensitive stderr content" not in content
