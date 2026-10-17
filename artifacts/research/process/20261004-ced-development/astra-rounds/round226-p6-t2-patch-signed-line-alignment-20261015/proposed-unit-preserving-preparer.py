"""R226 candidate: preserve raw original edit units; ROOT gate required to run."""
from pathlib import Path
import collections
import hashlib
import json
import signal
import sys
import traceback

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUNDS = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds'
D226 = ROUNDS / 'round226-p6-t2-patch-signed-line-alignment-20261015'
D225 = ROUNDS / 'round225-p6-t2-patch-preparer-class-scope-20261015'
D222 = ROUNDS / 'round222-p6-t2-local-lease-dispatch-patch-recovery-20261015'
SIM = ROOT / 'src/cloud_edge_robot_arm/simulation_runtime'
ORDER = [
    (str(SIM / 'operational_lease.py'), 'OperationalLeaseSession', ['__init__', '_check_ingress']),
    (str(SIM / 'sqlite_repository.py'), 'SQLiteSimulationJobRepository', ['heartbeat_lease', '_local_read_scope']),
    (str(SIM / 'worker.py'), 'SimulationWorker', ['_owns_artifact_publication', '_active_job_cancelled', '_raise_if_cancelled_or_timed_out']),
]
TARGETS = [
    (ORDER[0][0], ORDER[0][1], '__init__'),
    (ORDER[0][0], ORDER[0][1], '_check_ingress'),
    (ORDER[1][0], ORDER[1][1], '_local_read_scope'),
    (ORDER[1][0], ORDER[1][1], '_local_read_scope'),
    (ORDER[1][0], ORDER[1][1], '_local_read_scope'),
    (ORDER[1][0], ORDER[1][1], 'heartbeat_lease'),
    (ORDER[2][0], ORDER[2][1], '_owns_artifact_publication'),
    (ORDER[2][0], ORDER[2][1], '_active_job_cancelled'),
    (ORDER[2][0], ORDER[2][1], '_raise_if_cancelled_or_timed_out'),
]
CHECKS, WRITE_ATTEMPTS = [], []
DIAGNOSTICS = {}
RESULT = D226 / 'preparation-result.json'


def require(condition, label):
    CHECKS.append({'check': label, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(label)


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def pin(path, data):
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def pinned(record):
    path = Path(record['path'])
    require(not path.is_symlink(), 'not symlink: ' + str(path))
    data = path.read_bytes()
    require(pin(path, data) == {k: record[k] for k in ('path', 'bytes', 'sha256')}, 'exact input: ' + str(path))
    return data


def region(text, class_name, method):
    lines = text.splitlines(keepends=True)
    prefix = 'class ' + class_name
    classes = [i for i, line in enumerate(lines) if line.startswith(prefix) and line[len(prefix):len(prefix) + 1] in (':', '(')]
    require(len(classes) == 1, 'unique class: ' + class_name)
    first, last = classes[0], len(lines)
    for i in range(first + 1, len(lines)):
        line = lines[i]
        if line.strip() and not line.startswith(('#', ' ', '\t', '\r', '\n')):
            last = i
            break
    methods = [i for i in range(first + 1, last) if lines[i].startswith('    def ' + method + '(')]
    require(len(methods) == 1, 'unique qualified method: ' + class_name + '.' + method)
    start, end = methods[0], last
    for i in range(start + 1, last):
        if lines[i].startswith(('    def ', '    @')):
            end = i
            break
    return sum(map(len, lines[:start])), sum(map(len, lines[:end]))


def coordinate(text, start, end):
    return {'char_start': start, 'char_end': end, 'byte_start': len(text[:start].encode('utf-8')), 'byte_end': len(text[:end].encode('utf-8')), 'line_start_1based': text.count('\n', 0, start) + 1, 'line_end_exclusive_1based': text.count('\n', 0, end) + 1}


def parse_units(patch):
    units, part, current = [], [], None

    def flush():
        if part and any(line.startswith(('+', '-')) for line in part):
            units.append({'path': current, 'raw_lines': list(part), 'old': ''.join(line[1:] for line in part if not line.startswith('+')), 'new': ''.join(line[1:] for line in part if not line.startswith('-')), 'signed_lines': [line for line in part if line.startswith(('+', '-'))]})

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
    require(len(units) == 9, 'exact nine original changed units')
    return units


def counters(patch):
    result, current = {}, None
    for line in patch.splitlines(keepends=True):
        if line.startswith('*** Update File: '):
            current = line[len('*** Update File: '):].rstrip('\r\n')
            result.setdefault(current, collections.Counter())
        elif current is not None and line.startswith(('+', '-')):
            result[current][line] += 1
    return result


def counter_rows(counter):
    return [{'line': line, 'repr': repr(line), 'count': count} for line, count in sorted(counter.items())]


def write_exclusive(path, data):
    attempt = {'path': str(path), 'expected': pin(path, data), 'status': 'OPEN_NOT_YET_ATTEMPTED'}
    WRITE_ATTEMPTS.append(attempt)
    path.parent.mkdir(parents=True, exist_ok=True)
    attempt['status'] = 'OPEN_OR_WRITE_IN_PROGRESS_PARTIAL_UNKNOWN'
    with path.open('xb') as handle:
        require(handle.write(data) == len(data), 'complete exclusive write: ' + str(path))
    attempt['status'] = 'WRITE_RETURNED_COMPLETE_READBACK_PENDING'
    require(path.read_bytes() == data, 'exact metadata readback: ' + str(path))
    attempt['status'] = 'COMPLETE_EXACT_READBACK'


def main():
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('R226 120-second cap')))
    signal.alarm(120)
    gate_path = D226 / 'source-gate.json'
    gate_data = gate_path.read_bytes()
    gate = json.loads(gate_data)['metadata_generation']
    argv = [str(ROOT / '.venv/bin/python'), '-I', '-B', str(D226 / 'proposed-unit-preserving-preparer.py')]
    environment = {'inherit': True, 'overrides': {'PYTHONDONTWRITEBYTECODE': '1'}}
    require(gate['state'] == 'RESERVED_BY_ROOT' and gate['authorized'] == gate['used'] == 1 and gate['remaining'] == 0, 'one new R226 reservation')
    require(gate['argv'] == argv and gate['cwd'] == str(ROOT) and gate['environment'] == environment and gate['timeout_seconds'] == 120, 'exact launch contract')
    require(Path.cwd() == ROOT and sys.argv == [argv[-1]], 'actual cwd and source argv')
    require(gate['source_pin']['path'] == str(Path(__file__)), 'new R226 source identity')
    pinned(gate['source_pin'])
    plan_data = (D226 / 'plan.json').read_bytes()
    plan = json.loads(plan_data)
    require(len(plan['inputs']) == 29, '29 immutable R226 inputs')
    for record in plan['inputs']:
        pinned(record)
    old_inputs = json.loads((D225 / 'plan.json').read_bytes())['inputs']
    require(len(old_inputs) == 18 and old_inputs == plan['inputs'][:18], 'frozen original18 reader inputs')
    parent = json.loads((D222 / 'plan.json').read_bytes())
    pairs = {pair['source']['path']: pair for pair in parent['current_and_archive_pins']}
    require(len(pairs) == 25, '25 physical source/archive pairs')
    for pair in pairs.values():
        require(pinned(pair['source']) == pinned(pair['archive']), 'physical before equals current: ' + pair['source']['path'])
    protected = json.loads(pinned(gate['protected_manifest_pin']))['protected']
    require(len(protected) == 211, '211 protected files')
    for record in protected:
        pinned(record)
    for role, record in gate['role_pins'].items():
        ledger = json.loads(pinned(record))
        red, green = ledger['commands']['t2_red'], ledger['commands']['t2_green']
        require(red['used'] == 1 and red['remaining'] == 0, role + ' RED spent')
        require(green['used'] == 0 and green['remaining'] == 1 and green['state'].startswith('HELD'), role + ' GREEN held')
    original_patch = json.loads((D222 / 'original-author-patch-failure.json').read_bytes())['exact_patch']
    units = parse_units(original_patch)
    originals = {path: pinned(pairs[path]['archive']).decode('utf-8') for path, _, _ in ORDER}
    modes = {path: Path(path).stat().st_mode for path in originals}
    for number, (unit, target) in enumerate(zip(units, TARGETS), 1):
        path, class_name, method = target
        require(unit['path'] == path, 'original unit path ' + str(number))
        text = originals[path]
        start, end = region(text, class_name, method)
        body = text[start:end]
        require(body.count(unit['old']) == 1, 'unique original baseline old projection: ' + str(number))
        offset = start + body.index(unit['old'])
        stop = offset + len(unit['old'])
        require((offset == 0 or text[offset - 1] == '\n') and text[stop - 1:stop] == '\n', 'unit spans complete original lines: ' + str(number))
        unit.update(unit=number, qualified_function=class_name + '.' + method, class_name=class_name, method=method, baseline_start=offset, baseline_end=stop, baseline_position=coordinate(text, offset, stop), before_function=body)
    DIAGNOSTICS['original_units'] = units
    afters, function_regions, hunk_evidence = {}, [], []
    corrected = ['*** Begin Patch\n']
    for path, class_name, methods in ORDER:
        text = originals[path]
        file_units = sorted((unit for unit in units if unit['path'] == path), key=lambda unit: unit['baseline_start'])
        previous = 0
        for unit in file_units:
            require(previous <= unit['baseline_start'] < unit['baseline_end'], 'nonoverlapping baseline intervals: ' + str(unit['unit']))
            previous = unit['baseline_end']
        # Independent exact-nine replacements, from right to left on original coordinates.
        independent = text
        for unit in reversed(file_units):
            a, b = unit['baseline_start'], unit['baseline_end']
            require(independent[a:b] == unit['old'], 'independent original unit before: ' + str(unit['unit']))
            independent = independent[:a] + unit['new'] + independent[b:]
        afters[path] = independent
        corrected.append('*** Update File: ' + path + '\n')
        reconstructed, file_cursor = [], 0
        for method in methods:
            start, end = region(text, class_name, method)
            group = [unit for unit in file_units if unit['method'] == method]
            require(bool(group) and file_cursor <= start, 'natural qualified method order: ' + method)
            raw, cursor, emitted_signed = [], start, []
            for unit in group:
                a, b = unit['baseline_start'], unit['baseline_end']
                require(start <= cursor <= a < b <= end, 'unit within exact method: ' + str(unit['unit']))
                raw.extend(' ' + line for line in text[cursor:a].splitlines(keepends=True))
                raw.extend(unit['raw_lines'])
                signed = [line for line in unit['raw_lines'] if line.startswith(('+', '-'))]
                require(signed == unit['signed_lines'], 'verbatim unit signed sequence: ' + str(unit['unit']))
                emitted_signed.extend(signed)
                cursor = b
            raw.extend(' ' + line for line in text[cursor:end].splitlines(keepends=True))
            old_projection = ''.join(line[1:] for line in raw if not line.startswith('+'))
            new_projection = ''.join(line[1:] for line in raw if not line.startswith('-'))
            astart, aend = region(independent, class_name, method)
            hunk_evidence.append({'path': path, 'qualified_function': class_name + '.' + method, 'unit_ids': [unit['unit'] for unit in group], 'raw_lines': raw, 'old_projection': old_projection, 'new_projection': new_projection, 'emitted_signed_lines': emitted_signed})
            require(old_projection == text[start:end], 'full hunk old projection: ' + method)
            require(new_projection == independent[astart:aend], 'full hunk new projection: ' + method)
            reconstructed.extend((text[file_cursor:start], new_projection))
            file_cursor = end
            function_regions.append({'path': path, 'qualified_function': class_name + '.' + method, 'before_start': start, 'before_end': end, 'after_start': astart, 'after_end': aend, 'before_text': text[start:end], 'after_text': new_projection, 'before_position': coordinate(text, start, end), 'after_position': coordinate(independent, astart, aend)})
            for unit in group:
                unit['after_function'] = new_projection
            corrected.extend(['@@\n', *raw])
        reconstructed.append(text[file_cursor:])
        require(''.join(reconstructed) == independent, 'independent replay/full reconstruction/outside functions: ' + path)
        require(text.endswith('\n') == independent.endswith('\n') and '\r' not in text and '\r' not in independent, 'newline and EOF unchanged: ' + path)
    corrected.append('*** End Patch')
    corrected = ''.join(corrected)
    original_counters, generated_counters = counters(original_patch), counters(corrected)
    # Complete diagnostics exist before strict Counter equality is asserted.
    DIAGNOSTICS.update(corrected_patch=corrected, hunk_evidence=hunk_evidence, signed_counters={path: {'original': counter_rows(original_counters.get(path, collections.Counter())), 'generated': counter_rows(generated_counters.get(path, collections.Counter())), 'original_minus_generated': counter_rows(original_counters.get(path, collections.Counter()) - generated_counters.get(path, collections.Counter())), 'generated_minus_original': counter_rows(generated_counters.get(path, collections.Counter()) - original_counters.get(path, collections.Counter()))} for path in sorted(set(original_counters) | set(generated_counters))})
    require(original_counters == generated_counters, 'strict exact per-file signed Counter equality')
    require(corrected.count('\n@@\n') == len(function_regions) == 7 and len(afters) == 3, 'three paths/seven bare native hunks')
    expected = {path: {'before': pairs[path]['source'], 'before_archive': pairs[path]['archive'], 'before_mode': modes[path], 'after_text': text, 'after_bytes': len(text.encode('utf-8')), 'after_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()} for path, text in afters.items()}
    values = {'expected': expected, 'edit_units': units, 'function_regions': function_regions, 'manifest_pairs': list(pairs.values()), 'protected': protected, 'r225_inputs': old_inputs, 'role_pins': gate['role_pins'], 'source_pin': gate['source_pin'], 'r226_inputs': plan['inputs'], 'r226_plan_pin': pin(D226 / 'plan.json', plan_data), 'r226_gate_pin': pin(gate_path, gate_data), 'r226_signed_provenance': DIAGNOSTICS, 'checks': CHECKS}
    outputs = {D222 / 'implementation/corrected-patch.txt': corrected.encode('utf-8'), D222 / 'implementation/prepared-text-values.json': encode(values)}
    require(all(not path.exists() for path in [*outputs, RESULT]), 'all three output destinations absent before writes')
    for record in plan['inputs']:
        pinned(record)
    for pair in pairs.values():
        pinned(pair['source'])
        pinned(pair['archive'])
    for record in protected:
        pinned(record)
    result = {'round': 'R226', 'status': 'PREPARED_TEXT_ONLY', 'exit_code': 0, 'attempt': 1, 'retry': 0, 'argv': argv, 'cwd': str(ROOT), 'environment': environment, 'source_pin': gate['source_pin'], 'r226_plan_pin': values['r226_plan_pin'], 'r226_gate_pin': values['r226_gate_pin'], 'checks': CHECKS, 'diagnostics': DIAGNOSTICS, 'outputs': [pin(path, data) for path, data in outputs.items()], 'edit_units': 9, 'function_regions': 7, 'live_product_writes': 0, 'native_apply_calls': 0, 'product_execution': False}
    result_data = encode(result)
    for path, data in outputs.items():
        write_exclusive(path, data)
    write_exclusive(RESULT, result_data)
    signal.alarm(0)
    print(json.dumps({'status': result['status'], 'outputs': result['outputs'], 'result': pin(RESULT, result_data), 'edit_units': 9, 'function_regions': 7}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        signal.alarm(0)
        failure = {'round': 'R226', 'status': 'FAILED_STOP_NO_RETRY', 'exit_code': 1, 'attempt': 1, 'retry': 0, 'exception_type': type(error).__name__, 'exception': str(error), 'full_traceback': traceback.format_exc(), 'checks': CHECKS, 'diagnostics': DIAGNOSTICS, 'write_attempts': WRITE_ATTEMPTS, 'product_execution': False}
        with RESULT.open('xb') as handle:
            handle.write(encode(failure))
        print(json.dumps({'status': failure['status'], 'failure_result': str(RESULT)}, ensure_ascii=False))
        raise SystemExit(1)
