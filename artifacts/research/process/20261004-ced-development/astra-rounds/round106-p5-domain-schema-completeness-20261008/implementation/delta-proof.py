from pathlib import Path
from datetime import UTC, datetime
import ast
import hashlib
import io
import json
import tokenize

ROUND = Path("artifacts/research/process/20261004-ced-development/astra-rounds/round106-p5-domain-schema-completeness-20261008")
IMP = ROUND / "implementation"
PLAN = json.loads((ROUND / "plan.json").read_text())
SPEC = json.loads((IMP / "semantic-edit-spec.json").read_text())
checks = []

def parse(path):
    return ast.parse(path.read_text(), filename=str(path), type_comments=True)

def dump(node):
    return ast.dump(node, include_attributes=False)

def comments(path):
    return [t.string for t in tokenize.generate_tokens(io.StringIO(path.read_text()).readline) if t.type == tokenize.COMMENT]

def ignores(tree):
    result = []
    for ignore in tree.type_ignores:
        candidates = [n for n in ast.walk(tree) if isinstance(n, ast.stmt) and n.lineno <= ignore.lineno <= n.end_lineno]
        anchor = min(candidates, key=lambda n: n.end_lineno - n.lineno) if candidates else None
        result.append((ignore.tag, dump(anchor) if anchor else None))
    return result

for name in PLAN["scope"]["modified_paths"]:
    before = IMP / "source-before" / name
    semantic = IMP / "semantic-after" / name
    formatted = IMP / "format-after" / name
    expected = before.read_text()
    for old, new in SPEC[name]:
        assert expected.count(old) == 1
        expected = expected.replace(old, new)
    assert semantic.read_text() == expected, (name, "semantic delta exceeds exact specification")
    old_tree, new_tree = parse(before), parse(semantic)
    old_defs = {n.name:n for n in old_tree.body if isinstance(n, ast.FunctionDef)}
    new_defs = {n.name:n for n in new_tree.body if isinstance(n, ast.FunctionDef)}
    changed = [name for name in old_defs if dump(old_defs[name]) != dump(new_defs[name])]
    allowed = ["_validate_domain"] if Path(name).name == "operational_windows.py" else ["test_window_export_preserves_typed_boundary_constraints"]
    assert changed == allowed, (name, changed)
    checks.append({"path":name,"exact_semantic_delta":True,"changed_functions":changed})
    left, right = parse(semantic), parse(formatted)
    assert ignores(left) == ignores(right), (name, "TypeIgnore attachment")
    for tree in (left,right):
        for ignore in tree.type_ignores:
            ignore.lineno = 0
    assert dump(left) == dump(right), (name, "format AST/typecomments")
    assert comments(semantic) == comments(formatted)
    assert Path(name).read_bytes() == formatted.read_bytes()
    checks.append({"path":name,"format_AST_typecomments_ignores_comments_equal":True})

module = parse(IMP / "semantic-after/src/cloud_edge_robot_arm/vision/operational_windows.py")
function = next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name == "_validate_domain")
expected_fields = ast.literal_eval(function.body[0].value.args[1])
constant_node = next(n for n in function.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id == "constants" for t in n.targets))
constants = ast.literal_eval(constant_node.value)
oc1 = parse(Path("src/cloud_edge_robot_arm/research/operational_time_v1.py"))
domain = next(n for n in oc1.body if isinstance(n,ast.ClassDef) and n.name == "OperationalDomain")
fields = {n.target.id for n in domain.body if isinstance(n,ast.AnnAssign)}
assert expected_fields == fields and len(fields) == 27
for key,value in PLAN["required_constants"].items():
    assert constants[key] == value
checks.append({"native_domain_exact_keys":27,"three_restriction_constants_preserved":True})
for name in PLAN["scope"]["protected_p5_paths"] + PLAN["scope"]["oc1_and_test_protected"] + ["pyproject.toml"]:
    pin = next(x for x in PLAN["inputs"] if x["path"] == name)
    data = Path(name).read_bytes()
    assert len(data) == pin["bytes"] and hashlib.sha256(data).hexdigest() == pin["sha256"]
    checks.append({"path":name,"protected_byte_identity":True})

def nodes(path):
    result=[]
    for node in parse(path).body:
        if isinstance(node,ast.FunctionDef) and node.name.startswith("test_"):
            count=1
            for decorator in node.decorator_list:
                if isinstance(decorator,ast.Call) and isinstance(decorator.func,ast.Attribute) and decorator.func.attr == "parametrize":
                    count *= len(ast.literal_eval(decorator.args[1]))
            result.append((node.name,count,[dump(d) for d in node.decorator_list]))
    return result
name="tests/test_operational_windows.py"
before_nodes=nodes(IMP/"source-before"/name)
after_nodes=nodes(IMP/"format-after"/name)
assert before_nodes == after_nodes and sum(x[1] for x in after_nodes)==32
result={"status":"AUTHOR_R106_DELTA_PROOF_PASS","at_utc":datetime.now(UTC).isoformat(),"checks":checks,"P5_named_cases":32,"old_proofs_reused_not_run":True,"OC1_not_run":True,"limits":"Source/AST delta evidence only; P5 new32 execution and independent review still required."}
with (IMP/"delta-proof-result.json").open("x") as stream:
    json.dump(result,stream,indent=2)
    stream.write("\n")
print(json.dumps({"status":result["status"],"checks":len(checks),"native_domain_keys":27,"P5_named_cases":32}))
