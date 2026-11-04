"""Administrative scope proof; does not execute product code."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[7]
ROUND = Path(__file__).resolve().parents[1]
reader = 'src/cloud_edge_robot_arm/research/native_completion_horizon_originals.py'
test = 'tests/test_native_completion_horizon_originals_v1.py'
old_reader = (ROUND / 'intake/source-originals' / reader).read_text()
new_reader = (ROOT / reader).read_text()
def method(text):
    tree = ast.parse(text)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == '_Audit')
    return next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'retain_failures')
a, b = method(old_reader), method(new_reader)
old_lines, new_lines = old_reader.splitlines(True), new_reader.splitlines(True)
assert old_lines[:a.lineno] == new_lines[:b.lineno]
assert old_lines[a.end_lineno:] == new_lines[b.end_lineno:]
old_test = (ROUND / 'intake/source-originals' / test).read_text()
new_test = (ROOT / test).read_text()
prefix, suffix = old_test.split('def rebuild_clock_tee(raw):', 1)
assert new_test.startswith(prefix) and new_test.endswith('def rebuild_clock_tee(raw):' + suffix)
old_ast, new_ast = ast.parse(old_test), ast.parse(new_test)
added = [n for n in new_ast.body if isinstance(n, ast.FunctionDef) and n.name == 'test_malformed_result_does_not_hide_later_original_failure']
assert len(added) == 1
new_ast.body.remove(added[0])
assert ast.dump(old_ast, include_attributes=False) == ast.dump(new_ast, include_attributes=False)
red = json.loads((ROUND / 'implementation/pre-red-source-pins.json').read_text())
assert hashlib.sha256((ROOT / test).read_bytes()).hexdigest() == next(p['sha256'] for p in red['files'] if p['path']==test)
unchanged = []
for name in ['src/cloud_edge_robot_arm/vision/native_completion_horizon.py', 'tests/test_native_completion_horizon_v1.py']:
    assert (ROOT / name).read_bytes() == (ROUND / 'intake/source-originals' / name).read_bytes()
    unchanged.append(name)
proof = dict(reader_change_only_method_body=True, test_only_new_function=True, test_bytes_unchanged_since_red=True, other_two_files_unchanged=unchanged)
(ROUND / 'validation/scope-proof.json').write_text(json.dumps(proof, indent=2)+'\n')
patch = ''.join(difflib.unified_diff(old_reader.splitlines(True),new_reader.splitlines(True),fromfile='R432/'+reader,tofile=reader))
patch += ''.join(difflib.unified_diff(old_test.splitlines(True),new_test.splitlines(True),fromfile='R431/'+test,tofile=test))
(ROUND / 'implementation/allowed-source-diff.patch').write_text(patch)
pins=[]
for name in (reader,test):
    raw=(ROOT/name).read_bytes()
    target=ROUND/'implementation/pre-green-source-originals'/name
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as f:f.write(raw)
    pins.append(dict(path=name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
(ROUND/'implementation/pre-green-source-pins.json').write_text(json.dumps({'files':pins},indent=2)+'\n')
print(json.dumps(proof))
