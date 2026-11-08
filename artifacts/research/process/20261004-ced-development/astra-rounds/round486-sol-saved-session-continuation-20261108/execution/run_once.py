"""One existing-session API observation under the frozen R486 plan; no secrets."""

import csv
import fcntl
import hashlib
import io
import json
import os
import shutil
import signal
import subprocess
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUND = Path(__file__).resolve().parents[1]
HERE = ROUND / 'execution'
RAW = ROOT / 'cache/research/r486-sol-saved-session-20261108'
BASE = 'http://127.0.0.1:8000'
PROFILE = 'profile-4f24f5330ad644ad'
PLAN = json.loads((ROUND / 'plan.json').read_bytes())
FIELDS = tuple(json.loads((ROUND / 'intake/continuation-context.json').read_bytes())['profiles'][0])


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    path = HERE / name
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def metadata(path, *, post=False):
    request = urllib.request.Request(BASE + path, method='POST' if post else 'GET')
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def profiles():
    return [{key: row.get(key) for key in FIELDS}
            for row in metadata('/api/v1/model-control/profiles')]


def assert_profile(rows):
    expected = next(row for row in json.loads(
        (ROUND / 'intake/continuation-context.json').read_bytes())['profiles']
        if row['profile_id'] == PROFILE)
    actual = next(row for row in rows if row['profile_id'] == PROFILE)
    assert {k: v for k, v in actual.items() if k != 'active'} == {
        k: v for k, v in expected.items() if k != 'active'}
    assert actual['enabled'] and actual['secret_present']
    assert actual['max_tokens'] == 4096 and actual['timeout_seconds'] == 30
    assert actual['model_name'] == 'gpt-6.1-sol'
    assert actual['base_url'] == 'https://api.openai.com'
    assert actual['chat_completions_path'] == '/v1/chat/completions'
    return actual


def main():
    os.umask(0o077)
    assert not RAW.exists() and not (HERE / 'attempted.json').exists()
    old = ROUND.parent / 'round469-current-sol-nominal-runtime-20261108'
    old_plan = json.loads((old / 'plan.json').read_bytes())
    rows = PLAN['inputs'] + old_plan['inputs'] + json.loads((old / 'source-pins.json').read_bytes())
    for row in rows:
        path = ROOT / row['path']
        assert path.is_file() and sha(path) == row['sha256']
        assert path.stat().st_size == row['bytes']
    assert sha(ROUND / 'input-pins.json') == PLAN['input_manifest_sha256']
    assert sha(ROUND / 'static-issue-evidence.json') == PLAN['static_evidence_sha256']
    save('attempted.json', {'utc': datetime.now(UTC).isoformat(), 'pin_count': len(rows),
        'plan_sha256': sha(ROUND / 'plan.json'), 'client_sha256': sha(Path(__file__)),
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'scoped_dirty': subprocess.check_output(['git', 'status', '--short', '-uno', '--',
            'src', 'tests', 'configs', 'assets'], cwd=ROOT, text=True)})
    before = profiles()
    selected = assert_profile(before)
    runtime = metadata('/api/v1/model-control/runtime')
    save('metadata-before.json', {'profiles': before, 'runtime': runtime})
    lock = (ROOT / PLAN['resource_gate']['lock']).open('a')
    try:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            save('integration-result.json', {'status': 'WAITING_RESOURCE', 'dry_run_requests': 0})
            print(json.dumps({'status': 'WAITING_RESOURCE', 'dry_run_requests': 0}), flush=True)
            return
        commands = [
            ['/usr/bin/nvidia-smi', '--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu', '--format=csv,noheader,nounits'],
            ['/usr/bin/nvidia-smi', '--query-compute-apps=pid,process_name,used_memory', '--format=csv,noheader,nounits'],
            ['/usr/bin/systemctl', '--user', 'show', 'qwen38-flash-strata.service', '--no-pager', '--property=Id,LoadState,ActiveState,SubState,MainPID,ControlPID,ControlGroup,NRestarts'],
        ]
        records = []
        for command in commands:
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                    timeout=8, check=False)
            records.append({'command': command, 'returncode': result.returncode,
                            'stdout': result.stdout, 'stderr': result.stderr})
        disk_free = shutil.disk_usage(ROOT).free
        save('admission.json', {'commands': records, 'disk_free_bytes': disk_free})
        assert all(row['returncode'] == 0 for row in records)
        gpu = next(row for row in csv.reader(io.StringIO(records[0]['stdout'])) if row[0].strip() == '0')
        unit = dict(line.split('=', 1) for line in records[2]['stdout'].splitlines() if '=' in line)
        admitted = (int(gpu[4].strip()) >= 2048 and not records[1]['stdout'].strip()
            and all(unit.get(key) == value for key, value in {
                'LoadState': 'loaded', 'ActiveState': 'inactive', 'SubState': 'dead',
                'MainPID': '0', 'ControlPID': '0'}.items()) and disk_free >= 2147483648)
        if not admitted:
            save('integration-result.json', {'status': 'RESOURCE_ADMISSION_BLOCKED', 'dry_run_requests': 0})
            print(json.dumps({'status': 'RESOURCE_ADMISSION_BLOCKED', 'dry_run_requests': 0}), flush=True)
            return
        activated = metadata('/api/v1/model-control/profiles/' + PROFILE + '/activate', post=True)
        assert activated['active_profile_id'] == PROFILE
        active_runtime = metadata('/api/v1/model-control/runtime')
        after = profiles()
        selected = assert_profile(after)
        assert selected['active'] and active_runtime['active_profile_id'] == PROFILE
        save('metadata-active.json', {'activation': activated, 'runtime': active_runtime, 'profiles': after})
        request_body = PLAN['request']
        save('execution-start.json', {'utc': datetime.now(UTC).isoformat(),
            'plan_sha256': sha(ROUND / 'plan.json'), 'pins_sha256': sha(ROUND / 'input-pins.json'),
            'selected_profile': selected, 'max_paid_calls': 1, 'max_completion_tokens': 4096,
            'request': request_body})
        RAW.mkdir(parents=True)
        request = urllib.request.Request(BASE + '/api/v1/model-control/planner/dry-run',
            data=json.dumps(request_body).encode(), method='POST', headers={'Content-Type': 'application/json'})
        started = time.monotonic()
        raw = b''
        try:
            try:
                response = urllib.request.urlopen(request, timeout=90)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                status = response.status
                raw = response.read(4194305)
                if len(raw) > 4194304:
                    raise ValueError('response ceiling exceeded; completion unknown')
        except BaseException as error:
            (RAW / 'response.partial.bin').write_bytes(raw)
            save('integration-result.json', {'status': 'SERVER_REQUEST_COMPLETION_UNKNOWN',
                'error_type': type(error).__name__, 'dry_run_requests': 1, 'lock_retained': True})
            print(json.dumps({'status': 'SERVER_REQUEST_COMPLETION_UNKNOWN', 'lock_retained': True}), flush=True)
            while True:
                signal.pause()
        (RAW / 'response.json').write_bytes(raw)
        data = json.loads(raw)
        reason = str(data.get('reason', ''))
        observation = data.get('observation', {})
        reproduced = (data.get('parse_result') == 'REQUEST_MORE_OBSERVATION'
            and 'top grasp requires a trusted MuJoCo upright-box calibration profile' in reason
            and bool(data.get('raw_planner_output')) and observation.get('source') == 'mujoco_camera'
            and observation.get('width') == 320 and observation.get('height') == 240)
        classification = 'LIVE_SAFE_REJECTION_REPRODUCED' if reproduced else (
            'PAID_GATE_BLOCKED' if 'BIGSMALL_VLM_ALLOW_PAID_CALL' in reason else 'LIVE_RESULT_RECORDED')
        result = {'status': classification, 'http_status': status, 'dry_run_requests': 1,
            'elapsed_seconds': round(time.monotonic() - started, 3),
            'max_paid_calls': 1, 'actual_paid_calls': None, 'tokens': None, 'cost': None,
            'parse_result': data.get('parse_result'), 'reason': reason,
            'scope': data.get('evaluation_scope'), 'dispatch': data.get('dispatch'),
            'hardware_execution': data.get('hardware_execution'),
            'final_contract_present': data.get('final_contract') is not None,
            'observation': observation, 'raw_planner_output_present': bool(data.get('raw_planner_output')),
            'raw_response_sha256': hashlib.sha256(raw).hexdigest(), 'raw_response_bytes': len(raw),
            'response_complete': True, 'live_fixed_generation_validated': False,
            'r469_nominal': 'NOT_RUN'}
        save('integration-result.json', result)
        print(json.dumps({key: result[key] for key in ('status', 'http_status', 'elapsed_seconds',
            'parse_result', 'reason', 'scope', 'dispatch', 'final_contract_present')}), flush=True)
    finally:
        lock.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        save('client-stopped.json', {'error_type': type(error).__name__, 'api_dry_run_retried': False})
        print(json.dumps({'status': 'CLIENT_STOPPED', 'error_type': type(error).__name__}), flush=True)
        raise SystemExit(2) from None
