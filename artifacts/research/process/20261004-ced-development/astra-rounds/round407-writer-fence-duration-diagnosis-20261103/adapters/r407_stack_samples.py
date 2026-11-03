"""Low-frequency native stacks; preserves the test's existing Python observers."""
import faulthandler
import json
import os
from pathlib import Path
import sys
import threading
import pytest

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    hooks = (sys.getprofile(),threading.getprofile(),sys.gettrace(),threading.gettrace())
    assert all(value is None for value in hooks)
    prerequisite = json.loads(Path(os.environ["BIGSMALL_R235_PREREQUISITE_RECORD"]).read_text())
    assert prerequisite["accepted_prerequisite"]
    path = Path(os.environ["R407_STACKS"])
    with path.open("x") as stream:
        faulthandler.dump_traceback_later(20,repeat=True,exit=False,file=stream)
        try:
            yield
        finally:
            faulthandler.cancel_dump_traceback_later()
    after = (sys.getprofile(),threading.getprofile(),sys.gettrace(),threading.gettrace())
    record = {"hooks_empty_before":all(value is None for value in hooks),"hooks_restored":all(x is y for x,y in zip(hooks,after)),"timer_cancelled":True,"sampling_seconds":20,"repeat":True,"exit_on_sample":False}
    with (path.parent / "stacks-observer.json").open("x") as out:
        json.dump(record,out,indent=2)
