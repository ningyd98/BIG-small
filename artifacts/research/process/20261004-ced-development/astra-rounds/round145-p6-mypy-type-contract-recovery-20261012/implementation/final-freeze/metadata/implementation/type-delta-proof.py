from pathlib import Path
import ast
import copy
import difflib
import hashlib
import io
import json
import tokenize

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUND = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round145-p6-mypy-type-contract-recovery-20261012'
PLAN_SHA = '91ae27194e5a2d5c09e3610a3ef52af12a9e888a124fef443dec46d13197c558'
FROZEN = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round141-p6-positive-publication-control-20261012/implementation/stopped-final-mypy'
plan_bytes = (ROUND / 'plan.json').read_bytes()
assert hashlib.sha256(plan_bytes).hexdigest() == PLAN_SHA
plan = json.loads(plan_bytes)
pins = {p['path']: p for p in plan['inputs']}
assert len(pins) == len(plan['inputs'])


def read_pinned(path):
    path = Path(path)
    record = pins[str(path)]
    data = path.read_bytes()
    assert len(data) == record['bytes']
    assert hashlib.sha256(data).hexdigest() == record['sha256']
    return data


def record(path, data=None):
    path = Path(path)
    data = path.read_bytes() if data is None else data
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def dump(node):
    return ast.dump(node, include_attributes=False)


def expression(text):
    return ast.parse(text, mode='eval').body


def unique(nodes):
    nodes = list(nodes)
    assert len(nodes) == 1
    return nodes[0]


def top_class(module, name):
    return unique(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == name)


def method(cls, name):
    return unique(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)


def names(node, name):
    return [n for n in ast.walk(node) if isinstance(n, ast.Name) and n.id == name]


def alpha(node, new, old, count):
    found = names(node, new)
    assert len(found) == count
    for n in found:
        n.id = old


def replace_exact(scope, new, old):
    wanted = dump(expression(new))
    count = 0

    class Replace(ast.NodeTransformer):
        def visit(self, node):
            nonlocal count
            if dump(node) == wanted:
                count += 1
                return copy.deepcopy(expression(old))
            return super().visit(node)

    Replace().visit(scope)
    assert count == 1


def remove_added_import(module, package, name):
    candidates = [n for n in module.body if isinstance(n, ast.ImportFrom) and n.module == package and n.level == 0 and any(a.name == name for a in n.names)]
    node = unique(candidates)
    added = unique(a for a in node.names if a.name == name)
    assert added.asname is None
    node.names.remove(added)
    if not node.names:
        module.body.remove(node)


def normalized_import_order(module):
    module = copy.deepcopy(module)
    for node in module.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            node.names.sort(key=lambda a: (a.name, a.asname or ''))
    start = 0
    while start < len(module.body):
        if not isinstance(module.body[start], (ast.Import, ast.ImportFrom)):
            start += 1
            continue
        end = start
        while end < len(module.body) and isinstance(module.body[end], (ast.Import, ast.ImportFrom)):
            end += 1
        module.body[start:end] = sorted(module.body[start:end], key=dump)
        start = end
    return module


def constants(module):
    return [(type(n.value).__name__, n.value.encode('utf-8').hex() if isinstance(n.value, str) else n.value.hex()) for n in ast.walk(module) if isinstance(n, ast.Constant) and isinstance(n.value, (str, bytes))]


def comments(data):
    return [t.string for t in tokenize.tokenize(io.BytesIO(data).readline) if t.type == tokenize.COMMENT]


index_path = FROZEN / 'source-index.json'
frozen_index = json.loads(read_pinned(index_path))
protected = []
for p in frozen_index['protected']:
    data = read_pinned(p['path'])
    assert len(data) == p['bytes'] and hashlib.sha256(data).hexdigest() == p['sha256']
    protected.append(p)
assert len(protected) == 53
all_after = []
for path in plan['scope']['fixed_paths']:
    data = read_pinned(path)
    frozen = FROZEN / 'sources' / str(Path(path).relative_to(ROOT))
    assert data == read_pinned(frozen)
    all_after.append(record(path, data))
assert len(all_after) == 4
results = []
diffs = []
for path in plan['scope']['edit_paths']:
    path = Path(path)
    frozen = FROZEN / 'sources' / str(path.relative_to(ROOT))
    before_bytes = read_pinned(frozen)
    before_pin = pins[str(path)]
    assert before_pin['sha256'] == hashlib.sha256(before_bytes).hexdigest()
    assert before_pin['bytes'] == len(before_bytes)
    after_bytes = path.read_bytes()
    before = ast.parse(before_bytes.decode('utf-8'), type_comments=True)
    after = ast.parse(after_bytes.decode('utf-8'), type_comments=True)
    original_after = copy.deepcopy(after)
    if path.name == 'operational_lease.py':
        before_reduce = method(top_class(before, '_Opaque'), '__reduce_ex__')
        after_reduce = method(top_class(after, '_Opaque'), '__reduce_ex__')
        assert dump(before_reduce.args.args[1].annotation) == dump(expression('int'))
        assert dump(before_reduce.returns) == dump(expression('object'))
        assert dump(after_reduce.args.args[1].annotation) == dump(expression('SupportsIndex'))
        assert dump(after_reduce.returns) == dump(expression('NoReturn'))
        after_reduce.args.args[1].annotation = copy.deepcopy(before_reduce.args.args[1].annotation)
        after_reduce.returns = copy.deepcopy(before_reduce.returns)
        before_session = top_class(before, 'OperationalLeaseSession')
        after_session = top_class(after, 'OperationalLeaseSession')
        before_invalidate = method(before_session, 'invalidate')
        after_invalidate = method(after_session, 'invalidate')
        assert not names(before_invalidate, 'issued_view')
        loop = unique(n for n in ast.walk(after_invalidate) if isinstance(n, ast.For) and dump(n.iter) == dump(expression('_VIEWS.values()')))
        assert dump(loop.target) == dump(ast.Name(id='issued_view', ctx=ast.Store()))
        assert len(names(after_invalidate, 'issued_view')) == 4
        alpha(loop, 'issued_view', 'issued', 4)
        before_decide = method(before_session, '_decide')
        after_decide = method(after_session, '_decide')
        assert not names(before_decide, 'issued_proposal')
        consume = unique(n for n in ast.walk(after_decide) if isinstance(n, ast.If) and dump(n.test) == dump(expression("binding.kind == 'consume'")))
        assert len(names(after_decide, 'issued_proposal')) == 3
        alpha(consume, 'issued_proposal', 'proposal', 3)
        remove_added_import(after, 'typing', 'NoReturn')
        remove_added_import(after, 'typing', 'SupportsIndex')
        allowed = ['T1 exact reduce_ex annotations', 'T2 only invalidate _VIEWS loop alpha4', 'T3 only consume branch alpha3', 'typing NoReturn/SupportsIndex imports']
    else:
        assert path.name == 'sqlite_repository.py'
        descriptor = top_class(after, '_ContextManagerFunction')
        expected = ast.parse('class _ContextManagerFunction(Protocol):\n    __wrapped__: FunctionType\n').body[0]
        assert dump(descriptor) == dump(expected)
        assert not any(isinstance(n, ast.ClassDef) and n.name == '_ContextManagerFunction' for n in before.body)
        after.body.remove(descriptor)
        writer = unique(n for n in after.body if isinstance(n, ast.FunctionDef) and n.name == '_job_writer')
        replace_exact(writer, 'cast(FunctionType, guarded).__code__', 'guarded.__code__')
        cls = top_class(after, 'SQLiteSimulationJobRepository')
        register = method(cls, '_register_writer')
        replace_exact(register, 'cast(_ContextManagerFunction, self._legacy_write_transaction).__wrapped__.__code__', 'self._legacy_write_transaction.__wrapped__.__code__')
        replace_exact(register, 'cast(_ContextManagerFunction, self._operational_transaction).__wrapped__.__code__', 'self._operational_transaction.__wrapped__.__code__')
        writer_call = method(cls, '_writer_call')
        replace_exact(writer_call, 'cast(OperationalLeaseSession, _current_session(self)).lease_id', '_current_session(self).lease_id')
        remove_added_import(after, 'types', 'FunctionType')
        remove_added_import(after, 'typing', 'Protocol')
        allowed = ['T4 one exact __wrapped__ FunctionType Protocol and imports', 'T4 exact guarded cast', 'T4 two exact contextmanager casts', 'T5 exact lazy right-operand session cast']
    assert dump(normalized_import_order(after)) == dump(normalized_import_order(before))
    assert constants(original_after) == constants(before)
    assert comments(after_bytes) == comments(before_bytes)
    after_record = record(path, after_bytes)
    all_after.append(after_record)
    results.append({'before': record(frozen, before_bytes), 'after': after_record, 'exact_whitelist': allowed, 'normalized_full_module_AST_type_comments_equal': True, 'existing_str_bytes_UTF8_constants_equal': True, 'ordered_comment_tokens_equal': True, 'existing_function_class_shapes_branches_calls_exceptions_frames_preserved_by_full_AST': True})
    diffs.append(''.join(difflib.unified_diff(before_bytes.decode().splitlines(True), after_bytes.decode().splitlines(True), fromfile=str(frozen), tofile=str(path))))
output = ROUND / 'implementation/delta_proof/proof.json'
diff_path = output.parent / 'before-after.diff'
assert not output.exists() and not diff_path.exists()
result = {'status': 'PASS_TYPE_DELTA_SOURCE_ONLY', 'plan_sha256': PLAN_SHA, 'frozen_index': record(index_path), 'two_source_deltas': results, 'six_current': all_after, 'fixed_test_node_count_source_only': 40, 'protected': protected, 'product_import_eval_compile_collect_probe': False, 'boundary': 'Constrained T1-T5 type delta only. Existing CPU positive is software control, no physical/native/actual/formal evidence; two original GREEN commands still HELD.'}
serialized = (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode()
diff_bytes = ''.join(diffs).encode()
with diff_path.open('xb') as stream:
    stream.write(diff_bytes)
with output.open('xb') as stream:
    stream.write(serialized)
print(json.dumps({'status': result['status'], 'proof': record(output), 'diff': record(diff_path)}, ensure_ascii=False))
