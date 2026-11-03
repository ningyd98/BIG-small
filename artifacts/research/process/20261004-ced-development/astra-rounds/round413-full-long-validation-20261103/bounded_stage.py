"""Run one declared R413 stage; record raw termination before derived analysis."""
from datetime import UTC, datetime
import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import traceback

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUND = Path(__file__).resolve().parent

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write('\n')

def source_check(pins):
    drift = []
    for row in pins:
        path = ROOT / row['path']
        try:
            raw = path.read_bytes()
            if path.is_symlink() or len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
                drift.append(row['path'])
        except OSError:
            drift.append(row['path'])
    return drift

def processes():
    rows = {}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            raw = (path / 'stat').read_text()
            f = raw[raw.rfind(')') + 2:].split()
            rows[int(path.name)] = {'pid': int(path.name), 'state': f[0], 'ppid': int(f[1]),
                'pgid': int(f[2]), 'sid': int(f[3]), 'starttime_ticks': f[19],
                'cpu_ticks': int(f[11]) + int(f[12]), 'rss_pages': int(f[21])}
        except (OSError, ValueError, IndexError):
            pass
    return rows

def port_check(ports):
    rows = []
    for port in ports:
        try:
            with socket.socket() as connection:
                connection.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                connection.bind(('127.0.0.1', port))
            rows.append({'port': port, 'available': True})
        except OSError as error:
            rows.append({'port': port, 'available': False, 'error': str(error)})
    return rows

def run(spec_path):
    spec = json.loads(spec_path.read_text())
    directory = Path(spec['directory'])
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / 'invocation.json').exists():
        raise RuntimeError('Stage already invoked; refusing a second attempt')
    pins = json.loads((ROUND / 'preflight/runtime-source-pins.json').read_text())['files']
    before = source_check(pins)
    save(directory / 'source-before.json', {'drift': before, 'pins': 'preflight/runtime-source-pins.json'})
    save(directory / 'invocation.json', {**spec, 'started_utc': datetime.now(UTC).isoformat(),
        'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'spec_sha256': hashlib.sha256(spec_path.read_bytes()).hexdigest()})
    if before:
        save(directory / 'result.json', {'stage_id': spec['id'], 'state': 'BLOCKED_SOURCE_DRIFT',
            'launched': False, 'source_drift': before})
        return
    ports_before = port_check(spec.get('ports', []))
    save(directory / 'ports-before.json', ports_before)
    if any(not p['available'] for p in ports_before):
        save(directory / 'result.json', {'stage_id': spec['id'], 'state': 'BLOCKED_ENV',
            'launched': False, 'reason': 'Port unavailable; no listener reused or terminated', 'ports': ports_before})
        return
    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
        save(directory / 'result.json', {'stage_id': spec['id'], 'state': 'BLOCKED_ENV',
            'launched': False, 'reason': 'Subreaper prerequisite unavailable'})
        return
    owned, errors, signals, cancellations = {}, [], [], []
    process = None
    cleanup = False
    state = 'FINISHED'
    started = time.monotonic()
    reaped_adopted = []

    def refresh():
        current = processes()
        parents = {os.getpid()} | {pid for pid, row in owned.items()
            if pid in current and current[pid]['starttime_ticks'] == row['starttime_ticks']}
        changed = True
        while changed:
            changed = False
            for pid, row in current.items():
                if row['ppid'] in parents and pid not in parents:
                    parents.add(pid)
                    owned.setdefault(pid, row)
                    changed = True
        return [row for pid, row in current.items() if pid in owned
            and row['starttime_ticks'] == owned[pid]['starttime_ticks'] and row['state'] != 'Z']

    def deliver(sig):
        for row in refresh():
            try:
                os.kill(row['pid'], sig)
                signals.append({'pid': row['pid'], 'starttime_ticks': row['starttime_ticks'],
                    'signal': signal.Signals(sig).name, 'stage_root': process is not None and row['pid'] == process.pid})
            except ProcessLookupError:
                pass

    def interrupted(signum, frame):
        cancellations.append(signal.Signals(signum).name)
        if not cleanup:
            raise InterruptedError(signal.Signals(signum).name)

    handlers = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGINT)}
    next_sample = started
    with (directory / 'stdout.log').open('xb') as stdout, (directory / 'stderr.log').open('xb') as stderr:
        try:
            process = subprocess.Popen(spec['argv'], cwd=spec['cwd'], env=spec['env'], stdout=stdout,
                stderr=stderr, stdin=subprocess.DEVNULL, start_new_session=True)
            while process.poll() is None:
                live = refresh()
                now = time.monotonic()
                if now >= next_sample:
                    with (directory / 'resource-observations.jsonl').open('a') as out:
                        out.write(json.dumps({'elapsed_s': now-started, 'owned_live': live})+'\n')
                    next_sample = now + 20
                if now-started >= spec['timeout_s']:
                    state = 'TIMEOUT'
                    break
                time.sleep(0.5)
        except BaseException as error:
            state = 'INTERRUPTED' if process is not None else 'INFRASTRUCTURE_ERROR'
            errors.append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
        finally:
            cleanup = True
            cleanup_start = time.monotonic()
            save(directory / 'exit-observation-before-cleanup.json', {
                'state': state, 'returncode': process.poll() if process is not None else None,
                'at_utc': datetime.now(UTC).isoformat(), 'elapsed_s': time.monotonic()-started})
            deliver(signal.SIGTERM)
            while refresh() and time.monotonic()-cleanup_start < 15:
                if process is not None:
                    process.poll()
                time.sleep(0.1)
            if refresh():
                deliver(signal.SIGKILL)
            if process is not None:
                try:
                    process.wait(timeout=max(0.01, 30-(time.monotonic()-cleanup_start)))
                except subprocess.TimeoutExpired:
                    errors.append({'reason': 'stage_root_not_reaped'})
            save(directory / 'raw-exit.json', {'state': state,
                'returncode': process.returncode if process is not None else None,
                'reaped': process is not None and process.returncode is not None,
                'elapsed_s': time.monotonic()-started, 'at_utc': datetime.now(UTC).isoformat(),
                'signals': list(signals), 'errors': list(errors)})
            while refresh() and time.monotonic()-cleanup_start < 30:
                deliver(signal.SIGKILL)
                time.sleep(0.1)
            while True:
                try:
                    pid, status = os.waitpid(-1, os.WNOHANG)
                    if not pid:
                        break
                    reaped_adopted.append({'pid': pid, 'status': status})
                except ChildProcessError:
                    break
            remaining = refresh()
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
    # Persist termination and cleanup before optional source/port/report parsing.
    terminal = {'stage_id': spec['id'], 'state': state, 'launched': process is not None,
        'returncode': process.returncode if process is not None else None, 'elapsed_s': time.monotonic()-started,
        'ended_utc': datetime.now(UTC).isoformat(), 'signals': signals, 'errors': errors,
        'cancellations': cancellations, 'reaped': process is not None and process.returncode is not None,
        'remaining_live': remaining, 'adopted_children_reaped': reaped_adopted}
    save(directory / 'terminal.json', terminal)
    save(directory / 'owned-process-identities.json', list(owned.values()))
    drift = source_check(pins)
    ports_after = port_check(spec.get('ports', []))
    result = {**terminal, 'source_drift': drift, 'ports_after': ports_after,
        'stdout_bytes': (directory/'stdout.log').stat().st_size,
        'stderr_bytes': (directory/'stderr.log').stat().st_size}
    save(directory / 'result.json', result)
    print(json.dumps({k:result[k] for k in ['stage_id','state','returncode','elapsed_s','reaped','source_drift','remaining_live']}), flush=True)

if __name__ == '__main__':
    run(Path(sys.argv[1]).resolve())
