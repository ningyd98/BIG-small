from pathlib import Path
from datetime import UTC, datetime
import ast
import copy
import hashlib
import io
import json
import tokenize

ROUND = Path("artifacts/research/process/20261004-ced-development/astra-rounds/round105-p5-static-fixture-recovery-20261008")
IMP = ROUND / "implementation"
PLAN = json.loads((ROUND / "plan.json").read_text())
SPEC = json.loads((IMP / "manual-edit-spec.json").read_text())
checks = []

def parse(path):
    return ast.parse(path.read_text(), filename=str(path), type_comments=True)

def dump(tree):
    return ast.dump(tree, include_attributes=False)

def comments(path):
    return [t.string for t in tokenize.generate_tokens(io.StringIO(path.read_text()).readline) if t.type == tokenize.COMMENT]

def type_ignore_bindings(tree):
    statements = [n for n in ast.walk(tree) if isinstance(n, ast.stmt)]
    result = []
    for ignore in tree.type_ignores:
        candidates = [n for n in statements if n.lineno <= ignore.lineno <= n.end_lineno]
        anchor = min(candidates, key=lambda n: n.end_lineno - n.lineno) if candidates else None
        result.append((ignore.tag, dump(anchor) if anchor else None))
    return result

class ImportBlocks(ast.NodeTransformer):
    """Canonicalize only contiguous import blocks; never move between scopes."""
    def generic_visit(self, node):
        super().generic_visit(node)
        for field, value in ast.iter_fields(node):
            if not isinstance(value, list):
                continue
            result = []
            block = []
            def flush():
                if block:
                    expanded = []
                    for item in block:
                        for alias in item.names:
                            if isinstance(item, ast.Import):
                                expanded.append(ast.Import(names=[copy.deepcopy(alias)]))
                            else:
                                expanded.append(ast.ImportFrom(module=item.module, level=item.level, names=[copy.deepcopy(alias)]))
                    result.extend(sorted(expanded, key=dump))
                    block.clear()
            for item in value:
                if isinstance(item, (ast.Import, ast.ImportFrom)):
                    block.append(item)
                else:
                    flush()
                    result.append(item)
            flush()
            setattr(node, field, result)
        return node

for name in PLAN["scope"]["modified_paths"]:
    before = IMP / "source-before" / name
    manual = IMP / "manual-after" / name
    expected = before.read_text()
    for old, new, count in SPEC[name]:
        if count is not None:
            assert expected.count(old) == count, (name, "literal exact occurrence")
        expected = expected.replace(old, new)
    assert manual.read_text() == expected, (name, "manual delta beyond exact spec")
    checks.append({"path": name, "exact_manual_byte_delta": True, "edits": len(SPEC[name])})
    sorted_path = IMP / "import-sort-after" / name
    manual_tree, sorted_tree = parse(manual), parse(sorted_path)
    assert dump(ImportBlocks().visit(copy.deepcopy(manual_tree))) == dump(ImportBlocks().visit(copy.deepcopy(sorted_tree))), (name, "import inventory/scope/non-import semantics changed")
    assert comments(manual) == comments(sorted_path), (name, "import-sort comments")
    checks.append({"path": name, "imports_inventory_conserved_per_contiguous_scope_block": True})
    formatted = IMP / "format-after" / name
    left, right = parse(sorted_path), parse(formatted)
    assert type_ignore_bindings(left) == type_ignore_bindings(right), (name, "TypeIgnore attachment")
    for tree in (left, right):
        for ignore in tree.type_ignores:
            ignore.lineno = 0
    assert dump(left) == dump(right), (name, "format AST/typecomments")
    assert comments(sorted_path) == comments(formatted), (name, "format comments")
    assert Path(name).read_bytes() == formatted.read_bytes(), (name, "current does not match final stage")
    checks.append({"path": name, "format_AST_typecomments_comments_identical": True})

for name in PLAN["scope"]["protected_original_six"] + [PLAN["scope"]["oc1_read_only"]]:
    pin = next(x for x in PLAN["inputs"] if x["path"] == name)
    data = Path(name).read_bytes()
    assert len(data) == pin["bytes"] and hashlib.sha256(data).hexdigest() == pin["sha256"], (name, "protected byte drift")
    checks.append({"path": name, "protected_byte_identity": True})

# Preserve exact parameterized node definitions: no product import/collect/test.
name = "tests/test_operational_windows.py"
def nodes(tree):
    result = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            count = 1
            decorators = []
            for decorator in node.decorator_list:
                decorators.append(dump(decorator))
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "parametrize":
                    count *= len(ast.literal_eval(decorator.args[1]))
            result.append((node.name, count, decorators))
    return result
before_nodes = nodes(parse(IMP / "source-before" / name))
after_nodes = nodes(parse(IMP / "format-after" / name))
assert before_nodes == after_nodes and sum(x[1] for x in after_nodes) == 32
manual_test = (IMP / "manual-after" / name).read_text()
assert "counter.close_call_count += 1\n            original()" in manual_test
assert "assert clocks and counter.close_call_count == 1" in manual_test
assert "assert clocks[0]._closed" in manual_test
assert "raw.now = 0\n        assert owner.check(window, after=token).status == \"UNKNOWN\"\n        assert owner._clock._closed" in manual_test
start = manual_test.index("def test_all_p5_categories_use_same_original_owner")
end = manual_test.index("def test_public_replay_descriptor_never_live_authority")
category = manual_test[start:end]
assert "raw.now = 5_000_000_001" not in category
assert category.index("raw.now = 5_000_000_000") < category.index("raw.now += 1") < category.index('if category == "marker":')
checks.append({"P5_cases":32,"same_named_nodes_and_parametrizations":True,"cleanup_no_revival_marker_monotonic_source_assertions":True})
result = {"status":"AUTHOR_R105_DELTA_PROOF_PASS","at_utc":datetime.now(UTC).isoformat(),"checks":checks,"nodes":after_nodes,"old_scope_proof_reused_not_run":str(ROUND.parent / "round103-p5-frozen-reference-codec-20261008/implementation/scope-proof/command-result.json"),"limits":"Finite AST/source delta only; remaining product GREEN and independent review still required."}
with (IMP / "delta-proof-result.json").open("x") as stream:
    json.dump(result, stream, indent=2)
    stream.write("\n")
print(json.dumps({"status":result["status"],"checks":len(checks),"P5_cases":32}))
