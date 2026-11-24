import runpy
from pathlib import Path

import pytest


def module():
    return runpy.run_path(str(Path(__file__).with_name("independent_gate.py")))


def test_duplicate_worker_pid_does_not_sign_two_reads():
    verify = module()["pair_receipt"]
    with pytest.raises(ValueError, match="independent"):
        verify([{"pid": 8, "exit_code": 0, "sha256": "a"}] * 2)
    with pytest.raises(ValueError, match="independent"):
        verify([{"pid": 8, "exit_code": 0, "sha256": "a"}, {"pid": 9, "exit_code": 0, "sha256": "b"}])


def test_equal_content_requires_clean_exits_and_distinct_processes():
    v = module()["pair_receipt"]
    assert v([{"pid": 8, "exit_code": 0, "sha256": "a"}, {"pid": 9, "exit_code": 0, "sha256": "a"}]) == "a"
    with pytest.raises(ValueError):
        v([{"pid": 8, "exit_code": 1, "sha256": "a"}, {"pid": 9, "exit_code": 0, "sha256": "a"}])

