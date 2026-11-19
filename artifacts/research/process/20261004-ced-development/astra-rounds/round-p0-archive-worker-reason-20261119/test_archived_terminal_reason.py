"""Negative controls for derivation from three terminal records."""

from pathlib import Path
from runpy import run_path

import pytest

SCRIPT = (
    Path(__file__).resolve().parent.parent / "round-p0-archived-three-20261119/read_archived.py"
)
FILES = ("worker/result.json", "component/episode.json", "result.json")


class TerminalSources(dict):
    def json(self, path):
        return self[path]


def read_terminal(rows):
    return run_path(str(SCRIPT))["original_worker_terminal"](rows)


@pytest.mark.parametrize("reason", [None, "ValueError"])
def test_binds_three_original_terminal_records(reason):
    files = TerminalSources({path: {"terminal_reason": reason} for path in FILES})
    result = read_terminal(files)
    assert result["sources"] == dict.fromkeys(FILES, reason)
    assert result["online_exception_message"] is None
    assert result["online_exception_stack"] is None


@pytest.mark.parametrize("path", FILES)
def test_rejects_missing_key(path):
    files = TerminalSources({name: {"terminal_reason": "ValueError"} for name in FILES})
    del files[path]["terminal_reason"]
    with pytest.raises(ValueError, match="terminal_reason missing"):
        read_terminal(files)


@pytest.mark.parametrize("path", FILES)
def test_rejects_conflicting_terminal_sources(path):
    files = TerminalSources({name: {"terminal_reason": "ValueError"} for name in FILES})
    files[path]["terminal_reason"] = None
    with pytest.raises(ValueError, match="conflicting terminal_reason"):
        read_terminal(files)
