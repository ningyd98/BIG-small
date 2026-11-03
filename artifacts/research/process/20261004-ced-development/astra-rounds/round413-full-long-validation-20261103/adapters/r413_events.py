"""R413 record-only pytest events; preserves tests, markers and assertions."""
import json
import os
from pathlib import Path
from datetime import datetime, UTC

def record(value):
    value["at_utc"]=datetime.now(UTC).isoformat()
    with Path(os.environ["R413_PYTEST_EVENTS"]).open("a",encoding="utf-8") as f:
        f.write(json.dumps(value,ensure_ascii=False)+"\n")

def pytest_collection_finish(session):
    record({"event":"collection_finished","nodeids":[i.nodeid for i in session.items],"collection_errors":session.testsfailed})

def pytest_deselected(items):
    for item in items:record({"event":"deselected","nodeid":item.nodeid,"markers":sorted({m.name for m in item.iter_markers()})})

def pytest_runtest_logstart(nodeid,location):
    record({"event":"started","nodeid":nodeid})

def pytest_runtest_logreport(report):
    record({"event":"report","nodeid":report.nodeid,"when":report.when,"outcome":report.outcome,"duration_s":report.duration,"longrepr":str(report.longrepr) if report.failed or report.skipped else None})

def pytest_sessionfinish(session,exitstatus):
    record({"event":"finished","exitstatus":int(exitstatus)})
