"""R225 source-only candidate; execution requires a separate ROOT reservation."""
from pathlib import Path
import collections
import difflib
import hashlib
import json
import signal
import sys
import traceback

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUNDS = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds'
D225 = ROUNDS / 'round225-p6-t2-patch-preparer-class-scope-20261015'
D222 = ROUNDS / 'round222-p6-t2-local-lease-dispatch-patch-recovery-20261015'
SIM = ROOT / 'src/cloud_edge_robot_arm/simulation_runtime'
ORDER = [
    (str(SIM / 'operational_lease.py'), 'OperationalLeaseSession', ['__init__', '_check_ingress']),
    (str(SIM / 'sqlite_repository.py'), 'SQLiteSimulationJobRepository', ['heartbeat_lease', '_local_read_scope']),
    (str(SIM / 'worker.py'), 'SimulationWorker', ['_owns_artifact_publication', '_active_job_cancelled', '_raise_if_cancelled_or_timed_out']),
]
UNIT_TARGETS = [
    (ORDER[0][0], ORDER[0][1], '__init__'),
    (ORDER[0][0], ORDER[0][1], '_check_ingress'),
    *[(ORDER[1][0], ORDER[1][1], '_local_read_scope')] * 3,
    (ORDER[1][0], ORDER[1][1], 'heartbeat_lease'),
    *[(ORDER[2][0], ORDER[2][1], name) for name in ORDER[2][2]],
]
CHECKS = []
WRITTEN = []
RESULT = D225 / 'preparation-result.json'


def require(condition, label):
    CHECKS.append({'check': label, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(label)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def pin_bytes(path, data):
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def pinned(record):
    path = Path(record['path'])
    require(not path.is_symlink(), 'regular input: ' + str(path))
    data = path.read_bytes()
    require(pin_bytes(path, data) == {k: record[k] for k in ('path', 'bytes', 'sha256')}, 'input pin: ' + str(path))
    return data


def region(text, class_name, function_name):
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.startswith('class ' + class_name) and line[len('class ' + class_name):len('class ' + class_name) + 1] in (':', '(')]
    require(len(starts) == 1, 'unique class ' + class_name)
    cstart, cend = starts[0], len(lines)
    for i in range(cstart + 1, len(lines)):
        line = lines[i]
        if line.strip() and not line.startswith(('#', ' ', '\t', '\n', '\r')):
            cend = i
            break
    methods = [i for i in range(cstart + 1, cend) if lines[i].startswith('    def ' + function_name + '(')]
    require(len(methods) == 1, 'unique qualified method ' + class_name + '.' + function_name)
    start, end = methods[0], cend
    for i in range(start + 1, cend):
        if lines[i].startswith(('    def ', '    @')):
            end = i
            break
    return sum(map(len, lines[:start])), sum(map(len, lines[:end]))


def original_units(patch):
    units, part = [], []
    current = None

    def flush():
        if part and any(line.startswith(('+', '-')) for line in part):
            units.append({'path': current, 'old': ''.join(line[1:] for line in part if not line.startswith('+')), 'new': ''.join(line[1:] for line in part if not line.startswith('-')), 'signed_lines': [line for line in part if line.startswith(('+', '-'))]})

    for line in patch.splitlines(keepends=True):
        if line.startswith('*** Update File: '):
            flush()
            part = []
            current = line[len('*** Update File: '):].rstrip('\r\n')
        elif line.startswith('@@') or line.startswith('***'):
            flush()
            part = []
        elif current is not None and line[:1] in (' ', '+', '-'):
            part.append(line)
    require(len(units) == 9, 'exact nine original edit units')
    return units


def signed_by_path(patch):
    result, current = {}, None
    for line in patch.splitlines(keepends=True):
        if line.startswith('*** Update File: '):
            current = line[len('*** Update File: '):].rstrip('\r\n')
            result.setdefault(current, collections.Counter())
        elif current is not None and line.startswith(('+', '-')):
            result[current][line] += 1
    return result


def write_exclusive(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as handle:
        require(handle.write(data) == len(data), 'complete metadata write: ' + str(path))
    WRITTEN.append(pin_bytes(path, data))
    require(path.read_bytes() == data, 'metadata readback: ' + str(path))


def main():
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('R225 120-second cap')))
    signal.alarm(120)
    gate_path = D225 / 'source-gate.json'
    gate = json.loads(gate_path.read_bytes())['metadata_generation']
    require(gate['state'] == 'RESERVED_BY_ROOT' and gate['authorized'] == gate['used'] == 1 and gate['remaining'] == 0, 'ROOT reserved single metadata generation')
    argv = [str(ROOT / '.venv/bin/python'), '-I', '-B', str(D225 / 'proposed-class-qualified-preparer.py')]
    require(gate['argv'] == argv and gate['cwd'] == str(ROOT) and gate['timeout_seconds'] == 120, 'exact argv/cwd/cap')
    require(gate['environment'] == {'inherit': True, 'overrides': {'PYTHONDONTWRITEBYTECODE': '1'}}, 'declared environment; no credential capture')
    pinned(gate['source_pin'])
    require(gate['source_pin']['path'] == str(Path(__file__)), 'executed source identity')
    plan = json.loads((D225 / 'plan.json').read_bytes())
    require(len(plan['inputs']) == 18, 'eighteen immutable R225 inputs')
    for record in plan['inputs']:
        pinned(record)
    parent = json.loads((D222 / 'plan.json').read_bytes())
    pairs = {pair['source']['path']: pair for pair in parent['current_and_archive_pins']}
    require(len(pairs) == 25, 'twenty-five physical source/archive pairs')
    for pair in pairs.values():
        require(pinned(pair['source']) == pinned(pair['archive']), 'current equals physical before: ' + pair['source']['path'])
    protected_doc = json.loads(pinned(gate['protected_manifest_pin']))
    protected = protected_doc['protected']
    require(len(protected) == 211, '211 protected files')
    for record in protected:
        pinned(record)
    for role in ('author', 'root'):
        ledger = json.loads(pinned(gate['role_pins'][role]))
        red, green = ledger['commands']['t2_red'], ledger['commands']['t2_green']
        require(red['used'] == 1 and red['remaining'] == 0, role + ' original RED permanently spent')
        require(green['used'] == 0 and green['remaining'] == 1 and green['state'].startswith('HELD'), role + ' GREEN held')
    original_patch = json.loads((D222 / 'original-author-patch-failure.json').read_bytes())['exact_patch']
    units = original_units(original_patch)
    originals, afters, evidence, modes = {}, {}, [], {}
    for path, _, _ in ORDER:
        originals[path] = pinned(pairs[path]['archive']).decode('utf-8')
        afters[path] = originals[path]
        modes[path] = Path(path).stat().st_mode
    for number, (unit, target) in enumerate(zip(units, UNIT_TARGETS), 1):
        path, class_name, method = target
        require(unit['path'] == path, 'unit target path ' + str(number))
        start, end = region(afters[path], class_name, method)
        body = afters[path][start:end]
        require(body.count(unit['old']) == 1, 'exact original old unit once: ' + str(number))
        changed = body.replace(unit['old'], unit['new'], 1)
        afters[path] = afters[path][:start] + changed + afters[path][end:]
        evidence.append(dict(unit, unit=number, qualified_function=class_name + '.' + method, start_before_this_unit=start, end_before_this_unit=end, before_function=body, after_function=changed))
    corrected = ['*** Begin Patch\n']
    regions = []
    for path, class_name, methods in ORDER:
        corrected.append('*** Update File: ' + path + '\n')
        reconstructed, cursor = [], 0
        for method in methods:
            start, end = region(originals[path], class_name, method)
            astart, aend = region(afters[path], class_name, method)
            old, new = originals[path][start:end], afters[path][astart:aend]
            require(cursor <= start, 'natural function order: ' + class_name + '.' + method)
            reconstructed.extend((originals[path][cursor:start], new))
            cursor = end
            regions.append({'path': path, 'qualified_function': class_name + '.' + method, 'before_start': start, 'before_end': end, 'after_start': astart, 'after_end': aend, 'before_text': old, 'after_text': new})
            corrected.append('@@\n')
            old_lines, new_lines = old.splitlines(keepends=True), new.splitlines(keepends=True)
            for op, i, j, a, b in difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False).get_opcodes():
                if op == 'equal':
                    corrected.extend(' ' + line for line in old_lines[i:j])
                else:
                    corrected.extend('-' + line for line in old_lines[i:j])
                    corrected.extend('+' + line for line in new_lines[a:b])
        reconstructed.append(originals[path][cursor:])
        require(''.join(reconstructed) == afters[path], 'all bytes outside qualified regions unchanged: ' + path)
        require(originals[path].endswith('\n') == afters[path].endswith('\n') and '\r' not in originals[path] and '\r' not in afters[path], 'newline and EOF form preserved: ' + path)
    corrected.append('*** End Patch')
    corrected = ''.join(corrected)
    require(signed_by_path(original_patch) == signed_by_path(corrected), 'per-file exact signed-line multiset')
    require(corrected.count('\n@@\n') == 7 and len(regions) == 7, 'seven bare native hunks')
    expected = {path: {'before': pairs[path]['source'], 'before_archive': pairs[path]['archive'], 'before_mode': modes[path], 'after_text': text, 'after_bytes': len(text.encode('utf-8')), 'after_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()} for path, text in afters.items()}
    outputs = {
        D222 / 'implementation/corrected-patch.txt': corrected.encode('utf-8'),
        D222 / 'implementation/prepared-text-values.json': encoded({'schema_version': 'bigsmall.r225.prepared-text-values.v1', 'expected': expected, 'edit_units': evidence, 'function_regions': regions, 'protected': protected, 'manifest_pairs': list(pairs.values()), 'r225_inputs': plan['inputs'], 'role_pins': gate['role_pins'], 'source_pin': gate['source_pin'], 'checks': CHECKS}),
    }
    require(all(not path.exists() for path in [*outputs, RESULT]), 'all new output paths absent before any write')
    # Final immutable recheck precedes all output writes.
    for record in plan['inputs']:
        pinned(record)
    for pair in pairs.values():
        pinned(pair['source'])
        pinned(pair['archive'])
    for record in protected:
        pinned(record)
    result = {'round': 'R225', 'status': 'PREPARED_TEXT_ONLY', 'exit_code': 0, 'attempt': 1, 'retry': 0, 'argv': argv, 'cwd': str(ROOT), 'environment': gate['environment'], 'source_pin': gate['source_pin'], 'gate_pin': pin_bytes(gate_path, gate_path.read_bytes()), 'inputs': plan['inputs'], 'checks': CHECKS, 'outputs': [pin_bytes(path, data) for path, data in outputs.items()], 'edit_units': 9, 'function_regions': 7, 'live_product_writes': 0, 'native_apply_calls': 0, 'product_execution': False}
    result_data = encoded(result)
    for path, data in outputs.items():
        write_exclusive(path, data)
    write_exclusive(RESULT, result_data)
    signal.alarm(0)
    print(json.dumps({'status': result['status'], 'outputs': result['outputs'], 'result': pin_bytes(RESULT, result_data), 'edit_units': 9, 'function_regions': 7}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        signal.alarm(0)
        failure = {'round': 'R225', 'status': 'FAILED_STOP_NO_RETRY', 'exit_code': 1, 'attempt': 1, 'retry': 0, 'exception_type': type(error).__name__, 'exception': str(error), 'full_traceback': traceback.format_exc(), 'checks': CHECKS, 'written_outputs': WRITTEN, 'product_execution': False}
        # Exclusive failure record; a persistence failure is itself propagated.
        with RESULT.open('xb') as handle:
            handle.write(encoded(failure))
        print(json.dumps({'status': failure['status'], 'failure_result': str(RESULT)}, ensure_ascii=False))
        raise SystemExit(1)
