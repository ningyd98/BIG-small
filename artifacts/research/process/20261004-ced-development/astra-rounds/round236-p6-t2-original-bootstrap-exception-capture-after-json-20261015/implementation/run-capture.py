"""R236 once-only passive diagnostic runner. Raw outcome precedes acceptance classification."""
from pathlib import Path
import base64
import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
D = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round236-p6-t2-original-bootstrap-exception-capture-after-json-20261015'


def read_json(path):
    return json.loads(path.read_bytes())


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def file_pin(path):
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def fixed(record):
    path = Path(record['path'])
    if path.is_symlink() or file_pin(path) != {k: record[k] for k in ('path', 'bytes', 'sha256')}:
        raise ValueError('fixed input pin differs: ' + str(path))


def save(path, value):
    with path.open('xb') as handle:
        data = encoded(value)
        if handle.write(data) != len(data):
            raise OSError('partial metadata write: ' + str(path))


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


def resolved_evidence(plan, gate):
    fixed(plan['inputs']['index'])
    observed = read_json(Path(plan['inputs']['index']['path']))
    fixed(gate['resolved_history_pin'])
    resolved = read_json(Path(gate['resolved_history_pin']['path']))
    if resolved['status'] != 'RESOLVED_FOR_ROOT_SOURCE_GATE' or resolved['unresolved']:
        raise ValueError('full explicit historical resolution required')
    for document in resolved['documents']:
        fixed(document)
    history = []
    for item in resolved['entries']:
        original, resolution = item['original'], item['resolution']
        row = resolution['pin']
        if (row['bytes'] != original['bytes'] or row['sha256'] != original['sha256']
                or resolution['kind'] not in {'CURRENT_EXACT_ORIGINAL_BYTES',
                                             'EXISTING_PHYSICAL_ARCHIVE', 'COMPLETE_ORIGINAL_BYTES'}):
            raise ValueError('historical original/archive identity differs')
        if resolution['kind'] == 'CURRENT_EXACT_ORIGINAL_BYTES' and row['path'] != original['path']:
            raise ValueError('current resolution cannot rename an original')
        fixed(row)
        if 'source_document' in resolution:
            fixed(resolution['source_document'])
        history.append(row)
    for row in observed['inputs'] + observed['case_pins']:
        fixed(row)
    if len(observed['retained_databases']) != 12:
        raise ValueError('exact12 retained old databases required')
    absent = []
    for database in observed['retained_databases']:
        fixed(database['pin'])
        for row in database['sidecars']:
            path = Path(row['path'])
            if row['exists'] is not False or path.exists() or path.is_symlink():
                raise ValueError('old exact sidecar state changed')
            absent.append(row)
    if len(absent) != 36:
        raise ValueError('exact36 absent old database sidecars required')
    return observed, resolved, history, absent


def capture_sources(plan, gate, out, author_data, root_data, gate_data):
    observed, resolved, history, absent = resolved_evidence(plan, gate)
    fixed(plan['inputs']['baseline_index'])
    baseline = read_json(Path(plan['inputs']['baseline_index']['path']))
    original = {row['path']: row for row in baseline['sources']}
    if (len(observed['current_sources']) != 27 or len(original) != 27
            or set(original) != {row['path'] for row in observed['current_sources']}
            or len(observed['protected']) != 211):
        raise ValueError('exact current27/protected211 source interval required')
    rows = []
    for current in observed['current_sources']:
        fixed(current)
        path = Path(current['path'])
        raw = path.read_bytes()
        reference = original[str(path)]
        if (raw != base64.b64decode(reference['base64'], validate=True)
                or path.stat().st_mode != reference['mode']):
            raise ValueError('current source differs from accepted R235 candidate')
        target = out / 'before/sources' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as handle:
            if handle.write(raw) != len(raw):
                raise OSError('partial physical source archive')
        if target.read_bytes() != raw:
            raise OSError('physical source archive readback mismatch')
        rows.append({**file_pin(path), 'mode': path.stat().st_mode,
                     'base64': base64.b64encode(raw).decode(), 'physical_archive': file_pin(target)})
    for row in observed['protected']:
        fixed(row)
    controls = []
    for name in ('plan.json', 'input-observation.json', 'root-activation.json', 'source-gate.json'):
        path = D / name
        raw = path.read_bytes()
        controls.append({**file_pin(path), 'base64': base64.b64encode(raw).decode()})
    for row in (gate['source'], gate['observer_source'], gate['prerequisite_source'], gate['resolved_history_pin']):
        fixed(row)
        raw = Path(row['path']).read_bytes()
        controls.append({**file_pin(Path(row['path'])), 'base64': base64.b64encode(raw).decode()})
    for field, source in (('trace', gate['observer_source']), ('prerequisite', gate['prerequisite_source'])):
        if {k: source[k] for k in ('path', 'bytes', 'sha256')} != {
                k: plan['reuse'][field][k] for k in ('path', 'bytes', 'sha256')}:
            raise ValueError('frozen reused plugin identity differs')
    for name, raw in (('command-ledger.json', author_data),
                      ('root-command-ledger.json', root_data), ('script-gate.json', gate_data)):
        controls.append({'path': str(D / name), 'bytes': len(raw),
                         'sha256': hashlib.sha256(raw).hexdigest(),
                         'base64': base64.b64encode(raw).decode()})
    result = {'round': 'R236', 'sources': rows, 'protected': observed['protected'],
              'history': history, 'resolved_history': resolved, 'absent_sidecars': absent,
              'controls': controls, 'product_execution': False}
    path = out / 'before/source-index.json'
    save(path, result)
    return {**result, 'index_pin': file_pin(path)}


def check_sources_after(before, plan, gate):
    resolved_evidence(plan, gate)
    for row in before['sources'] + before['protected'] + before['history']:
        fixed(row)
        if 'mode' in row and Path(row['path']).stat().st_mode != row['mode']:
            raise ValueError('source file mode changed')
    for row in before['controls']:
        path = Path(row['path'])
        if path == D / 'command-ledger.json':
            expected = json.loads(base64.b64decode(row['base64'], validate=True))
            original_gate = next(item for item in before['controls']
                                 if item['path'] == str(D / 'script-gate.json'))
            archived_gate = json.loads(base64.b64decode(original_gate['base64'], validate=True))
            expected['commands']['R236_exception_capture'].update(
                state='SPENT', used=1, remaining=0,
                reservation_id=archived_gate['commands']['R236_exception_capture']['reservation_id'])
            if path.read_bytes() != encoded(expected):
                raise ValueError('author role differs beyond exact single-slot consumption')
        else:
            fixed(row)
    return {'all_unchanged': True, 'sources': [{k: row[k] for k in ('path', 'bytes', 'sha256')}
                                             for row in before['sources']],
            'protected_count': len(before['protected']), 'source_count': len(before['sources']),
            'retained_database_count': 12, 'absent_sidecar_count': len(before['absent_sidecars'])}


def prerequisite_record(plan, command, child_pid):
    path = Path(command['finite_env']['BIGSMALL_R235_PREREQUISITE_RECORD'])
    value = read_json(path)
    expected = plan['reuse']['prerequisite']
    if (value['schema_version'] != expected['raw_schema'] or value['pid'] != child_pid
            or value['module_name'] != expected['module']
            or value['expected_pin'] != expected['module_pin']
            or value['actual_file_pin'] != expected['module_pin']
            or value['accepted_prerequisite'] is not True or value['exception'] is not None
            or value['same_sys_modules_object_after'] is not True
            or value['pre_import_hooks_empty'] is not True
            or value['profile_trace_before_after_equal'] is not True
            or any(item is not None for item in value['profile_trace_before'])
            or any(item is not None for item in value['profile_trace_after'])
            or value['pre_observer_resource_measurement'] is not None
            or (value['already_loaded_before'] and value['same_previously_loaded_object'] is not True)):
        raise ValueError('startup prerequisite evidence incomplete or different')
    return {'pin': file_pin(path), 'data': value}


def trace_records(directory, expected, child_pid, targets, resources):
    allowed = {(row['path'], row['qualname'], row['first_line']): row for row in targets}
    records = []
    paths = sorted(directory.iterdir())
    if (len(paths) != 3 or {path.name for path in paths}
            != {hashlib.sha256(node.encode()).hexdigest() + '.json' for node in expected}):
        raise ValueError('exact three trace sidecars required')
    resource_nodes = {} if resources is None else {
        row['data']['nodeid']: row['data'] for row in resources['records'] if row['data'] is not None}
    for path in paths:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1048576:
            raise ValueError('regular bounded trace JSON required')
        value = read_json(path)
        if (value['schema_version'] != 'bigsmall.r234.exception-trace.v1'
                or value['pid'] != child_pid or value['nodeid'] not in expected
                or value['capture_complete'] is not True or value['incomplete_reasons']
                or value['dropped_events'] != 0 or not value['diagnostic_only']):
            raise ValueError('incomplete or wrong-provenance passive trace')
        if len(value['events']) > 512 or value['event_count'] != len(value['events']):
            raise ValueError('actual trace event cap/count differs')
        if any(value['restoration'][key] is not True
               for key in ('sys_trace', 'threading_trace', 'sys_profile', 'threading_profile')):
            raise ValueError('trace/profile restoration differs')
        previous = 0
        for event in value['events']:
            code = event['code']
            identity = (code['filename'], code['qualname'], code['first_line'])
            if (identity not in allowed or event['nodeid'] != value['nodeid']
                    or event['pid'] != child_pid or event['sequence'] <= previous):
                raise ValueError('trace target or sequence differs')
            previous = event['sequence']
            if event['event'] == 'line' and event['line'] not in allowed[identity]['line_events']:
                raise ValueError('unapproved trace line observation')
        sidecar = resource_nodes.get(value['nodeid'])
        if sidecar is None:
            raise ValueError('trace has no same-node original resource sidecar')
        resource_threads = {r.get('thread_ident') for r in sidecar['resources']
                            if r['kind'] in ('broker_thread', 'heartbeat_thread')}
        correspondence = []
        for thread in value['threads']:
            if thread['alive_after_teardown'] and not thread['main_protocol_thread']:
                raise ValueError('observed supplemental thread survived')
            correspondence.append({'thread_id': thread['thread_id'],
                                   'matches_original_thread_resource': thread['thread_id'] in resource_threads,
                                   'exhaustive_allocation_or_close_claim': False})
        records.append({'pin': file_pin(path), 'data': value, 'thread_correspondence': correspondence})
    return records


def main(key):
    plan = read_json(D / 'plan.json')
    execution = plan['execution']
    command = {'argv': execution['child_argv'], 'launcher_argv': execution['launcher_argv'],
               'cwd': execution['cwd'], 'finite_env': execution['finite_env'],
               'timeout_seconds': execution['child_timeout_seconds'],
               'evidence_directory': str(D / 'implementation/capture')}
    gate_data = (D / 'script-gate.json').read_bytes()
    gate = json.loads(gate_data)['commands'][key]
    author_data, root_data = (D / 'command-ledger.json').read_bytes(), (D / 'root-command-ledger.json').read_bytes()
    author, root = json.loads(author_data), json.loads(root_data)
    entry, reservation = author['commands'][key], root['commands'][key]
    if (gate['state'] != 'APPROVED' or gate['full_source_reviewed'] is not True
            or reservation['state'] != 'RESERVED_BY_ROOT' or reservation['used'] != 1
            or reservation['remaining'] != 0 or entry['state'] != 'HELD'
            or entry['used'] != 0 or entry['remaining'] != 1
            or gate['reservation_id'] != reservation['reservation_id']):
        raise ValueError('exact one-use ROOT reservation/author gate required')
    launcher = execution['launcher_argv']
    if (key != 'R236_exception_capture' or sys.argv != launcher[1:] or Path.cwd() != ROOT or gate['launcher_argv'] != launcher
            or gate['argv'] != command['argv'] or entry['argv'] != command['argv']
            or gate['finite_env'] != command['finite_env'] or gate['cwd'] != str(ROOT)
            or gate['timeout_seconds'] != command['timeout_seconds']
            or gate['source']['path'] != str(Path(__file__))):
        raise ValueError('exact command/launcher/environment/cap mismatch')
    fixed(gate['source'])
    fixed(gate['observer_source'])
    fixed(gate['prerequisite_source'])
    mutable = {str(D / name) for name in ('script-gate.json', 'source-gate.json', 'root-activation.json', 'command-ledger.json', 'root-command-ledger.json')}
    for record in gate['input_records']:
        if record['path'] in mutable:
            raise ValueError('mutable role/gate cannot enter current-fixed input loop')
        fixed(record)
    out = Path(command['evidence_directory'])
    out.mkdir(parents=True, exist_ok=False)
    expected = [arg for arg in command['argv'] if '::' in arg]
    base = next((Path(arg.split('=', 1)[1]) for arg in command['argv'] if arg.startswith('--basetemp=')), None)
    if base is not None and base.exists():
        raise ValueError('fresh exact basetemp required')
    for name in ('BIGSMALL_R223_RESOURCE_ROOT', 'BIGSMALL_R223_CASE_ROOT', 'BIGSMALL_R234_TRACE_ROOT'):
        if name in command['finite_env']:
            Path(command['finite_env'][name]).mkdir(parents=True, exist_ok=False)
    # This is part of the single diagnostic action, never a separate baseline command.
    before = capture_sources(plan, gate, out, author_data, root_data, gate_data)
    invocation = {'round': 'R236', 'command': key, 'argv': command['argv'], 'launcher_argv': launcher,
                  'cwd': str(ROOT), 'finite_env': command['finite_env'], 'timeout_seconds': command['timeout_seconds'],
                  'cleanup_seconds': 15, 'attempt': 1, 'retry': 0, 'reservation_id': gate['reservation_id'],
                  'source': gate['source'], 'script_gate': file_pin(D / 'script-gate.json'),
                  'script_gate_before_base64': base64.b64encode(gate_data).decode(),
                  'author_ledger_before_base64': base64.b64encode(author_data).decode(),
                  'root_ledger_before_base64': base64.b64encode(root_data).decode(),
                  'outer_capture': gate['transport'], 'independent_tool_streams': None,
                  'source_before_pin': before['index_pin'], 'observer_source': gate['observer_source'],
                  'prerequisite_source': gate['prerequisite_source'],
                  'resolved_history_pin': gate['resolved_history_pin'], 'reused_plugins': plan['reuse']}
    save(out / 'invocation.json', invocation)
    if ((D / 'command-ledger.json').read_bytes() != author_data
            or (D / 'root-command-ledger.json').read_bytes() != root_data
            or (D / 'script-gate.json').read_bytes() != gate_data):
        raise ValueError('immediate role/gate CAS failed')
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
    traces = []
    source_after, prerequisite = None, None
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
    try:
        traces = trace_records(Path(command['finite_env']['BIGSMALL_R234_TRACE_ROOT']),
                               expected, None if process is None else process.pid,
                               [{'path': str(ROOT / row[0]), 'qualname': row[1], 'first_line': row[2],
                                 'line_events': plan['reuse']['trace']['serve_first_line_milestones']
                                 if row[1] == 'OperationalLeaseSession._serve' else []}
                                for row in plan['reuse']['trace']['targets']], resources)
        save(out / 'trace-summary.json', {'records': traces, 'diagnostic_only': True})
    except BaseException as error:
        observation_errors.append({'stage': 'trace', 'type': type(error).__name__, 'message': str(error)})
    try:
        prerequisite = prerequisite_record(plan, command, None if process is None else process.pid)
    except BaseException as error:
        observation_errors.append({'stage': 'prerequisite', 'type': type(error).__name__, 'message': str(error)})
    try:
        source_after = check_sources_after(before, plan, gate)
        save(out / 'source-after.json', source_after)
    except BaseException as error:
        observation_errors.append({'stage': 'source-after', 'type': type(error).__name__, 'message': str(error)})
    for record in gate['input_records']:
        try:
            fixed(record)
        except BaseException as error:
            observation_errors.append({'stage': 'post-input', 'path': record['path'], 'type': type(error).__name__, 'message': str(error)})
    accepted = (failure is None and not observation_errors and not timed_out
                and child_exit in (0, 1) and cleaned['leader_reaped'] is True
                and cleaned['group_remaining'] is False and xml is not None
                and xml['names_exact'] and xml['tests'] == 3
                and resources is not None and resources['all_records_valid']
                and len(traces) == 3 and all(row['data']['capture_complete'] for row in traces)
                and prerequisite is not None and prerequisite['data']['accepted_prerequisite'] is True
                and source_after is not None and source_after['all_unchanged'] is True)
    # Diagnostic success never means the underlying tests or product passed.
    wrapper_exit = 0 if accepted else 1
    streams = {name: file_pin(out / (name + '.txt')) if (out / (name + '.txt')).is_file() else None
               for name in ('stdout', 'stderr')}
    result = {'round': 'R236', 'command': key, 'attempt': 1, 'retry': 0, 'child_pid': None if process is None else process.pid,
              'child_exit': child_exit, 'wrapper_exit': wrapper_exit, 'accepted_command_outcome': bool(accepted),
              'timed_out': timed_out, 'cleanup': cleaned, 'JUnit': xml, 'resource_summary': resources,
              'cases': case_records, 'streams': streams, 'input_records': gate['input_records'],
              'invocation': invocation, 'source_index_pin': before['index_pin'],
              'source_before': before, 'source_after': source_after, 'traces': traces,
              'prerequisite': prerequisite, 'reused_plugins': plan['reuse'],
              'diagnostic_capture_complete': bool(accepted), 'legal_RED': False,
              'GREEN': False, 'product_acceptance': False,
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
    if sys.argv != [str(D / 'implementation/run-capture.py'), 'capture']:
        raise SystemExit('exact R236 capture launcher required')
    try:
        raise SystemExit(main('R236_exception_capture'))
    except Exception as error:
        out = D / 'implementation/capture'
        out.mkdir(parents=True, exist_ok=True)
        failure = {'round': 'R236', 'command': 'R236_exception_capture',
                   'attempt': 1, 'retry': 0, 'wrapper_exit': 1, 'child_exit': None,
                   'diagnostic_capture_complete': False, 'legal_RED': False,
                   'GREEN': False, 'product_acceptance': False,
                   'runner_exception': {'type': type(error).__name__, 'message': str(error),
                                        'traceback': traceback.format_exc()},
                   'file_index': index(out)}
        if not (out / 'result.json').exists():
            save(out / 'result.json', failure)
        print(json.dumps({'command': 'R236_exception_capture', 'wrapper_exit': 1,
                          'diagnostic_capture_complete': False,
                          'result_pin': file_pin(out / 'result.json')}, ensure_ascii=False))
        raise SystemExit(1)
