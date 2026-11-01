"""R373 bounded diagnostic runner; does not modify product or test sources."""
import argparse
from collections import defaultdict
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

ROUND = Path(__file__).resolve().parent
ROOT = Path.cwd()
PLAN = json.loads((ROUND / 'plan.json').read_text())
BASELINE = json.loads((ROUND / 'preflight/workspace-source-before.json').read_text())
PYTHON = str(ROOT / '.venv/bin/python')
EXCLUDE = ' and '.join('not ' + marker for marker in PLAN['collection']['marker_exclusions'])


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def source_check():
    drift = []
    for row in BASELINE['files']:
        p = ROOT / row['path']
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != row['sha256']:
            drift.append(row['path'])
    return {'manifest': str(ROUND / 'preflight/workspace-source-before.json'), 'drift': drift}


def prepare():
    nodes = [s for s in (ROUND / 'preflight/collect.stdout').read_text().splitlines()
             if s.startswith('tests/') and '::' in s]
    assert len(nodes) == len(set(nodes)) == 4732
    stages = []
    for section in ('static_commands', 'dashboard_commands', 'ced_commands'):
        stages.extend(PLAN[section])
    reserved = {item['nodeid'] for item in PLAN['pytest']['t3']}
    closure = sorted(n for n in nodes if n.startswith('tests/test_operational_runtime_closure.py::') and n not in reserved)
    mujoco = [n for n in nodes if n.split('::')[0] in PLAN['pytest']['key_mujoco']['files']]
    ordinary = defaultdict(list)
    for node in nodes:
        if node not in reserved and node not in closure and node not in mujoco:
            ordinary[node.split('::')[0]].append(node)
    groups = [[] for _ in range(6)]
    for i, name in enumerate(sorted(ordinary)):
        groups[i % 6].extend(ordinary[name])
    for i, group in enumerate(groups):
        stages.append({'id': f'pytest_software_{i+1:02}', 'nodes': group, 'timeout_s': 900})
    for i in range(3):
        stages.append({'id': f'pytest_closure_{i+1:02}', 'nodes': closure[i*len(closure)//3:(i+1)*len(closure)//3], 'timeout_s': 900, 'closure': True})
    stages.append({'id': 'mujoco_key', 'nodes': mujoco, 'timeout_s': 900})
    for item in PLAN['pytest']['t3']:
        stages.append({**item, 'nodes': [item['nodeid']], 'closure': True})
    for item in PLAN['e2e'].values():
        if isinstance(item, dict):
            stages.append({**item, 'argv': [s.replace('<R373>', str(ROUND)) for s in item['argv']], 'cwd': str(ROOT / 'dashboard')})
    assigned = [n for s in stages for n in s.get('nodes', [])]
    assert sorted(assigned) == sorted(nodes)
    write(ROUND / 'stages.json', stages)
    write(ROUND / 'assignment-manifest.json', {'collected': len(nodes), 'stages': {s['id']: s.get('nodes', []) for s in stages if 'nodes' in s}})
    write(ROUND / 'batch-start.json', {'started_utc': datetime.now(UTC).isoformat(), 'started_epoch_s': time.time(), 'max_wall_s': 28800})
    (ROUND / 'progress.md').write_text('# R373 progress\n\nPlan: plan.json. Diagnostic only; no repairs.\n\nCollection and three static checks reused from preflight.\n')
    print(json.dumps({'stages': len(stages), 'assigned_nodes': len(assigned)}))


def environment(stage, directory):
    env = {k: os.environ[k] for k in ('HOME', 'USER', 'LOGNAME', 'TMPDIR', 'DISPLAY', 'XAUTHORITY', 'LD_LIBRARY_PATH', '__EGL_VENDOR_LIBRARY_FILENAMES') if k in os.environ}
    env.update(PLAN['environment']['base'])
    env.update(REAL_MOTION_DISPATCH_ENABLED='false', PLAYWRIGHT_BROWSERS_PATH=str(ROOT / 'cache/playwright'),
               PYTHONPYCACHEPREFIX=str(directory / 'pycache'), RUFF_CACHE_DIR=str(directory / 'ruff-cache'),
               MYPY_CACHE_DIR=str(directory / 'mypy-cache'), R373_PYTEST_EVENTS=str(directory / 'pytest-events.jsonl'),
               R373_STAGE_DIR=str(directory))
    env['PYTHONPATH'] += ':' + str(ROUND / 'adapters')
    if stage.get('closure'):
        plugin = ROOT / PLAN['environment']['closure_plugin']
        env['PYTHONPATH'] += ':' + str(plugin.parent)
        for key, value in PLAN['environment']['closure_env'].items():
            env[key] = value.replace('<stage>', str(directory))
        for name in ('resources', 'resources-a'):
            (directory / name).mkdir()
    if stage['id'].startswith('dashboard_e2e'):
        env.update(BIGSMALL_E2E_ARTIFACT_ROOT=str(directory / 'runtime'),
                   PLAYWRIGHT_JUNIT_OUTPUT_FILE=str(directory / 'junit.xml'),
                   DASHBOARD_ARTIFACT_ROOT=str(directory / 'runtime'),
                   MODEL_CONTROL_DB=str(directory / 'runtime/model_control.db'),
                   SIMULATION_RUNTIME_DB=str(directory / 'runtime/simulation_runtime.db'))
    if stage['id'] == 'dashboard_e2e_research':
        original = ROOT / 'artifacts/research/process/20261004-ced-development/t17b-ui-module/browser'
        shutil.copyfile(original / 'backend.py', directory / 'backend.py')
        shutil.copytree(original / 'fixture', directory / 'fixture')
    return env


def run(stage_id, retry=False):
    stage = next(s for s in json.loads((ROUND / 'stages.json').read_text()) if s['id'] == stage_id)
    original = ROUND / 'implementation' / stage_id
    directory = original if not retry else ROUND / 'implementation' / (stage_id + '-environment-retry')
    directory.mkdir(parents=True, exist_ok=False)
    before = source_check()
    write(directory / 'source-before.json', before)
    if before['drift']:
        write(directory / 'result.json', {'stage_id': stage_id, 'state': 'BLOCKED_SOURCE_DRIFT', **before})
        return
    argv = list(stage.get('argv', []))
    if 'nodes' in stage:
        argv = [PYTHON, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-p', 'r373_tracking', '-m', EXCLUDE]
        if stage.get('closure'):
            argv += ['-p', 'r235_startup_prerequisite']
        argv += stage['nodes'] + [f'--basetemp={directory}/persistent-basetemp', f'--junitxml={directory}/junit.xml']
    if retry:
        argv = [s.replace(str(original), str(directory)) for s in argv]
    env = environment(stage, directory)
    started = time.monotonic()
    invocation = {'stage_id': stage_id, 'argv': argv, 'cwd': stage.get('cwd', str(ROOT)), 'env': env,
                  'timeout_s': stage['timeout_s'], 'started_utc': datetime.now(UTC).isoformat(), 'environment_retry': retry}
    write(directory / 'invocation.json', invocation)
    print('START ' + stage_id, flush=True)
    state = 'FINISHED'
    signals = []
    with (directory / 'stdout.log').open('xb') as out, (directory / 'stderr.log').open('xb') as err:
        process = subprocess.Popen(argv, cwd=invocation['cwd'], env=env, stdout=out, stderr=err, stdin=subprocess.DEVNULL, start_new_session=True)
        while process.poll() is None:
            if time.monotonic() - started >= stage['timeout_s']:
                state = 'TIMEOUT'
            if max(out.tell(), err.tell()) > 268435456:
                state = 'OUTPUT_LIMIT'
            if state != 'FINISHED':
                os.killpg(process.pid, signal.SIGTERM); signals.append('SIGTERM')
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL); signals.append('SIGKILL')
                    process.wait(timeout=10)
                break
            time.sleep(0.5)
        process.wait()
    result = {'stage_id': stage_id, 'state': state, 'returncode': process.returncode,
              'elapsed_s': time.monotonic() - started, 'ended_utc': datetime.now(UTC).isoformat(),
              'signals': signals, 'reaped': True, 'environment_retry': retry,
              'junit_exists': (directory / 'junit.xml').exists(), 'source_after': source_check(),
              'stream_bytes': {name: (directory / name).stat().st_size for name in ('stdout.log', 'stderr.log')}}
    write(directory / 'result.json', result)
    with (ROUND / 'progress.md').open('a') as ledger:
        ledger.write(f"\n- {directory.name}: {state}, exit={process.returncode}, {result['elapsed_s']:.3f}s; evidence implementation/{directory.name}.\n")
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'run', 'batch'])
    parser.add_argument('stages', nargs='*')
    parser.add_argument('--environment-retry', action='store_true')
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
    else:
        for stage_id in args.stages:
            start = json.loads((ROUND / 'batch-start.json').read_text())['started_epoch_s']
            if time.time() - start > 28800 - 900:
                print('BATCH_BUDGET_STOP', flush=True)
                break
            run(stage_id, args.environment_retry)
