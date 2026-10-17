from pathlib import Path
import hashlib
import json
import signal
signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('R259 metadata read 120s limit')))
signal.alarm(120)
EXPECTED = [{'path': '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/plan.json', 'bytes': 114866, 'sha256': '70f51381f8f401c5456304d9eb12f019e7f903a582407ab7819447b8cd1f871b'}, {'path': '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/root-command-ledger.json', 'bytes': 76862, 'sha256': '475ebe8b47fec9539b24fd19f7431b2803e45ecf3340964c3645c18f7fda1516'}, {'path': '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/command-ledger.json', 'bytes': 33161, 'sha256': '902b7e59ee8bebd9f1453e9dc4f9b58efd1b9bdfd32a0204e15a65dcd20b7d70'}]
loaded = {}
for expected in EXPECTED:
    path = Path(expected['path'])
    raw = path.read_bytes()
    actual = {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    assert actual == expected, 'input identity changed'
    value = json.loads(raw)
    assert type(value) is dict, 'top-level dictionary required'
    assert type(value['commands']) is dict, 'commands must be a dictionary keyed by command ID'
    assert all(type(key) is str for key in value['commands']), 'string command IDs required'
    assert all(key in value['commands'] for key in ('t2_red', 't2_green')), 'exact T2 command IDs required'
    assert all(type(value['commands'][key]) is dict for key in ('t2_red', 't2_green')), 'T2 command records required'
    loaded[path.name] = value
parent = loaded['plan.json']
selected = {command_id: record for command_id, record in parent['commands'].items() if command_id in ('t2_red', 't2_green')}
assert set(selected) == {'t2_red', 't2_green'}
role_rows = {}
for name in ('root-command-ledger.json', 'command-ledger.json'):
    role_rows[name] = {command_id: loaded[name]['commands'][command_id] for command_id in ('t2_red', 't2_green')}
    assert role_rows[name]['t2_green']['used'] == 0
    assert role_rows[name]['t2_green']['remaining'] == 1
result = {'schema_version': 'r259-explicit-command-map-read-v1', 'input_pins': EXPECTED, 'command_ids_are_keys': True, 'T2_commands': selected, 'roles': role_rows, 'fixture': parent['fixture'], 'review_budget': parent['review_budget'], 'metadata_paths': parent['metadata_paths'], 'product_execution': False, 'R258_plan_frozen': False}
encoded = (json.dumps(result, ensure_ascii=False, indent=2) + chr(10)).encode('utf-8')
assert len(encoded) <= 48000, 'bounded metadata output exceeded'
OUTPUT = Path('/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round259-p6-t2-parent-planner-command-map-schema-20261017/implementation/reader-result.json')
assert OUTPUT.parent.is_dir() and not OUTPUT.exists()
with OUTPUT.open('xb') as stream:
    stream.write(encoded)
print(json.dumps({'result': {'path': str(OUTPUT), 'bytes': len(encoded), 'sha256': hashlib.sha256(encoded).hexdigest()}, 'commands': ['t2_red', 't2_green'], 'roles_checked': 2, 'product_execution': False}, ensure_ascii=False))
signal.alarm(0)
