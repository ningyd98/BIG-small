from __future__ import annotations

import json
import subprocess
import sys


def test_isaac_standalone_app_reports_blocked_without_isaac_runtime() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/phase9/isaac_standalone_app.py", "--check-imports"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] in {"BLOCKED_BY_ENV", "READY"}
    assert payload["validation_claimed"] is False
    if payload["status"] == "BLOCKED_BY_ENV":
        assert "Isaac Sim Python modules are unavailable" in payload["message"]
