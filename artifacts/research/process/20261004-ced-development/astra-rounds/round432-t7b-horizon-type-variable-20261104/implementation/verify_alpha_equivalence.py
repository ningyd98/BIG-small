"""Prove the sole permitted R432 five-Name alpha rename against frozen R431."""
import ast
import copy
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
ROUND = Path(__file__).resolve().parents[1]
plan = json.loads((ROUND / 'plan.json').read_text())
old_path = ROOT / plan['ast_proof']['frozen_source']
new_path = ROOT / plan['allowed_source_modifications'][0]
old_text, new_text = old_path.read_text(), new_path.read_text()
old, new = ast.parse(old_text), ast.parse(new_text)

def only(items):
    assert len(items) == 1, len(items)
    return items[0]

def target(tree):
    cls = only([n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == '_Audit'])
    fn = only([n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'legacy_time'])
    outer = only([n for n in fn.body if isinstance(n, ast.For)
                  and ast.dump(n.target) == ast.dump(ast.Name(id='interval', ctx=ast.Store()))
                  and ast.dump(n.iter) == ast.dump(ast.parse('self.raw["legacy_intervals"]', mode='eval').body)])
    inner = only([n for n in outer.body if isinstance(n, ast.For)
                  and isinstance(n.target, ast.Name) and n.target.id == 'key'
                  and ast.dump(n.iter) == ast.dump(ast.parse('("start", "end")', mode='eval').body)])
    return fn, inner

old_fn, old_inner = target(old)
new_fn, new_inner = target(new)
old_names = [n for n in ast.walk(old_inner) if isinstance(n, ast.Name) and n.id == 'pair']
new_names = [n for n in ast.walk(new_inner) if isinstance(n, ast.Name) and n.id == 'interval_pair']
assert len(old_names) == len(new_names) == 5
assert sorted(type(n.ctx).__name__ for n in old_names) == ['Load'] * 4 + ['Store']
assert sorted(type(n.ctx).__name__ for n in new_names) == ['Load'] * 4 + ['Store']
assert not any(isinstance(n, ast.Name) and n.id == 'interval_pair' for n in ast.walk(old_fn))
assert not any(isinstance(n, ast.Name) and n.id == 'pair' for n in ast.walk(new_inner))
old_ids, new_ids = {id(n) for n in ast.walk(old_inner)}, {id(n) for n in ast.walk(new_inner)}
old_out = [ast.dump(n) for n in ast.walk(old_fn) if isinstance(n, ast.Name) and n.id == 'pair' and id(n) not in old_ids]
new_out = [ast.dump(n) for n in ast.walk(new_fn) if isinstance(n, ast.Name) and n.id == 'pair' and id(n) not in new_ids]
assert old_out == new_out and len(old_out) == 10
assert not any(isinstance(n, ast.Name) and n.id == 'interval_pair' and id(n) not in new_ids for n in ast.walk(new_fn))
normalized = copy.deepcopy(new)
_, normalized_inner = target(normalized)
for node in ast.walk(normalized_inner):
    if isinstance(node, ast.Name) and node.id == 'interval_pair':
        node.id = 'pair'
old_dump, normalized_dump = ast.dump(old, include_attributes=False), ast.dump(normalized, include_attributes=False)
assert old_dump == normalized_dump
unchanged = []
for pin in plan['input_pins']:
    if pin['path'] in ('tests/test_native_completion_horizon_originals_v1.py', 'tests/test_native_completion_horizon_v1.py', 'src/cloud_edge_robot_arm/vision/native_completion_horizon.py'):
        assert hashlib.sha256((ROOT / pin['path']).read_bytes()).hexdigest() == pin['sha256']
        unchanged.append(pin)
assert len(unchanged) == 3
result = dict(old_sha256=hashlib.sha256(old_path.read_bytes()).hexdigest(), new_sha256=hashlib.sha256(new_path.read_bytes()).hexdigest(), frozen_source=str(old_path.relative_to(ROOT)), selector=plan['ast_proof']['selector'], rename_count=5, contexts={'Store':1,'Load':4}, outside_pair_count=10, outside_unchanged=True, whole_module_ast_equal=True, normalized_ast_sha256=hashlib.sha256(old_dump.encode()).hexdigest(), unchanged_files=unchanged)
(ROUND / 'validation/alpha-equivalence.json').write_text(json.dumps(result,indent=2)+'\n')
(ROUND / 'implementation/allowed-source-diff.patch').write_text(''.join(difflib.unified_diff(old_text.splitlines(True),new_text.splitlines(True),fromfile=str(old_path.relative_to(ROOT)),tofile=str(new_path.relative_to(ROOT)))))
print(json.dumps({k:v for k,v in result.items() if k!='unchanged_files'},indent=2))
