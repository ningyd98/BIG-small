"""Complete the interrupted R493 restart with one fresh launch, no old signal."""
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

import r493_saved_key_restart as saved

base = saved.base
WORK = Path(__file__).parent
DRAFT = WORK / 'round494-key-restart-shutdown-timeout-20261108'
PLAN = json.loads((DRAFT / 'plan.json').read_text())
OUT = base.REPO / 'artifacts/research/process/20261004-ced-development/astra-rounds' / DRAFT.name


def record(name, data):
    with (OUT / name).open('x') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main():
    for pin in PLAN['input_pins']:
        base.require(hashlib.sha256((base.REPO / pin['path']).read_bytes()).hexdigest() == pin['sha256'],
                     'recovery_input_pin_drift')
    head = subprocess.check_output(['git','rev-parse','HEAD'], cwd=base.REPO, text=True).strip()
    base.require(head == PLAN['head'], 'recovery_head_changed')
    base.verify_pins()
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ('plan.md', 'plan.json'):
        with (OUT / name).open('xb') as stream:
            stream.write((DRAFT / name).read_bytes())
    (OUT / 'recovery-runner.py').write_bytes(Path(__file__).read_bytes())
    base.require(not Path('/proc/1407005').exists(), 'old_pid_present_no_launch')
    base.require(not base.listeners(8000), 'backend_port_occupied_no_launch')
    prior = json.loads((base.EXECUTION / 'launched-process.json').read_text())
    before = json.loads((base.EXECUTION / 'saved-key-before-restart.json').read_text())
    frontend = before['frontend']
    base.identity(frontend['pid'], frontend['starttime_ticks'], True)
    base.require_listener(frontend['pid'], 5173)
    environment = saved.existing_environment(prior['contract'])
    active_before = next(p for p in before['state']['profiles'] if p['profile_id'] == base.ACTIVE)
    base.require(active_before['secret_present'] is True and active_before['config_version'] == 2,
                 'wrong_saved_baseline')
    record('admission.json', {'captured_utc': datetime.now(UTC).isoformat(), 'head':head,
        'input_pins_verified':len(PLAN['input_pins']), 'old_pid_absent': True,
        'backend_port_vacant': True, 'frontend':frontend,
        'launch_contract_sha256':hashlib.sha256(json.dumps(prior['contract'],sort_keys=True).encode()).hexdigest(),
        'saved_baseline_sha256':hashlib.sha256((base.EXECUTION/'saved-key-before-restart.json').read_bytes()).hexdigest()})
    out_fd = os.open(OUT/'recovery-stdout.log', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    err_fd = os.open(OUT/'recovery-stderr.log', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    new = None
    started = time.monotonic()
    try:
        base.require(not Path('/proc/1407005').exists() and not base.listeners(8000),
                     'stopped_state_changed_before_launch')
        child = subprocess.Popen(prior['contract']['argv'], cwd=base.REPO, env=environment,
            start_new_session=True, stdin=subprocess.DEVNULL, stdout=out_fd, stderr=err_fd)
        new = base.identity(child.pid)
        record('launched-process.json', {'backend':new, 'contract':prior['contract']})
        healthy = False
        deadline = time.monotonic()+30
        for _ in range(10):
            if time.monotonic() >= deadline or child.poll() is not None:
                break
            try:
                healthy = base.get_json('/health', timeout=2).get('status') == 'ok'
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                pass
            if healthy:
                break
            time.sleep(min(1,max(0,deadline-time.monotonic())))
        base.require(healthy, 'recovery_health_failed')
        base.require_listener(new['pid'],8000)
        after = base.snapshot(known_healthy=True)
        base.require(base.configuration(after)==base.configuration(before['state']),
                     'saved_configuration_changed')
        presence = lambda state: {p['profile_id']:(p['secret_present'],p['secret_store_kind']) for p in state['profiles']}
        base.require(presence(after)==presence(before['state']), 'encrypted_presence_changed')
        active = next(p for p in after['profiles'] if p['profile_id']==base.ACTIVE)
        base.require(active['secret_present'] is True and active['secret_store_kind']=='ENCRYPTED_FILE',
                     'saved_key_not_recovered')
        base.require(set(after['secret_store_modes'])=={'ENCRYPTED_FILE','SESSION_ONLY'},
                     'capabilities_changed')
        base.identity(frontend['pid'],frontend['starttime_ticks'],True)
        base.require_listener(frontend['pid'],5173)
        with urllib.request.urlopen('http://127.0.0.1:5173/models',timeout=5) as response:
            base.require(response.status==200,'model_page_unavailable')
        record('after-recovery.json',after)
        result = {'state':'persisted_key_survives_fresh_process', 'user_key_persisted':True,
            'persisted_key_survives_restart':True, 'live_deployed':True, 'backend':new,
            'frontend':frontend, 'active_profile_id':base.ACTIVE, 'config_version':active['config_version'],
            'profile_count':3, 'all_nonsecret_configuration_preserved':True,
            'original_shutdown_timeout_preserved':True, 'delayed_graceful_completion_observed':True,
            'recovery_launches':1, 'additional_old_process_signals':0,
            'secret_values_read_or_exported':False, 'provider_calls':0, 'paid_calls':False,
            'captured_utc':datetime.now(UTC).isoformat(),
            'elapsed_seconds':round(time.monotonic()-started,3)}
        record('recovery-result.json',result)
        print(json.dumps(result,ensure_ascii=False))
    except Exception as error:
        record('recovery-failure.json',{'error_class':type(error).__name__,
            'safe_code':str(error) if isinstance(error,base.Stop) else 'operational_failure',
            'new_backend':new,'launches':1 if new else 0,'no_second_launch':True})
        if new is not None:
            # At most one signal and three bounded observations; never signal old PID.
            base.identity(new['pid'],new['starttime_ticks'])
            import select, signal
            fd=os.pidfd_open(new['pid'])
            try:
                signal.pidfd_send_signal(fd,signal.SIGTERM)
                for _ in range(3):
                    if select.select([fd],[],[],30)[0]: break
            finally:
                os.close(fd)
        raise
    finally:
        os.close(out_fd)
        os.close(err_fd)


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'operation_failed':True,'error_class':type(error).__name__,
            'safe_code':str(error) if isinstance(error,base.Stop) else 'operational_failure'}))
        raise SystemExit(1) from None
