"""R495 one-shot operational runner. Never reads credential values."""
from __future__ import annotations

from datetime import UTC, datetime
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import select
import signal
import shutil
import stat
import subprocess
import time

WORK = Path(__file__).parent
REPO = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
BASE = REPO / 'artifacts/research/process/20261004-ced-development/astra-rounds'
OUT = BASE / 'round495-persisted-sol-real-rgbd-retest-20261108'
PRIOR = BASE / 'round494-key-restart-shutdown-timeout-20261108'
CACHE = REPO / 'cache/research/r495-persisted-sol-real-rgbd-retest-20261108'
PLAN = json.loads((WORK / OUT.name / 'plan.json').read_text())
assert (WORK / 'r493_transition.py').read_bytes() == (BASE / 'round493-persistent-key-live-transition-20261108/execution/operational-runner.py').read_bytes()
assert (WORK / 'r493_saved_key_restart.py').read_bytes() == (BASE / 'round493-persistent-key-live-transition-20261108/execution/saved-key-restart-runner.py').read_bytes()
import r493_transition as base
from r493_saved_key_restart import existing_environment


def now():
    return datetime.now(UTC).isoformat()


def save(name, value, directory=OUT):
    with (directory / name).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def event(stage, **fields):
    print(json.dumps({'stage': stage, 'utc': now(), **fields}), flush=True)


def command(args, timeout=10):
    return subprocess.check_output(args, cwd=REPO, timeout=timeout, text=True).strip()


def pins():
    for name in ('plan.md', 'plan.json'):
        base.require((OUT / name).read_bytes() == (WORK / OUT.name / name).read_bytes(), 'plan_drift')
    for pin in PLAN['input_pins']:
        data = (REPO / pin['path']).read_bytes()
        base.require(len(data) == pin['bytes'] and hashlib.sha256(data).hexdigest() == pin['sha256'], 'source_pin_drift')
    # R496 authorizes an exact artifact/report allowlist, never a prefix broadening.
    supplement = BASE / 'round496-r495-artifact-progression-admission-20261108'
    admission = json.loads((supplement / 'admission.json').read_text())
    base.require(command(['git', 'rev-parse', 'HEAD']) == admission['head'], 'head_changed')
    changed = command(['git', 'diff', '--name-only', PLAN['baseline_head'], 'HEAD']).splitlines()
    base.require(changed == admission['allowed_changed_paths'], 'artifact_progression_drift')
    for pin in admission['additional_input_pins']:
        data = (REPO / pin['path']).read_bytes()
        base.require(len(data) == pin['bytes'] and hashlib.sha256(data).hexdigest() == pin['sha256'], 'additional_pin_drift')
    return {'plan_input_pins_verified': len(PLAN['input_pins']), 'supplemental_pins_verified': len(admission['additional_input_pins']), 'head': admission['head']}


def graphics_metadata():
    modules = [REPO / '.venv/lib/python3.12/site-packages' / p for p in ('mujoco/gl_context.py', 'mujoco/egl/__init__.py', 'OpenGL/EGL/__init__.py')]
    base.require(all(p.is_file() for p in modules), 'egl_module_metadata_missing')
    libraries = command(['ldconfig', '-p'])
    selected = [line.strip() for line in libraries.splitlines() if any(name in line for name in ('libEGL.so.1 ', 'libEGL_nvidia.so.0 ', 'libOpenGL.so.0 '))]
    base.require(all(any(name in line for line in selected) for name in ('libEGL.so.1 ', 'libEGL_nvidia.so.0 ', 'libOpenGL.so.0 ')), 'graphics_library_metadata_missing')
    base.require(all(Path(line.rsplit('=>', 1)[1].strip()).is_file() for line in selected), 'graphics_library_file_missing')
    return {'module_files': [str(p.relative_to(REPO)) for p in modules], 'libraries': selected, 'render_or_import_probe': False}


def resources():
    gpu = command(['nvidia-smi', '--query-gpu=index,memory.free', '--format=csv,noheader,nounits'])
    rows = [[int(v.strip()) for v in line.split(',')] for line in gpu.splitlines()]
    free = next((row[1] for row in rows if row[0] == 0), -1)
    compute = command(['nvidia-smi', '--query-compute-apps=pid,process_name,used_memory', '--format=csv,noheader,nounits'])
    service_text = command(['systemctl', '--user', 'show', 'qwen38-flash-strata.service', '--property=LoadState,ActiveState,SubState,MainPID,ControlPID'])
    service = dict(line.split('=', 1) for line in service_text.splitlines())
    disk = shutil.disk_usage(REPO).free
    ok = free >= 2048 and not compute and service == {'LoadState': 'loaded', 'ActiveState': 'inactive', 'SubState': 'dead', 'MainPID': '0', 'ControlPID': '0'} and disk >= 2147483648
    return {'admitted': ok, 'gpu0_free_mib': free, 'compute_app_rows': compute.splitlines(), 'qwen_service': service, 'disk_free_bytes': disk, 'captured_utc': now()}


def check_profiles(state, previous):
    base.require(base.configuration(state) == base.configuration(previous), 'saved_configuration_changed')
    presence = lambda s: {p['profile_id']: (p['secret_present'], p['secret_store_kind']) for p in s['profiles']}
    base.require(presence(state) == presence(previous), 'saved_secret_presence_changed')
    active = next(p for p in state['profiles'] if p['profile_id'] == base.ACTIVE)
    required = {'active': True, 'model_name': 'gpt-6.1-sol', 'base_url': 'https://api.openai.com', 'chat_completions_path': '/v1/chat/completions', 'max_tokens': 4096, 'timeout_seconds': 30.0, 'config_version': 2, 'secret_present': True, 'secret_store_kind': 'ENCRYPTED_FILE'}
    base.require(all(active.get(k) == v for k, v in required.items()), 'active_profile_contract_mismatch')


def stop_once(old):
    descriptor = os.pidfd_open(old['pid'])
    try:
        base.identity(old['pid'], old['starttime_ticks'])
        signal.pidfd_send_signal(descriptor, signal.SIGTERM)
        event('one_sigterm_sent', pid=old['pid'])
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if select.select([descriptor], [], [], min(30, deadline - time.monotonic()))[0]:
                event('old_backend_exited')
                return
            event('waiting_for_graceful_exit', remaining_s=round(max(0, deadline - time.monotonic()), 1))
        raise base.Stop('backend_did_not_exit_within_90_seconds')
    finally:
        os.close(descriptor)


class Deadline(TimeoutError):
    pass


def deadline_handler(_signal, _frame):
    raise Deadline()


def post_once():
    marker = {'round': 'R495', 'request': PLAN['request'], 'created_utc': now(), 'max_api_posts': 1, 'max_provider_inferences_source_ceiling': 1}
    save('attempted.json', marker, CACHE)
    save('execution-start.json', marker)
    payload = json.dumps(PLAN['request'], separators=(',', ':')).encode()
    result = {'started_utc': now(), 'request_sha256': hashlib.sha256(payload).hexdigest(), 'post_attempts': 1, 'retry': 0, 'fallback': 0, 'http_status': None, 'complete': False, 'response_bytes': 0}
    chunks = bytearray()
    started = time.monotonic()
    connection = http.client.HTTPConnection('127.0.0.1', 8000, timeout=90)
    signal.signal(signal.SIGALRM, deadline_handler)
    signal.setitimer(signal.ITIMER_REAL, 90)
    try:
        connection.request('POST', '/api/v1/model-control/planner/dry-run', payload, {'Content-Type': 'application/json', 'Connection': 'close'})
        response = connection.getresponse()
        result['http_status'] = response.status
        while len(chunks) <= 4194304:
            chunk = response.read1(min(65536, 4194305 - len(chunks)))
            if not chunk:
                base.require(response.length in (None, 0), 'incomplete_response_body')
                result['complete'] = True
                break
            chunks.extend(chunk)
        if len(chunks) > 4194304:
            result['classification'] = 'RESPONSE_LIMIT'
    except Exception as error:
        result['error_class'] = type(error).__name__
        result['classification'] = 'UNKNOWN'
        if isinstance(error, base.Stop):
            result['safe_code'] = str(error)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        connection.close()
    result.update({'ended_utc': now(), 'elapsed_seconds': round(time.monotonic() - started, 6), 'response_bytes': len(chunks), 'response_sha256': hashlib.sha256(chunks).hexdigest(), 'response_local_path': str(CACHE / 'response.body')})
    with (CACHE / 'response.body').open('xb') as stream:
        stream.write(chunks)
    save('http-receipt.json', result, CACHE)
    save('http-receipt.json', result)
    return result


def execute():
    os.umask(0o077)
    checked = pins()
    graphics = graphics_metadata()
    base.require(command(['git', 'check-ignore', '--', str(CACHE)]) == str(CACHE), 'private_cache_not_ignored')
    CACHE.mkdir(mode=0o700)
    base.require(stat.S_IMODE(CACHE.stat().st_mode) == 0o700, 'private_cache_mode')
    (OUT / 'operational-runner.py').write_bytes(Path(__file__).read_bytes())
    # This detached process is the durable flock owner; UNKNOWN retains it.
    lock_path = REPO / 'cache/research/.r468-r469-gpu.lock'
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    held = False
    unknown = False
    new = None
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            save('result.json', {'classification': 'WAITING_RESOURCE', 'reason': 'gpu_lock_busy', 'post_attempts': 0, 'backend_untouched': True})
            return
        held = True
        proc_stat = (Path('/proc') / str(os.getpid()) / 'stat').read_text().rsplit(')', 1)[1].split()
        owner = {'pid': os.getpid(), 'starttime_ticks': int(proc_stat[19]), 'lock_path': str(lock_path), 'acquired_utc': now(), 'unknown_completion_policy': 'retain_process_and_flock_until_new_Astra'}
        save('lock-owner.json', owner)
        gate = resources()
        save('admission.json', {**checked, 'graphics': graphics, 'resource_gate': gate, 'owner': owner})
        if not gate['admitted']:
            save('result.json', {'classification': 'WAITING_RESOURCE', 'reason': 'resource_gate', 'post_attempts': 0, 'backend_untouched': True})
            return
        original = json.loads((PRIOR / 'launched-process.json').read_text())
        previous = json.loads((PRIOR / 'after-recovery.json').read_text())
        old = base.identity(original['backend']['pid'], original['backend']['starttime_ticks'])
        frontend = base.identity(159968, 8153269, True)
        base.require_listener(old['pid'], 8000)
        base.require_listener(frontend['pid'], 5173)
        before = base.snapshot()
        check_profiles(before, previous)
        save('before-restart.json', before)
        environment = existing_environment(original['contract'])
        environment.update({'BIGSMALL_VLM_ALLOW_PAID_CALL': 'true', 'MUJOCO_GL': 'egl'})
        base.require('PYOPENGL_PLATFORM' not in environment and 'DISPLAY' not in environment, 'unexpected_display_selection')
        contract = json.loads(json.dumps(original['contract']))
        contract['environment'].update({'BIGSMALL_VLM_ALLOW_PAID_CALL': 'true', 'MUJOCO_GL': 'egl'})
        contract.update({'paid_calls': True, 'pyopengl_platform': None})
        save('prepared-launch.json', contract)
        out_fd = os.open(CACHE / 'backend-stdout.log', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        err_fd = os.open(CACHE / 'backend-stderr.log', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            stop_once(old)
            base.require(not base.listeners(8000), 'unexpected_listener_after_stop')
            child = subprocess.Popen(contract['argv'], cwd=REPO, env=environment, start_new_session=True, stdin=subprocess.DEVNULL, stdout=out_fd, stderr=err_fd)
            new = base.identity(child.pid)
            save('launched-process.json', {'backend': new, 'frontend': frontend, 'contract': contract})
        finally:
            os.close(out_fd)
            os.close(err_fd)
        healthy = False
        ready_deadline = time.monotonic() + 30
        for _ in range(10):
            if time.monotonic() >= ready_deadline or child.poll() is not None:
                break
            try:
                healthy = base.get_json('/health', timeout=2).get('status') == 'ok'
            except (OSError, ValueError):
                pass
            if healthy:
                break
            time.sleep(min(1, max(0, ready_deadline - time.monotonic())))
        base.require(healthy, 'new_backend_health_failed')
        base.require_listener(new['pid'], 8000)
        after = base.snapshot(known_healthy=True)
        check_profiles(after, previous)
        base.identity(159968, 8153269, True)
        base.require_listener(159968, 5173)
        save('after-restart.json', after)
        again = resources()
        save('pre-request-resources.json', again)
        base.require(again['admitted'], 'resource_gate_changed_before_post')
        base.require(os.fstat(lock_fd).st_ino == lock_path.stat().st_ino, 'lock_inode_changed')
        pins()
        event('one_rgbd_request_starting', backend_pid=new['pid'])
        unknown = True
        receipt = post_once()
        unknown = not receipt['complete']
        if unknown:
            health = {'terminal_request_evidence': False, 'replay_forbidden': True}
            try:
                base.identity(new['pid'], new['starttime_ticks'])
                base.require_listener(new['pid'], 8000)
                health['health'] = base.get_json('/health', timeout=5)
            except Exception as error:
                health['health_error_class'] = type(error).__name__
            save('unknown-completion.json', {**health, 'owner': owner})
            event('unknown_completion_lock_retained')
        else:
            final_state = base.snapshot()
            check_profiles(final_state, previous)
            save('final-metadata.json', final_state)
            event('one_rgbd_response_completed', http_status=receipt['http_status'], response_bytes=receipt['response_bytes'], elapsed_seconds=receipt['elapsed_seconds'])
    except Exception as error:
        save('operational-failure.json', {'error_class': type(error).__name__, 'safe_code': str(error) if isinstance(error, base.Stop) else 'operational_failure', 'new_backend': new, 'post_reserved': (CACHE / 'attempted.json').exists(), 'completion_unknown': unknown, 'automatic_retry': False})
        event('operational_failure', error_class=type(error).__name__, completion_unknown=unknown)
    finally:
        if unknown and held:
            # Keep this detached owner alive; never interpret client timeout as cancellation.
            while True:
                time.sleep(30)
        if held:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            save('lock-released.json', {'released_utc': now(), 'post_reserved': (CACHE / 'attempted.json').exists(), 'known_complete_or_not_sent': True})
        os.close(lock_fd)


if __name__ == '__main__':
    execute()
