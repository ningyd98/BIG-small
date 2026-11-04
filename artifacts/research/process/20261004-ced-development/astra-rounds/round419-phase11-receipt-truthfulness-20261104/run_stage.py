"""Run an R419 targeted stage with the frozen owned R413 supervisor."""
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUND = Path(__file__).resolve().parent
R413 = ROUND.parent / 'round413-full-long-validation-20261103'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main():
    stage_id, kind, *nodes = sys.argv[1:]
    assert kind in {'pure', 'native'} and nodes
    directory = ROUND / 'validation' / stage_id
    directory.mkdir(parents=True, exist_ok=False)
    baseline = json.loads((ROUND / 'preflight/baseline-source-pins.json').read_text())['files']
    allow = 'src/cloud_edge_robot_arm/final_evaluation/adapters/simulation_runtime.py'
    pins = []
    for item in baseline:
        path = ROOT / item['path']
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if item['path'] != allow:
            assert digest == item['sha256'] and len(raw) == item['bytes'], item['path']
        pins.append({**item, 'bytes': len(raw), 'sha256': digest})
    new = ROOT / 'tests/test_phase11_adapter_receipt_truthfulness.py'
    pins.append({'path': str(new.relative_to(ROOT)), 'bytes': new.stat().st_size,
                 'sha256': hashlib.sha256(new.read_bytes()).hexdigest()})
    save(directory / 'preflight/runtime-source-pins.json', {'files': pins})
    prior = json.loads((R413 / 'specs/py-module-075.json').read_text())
    old = prior['directory']
    environment = {k: v.replace(old, str(directory)) for k, v in prior['env'].items()
                   if k != 'SIMULATION_RUNTIME_DB'}
    environment['R419_EVIDENCE_DIR'] = str(directory)
    for name in prior['resource_dirs']:
        (directory / name).mkdir(parents=True, exist_ok=True)
    argv = prior['argv'][:prior['argv'].index('tests/test_phase12_2_runtime_authenticity.py::test_blocked_environment_rows_are_not_runtime_execution')]
    argv = [arg.replace(old, str(directory)) for arg in argv]
    argv = [f'--basetemp=/tmp/bigsmall-r419-{stage_id}' if arg.startswith('--basetemp=') else arg for arg in argv]
    argv.extend(nodes)
    spec = {'id': stage_id, 'directory': str(directory), 'cwd': str(ROOT), 'argv': argv,
            'env': environment, 'nodes': nodes, 'timeout_s': 600 if kind == 'native' else 120,
            'ports': [], 'created_utc': datetime.now(UTC).isoformat(),
            'source_supervisor_sha256': hashlib.sha256((R413 / 'bounded_stage.py').read_bytes()).hexdigest(),
            'round_binding': 'Only bind imported frozen supervisor ROUND to this stage for per-stage pins.'}
    spec_path = directory / 'spec.json'
    save(spec_path, spec)
    module_spec = importlib.util.spec_from_file_location('r419_owned_supervisor', R413 / 'bounded_stage.py')
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    module.ROUND = directory
    module.run(spec_path)


if __name__ == '__main__':
    main()
