"""Record original pytest outcomes and selection without changing assertions."""
import json
import os
from pathlib import Path


def record(value):
    with Path(os.environ['R373_PYTEST_EVENTS']).open('a') as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + '\n')


def pytest_deselected(items):
    for item in items:
        record({'event': 'deselected', 'nodeid': item.nodeid,
                'markers': sorted(marker.name for marker in item.iter_markers())})


def pytest_runtest_logstart(nodeid, location):
    record({'event': 'started', 'nodeid': nodeid})


def pytest_runtest_logreport(report):
    record({'event': 'report', 'nodeid': report.nodeid, 'when': report.when,
            'outcome': report.outcome, 'duration': report.duration,
            'longrepr': str(report.longrepr) if report.failed else None})


def pytest_sessionfinish(session, exitstatus):
    record({'event': 'finished', 'exitstatus': int(exitstatus)})
