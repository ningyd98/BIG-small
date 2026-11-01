"""按 R375 Astra 计划执行一次有界数据库作用域对照；保留全部原始尝试。"""
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
PLAN = json.loads((HERE / 'plan.json').read_text())
ROOT = Path(PLAN['command']['cwd'])
R374 = HERE.parent / 'round374-diagnostic-runtime-prerequisites-20261101'
CONTINUATION = R374 / 'continuation-v2'
SOURCE_MANIFEST = HERE.parent / 'round373-full-workflow-rerun-20261101/preflight/workspace-source-before.json'
STAGE = 'workbench_module_without_runtime_db'
OUT = HERE / 'implementation' / STAGE


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def digest(path):
    raw = path.read_bytes()
    return {'path': str(path.relative_to(ROOT)), 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest()}


def source_check():
    manifest = json.loads(SOURCE_MANIFEST.read_text())
    drift = [r['path'] for r in manifest['files']
             if not (ROOT / r['path']).is_file()
             or digest(ROOT / r['path'])['sha256'] != r['sha256']]
    return {'manifest': digest(SOURCE_MANIFEST), 'files_checked': len(manifest['files']), 'drift': drift}


def processes():
    rows = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            raw = (path / 'stat').read_text()
            f = raw[raw.rfind(')') + 2:].split()
            rows.append({'pid': int(path.name), 'ppid': int(f[1]), 'pgid': int(f[2]),
                         'starttime_ticks': f[19], 'state': f[0],
                         'cmdline': (path / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')})
        except (FileNotFoundError, ProcessLookupError):
            pass
    return rows


def members(pgid):
    return [p for p in processes() if p['pgid'] == pgid and p['state'] != 'Z']


def applicability():
    drift = [r['path'] for r in PLAN['inputs']
             if not (ROOT / r['path']).is_file() or digest(ROOT / r['path']) != r]
    before = source_check()
    if drift or before['drift']:
        raise RuntimeError({'input_drift': drift, 'source_drift': before['drift']})
    original = json.loads((ROOT / PLAN['original_failure']['directory'] / 'invocation.json').read_text())
    old = str(ROOT / PLAN['original_failure']['directory'])
    relocated_env = {k: v.replace(old, str(OUT)) for k, v in original['env'].items()}
    removed = relocated_env.pop('SIMULATION_RUNTIME_DB')
    command = PLAN['command']
    assert relocated_env == command['env'], 'Only the planned env removal/relocation is allowed'
    assert [v.replace(old, str(OUT)) for v in original['argv']] == command['argv']
    assert 'SIMULATION_RUNTIME_DB' not in command['env']
    for key in ('MODEL_CONTROL_DB', 'DASHBOARD_ARTIFACT_ROOT'):
        assert Path(command['env'][key]).is_absolute() and Path(command['env'][key]).is_relative_to(OUT)
    return {'checked_utc': datetime.now(UTC).isoformat(), 'input_pins_verified': len(PLAN['inputs']),
            'plan': digest(HERE / 'plan.json'), 'launcher': digest(Path(__file__)), 'source_before': before,
            'env_diff': {'relocation_from': old, 'relocation_to': str(OUT),
                         'semantic_removed': {'SIMULATION_RUNTIME_DB': removed},
                         'other_semantic_changes': []}}


def prerequisite_check():
    completion = CONTINUATION / 'completion.json'
    if not completion.exists():
        raise RuntimeError('Entire continuation-v2 is not terminal')
    value = json.loads(completion.read_text())
    assert value['state'] == 'ALL_GROUPS_ACCOUNTED' and not value['source_after']['drift']
    live = processes()
    receipt = json.loads((CONTINUATION / 'launch-receipt.json').read_text())
    for old in receipt['processes']:
        assert not any(p['pid'] == old['pid'] and p['starttime_ticks'] == old['starttime_ticks']
                       for p in live), 'Predecessor process has not exited'
    child_count = 0
    for child in (CONTINUATION / 'children').iterdir():
        if not child.is_dir():
            continue
        cleanup = json.loads((child / 'cleanup.json').read_text())
        identity = json.loads((child / 'process-identity.json').read_text())
        assert not cleanup.get('remaining_live') and not members(identity['pgid'])
        child_count += 1
    test_processes = [p for p in live if p['state'] != 'Z' and p['pid'] != os.getpid()
                      and str(ROOT) in p['cmdline'] and
                      any(token in p['cmdline'].split() for token in ('pytest', 'playwright'))]
    assert not test_processes, test_processes
    return {'continuation_completion': digest(completion), 'children_cleaned': child_count,
            'predecessor_processes_exited': True, 'other_product_test_processes': test_processes}


def cleanup(process, was_timeout):
    result = {'signals': [], 'after_wait': members(process.pid)}
    deadline = time.monotonic() + PLAN['command']['cleanup_total_s']
    if result['after_wait']:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            result['signals'].append('SIGTERM')
        except ProcessLookupError:
            pass
        grace = min(deadline, time.monotonic() + PLAN['command']['TERM_grace_s'])
        while members(process.pid) and time.monotonic() < grace:
            time.sleep(0.1)
        if members(process.pid):
            try:
                os.killpg(process.pid, signal.SIGKILL)
                result['signals'].append('SIGKILL')
            except ProcessLookupError:
                pass
    try:
        process.wait(timeout=max(0.01, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        pass
    while members(process.pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    result.update(remaining_live=members(process.pid), returncode=process.poll(),
                  reaped=process.poll() is not None, child_timeout=was_timeout)
    return result


def database_inventory():
    rows = []
    for path in sorted(OUT.rglob('simulation_runtime.db')):
        if path.is_symlink():
            continue
        relative = path.relative_to(OUT)
        rows.append({**digest(path),
                     'per_test_artifact_path': relative.parts[0] == 'persistent-basetemp'
                     and len(relative.parts) >= 4 and path.parent.name == 'artifacts',
                     'adjacent': [digest(Path(str(path) + suffix)) for suffix in ('-wal', '-shm')
                                  if Path(str(path) + suffix).is_file()]})
    return {'files': rows, 'all_produced_per_test': bool(rows) and all(r['per_test_artifact_path'] for r in rows),
            'stage_runtime_db_exists': (OUT / 'runtime/simulation_runtime.db').exists(),
            'method': 'Quiescent filesystem path/size/SHA256 inventory only; no SQLite connection.',
            'limitation': 'Known default historical database and entire filesystem were not inventoried.'}


def main():
    if sys.argv[1:] not in (['--inspect'], ['--run']):
        raise SystemExit('Use --inspect or --run')
    prepared = applicability()
    if sys.argv[1:] == ['--inspect']:
        save(HERE / 'adapter-preparation.json', prepared)
        print(json.dumps(prepared, ensure_ascii=False))
        return
    prerequisites = prerequisite_check()
    remaining = PLAN['global_budget']['no_new_test_after_epoch_s'] - time.time()
    assert not OUT.exists(), 'One attempt only; output already exists'
    if remaining < PLAN['global_budget']['start_requires_remaining_s']:
        save(HERE / 'not-run.json', {'state': 'NOT_RUN_BUDGET', 'remaining_s': remaining,
                                    'utc': datetime.now(UTC).isoformat(), 'prerequisites': prerequisites})
        return
    OUT.mkdir(parents=True, exist_ok=False)
    for relative in ('r223/resources', 'r223/cases', 'runtime/artifacts', 'pycache', 'ruff-cache', 'mypy-cache'):
        (OUT / relative).mkdir(parents=True, exist_ok=False)
    save(OUT / 'preflight.json', {**prepared, 'prerequisites': prerequisites, 'wall_remaining_s': remaining})
    save(OUT / 'source-before.json', prepared['source_before'])
    command = PLAN['command']
    invocation = {'stage_id': STAGE, 'argv': command['argv'], 'cwd': str(ROOT), 'env': command['env'],
                  'timeout_s': command['child_timeout_s'], 'started_utc': datetime.now(UTC).isoformat(),
                  'environment_retry': False, 'diagnostic_comparison': True}
    save(OUT / 'invocation.json', invocation)
    started = time.monotonic()
    timed_out = False
    execution_errors = []
    evidence_errors = []
    process = None
    cleaned = {'reaped': False, 'remaining_live': [], 'signals': []}

    def outer_stop(signum, frame):
        raise RuntimeError('Bounded outer supervisor requested stop: ' + str(signum))

    signal.signal(signal.SIGTERM, outer_stop)
    with (OUT / 'stdout.log').open('wb') as stdout, (OUT / 'stderr.log').open('wb') as stderr:
        try:
            process = subprocess.Popen(command['argv'], cwd=ROOT, env=command['env'],
                                       stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                save(OUT / 'process-identity.json', {'pid': process.pid, 'pgid': process.pid,
                                                   'members_at_launch': members(process.pid)})
                process.wait(timeout=command['child_timeout_s'])
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                cleaned = cleanup(process, timed_out)
                save(OUT / 'cleanup.json', cleaned)
        except Exception as error:
            execution_errors.append({'type': type(error).__name__, 'message': str(error)})

    def observed(label, function, fallback):
        try:
            return function()
        except Exception as error:
            evidence_errors.append({'evidence': label, 'type': type(error).__name__, 'message': str(error)})
            return fallback

    after = observed('source-after', source_check, {'drift': ['SOURCE_CHECK_UNAVAILABLE']})
    if cleaned['reaped'] and not cleaned['remaining_live']:
        inventory = observed('database-path-inventory', database_inventory,
                             {'state': 'READ_ERROR', 'all_produced_per_test': False, 'stage_runtime_db_exists': None})
    else:
        inventory = {'state': 'NOT_PERFORMED_CLEANUP_INCOMPLETE', 'all_produced_per_test': False,
                     'stage_runtime_db_exists': None}
    save(OUT / 'database-path-inventory.json', inventory)
    junit = OUT / 'junit.xml'
    tests = observed('junit.xml', lambda: list(ET.parse(junit).getroot().iter('testcase')), [])
    bad = [t.attrib.get('name') for t in tests if any(t.find(tag) is not None for tag in ('failure', 'error', 'skipped'))]
    events_path = OUT / 'pytest-events.jsonl'
    events = observed('pytest-events.jsonl',
                      lambda: [json.loads(s) for s in events_path.read_text().splitlines()], [])
    starts = [e['nodeid'] for e in events if e.get('event') == 'report' and e.get('when') == 'setup']
    returncode = process.returncode if process else None
    accepted = (returncode == 0 and not execution_errors and not evidence_errors
                and not timed_out and not cleaned['remaining_live']
                and cleaned['reaped'] and not after['drift'] and len(tests) == 7 and not bad
                and starts == command['expected_nodeids_in_order'] and inventory['all_produced_per_test']
                and not inventory['stage_runtime_db_exists'])
    result = {'stage_id': STAGE, 'state': 'TIMEOUT' if timed_out else 'FINISHED',
              'returncode': returncode, 'elapsed_s': time.monotonic() - started,
              'ended_utc': datetime.now(UTC).isoformat(), 'reaped': cleaned['reaped'],
              'source_after': after, 'junit_exists': junit.exists(), 'junit_tests': len(tests),
              'junit_nonpassing': bad, 'node_order_matches': starts == command['expected_nodeids_in_order'],
              'comparison_acceptance': accepted, 'environment_retry': False,
              'execution_errors': execution_errors, 'evidence_errors': evidence_errors,
              'boundary': 'One same-order module comparison; original failed attempt remains unchanged.'}
    save(OUT / 'result.json', result)
    print(json.dumps(result, ensure_ascii=False))
    if not accepted:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
