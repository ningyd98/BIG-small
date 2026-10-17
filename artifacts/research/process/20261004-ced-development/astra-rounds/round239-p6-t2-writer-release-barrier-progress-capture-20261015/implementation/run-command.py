"""R239 single bounded diagnostic; raw evidence precedes completeness classification."""
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
D = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round239-p6-t2-writer-release-barrier-progress-capture-20261015'


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
    deadline = time.monotonic() + 9
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
            process.wait(timeout=max(0.01, min(4, deadline - time.monotonic())))
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



def canonical(row):
    return {key: row[key] for key in ('path', 'bytes', 'sha256')}


def verify_retained(plan, gate):
    expected = next(row for row in plan['inputs'] if row['path'].endswith(
        '/round237-p6-t2-original-verification-budget-intersection-20261015/implementation/baseline/source-index.json'))
    if gate['source_index_pin'] != canonical(expected):
        raise ValueError('exact accepted R237 baseline required')
    fixed(expected)
    baseline = read_json(Path(expected['path']))
    if len(baseline['sources']) != 27 or len(baseline['protected']) != 211:
        raise ValueError('exact accepted27/protected211 coverage required')
    physical_current = []
    for row in baseline['sources']:
        fixed(row)
        raw = base64.b64decode(row['base64'], validate=True)
        if (len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']
                or Path(row['path']).stat().st_mode != row['mode']):
            raise ValueError('accepted complete current generation differs')
        physical = Path(expected['path']).parent / 'sources' / Path(row['path']).relative_to(ROOT)
        if physical.is_symlink() or physical.read_bytes() != raw:
            raise ValueError('accepted current physical full source differs')
        physical_current.append(file_pin(physical))
        prior = row['physical_original']
        old_raw = Path(prior['archive']['path']).read_bytes()
        fixed(prior['archive'])
        if (len(old_raw), hashlib.sha256(old_raw).hexdigest()) != (
                prior['original']['bytes'], prior['original']['sha256']):
            raise ValueError('older physical original generation differs')
        if prior['original']['path'] != row['path']:
            raise ValueError('historical logical source identity differs')
    for row in baseline['protected'] + baseline['scripts'] + baseline['history']:
        fixed(row)
    resolved = baseline['resolved_history']
    if len(resolved['entries']) != 321 or resolved['unresolved']:
        raise ValueError('exact finite321 history resolution required')
    for row in resolved['documents']:
        fixed(row)
    records = []
    for entry in resolved['entries']:
        original, mapped = entry['original'], entry['resolution']
        if (mapped['kind'] not in {'EXACT_PHYSICAL_BEFORE', 'CURRENT_EXACT_BYTES'}
                or (original['bytes'], original['sha256']) != (
                    mapped['pin']['bytes'], mapped['pin']['sha256'])):
            raise ValueError('explicit original/archive identity differs')
        fixed(mapped['pin'])
        records.append(mapped['pin'])
    if records != baseline['history']:
        raise ValueError('accepted finite resolved history mapping differs')
    old_observation = next(row for row in resolved['documents'] if row['path'].endswith(
        '/round237-p6-t2-original-verification-budget-intersection-20261015/input-observation.json'))
    observed = read_json(Path(old_observation['path']))
    old_databases = observed['retained_databases']
    new_databases = plan['input_generations']['new_retained_databases']
    if len(old_databases) != 18 or len(new_databases) != 6:
        raise ValueError('exact old18 plus R237 six databases required')
    absences = []
    for row in old_databases + new_databases:
        fixed(row['pin'])
        if len(row['sidecars']) != 3:
            raise ValueError('exact three retained sidecar absences per DB required')
        for sidecar in row['sidecars']:
            path = Path(sidecar['path'])
            if sidecar['exists'] is not False or path.exists() or path.is_symlink():
                raise ValueError('retained DB sidecar became present')
            absences.append(sidecar)
    if len(absences) != 72 or absences[:54] != baseline['absent_sidecars']:
        raise ValueError('exact retained24 DB/72 sidecar generations required')
    return baseline, physical_current, old_databases + new_databases, absences


def progress_records(plan, command, process_pid):
    records, errors = [], []
    attempted_threads = initialized_threads = started_threads = joined_threads = 0
    attempted_events = initialized_events = 0
    ticks = join_ns = 0
    directory = Path(command['finite_env']['BIGSMALL_R239_PROGRESS_ROOT'])
    expected = plan['observer_contract']['sidecar_names']
    actual_paths = sorted(str(path) for path in directory.iterdir()) if directory.is_dir() else []
    if actual_paths != sorted(row['path'] for row in expected):
        errors.append({'stage': 'progress map', 'message': 'exact three expected sidecar paths required'})
    for row in expected:
        record = {'pin': None, 'data': None, 'error': None}
        try:
            path = Path(row['path'])
            fixed_file = file_pin(path)
            if path.is_symlink() or fixed_file['bytes'] > 8 * 1024 * 1024:
                raise ValueError('regular bounded progress sidecar required')
            value = read_json(path)
            record.update(pin=fixed_file, data=value)
            if (value['schema_version'] != 'bigsmall.r239.barrier-progress.v1'
                    or value['exact_nodeid'] != row['nodeid']):
                raise ValueError('progress exact node/schema differs')
            for pin in value['pinned_sources']:
                fixed(pin)
            samples, counter = value['samples'], value['counters']
            if (not 0 < len(samples) <= 1024 or counter['records'] != len(samples)
                    or type(counter['ticks']) is not int or counter['ticks'] <= 0
                    or counter['dropped'] != 0 or counter['bound_reached']
                    or value['observation_errors'] or value['complete'] is not True):
                raise ValueError('progress coverage incomplete or exceeded bound')
            previous_ordinal, previous_offset = 0, -1
            for sample in samples:
                if (type(sample['ordinal']) is not int or sample['ordinal'] <= previous_ordinal
                        or type(sample['host_offset_ns']) is not int
                        or sample['host_offset_ns'] < previous_offset):
                    raise ValueError('actual monotonic diagnostic sample coordinates required')
                previous_ordinal, previous_offset = sample['ordinal'], sample['host_offset_ns']
                if len(sample['main_stack']) > 12 or len(sample['writer_stack']) > 12:
                    raise ValueError('bounded per-thread frame projection required')
                for stack in (sample['main_stack'], sample['writer_stack']):
                    for frame in stack:
                        if (len(frame['filename']) > 512 or len(frame['qualname']) > 256
                                or type(frame['lineno']) is not int):
                            raise ValueError('bounded scalar stack metadata differs')
                if any(type(flag) is not bool for flag in sample['barrier_flags'].values()):
                    raise ValueError('only native boolean barrier flags permitted')
            if not any(sample['primitive_state'] for sample in samples):
                raise ValueError('no original fixture frame observed; obtained coverage retained')
            inherited = value['inherited_hooks']
            before, after = inherited['main_before_setup'], inherited['main_after_teardown']
            if (before != after or value['final_hook_comparison']['main_before_equals_after'] is not True
                    or value['final_hook_comparison']['hooks_modified_by_plugin'] is not False
                    or not all(inherited['sys_hooks_match_original_thread_hooks'].values())
                    or inherited['sampler_start']['sys_profile'] != before['threading_profile']
                    or inherited['sampler_start']['sys_trace'] != before['threading_trace']):
                raise ValueError('actual inherited/main hooks evidence differs')
            resource = value['sampler_resources']
            event, thread = resource['event'], resource['thread']
            if (not event['constructor_attempted'] or not event['initialized']
                    or not event['stop_requested'] or event['exception'] is not None
                    or type(event['id']) is not int or not thread['constructor_attempted']
                    or not thread['initialized'] or not thread['start_attempted']
                    or not thread['started'] or not thread['target_entered']
                    or not thread['target_finally_reached'] or not thread['join_attempted']
                    or not thread['joined'] or thread['alive_after_join'] is not False
                    or thread['exception'] is not None or type(thread['ident']) is not int
                    or type(thread['native_id']) is not int or type(thread['id']) is not int
                    or type(thread['join_elapsed_ns']) is not int
                    or not 0 <= thread['join_elapsed_ns'] <= 2000000000):
                raise ValueError('actual additional sampler Event/thread lifecycle incomplete')
            if value['host_end_ns'] < value['host_start_ns']:
                raise ValueError('host diagnostic time order differs')
        except BaseException as error:
            record['error'] = {'type': type(error).__name__, 'message': str(error)}
            errors.append({'path': row['path'], **record['error']})
        records.append(record)
    captured = [row['data'] for row in records if type(row['data']) is dict]
    def observed_sum(section, key, expected_type):
        values = [row.get(section, {}).get(key) for row in captured]
        return sum(int(value) for value in values) if all(type(value) is expected_type for value in values) else None
    ticks = observed_sum('counters', 'ticks', int)
    resource_rows = [row.get('sampler_resources') for row in captured]
    def resource_sum(kind, key, expected_type):
        values = [row.get(kind, {}).get(key) if type(row) is dict else None for row in resource_rows]
        return sum(int(value) for value in values) if all(type(value) is expected_type for value in values) else None
    attempted_events = resource_sum('event', 'constructor_attempted', bool)
    initialized_events = resource_sum('event', 'initialized', bool)
    attempted_threads = resource_sum('thread', 'constructor_attempted', bool)
    initialized_threads = resource_sum('thread', 'initialized', bool)
    started_threads = resource_sum('thread', 'started', bool)
    joined_threads = resource_sum('thread', 'joined', bool)
    join_ns = resource_sum('thread', 'join_elapsed_ns', int)
    if ticks is not None and ticks > 2401:
        errors.append({'stage': 'progress ticks', 'message': 'whole invocation tick cap exceeded'})
    return {'schema_version': 'bigsmall.r239.progress-summary.v1', 'records': records,
            'all_records_valid': not errors, 'validation_errors': errors,
            'child_pid_from_runner': process_pid, 'sidecar_pid_field': None,
            'ticks': ticks, 'sampler_join_ns': join_ns, 'captured_resource_record_denominator': len(captured),
            'partial_records_included_in_counts': True,
            'sampler_resources': {'event_constructor_attempts': attempted_events,
                 'initialized_events': initialized_events, 'thread_constructor_attempts': attempted_threads,
                 'initialized_threads': initialized_threads, 'started_threads': started_threads,
                 'joined_threads': joined_threads},
            'frozen_resource_denominator': 'Separate original sidecars; never add/relabel sampler objects as the same original identities.',
            'root_cause': 'unknown; sampled stacks are non-atomic and perturb scheduling',
            'unobserved': {'OS_handles': None, 'network_calls': None, 'native_models': None}}


def main():
    began = time.monotonic()
    plan = read_json(D / 'plan.json')
    command = plan['command']
    key = 'capture'
    gate_raw = (D / 'script-gate.json').read_bytes()
    author_raw, root_raw = (D / 'command-ledger.json').read_bytes(), (D / 'root-command-ledger.json').read_bytes()
    gate, author, root = json.loads(gate_raw)['commands'][key], json.loads(author_raw), json.loads(root_raw)
    entry, reservation = author['commands'][key], root['commands'][key]
    if (command['id'] != key or gate['state'] != 'APPROVED' or gate['full_source_reviewed'] is not True
            or reservation['state'] != 'RESERVED_BY_ROOT' or reservation['used'] != 1
            or reservation['remaining'] != 0 or entry['state'] != 'HELD' or entry['used'] != 0
            or entry['remaining'] != 1 or gate['reservation_id'] != reservation['reservation_id']):
        raise ValueError('exact one-use ROOT reservation and unused author slot required')
    if (sys.argv != command['launcher_argv'][1:] or Path.cwd() != ROOT
            or gate['argv'] != command['child_argv'] or gate['launcher_argv'] != command['launcher_argv']
            or gate['cwd'] != command['cwd'] or gate['finite_env'] != command['finite_env']
            or gate['timeout_seconds'] != command['timeout_seconds'] or command['timeout_seconds'] != 600
            or gate['cleanup_seconds'] != command['cleanup_total_seconds'] or command['cleanup_total_seconds'] != 15
            or gate['source']['path'] != str(Path(__file__))):
        raise ValueError('exact launcher/child/environment/cap mismatch')
    fixed(gate['source'])
    fixed(gate['observer_source'])
    fixed(gate['prerequisite_source'])
    if gate['observer_source']['path'] != str(D / 'implementation/r239_barrier_observer.py'):
        raise ValueError('exact new bystander source required')
    prerequisite_pin = next(row for row in plan['inputs'] if row['path'].endswith('/implementation/r235_startup_prerequisite.py'))
    if gate['prerequisite_source'] != canonical(prerequisite_pin):
        raise ValueError('exact unchanged R235 import-only plugin required')
    mutable = {str(D / name) for name in ('command-ledger.json', 'root-command-ledger.json',
                                         'script-gate.json', 'source-gate.json', 'root-activation.json')}
    for row in gate['input_records']:
        if row['path'] in mutable:
            raise ValueError('live own mutable controls cannot enter immutable fixed loop')
        fixed(row)
    baseline, physical_current, databases, absences = verify_retained(plan, gate)
    out = D / 'implementation/capture'
    out.mkdir(parents=True, exist_ok=False)
    expected = [arg for arg in command['child_argv'] if '::' in arg]
    base = next(Path(arg.split('=', 1)[1]) for arg in command['child_argv'] if arg.startswith('--basetemp='))
    if base.exists() or base.is_symlink():
        raise ValueError('fresh exact basetemp required')
    for name in ('BIGSMALL_R223_RESOURCE_ROOT', 'BIGSMALL_R223_CASE_ROOT', 'BIGSMALL_R239_PROGRESS_ROOT'):
        Path(command['finite_env'][name]).mkdir(parents=True, exist_ok=False)
    source_rows = []
    for row in baseline['sources']:
        path = Path(row['path'])
        data = path.read_bytes()
        physical = out / 'before/sources' / path.relative_to(ROOT)
        physical.parent.mkdir(parents=True, exist_ok=True)
        with physical.open('xb') as handle:
            if handle.write(data) != len(data):
                raise OSError('partial fresh physical source archive')
        if physical.read_bytes() != data:
            raise ValueError('fresh physical source byte readback differs')
        source_rows.append({**file_pin(path), 'mode': path.stat().st_mode,
                            'base64': base64.b64encode(data).decode(),
                            'physical': file_pin(physical), 'physical_original': row['physical_original']})
    scripts = []
    for row in (gate['source'], gate['observer_source'], gate['prerequisite_source']):
        fixed(row)
        scripts.append({**canonical(row), 'base64': base64.b64encode(Path(row['path']).read_bytes()).decode()})
    source_index = {'round': 'R239', 'accepted_baseline': gate['source_index_pin'],
                    'sources': source_rows, 'protected': baseline['protected'], 'scripts': scripts,
                    'historical_current_physical': physical_current, 'history': baseline['history'],
                    'resolved_history': baseline['resolved_history'], 'retained_databases': databases,
                    'absent_sidecars': absences, 'input_records': gate['input_records']}
    save(out / 'before/source-index.json', source_index)
    controls = []
    for name in ('command-ledger.json', 'root-command-ledger.json', 'script-gate.json', 'source-gate.json', 'root-activation.json'):
        path = D / name
        raw = path.read_bytes()
        controls.append({**file_pin(path), 'base64': base64.b64encode(raw).decode()})
    invocation = {'round': 'R239', 'command': key, 'argv': command['child_argv'],
                  'launcher_argv': command['launcher_argv'], 'cwd': str(ROOT), 'finite_env': command['finite_env'],
                  'timeout_seconds': 600, 'cleanup_total_seconds': 15, 'process_group_cleanup_cap_seconds': 9,
                  'sampler_cleanup_reserved_seconds': 6, 'attempt': 1, 'retry': 0,
                  'reservation_id': gate['reservation_id'], 'source': gate['source'],
                  'observer_source': gate['observer_source'], 'prerequisite_source': gate['prerequisite_source'],
                  'controls_before': controls, 'outer_capture': gate['transport'], 'independent_tool_streams': None,
                  'accepted_baseline': gate['source_index_pin'], 'fresh_source_index': file_pin(out / 'before/source-index.json')}
    save(out / 'invocation.json', invocation)
    for row in controls + gate['input_records']:
        fixed(row)
    if ((D / 'command-ledger.json').read_bytes() != author_raw
            or (D / 'root-command-ledger.json').read_bytes() != root_raw
            or (D / 'script-gate.json').read_bytes() != gate_raw):
        raise ValueError('immediate complete role/gate CAS failed')
    applied_timeout = 600 - (time.monotonic() - began)
    if applied_timeout <= 0:
        raise TimeoutError('integrated baseline exhausted diagnostic deadline before spawn')
    invocation['applied_child_timeout_seconds'] = applied_timeout
    save(out / 'spawn-invocation.json', invocation)
    entry.update(state='SPENT', used=1, remaining=0, reservation_id=gate['reservation_id'])
    temporary = D / '.author-capture.tmp'
    save(temporary, author)
    os.replace(temporary, D / 'command-ledger.json')
    process, child_exit, timed_out = None, None, False
    failure = None
    cleaned = {'leader_reaped': None, 'group_remaining': None, 'cleanup_notes': []}
    cleanup_elapsed = None
    try:
        with (out / 'stdout.txt').open('xb') as stdout, (out / 'stderr.txt').open('xb') as stderr:
            process = subprocess.Popen(command['child_argv'], cwd=ROOT, env=dict(command['finite_env']),
                                       stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       shell=False, start_new_session=True)
            try:
                child_exit = process.wait(timeout=applied_timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                cleanup_start = time.monotonic()
                cleaned = cleanup(process)
                cleanup_elapsed = time.monotonic() - cleanup_start
                child_exit = process.returncode
    except BaseException as error:
        failure = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    xml, resources, progress, prerequisite, source_after = None, None, None, None, None
    cases, errors = [], []
    try:
        xml = junit(out / 'junit.xml', expected)
    except BaseException as error:
        errors.append({'stage': 'JUnit', 'type': type(error).__name__, 'message': str(error)})
    try:
        resources = resource_records(Path(command['finite_env']['BIGSMALL_R223_RESOURCE_ROOT']), key,
                                     command['child_argv'], None if process is None else process.pid)
        save(out / 'resource-summary.json', resources)
    except BaseException as error:
        errors.append({'stage': 'frozen resources', 'type': type(error).__name__, 'message': str(error)})
    try:
        directory = Path(command['finite_env']['BIGSMALL_R223_CASE_ROOT'])
        for path in sorted(directory.iterdir()):
            if path.is_symlink() or not path.is_file() or path.suffix != '.json':
                raise ValueError('exact regular frozen case JSON required')
            cases.append({'pin': file_pin(path), 'data': read_json(path)})
        if (len(cases) != len(expected) or {Path(row['pin']['path']).name for row in cases}
                != {hashlib.sha256(node.encode()).hexdigest() + '.json' for node in expected}):
            raise ValueError('one complete original case per node required')
    except BaseException as error:
        errors.append({'stage': 'cases', 'type': type(error).__name__, 'message': str(error)})
    try:
        progress = progress_records(plan, command, None if process is None else process.pid)
        save(out / 'progress-summary.json', progress)
    except BaseException as error:
        errors.append({'stage': 'progress', 'type': type(error).__name__, 'message': str(error)})
    try:
        path = Path(command['finite_env']['BIGSMALL_R235_PREREQUISITE_RECORD'])
        prerequisite = {'pin': file_pin(path), 'data': read_json(path)}
        value = prerequisite['data']
        dependency = next(row for row in plan['inputs'] if row['path'] == str(ROOT / 'tests/test_operational_time_v1.py'))
        if (value['schema_version'] != 'bigsmall.r235.startup-prerequisite.v1'
                or value['pid'] != (None if process is None else process.pid)
                or value['module_name'] != 'tests.test_operational_time_v1'
                or value['expected_pin'] != canonical(dependency) or value['actual_file_pin'] != canonical(dependency)
                or value['accepted_prerequisite'] is not True or value['exception'] is not None
                or value['same_sys_modules_object_after'] is not True or value['pre_import_hooks_empty'] is not True
                or value['profile_trace_before_after_equal'] is not True
                or any(item is not None for item in value['profile_trace_before'])
                or any(item is not None for item in value['profile_trace_after'])
                or value['pre_observer_resource_measurement'] is not None
                or (value['already_loaded_before'] and value['same_previously_loaded_object'] is not True)):
            raise ValueError('original import-only prerequisite evidence differs')
    except BaseException as error:
        errors.append({'stage': 'prerequisite', 'type': type(error).__name__, 'message': str(error)})
    try:
        post, _, _, _ = verify_retained(plan, gate)
        for row in gate['input_records'] + scripts:
            fixed(row)
        for row in controls:
            if row['path'] == str(D / 'command-ledger.json'):
                if Path(row['path']).read_bytes() != encoded(author):
                    raise ValueError('exact author single-slot transition differs')
            else:
                fixed(row)
        source_after = {'all_unchanged': True, 'sources': [canonical(row) for row in post['sources']],
                        'protected_count': 211, 'history_count': 321, 'retained_DB_count': 24,
                        'absent_sidecar_count': 72, 'scripts': [canonical(row) for row in scripts]}
        save(out / 'source-after.json', source_after)
    except BaseException as error:
        errors.append({'stage': 'post-source-history-controls', 'type': type(error).__name__, 'message': str(error)})
    capture_databases = []
    file_index, temp_index = index(out), index(base)
    if cleaned['leader_reaped'] is True and cleaned['group_remaining'] is False:
        for row in temp_index:
            if row.get('kind') == 'regular' and row.get('database_bytes_read') is False:
                try:
                    path = Path(row['path'])
                    if path.is_symlink():
                        raise ValueError('capture database became symlink')
                    capture_databases.append({'pin': file_pin(path), 'bytes_read_after_process_cleanup': True})
                except BaseException as error:
                    errors.append({'stage': 'capture database hash', 'path': row['path'],
                                   'type': type(error).__name__, 'message': str(error)})
    else:
        errors.append({'stage': 'capture database hash', 'message': 'not read without observed process closure'})
    sampler_cleanup = (None if progress is None or progress['sampler_join_ns'] is None
                       else progress['sampler_join_ns'] / 1000000000)
    cleanup_total = None if sampler_cleanup is None or cleanup_elapsed is None else sampler_cleanup + cleanup_elapsed
    complete = bool(failure is None and not errors and not timed_out and child_exit in {0, 1}
                    and cleaned['leader_reaped'] is True and cleaned['group_remaining'] is False
                    and cleanup_total is not None and cleanup_total <= 15
                    and xml is not None and xml['tests'] == 3 and xml['names_exact']
                    and resources is not None and resources['all_records_valid']
                    and progress is not None and progress['all_records_valid']
                    and prerequisite is not None and prerequisite['data']['accepted_prerequisite'] is True
                    and source_after is not None and source_after['all_unchanged'])
    wrapper_exit = 0 if complete else 1
    streams = {name: file_pin(out / (name + '.txt')) if (out / (name + '.txt')).is_file() else None
               for name in ('stdout', 'stderr')}
    result = {'round': 'R239', 'command': key, 'attempt': 1, 'retry': 0,
              'child_pid': None if process is None else process.pid, 'child_exit': child_exit,
              'wrapper_exit': wrapper_exit, 'accepted_command_outcome': complete, 'diagnostic_complete': complete,
              'timed_out': timed_out, 'cleanup': cleaned, 'process_cleanup_elapsed_seconds': cleanup_elapsed,
              'sampler_cleanup_elapsed_seconds': sampler_cleanup, 'combined_cleanup_seconds': cleanup_total,
              'JUnit': xml, 'resource_summary': resources, 'progress_summary': progress,
              'cases': cases, 'prerequisite': prerequisite, 'streams': streams,
              'input_records': gate['input_records'], 'invocation': invocation,
              'source_index_pin': file_pin(out / 'before/source-index.json'), 'source_after': source_after,
              'file_index': file_index, 'temp_index': temp_index, 'capture_databases': capture_databases,
              'runner_exception': failure,
              'observation_errors': errors, 'outer_capture': gate['transport'],
              'root_cause': 'unknown pending ROOT interpretation of bounded non-atomic observations',
              'legal_RED': False, 'GREEN': False, 'T2_complete': False, 'T12_complete': False}
    save(out / 'file-index.json', result['file_index'])
    save(out / 'temp-index.json', result['temp_index'])
    save(out / 'result.json', result)
    print(json.dumps({'command': key, 'child_exit': child_exit, 'wrapper_exit': wrapper_exit,
                      'diagnostic_complete': complete, 'result_pin': file_pin(out / 'result.json')}, ensure_ascii=False))
    return wrapper_exit


if __name__ == '__main__':
    try:
        if sys.argv != [str(D / 'implementation/run-command.py'), 'capture']:
            raise ValueError('exact R239 capture launcher required')
        raise SystemExit(main())
    except Exception as error:
        out = D / 'implementation/capture'
        out.mkdir(parents=True, exist_ok=True)
        failure = {'round': 'R239', 'command': 'capture', 'attempt': 1, 'retry': 0, 'wrapper_exit': 1,
                   'child_exit': None, 'diagnostic_complete': False, 'legal_RED': False, 'GREEN': False,
                   'runner_exception': {'type': type(error).__name__, 'message': str(error),
                                        'traceback': traceback.format_exc()}, 'file_index': index(out)}
        if not (out / 'result.json').exists():
            save(out / 'result.json', failure)
        print(json.dumps({'command': 'capture', 'wrapper_exit': 1,
                          'result_pin': file_pin(out / 'result.json')}, ensure_ascii=False))
        raise SystemExit(1)
