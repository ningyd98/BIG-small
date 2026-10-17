from pathlib import Path
from datetime import datetime, UTC
from copy import deepcopy
import ast
import hashlib
import io
import json
import tokenize
import xml.etree.ElementTree as ET

ROUND = Path("artifacts/research/process/20261004-ced-development/astra-rounds/round110-p5-consumer-fixture-api-20261008")
IMP = ROUND / "implementation"
PLAN = json.loads((ROUND / "plan.json").read_text())
NAME = "tests/test_operational_windows.py"
BEFORE = IMP / "source-before" / NAME
SEMANTIC = IMP / "semantic-after" / NAME
FORMATTED = IMP / "format-after" / NAME

def parse(path):
    return ast.parse(path.read_text(), filename=str(path), type_comments=True)

def dump(node):
    return ast.dump(node, include_attributes=False)

def comments(path):
    return [t.string for t in tokenize.generate_tokens(io.StringIO(path.read_text()).readline) if t.type == tokenize.COMMENT]

def ignores(tree):
    rows = []
    for item in tree.type_ignores:
        candidates = [n for n in ast.walk(tree) if isinstance(n, ast.stmt) and n.lineno <= item.lineno <= n.end_lineno]
        anchor = min(candidates, key=lambda n: n.end_lineno - n.lineno) if candidates else None
        rows.append((item.tag, dump(anchor) if anchor else None))
    return rows

old, semantic, formatted = parse(BEFORE), parse(SEMANTIC), parse(FORMATTED)
assert ignores(semantic) == ignores(formatted)
for tree in (semantic, formatted):
    for item in tree.type_ignores:
        item.lineno = 0
assert dump(semantic) == dump(formatted)
assert comments(BEFORE) == comments(SEMANTIC) == comments(FORMATTED)
assert Path(NAME).read_bytes() == FORMATTED.read_bytes()

old_defs = {n.name: n for n in old.body if isinstance(n, ast.FunctionDef)}
new_defs = {n.name: n for n in formatted.body if isinstance(n, ast.FunctionDef)}
changed = {key for key in old_defs if dump(old_defs[key]) != dump(new_defs[key])}
assert set(old_defs) == set(new_defs)
assert changed == {"test_all_p5_categories_use_same_original_owner", "test_public_replay_descriptor_never_live_authority"}
restored = deepcopy(formatted)
defs = {n.name: n for n in restored.body if isinstance(n, ast.FunctionDef)}
marker = defs["test_all_p5_categories_use_same_original_owner"]
calls = [n for n in ast.walk(marker) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "associate_marker_target"]
assert len(calls) == 3
expected_now = dump(ast.parse("datetime.now(UTC)", mode="eval").body)
for call in calls:
    now = [k for k in call.keywords if k.arg == "now"]
    assert len(now) == 1 and dump(now[0].value) == expected_now
    call.keywords.remove(now[0])
assert dump(marker) == dump(old_defs[marker.name])
# The only two calls in the category else and one in the marker-only tail are
# the three original consumer sites; no other category/tail expression changed.
original_marker_calls = [n for n in ast.walk(old_defs[marker.name]) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "associate_marker_target"]
assert len(original_marker_calls) == 3 and all(not n.keywords for n in original_marker_calls)
replay = defs["test_public_replay_descriptor_never_live_authority"]
def assignment(function):
    return next(n for n in ast.walk(function) if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "legacy_arguments")
new_legacy = assignment(replay)
expected_legacy = ast.parse('{field.name: getattr(original.definition, field.name) for field in fields(original.definition) if field.init and field.name != "operational_windows"}', mode="eval").body
assert dump(new_legacy.value) == dump(expected_legacy)
new_legacy.value = deepcopy(assignment(old_defs[replay.name]).value)
assert dump(replay) == dump(old_defs[replay.name])
imports = [n for n in restored.body if isinstance(n, ast.ImportFrom) and n.module == "dataclasses"]
assert len(imports) == 1
assert [(n.name, n.asname) for n in imports[0].names] == [("fields", None), ("replace", None)]
imports[0].names = [n for n in imports[0].names if n.name != "fields"]
assert ignores(old) == ignores(restored)
for tree in (old, restored):
    for item in tree.type_ignores:
        item.lineno = 0
assert dump(old) == dump(restored), "Whole file restore must match including all old assertions, helpers and all unaffected branches"

def nodes(tree):
    rows = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            count = 1
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "parametrize":
                    count *= len(ast.literal_eval(decorator.args[1]))
            rows.append((node.name, count, [dump(d) for d in node.decorator_list]))
    return rows

assert nodes(old) == nodes(formatted) and sum(x[1] for x in nodes(formatted)) == 32
assert len([n for n in ast.walk(old) if isinstance(n, ast.Assert)]) == len([n for n in ast.walk(formatted) if isinstance(n, ast.Assert)])
protected = []
for pin in PLAN["frozen_delivery_inputs"]:
    if pin["path"] == NAME:
        continue
    data = Path(pin["path"]).read_bytes()
    assert len(data) == pin["bytes"] and hashlib.sha256(data).hexdigest() == pin["sha256"]
    protected.append({"path": pin["path"], "bytes": len(data), "sha256": pin["sha256"]})
legacy = [x for x in PLAN["inputs"] if "round102" in x["path"]]
assert len(legacy) == 2
for pin in legacy:
    data = Path(pin["path"]).read_bytes()
    assert len(data) == pin["bytes"] and hashlib.sha256(data).hexdigest() == pin["sha256"]
    protected.append({"path": pin["path"], "bytes": len(data), "sha256": pin["sha256"]})
prior = ROUND.parent / "round107-p5-boundary-fixture-recovery-20261008/implementation"
oc1 = json.loads((prior / "pre-GREEN-freeze.json").read_text())["OC1_result_reuse"]
for path, key in [
    ("src/cloud_edge_robot_arm/research/operational_time_v1.py", "source_sha256"),
    ("tests/test_operational_time_v1.py", "test_sha256"),
]:
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == oc1[key]
old_plan = json.loads((ROUND.parent / "round107-p5-boundary-fixture-recovery-20261008/plan.json").read_text())
config = next(x for x in old_plan["inputs"] if x["path"] == "pyproject.toml")
assert hashlib.sha256(Path(config["path"]).read_bytes()).hexdigest() == config["sha256"]
passed = []
failed = []
for node in ET.parse(prior / "green/junit.xml").getroot().iter("testcase"):
    nodeid = NAME + "::" + node.get("name")
    if node.find("failure") is None and node.find("error") is None and node.find("skipped") is None:
        passed.append(nodeid)
    else:
        failed.append(nodeid)
assert len(passed) == len(set(passed)) == 30
assert set(failed) == {x["nodeid"] for x in PLAN["failures"]}
reuse = {
    "status": "R107_30_PASS_APPLICABLE_BY_EXACT_DELTA_PROOF",
    "old_raw_JUnit": str(prior / "green/junit.xml"),
    "old_JUnit_sha256": hashlib.sha256((prior / "green/junit.xml").read_bytes()).hexdigest(),
    "reused_30_nodeids": passed,
    "new_2_required_nodeids": failed,
    "shared_helper_AST_unchanged": True,
    "other_test_nodes_and_all_six_other_category_branches_unchanged": True,
    "whole_module_after_exact_delta_undo_same": True,
    "nine_products_three_fixtures_two_legacy_pins_unchanged": protected,
    "OC1_prior_60": oc1,
    "denominator": "New2 plus applicable prior30, not new32 or new92",
}
with (IMP / "reuse-applicability.json").open("x") as f:
    json.dump(reuse, f, ensure_ascii=False, indent=2)
    f.write("\n")
result = {"status": "AUTHOR_R110_TEST_DELTA_PROOF_PASS", "at_utc": datetime.now(UTC).isoformat(), "three_exact_now_kwargs": True, "standard_fields_init_comprehension": True, "whole_file_AST_restores": True, "format_AST_typecomments_ignore_bindings_comments": True, "all_assertions_preserved": True, "original_named_cases": 32, "applicable_prior_nodeids": passed, "protected": protected, "product_imports": 0, "old_proofs_rerun": 0}
with (IMP / "delta-proof-result.json").open("x") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(json.dumps({"status": result["status"], "old_PASS_applicable": len(passed), "new_nodes": 2, "products_fixtures_protected": 12, "legacy_sources_protected": 2}))
