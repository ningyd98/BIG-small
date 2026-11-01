"""为 R375 唯一对照提供 90 秒总上限，末 15 秒用于按身份清理。"""
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
PLAN = json.loads((HERE / 'plan.json').read_text())
ROOT = Path(PLAN['command']['cwd'])
OUT = HERE / 'implementation/workbench_module_without_runtime_db'
RECEIPTS = HERE / 'outer-run'


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def members(pgid):
    found = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            raw = (path / 'stat').read_text()
            f = raw[raw.rfind(')') + 2:].split()
            if int(f[2]) == pgid and f[0] != 'Z':
                found.append({'pid': int(path.name), 'pgid': pgid, 'starttime_ticks': f[19]})
        except (FileNotFoundError, ProcessLookupError):
            pass
    return found


def signal_owned(identity, sig, signals, errors):
    current = members(identity['pgid'])
    leader = next((p for p in current if p['pid'] == identity['pgid']), None)
    original = next((p for p in identity['members_at_launch'] if p['pid'] == identity['pgid']), None)
    if leader and original and leader['starttime_ticks'] != original['starttime_ticks']:
        errors.append({'reason': 'identity_changed', 'identity': identity, 'current': current})
        return
    if current:
        try:
            os.killpg(identity['pgid'], sig)
            signals.append({'pgid': identity['pgid'], 'signal': signal.Signals(sig).name,
                            'utc': datetime.now(UTC).isoformat()})
        except ProcessLookupError:
            pass


def main():
    argv = [sys.executable, '-u', str(HERE / 'run_comparison.py'), '--run']
    launch_spec = {'argv': argv, 'cwd': str(ROOT), 'outer_timeout_s': 90,
                   'work_before_cleanup_s': 75, 'cleanup_reserve_s': 15,
                   'TERM_grace_s': 5, 'attempts': 1,
                   'launcher_sha256': hashlib.sha256((HERE / 'run_comparison.py').read_bytes()).hexdigest(),
                   'supervisor_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   'outer_policy': 'At 75s stop launcher; within final15s reap launcher and owned separate child group; hard limit90s.'}
    if sys.argv[1:] == ['--inspect']:
        save(HERE / 'bounded-launch-spec.json', launch_spec)
        print(json.dumps(launch_spec, ensure_ascii=False))
        return
    if sys.argv[1:] != ['--run']:
        raise SystemExit('Use --inspect or --run')
    assert not RECEIPTS.exists() and not OUT.exists(), 'One outer invocation only'
    RECEIPTS.mkdir()
    started = time.monotonic()
    hard_deadline = started + 90
    start_epoch = time.time()
    launch_spec.update(started_utc=datetime.now(UTC).isoformat(), hard_deadline_epoch_s=start_epoch + 90)
    save(RECEIPTS / 'invocation.json', launch_spec)
    identities = []
    signals = []
    errors = []
    timed_out = False
    process = None
    with (RECEIPTS / 'stdout.log').open('wb') as stdout, (RECEIPTS / 'stderr.log').open('wb') as stderr:
        try:
            process = subprocess.Popen(argv, cwd=ROOT, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                identity = {'pid': process.pid, 'pgid': process.pid,
                            'members_at_launch': members(process.pid)}
                identities.append(identity)
                save(RECEIPTS / 'process-identity.json', identity)
                process.wait(timeout=max(0.01, started + 75 - time.monotonic()))
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                if not identities:
                    identities.append({'pid': process.pid, 'pgid': process.pid,
                                       'members_at_launch': members(process.pid)})
                # Stop launcher first so it cannot start a new child during fallback cleanup.
                for identity in identities:
                    signal_owned(identity, signal.SIGTERM, signals, errors)
                grace = min(hard_deadline - 5, time.monotonic() + 5)
                while time.monotonic() < grace and process.poll() is None:
                    time.sleep(0.05)
                child_path = OUT / 'process-identity.json'
                if child_path.exists():
                    try:
                        identities.append(json.loads(child_path.read_text()))
                    except Exception as error:
                        errors.append({'evidence': str(child_path), 'error': str(error)})
                for identity in identities:
                    signal_owned(identity, signal.SIGTERM, signals, errors)
                grace = min(hard_deadline - 2, time.monotonic() + 5)
                while any(members(i['pgid']) for i in identities) and time.monotonic() < grace:
                    time.sleep(0.05)
                for identity in identities:
                    signal_owned(identity, signal.SIGKILL, signals, errors)
                try:
                    process.wait(timeout=max(0.01, hard_deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    errors.append({'reason': 'launcher_not_reaped_by_deadline'})
        except Exception as error:
            errors.append({'type': type(error).__name__, 'message': str(error)})
    remaining = [p for i in identities for p in members(i['pgid'])]
    result = {'state': 'OUTER_TIMEOUT' if timed_out else 'FINISHED',
              'returncode': process.returncode if process else None,
              'elapsed_s': time.monotonic() - started, 'ended_utc': datetime.now(UTC).isoformat(),
              'signals': signals, 'remaining_live': remaining, 'errors': errors,
              'launcher_reaped': bool(process and process.returncode is not None),
              'child_result_exists': (OUT / 'result.json').exists()}
    save(RECEIPTS / 'result.json', result)
    if OUT.exists() and not result['child_result_exists']:
        save(OUT / 'result.json', {'stage_id': 'workbench_module_without_runtime_db',
                                  'state': 'INFRASTRUCTURE_ERROR', 'comparison_acceptance': False,
                                  'returncode': None, 'ended_utc': result['ended_utc'],
                                  'evidence_errors': ['Launcher ended without result; see outer-run/result.json'],
                                  'reaped': not remaining, 'source_after': {'drift': ['NOT_VERIFIED']}})
    elif not OUT.exists() and not (HERE / 'not-run.json').exists():
        save(HERE / 'not-run.json', {'state': 'BLOCKED_PRECONDITION', 'outer_result': result})
    print(json.dumps(result, ensure_ascii=False))
    if result['returncode'] != 0 or timed_out or remaining or errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
