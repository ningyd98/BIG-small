"""R232 once-only source evidence; no product import, execution or database access."""
from pathlib import Path
import base64
import difflib
import hashlib
import json
import os
import signal
import sys
import traceback

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
D = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round232-p6-t2-genuine-poll-observer-caller-identity-20261015'
CHECKS, WRITES = [], []
WORKER_INSERT = "_GENUINE_WORKER_POLL_CODE = SimulationWorker.poll_once.__code__\n_GENUINE_WORKER_MODULE_GLOBALS = globals()\n\n\n"
LEASE_BEFORE = "    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker\n\n    if (\n        type(worker) is not SimulationWorker\n        or sys._getframe(1).f_code is not SimulationWorker.poll_once.__code__\n    ):\n"
LEASE_AFTER = "    from cloud_edge_robot_arm.simulation_runtime.worker import (\n        SimulationWorker,\n        _GENUINE_WORKER_MODULE_GLOBALS,\n        _GENUINE_WORKER_POLL_CODE,\n    )\n\n    caller = sys._getframe(1)\n    if (\n        type(worker) is not SimulationWorker\n        or caller.f_code is not _GENUINE_WORKER_POLL_CODE\n        or caller.f_globals is not _GENUINE_WORKER_MODULE_GLOBALS\n        or caller.f_locals.get(\"self\") is not worker\n    ):\n"



def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def pin(path, data=None):
    data = path.read_bytes() if data is None else data
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def check(value, name, detail=None):
    CHECKS.append({'name': name, 'passed': bool(value), 'detail': detail})
    if not value:
        raise AssertionError(name)


def read_pin(record):
    path = Path(record['path'])
    check(not path.is_symlink(), 'regular fixed input', str(path))
    data = path.read_bytes()
    check(pin(path, data) == {k: record[k] for k in ('path', 'bytes', 'sha256')}, 'fixed input hash', str(path))
    return data


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    WRITES.append({'path': str(path), 'state': 'ATTEMPTED_PARTIAL_UNKNOWN'})
    with path.open('xb') as handle:
        check(handle.write(data) == len(data), 'full exclusive artifact write', str(path))
    check(path.read_bytes() == data, 'artifact byte readback', str(path))
    WRITES[-1]['state'] = 'COMPLETE_EXACT'


def main(phase):
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('R232 prepare 120s')))
    signal.alarm(120)
    key = 'prepare_' + phase
    plan = json.loads((D / 'plan.json').read_bytes())
    command = next(item for item in plan['execution']['new_slots'] if item['key'] == key)
    out = Path(command['evidence_directory'])
    gate_data = (D / 'script-gate.json').read_bytes()
    gate = json.loads(gate_data)['commands'][key]
    author_data, root_data = (D / 'command-ledger.json').read_bytes(), (D / 'root-command-ledger.json').read_bytes()
    author, root = json.loads(author_data), json.loads(root_data)
    entry, reservation = author['commands'][key], root['commands'][key]
    check(gate['state'] == 'APPROVED' and gate['full_source_reviewed'] is True, 'ROOT full source gate')
    check(reservation['state'] == 'RESERVED_BY_ROOT' and reservation['used'] == 1 and reservation['remaining'] == 0, 'ROOT single reservation')
    check(entry['state'] == 'HELD' and entry['used'] == 0 and entry['remaining'] == 1, 'author unused slot')
    check(gate['reservation_id'] == reservation['reservation_id'], 'same reservation identity')
    check(gate['argv'] == command['argv'] == entry['argv'] and gate['cwd'] == command['cwd'] == str(ROOT), 'exact argv/cwd')
    check(Path.cwd() == ROOT and sys.argv == [str(D / 'implementation/prepare-evidence.py'), phase], 'actual metadata source argv')
    check(gate['finite_env'] == command['finite_env'] and gate['timeout_seconds'] == 120, 'finite environment/cap')
    check({name: os.environ.get(name) for name in command['finite_env']} == command['finite_env'], 'actual declared environment keys')
    check(gate['source']['path'] == str(Path(__file__)), 'metadata source identity')
    read_pin(gate['source'])
    mutable = {str(directory / name) for directory in (D, D.parent / 'round223-p6-t2-public-writer-binding-race-20261015') for name in ('script-gate.json', 'root-activation.json', 'command-ledger.json', 'root-command-ledger.json')}
    for record in gate['input_records']:
        check(record['path'] not in mutable, 'no mutable gate/role in fixed input loop')
        read_pin(record)
    contract = gate['source_contract']
    paths = contract['source_paths']
    check(len(paths) == len(set(paths)) == 27, '27 exact source paths')
    parent = json.loads((D.parent / 'round158-p6-stage-b-local-temporal-publication-20261013/plan.json').read_bytes())
    parent_paths = [str(ROOT / path) for path in parent['tasks'][1]['owned_paths'] if path.startswith('src/')]
    check(contract['parent_product_paths'] == parent_paths and len(parent_paths) == 19, 'exact original19 product authority')
    protected = json.loads(read_pin(contract['protected_manifest_pin']))['protected']
    check(len(protected) == 211, '211 protected records')
    for record in protected:
        read_pin(record)
    sources, physical = [], {}
    for name in paths:
        path = Path(name)
        check(not path.is_symlink() and path.is_relative_to(ROOT), 'regular owned source', name)
        data = path.read_bytes()
        sources.append({**pin(path, data), 'mode': path.stat().st_mode, 'base64': base64.b64encode(data).decode()})
        physical[out / 'sources' / path.relative_to(ROOT)] = data
    current = {record['path']: record for record in sources}
    for record in contract['expected_source_pins']:
        check({k: current[record['path']][k] for k in ('path', 'bytes', 'sha256')} == {k: record[k] for k in ('path', 'bytes', 'sha256')}, 'ROOT final source pin', record['path'])
    check(len(contract['expected_source_pins']) == 27, 'all27 source pins covered')
    check(phase == 'red', 'only new recovery baseline phase')
    old_plan = json.loads((D.parent / 'round223-p6-t2-public-writer-binding-race-20261015/plan.json').read_bytes())
    event_paths = old_plan['scope']['product']
    caller_paths = plan['scope']['product']
    originals = {pair['original']['path']: pair for pair in plan['physical_originals']}
    check(set(originals) == set(current) and len(originals) == 27, '27 exact physical originals')
    diffs, delta_pairs = [], []
    for name, pair in originals.items():
        before = read_pin(pair['archive'])
        check(pin(Path(name), before) == {k: pair['original'][k] for k in ('path', 'bytes', 'sha256')}, 'original full physical identity', name)
        after = base64.b64decode(current[name]['base64'], validate=True)
        if name not in caller_paths:
            check(before == after, 'all25 non-caller sources unchanged', name)
        elif name.endswith('/worker.py'):
            anchor = b'\n\ndef _experiment_config('
            check(before.count(anchor) == 1, 'unique original post-class insertion anchor')
            expected = before.replace(anchor, b'\n\n' + WORKER_INSERT.encode() + b'def _experiment_config(', 1)
            check(after == expected, 'worker exact private anchors insertion only')
        else:
            check(name.endswith('/operational_lease.py'), 'exact second caller source')
            check(before.count(LEASE_BEFORE.encode()) == 1, 'unique original opener guard')
            check(after == before.replace(LEASE_BEFORE.encode(), LEASE_AFTER.encode(), 1), 'opener exact import/first guard only')
        check(current[name]['mode'] == Path(pair['archive']['path']).stat().st_mode, 'source file mode retained', name)
        delta_pairs.append({'before': pair['original'], 'archive': pair['archive'], 'after': {k: current[name][k] for k in ('path', 'bytes', 'sha256')}})
        if name in caller_paths:
            diffs.extend(difflib.unified_diff(before.decode().splitlines(keepends=True), after.decode().splitlines(keepends=True), fromfile=name + ' (failed R223 baseline)', tofile=name + ' (R232 recovery baseline)'))
    check(len(caller_paths) == 2 and set(caller_paths).issubset(originals), 'two exact caller edit paths')
    for row in plan['inputs']:
        if row['path'] in originals or row['applicability'].startswith('observed-role-generation:'):
            continue
        read_pin(row)
    # Original roles may advance only by explicit ROOT transitions, not old whole-pin equality.
    role_evidence = {}
    old_directory = D.parent / 'round223-p6-t2-public-writer-binding-race-20261015'
    for role_name, role_contract in plan['role_and_history_contract']['current_observed'].items():
        raw = (old_directory / role_name).read_bytes()
        observed = json.loads(raw)
        for command_key, wanted in role_contract['commands'].items():
            actual = observed['commands'][command_key]
            check(all(actual[field] == wanted[field] for field in ('state', 'used', 'remaining', 'argv')), 'original role exact command generation', [role_name, command_key])
        role_evidence[role_name] = {'pin': pin(old_directory / role_name, raw), 'base64': base64.b64encode(raw).decode()}
    inventory = contract['writer_fence_inventory']
    check(len(inventory) == 72 and len({(row['backend'], row['method']) for row in inventory}) == 72, '72 literal fence inventory entries')
    for item in inventory:
        check(item['path'] in event_paths, 'fence inventory exact event scope')
        check({k: item['source_pin'][k] for k in ('path', 'bytes', 'sha256')} == {k: current[item['path']][k] for k in ('path', 'bytes', 'sha256')}, 'inventory actual source pin')
        if phase == 'green':
            check(all(item[field] for field in ('qualified_function', 'lock', 'transaction', 'guard_location', 'first_effect')), 'ROOT-reviewed critical section fields')
    invocation = {'round': 'R232', 'command': key, 'argv': command['argv'], 'cwd': str(ROOT), 'finite_env': command['finite_env'], 'timeout_seconds': 120, 'attempt': 1, 'retry': 0, 'reservation_id': gate['reservation_id'], 'source': gate['source'], 'script_gate': pin(D / 'script-gate.json', gate_data), 'script_gate_before_base64': base64.b64encode(gate_data).decode(), 'author_ledger_before_base64': base64.b64encode(author_data).decode(), 'root_ledger_before_base64': base64.b64encode(root_data).decode(), 'outer_capture': gate['transport'], 'independent_tool_streams': None}
    index = {'round': 'R232', 'phase': phase, 'sources': sources, 'protected': protected, 'input_records': gate['input_records'], 'source_contract': contract}
    index_data = encoded(index)
    scope = {'round': 'R232', 'phase': phase, 'checks': CHECKS, 'source_index_pin': pin(out / 'source-index.json', index_data), 'parent_baseline_pins': [{k: current[name][k] for k in ('path', 'bytes', 'sha256')} for name in parent_paths], 'immutable_source_pins': [{k: row[k] for k in ('path', 'bytes', 'sha256')} for row in sources if row['path'] not in event_paths], 'protected_count': 211, 'product_execution': False, 'caller_delta_pairs': delta_pairs, 'original_role_generations': role_evidence}
    artifacts = {**physical, out / 'source-index.json': index_data, out / 'scope-proof.json': encoded(scope), out / 'invocation.json': encoded(invocation), out / 'limited.diff': ''.join(diffs).encode(), out / 'writer-fence-scope.json': encoded({'round': 'R232', 'phase': phase, 'entries': inventory, 'status': 'VULNERABLE_BASELINE' if phase == 'red' else 'ROOT_REVIEWED_SOURCE_FENCES', 'runtime_evidence': None})}
    check(all(not path.exists() for path in [*artifacts, out / 'result.json']), 'all outputs absent inside single action')
    for record in gate['input_records']:
        read_pin(record)
    for source in sources:
        read_pin(source)
    check((D / 'command-ledger.json').read_bytes() == author_data, 'author ledger immediate CAS')
    check((D / 'root-command-ledger.json').read_bytes() == root_data and (D / 'script-gate.json').read_bytes() == gate_data, 'ROOT reservation/gate immediate CAS')
    entry.update(state='SPENT', used=1, remaining=0, reservation_id=gate['reservation_id'])
    temporary = D / ('.author-' + key + '.tmp')
    save(temporary, encoded(author))
    os.replace(temporary, D / 'command-ledger.json')
    for path, data in artifacts.items():
        save(path, data)
    result = {'round': 'R232', 'command': key, 'exit_code': 0, 'attempt': 1, 'retry': 0, 'test_execution': False, 'product_commands': 0, 'input_records': gate['input_records'], 'candidate': pin(out / 'source-index.json', index_data), 'outputs': [pin(path, data) for path, data in artifacts.items()], 'checks': CHECKS, 'runtime_evidence': None, 'actual_resources': None, 'outer_capture': gate['transport']}
    save(out / 'result.json', encoded(result))
    signal.alarm(0)
    print(json.dumps({'command': key, 'exit_code': 0, 'result': pin(out / 'result.json'), 'candidate': result['candidate'], 'test_execution': False}, ensure_ascii=False))


if __name__ == '__main__':
    phase = sys.argv[1] if len(sys.argv) == 2 else ''
    try:
        if phase != 'red':
            raise ValueError('R232 prepare requires exact red phase')
        main(phase)
    except BaseException as error:
        signal.alarm(0)
        out = D / 'implementation' / ('prepare_' + phase)
        out.mkdir(parents=True, exist_ok=True)
        failure = {'round': 'R232', 'command': 'prepare_' + phase, 'exit_code': 1, 'attempt': 1, 'retry': 0, 'test_execution': False, 'product_commands': 0, 'exception': {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}, 'checks': CHECKS, 'writes': WRITES}
        with (out / 'result.json').open('xb') as handle:
            handle.write(encoded(failure))
        print(json.dumps({'command': failure['command'], 'exit_code': 1, 'result_path': str(out / 'result.json')}, ensure_ascii=False))
        raise SystemExit(1)

