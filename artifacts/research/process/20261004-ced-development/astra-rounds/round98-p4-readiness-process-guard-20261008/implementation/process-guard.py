"""Read-only structured argv observation; ROOT separately decides resource readiness."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import re

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
KNOWN = {'run_operational_prefix_v1.py', 'collect_native_calibration.py',
         'run_rgbd_pilot.py', 'probe_rgbd_roles.py', 'generate_rgbd_protocol_evidence.py'}
MODULES = {Path(n).stem for n in KNOWN} | {'scripts.' + Path(n).stem for n in KNOWN}
SHELLS = {'bash', 'sh', 'dash', 'zsh', 'fish'}
WRAPPERS = {'env', 'timeout', 'nice', 'nohup', 'sudo'}

def stamp():
    return datetime.now(timezone.utc).isoformat()

def program(name, default):
    base = Path(name).name
    if base in KNOWN:
        return {'kind': 'KNOWN_CAPTURE_PROGRAM', 'program': base}
    if 'visible_marker' in base or 'marker_observ' in base:
        return {'kind': 'UNRESOLVED_MARKER_PROGRAM', 'program': base}
    return {'kind': default, 'program': base}

def classify(argv):
    if not argv:
        return {'kind': 'EMPTY_ARGV'}
    base = Path(argv[0]).name
    if base in KNOWN:
        return program(base, 'OTHER_EXECUTABLE')
    if base in WRAPPERS:
        return {'kind': 'UNRESOLVED_WRAPPER', 'program': base}
    if base in SHELLS:
        for operand in argv[1:]:
            if operand == '--':
                break
            if not operand.startswith('-'):
                return {'kind': 'SHELL_SCRIPT', 'program': Path(operand).name}
            if operand.startswith('-') and not operand.startswith('--') and 'c' in operand[1:]:
                return {'kind': 'OPAQUE_SHELL_COMMAND', 'program': base}
        return {'kind': 'SHELL_WITHOUT_COMMAND_OPERAND', 'program': base}
    if not re.fullmatch(r'python(?:3(?:\.\d+)?)?', base):
        return program(base, 'OTHER_EXECUTABLE')
    index = 1
    while index < len(argv):
        operand = argv[index]
        if operand == '--':
            index += 1
            break
        if operand == '-':
            return {'kind': 'OPAQUE_PYTHON_STDIN'}
        if operand == '-c' or operand.startswith('-c'):
            return {'kind': 'OPAQUE_PYTHON_CODE'}
        if operand == '-m' or operand.startswith('-m'):
            module = operand[2:] if len(operand) > 2 else (argv[index + 1] if index + 1 < len(argv) else '')
            if not module:
                return {'kind': 'UNRESOLVED_INTERPRETER'}
            return {'kind': 'KNOWN_CAPTURE_PROGRAM' if module in MODULES else 'UNKNOWN_PYTHON_MODULE', 'program': module}
        if operand in {'-W', '-X', '--check-hash-based-pycs'}:
            if index + 1 >= len(argv):
                return {'kind': 'UNRESOLVED_INTERPRETER'}
            index += 2
            continue
        if operand.startswith(('-W', '-X', '--check-hash-based-pycs=')):
            index += 1
            continue
        if operand.startswith('-'):
            if re.fullmatch(r'-[bBdEhiIOPqRsSuvVx]+', operand):
                index += 1
                continue
            return {'kind': 'UNRESOLVED_INTERPRETER'}
        break
    if index >= len(argv) or argv[index] == '-':
        return {'kind': 'OPAQUE_PYTHON_STDIN'}
    return program(argv[index], 'UNKNOWN_PYTHON_SCRIPT')

def self_test():
    cases = json.loads((HERE.parent / 'bounded-diagnosis.json').read_text())['memory_argv_cases']
    cases += [
        {'argv': ['timeout', '10', 'run_operational_prefix_v1.py'], 'expected': 'UNRESOLVED_WRAPPER'},
        {'argv': ['python', '--unrecognized', 'run_rgbd_pilot.py'], 'expected': 'UNRESOLVED_INTERPRETER'},
        {'argv': ['python', 'audit.py', 'probe_rgbd_roles.py'], 'expected': 'UNKNOWN_PYTHON_SCRIPT'},
    ]
    results = []
    for case in cases:
        actual = classify(case['argv'])['kind']
        assert actual == case['expected'], (case['argv'], actual, case['expected'])
        results.append({'expected': case['expected'], 'actual': actual})
    ancestor = {'relation': 'ANCESTOR', 'classification': classify(['python', '/work/run_operational_prefix_v1.py'])}
    assert ancestor['classification']['kind'] == 'KNOWN_CAPTURE_PROGRAM'
    results.append({'control': 'actual_capture_ancestor_remains_candidate', 'passed': True})
    print(json.dumps({'status': 'PASS', 'memory_cases': len(results), 'results': results, 'proc_scans': 0}))

def stat_row(path):
    raw = (path / 'stat').read_text()
    fields = raw[raw.rfind(')') + 2:].split()
    return {'state': fields[0], 'ppid': int(fields[1]), 'start_ticks': int(fields[19])}

def resources(path, cwd):
    devices, own_temp, outputs, children, errors = [], [], [], [], []
    try:
        for fd in (path / 'fd').iterdir():
            try:
                target = os.readlink(fd)
                if target.startswith(('/dev/nvidia', '/dev/dri')):
                    devices.append({'fd': fd.name, 'target': target})
                elif target.startswith('/tmp/') and '.db' in target:
                    own_temp.append({'fd': fd.name, 'target': target})
                elif '/t12-convergence-execution/P4/' in target:
                    outputs.append({'fd': fd.name, 'target': target})
            except OSError as error:
                errors.append({'field': 'fd', 'error': type(error).__name__})
        tasks = list((path / 'task').iterdir())
        for task in tasks:
            try:
                children.extend((task / 'children').read_text().split())
            except OSError as error:
                errors.append({'field': 'children', 'error': type(error).__name__})
    except OSError as error:
        errors.append({'field': 'resources', 'error': type(error).__name__})
    return {'cwd': cwd, 'device_holders': devices, 'own_temp_databases': own_temp,
            'P4_output_holders': outputs, 'children': sorted(set(children)), 'errors': errors,
            'limitation': 'Snapshot only; no content opened, no signals, no promise of future inactivity.'}

def observe(output):
    uid, self_pid = os.getuid(), os.getpid()
    rows, coverage = {}, {'current_uid': uid, 'visited': 0, 'other_uid': 0, 'disappeared': [], 'denied': [], 'truncated': [], 'reused': []}
    for path in Path('/proc').iterdir():
        if not path.name.isdecimal():
            continue
        pid = int(path.name)
        coverage['visited'] += 1
        try:
            process_uid = path.stat().st_uid
            if process_uid != uid:
                coverage['other_uid'] += 1
                continue
            first = stat_row(path)
            with (path / 'cmdline').open('rb') as stream:
                raw = stream.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                coverage['truncated'].append(pid)
                continue
            argv = [s.decode(errors='replace') for s in raw.split(b'\0') if s]
            classification = classify(argv)
            try:
                cwd = os.readlink(path / 'cwd')
            except OSError:
                cwd = None
            relevant = bool(cwd and (cwd == str(ROOT) or cwd.startswith(str(ROOT) + '/')))
            row = {'pid': pid, 'uid': process_uid, **first, 'argv_sha256': hashlib.sha256(raw).hexdigest(),
                   'argc': len(argv), 'classification': classification, 'project_relevant': relevant,
                   'cwd_class': 'PROJECT' if relevant else ('DESKTOP_TERMINAL' if classification.get('program') == 'gnome-terminal' else 'OTHER_WORKSPACE_OR_SYSTEM')}
            if relevant or classification['kind'] in {'KNOWN_CAPTURE_PROGRAM', 'UNRESOLVED_MARKER_PROGRAM'}:
                row['resource_evidence'] = resources(path, cwd)
            last = stat_row(path)
            if last['start_ticks'] != first['start_ticks']:
                coverage['reused'].append(pid)
                continue
            rows[pid] = row
        except FileNotFoundError:
            coverage['disappeared'].append(pid)
        except PermissionError:
            coverage['denied'].append(pid)
        except ProcessLookupError:
            coverage['disappeared'].append(pid)
    ancestors, seen, current = [], set(), self_pid
    while current in rows and current not in seen:
        seen.add(current)
        row = rows[current]
        row['observer_relation'] = 'SELF' if current == self_pid else 'ANCESTOR'
        ancestors.append({'pid': current, 'start_ticks': row['start_ticks'], 'ppid': row['ppid']})
        current = row['ppid']
    for pid, row in rows.items():
        row.setdefault('observer_relation', 'OTHER')
    candidates = [r for r in rows.values() if r['classification']['kind'] == 'KNOWN_CAPTURE_PROGRAM']
    unknowns = [r for r in rows.values() if r['classification']['kind'].startswith(('UNKNOWN_', 'OPAQUE_', 'UNRESOLVED_', 'SHELL_SCRIPT')) and r['observer_relation'] != 'SELF']
    evidence = [r for r in rows.values() if 'resource_evidence' in r]
    result = {'at': stamp(), 'status': 'OBSERVATION_COMPLETE', 'readiness_decision': 'ROOT_RESOURCE_REVIEW',
              'named_program_candidates': candidates, 'unknowns': unknowns, 'observer_chain': ancestors,
              'coverage_and_races': coverage, 'resource_evidence': evidence,
              'limitations': ['Current UID readable processes only', 'Names/device holders need attribution; not automatically renderer activity', 'Unknown does not require all-host idle', 'No future inactivity guarantee'],
              'processes_killed_or_signalled': 0, 'actual_authorized': False}
    with output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'named_candidates': len(candidates), 'unknowns': len(unknowns), 'output': str(output)}))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--self-test', action='store_true')
    mode.add_argument('--observe', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        assert args.output is not None
        observe(args.output)
