"""Single R141 append-only source proof; never executes product or test code."""

import ast
import hashlib
import io
import json
from pathlib import Path
import tokenize

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUNDS = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds'
BASE = ROUNDS / 'round141-p6-positive-publication-control-20261012'
RECOVERY = ROUNDS / 'round143-p6-positive-control-schema-recovery-20261012'
HISTORY = ROUNDS / 'round139-p6-test-capture-lint-repair-20261011'
PLAN_SHA = '2bb2e3e28c15e10f0af1d05b9f7815ac0e87b9f76c8536b8b755a77c58b9b6c5'
RECOVERY_SHA = '5495760c8b123b572a78854260066ce09448d88d9deb86c634b97703bc09c04a'
OLD_TEST_SHA = '99b85ff009236bdc4c09d878d702b4f42b3754f0596296daf702c96715213eaf'
TEST_REL = 'tests/test_operational_runtime_closure.py'
NEW_FUNCTION = 'test_normal_success_publication_uses_real_operational_authority'


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def verify(pin):
    blob = Path(pin['path']).read_bytes()
    assert len(blob) == pin['bytes'] and digest(blob) == pin['sha256'], pin['path']
    return blob


def parse(blob):
    tree = ast.parse(blob.decode('utf-8'), type_comments=True)
    for node in ast.walk(tree):
        if isinstance(node, ast.TypeIgnore):
            node.lineno = 0
    return tree


def dump(node):
    return ast.dump(node, include_attributes=False)


def string_bytes(tree):
    return [node.value.encode('utf-8') for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def comments(blob, exclude=None):
    return [token.string for token in tokenize.generate_tokens(
        io.StringIO(blob.decode('utf-8')).readline)
        if token.type == tokenize.COMMENT and
        (exclude is None or not exclude[0] <= token.start[0] <= exclude[1])]


def source_ids(tree):
    rows = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith('test_'):
            continue
        ids = None
        for decorator in node.decorator_list:
            if (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr == 'parametrize'):
                explicit = [item.value for item in decorator.keywords if item.arg == 'ids']
                assert len(explicit) <= 1 and ids is None
                value = explicit[0] if explicit else decorator.args[1]
                assert isinstance(value, (ast.List, ast.Tuple))
                assert all(isinstance(item, ast.Constant) and isinstance(item.value, str)
                           for item in value.elts)
                ids = [item.value for item in value.elts]
        rows.extend([TEST_REL + '::' + node.name] if ids is None else [
            TEST_REL + '::' + node.name + '[' + value + ']' for value in ids])
    return rows


plan_blob = (BASE / 'plan.json').read_bytes()
recovery_blob = (RECOVERY / 'plan.json').read_bytes()
assert digest(plan_blob) == PLAN_SHA and digest(recovery_blob) == RECOVERY_SHA
plan, recovery = json.loads(plan_blob), json.loads(recovery_blob)
pins = {pin['path']: pin for pin in plan['inputs']}
recovery_pins = {pin['path']: pin for pin in recovery['inputs']}
history_path = HISTORY / 'plan.json'
history_blob = verify(pins[str(history_path)])
history = json.loads(history_blob)
history_pins = {pin['path']: pin for pin in history['inputs']}
frozen_path = HISTORY / 'implementation/final-freeze/sources' / TEST_REL
frozen_blob = verify(pins[str(frozen_path)])
baseline_index_path = HISTORY / 'implementation/final-freeze/source-index.json'
verify(pins[str(baseline_index_path)])
dependencies = [
    {'pin': pins[str(history_path)], 'source_plan': str(BASE / 'plan.json')},
    {'pin': pins[str(frozen_path)], 'source_plan': str(BASE / 'plan.json')},
    {'pin': pins[str(baseline_index_path)], 'source_plan': str(BASE / 'plan.json')},
]
old_scope_paths = [
    ROUNDS / 'round134-p6-red-interface-connection-recovery-20261011/implementation/stopped-ruff-r137/scope-proof.py',
    ROUNDS / 'round134-p6-red-interface-connection-recovery-20261011/implementation/stopped-ruff-r137/evidence/scope_proof/proof.json',
]
for path in old_scope_paths:
    pin = history_pins[str(path)]
    verify(pin)
    dependencies.append({'pin': pin, 'source_plan': str(history_path)})
schema_paths = [
    ROOT / 'tests/test_visual_worker_factory.py',
    ROOT / 'tests/test_rgbd_lease_handoff.py',
    ROOT / 'src/cloud_edge_robot_arm/vision/evaluation.py',
    ROOT / 'src/cloud_edge_robot_arm/vision/operational_windows.py',
    ROOT / 'src/cloud_edge_robot_arm/repositories/event_autonomy/sqlite.py',
]
for path in schema_paths:
    pin = pins[str(path)]
    verify(pin)
    dependencies.append({'pin': pin, 'source_plan': str(BASE / 'plan.json')})
assert len(plan['scope']['production_pins']) == 5 and len(plan['scope']['protected']) == 53
for pin in plan['scope']['production_pins']:
    original = verify(pins[pin['snapshot']])
    current = verify(pins[pin['source']])
    assert original == current and digest(current) == pin['sha256']
for pin in plan['scope']['protected']:
    verify(pin)
event_receipt_path = ROUNDS / 'round144-astra-event-repository-path-recovery-20261012/read-observation.json'
event_pin = recovery_pins[str(event_receipt_path)]
verify(event_pin)
dependencies.append({'pin': event_pin, 'source_plan': str(RECOVERY / 'plan.json')})

before_blob = (BASE / 'implementation/before-test.py').read_bytes()
assert before_blob == frozen_blob and len(before_blob) == 65231 and digest(before_blob) == OLD_TEST_SHA
after_blob = Path(plan['scope']['edit_path']).read_bytes()
before_tree, after_tree = parse(before_blob), parse(after_blob)
assert len(after_tree.body) == len(before_tree.body) + 1
added = after_tree.body[-1]
assert isinstance(added, ast.FunctionDef) and added.name == NEW_FUNCTION
assert not added.decorator_list
assert [item.arg for item in added.args.args] == ['monkeypatch', 'tmp_path']
assert not added.args.posonlyargs and not added.args.kwonlyargs
assert added.args.vararg is None and added.args.kwarg is None and not added.args.defaults
assert sum(isinstance(node, ast.FunctionDef) and node.name == NEW_FUNCTION
           for node in after_tree.body) == 1
old_ids, total_ids = source_ids(before_tree), source_ids(after_tree)
assert old_ids == history['scope']['source_nodeids'] and len(old_ids) == 39
assert total_ids == old_ids + [plan['scope']['append_only_test']]
assert len(total_ids) == len(set(total_ids)) == 40
assert comments(before_blob) == comments(after_blob, (added.lineno, added.end_lineno))
after_tree.body.pop()
assert dump(before_tree) == dump(after_tree)
assert string_bytes(before_tree) == string_bytes(after_tree)
calls = [node for node in ast.walk(added) if isinstance(node, ast.Call)]
patches = [node for node in calls if isinstance(node.func, ast.Attribute)
           and isinstance(node.func.value, ast.Name) and node.func.value.id == 'monkeypatch']
assert len(patches) == 1
patch = patches[0]
assert patch.func.attr == 'setattr' and not patch.keywords and len(patch.args) == 3
assert dump(patch.args[0]) == dump(ast.Name(id='execution', ctx=ast.Load()))
assert isinstance(patch.args[1], ast.Constant) and patch.args[1].value == 'run_visual_episode'
assert dump(patch.args[2]) == dump(ast.Name(id='controlled_episode', ctx=ast.Load()))
assert sum(isinstance(node.func, ast.Name) and node.func.id == '_exercise' for node in calls) == 1
assert sum(isinstance(node.func, ast.Name) and node.func.id == 'original_episode'
           for node in calls) == 1
for node in calls:
    if isinstance(node.func, ast.Attribute):
        assert node.func.attr not in {
            'execute', 'executemany', 'executescript', 'poll_once', 'update_status_cas',
            'start_attempt', 'finish_attempt', 'save_artifacts', 'save_metrics',
            'finalize_operational_publication', 'propose_locked', 'confirm_committed',
        }, ast.unparse(node.func)
    if isinstance(node.func, ast.Name):
        assert node.func.id not in {'eval', 'exec', 'compile', '_successful_visual_episode'}
injections = [node for node in added.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == 'injected'
                      for target in node.targets)]
assert len(injections) == 1 and isinstance(injections[0].value, ast.Dict)
mapping = injections[0].value
assert all(isinstance(key, ast.Constant) and isinstance(value, ast.Constant)
           for key, value in zip(mapping.keys, mapping.values, strict=True))
assert {key.value: value.value for key, value in zip(mapping.keys, mapping.values, strict=True)} == plan['scope']['injected_fields']
replacements = [node for node in calls if isinstance(node.func, ast.Name) and node.func.id == 'replace']
assert len(replacements) == 1 and len(replacements[0].args) == 1
assert dump(replacements[0].args[0]) == dump(ast.Name(id='original', ctx=ast.Load()))
assert len(replacements[0].keywords) == 1 and replacements[0].keywords[0].arg is None
assert dump(replacements[0].keywords[0].value) == dump(ast.Name(id='injected', ctx=ast.Load()))
output = {
    'status': 'R141_APPEND_ONE_TEST_SOURCE_PROOF_PASS',
    'plan_sha256': PLAN_SHA, 'R143_plan_sha256': RECOVERY_SHA,
    'before_test_sha256': digest(before_blob), 'final_test_sha256': digest(after_blob),
    'final_test_bytes': len(after_blob), 'appended_function': NEW_FUNCTION,
    'function_range': [added.lineno, added.end_lineno],
    'original_module_AST_type_comments_equal_after_removing_only_added_function': True,
    'original_comments_and_string_UTF8_constants_equal': True,
    'original39_source_nodeids': old_ids, 'total40_source_nodeids': total_ids,
    'source_only_not_collected': True,
    'exact_episode_seam': ast.unparse(patch),
    'injected_flags': plan['scope']['injected_fields'],
    'no_direct_SQL_writes_permission_or_publication_patches': True,
    'five_production': plan['scope']['production_pins'], 'protected': plan['scope']['protected'],
    'dependency_pins_and_exact_source_plans': dependencies,
    'product_import_compile_eval_collect': False,
    'boundary': 'Append-only software control source proof. Positive run and original four remain HELD; no physics/native/actual/formal acceptance.',
}
serialized = (json.dumps(output, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
target = BASE / 'implementation/scope_proof/proof.json'
with target.open('xb') as stream:
    stream.write(serialized)
print(json.dumps({'status': output['status'], 'path': str(target),
                  'bytes': len(serialized), 'sha256': digest(serialized)}, ensure_ascii=False))
