"""Prepare an unused successor with only the R414 database-scope delta."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
R413 = HERE.parent / 'round413-full-long-validation-20261103'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main():
    assert sha(HERE / 'plan.json') == '94b0e908b4269f62307ddf4f14378f480cfece2ecfabf1cb0f4bc2e7a54be852'
    plan = json.loads((HERE / 'plan.json').read_text())
    original = json.loads((R413 / 'specs/py-module-073.json').read_text())
    successor = deepcopy(original)
    old = original['directory']
    new = plan['successor']['directory']
    successor['id'] = plan['successor']['id']
    successor['directory'] = new
    successor['argv'] = [arg.replace(old, new) for arg in original['argv']]
    successor['argv'] = ['--basetemp=/tmp/bigsmall-r414-py-module-073' if arg.startswith('--basetemp=') else arg for arg in successor['argv']]
    successor['env'] = {key: value.replace(old, new) for key, value in original['env'].items()}
    removed = successor['env'].pop('SIMULATION_RUNTIME_DB')
    normalized = deepcopy(successor)
    normalized['id'] = original['id']
    normalized['directory'] = old
    normalized['argv'] = [arg.replace(new, old) for arg in successor['argv']]
    normalized['argv'] = [next(a for a in original['argv'] if a.startswith('--basetemp=')) if a.startswith('--basetemp=') else a for a in normalized['argv']]
    normalized['env'] = {key: value.replace(new, old) for key, value in successor['env'].items()}
    expected = deepcopy(original)
    expected['env'].pop('SIMULATION_RUNTIME_DB')
    assert normalized == expected
    assert successor['nodes'] == plan['original_nodes_in_order']
    assert successor['timeout_s'] == 1800 and successor['tail_timeout_s'] == 600
    assert not Path('/tmp/bigsmall-r414-py-module-073').exists()
    directory = Path(new)
    directory.mkdir(parents=True, exist_ok=False)
    for name in successor['resource_dirs']:
        (directory / name).mkdir(parents=True, exist_ok=False)
    save(HERE / 'specs/py-module-073-r414-db-scope.json', successor)
    save(HERE / 'preflight/environment-delta.json', {
        'original_spec_sha256': sha(R413 / 'specs/py-module-073.json'),
        'successor_spec_sha256': sha(HERE / 'specs/py-module-073-r414-db-scope.json'),
        'normalized_equality_except_removed_env': True,
        'semantic_removed_keys': ['SIMULATION_RUNTIME_DB'], 'removed_value_in_original_scope': removed.replace(new, old),
        'necessary_output_relocations': {'from': old, 'to': new,
                                         'old_basetemp': '/tmp/bigsmall-r413-py-module-073',
                                         'new_basetemp': '/tmp/bigsmall-r414-py-module-073'},
        'nodes_in_original_order': successor['nodes'], 'assertions_modified': False,
        'software_tests_started': False, 'original_module_quota_s': 1800,
        'original_stage_guard_sha256': sha(R413 / 'implementation/py-module-073/result.json')})
    print(json.dumps({'prepared': successor['id'], 'semantic_delta': 'remove SIMULATION_RUNTIME_DB only'}))


if __name__ == '__main__':
    main()
