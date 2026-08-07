import threading
from pathlib import Path

_log_path: Path | None = None
_redact = False
_lock = threading.Lock()


def set_log_path(path: Path | None, redact: bool = False) -> None:
    """Set (or clear, with None) the active per-job log file. redact=True
    limits logged detail to command name + exit code only -- for secure
    mode, which must never write full argument lists or captured output to
    a log file, since either could contain sensitive filenames/content."""
    global _log_path, _redact
    with _lock:
        _log_path = path
        _redact = redact
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)


def log_subprocess(cmd: list[str], returncode: int, stdout: str, stderr: str) -> None:
    with _lock:
        if _log_path is None:
            return
        with _log_path.open("a") as f:
            if _redact:
                f.write(f"$ {cmd[0]} ... (args/output redacted, secure mode)\n")
                f.write(f"exit: {returncode}\n\n")
                return
            f.write(f"$ {' '.join(cmd)}\n")
            f.write(f"exit: {returncode}\n")
            if stdout:
                f.write(f"stdout:\n{stdout}\n")
            if stderr:
                f.write(f"stderr:\n{stderr}\n")
            f.write("\n")
