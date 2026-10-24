"""R351 single reserved offline forensic attempt; never application execution."""
import time
STARTED = time.monotonic()

import base64
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import stat
import subprocess
import sys
import traceback

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = Path(__file__).absolute().parent.parent
IMPL = D / "implementation"
OUT = D / "diagnostic/offline_db_01"
AUTHOR = IMPL / "author-diagnostic-ledger.json"
BINDING = IMPL / "author-binding.json"
IDENTITY = "R351:offline_db_01"
KEY = "offline_db_01"
PLAN_SHA = "53962dbec04478d1be52fd76732c1e06b674a2bf6400b8c7c86be9d47ba1a0c1"
HEAD = "729bce11bbd55a4a869e25e52174da3d0db1825b"
BRANCH = "research/20261004-continuation"
INNER_DEADLINE = STARTED + 60
QUERY_DEADLINE = STARTED + 50
OUTPUT_CAP = 16777216
STORAGE_CAP = 67108864
FINAL_RESERVE = 262144
PAYLOAD_CAP = 262144
HELD = "HELD_PENDING_ROOT_SCRIPT_REVIEW_AND_INDIVIDUAL_RESERVATION"

QUERIES = [{'database': 'runtime',
  'id': 'schema',
  'sql': "SELECT name, sql FROM sqlite_master WHERE type='table' AND name IN "
         "('simulation_jobs','simulation_job_leases','simulation_job_attempts','simulation_job_events','simulation_operational_leases_v1','simulation_local_publications_v1','simulation_publication_confirmations_v1') "
         'ORDER BY name LIMIT 7',
  'row_limit': 7,
  'table': None,
  'required_columns': [],
  'seconds_max': 3},
 {'database': 'runtime',
  'id': 'columns:simulation_jobs',
  'sql': "PRAGMA table_info('simulation_jobs')",
  'row_limit': 64,
  'table': 'simulation_jobs',
  'required_columns': [],
  'seconds_max': 3},
 {'database': 'runtime',
  'id': 'columns:simulation_job_leases',
  'sql': "PRAGMA table_info('simulation_job_leases')",
  'row_limit': 64,
  'table': 'simulation_job_leases',
  'required_columns': [],
  'seconds_max': 3},
 {'database': 'runtime',
  'id': 'columns:simulation_job_attempts',
  'sql': "PRAGMA table_info('simulation_job_attempts')",
  'row_limit': 64,
  'table': 'simulation_job_attempts',
  'required_columns': [],
  'seconds_max': 3},
 {'database': 'runtime',
  'id': 'columns:simulation_job_events',
  'sql': "PRAGMA table_info('simulation_job_events')",
  'row_limit': 64,
  'table': 'simulation_job_events',
  'required_columns': [],
  'seconds_max': 3},
 {'database': 'runtime',
  'id': 'columns:simulation_operational_leases_v1',
  'sql': "PRAGMA table_info('simulation_operational_leases_v1')",
  'row_limit': 64,
  'table': 'simulation_operational_leases_v1',
  'required_columns': [],
  'seconds_max': 3},
 {'database': 'runtime',
  'id': 'columns:simulation_local_publications_v1',
  'sql': "PRAGMA table_info('simulation_local_publications_v1')",
  'row_limit': 64,
  'table': 'simulation_local_publications_v1',
  'required_columns': [],
  'seconds_max': 3},
 {'database': 'runtime',
  'id': 'columns:simulation_publication_confirmations_v1',
  'sql': "PRAGMA table_info('simulation_publication_confirmations_v1')",
  'row_limit': 64,
  'table': 'simulation_publication_confirmations_v1',
  'required_columns': [],
  'seconds_max': 3},
 {'database': 'events',
  'id': 'schema',
  'sql': "SELECT name, sql FROM sqlite_master WHERE type='table' AND name IN "
         "('visual_local_tasks_v1','visual_local_publications_v1','visual_bootstraps','visual_supervision','visual_owner_publications') "
         'ORDER BY name LIMIT 5',
  'row_limit': 5,
  'table': None,
  'required_columns': [],
  'seconds_max': 3},
 {'database': 'events',
  'id': 'columns:visual_local_tasks_v1',
  'sql': "PRAGMA table_info('visual_local_tasks_v1')",
  'row_limit': 64,
  'table': 'visual_local_tasks_v1',
  'required_columns': [],
  'seconds_max': 3},
 {'database': 'events',
  'id': 'columns:visual_local_publications_v1',
  'sql': "PRAGMA table_info('visual_local_publications_v1')",
  'row_limit': 64,
  'table': 'visual_local_publications_v1',
  'required_columns': [],
  'seconds_max': 3},
 {'database': 'events',
  'id': 'columns:visual_bootstraps',
  'sql': "PRAGMA table_info('visual_bootstraps')",
  'row_limit': 64,
  'table': 'visual_bootstraps',
  'required_columns': [],
  'seconds_max': 3},
 {'database': 'events',
  'id': 'columns:visual_supervision',
  'sql': "PRAGMA table_info('visual_supervision')",
  'row_limit': 64,
  'table': 'visual_supervision',
  'required_columns': [],
  'seconds_max': 3},
 {'database': 'events',
  'id': 'columns:visual_owner_publications',
  'sql': "PRAGMA table_info('visual_owner_publications')",
  'row_limit': 64,
  'table': 'visual_owner_publications',
  'required_columns': [],
  'seconds_max': 3},
 {'database': 'runtime',
  'id': 'jobs',
  'sql': 'SELECT '
         'job_id,run_id,status,attempt,worker_id,lease_id,started_at,completed_at,updated_at,error_code,error_message '
         'FROM simulation_jobs ORDER BY job_id LIMIT 4',
  'row_limit': 4,
  'table': 'simulation_jobs',
  'required_columns': ['job_id',
                       'run_id',
                       'status',
                       'attempt',
                       'worker_id',
                       'lease_id',
                       'started_at',
                       'completed_at',
                       'updated_at',
                       'error_code',
                       'error_message'],
  'seconds_max': 3},
 {'database': 'runtime',
  'id': 'leases',
  'sql': 'SELECT lease_id,job_id,worker_id,acquired_at,expires_at,heartbeat_at,released_at FROM '
         'simulation_job_leases ORDER BY lease_id LIMIT 4',
  'row_limit': 4,
  'table': 'simulation_job_leases',
  'required_columns': ['lease_id',
                       'job_id',
                       'worker_id',
                       'acquired_at',
                       'expires_at',
                       'heartbeat_at',
                       'released_at'],
  'seconds_max': 3},
 {'database': 'runtime',
  'id': 'attempts',
  'sql': 'SELECT job_id,run_id,attempt,worker_id,started_at,ended_at,result,error FROM '
         'simulation_job_attempts ORDER BY attempt DESC,job_id LIMIT 8',
  'row_limit': 8,
  'table': 'simulation_job_attempts',
  'required_columns': ['job_id',
                       'run_id',
                       'attempt',
                       'worker_id',
                       'started_at',
                       'ended_at',
                       'result',
                       'error'],
  'seconds_max': 3},
 {'database': 'runtime',
  'id': 'operational_lease',
  'sql': 'SELECT '
         'lease_id,job_id,run_id,attempt,lifecycle,pid,epoch,generation,row_revision,proposal_id,operation_sha256,durable_phase,terminal_reason,length(original_acquisition_json) '
         'AS acquisition_bytes,length(job_snapshot_json) AS snapshot_bytes FROM '
         'simulation_operational_leases_v1 ORDER BY job_id LIMIT 4',
  'row_limit': 4,
  'table': 'simulation_operational_leases_v1',
  'required_columns': ['lease_id',
                       'job_id',
                       'run_id',
                       'attempt',
                       'lifecycle',
                       'pid',
                       'epoch',
                       'generation',
                       'row_revision',
                       'proposal_id',
                       'operation_sha256',
                       'durable_phase',
                       'terminal_reason',
                       'original_acquisition_json',
                       'job_snapshot_json'],
  'seconds_max': 3},
 {'database': 'runtime',
  'id': 'event_counts',
  'sql': 'SELECT event_type,count(*) AS rows,min(sequence) AS first_sequence,max(sequence) AS last_sequence '
         'FROM simulation_job_events GROUP BY event_type ORDER BY event_type LIMIT 64',
  'row_limit': 64,
  'table': 'simulation_job_events',
  'required_columns': ['sequence', 'event_type'],
  'seconds_max': 3},
 {'database': 'runtime',
  'id': 'last_events',
  'sql': 'SELECT '
         'event_id,job_id,run_id,sequence,stream_sequence,event_type,previous_status,next_status,reason_code,timestamp,source,length(payload_json) '
         'AS payload_bytes,CASE WHEN length(CAST(payload_json AS BLOB))<=262144 THEN payload_json ELSE NULL '
         'END AS bounded_payload_json FROM simulation_job_events ORDER BY stream_sequence DESC LIMIT 32',
  'row_limit': 32,
  'table': 'simulation_job_events',
  'required_columns': ['event_id',
                       'job_id',
                       'run_id',
                       'sequence',
                       'stream_sequence',
                       'event_type',
                       'previous_status',
                       'next_status',
                       'reason_code',
                       'timestamp',
                       'source',
                       'payload_json'],
  'seconds_max': 3},
 {'database': 'runtime',
  'id': 'local_publication_counts',
  'sql': 'SELECT phase,count(*) AS rows,min(rowid) AS first_rowid,max(rowid) AS last_rowid FROM '
         'simulation_local_publications_v1 GROUP BY phase ORDER BY phase LIMIT 16',
  'row_limit': 16,
  'table': 'simulation_local_publications_v1',
  'required_columns': ['phase'],
  'seconds_max': 3},
 {'database': 'runtime',
  'id': 'last_local_publications',
  'sql': 'SELECT '
         'rowid,operation_id,operation_sha256,job_id,attempt,lease_id,epoch,generation,row_revision,phase,event_record_hash,event_receipt_hash,job_receipt_hash,length(payload_json) '
         'AS payload_bytes,CASE WHEN length(CAST(payload_json AS BLOB))<=262144 THEN payload_json ELSE NULL '
         'END AS bounded_payload_json FROM simulation_local_publications_v1 ORDER BY rowid DESC LIMIT 24',
  'row_limit': 24,
  'table': 'simulation_local_publications_v1',
  'required_columns': ['operation_id',
                       'operation_sha256',
                       'job_id',
                       'attempt',
                       'lease_id',
                       'epoch',
                       'generation',
                       'row_revision',
                       'phase',
                       'event_record_hash',
                       'event_receipt_hash',
                       'job_receipt_hash',
                       'payload_json'],
  'seconds_max': 3},
 {'database': 'runtime',
  'id': 'confirmation_counts',
  'sql': 'SELECT state,count(*) AS rows FROM simulation_publication_confirmations_v1 GROUP BY state ORDER BY '
         'state LIMIT 8',
  'row_limit': 8,
  'table': 'simulation_publication_confirmations_v1',
  'required_columns': ['state'],
  'seconds_max': 3},
 {'database': 'events',
  'id': 'local_category_counts',
  'sql': 'SELECT category,count(*) AS rows FROM visual_local_tasks_v1 GROUP BY category ORDER BY category '
         'LIMIT 32',
  'row_limit': 32,
  'table': 'visual_local_tasks_v1',
  'required_columns': ['category'],
  'seconds_max': 3},
 {'database': 'events',
  'id': 'local_tasks',
  'sql': 'SELECT category,record_key,task_id,length(value_json) AS payload_bytes,CASE WHEN '
         'length(CAST(value_json AS BLOB))<=262144 THEN value_json ELSE NULL END AS bounded_payload_json '
         'FROM visual_local_tasks_v1 ORDER BY category,record_key LIMIT 16',
  'row_limit': 16,
  'table': 'visual_local_tasks_v1',
  'required_columns': ['category', 'record_key', 'task_id', 'value_json'],
  'seconds_max': 3},
 {'database': 'events',
  'id': 'local_publication_counts',
  'sql': 'SELECT phase,count(*) AS rows,min(rowid) AS first_rowid,max(rowid) AS last_rowid FROM '
         'visual_local_publications_v1 GROUP BY phase ORDER BY phase LIMIT 16',
  'row_limit': 16,
  'table': 'visual_local_publications_v1',
  'required_columns': ['phase'],
  'seconds_max': 3},
 {'database': 'events',
  'id': 'last_local_publications',
  'sql': 'SELECT '
         'rowid,operation_id,operation_sha256,job_id,attempt,lease_id,epoch,generation,row_revision,phase,event_record_hash,event_receipt_hash,job_receipt_hash,length(payload_json) '
         'AS payload_bytes,CASE WHEN length(CAST(payload_json AS BLOB))<=262144 THEN payload_json ELSE NULL '
         'END AS bounded_payload_json FROM visual_local_publications_v1 ORDER BY rowid DESC LIMIT 16',
  'row_limit': 16,
  'table': 'visual_local_publications_v1',
  'required_columns': ['operation_id',
                       'operation_sha256',
                       'job_id',
                       'attempt',
                       'lease_id',
                       'epoch',
                       'generation',
                       'row_revision',
                       'phase',
                       'event_record_hash',
                       'event_receipt_hash',
                       'job_receipt_hash',
                       'payload_json'],
  'seconds_max': 3},
 {'database': 'events',
  'id': 'bootstrap',
  'sql': 'SELECT bootstrap_id,job_id,run_id,revision,definition_hash,record_hash,length(payload_json) AS '
         'payload_bytes FROM visual_bootstraps ORDER BY bootstrap_id LIMIT 4',
  'row_limit': 4,
  'table': 'visual_bootstraps',
  'required_columns': ['bootstrap_id',
                       'job_id',
                       'run_id',
                       'revision',
                       'definition_hash',
                       'record_hash',
                       'payload_json'],
  'seconds_max': 3},
 {'database': 'events',
  'id': 'supervision',
  'sql': 'SELECT task_id,revision,definition_hash,record_hash,length(payload_json) AS payload_bytes FROM '
         'visual_supervision ORDER BY task_id LIMIT 4',
  'row_limit': 4,
  'table': 'visual_supervision',
  'required_columns': ['task_id', 'revision', 'definition_hash', 'record_hash', 'payload_json'],
  'seconds_max': 3},
 {'database': 'events',
  'id': 'publication',
  'sql': 'SELECT task_id,owner_revision,owner_epoch,state_generation,publication_hash,length(payload_json) '
         'AS payload_bytes FROM visual_owner_publications ORDER BY task_id,owner_revision DESC LIMIT 4',
  'row_limit': 4,
  'table': 'visual_owner_publications',
  'required_columns': ['task_id',
                       'owner_revision',
                       'owner_epoch',
                       'state_generation',
                       'publication_hash',
                       'payload_json'],
  'seconds_max': 3}]

DESTINATIONS = {'runtime': '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round351-p6-t3-utc-noncompletion-diagnosis-20261024/diagnostic/offline_db_01/disposable/runtime.db',
 'events': '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round351-p6-t3-utc-noncompletion-diagnosis-20261024/diagnostic/offline_db_01/disposable/events.db'}

DB_SOURCES = [{'original': {'path': '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round350-p6-t3-successor-lineage-execution-20261024/implementation/t3_03/persistent-basetemp/test_local_new_schema_ignores_0/memory-1/events.db',
               'bytes': 327680,
               'sha256': '851199f0503d55c003d9fc1b638846e4a9e4b43474aaf4c95fb5bb453af506a8'},
  'copy': {'path': '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round350-p6-t3-successor-lineage-execution-20261024/implementation/t3_03/retained-databases/test_local_new_schema_ignores_0/memory-1/events.db',
           'bytes': 327680,
           'sha256': '851199f0503d55c003d9fc1b638846e4a9e4b43474aaf4c95fb5bb453af506a8'},
  'match': True},
 {'original': {'path': '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round350-p6-t3-successor-lineage-execution-20261024/implementation/t3_03/persistent-basetemp/test_local_new_schema_ignores_0/memory-1/runtime.db',
               'bytes': 13467648,
               'sha256': 'e74d5f5da1785c33b0a55a5a3e38bd12d14d4176a3c767850de3b6f104dc5a47'},
  'copy': {'path': '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round350-p6-t3-successor-lineage-execution-20261024/implementation/t3_03/retained-databases/test_local_new_schema_ignores_0/memory-1/runtime.db',
           'bytes': 13467648,
           'sha256': 'e74d5f5da1785c33b0a55a5a3e38bd12d14d4176a3c767850de3b6f104dc5a47'},
  'match': True}]


class DeadlineExpired(TimeoutError):
    pass


def require(condition, message):
    if not condition:
        raise ValueError(message)


def failure(stage, error):
    return {"stage": stage, "type": type(error).__name__, "message": str(error),
            "traceback": traceback.format_exc()}


@contextmanager
def bounded(seconds, absolute=INNER_DEADLINE):
    began = time.monotonic()
    budget = min(seconds, absolute - began)
    if budget <= 0:
        raise DeadlineExpired("existing diagnostic deadline exhausted")
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)

    def expired(signum, frame):
        raise DeadlineExpired("R351 bounded operation exceeded %.6fs" % budget)

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, min(budget, previous_timer[0]) if previous_timer[0] else budget)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0]:
            signal.setitimer(signal.ITIMER_REAL, max(0.000001, previous_timer[0] - (time.monotonic() - began)),
                             previous_timer[1])


def coordinates(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def stable(path):
    """Read through nofollow absolute ancestors and verify their actual identities."""
    path = Path(path)
    require(path.is_absolute() and ".." not in path.parts, "fixed absolute file required")
    directories = [os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)]
    relations = []
    descriptor = None
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directories[-1])
            relations.append((directories[-1], part, child))
            directories.append(child)
        initial = os.stat(path.name, dir_fd=directories[-1], follow_symlinks=False)
        require(stat.S_ISREG(initial.st_mode), "regular nofollow source required")
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directories[-1])
        opened = os.fstat(descriptor)
        require(coordinates(initial) == coordinates(opened), "file changed before byte read")
        chunks = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        raw = b"".join(chunks)
        require(len(raw) == opened.st_size and coordinates(opened) == coordinates(os.fstat(descriptor))
                == coordinates(os.stat(path.name, dir_fd=directories[-1], follow_symlinks=False)),
                "file changed during byte read")
        for parent, name, child in relations:
            actual, actual_fd = os.stat(name, dir_fd=parent, follow_symlinks=False), os.fstat(child)
            require(stat.S_ISDIR(actual.st_mode) and (actual.st_dev, actual.st_ino) == (actual_fd.st_dev, actual_fd.st_ino),
                    "source ancestor identity changed")
        return raw
    finally:
        if descriptor is not None:
            os.close(descriptor)
        for directory in reversed(directories):
            os.close(directory)


def bytes_pin(path, raw):
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def pin(path):
    return bytes_pin(Path(path), stable(path))


def check(expected):
    require(pin(expected["path"]) == expected, "frozen pin changed: " + expected["path"])


def read_json(path):
    value = json.loads(stable(path))
    require(type(value) is dict, "JSON object required")
    return value


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()


def usage():
    metadata = total = count = 0
    pending = [D]
    while pending:
        directory = pending.pop()
        require(not directory.is_symlink(), "new output directory substituted")
        with os.scandir(directory) as entries:
            for entry in entries:
                count += 1
                require(count <= 256, "finite diagnostic output entry cap exceeded")
                info = entry.stat(follow_symlinks=False)
                path = Path(entry.path)
                if stat.S_ISDIR(info.st_mode):
                    pending.append(path)
                else:
                    require(stat.S_ISREG(info.st_mode), "unexpected nonregular diagnostic output")
                    total += info.st_size
                    if path.is_relative_to(OUT) and str(path) not in DESTINATIONS.values():
                        metadata += info.st_size
    return {"metadata_bytes": metadata, "total_bytes": total, "entries": count}


def output_room(additional, *, database=False, final=False):
    observed = usage()
    reserve = 0 if final else FINAL_RESERVE
    require(observed["metadata_bytes"] + (0 if database else additional) <= OUTPUT_CAP - reserve,
            "16MiB diagnostic output bound reached; originals retained")
    require(observed["total_bytes"] + additional <= STORAGE_CAP - reserve,
            "64MiB diagnostic storage bound reached; originals retained")
    return observed


def write(path, value, *, database=False, final=False):
    raw = value if isinstance(value, bytes) else encoded(value)
    output_room(len(raw), database=database, final=final)
    with Path(path).open("xb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    actual = pin(path)
    require(actual == bytes_pin(path, raw), "exclusive diagnostic write readback differs")
    return actual


def emit_stderr(value):
    with bounded(2):
        remaining = memoryview(encoded(value))
        while remaining:
            size = os.write(2, remaining)
            require(size > 0, "stderr write made no progress")
            remaining = remaining[size:]


def cas(before, after, name):
    descriptor = os.open(AUTHOR, os.O_RDONLY | os.O_NOFOLLOW)
    temporary = AUTHOR.with_name(AUTHOR.name + ".r351-next")
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(stable(AUTHOR) == before, "AUTHOR diagnostic CAS bytes changed")
        require(coordinates(os.fstat(descriptor)) == coordinates(AUTHOR.lstat()), "AUTHOR ledger inode changed")
        mode = stat.S_IMODE(os.fstat(descriptor).st_mode)
        write(OUT / (name + "-before.json"), {"pin": bytes_pin(AUTHOR, before),
              "base64": base64.b64encode(before).decode(), "mode": mode})
        raw = encoded(after)
        with temporary.open("xb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        require(stable(AUTHOR) == before, "AUTHOR diagnostic CAS raced")
        os.replace(temporary, AUTHOR)
        require(stable(AUTHOR) == raw, "AUTHOR diagnostic CAS readback differs")
        return write(OUT / (name + ".json"), {"before": bytes_pin(AUTHOR, before), "after": pin(AUTHOR)})
    finally:
        os.close(descriptor)


def source_observation(gate):
    result = {"pins": [], "errors": [], "HEAD": None, "branch": None, "accepted": False}
    for expected in gate["pins"]:
        row = {"expected": expected, "actual": None, "match": False}
        result["pins"].append(row)
        try:
            row["actual"] = pin(expected["path"])
            row["match"] = row["actual"] == expected
        except DeadlineExpired:
            raise
        except Exception as error:
            row["error"] = failure("source pin", error)
            result["errors"].append(row["error"])
    for name, argv in (("HEAD", ["/usr/bin/git", "rev-parse", "HEAD"]),
                       ("branch", ["/usr/bin/git", "branch", "--show-current"])):
        try:
            with bounded(1):
                result[name] = subprocess.check_output(argv, cwd=ROOT, text=True, timeout=1,
                                                       stderr=subprocess.PIPE).strip()
        except DeadlineExpired:
            raise
        except Exception as error:
            result["errors"].append(failure(name, error))
    result["accepted"] = bool(result["pins"] and all(row["match"] for row in result["pins"])
                              and result["HEAD"] == HEAD and result["branch"] == BRANCH and not result["errors"])
    return result


def verify_launch(reserved):
    capture = reserved["launch_capture"]
    info = OUT.lstat()
    require(stat.S_ISDIR(info.st_mode) and capture["output_directory"] == {
        "path": str(OUT), "device": info.st_dev, "inode": info.st_ino}, "ROOT exclusive output identity differs")
    require({path.name for path in OUT.iterdir()} == {"wrapper.stdout.txt", "wrapper.stderr.txt"},
            "only two preopened ROOT logs may exist at inspector start")
    for name, fd in (("stdout", 1), ("stderr", 2)):
        path = OUT / ("wrapper." + name + ".txt")
        actual, opened = path.lstat(), os.fstat(fd)
        expected = capture[name]
        require(stat.S_ISREG(actual.st_mode) and stat.S_ISREG(opened.st_mode)
                and expected == {**pin(path), "device": actual.st_dev, "inode": actual.st_ino}
                and actual.st_size == 0 and (opened.st_dev, opened.st_ino) == (actual.st_dev, actual.st_ino),
                "actual wrapper stream/empty pin differs")


def verify_interpreter(record):
    requested = Path(record["requested"])
    require(str(requested) == "/usr/bin/python3" == os.path.abspath(sys.executable)
            and record["resolved"] == os.path.realpath(sys.executable)
            and sys.flags.isolated == 1 and sys.dont_write_bytecode is True,
            "actual isolated diagnostic interpreter differs")
    link = requested.lstat()
    require(stat.S_ISLNK(link.st_mode) and os.readlink(requested) == record["link_target"]
            and (link.st_dev, link.st_ino) == (record["link_device"], record["link_inode"]),
            "actual interpreter symlink differs")
    check(record["binary"])
    return {"sys_executable": sys.executable, "realpath": os.path.realpath(sys.executable),
            "isolated": sys.flags.isolated, "dont_write_bytecode": sys.dont_write_bytecode,
            "binary": record["binary"], "loaded_memory_attestation": False}


def sibling_observations(source):
    rows = []
    for expected in (source["original"], source["copy"]):
        for suffix in ("-wal", "-shm", "-journal"):
            path = Path(expected["path"] + suffix)
            exists = path.exists() or path.is_symlink()
            rows.append({"path": str(path), "exists": exists})
            require(not exists, "new original/retained DB sibling observed; no replay authorized")
    return rows


def authorizer(database, tables, active):
    def authorize(action, arg1, arg2, dbname, trigger):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_PRAGMA:
            if arg1.lower() == "query_only" and str(arg2).upper() == "ON":
                return sqlite3.SQLITE_OK
            if arg1.lower() == "table_info" and arg2 in tables and active.get("id") == "columns:" + arg2:
                return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and str(arg2).lower() in {"count", "min", "max", "length"}:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ and dbname == "main" and trigger is None:
            columns = ({"name", "sql", "type"} if arg1 == "sqlite_master"
                       else set(active.get("required_columns", [])) | {"", "rowid", "ROWID"})
            if (arg1 == "sqlite_master" or arg1 in tables) and arg2 in columns:
                return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    return authorize


def payload_facts(row):
    if "bounded_payload_json" not in row:
        return None
    raw = row["bounded_payload_json"]
    if raw is None:
        return {"status": "OMITTED_BY_FIXED_SQL_BOUND_OR_NULL", "reported_SQL_length": row.get("payload_bytes"),
                "SQL_length_is_text_characters_not_UTF8_byte_measurement": True}
    require(type(raw) is str and len(raw.encode()) <= PAYLOAD_CAP, "included payload exceeds UTF8 bound")
    facts = {"status": "INCLUDED_RAW_JSON", "UTF8_bytes": len(raw.encode()),
             "sha256": hashlib.sha256(raw.encode()).hexdigest(), "parse_error": None}
    try:
        parsed = json.loads(raw)
        facts["parsed_type"] = type(parsed).__name__
        if type(parsed) is dict:
            facts["top_level_keys"] = list(parsed)[:64]
            facts["key_list_capped"] = len(parsed) > 64
    except (ValueError, TypeError, RecursionError) as error:
        facts["parse_error"] = {"type": type(error).__name__, "message": str(error)}
    return facts


def inspect():
    connections, errors, query_index, copies, after_sources = {}, [], [], [], []
    gate = reserved = plan = None
    consumed = output_verified = False
    state = {"command_id": IDENTITY, "diagnostic_completed": False, "ROOT_accepted": False,
             "product_runtime_polls": 0, "query_opportunities": 0, "SQL_queries_executed": 0,
             "errors": errors, "connections_closed": [], "source_after_accepted": False,
             "RAM_state_recoverable": False, "UTC_causal_ordering_established": False,
             "transactionally_consistent_backup": False, "root_cause_proven": False}
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}

    def stop(signum, frame):
        raise InterruptedError("diagnostic interrupted by signal " + str(signum))

    for sig in previous:
        signal.signal(sig, stop)
    try:
        with bounded(60):
            require(sys.argv[1:] == ["--command", IDENTITY], "exact reserved offline command required")
            require(pin(D / "plan.json")["sha256"] == PLAN_SHA, "actual R351 plan changed")
            plan = read_json(D / "plan.json")
            require(QUERIES == plan["query_contract"]["exact_queries"] and len(QUERIES) == 30
                    and DESTINATIONS == plan["copy_open_policy"]["destinations"]
                    and DB_SOURCES == plan["original_DB_sources"], "literal query/copy contract differs")
            root = read_json(D / "root-diagnostic-ledger.json")
            require(root["round"] == "R351" and root["actor"] == "/root" and root["plan"] == pin(D / "plan.json")
                    and list(root["commands"]) == [KEY], "ROOT diagnostic ledger identity differs")
            proposed = root["commands"][KEY]
            require(proposed["identity"] == IDENTITY and proposed["state"] == "RESERVED"
                    and proposed["used"] == 1 and proposed["remaining"] == 0
                    and type(proposed["reservation_id"]) is str and proposed["reservation_id"], "diagnostic reservation required")
            reserved = proposed
            verify_launch(reserved)
            output_verified = True
            write(OUT / "invocation.json", {"plan": pin(D / "plan.json"), "argv": list(sys.argv),
                  "wrapper_pid": os.getpid(), "reservation": reserved, "monotonic_start": STARTED})
            gate = read_json(D / "diagnostic-source-gate.json")
            accepted = read_json(D / "root-diagnostic-source-acceptance.json")
            require(gate["round"] == accepted["round"] == "R351" and accepted["actor"] == "/root"
                    and accepted["reviewed"] is True and gate["plan"] == accepted["plan"] == pin(D / "plan.json")
                    and accepted["source_gate"] == reserved["source_gate"] == pin(D / "diagnostic-source-gate.json")
                    and reserved["acceptance"] == pin(D / "root-diagnostic-source-acceptance.json")
                    and gate["script"] == accepted["script"] == pin(__file__)
                    and gate["executor_binding"] == accepted["executor_binding"] == reserved["executor_binding"] == pin(BINDING)
                    and gate["command"] == plan["command"] and gate["HEAD"] == HEAD and gate["branch"] == BRANCH,
                    "ROOT diagnostic source/actor/command acceptance differs")
            binding = read_json(BINDING)
            require(binding["actual_actor"] == "/root/p6_t3_sol" and binding["acknowledged_by_actual_live_seat"] is True
                    and gate["activation"] == root["activation"] == binding["activation"]
                    and gate["locator_acceptance"] == binding["locator_acceptance"], "actual binding/locator differs")
            check(gate["activation"])
            check(gate["locator_acceptance"])
            check(binding["locator_plan"])
            check(binding["original_locator_failure"])
            check(gate["source_proof"])
            check(accepted["source_review"])
            require(gate["source_proof"]["path"] == str(IMPL / "source-proof.json"), "fixed proof path required")
            for expected in plan["inputs"]:
                check(expected)  # All 61 are immutable history; no R352 historical live-ledger recursion.
            activation = read_json(gate["activation"]["path"])
            require(gate["interpreter_evidence"] == activation["interpreter_filesystem_evidence"], "actual interpreter record differs")
            state["actual_interpreter"] = verify_interpreter(gate["interpreter_evidence"])
            before = source_observation(gate)
            write(OUT / "source-before.json", before)
            require(before["accepted"], "diagnostic source/HEAD rejected before copy")
            raw_author = stable(AUTHOR)
            author = json.loads(raw_author)
            slot = author["commands"][KEY]
            require(author["round"] == "R351" and author["actor"] == "/root/p6_t3_sol"
                    and author["plan"] == pin(D / "plan.json") and author["executor_binding"] == pin(BINDING)
                    and list(author["commands"]) == [KEY] and slot["identity"] == IDENTITY
                    and slot["state"] == HELD and slot["used"] == 0 and slot["remaining"] == 1,
                    "AUTHOR diagnostic allowance not HELD")
            slot.update(state="CONSUMED_BEFORE_START", used=1, remaining=0, reservation_id=reserved["reservation_id"])
            cas(raw_author, author, "author-consumed")
            consumed = True
            (OUT / "disposable").mkdir(mode=0o700)
            for source in DB_SOURCES:
                record = {"original": source["original"], "retained": source["copy"], "siblings_before": sibling_observations(source)}
                copies.append(record)
                check(source["original"])
                check(source["copy"])
                name = Path(source["copy"]["path"]).stem
                require(name in DESTINATIONS, "only fixed database identities allowed")
                destination = Path(DESTINATIONS[name])
                raw = stable(source["copy"]["path"])
                record["disposable"] = write(destination, raw, database=True)
                require(record["disposable"]["sha256"] == source["copy"]["sha256"], "disposable copy differs")
                os.chmod(destination, 0o400)
                record["read_only_mode"] = stat.S_IMODE(destination.lstat().st_mode)
            write(OUT / "copy-manifest.json", {"files": copies, "consistent_backup": False})
            active = {"runtime": {}, "events": {}}
            schemas = {"runtime": {}, "events": {}}
            columns = {"runtime": {}, "events": {}}
            tables = {database: {q["table"] for q in QUERIES if q["database"] == database and q["table"]}
                      for database in DESTINATIONS}
            for database in ("runtime", "events"):
                require(time.monotonic() < QUERY_DEADLINE, "query work cutoff reached before open")
                destination = Path(DESTINATIONS[database])
                require(destination.parent == OUT / "disposable" and destination.name == database + ".db"
                        and not destination.is_symlink() and stat.S_IMODE(destination.lstat().st_mode) == 0o400,
                        "only fixed read-only disposable paths may be SQLite-opened")
                connection = sqlite3.connect(destination.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=0,
                                             isolation_level=None, cached_statements=0)
                connections[database] = connection
                connection.set_authorizer(authorizer(database, tables[database], active[database]))
                with bounded(3, QUERY_DEADLINE):
                    cursor = connection.execute("PRAGMA query_only=ON")
                    cursor.close()
            with (OUT / "query-results.jsonl").open("xb") as log:
                for ordinal, query in enumerate(QUERIES, 1):
                    if time.monotonic() >= QUERY_DEADLINE:
                        raise DeadlineExpired("query work stops by50s; existing10s finalization reserve")
                    opportunity_deadline = min(time.monotonic() + 3, QUERY_DEADLINE)
                    with bounded(3, opportunity_deadline):
                        database, table = query["database"], query["table"]
                        record = {"ordinal": ordinal, "database": database, "id": query["id"], "sql": query["sql"],
                                  "parameters": [], "row_limit": query["row_limit"], "status": "STARTED", "rows": [],
                                  "required_columns": query["required_columns"], "started_monotonic": time.monotonic()}
                        query_index.append(record)
                        state["query_opportunities"] += 1
                        unavailable = []
                        if table is not None and table not in schemas[database]:
                            unavailable.append("TABLE_NOT_IN_FIXED_SCHEMA_READOUT")
                        if query["required_columns"]:
                            absent = sorted(set(query["required_columns"]) - columns[database].get(table, set()))
                            if absent:
                                unavailable.append({"missing_columns": absent})
                        if "rowid" in query["sql"].lower() and table is not None and table in schemas[database]:
                            declaration = schemas[database][table]
                            if not (type(declaration) is str and re.match(r"^\s*CREATE\s+TABLE\b", declaration, re.I)
                                    and not re.search(r"\bWITHOUT\s+ROWID\b", declaration, re.I)):
                                unavailable.append("ORDINARY_ROWID_TABLE_NOT_PROVEN")
                        cursor = None
                        try:
                            if unavailable:
                                record.update(status="UNAVAILABLE", reason=unavailable)
                            else:
                                active[database].clear()
                                active[database].update(query)
                                query_deadline = opportunity_deadline
                                connection = connections[database]
                                connection.set_progress_handler(lambda: int(time.monotonic() >= query_deadline), 1000)
                                with bounded(3, query_deadline):
                                    state["SQL_queries_executed"] += 1
                                    cursor = connection.execute(query["sql"])
                                    labels = [x[0] for x in cursor.description]
                                    rows = cursor.fetchmany(query["row_limit"])
                                    for values in rows:
                                        row = dict(zip(labels, values))
                                        record["rows"].append({"values": row})
                                    record.update(status="OBSERVED", returned_rows=len(rows),
                                                  may_be_row_limited=len(rows) == query["row_limit"],
                                                  sample_not_complete_population=True)
                        except BaseException as error:
                            record.update(status="ERROR", error=failure("fixed query", error))
                            raise
                        finally:
                            if cursor is not None:
                                cursor.close()
                            connections[database].set_progress_handler(None, 0)
                            record["elapsed_seconds"] = time.monotonic() - record["started_monotonic"]
                            raw = (json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n").encode()
                            output_room(len(raw))
                            log.write(raw)
                            log.flush()
                            os.fsync(log.fileno())
                        # Genuine raw rows are durable before JSON/schema interpretation.
                        record["payloads"] = [payload_facts(row["values"]) for row in record["rows"]]
                        if record["status"] == "OBSERVED" and query["id"] == "schema":
                            require(all(row["values"]["name"] in tables[database] for row in record["rows"]),
                                    "unlisted table escaped fixed schema filter")
                            schemas[database].update({row["values"]["name"]: row["values"]["sql"] for row in record["rows"]})
                        elif record["status"] == "OBSERVED" and query["id"].startswith("columns:"):
                            columns[database][table] = {row["values"]["name"] for row in record["rows"]}
            state["all30_opportunities_recorded"] = len(query_index) == 30
    except BaseException as error:
        errors.append(failure("diagnostic", error))
        try:
            emit_stderr(errors[-1])
        except BaseException as persistence_error:
            errors.append(failure("primary stderr retention", persistence_error))
    finally:
        for database, connection in connections.items():
            try:
                connection.close()
                state["connections_closed"].append(database)
            except BaseException as error:
                errors.append(failure("finally close " + database, error))
        if output_verified:
            for source in DB_SOURCES:
                try:
                    with bounded(3):
                        observation = {"original": pin(source["original"]["path"]),
                                       "retained": pin(source["copy"]["path"]),
                                       "siblings_after": sibling_observations(source)}
                        check(source["original"])
                        check(source["copy"])
                        destination = Path(DESTINATIONS[Path(source["copy"]["path"]).stem])
                        observation["disposable"] = pin(destination)
                        require(observation["disposable"]["bytes"] == source["copy"]["bytes"]
                                and observation["disposable"]["sha256"] == source["copy"]["sha256"],
                                "disposable database changed after read-only inspection")
                        after_sources.append(observation)
                except BaseException as error:
                    errors.append(failure("post-close DB byte observations", error))
            try:
                with bounded(3):
                    if consumed:
                        raw_author = stable(AUTHOR)
                        author = json.loads(raw_author)
                        slot = author["commands"][KEY]
                        require(slot["state"] == "CONSUMED_BEFORE_START"
                                and slot["reservation_id"] == reserved["reservation_id"], "AUTHOR diagnostic consumed state changed")
                        slot["state"] = "SPENT"
                        cas(raw_author, author, "author-spent")
                    else:
                        state["ROOT_spent_no_SQL_reconciliation_required"] = reserved is not None
            except BaseException as error:
                errors.append(failure("AUTHOR spent reconciliation", error))
            try:
                with bounded(3):
                    after = source_observation(gate) if gate is not None else {"accepted": False, "gate_unavailable": True}
                    state["source_after_accepted"] = after["accepted"]
                    write(OUT / "source-after.json", {"sources": after, "DB_byte_observations": after_sources}, final=True)
            except BaseException as error:
                errors.append(failure("source-after retention", error))
            try:
                with bounded(3):
                    write(OUT / "queries-index.json", {"queries": [{k: v for k, v in row.items() if k != "rows"}
                          for row in query_index], "opportunities_not_visited": [q["id"] for q in QUERIES[len(query_index):]],
                          "memory_event_DB_not_RAM": True, "UTC_timestamps_not_causal_order": True}, final=True)
                    write(OUT / "diagnostic-errors.json", {"errors": errors}, final=True)
                    state["elapsed_seconds"] = time.monotonic() - STARTED
                    state["usage"] = usage()
                    state["diagnostic_completed"] = bool(not errors and consumed and state.get("all30_opportunities_recorded")
                        and state["source_after_accepted"] and len(after_sources) == 2
                        and len(state["connections_closed"]) == len(connections) == 2)
                    state["query_log"] = pin(OUT / "query-results.jsonl") if (OUT / "query-results.jsonl").exists() else None
                    write(OUT / "result.json", state, final=True)
            except BaseException as error:
                errors.append(failure("final diagnostic persistence", error))
                try:
                    emit_stderr(errors[-1])
                except BaseException:
                    pass
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    return 0 if state["diagnostic_completed"] and not errors else 1


def main():
    # Includes finally-close, after-hashes and result persistence in the same60s budget.
    with bounded(60):
        return inspect()


if __name__ == "__main__":
    raise SystemExit(main())
