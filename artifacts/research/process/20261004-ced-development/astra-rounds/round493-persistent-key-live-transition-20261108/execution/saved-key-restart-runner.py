"""R493 step 6: user-acknowledged key save, one ordinary restart, metadata only."""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import time
import urllib.error

WORK = Path(__file__).parent
REPO = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUND = REPO / 'artifacts/research/process/20261004-ced-development/astra-rounds/round493-persistent-key-live-transition-20261108'
FROZEN_RUNNER = ROUND / 'execution/operational-runner.py'
assert (WORK / 'r493_transition.py').read_bytes() == FROZEN_RUNNER.read_bytes()
import r493_transition as base


def existing_environment(contract):
    account_home = Path(pwd.getpwuid(os.geteuid()).pw_dir)
    base.require(str(account_home) == contract['environment']['HOME'], 'account_home_changed')
    base.require(os.environ.get('HOME') == str(account_home), 'executing_home_changed')
    xdg = os.environ.get('XDG_DATA_HOME', '')
    base.require(xdg == (contract['xdg_data_home'] or ''), 'executing_xdg_changed')
    selected = Path(xdg) if xdg else account_home / '.local/share'
    base.require(str(selected) == contract['selected_data_base'], 'data_base_changed')
    namespace = hashlib.sha256(os.path.abspath(os.fspath(base.DB)).encode()).hexdigest()
    base.require(namespace == contract['namespace'], 'database_namespace_changed')
    directory = selected / 'BIGsmall/model-control-secrets' / namespace
    current = Path('/')
    for part in directory.parts[1:]:
        current /= part
        info = current.lstat()  # Directory metadata only; never read a vault file.
        base.require(stat.S_ISDIR(info.st_mode), 'unsafe_directory_component')
        base.require(info.st_uid in {0, os.geteuid()}, 'directory_owner_changed')
        base.require(not stat.S_IMODE(info.st_mode) & 0o022, 'unsafe_directory_permissions')
    base.require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700,
                 'private_vault_directory_required')
    ordinary = ('HOME', 'PATH', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TZ')
    environment = {name: os.environ[name] for name in ordinary if name in os.environ}
    environment.update({name: value for name, value in contract['environment'].items() if name != 'HOME'})
    if xdg:
        environment['XDG_DATA_HOME'] = xdg
    base.require(environment['BIGSMALL_VLM_ALLOW_PAID_CALL'] == 'false', 'paid_gate_changed')
    base.require('MODEL_CONTROL_SECRET_DIR' not in environment, 'vault_override_not_allowed')
    return environment


def main():
    base.verify_pins()
    prior = json.loads((base.EXECUTION / 'launched-process.json').read_text())
    original = json.loads((base.EXECUTION / 'transition-result.json').read_text())
    base.require(original['state'] == 'ready_for_one_time_key_entry', 'wrong_prior_stage')
    backend = base.identity(prior['backend']['pid'], prior['backend']['starttime_ticks'])
    frontend = base.identity(original['frontend']['pid'], original['frontend']['starttime_ticks'], True)
    base.require_listener(backend['pid'], 8000)
    base.require_listener(frontend['pid'], 5173)
    before = base.snapshot()
    active = next(p for p in before['profiles'] if p['profile_id'] == base.ACTIVE)
    base.require(active['secret_present'] is True and active['secret_store_kind'] == 'ENCRYPTED_FILE',
                 'saved_active_key_not_present_in_encrypted_store')
    base.require(active['active'] is True, 'active_selection_changed')
    environment = existing_environment(prior['contract'])
    base.save('saved-key-before-restart.json', {
        'user_acknowledgement': '已经保存', 'captured_utc': datetime.now(UTC).isoformat(),
        'backend': backend, 'frontend': frontend, 'state': before,
        'source_plan': 'R493 step 6', 'secret_values_read_or_exported': False,
    })
    (base.EXECUTION / 'saved-key-restart-runner.py').write_bytes(Path(__file__).read_bytes())
    out_fd = os.open(base.EXECUTION / 'saved-key-restart-stdout.log',
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    err_fd = os.open(base.EXECUTION / 'saved-key-restart-stderr.log',
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    new = None
    started = time.monotonic()
    try:
        base.stop_process(backend)
        base.require(not base.listeners(8000), 'unexpected_listener_after_stop')
        child = subprocess.Popen(prior['contract']['argv'], cwd=REPO, env=environment,
            start_new_session=True, stdin=subprocess.DEVNULL, stdout=out_fd, stderr=err_fd)
        new = base.identity(child.pid)
        base.save('saved-key-restart-launched.json', {'backend': new, 'contract': prior['contract']})
        deadline = time.monotonic() + 30
        healthy = False
        for _ in range(10):
            if time.monotonic() >= deadline or child.poll() is not None:
                break
            try:
                healthy = base.get_json('/health', timeout=2).get('status') == 'ok'
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                pass
            if healthy:
                break
            time.sleep(min(1, max(0, deadline-time.monotonic())))
        base.require(healthy, 'restarted_backend_health_failed')
        base.require_listener(new['pid'], 8000)
        after = base.snapshot(known_healthy=True)
        base.require(base.configuration(after) == base.configuration(before),
                     'configuration_changed_across_restart')
        presence = lambda state: {p['profile_id']: (p['secret_present'], p['secret_store_kind']) for p in state['profiles']}
        base.require(presence(after) == presence(before), 'secret_metadata_changed_across_restart')
        recovered = next(p for p in after['profiles'] if p['profile_id'] == base.ACTIVE)
        base.require(recovered['secret_present'] is True and recovered['secret_store_kind'] == 'ENCRYPTED_FILE',
                     'encrypted_key_recovery_failed')
        base.identity(frontend['pid'], frontend['starttime_ticks'], True)
        base.require_listener(frontend['pid'], 5173)
        base.save('saved-key-after-restart.json', after)
        receipt = {
            'state': 'persisted_key_survives_restart', 'user_key_persisted': True,
            'persisted_key_survives_restart': True, 'live_deployed': True,
            'old_backend': backend, 'new_backend': new, 'frontend': frontend,
            'active_profile_id': base.ACTIVE, 'profile_count': len(after['profiles']),
            'all_nonsecret_config_preserved': True, 'secret_values_read_or_exported': False,
            'provider_called': False, 'paid_calls': False, 'ordinary_restarts': 1,
            'captured_utc': datetime.now(UTC).isoformat(),
            'elapsed_seconds': round(time.monotonic()-started, 3),
        }
        base.save('saved-key-restart-result.json', receipt)
        print(json.dumps(receipt, ensure_ascii=False))
    except Exception as error:
        stopped = False
        if new is not None:
            try:
                base.stop_process(new)
                stopped = True
            except Exception:
                pass
        base.save('saved-key-restart-failure.json', {
            'error_class': type(error).__name__,
            'safe_code': str(error) if isinstance(error, base.Stop) else 'operational_failure',
            'new_backend_stopped': stopped,
        })
        raise
    finally:
        os.close(out_fd)
        os.close(err_fd)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'operation_failed': True, 'error_class': type(error).__name__,
            'safe_code': str(error) if isinstance(error, base.Stop) else 'operational_failure'}))
        raise SystemExit(1) from None
