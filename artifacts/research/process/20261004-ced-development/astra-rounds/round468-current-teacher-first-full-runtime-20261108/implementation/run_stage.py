"""One R468 production stage; no retries, alternate recipes or product changes."""

import argparse
import csv
import ctypes
import fcntl
import hashlib
import io
import json
import os
import resource
import shutil
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUND = Path(__file__).resolve().parents[1]
RAW = ROOT / 'cache/research/r468-teacher-first-full-20261108'
PLAN_SHA = 'c55fd44ce577d95048f827fba8382ac4fe2338f63cb2458386ddcc03fcec3298'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def load(path):
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError('nonfinite value')

    return json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=nonfinite)


def sources(plan):
    paths = sorted((ROOT / 'src/cloud_edge_robot_arm').rglob('*.py'))
    paths += [ROOT / name for name in (
        'configs/research/native_operational_calibration.yaml',
        'assets/robots/franka_panda/scene.xml',
        'assets/robots/franka_panda/scene_pose_marker_outboard_v3.xml',
        'scripts/collect_native_calibration.py', 'pyproject.toml')]
    actual = {str(path.relative_to(ROOT)): sha(path) for path in paths}
    if actual != plan['source_hashes']:
        raise ValueError('source generation drift')
    for row in plan['input_pins']:
        path = ROOT / row['path']
        if sha(path) != row['sha256']:
            raise ValueError('input drift: ' + row['path'])
    return actual


def protocol_check(plan):
    path = ROUND / 'actual/protocol/protocol.json'
    protocol = load(path)
    assert protocol['source_hashes'] == plan['source_hashes']
    assert protocol['source_generation'] == plan['source_generation']
    assert protocol['settings'] == load(ROOT / 'configs/research/native_operational_calibration.yaml')
    assert protocol['config_sha256'] == sha(ROOT / 'configs/research/native_operational_calibration.yaml')
    assert protocol['role']['scope'] == 'TEACHER_COLLECTION'
    assert protocol['role']['provider'] is None and protocol['role']['model'] is None
    assert protocol['role']['model_requests'] == 0
    assert protocol['native_qualification'] == 'UNKNOWN'
    assert protocol['admission']['execution_admitted'] is False
    assert len(protocol['actions']) == 8
    assert protocol['physical_budget'] == 12960
    assert protocol['explicit_acquisition_budget'] == 12976
    assert protocol['implicit_capture_budget'] == 12962
    assert protocol['render_pass_budget'] == 64852
    assert 120 + sum(row['horizon']['total_steps'] for row in protocol['actions']) == 12960
    assignments = protocol['assignments']
    assert len(assignments) == 9
    for index, row in enumerate(assignments, 1):
        assert row['assignment_id'] == f'native-r439-{index:04d}'
        assert row['seed'] == 439000 + index
        assert row['status'] == ('RELEASED' if index == 1 else 'PREASSIGNED_NOT_RUN')
    return {'path': str(path), 'sha256': sha(path), 'source_generation': protocol['source_generation']}


def file_bytes(root):
    total = count = 0
    if not root.exists():
        return {'bytes': 0, 'files': 0}
    for directory, folders, files in os.walk(root, followlinks=False):
        for name in folders + files:
            if (Path(directory) / name).is_symlink():
                raise ValueError('symlink in monitored output')
        for name in files:
            total += (Path(directory) / name).stat().st_size
            count += 1
    return {'bytes': total, 'files': count}


def process(pid):
    try:
        raw = Path(f'/proc/{pid}/stat').read_text()
        fields = raw[raw.rfind(')') + 2:].split()
        resident = int(Path(f'/proc/{pid}/statm').read_text().split()[1])
        return {'pid': pid, 'state': fields[0], 'ppid': int(fields[1]),
                'pgid': int(fields[2]), 'sid': int(fields[3]),
                'starttime': int(fields[19]), 'rss_bytes': resident * os.sysconf('SC_PAGE_SIZE')}
    except (FileNotFoundError, ProcessLookupError):
        return None


def children(pid):
    try:
        return [int(value) for value in Path(f'/proc/{pid}/task/{pid}/children').read_text().split()]
    except (FileNotFoundError, ProcessLookupError):
        return []


def admission(plan, evidence):
    rows = []
    for spec in plan['gpu_admission']['commands']:
        label = spec['label']
        started = time.monotonic()
        row = {'label': label, 'argv': spec['argv'], 'started_utc': datetime.now(UTC).isoformat()}
        try:
            result = subprocess.run(spec['argv'], env=plan['gpu_admission']['admission_env'],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=8, check=False)
            code, output, error_output = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired as error:
            code, output, error_output = None, error.stdout or b'', error.stderr or b''
            row['error'] = 'TIMEOUT'
        for name, data in [('stdout', output), ('stderr', error_output)]:
            path = evidence / f'admission-{label}.{name}'
            with path.open('xb') as stream:
                stream.write(data)
            row[name] = {'path': str(path), 'sha256': sha(path), 'bytes': len(data)}
        row.update(returncode=code, elapsed_s=time.monotonic() - started)
        rows.append(row)
        save(evidence / f'admission-{label}.json', row)
        if code != 0:
            raise RuntimeError('resource admission command failed: ' + label)
    gpu = list(csv.reader(io.StringIO((evidence / 'admission-gpu.stdout').read_text())))
    assert len(gpu) == 1 and len(gpu[0]) == 6
    gpu = [value.strip() for value in gpu[0]]
    assert gpu[0] == '0' and gpu[1] == 'NVIDIA GeForce RTX 4070 Ti SUPER'
    assert all(value.isdigit() for value in gpu[2:]) and int(gpu[4]) >= 8192
    assert (evidence / 'admission-compute.stdout').read_bytes() == b''
    service = dict(line.split('=', 1) for line in (evidence / 'admission-qwen_service.stdout').read_text().splitlines())
    assert all(service[key] == value for key, value in {
        'LoadState': 'loaded', 'ActiveState': 'inactive', 'SubState': 'dead',
        'MainPID': '0', 'ControlPID': '0'}.items())
    save(evidence / 'admission.json', {'status': 'ADMITTED_AT_SNAPSHOT', 'commands': rows,
                                    'gpu_csv_fields': gpu, 'qwen': service})


def run(stage):
    assert sha(ROUND / 'plan.json') == PLAN_SHA
    plan = load(ROUND / 'plan.json')
    spec = plan['stages'][stage]
    sources(plan)
    assert subprocess.check_output(['/usr/bin/git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                   env={'PATH': '/usr/bin:/bin'}, text=True).strip() == plan['baseline_head']
    assert not subprocess.check_output(['/usr/bin/git', 'diff', '--name-only', '--', 'src', 'scripts', 'configs', 'assets', 'tests'], cwd=ROOT,
                                       env={'PATH': '/usr/bin:/bin'}, text=True).strip()
    frozen = load(ROUND / 'implementation/frozen-invocations.json')
    assert frozen['runner_sha256'] == sha(Path(__file__)) and frozen['plan_sha256'] == PLAN_SHA
    evidence = Path(spec['evidence_directory'])
    assert not evidence.exists()
    for path in [evidence, Path(spec['argv'][-1]), RAW]:
        assert not any(parent.is_symlink() for parent in (path, *path.parents))
    protocol = None
    if stage != 'prepare':
        prior = load(ROUND / 'actual/prepare-evidence/result.json')
        assert prior['returncode'] == 0 and prior['reaped'] and not prior['remaining_live'] and not prior['errors']
        protocol = protocol_check(plan)
        assert protocol == load(ROUND / 'actual/prepare-evidence/protocol-pin.json')
    if stage == 'full':
        assert not (ROUND / 'actual/protocol/claims').exists() and not RAW.exists()
    if stage == 'read':
        prior = load(ROUND / 'actual/full-evidence/result.json')
        assert prior['launched'] and prior['reaped'] and not prior['remaining_live'] and prior['source_unchanged']
    for name in ('XDG_CACHE_HOME', 'TMPDIR'):
        Path(spec['env'][name]).mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True)
    started = time.monotonic()
    save(evidence / 'started.json', {'stage': stage, 'spec': spec, 'plan_sha256': PLAN_SHA,
         'runner_sha256': sha(Path(__file__)), 'started_utc': datetime.now(UTC).isoformat(),
         'monotonic': started, 'protocol': protocol, 'retry': 0})
    lock = None
    child = None
    owned = {}
    errors = []
    signals = []
    reaped = []
    reason = None
    peak_rss = peak_bytes = peak_raw = 0
    peak_interval = 0.0
    last_sample = None
    state = 'NOT_LAUNCHED'
    remaining = []
    initial_bytes = file_bytes(ROUND / 'actual')['bytes'] + file_bytes(RAW)['bytes']

    def refresh():
        pending = children(os.getpid()) + list(owned)
        seen = set()
        while pending:
            pid = pending.pop()
            if pid in seen:
                continue
            seen.add(pid)
            row = process(pid)
            if row is None:
                continue
            if pid in owned and owned[pid]['starttime'] != row['starttime']:
                continue
            owned.setdefault(pid, row)
            pending.extend(children(pid))
        live = []
        for pid, identity in owned.items():
            row = process(pid)
            if row is not None and row['starttime'] == identity['starttime'] and row['state'] != 'Z':
                live.append(row)
        return live

    def deliver(sig):
        live = refresh()
        groups = {row['pgid'] for row in live if child is not None and row['pgid'] == child.pid and row['sid'] == child.pid}
        for group in groups:
            try:
                os.killpg(group, sig)
                signals.append({'pgid': group, 'signal': signal.Signals(sig).name})
            except ProcessLookupError:
                pass
        for row in live:
            if row['pgid'] in groups:
                continue
            current = process(row['pid'])
            if current is not None and current['starttime'] == row['starttime']:
                try:
                    os.kill(row['pid'], sig)
                    signals.append({'pid': row['pid'], 'starttime': row['starttime'], 'signal': signal.Signals(sig).name})
                except ProcessLookupError:
                    pass

    def interrupted(signum, frame):
        nonlocal reason
        reason = 'SIGNAL_' + signal.Signals(signum).name

    handlers = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        assert ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0
        assert shutil.disk_usage(ROOT).free >= spec['free_disk_min_bytes']
        if stage == 'full':
            path = Path(plan['gpu_admission']['lock_path'])
            assert not path.is_symlink()
            path.parent.mkdir(parents=True, exist_ok=True)
            lock = path.open('a+b')
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            admission(plan, evidence)
        with (evidence / 'stdout.log').open('xb') as stdout, (evidence / 'stderr.log').open('xb') as stderr:
            child = subprocess.Popen(spec['argv'], cwd=spec['cwd'], env=spec['env'],
                                     stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                     start_new_session=True, shell=False)
            row = process(child.pid)
            if row is not None:
                owned[child.pid] = row
            state = 'RUNNING'
            while child.poll() is None:
                now = time.monotonic()
                live = refresh()
                rss = sum(row['rss_bytes'] for row in live)
                raw = file_bytes(RAW)
                actual = file_bytes(ROUND / 'actual')
                total = raw['bytes'] + actual['bytes']
                free = shutil.disk_usage(ROOT).free
                if last_sample is not None:
                    peak_interval = max(peak_interval, now - last_sample)
                last_sample = now
                peak_rss, peak_bytes, peak_raw = max(peak_rss, rss), max(peak_bytes, total), max(peak_raw, raw['bytes'])
                sample = {'utc': datetime.now(UTC).isoformat(), 'elapsed_s': now - started,
                          'owned_live': live, 'tree_rss_bytes': rss, 'raw': raw, 'actual': actual,
                          'total_bytes': total, 'new_bytes': max(0, total - initial_bytes), 'free_bytes': free}
                with (evidence / 'resource-observations.jsonl').open('a') as stream:
                    stream.write(json.dumps(sample) + '\n')
                output_size = total if stage == 'full' else max(0, total - initial_bytes)
                if now - started >= spec['child_wall_s']:
                    reason = 'WALL_LIMIT'
                elif rss > spec['tree_RSS_bytes']:
                    reason = 'TREE_RSS_LIMIT'
                elif output_size > spec['output_bytes_limit'] or raw['bytes'] > plan['budgets']['raw_bytes']:
                    reason = 'OUTPUT_BYTES_LIMIT'
                elif free < spec['free_disk_min_bytes']:
                    reason = 'FREE_DISK_LIMIT'
                if reason:
                    break
                time.sleep(max(0, 0.5 - (time.monotonic() - now)))
            state = 'STOPPED' if reason else 'FINISHED'
    except BaseException as error:
        state = 'FAILED_STOPPED'
        errors.append({'type': type(error).__name__, 'message': str(error)})
    finally:
        cleanup = time.monotonic()
        save(evidence / 'exit-before-cleanup.json', {'state': state, 'reason': reason,
             'returncode': child.poll() if child is not None else None, 'utc': datetime.now(UTC).isoformat()})
        try:
            if child is not None:
                if refresh():
                    deliver(signal.SIGTERM)
                while refresh() and time.monotonic() - cleanup < 5:
                    child.poll()
                    time.sleep(0.05)
                if refresh():
                    deliver(signal.SIGKILL)
                child.wait(timeout=3)
                while refresh() and time.monotonic() - cleanup < 8:
                    time.sleep(0.05)
                while True:
                    try:
                        pid, status = os.waitpid(-1, os.WNOHANG)
                    except ChildProcessError:
                        break
                    if not pid:
                        break
                    reaped.append({'pid': pid, 'status': status})
                remaining = refresh()
                if remaining:
                    errors.append({'type': 'CleanupIncomplete', 'remaining_live': remaining})
        except BaseException as error:
            errors.append({'type': type(error).__name__, 'message': str(error), 'phase': 'cleanup'})
            remaining = refresh()
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
            if lock is not None and not remaining:
                fcntl.flock(lock, fcntl.LOCK_UN)
                lock.close()
    terminal = {'stage': stage, 'state': state, 'reason': reason, 'launched': child is not None,
                'returncode': child.returncode if child is not None else None,
                'reaped': child is not None and child.returncode is not None,
                'remaining_live': remaining, 'errors': errors, 'signals': signals,
                'adopted_reaped': reaped, 'owned': list(owned.values()),
                'elapsed_s': time.monotonic() - started, 'ended_utc': datetime.now(UTC).isoformat()}
    save(evidence / 'terminal.json', terminal)
    unchanged = False
    try:
        sources(plan)
        unchanged = True
    except BaseException as error:
        errors.append({'type': type(error).__name__, 'message': str(error), 'phase': 'source-after'})
    if stage == 'prepare' and terminal['returncode'] == 0 and unchanged and not errors:
        try:
            pin = protocol_check(plan)
            assert not (ROUND / 'actual/protocol/claims').exists() and not RAW.exists()
            save(evidence / 'protocol-pin.json', pin)
        except BaseException as error:
            errors.append({'type': type(error).__name__, 'message': str(error), 'phase': 'protocol-check'})
    logs = []
    for name in ('stdout.log', 'stderr.log'):
        path = evidence / name
        if path.exists():
            logs.append({'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size})
    final_raw = file_bytes(RAW)
    final_actual = file_bytes(ROUND / 'actual')
    final_total = final_raw['bytes'] + final_actual['bytes']
    final_output = final_total if stage == 'full' else max(0, final_total - initial_bytes)
    waited_peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024
    if final_output > spec['output_bytes_limit'] or final_raw['bytes'] > plan['budgets']['raw_bytes'] or waited_peak > spec['tree_RSS_bytes']:
        errors.append({'type': 'FinalResourceAuditExceeded'})
    result = dict(terminal, errors=errors, source_unchanged=unchanged, logs=logs,
                  peak_sampled_tree_rss_bytes=peak_rss, peak_sampled_total_bytes=peak_bytes,
                  peak_sampled_raw_bytes=peak_raw, maximum_sample_interval_s=peak_interval,
                  waited_child_maxrss_bytes=waited_peak,
                  rss_scope='Sampled concurrent owned tree plus Linux waited-child maximum (latter not tree sum)',
                  sampling='0.5s target cadence plus any observation overrun; intervals measured, not continuous hard enforcement',
                  final_raw=final_raw, final_actual=final_actual)
    save(evidence / 'result.json', result)
    print(json.dumps({key: result[key] for key in ('stage', 'state', 'returncode', 'reaped', 'remaining_live', 'errors', 'elapsed_s')}), flush=True)
    return 0 if result['returncode'] == 0 and unchanged and not errors and not reason and not remaining else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', required=True, choices=('prepare', 'full', 'read'))
    raise SystemExit(run(parser.parse_args().stage))
