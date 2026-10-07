"""Revert only Round74's registered type/cast/import AST differences for comparison."""
import ast
import hashlib
import io
import json
from pathlib import Path
import tokenize

root = Path('artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007')
out = root / 'implementation'
plan = json.loads((root / 'plan.json').read_text())
proof = {}
registrations = []
dump = lambda tree: ast.dump(tree, include_attributes=False)
hash_text = lambda text: hashlib.sha256(text.encode()).hexdigest()

def one(nodes, condition):
    matches = [node for node in nodes if condition(node)]
    if len(matches) != 1:
        raise ValueError('registered AST coordinate must have exactly one match')
    return matches[0]

def function(nodes, name):
    return one(nodes, lambda node: isinstance(node, ast.FunctionDef) and node.name == name)

def klass(tree, name):
    return one(tree.body, lambda node: isinstance(node, ast.ClassDef) and node.name == name)

def register(path, node, kind, before, after, explanation):
    registrations.append({'path': path, 'line_after': node.lineno, 'column_after': node.col_offset, 'kind': kind, 'before': before, 'after': after, 'reason': explanation})

def strip_type_import(tree, path, module, imported):
    block = one(tree.body, lambda node: isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == 'TYPE_CHECKING')
    node = one(block.body, lambda node: isinstance(node, ast.ImportFrom) and node.module == module and [alias.name for alias in node.names] == [imported])
    register(path, node, 'TYPE_CHECKING import', None, dump(node), 'type-only concrete reference; no runtime module import')
    block.body.remove(node)
    if not block.body:
        tree.body.remove(block)

def restore_annotation(path, before_func, after_func, parameter):
    args_before = [*before_func.args.args, *before_func.args.kwonlyargs]
    args_after = [*after_func.args.args, *after_func.args.kwonlyargs]
    old = one(args_before, lambda node: node.arg == parameter)
    new = one(args_after, lambda node: node.arg == parameter)
    register(path, new, 'parameter annotation', dump(old.annotation), dump(new.annotation), 'concrete application or object annotation; exact runtime checks remain')
    new.annotation = old.annotation

def comments(text):
    return [token.string for token in tokenize.generate_tokens(io.StringIO(text).readline) if token.type == tokenize.COMMENT]

for path in plan['scope']['modify']:
    before_text = (out / 'source-before' / path).read_text()
    after_text = Path(path).read_text()
    before = ast.parse(before_text, type_comments=True)
    after = ast.parse(after_text, type_comments=True)
    original_after_dump = dump(after)
    if path.endswith('/operational_prefix_v1.py'):
        strip_type_import(after, path, 'cloud_edge_robot_arm.research.operational_capture_v1', 'OperationalPrefixRecorderV1')
        cb, ca = klass(before, 'OperationalPrefixApplicationV1'), klass(after, 'OperationalPrefixApplicationV1')
        restore_annotation(path, function(cb.body, 'check_recorder'), function(ca.body, 'check_recorder'), 'recorder')
        fb, fa = function(before.body, '_issue_recorder_v1'), function(after.body, '_issue_recorder_v1')
        register(path, fa, 'factory return annotation', dump(fb.returns), dump(fa.returns), 'factory signs and returns exact recorder class; all guards preserved')
        fa.returns = fb.returns
        ib, ia = fb.body[0], fa.body[0]
        if not isinstance(ia, ast.ImportFrom) or ia.module != ib.module or sorted(alias.name for alias in ia.names) != sorted(alias.name for alias in ib.names):
            raise ValueError('factory import names/modules changed')
        register(path, ia, 'registered same-module import order', dump(ib), dump(ia), 'only _ISSUER / OperationalPrefixRecorderV1 alias order')
        ia.names = ib.names
    elif path.endswith('/operational_capture_v1.py'):
        typing_import = one(after.body, lambda node: isinstance(node, ast.ImportFrom) and node.module == 'typing')
        alias = one(typing_import.names, lambda node: node.name == 'TYPE_CHECKING' and node.asname is None)
        register(path, typing_import, 'typing TYPE_CHECKING alias', None, dump(alias), 'allows type-only branch without circular runtime import')
        typing_import.names.remove(alias)
        strip_type_import(after, path, 'cloud_edge_robot_arm.research.operational_prefix_v1', 'OperationalPrefixApplicationV1')
        cb, ca = klass(before, 'OperationalPrefixRecorderV1'), klass(after, 'OperationalPrefixRecorderV1')
        for name in ['__init__', 'from_application']:
            restore_annotation(path, function(cb.body, name), function(ca.body, name), 'application')
        cast_count = 0
        for name, attribute, expected_count in [('freeze_operational_prefix','_operational_frozen',1), ('export_operational_prefix','_operational_export',2)]:
            fa = function(ca.body, name)
            returns = [node for node in ast.walk(fa) if isinstance(node, ast.Return) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == 'cast']
            if len(returns) != expected_count:
                raise ValueError('cast count does not match registered method sites')
            for node in returns:
                call = node.value
                expected_type = ast.parse('dict[str, Any]', mode='eval').body
                if len(call.args) != 2 or call.keywords or dump(call.args[0]) != dump(expected_type):
                    raise ValueError('cast type differs from closed dict JSON contract')
                expected_expression = ast.parse(f'json.loads(canonical_bytes_v1(self.{attribute}))', mode='eval').body
                if dump(call.args[1]) != dump(expected_expression):
                    raise ValueError('cast expression changed JSON copy or producer')
                register(path, node, 'registered closed-dict JSON cast', dump(call.args[1]), dump(call), '_detached_operational_ledger builds dict before frozen JSON, or _operational_export is a dict literal tested non-None; cast is identity and loads still executes')
                node.value = call.args[1]
                cast_count += 1
        if cast_count != 3:
            raise ValueError('three registered cast sites required')
    elif path.endswith('/worker.py'):
        strip_type_import(after, path, 'cloud_edge_robot_arm.research.operational_prefix_v1', 'OperationalPrefixApplicationV1')
        ca = klass(after, 'SimulationWorker')
        block = one(ca.body, lambda node: isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == 'TYPE_CHECKING')
        expected = ast.parse('if TYPE_CHECKING:\n    _operational_prefix_application: OperationalPrefixApplicationV1 | None\n').body[0]
        if dump(block) != dump(expected):
            raise ValueError('worker type-only block differs or adds runtime assignment')
        register(path, block, 'registered worker TYPE_CHECKING attribute declaration', None, dump(block), 'no default assignment; startup dynamic issuance and getattr(None) unchanged')
        ca.body.remove(block)
    elif path.endswith('/test_operational_prefix_cli_v1.py'):
        fb, fa = function(before.body, 'test_execute_once_cli_real_worker_no_retry'), function(after.body, 'test_execute_once_cli_real_worker_no_retry')
        if [dump(node) for node in fa.body[:2]] != [dump(node) for node in reversed(fb.body[:2])]:
            raise ValueError('only the registered two adjacent import statements may swap')
        register(path, fa.body[0], 'registered CLI adjacent import order', [dump(node) for node in fb.body[:2]], [dump(node) for node in fa.body[:2]], 'only two import statements reverse; lazy/default and execute-once CPU cases validate import effects')
        fa.body[:2] = fb.body[:2]
    equal = dump(before) == dump(after)
    proof[path] = {'before_source_sha256': hash_text(before_text), 'after_source_sha256': hash_text(after_text), 'before_full_AST_sha256': hash_text(dump(before)), 'after_full_AST_sha256': hash_text(original_after_dump), 'restricted_after_AST_sha256': hash_text(dump(after)), 'restricted_AST_equal': equal, 'comments_equal': comments(before_text) == comments(after_text), 'whole_module_covered': True, 'type_comments': True, 'global_AST_sorting_or_assert_removal': False}
    if not equal or comments(before_text) != comments(after_text):
        raise ValueError('AST or comments differ outside registered changes: ' + path)
(out / 'restricted-ast-proof.json').write_text(json.dumps({'four_files': proof, 'registered_differences': registrations, 'all_equal': True}, indent=2) + '\n')
print(json.dumps({'all_four_restricted_AST_equal': True, 'registered_changes': len(registrations), 'comments_equal': all(p['comments_equal'] for p in proof.values())}))
