"""R405 passive observer, enabled only after startup and target entry."""
from collections import deque
import json
import os
from pathlib import Path
import sys
import threading
import pytest

NAMES = {"_consume_transition", "_check_reference", "check", "_check_live", "_check_app_live", "_validate_references"}

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    if item.nodeid != "tests/test_operational_windows.py::test_foreign_thread_has_no_owner_context":
        yield
        return
    previous = sys.gettrace()
    hooks = (previous, sys.getprofile(), threading.gettrace(), threading.getprofile())
    prior_empty = all(value is None for value in hooks)
    prerequisite = json.loads(Path(os.environ["BIGSMALL_R235_PREREQUISITE_RECORD"]).read_text())
    assert prior_empty and prerequisite["accepted_prerequisite"], "Original startup prerequisite required"
    exceptions, boundaries = deque(), deque()
    dropped = {"exceptions":0,"boundaries":0}
    errors = []
    target = False
    captured_returned = False
    critical = {}
    used = 0
    sequence = 0

    def record(group, row):
        nonlocal used, sequence
        sequence += 1
        row["sequence"] = sequence
        raw = json.dumps(row,ensure_ascii=False)
        pair = (len(raw.encode()),row)
        ring = exceptions if group == "exceptions" else boundaries
        if len(ring) >= 128:
            used -= ring.popleft()[0]
            dropped[group] += 1
        while used + pair[0] > 240000 and (exceptions or boundaries):
            other = exceptions if exceptions else boundaries
            label = "exceptions" if exceptions else "boundaries"
            used -= other.popleft()[0]
            dropped[label] += 1
        ring.append(pair)
        used += pair[0]

    def trace(frame,event,arg):
        nonlocal target,captured_returned
        try:
            frame.f_trace_lines = False
            filename,name = frame.f_code.co_filename,frame.f_code.co_name
            selected_test = filename.endswith("/tests/test_operational_windows.py")
            product = "/cloud_edge_robot_arm/" in filename
            if not (product or selected_test):
                return None
            if selected_test and name == "captured" and event == "call":
                target = True
                record("boundaries",{"event":"target_entered","file":filename,"function":name,"line":frame.f_lineno})
            if not target:
                return trace
            row = {"event":event,"file":filename,"function":name,"line":frame.f_lineno,"thread_id":threading.get_ident()}
            if selected_test and name == "captured" and event == "return":
                captured_returned = arg is not None
                record("boundaries",{**row,"captured_returned_value":captured_returned})
            if event == "exception" and arg[0].__name__ not in {"StopIteration","GeneratorExit"}:
                row.update(error_type=arg[0].__name__,message=str(arg[1])[:512])
                mode = frame.f_locals.get("mode")
                if type(mode) is str:
                    row["mode"] = mode
                record("exceptions",row)
                if name == "_consume_transition":
                    critical["consume_exception"] = row
                if name == "_check_reference" and row["message"] == "unsupported live operational owner mode":
                    critical["unsupported_mode_exception"] = row
            elif name in NAMES and event in {"call","return"}:
                if event == "return":
                    attrs = getattr(arg,"__dict__",{})
                    row["verdict"] = {key:value for key,value in attrs.items() if key in {"status","reasons"} and type(value) in {str,tuple}}
                    if name == "_check_reference":
                        critical["last_check_reference_return"] = row
                record("boundaries",row)
            return trace
        except BaseException as error:
            if len(errors) < 16:
                errors.append(type(error).__name__)
            return None
    try:
        sys.settrace(trace)
        yield
    finally:
        sys.settrace(previous)
        rows = sorted([pair[1] for pair in exceptions]+[pair[1] for pair in boundaries],key=lambda row:row["sequence"])
        summary = {"observer_summary":True,"errors":errors,"target_entered":target,
             "captured_returned":captured_returned,"prior_hooks_empty":prior_empty,
             "restored":sys.gettrace() is previous,"records":len(rows),"dropped":dropped,"critical":critical}
        data = "".join(json.dumps(row,ensure_ascii=False)+"\n" for row in rows+[summary])
        assert len(data.encode()) <= 262144,"Observer bounded output exceeded"
        with Path(os.environ["R405_OBSERVATIONS"]).open("x") as out:
            out.write(data)
