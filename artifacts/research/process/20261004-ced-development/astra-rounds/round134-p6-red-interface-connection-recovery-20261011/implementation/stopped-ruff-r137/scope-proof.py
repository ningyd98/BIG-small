"""One authorized source-only R127 proof; never imports or executes product code."""

import ast
import hashlib
import io
import json
from pathlib import Path
import tokenize

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUNDS = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds'
BASE = ROUNDS / 'round127-p6-private-authority-lifecycle-repair-20261011'
FROZEN = ROUNDS / 'round134-p6-red-interface-connection-recovery-20261011/implementation/semantic-before-format-r137'
INDEX_SHA = '7a71f26c1d452ef2c9bb44f4ae1dce2f9d4a72c1ee6a1de767f712fdc5d05f1d'
MANIFEST_SHA = '7dbc5814e57ea01e02801b78af69b7325171eb7035729d98db37c3289025d746'


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def comments(text):
    return [token.string for token in tokenize.generate_tokens(io.StringIO(text).readline)
            if token.type == tokenize.COMMENT]


def parse(text):
    tree = ast.parse(text, type_comments=True)
    for node in ast.walk(tree):
        if isinstance(node, ast.TypeIgnore):
            node.lineno = 0
    return tree


def sql_constants(tree):
    tokens = ('SELECT ', 'UPDATE ', 'INSERT ', 'DELETE ', 'CREATE ', 'BEGIN ',
              'COMMIT', 'ROLLBACK', 'SAVEPOINT ', 'RELEASE ', 'PRAGMA ')
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and node.value.lstrip().upper().startswith(tokens)]


def functions(tree, prefix=''):
    rows = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            rows.extend(functions(node, prefix + node.name + '.'))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            rows.append((prefix + node.name, node))
    return rows


def call_map(tree):
    rows = []
    for name, node in functions(tree):
        sql = []
        calls = []
        guards = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                callee = ast.unparse(child.func)
                calls.append(callee)
                if isinstance(child.func, ast.Attribute) and child.func.attr in {'execute', 'executescript'}:
                    sql.append({'line': child.lineno, 'call': ast.unparse(child)})
            if isinstance(child, (ast.With, ast.AsyncWith)):
                guards.extend(ast.unparse(item.context_expr) for item in child.items)
        rows.append({'function': name, 'start': node.lineno, 'end': node.end_lineno,
                     'decorators': [ast.unparse(item) for item in node.decorator_list],
                     'calls': sorted(set(calls)), 'contexts': guards, 'SQL_calls': sql})
    return rows


index_blob = (FROZEN / 'source-index.json').read_bytes()
manifest_blob = (FROZEN / 'finite-manifest.json').read_bytes()
assert digest(index_blob) == INDEX_SHA
assert digest(manifest_blob) == MANIFEST_SHA
index = json.loads(index_blob)
manifest = json.loads(manifest_blob)
assert len(index['sources']) == 6
assert len(index['protected']) == 53
protected = []
for pin in index['protected']:
    blob = Path(pin['path']).read_bytes()
    assert len(blob) == pin['bytes'] and digest(blob) == pin['sha256'], pin['path']
    protected.append(pin)

proof = []
trees = {}
for pin in index['sources']:
    before = Path(pin['snapshot']).read_bytes()
    after = Path(pin['path']).read_bytes()
    assert len(before) == pin['bytes'] and digest(before) == pin['sha256'], pin['snapshot']
    before_text, after_text = before.decode(), after.decode()
    before_tree, after_tree = parse(before_text), parse(after_text)
    assert ast.dump(before_tree, include_attributes=False) == ast.dump(after_tree, include_attributes=False), pin['path']
    assert comments(before_text) == comments(after_text), pin['path']
    before_sql, after_sql = sql_constants(before_tree), sql_constants(after_tree)
    assert before_sql == after_sql, pin['path']
    trees[pin['relative_path']] = after_tree
    proof.append({'path': pin['path'], 'before_sha256': digest(before), 'final_sha256': digest(after),
                  'final_bytes': len(after), 'AST_type_comments_equal': True, 'comments_equal': True,
                  'decoded_SQL_constants_equal': True,
                  'SQL_constants': [{'bytes': len(value.encode()), 'sha256': digest(value.encode()),
                                     'decoded': value} for value in after_sql],
                  'functions_SQL_guard_calls': call_map(after_tree)})

test_rel = 'tests/test_operational_runtime_closure.py'
nodeids = []
test_functions = []
for node in trees[test_rel].body:
    if not isinstance(node, ast.FunctionDef) or not node.name.startswith('test_'):
        continue
    ids = None
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == 'parametrize':
            for keyword in decorator.keywords:
                if keyword.arg == 'ids':
                    assert isinstance(keyword.value, (ast.List, ast.Tuple))
                    assert all(isinstance(item, ast.Constant) and isinstance(item.value, str) for item in keyword.value.elts)
                    ids = [item.value for item in keyword.value.elts]
            if ids is None:
                assert len(decorator.args) >= 2 and isinstance(decorator.args[1], (ast.List, ast.Tuple))
                assert all(isinstance(item, ast.Constant) and isinstance(item.value, str) for item in decorator.args[1].elts)
                ids = [item.value for item in decorator.args[1].elts]
    local = [test_rel + '::' + node.name] if ids is None else [test_rel + '::' + node.name + '[' + value + ']' for value in ids]
    nodeids.extend(local)
    test_functions.append({'function': node.name, 'start': node.lineno, 'end': node.end_lineno, 'nodeids': local})
assert len(nodeids) == 39 and len(set(nodeids)) == 39
assert nodeids == manifest['all39']
assert len(manifest['original20']) == 20 and len(manifest['new19']) == 19

sql_rel = 'src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py'
writer_rows = [row for row in call_map(trees[sql_rel]) if '_job_writer' in row['decorators']]
assert all(name in {row['function'] for row in writer_rows} for name in {
    'SQLiteSimulationJobRepository.acquire_lease', 'SQLiteSimulationJobRepository.cleanup_operational_session',
    'SQLiteSimulationJobRepository.finalize_operational_publication',
    'SQLiteSimulationJobRepository.terminate_orphaned_operational_attempts'})
resource = manifest['finite_source_lifecycle_review']
output = {'status': 'SOURCE_ONLY_SCOPE_PROOF_PASS', 'product_import_compile_collect': False,
          'six_before_final_proofs': proof, 'protected': protected,
          'original20_new19_source_manifest': nodeids, 'test_function_ranges': test_functions,
          'writer_ingress': writer_rows, 'finite_source_lifecycle_review': resource,
          'R134_resource_update': manifest['R134_resource_update'],
          'source_review': {key: value for key, value in index.items()
                            if key not in {'sources', 'protected'}},
          'boundary': 'Formatting/source scope only; no behavior/GREEN/actual/formal acceptance. Old proof passes not extended.'}
target = BASE / 'implementation/scope_proof/proof.json'
serialized = (json.dumps(output, ensure_ascii=False, indent=2) + '\n').encode()
with target.open('xb') as stream:
    stream.write(serialized)
print(json.dumps({'status': output['status'], 'proof': str(target), 'sha256': digest(serialized),
                  'sources': len(proof), 'protected': len(protected), 'source_nodeids': len(nodeids),
                  'writers': len(writer_rows)}, ensure_ascii=False))
