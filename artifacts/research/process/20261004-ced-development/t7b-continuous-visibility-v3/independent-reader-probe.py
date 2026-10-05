"""SOFTWARE_ONLY real-reader review probe; no actual simulator or decoder calls."""
from pathlib import Path
import importlib.util
import hashlib
import json
import tempfile
import copy

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
HERE = ROOT / 'artifacts/research/process/20261004-ced-development/t7b-continuous-visibility-v3'

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

helpers = load(HERE / 'test_cpu.py', 'v3_probe_helpers')
runner = load(HERE / 'run_once.py', 'v3_probe_runner')
reader = load(HERE / 'verify_offline.py', 'v3_probe_reader')
base = Path(tempfile.mkdtemp(prefix='v3_reader_probe_', dir='/tmp'))
results = []
for kind in ('baseline', 'declared_120_9', 'physics_begin_step', 'control_begin_kind', 'control_end_episode', 'actuator_episode', 'retained_acquisition_failed', 'extra_acquisition_begin'):
    case = base / kind
    case.mkdir()
    source = case / 'input'
    source.mkdir()
    old = helpers.v3_attempt(source, runner)
    records = old.rows(source)
    if kind == 'declared_120_9':
        path = source / 'execution-header.json'
        header = json.loads(path.read_text())
        header.update(settle_steps=120, planned_teacher_actions=9)
        path.write_text(json.dumps(header))
        path = source / 'summary.json'
        summary = json.loads(path.read_text())
        summary['execution_header_sha256'] = hashlib.sha256((source / 'execution-header.json').read_bytes()).hexdigest()
        path.write_text(json.dumps(summary))
    elif kind in ('physics_begin_step', 'control_begin_kind', 'control_end_episode', 'actuator_episode'):
        for row in records:
            if kind == 'physics_begin_step' and row['event'] == 'OPERATION' and row['source']['kind'] == 'PHYSICS' and row['source']['phase'] == 'BEGIN':
                row['source']['physics_step'] = 999
            if kind == 'control_begin_kind' and row['event'] == 'OPERATION' and row['source']['kind'] == 'CONTROL' and row['source']['phase'] == 'BEGIN':
                row['source']['kind'] = 'COMMAND'
            if kind == 'control_end_episode' and row['event'] == 'OPERATION' and row['source']['kind'] == 'CONTROL' and row['source']['phase'] == 'END':
                row['source']['episode_id'] = 'wrong-episode'
            if kind == 'actuator_episode' and row['event'] == 'ACTUATOR':
                row['source']['episode_id'] = 'wrong-episode'
        old.write_rows(source, records)
    elif kind in ('retained_acquisition_failed', 'extra_acquisition_begin'):
        added = copy.deepcopy(records[-1])
        last = records[-1]['clock']['monotonic_after_ns']
        added['clock'].update(monotonic_before_ns=last + 1, monotonic_after_ns=last + 2)
        added.update(event='ACQUISITION_FAILED' if kind == 'retained_acquisition_failed' else 'ACQUISITION_BEGIN', physics_step=3, episode_id='fake-e', sim_time_s=0.012, action_ordinal=None, error_type='ValueError')
        records.append(added)
        old.write_rows(source, records)
    before = old.hashes(source)
    result = reader.verify_attempt(source, output_directory=case / 'output', decode=False)
    results.append({'case': kind, 'status': result['integrity_status'], 'failures': result['failures'], 'allocated': result['allocated_steps'], 'verified': result['verified_frames'], 'actions': result['original_action_begins'], 'input_unchanged': before == old.hashes(source), 'run_status': json.loads((source / 'summary.json').read_text())['run_status']})
print(json.dumps({'base': str(base), 'results': results}, indent=2))

assert results[0]["status"] == "VERIFIED" and all(row["input_unchanged"] for row in results)
qualified = [row for row in results if row["case"] not in {"baseline", "declared_120_9"}]
assert all(row["status"] == "INCOMPLETE_OR_INVALID" for row in qualified), ("malformed original source boundaries and unmatched acquisition journals must fail closed", qualified)
