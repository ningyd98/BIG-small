"""R248 once-only Ruff and genuine race RED with explicit historical evidence loss."""
from pathlib import Path
import base64
import hashlib
import json
import os
import signal
import sys
import traceback

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
D = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round248-p6-t2-writer-start-condition-synchronization-20261015'
E = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round245-p6-t2-missing-temporary-evidence-continuation-20261015'


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def read_json(path):
    return json.loads(path.read_bytes())


def identity(row):
    return {key: row[key] for key in ('path', 'bytes', 'sha256')}


def key(row):
    return tuple(row[name] for name in ('path', 'bytes', 'sha256'))


def file_pin(path, raw=None):
    raw = path.read_bytes() if raw is None else raw
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def fixed(row):
    path = Path(row['path'])
    raw = path.read_bytes()
    if path.is_symlink() or file_pin(path, raw) != identity(row):
        raise ValueError('fixed input differs: ' + str(path))
    return raw


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if type(value) is bytes else encoded(value)
    with path.open('xb') as handle:
        if handle.write(raw) != len(raw):
            raise OSError('partial exclusive metadata write')
    if path.read_bytes() != raw:
        raise ValueError('exclusive metadata readback differs')



def verify_contract(plan, gate):
    observation = json.loads(fixed(plan['inputs']['observation']))
    source = json.loads(fixed(plan['inputs']['current_baseline']))
    if (len(source['sources']) != 27 or len(source['protected']) != 211 or len(source['scripts']) != 3
            or len(source['history_observations']) != 812 or len(source['explicit_maps']) != 13
            or len(source['input_records']) != 28 or len(observation['inputs']) != 344):
        raise ValueError('actual R24227/211/3/812/13/28 and R248344 schema required')
    registry, missing = {}, []
    for row in observation['known_missing']:
        original, authority = row['original'], row['authority']
        if key(original) in registry or row['disposition'] != 'HISTORICAL_BYTES_CURRENTLY_UNAVAILABLE_R245':
            raise ValueError('unique exact historical unavailable identity required')
        container = json.loads(fixed(authority['pin']))
        ordinal, selector = authority['ordinal'], authority['selector']
        if type(ordinal) is not int or ordinal < 0:
            raise ValueError('exact nonnegative authority ordinal required')
        if selector == 'input_records':
            values = container['input_records']
            if type(values) is not list or ordinal >= len(values):
                raise ValueError('input_records authority range differs')
            authoritative = values[ordinal]
        elif selector == 'new_retained_databases.pin':
            values = container['new_retained_databases']
            if type(values) is not list or ordinal >= len(values):
                raise ValueError('new database authority range differs')
            authoritative = values[ordinal]['pin']
        else:
            raise ValueError('unrecognized exact authority selector')
        if identity(authoritative) != identity(original):
            raise ValueError('historical registry exact original differs')
        path = Path(original['path'])
        try:
            path.lstat()
        except FileNotFoundError:
            pass
        else:
            raise ValueError('historical unavailable path reappeared; provenance review required')
        registry[key(original)] = row
        missing.append({'original': original, 'authority': authority, 'disposition': row['disposition'],
                        'current_exists': False, 'current_is_symlink': False,
                        'current_bytes': None, 'current_sha256': None, 'hash_match': None})
    if len(registry) != 35:
        raise ValueError('exact35 unavailable identities required')
    pairs = (observation['history_authority']['explicit_maps']
             + [observation['additional_fixture_generation']] + observation['R242_final_settlement_maps'])
    if (len(observation['history_authority']['explicit_maps']) != 13
            or len(observation['R242_final_settlement_maps']) != 7):
        raise ValueError('exact inherited13 plus c14 plus final7 maps required')
    allowed = {str(ROOT / 'artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007' / name)
               for name in ('active-t12-state.json', 'phase-summary.md')}
    allowed.update(str(D / name) for name in ('script-gate.json', 'source-gate.json', 'root-activation.json',
                                              'command-ledger.json', 'root-command-ledger.json'))
    for pair in gate['context_history']:
        if pair['original']['path'] not in allowed:
            raise ValueError('extra mapping outside authorized mutable context')
        pairs.append(pair)
    mappings = {}
    for pair in pairs:
        raw = fixed(pair['archive'])
        if (len(raw), hashlib.sha256(raw).hexdigest()) != (pair['original']['bytes'], pair['original']['sha256']):
            raise ValueError('full physical original/archive equivalence differs')
        mappings[key(pair['original'])] = identity(pair['archive'])
    observations = []
    def historical(original, origin, resolved=None):
        if key(original) in registry:
            observations.append({'original': identity(original), 'origin': origin,
                                 'classification': 'HISTORICAL_BYTES_CURRENTLY_UNAVAILABLE_R245',
                                 'hash_match': None})
            return None
        target = mappings.get(key(original), mappings.get(key(resolved), resolved) if resolved is not None else original)
        raw = fixed(target)
        if (len(raw), hashlib.sha256(raw).hexdigest()) != (original['bytes'], original['sha256']):
            raise ValueError('exact mapped historical bytes differ')
        observations.append({'original': identity(original), 'origin': origin, 'resolved': identity(target),
                             'classification': 'VERIFIED_ARCHIVED' if target['path'] != original['path'] else 'CURRENT_EXACT',
                             'hash_match': True})
        return raw
    for name, rows in [('inputs344', observation['inputs']), ('baseline_inputs28', source['input_records']),
                       ('current_context', [observation['current_final_context']['STATE'],
                                            observation['current_final_context']['PHASE']]
                        + observation['current_final_context']['controls']),
                       ('gate_fixed_inputs', gate['input_records'])]:
        for ordinal, row in enumerate(rows):
            raw = historical(row, {'list': name, 'ordinal': ordinal})
            if raw is not None and row['path'].endswith('/invocation.json'):
                invocation = json.loads(raw)
                for control in invocation.get('controls_before', []):
                    decoded = base64.b64decode(control['base64'], validate=True)
                    if file_pin(Path(control['path']), decoded) != identity(control):
                        raise ValueError('invocation own exact recorded control generation differs')
    for ordinal, row in enumerate(source['history_observations']):
        if key(row['original']) in registry:
            if row['hash_match'] is not None:
                raise ValueError('unavailable historical hash cannot become true')
            historical(row['original'], {'list': 'history_observations812', 'ordinal': ordinal})
        else:
            historical(row['original'], {'list': 'history_observations812', 'ordinal': ordinal}, row['resolved'])
    fixture = Path(plan['scope']['modified_existing'][0])
    before = fixed(gate['fixture_before_pin'])
    if before != fixed(observation['additional_fixture_generation']['archive']):
        raise ValueError('c14 complete fixture before differs from physical authority')
    delta = plan['scope']['exact_change']
    old, new = delta['before'].encode(), delta['after'].encode()
    after = fixture.read_bytes()
    if (before.count(old) != 1 or after != before.replace(old, new, 1)
            or len(after) != delta['expected_after_bytes']
            or hashlib.sha256(after).hexdigest() != delta['expected_after_sha256']):
        raise ValueError('unique whole fixture start wait2B delta differs')
    for row in source['sources']:
        raw = base64.b64decode(row['base64'], validate=True)
        if file_pin(Path(row['path']), raw) != identity(row) or fixed(row['physical']) != raw:
            raise ValueError('actual R242 physical/base64 source identity differs')
        if Path(row['path']).read_bytes() != (after if row['path'] == str(fixture) else raw):
            raise ValueError('unapproved current source byte difference')
        if Path(row['path']).stat().st_mode != row['mode']:
            raise ValueError('current source mode differs')
    if len(observation['current_sources']) != 27 or len(observation['protected']) != 211:
        raise ValueError('current27/protected211 observation required')
    for row in observation['current_sources']:
        if fixed(row['physical']) != base64.b64decode(next(
                item['base64'] for item in source['sources'] if item['path'] == row['original']['path']), validate=True):
            raise ValueError('observed current source complete physical generation differs')
    for row in observation['protected'] + source['protected']:
        fixed(row)
    for row in source['scripts']:
        if fixed(row) != base64.b64decode(row['base64'], validate=True):
            raise ValueError('frozen parent script full bytes differ')
    sidecars = observation['old_absent_sidecars']
    if len(sidecars) != 90 or len({row['path'] for row in sidecars}) != 90:
        raise ValueError('exact90 historical sidecar paths required')
    for row in sidecars:
        path = Path(row['path'])
        if row['exists'] is not False or path.exists() or path.is_symlink():
            raise ValueError('old90 sidecar state differs')
    databases = observation['R242_current_persistent_databases']
    if len(databases) != 6 or len({row['pin']['path'] for row in databases}) != 6:
        raise ValueError('six current persistent R242 databases required')
    count = 0
    for row in databases:
        fixed(row['pin'])
        if key(row['pin']) in registry:
            raise ValueError('current persistent DB cannot use historical missing exception')
        for side in row['sidecars']:
            path = Path(side['path'])
            if (side['exists'] is not False or side['is_symlink'] is not False
                    or path.exists() or path.is_symlink()):
                raise ValueError('current R242 database sidecar state differs')
            count += 1
    if count != 18:
        raise ValueError('exact18 current R242 sidecar states required')
    return {'status': 'ACCEPTED_FOR_BOUNDED_NEW_RUN_WITH_DECLARED_HISTORICAL_EVIDENCE_LOSS',
            'source': source, 'observation': observation, 'missing_registry': missing,
            'history_observations': observations, 'explicit_maps': pairs, 'sidecars': sidecars,
            'current_R242_databases': databases, 'commands': plan['commands'],
            'fixture_after': file_pin(fixture), 'all_historical_bytes_available': False}

def role_gate(key_name):
    plan = read_json(D / 'plan.json')
    gate_raw, author_raw, root_raw = [(D / name).read_bytes() for name in
                                     ('script-gate.json', 'command-ledger.json', 'root-command-ledger.json')]
    gate = json.loads(gate_raw)['commands'][key_name]
    author, root = json.loads(author_raw), json.loads(root_raw)
    entry, reservation = author['commands'][key_name], root['commands'][key_name]
    if (gate['state'] != 'APPROVED' or gate['full_source_reviewed'] is not True
            or entry['state'] != 'HELD' or entry['used'] != 0 or entry['remaining'] != 1
            or reservation['state'] != 'RESERVED_BY_ROOT' or reservation['used'] != 1
            or reservation['remaining'] != 0 or gate['reservation_id'] != reservation['reservation_id']):
        raise ValueError('exact one-use ROOT reservation and author slot required')
    fixed(gate['source'])
    if gate['source']['path'] != str(Path(__file__)):
        raise ValueError('actual author source differs')
    mutable = {str(D / name) for name in ('script-gate.json', 'command-ledger.json', 'root-command-ledger.json',
                                         'source-gate.json', 'root-activation.json')}
    if any(row['path'] in mutable for row in gate['input_records']):
        raise ValueError('live own mutable control in fixed input loop')
    controls = []
    for name in ('script-gate.json', 'command-ledger.json', 'root-command-ledger.json', 'source-gate.json', 'root-activation.json'):
        path = D / name
        raw = path.read_bytes()
        controls.append({**file_pin(path, raw), 'base64': base64.b64encode(raw).decode()})
    return plan, gate, author, entry, controls, (gate_raw, author_raw, root_raw)


def consume(key_name, gate, author, entry, controls, raw_roles):
    for row in controls:
        fixed(row)
    if tuple((D / name).read_bytes() for name in
             ('script-gate.json', 'command-ledger.json', 'root-command-ledger.json')) != raw_roles:
        raise ValueError('immediate full role/gate CAS differs')
    entry.update(state='SPENT', used=1, remaining=0, reservation_id=gate['reservation_id'])
    temporary = D / ('.author-' + key_name + '.tmp')
    save(temporary, author)
    os.replace(temporary, D / 'command-ledger.json')


def post_controls(controls, author):
    for row in controls:
        if row['path'] == str(D / 'command-ledger.json'):
            if Path(row['path']).read_bytes() != encoded(author):
                raise ValueError('exact author one-slot transition differs')
        else:
            fixed(row)

import stat
import subprocess
import time
import xml.etree.ElementTree as ET

def index(directory):
    result = []
    if not directory.exists():
        return result
    for base, dirs, files in os.walk(directory, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(base) / name
            info = path.lstat()
            row = {'path': str(path), 'mode': info.st_mode, 'bytes': info.st_size}
            if stat.S_ISLNK(info.st_mode):
                row.update(kind='symlink', target=os.readlink(path), sha256=None)
            elif stat.S_ISREG(info.st_mode):
                database = path.suffix in {'.db', '.sqlite', '.sqlite3'} or path.name.endswith(('-wal', '-shm', '-journal'))
                row.update(kind='regular', sha256=None if database else file_pin(path)['sha256'],
                           database_bytes_read=False if database else None)
            else:
                row.update(kind='directory' if stat.S_ISDIR(info.st_mode) else 'special', sha256=None)
            result.append(row)
    if len(result) > 10000:
        raise ValueError('finite evidence index cap exceeded')
    return result


def cleanup(process):
    notes = []
    deadline = time.monotonic() + 15
    try:
        os.killpg(process.pid, 0)
        remaining = True
    except ProcessLookupError:
        remaining = False
    if remaining:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=max(0.01, min(7, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            notes.append('leader remained after TERM')
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            remaining = False
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=max(0.01, deadline - time.monotonic()))
            while time.monotonic() < deadline:
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    remaining = False
                    break
                time.sleep(0.01)
    else:
        process.wait(timeout=max(0.01, deadline - time.monotonic()))
    return {'leader_reaped': process.returncode is not None,
            'group_remaining': remaining, 'cleanup_notes': notes}

def resource_records(directory: Path, command_id: str, argv: list[str], process_pid: int | None) -> dict:
    from collections import Counter

    expected = [arg for arg in argv if "::" in arg]
    records, errors, nodes = [], [], Counter()
    counts = Counter()
    scenario_caps = {
        "test_late_binding_rejects_public_writer": 1,
        "test_late_binding_rejects_public_writer_second_connection": 1,
        "test_writer_committed_before_binding_is_legacy": 1,
        "test_bound_negative_cancellation_remains_supported": 1,
        "test_unbound_legacy_writer_roundtrip": 0,
    }
    peak_active_polls = 0
    paths = sorted(directory.iterdir()) if directory.is_dir() else []
    if len(paths) > 10000:
        raise ValueError("T2 resource directory exceeds finite evidence cap")
    for path in paths:
        record = {"path": str(path), "pin": None, "data": None, "error": None}
        try:
            if path.is_symlink() or not path.is_file() or path.suffix != ".json":
                raise ValueError("exact regular T2 resource JSON required")
            record["pin"] = file_pin(path)
            value = read_json(path)
            record["data"] = value
            if value["schema_version"] != "bigsmall.r158-t2-resource.v1":
                raise ValueError("exact T2 resource sidecar schema required")
            if value["command_id"] != "R223" or value["nodeid"] not in expected:
                raise ValueError("T2 sidecar command/node provenance differs")
            if value["pid"] != process_pid or process_pid is None:
                raise ValueError("T2 sidecar actual child PID differs")
            nodes[value["nodeid"]] += 1
            if value["entered_contract_guard"] is not True:
                raise ValueError("T2 attempt must record the contract guard")
            if command_id == "green" and value["entered_behavior"] is not True:
                raise ValueError("T2 GREEN must enter every behavioral body")
            resources = value["resources"]
            if type(resources) is not list or type(value["allocation_attempts"]) is not int:
                raise ValueError("actual resource allocation denominator required")
            if value["allocation_attempts"] != len(resources):
                raise ValueError("resource attempts do not match actual object records")
            if value["cleanup_errors"]:
                raise ValueError("actual T2 resource cleanup errors retained")
            by_id = {}
            for resource in resources:
                key = resource["resource_id"]
                if type(key) is not int or key <= 0 or key in by_id:
                    raise ValueError("unique actual resource identities required")
                if resource["pid"] != process_pid:
                    raise ValueError("resource child identity differs")
                by_id[key] = resource
            lifecycles = value["worker_lifecycles"]
            if type(lifecycles) is not list:
                raise ValueError("actual worker lifecycle records required")
            poll_ids, linked, intervals = set(), Counter(), []
            observed_sequences, previous_start = set(), 0
            for ordinal, call in enumerate(lifecycles, 1):
                poll_id = call["poll_id"]
                if type(poll_id) is not int or poll_id != ordinal or poll_id in poll_ids:
                    raise ValueError("unique monotonic poll IDs required")
                poll_ids.add(poll_id)
                worker = by_id[call["worker_resource_id"]]
                if worker["kind"] != "worker" or poll_id not in worker["poll_ids"]:
                    raise ValueError("poll must resolve to the same actual worker")
                linked[worker["resource_id"]] += 1
                if call["attempted"] is not True:
                    raise ValueError("actual poll attempt required")
                if type(call["entered"]) is not bool or type(call["returned_normally"]) is not bool:
                    raise ValueError("strict poll entry/return observations required")
                start, end = call["start_sequence"], call["end_sequence"]
                if type(start) is not int or type(end) is not int or not 0 < start < end:
                    raise ValueError("finished poll attempt sequence required")
                if start <= previous_start or start in observed_sequences or end in observed_sequences:
                    raise ValueError("unique ordered observation sequences required")
                previous_start = start
                observed_sequences.update((start, end))
                counts["attempted_poll_lifecycles"] += 1
                if call["entered"]:
                    entry = call["entry_sequence"]
                    if type(entry) is not int or not start < entry < end:
                        raise ValueError("actual poll entry must precede its finish")
                    if entry in observed_sequences:
                        raise ValueError("poll entry sequence duplicated")
                    observed_sequences.add(entry)
                    if (type(call["thread_id"]) is not int
                            or type(call["native_thread_id"]) is not int):
                        raise ValueError("actual poll thread coordinates required")
                    counts["entered_poll_lifecycles"] += 1
                    intervals.extend(((entry, 1), (end, -1)))
                elif (call["entry_sequence"] is not None or call["thread_id"] is not None
                      or call["native_thread_id"] is not None):
                    raise ValueError("unentered poll cannot invent entry/thread observations")
                if call["returned_normally"]:
                    if (not call["entered"] or type(call["return_value"]) is not bool
                            or call["exception"] is not None):
                        raise ValueError("normal poll return must preserve actual bool and entry")
                    counts["normally_returned_poll_lifecycles"] += 1
                elif (call["return_value"] is not None or type(call["exception"]) is not dict
                      or set(call["exception"]) != {"type", "message"}
                      or any(type(item) is not str for item in call["exception"].values())):
                    raise ValueError("failed poll must preserve its actual exception")
            family = value["nodeid"].split("::")[-1].split("[")[0]
            if family not in scenario_caps or len(lifecycles) > scenario_caps[family]:
                raise ValueError("actual scenario poll lifecycle cap exceeded")
            active, local_peak = 0, 0
            for _, delta in sorted(intervals):
                active += delta
                if active < 0:
                    raise ValueError("poll interval ordering differs")
                local_peak = max(local_peak, active)
            if active != 0 or local_peak > 2:
                raise ValueError("actual concurrent poll cap exceeded or unfinished")
            peak_active_polls = max(peak_active_polls, local_peak)
            counts["allocation_attempts"] += len(resources)
            for resource in resources:
                if resource["initialization_attempted"] is not True:
                    raise ValueError("resource attempt missing")
                if type(resource["initialized"]) is not bool:
                    raise ValueError("actual resource initialization observation required")
                counts["initialized"] += int(resource["initialized"])
                counts["kind:" + resource["kind"]] += 1
                if resource["cleanup_observed"] is not True:
                    raise ValueError("resource cleanup unavailable or failed")
                if resource["kind"] == "worker":
                    counts["constructed_worker_attempts"] += 1
                    counts["initialized_workers"] += int(resource["initialized"])
                    ids = resource["poll_ids"]
                    actual_ids = [call["poll_id"] for call in lifecycles
                                  if call["worker_resource_id"] == resource["resource_id"]]
                    if (type(ids) is not list or any(type(item) is not int for item in ids)
                            or ids != actual_ids or len(ids) != linked[resource["resource_id"]]):
                        raise ValueError("worker poll associations differ")
                    if resource["final_active_job_id"] != "":
                        raise ValueError("actual worker idle state must be empty string")
                    if (type(resource["session_observed"]) is not bool
                            or type(resource["heartbeat_observed"]) is not bool):
                        raise ValueError("worker runtime allocation observation missing")
                    for key, kind, peak_key in (
                        ("broker_resource_ids", "broker_thread", "broker_peak_alive"),
                        ("heartbeat_resource_ids", "heartbeat_thread", "heartbeat_peak_alive"),
                    ):
                        thread_ids = resource[key]
                        if (type(thread_ids) is not list or len(set(thread_ids)) != len(thread_ids)
                                or type(resource[peak_key]) is not int
                                or not 0 <= resource[peak_key] <= 1):
                            raise ValueError("worker thread identity/concurrency observation differs")
                        for thread_id in thread_ids:
                            thread = by_id[thread_id]
                            if (thread["kind"] != kind
                                    or thread["worker_resource_id"] != resource["resource_id"]
                                    or thread["cleanup_observed"] is not True
                                    or thread["alive_after_join"] is not False
                                    or type(thread["thread_ident"]) is not int
                                    or type(thread["native_thread_id"]) is not int
                                    or thread["session_resource_id"] not in resource["session_resource_ids"]):
                                raise ValueError("actual worker thread link or termination differs")
                    sessions = resource["session_resource_ids"]
                    if type(sessions) is not list or len(set(sessions)) != len(sessions):
                        raise ValueError("actual session identities required")
                    for session_id in sessions:
                        session = by_id[session_id]
                        if (session["kind"] != "lease_session"
                                or session["worker_resource_id"] != resource["resource_id"]
                                or session["cleanup_observed"] is not True
                                or session["broker_alive"] is not False):
                            raise ValueError("worker session ownership/release differs")
                    if (resource["session_observed"] != bool(sessions)
                            or resource["heartbeat_observed"] != bool(resource["heartbeat_resource_ids"])):
                        raise ValueError("runtime presence and actual resource links differ")
                    if not ids:
                        if (resource["cleanup_basis"] != "never_polled_no_owned_runtime"
                                or resource["initial_active_job_id"] != ""
                                or resource["session_observed"] is not False
                                or resource["heartbeat_observed"] is not False
                                or sessions or resource["broker_resource_ids"]
                                or resource["heartbeat_resource_ids"] or resource["close_attempts"]):
                            raise ValueError("unpolled worker cannot invent runtime execution/close")
                        counts["never_polled_workers"] += 1
                    elif resource["cleanup_basis"] != "poll_finished_runtime_released":
                        raise ValueError("polled worker must preserve actual runtime cleanup basis")
                elif resource["kind"] in {"broker_thread", "heartbeat_thread"}:
                    owner = by_id[resource["worker_resource_id"]]
                    key = ("broker_resource_ids" if resource["kind"] == "broker_thread"
                           else "heartbeat_resource_ids")
                    if owner["kind"] != "worker" or resource["resource_id"] not in owner[key]:
                        raise ValueError("thread cannot omit its real owning worker")
                counts["cleanup_observed"] += 1
            if value["observations"]["observers_restored"] is not True:
                raise ValueError("T2 observer restoration not observed")
            if command_id == "green" and value["observations"]["assertions_completed"] is not True:
                raise ValueError("T2 behavioral assertions did not complete")
        except (OSError, ValueError, TypeError, KeyError) as error:
            record["error"] = {"type": type(error).__name__, "message": str(error)}
            errors.append({"path": str(path), **record["error"]})
        records.append(record)
    mapping_match = nodes == Counter(expected)
    if not mapping_match:
        errors.append({"stage": "helper map", "type": "MissingOrDuplicateNode",
                       "message": "exactly one actual attempt sidecar per selected node required"})
    if counts["attempted_poll_lifecycles"] > 18 or counts["attempted_poll_lifecycles"] > 64:
        errors.append({"stage": "cap", "type": "WorkerLifecycleCap",
                       "message": "T2 attempted poll18/parent64 cap exceeded"})
    valid = not errors and mapping_match
    return {"schema_version": "bigsmall.r223-resource-summary.v1",
            "command_id": command_id, "actual_node_attempts": len(records),
            "actual_node_counts": dict(nodes), "records": records,
            "counts": dict(counts), "all_records_valid": valid, "validation_errors": errors,
            "peak_active_polls_per_node": peak_active_polls,
            "interpretation": "Observed CPU fixture resources only; counts include all partial/transitive allocations.",
            "unobserved": {"OS_handles": None, "external_models": None, "GPU_native": None,
                           "network_calls": None}}


def junit(path, expected):
    root = ET.fromstring(path.read_bytes())
    nodes = root.findall('.//testcase')
    names = [item.get('classname', '').replace('.', '/') + '.py::' + item.get('name', '') for item in nodes]
    failures = [item for item in nodes if item.find('failure') is not None]
    errors = [item for item in nodes if item.find('error') is not None]
    skips = [item for item in nodes if item.find('skipped') is not None]
    return {'tests': len(nodes), 'passes': len(nodes) - len(failures) - len(errors) - len(skips),
            'failures': len(failures), 'errors': len(errors), 'skips': len(skips), 'nodeids': names,
            'names_exact': names == expected,
            'failure_details': [{'nodeid': names[nodes.index(item)], 'text': ET.tostring(item, encoding='unicode')} for item in failures]}



def verify_baseline(plan, gate):
    verified = verify_contract(plan, gate)
    baseline = json.loads(fixed(gate['source_index_pin']))
    if len(baseline['sources']) != 27 or len(baseline['protected']) != 211:
        raise ValueError('exact accepted new27/211 baseline required')
    for row in baseline['sources']:
        raw = fixed(row)
        if raw != base64.b64decode(row['base64'], validate=True) or fixed(row['physical']) != raw:
            raise ValueError('accepted new physical full source differs')
    for row in baseline['scripts'] + baseline['protected']:
        fixed(row)
    if baseline['historical_registry'] != verified['missing_registry']:
        raise ValueError('exact35 current unavailable states differ from accepted baseline')
    return baseline, verified


def persistent_index(base):
    files = index(base)
    databases = []
    for row in files:
        path = Path(row['path'])
        if row['kind'] == 'regular' and path.suffix in {'.db', '.sqlite', '.sqlite3'}:
            if path.is_symlink():
                raise ValueError('new persistent database is a symlink')
            sidecars = []
            for suffix in ('-wal', '-shm', '-journal'):
                side = Path(str(path) + suffix)
                sidecars.append({'path': str(side), 'exists': side.exists(), 'is_symlink': side.is_symlink(),
                                 'pin': file_pin(side) if side.is_file() and not side.is_symlink() else None})
            databases.append({'pin': file_pin(path), 'sidecars': sidecars,
                              'provenance': 'This genuine new R248 run only; old bytes not recovered'})
    return {'files': files, 'databases': databases, 'retained_in_place': True,
            'SQL': False, 'old_bytes_recovered': False}


def main(key):
    plan, gate, author, entry, controls_before, raw_roles = role_gate(key)
    gate_data, author_data, root_data = raw_roles
    verified = verify_contract(plan, gate)
    normative = next(row for row in verified['commands'] if row['id'] == key)
    command = {**normative, 'argv': normative['child_argv'], 'evidence_directory': str(D / 'implementation' / key)}
    launcher = command['launcher_argv']
    if (sys.argv != launcher[1:] or Path.cwd() != ROOT or gate['launcher_argv'] != launcher
            or gate['argv'] != command['argv'] or gate['finite_env'] != command['finite_env']
            or gate['cwd'] != str(ROOT) or gate['timeout_seconds'] != command['timeout_seconds']):
        raise ValueError('exact overlaid command/launcher/environment/cap differs')
    fixed(gate['prerequisite_source'])
    if gate['prerequisite_source'] != {'path': str(ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round235-p6-t2-bootstrap-json-and-startup-prerequisites-20261015/implementation/r235_startup_prerequisite.py'),
                                      'bytes': 5022, 'sha256': 'e46122f6ce00f9c5d0e13be33301b8861b567cb3f25c33d41447f1ea68880e0d'}:
        raise ValueError('unchanged exact R235 import-only prerequisite required')
    baseline, verified = verify_baseline(plan, gate)
    out = Path(command['evidence_directory'])
    out.mkdir(parents=True, exist_ok=False)
    expected = [arg for arg in command['argv'] if '::' in arg]
    base = next((Path(arg.split('=', 1)[1]) for arg in command['argv'] if arg.startswith('--basetemp=')), None)
    persistent_absence = None
    if base is not None:
        if (base != D / 'implementation/red/persistent-basetemp' or base.exists() or base.is_symlink()
                or base.parent.resolve() != (D / 'implementation/red').resolve()
                or any(path.is_symlink() for path in [D, D / 'implementation', D / 'implementation/red'])):
            raise ValueError('exclusive nonsymlink workspace persistent basetemp required')
        persistent_absence = {'path': str(base), 'exists': False, 'is_symlink': False,
                              'parent_resolved': str(base.parent.resolve())}
    for name in ('BIGSMALL_R223_RESOURCE_ROOT', 'BIGSMALL_R223_CASE_ROOT'):
        if name in command['finite_env']:
            Path(command['finite_env'][name]).mkdir(parents=True, exist_ok=False)
    invocation = {'round': 'R248', 'command': key, 'argv': command['argv'], 'launcher_argv': launcher,
                  'cwd': str(ROOT), 'finite_env': command['finite_env'], 'timeout_seconds': command['timeout_seconds'],
                  'cleanup_seconds': 15, 'attempt': 1, 'retry': 0, 'reservation_id': gate['reservation_id'],
                  'source': gate['source'], 'script_gate': file_pin(D / 'script-gate.json'),
                  'script_gate_before_base64': base64.b64encode(gate_data).decode(),
                  'author_ledger_before_base64': base64.b64encode(author_data).decode(),
                  'root_ledger_before_base64': base64.b64encode(root_data).decode(),
                  'outer_capture': gate['transport'], 'independent_tool_streams': None,
                  'baseline': gate['source_index_pin'], 'prerequisite_source': gate['prerequisite_source'],
                  'historical_unavailable': verified['missing_registry'], 'controls_before': controls_before,
                  'persistent_basetemp_before': persistent_absence}
    save(out / 'invocation.json', invocation)
    if ((D / 'command-ledger.json').read_bytes() != author_data
            or (D / 'root-command-ledger.json').read_bytes() != root_data
            or (D / 'script-gate.json').read_bytes() != gate_data):
        raise ValueError('immediate role/gate CAS failed')
    for row in controls_before:
        fixed(row)
    entry.update(state='SPENT', used=1, remaining=0, reservation_id=gate['reservation_id'])
    temporary = D / ('.author-' + key + '.tmp')
    save(temporary, author)
    os.replace(temporary, D / 'command-ledger.json')
    process, child_exit, timed_out = None, None, False
    failure = None
    cleaned = {'leader_reaped': None, 'group_remaining': None, 'cleanup_notes': []}
    try:
        with (out / 'stdout.txt').open('xb') as stdout, (out / 'stderr.txt').open('xb') as stderr:
            process = subprocess.Popen(command['argv'], cwd=ROOT, env=dict(command['finite_env']),
                                       stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       shell=False, start_new_session=True)
            try:
                child_exit = process.wait(timeout=command['timeout_seconds'])
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                cleaned = cleanup(process)
                child_exit = process.returncode
    except BaseException as error:
        failure = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    xml, resources, case_records, observation_errors = None, None, [], []
    prerequisite, source_after = None, None
    if key != 'ruff':
        try:
            xml = junit(out / 'junit.xml', expected)
        except BaseException as error:
            observation_errors.append({'stage': 'JUnit', 'type': type(error).__name__, 'message': str(error)})
        try:
            resources = resource_records(Path(command['finite_env']['BIGSMALL_R223_RESOURCE_ROOT']),
                                         key, command['argv'], None if process is None else process.pid)
            save(out / 'resource-summary.json', resources)
        except BaseException as error:
            observation_errors.append({'stage': 'resources', 'type': type(error).__name__, 'message': str(error)})
        try:
            directory = Path(command['finite_env']['BIGSMALL_R223_CASE_ROOT'])
            for path in sorted(directory.iterdir()):
                if path.is_symlink() or not path.is_file() or path.suffix != '.json':
                    raise ValueError('exact regular case JSON required')
                case_records.append({'pin': file_pin(path), 'data': read_json(path)})
            if (len(case_records) != len(expected)
                    or {Path(item['pin']['path']).name for item in case_records}
                    != {hashlib.sha256(node.encode()).hexdigest() + '.json' for node in expected}):
                raise ValueError('one full raw case per exact node required')
        except BaseException as error:
            observation_errors.append({'stage': 'cases', 'type': type(error).__name__, 'message': str(error)})
    if key == 'red':
        try:
            prerequisite_file = {'path': str(ROOT / 'tests/test_operational_time_v1.py'), 'bytes': 24211,
                                 'sha256': 'ff226e9a616462c67d74d29931f8f9a7d21548f4f13f93ced64901b263229c0f'}
            fixed(prerequisite_file)
            path = Path(command['finite_env']['BIGSMALL_R235_PREREQUISITE_RECORD'])
            prerequisite = {'pin': file_pin(path), 'data': read_json(path)}
            value = prerequisite['data']
            if (value['schema_version'] != 'bigsmall.r235.startup-prerequisite.v1'
                    or value['pid'] != (None if process is None else process.pid)
                    or value['module_name'] != 'tests.test_operational_time_v1'
                    or value['expected_pin'] != prerequisite_file
                    or value['actual_file_pin'] != prerequisite_file
                    or value['accepted_prerequisite'] is not True or value['exception'] is not None
                    or value['same_sys_modules_object_after'] is not True
                    or value['pre_import_hooks_empty'] is not True
                    or value['profile_trace_before_after_equal'] is not True
                    or any(item is not None for item in value['profile_trace_before'])
                    or any(item is not None for item in value['profile_trace_after'])
                    or value['pre_observer_resource_measurement'] is not None
                    or (value['already_loaded_before'] and value['same_previously_loaded_object'] is not True)):
                raise ValueError('startup prerequisite evidence incomplete or different')
        except BaseException as error:
            observation_errors.append({'stage': 'prerequisite', 'type': type(error).__name__, 'message': str(error)})
    try:
        post, post_verified = verify_baseline(plan, gate)
        source_after = {'all_unchanged': True, 'sources': [
            {k: row[k] for k in ('path', 'bytes', 'sha256')} for row in post['sources']],
            'protected_count': len(post['protected'])}
        save(out / 'source-after.json', source_after)
    except BaseException as error:
        observation_errors.append({'stage': 'source-after', 'type': type(error).__name__, 'message': str(error)})
    for row in controls_before:
        try:
            if row['path'] == str(D / 'command-ledger.json'):
                if Path(row['path']).read_bytes() != encoded(author):
                    raise ValueError('exact author single-slot transition differs')
            else:
                fixed(row)
        except BaseException as error:
            observation_errors.append({'stage': 'post-control', 'path': row['path'], 'type': type(error).__name__, 'message': str(error)})
    new_run_index = None
    if base is not None:
        try:
            if cleaned['leader_reaped'] is not True or cleaned['group_remaining'] is not False:
                raise ValueError('new DB hashes require actual process closure')
            new_run_index = persistent_index(base)
            new_run_index['historical_unavailable'] = verified['missing_registry']
            save(out / 'persistent-file-database-index.json', new_run_index)
        except BaseException as error:
            observation_errors.append({'stage': 'new persistent evidence', 'type': type(error).__name__, 'message': str(error)})
    accepted = (failure is None and not observation_errors and not timed_out
                and cleaned['leader_reaped'] is True and cleaned['group_remaining'] is False
                and source_after is not None and source_after['all_unchanged'] is True)
    if key == 'ruff':
        accepted = accepted and child_exit == 0
    elif key == 'red':
        accepted = (accepted and prerequisite is not None and prerequisite['data']['accepted_prerequisite'] is True
                    and child_exit == 1 and xml is not None and xml['names_exact']
                    and (xml['tests'], xml['passes'], xml['failures'], xml['errors'], xml['skips']) == (3, 0, 3, 0, 0)
                    and all('R223 late local binding was not rejected' in item['text'] for item in xml['failure_details'])
                    and all(item['data']['bootstrap_complete'] is True
                            and item['data']['writer']['returned'] is True
                            and item['data']['writer']['exception'] is None
                            and item['data']['legacy_after'] != item['data']['legacy_before'] for item in case_records)
                    and resources is not None and resources['all_records_valid'])
    wrapper_exit = child_exit if accepted else 1
    streams = {name: file_pin(out / (name + '.txt')) if (out / (name + '.txt')).is_file() else None
               for name in ('stdout', 'stderr')}
    result = {'round': 'R248', 'command': key, 'attempt': 1, 'retry': 0, 'child_pid': None if process is None else process.pid,
              'child_exit': child_exit, 'wrapper_exit': wrapper_exit, 'accepted_command_outcome': bool(accepted),
              'timed_out': timed_out, 'cleanup': cleaned, 'JUnit': xml, 'resource_summary': resources,
              'cases': case_records, 'streams': streams, 'input_records': gate['input_records'],
              'invocation': invocation, 'source_index_pin': gate['source_index_pin'],
              'prerequisite': prerequisite, 'source_after': source_after,
              'new_run_index': new_run_index, 'historical_unavailable': verified['missing_registry'],
              'qualification': verified['status'], 'all_historical_bytes_available': False,
              'legal_RED_requires_ROOT_acceptance': True, 'GREEN': False, 'product_acceptance': False,
              'file_index': index(out), 'temp_index': [] if base is None else index(base),
              'runner_exception': failure, 'observation_errors': observation_errors, 'outer_capture': gate['transport']}
    save(out / 'file-index.json', result['file_index'])
    save(out / 'temp-index.json', result['temp_index'])
    save(out / 'result.json', result)
    # The full XML failures/resources/cases stay on disk, not in the console.
    print(json.dumps({'command': key, 'child_exit': child_exit, 'wrapper_exit': wrapper_exit,
                      'accepted_command_outcome': bool(accepted), 'result_pin': file_pin(out / 'result.json')},
                     ensure_ascii=False))
    return wrapper_exit


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in {'ruff', 'red'}:
            raise ValueError('exact R248 ruff|red launcher required')
        raise SystemExit(main(sys.argv[1]))
    except Exception as error:
        key_name = sys.argv[1] if len(sys.argv) == 2 else 'unknown'
        out = D / 'implementation' / key_name
        out.mkdir(parents=True, exist_ok=True)
        failure = {'round': 'R248', 'command': key_name, 'attempt': 1, 'retry': 0,
                   'wrapper_exit': 1, 'child_exit': None, 'accepted_command_outcome': False,
                   'runner_exception': {'type': type(error).__name__, 'message': str(error),
                                        'traceback': traceback.format_exc()}, 'file_index': index(out)}
        if not (out / 'result.json').exists():
            save(out / 'result.json', failure)
        print(json.dumps({'command': key_name, 'wrapper_exit': 1,
                          'result_pin': file_pin(out / 'result.json')}, ensure_ascii=False))
        raise SystemExit(1)
