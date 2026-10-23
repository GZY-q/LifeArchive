import os
import subprocess
import sys
from pathlib import Path


def test_worker_exits_cleanly_without_database_or_scheduler(tmp_path: Path) -> None:
    environment = os.environ | {"LIFEARCHIVE_LOG_LEVEL": "INFO"}
    result = subprocess.run(
        [sys.executable, "-m", "life_archive.worker"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 0
    assert "M0 worker placeholder: no jobs or scheduler configured; exiting." in result.stderr
