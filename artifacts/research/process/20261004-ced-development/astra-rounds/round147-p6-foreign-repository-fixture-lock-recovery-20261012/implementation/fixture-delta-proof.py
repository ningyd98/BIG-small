from pathlib import Path
import ast
import copy
import difflib
import hashlib
import io
import json
import tokenize

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUND = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012'
PLAN_SHA = '0e153156b8b47e175063037d6807943348a4e4f9751ca51a0ad7b9b7c52b6d30'
PREVIOUS = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round145-p6-mypy-type-contract-recovery-20261012/implementation/stopped-green20'
TEST = ROOT / 'tests/test_operational_runtime_closure.py'
plan_bytes = (ROUND / 'plan.json').read_bytes()
assert hashlib.sha256(plan_bytes).hexdigest() == PLAN_SHA
plan = json.loads(plan_bytes)
pins = {p['path']: p for p in plan['inputs']}
assert len(pins) == len(plan['inputs'])

PREPARATION = '''if variant == "foreign_repo":
    other = SQLiteSimulationJobRepository(repo.database_path)
'''
FOREIGN_BODY = '''assert other is not repo
assert other.database_path.resolve() == repo.database_path.resolve()
assert session.repository is repo
live_before = view._connection.in_transaction
assert live_before
with pytest.raises(module.OperationalLeaseError, match="session requires exact concrete repository/job") as denial:
    with _tx(other, session, job) as foreign:
        session.propose_locked(foreign, ttl_ns=session.ttl_ns)
live_after = view._connection.in_transaction
assert live_after
'''
SIDECAR = '''if variant == "foreign_repo":
    _evidence(
        tmp_path,
        "foreign-repository-denial",
        {
            "repository_id": id(repo),
            "other_repository_id": id(other),
            "different_repository_objects": other is not repo,
            "repository_database": str(repo.database_path.resolve()),
            "other_database": str(other.database_path.resolve()),
            "session_repository_is_original": session.repository is repo,
            "original_connection_id": id(view._connection),
            "original_connection_in_transaction_before": live_before,
            "original_connection_in_transaction_after": live_after,
            "denial_type": type(denial.value).__name__,
            "denial_message": str(denial.value),
            "whole_sql_equal_assertion_completed": True,
        },
    )
'''


def read_pinned(path):
    path = Path(path)
    pin = pins[str(path)]
    data = path.read_bytes()
    assert len(data) == pin['bytes'] and hashlib.sha256(data).hexdigest() == pin['sha256']
    return data


def record(path, data=None):
    path = Path(path)
    data = path.read_bytes() if data is None else data
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def dump(node):
    return ast.dump(node, include_attributes=False)


def unique(nodes):
    nodes = list(nodes)
    assert len(nodes) == 1
    return nodes[0]


def statements(text):
    return ast.parse(text, type_comments=True).body


def expression(text):
    return ast.parse(text, mode='eval').body


def function(module, name):
    return unique(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == name)


def statement_dumps(nodes):
    return [dump(n) for n in nodes]


def constants(module):
    return [(type(n.value).__name__, n.value.encode('utf-8').hex() if isinstance(n.value, str) else n.value.hex()) for n in ast.walk(module) if isinstance(n, ast.Constant) and isinstance(n.value, (str, bytes))]


def comments(data):
    return [t.string for t in tokenize.tokenize(io.BytesIO(data).readline) if t.type == tokenize.COMMENT]


def source_nodeids(module):
    result = []
    for node in module.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith('test_'):
            continue
        parameterizations = [d for d in node.decorator_list if isinstance(d, ast.Call) and dump(d.func) == dump(expression('pytest.mark.parametrize'))]
        if not parameterizations:
            result.append('tests/test_operational_runtime_closure.py::' + node.name)
            continue
        call = unique(parameterizations)
        ids = [k.value for k in call.keywords if k.arg == 'ids']
        values = unique(ids) if ids else call.args[1]
        assert isinstance(values, (ast.List, ast.Tuple))
        assert all(isinstance(n, ast.Constant) and isinstance(n.value, str) for n in values.elts)
        for n in values.elts:
            result.append('tests/test_operational_runtime_closure.py::' + node.name + '[' + n.value + ']')
    assert len(result) == 40 and len(set(result)) == 40
    return result


old_index_path = PREVIOUS / 'source-index.json'
old_index = json.loads(read_pinned(old_index_path))
before_path = PREVIOUS / 'sources/tests/test_operational_runtime_closure.py'
before_bytes = read_pinned(before_path)
assert len(before_bytes) == 79032 and hashlib.sha256(before_bytes).hexdigest() == plan['scope']['baseline_test_sha256']
after_bytes = TEST.read_bytes()
before = ast.parse(before_bytes.decode(), type_comments=True)
after = ast.parse(after_bytes.decode(), type_comments=True)
original_after = copy.deepcopy(after)
before_test = function(before, 'test_caller_cannot_register_locked_view')
after_test = function(after, 'test_caller_cannot_register_locked_view')
before_callback = function(before_test, 'check')
after_callback = function(after_test, 'check')
assert len(before_callback.body) == 6 and len(after_callback.body) == 8
assert dump(before_callback.body[1]) == dump(statements('before = _all_sql(repo)')[0])
assert dump(after_callback.body[1]) == dump(before_callback.body[1])
assert dump(after_callback.body[2]) == dump(statements(PREPARATION)[0])
assert dump(after_callback.body[6]) == dump(statements(SIDECAR)[0])
assert dump(before_callback.body[4]) == dump(statements('assert _all_sql(repo) == before')[0])
assert dump(after_callback.body[5]) == dump(before_callback.body[4])
before_context = before_callback.body[3]
after_context = after_callback.body[4]
assert isinstance(before_context, ast.With) and isinstance(after_context, ast.With)
assert statement_dumps(before_context.items) == statement_dumps(after_context.items)
before_branch = before_context.body[0].orelse[0].orelse[0]
after_branch = after_context.body[0].orelse[0].orelse[0]
assert isinstance(before_branch, ast.If) and isinstance(after_branch, ast.If)
assert dump(before_branch.test) == dump(expression('variant == "foreign_repo"'))
assert dump(after_branch.test) == dump(before_branch.test)
assert len(before_branch.body) == 2
assert dump(before_branch.body[0]) == dump(statements('other = SQLiteSimulationJobRepository(repo.database_path)')[0])
assert statement_dumps(after_branch.body) == statement_dumps(statements(FOREIGN_BODY))
original_denial = before_branch.body[1]
new_denial = after_branch.body[5]
assert isinstance(original_denial, ast.With) and isinstance(new_denial, ast.With)
assert statement_dumps(original_denial.body) == statement_dumps(new_denial.body)
assert dump(original_denial.items[0].context_expr.func) == dump(new_denial.items[0].context_expr.func)
assert statement_dumps(original_denial.items[0].context_expr.args) == statement_dumps(new_denial.items[0].context_expr.args)
constructors = [n for n in ast.walk(after_callback) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'SQLiteSimulationJobRepository']
assert len(constructors) == 1
assert dump(constructors[0]) == dump(before_branch.body[0].value)
after_branch.body = copy.deepcopy(before_branch.body)
after_callback.body = [after_callback.body[i] for i in (0, 1, 3, 4, 5, 7)]
assert dump(after) == dump(before)
assert constants(after) == constants(before)
assert comments(after_bytes) == comments(before_bytes)
before_ids = source_nodeids(before)
after_ids = source_nodeids(original_after)
assert before_ids == after_ids
five = []
for p in old_index['sources']:
    if p['source'] == str(TEST):
        continue
    data = read_pinned(p['source'])
    assert len(data) == p['bytes'] and hashlib.sha256(data).hexdigest() == p['sha256']
    five.append(record(p['source'], data))
assert len(five) == 5
protected = []
for p in old_index['protected']:
    data = read_pinned(p['path'])
    assert len(data) == p['bytes'] and hashlib.sha256(data).hexdigest() == p['sha256']
    protected.append(p)
assert len(protected) == 53
type_proof_path = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round145-p6-mypy-type-contract-recovery-20261012/implementation/delta_proof/proof.json'
read_pinned(type_proof_path)
output = ROUND / 'implementation/delta_proof/proof.json'
diff_path = output.parent / 'before-after.diff'
assert not output.exists() and not diff_path.exists()
proof = {'status': 'PASS_FOREIGN_FIXTURE_DELTA_SOURCE_ONLY', 'plan_sha256': PLAN_SHA, 'before': record(before_path, before_bytes), 'after': record(TEST, after_bytes), 'entire_module_AST_type_comments_equal_after_only_exact_statement_normalization': True, 'original_comments_and_normalized_str_bytes_constants_equal': True, 'parameter_values_ids_and40_source_nodeids_unchanged': after_ids, 'source_only_not_collected': True, 'original_constructor_count': 1, 'new_constructor_count': 1, 'constructor_same_class_argument_relocated_after_original_SQL_before_contexts': True, 'exact_live_foreign_tx_session_job_proposal_and_OperationalLeaseError_retained': True, 'exact_denial_message': 'session requires exact concrete repository/job', 'other39_nodes_and_three_other_variants_unchanged': True, 'full_original_SQL_before_after_equality_retained': True, 'new_foreign_only_sidecar': 'foreign-repository-denial.json', 'five_production': five, 'protected': protected, 'prior_type_proof': record(type_proof_path), 'old_GREEN20_actual': {'passed': 19, 'failed': 1, 'immutable': True, 'rerun': False}, 'product_import_eval_compile_collect_probe': False, 'boundary': 'Foreign fixture source delta only, not a synthetic1PASS. Original19PASS constrained reuse awaits ROOT; foreign/new19 actual gates remain HELD. CPU positive not physics/native/actual/formal.'}
serialized = (json.dumps(proof, ensure_ascii=False, indent=2) + '\n').encode()
diff_bytes = ''.join(difflib.unified_diff(before_bytes.decode().splitlines(True), after_bytes.decode().splitlines(True), fromfile=str(before_path), tofile=str(TEST))).encode()
with diff_path.open('xb') as stream:
    stream.write(diff_bytes)
with output.open('xb') as stream:
    stream.write(serialized)
print(json.dumps({'status': proof['status'], 'proof': record(output), 'diff': record(diff_path)}, ensure_ascii=False))
