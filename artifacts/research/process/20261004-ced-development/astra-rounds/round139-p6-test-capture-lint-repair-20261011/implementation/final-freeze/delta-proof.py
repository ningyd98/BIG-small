"""R139 single authorized narrow source proof; no product execution."""

import ast
import hashlib
import io
import json
from pathlib import Path
import tokenize

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUNDS = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds'
BASE = ROUNDS / 'round139-p6-test-capture-lint-repair-20261011'
OLD = ROUNDS / 'round134-p6-red-interface-connection-recovery-20261011/implementation/stopped-ruff-r137'
PLAN_SHA = '4812519c7b0e00e1fb5158cbcdc2f3267db81839b92fe83d4a70af6488ae64b9'
TEST_SHA = '6bced34545df1e9d733444012ef427e321f07aed83fa3ae16c3fc3f71326abd4'
TEST_REL = 'tests/test_operational_runtime_closure.py'
FUNCTION = 'test_operational_status_cas_cannot_grant_without_session'
CAPTURES = ['source', 'target', 'trial_root']
ORIGINAL_COMMENT = '# This preparation is actual authorized main-thread status CAS, never foreign success.'
REFLOWED_COMMENTS = [
    '# This preparation is actual authorized main-thread status CAS,',
    '# never foreign success.',
]
ORIGINAL_SCOPE_PIN = {
    'path': '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round127-p6-private-authority-lifecycle-repair-20261011/implementation/scope-proof.py',
    'bytes': 7714,
    'sha256': '2fbff6a9b43ab829245f7e09370eb392e607b4af17b9c63dcfd6ef7e21b13983',
}


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def pinned(path, size, expected):
    blob = Path(path).read_bytes()
    assert len(blob) == size and digest(blob) == expected, str(path)
    return blob


def dump(node):
    return ast.dump(node, include_attributes=False)


def parse(blob):
    tree = ast.parse(blob.decode('utf-8'), type_comments=True)
    # TypeIgnore.lineno is a location stored as a field rather than an attribute.
    for node in ast.walk(tree):
        if isinstance(node, ast.TypeIgnore):
            node.lineno = 0
    return tree


def callback(tree):
    roots = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name == FUNCTION]
    assert len(roots) == 1
    loops = [node for node in roots[0].body if isinstance(node, ast.For)
             and isinstance(node.target, ast.Tuple)
             and [dump(item) for item in node.target.elts]
             == [dump(ast.Name(id=name, ctx=ast.Store())) for name in ('source', 'target')]]
    assert len(loops) == 1
    checks = [node for node in loops[0].body
              if isinstance(node, ast.FunctionDef) and node.name == 'check']
    assert len(checks) == 1
    bindings = [node for node in loops[0].body if isinstance(node, ast.Assign)
                and any(isinstance(item, ast.Name) and item.id == 'trial_root'
                        for item in node.targets)]
    assert len(bindings) == 1
    assert bindings[0].lineno < checks[0].lineno
    return roots[0], loops[0], checks[0]


def comments(blob):
    return [token.string for token in tokenize.generate_tokens(
        io.StringIO(blob.decode('utf-8')).readline) if token.type == tokenize.COMMENT]


def string_constants(tree):
    return [node.value.encode('utf-8') for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def source_ids(tree):
    rows, functions = [], []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith('test_'):
            continue
        ids = None
        for decorator in node.decorator_list:
            if (isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr == 'parametrize'):
                explicit = [item.value for item in decorator.keywords if item.arg == 'ids']
                assert len(explicit) <= 1
                value = explicit[0] if explicit else decorator.args[1]
                assert isinstance(value, (ast.List, ast.Tuple))
                assert all(isinstance(item, ast.Constant) and isinstance(item.value, str)
                           for item in value.elts)
                assert ids is None, 'Multiple parametrization dimensions are not authorized'
                ids = [item.value for item in value.elts]
        local = ([TEST_REL + '::' + node.name] if ids is None else
                 [TEST_REL + '::' + node.name + '[' + value + ']' for value in ids])
        rows.extend(local)
        functions.append({'function': node.name, 'start': node.lineno,
                          'end': node.end_lineno, 'nodeids': local,
                          'decorators_AST': [dump(item) for item in node.decorator_list]})
    return rows, functions


plan_blob = (BASE / 'plan.json').read_bytes()
assert digest(plan_blob) == PLAN_SHA
plan = json.loads(plan_blob)
assert len(plan['scope']['unchanged_production']) == 5
assert len(plan['scope']['protected']) == 53
assert len(plan['scope']['source_nodeids']) == 39
pins = {item['path']: item for item in plan['inputs']}
dependency_paths = [
    ROUNDS / 'round127-p6-private-authority-lifecycle-repair-20261011/implementation/scope-proof.py',
    ROUNDS / 'round127-p6-private-authority-lifecycle-repair-20261011/implementation/scope_proof/proof.json',
    OLD / 'evidence/scope_proof/proof.json',
    OLD / 'preformat-source-index.json',
    OLD / 'finite-manifest.json',
]
dependencies = []
for path in dependency_paths:
    if str(path) == ORIGINAL_SCOPE_PIN['path']:
        pin = ORIGINAL_SCOPE_PIN
    else:
        pin = pins[str(path)]
    pinned(path, pin['bytes'], pin['sha256'])
    dependencies.append(pin)
manifest = json.loads((OLD / 'finite-manifest.json').read_bytes())
production = []
for pin in plan['scope']['unchanged_production']:
    original = pinned(pin['snapshot'], pin['bytes'], pin['sha256'])
    current = pinned(pin['source'], pin['bytes'], pin['sha256'])
    assert original == current
    production.append(pin)
for pin in plan['scope']['protected']:
    pinned(pin['path'], pin['bytes'], pin['sha256'])

before_blob = (BASE / 'implementation/before-test.py').read_bytes()
assert len(before_blob) == 65002 and digest(before_blob) == TEST_SHA
assert before_blob == (OLD / 'sources' / TEST_REL).read_bytes()
after_blob = Path(plan['scope']['edit_path']).read_bytes()
before_tree, after_tree = parse(before_blob), parse(after_blob)
old_root, old_loop, old_check = callback(before_tree)
new_root, new_loop, new_check = callback(after_tree)
assert len(old_check.args.args) == 8
assert [item.arg for item in old_check.args.args] == [
    'module', 'session', 'runtime', 'lease_raw', 'app_raw', 'worker', 'repo', 'job']
assert not old_check.args.kwonlyargs and not old_check.args.kw_defaults
assert old_check.args.vararg is None and old_check.args.kwarg is None
assert len(new_check.args.kwonlyargs) == 3
assert len(new_check.args.kw_defaults) == 3
assert [item.arg for item in new_check.args.kwonlyargs] == CAPTURES
assert all(item.annotation is None and item.type_comment is None
           for item in new_check.args.kwonlyargs)
assert [dump(item) for item in new_check.args.kw_defaults] == [
    dump(ast.Name(id=name, ctx=ast.Load())) for name in CAPTURES]
assert [dump(item) for item in old_check.decorator_list] == [
    dump(item) for item in new_check.decorator_list]
before_ids, before_functions = source_ids(before_tree)
after_ids, after_functions = source_ids(after_tree)
assert before_ids == after_ids == plan['scope']['source_nodeids'] == manifest['all39']
assert len(after_ids) == len(set(after_ids)) == 39
assert len(manifest['original20']) == 20 and len(manifest['new19']) == 19
assert [{k: v for k, v in row.items() if k not in ('start', 'end')}
        for row in before_functions] == [
        {k: v for k, v in row.items() if k not in ('start', 'end')}
        for row in after_functions]
old_strings, new_strings = string_constants(before_tree), string_constants(after_tree)
assert old_strings == new_strings
old_comments, new_comments = comments(before_blob), comments(after_blob)
assert old_comments.count(ORIGINAL_COMMENT) == 1
index = old_comments.index(ORIGINAL_COMMENT)
expected_comments = old_comments[:index] + REFLOWED_COMMENTS + old_comments[index + 1:]
assert new_comments == expected_comments
assert ' '.join(ORIGINAL_COMMENT[1:].split()) == ' '.join(
    ' '.join(item[1:] for item in REFLOWED_COMMENTS).split())

# Normalize only the three verified new keyword-only/default entries, in memory.
# Full-tree equality then covers all eight positional args, bodies, calls and asserts.
new_check.args.kwonlyargs = []
new_check.args.kw_defaults = []
assert dump(before_tree) == dump(after_tree)
output = {
    'status': 'R139_NARROW_SOURCE_DELTA_PASS',
    'before_test_sha256': digest(before_blob), 'final_test_sha256': digest(after_blob),
    'final_test_bytes': len(after_blob), 'plan_sha256': PLAN_SHA,
    'old_scope_proof_dependencies_unchanged': dependencies,
    'supplemental_dependency_provenance': {
        'pin': ORIGINAL_SCOPE_PIN,
        'source_plan': str(ROUNDS / 'round140-p6-delta-dependency-pin-recovery-20261011/plan.json'),
        'source_plan_sha256': 'bf95861fe0c6e81c934f76ff7d8fbd28cea82763ecdf1c2f99abf652aab001c3',
        'historical_R139_inclusion': False,
        'other_four_dependency_pin_source': str(BASE / 'plan.json'),
    },
    'exact_target': FUNCTION + '.for[source,target].check',
    'bindings': CAPTURES, 'original_positional_count': 8,
    'normalized_full_AST_type_comments_equal': True,
    'normalization': 'Only three verified kwonly args and matching default Name entries removed in memory',
    'comments': {'only_exact_reflow': True, 'before': ORIGINAL_COMMENT,
                 'after': REFLOWED_COMMENTS, 'words_order_equal': True},
    'complete_string_SQL_UTF8_sequence_equal': True,
    'string_constants': [{'bytes': len(value), 'sha256': digest(value)}
                         for value in new_strings],
    'unchanged_production': production, 'protected': plan['scope']['protected'],
    'source_nodeids': after_ids, 'test_function_ranges': after_functions,
    'source_only_not_collected': True, 'product_import_compile_eval_collect': False,
    'boundary': 'Limited static/source change only; behavior recovery and four final gates remain HELD',
}
serialized = (json.dumps(output, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
target = BASE / 'implementation/delta_proof/proof.json'
with target.open('xb') as stream:
    stream.write(serialized)
print(json.dumps({'status': output['status'], 'path': str(target),
                  'bytes': len(serialized), 'sha256': digest(serialized)}, ensure_ascii=False))
