"""Bounded passive call observations; no product replacement."""
import json
import os
from pathlib import Path
import sys
import threading
import pytest

NAMES = {"_check_reference", "_check_live", "_check_app_live", "check", "_validate_references", "_consume_transition", "_descriptor_plain"}

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    previous = sys.gettrace()
    rows, errors = [], []
    truncated = False
    used = 0
    def trace(frame, event, arg):
        nonlocal truncated, used
        try:
            frame.f_trace_lines = False
            filename, name = frame.f_code.co_filename, frame.f_code.co_name
            relevant = "/cloud_edge_robot_arm/" in filename or filename.endswith("test_operational_windows.py")
            if not relevant:
                return None
            selected = name in NAMES
            if event == "exception" or (selected and event in {"call", "return"}):
                row = {"event": event, "file": filename, "function": name, "line": frame.f_lineno, "thread_id": threading.get_ident()}
                if event == "exception":
                    row.update(error_type=arg[0].__name__, message=str(arg[1])[:240])
                elif event == "return":
                    attrs = getattr(arg, "__dict__", {})
                    row["verdict"] = {key: value for key, value in attrs.items() if key in {"status", "reason", "reasons"} and type(value) in {str, int, bool, tuple, list}}
                encoded = json.dumps(row, default=str)
                if len(rows) >= 256 or used + len(encoded.encode()) > 250000:
                    truncated = True
                else:
                    rows.append(row)
                    used += len(encoded.encode())
            return trace
        except BaseException as exc:
            errors.append(type(exc).__name__)
            return None
    try:
        sys.settrace(trace)
        yield
    finally:
        sys.settrace(previous)
        with Path(os.environ["R403_OBSERVATIONS"]).open("x") as out:
            for row in rows:
                out.write(json.dumps(row, default=str) + "\n")
            out.write(json.dumps({"observer_summary": True, "errors": errors[:16], "truncated": truncated, "records": len(rows), "prior_trace_was_none": previous is None, "restored": sys.gettrace() is previous}) + "\n")
