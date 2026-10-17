from pathlib import Path
from datetime import UTC, datetime
import ast
import collections
import gzip
import hashlib
import io
import json
import tokenize

ROUND = Path("artifacts/research/process/20261004-ced-development/astra-rounds/round107-p5-boundary-fixture-recovery-20261008")
IMP = ROUND / "implementation"
PLAN = json.loads((ROUND / "plan.json").read_text())
SPEC = json.loads((IMP / "semantic-edit-spec.json").read_text())
FIXTURE = json.loads((ROUND / "fixture-spec.json").read_text())
checks = []

def parse(path):
    return ast.parse(path.read_text(), filename=str(path), type_comments=True)

def dump(node):
    return ast.dump(node, include_attributes=False)

def comments(path):
    return [t.string for t in tokenize.generate_tokens(io.StringIO(path.read_text()).readline) if t.type == tokenize.COMMENT]

def ignores(tree):
    result = []
    for item in tree.type_ignores:
        candidates = [n for n in ast.walk(tree) if isinstance(n, ast.stmt) and n.lineno <= item.lineno <= n.end_lineno]
        anchor = min(candidates, key=lambda n: n.end_lineno - n.lineno) if candidates else None
        result.append((item.tag, dump(anchor) if anchor else None))
    return result

def inventory(tree):
    return collections.Counter(dump(n) for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)))

def without_imports(tree):
    class Remove(ast.NodeTransformer):
        def visit_Import(self, node):
            return None
        def visit_ImportFrom(self, node):
            return None
    return Remove().visit(tree)

def definitions(tree):
    result = {}
    def walk(body, prefix=""):
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                key = prefix + n.name
                result[key] = n
                if isinstance(n, ast.ClassDef):
                    walk(n.body, key + ".")
    walk(tree.body)
    return result

for name in PLAN["scope"]["modified_python"]:
    before = IMP / "source-before" / name
    semantic = IMP / "semantic-after" / name
    imported = IMP / "import-after" / name
    formatted = IMP / "format-after" / name
    expected = before.read_text()
    for replacement in SPEC[name]:
        count = replacement.get("count", 1)
        assert expected.count(replacement["old"]) == count, (name, "exact replacement count")
        expected = expected.replace(replacement["old"], replacement["new"], count)
    assert semantic.read_text() == expected, (name, "unlisted semantic bytes")
    old_tree, new_tree = parse(before), parse(semantic)
    old_defs, new_defs = definitions(old_tree), definitions(new_tree)
    changed = {key for key in old_defs if dump(old_defs[key]) != dump(new_defs[key])}
    new = set(new_defs) - set(old_defs)
    if Path(name).name == "operational_windows.py":
        assert changed == {"OperationalWindowOwner", "OperationalWindowOwner.from_worker"} and not new
        old_method = old_defs["OperationalWindowOwner.from_worker"]
        method = new_defs["OperationalWindowOwner.from_worker"]
        assert dump(old_method.args) == dump(method.args)
        assert all(dump(a) == dump(b) for a, b in zip(old_method.body[1:], method.body[3:], strict=True))
        assert isinstance(method.body[0], ast.ImportFrom)
        assert method.body[0].module == "cloud_edge_robot_arm.simulation_runtime.worker"
        assert isinstance(method.body[1], ast.If) and isinstance(method.body[2], ast.If)
        assert ast.unparse(method.body[2].test) == "worker not in _PENDING"
    elif Path(name).name == "visual_bootstrap.py":
        assert changed == {"VisualBootstrapDefinition", "VisualBootstrapDefinition.from_payload"} and not new
        method = new_defs["VisualBootstrapDefinition.from_payload"]
        assert ast.unparse(method.body[0]) == "normalized = _plain(raw)"
        assert ast.unparse(method.body[1]) == "body = dict(normalized)"
        assert "canonical(normalized)" in ast.unparse(method)
    else:
        assert changed == {
            "test_utc_jump_is_diagnostic_only_for_supported_local_domain",
            "test_public_worker_or_source_without_startup_capability_cannot_issue",
            "test_all_p5_categories_use_same_original_owner",
        }
        assert new == {"marker_cpu_inputs", "supervision_cpu_utc"}
        assert comments(before) == comments(semantic)
        helper = new_defs["supervision_cpu_utc"]
        calls = [n for n in ast.walk(helper) if isinstance(n, ast.Call)]
        assert sum(ast.unparse(n.func) == "datetime.now" for n in calls) == 1
        assert sum(ast.unparse(n.func) == "monkeypatch.context" for n in calls) == 1
        setter = [n for n in calls if ast.unparse(n.func) == "local.setattr"]
        assert len(setter) == 1 and ast.literal_eval(setter[0].args[1]) == "datetime"
        patched = next(n for n in ast.walk(helper) if isinstance(n, ast.For))
        assert ast.literal_eval(patched.iter) == (
            "cloud_edge_robot_arm.vision.worker_owner",
            "cloud_edge_robot_arm.vision.worker_runtime",
            "cloud_edge_robot_arm.repositories.event_autonomy.sqlite",
        )
        usages = [n for n in ast.walk(new_tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "supervision_cpu_utc"]
        assert len(usages) == 1
        category = new_defs["test_all_p5_categories_use_same_original_owner"]
        branch = next(n for n in ast.walk(category) if isinstance(n, ast.If) and ast.unparse(n.test) == "category == 'supervision'")
        with_node = next(n for n in branch.body if isinstance(n, ast.With))
        assert ast.unparse(with_node.items[0].context_expr) == "supervision_cpu_utc(monkeypatch, runtime, claim)"
        assert "maximum_age_s=5" in ast.unparse(with_node) and "maximum_age_s=6" in ast.unparse(with_node)
        assert "complete_supervision_plan" in ast.unparse(with_node)
        assert len([n for n in ast.walk(new_tree) if isinstance(n, ast.Assert)]) >= len([n for n in ast.walk(old_tree) if isinstance(n, ast.Assert)])
    checks.append({"path": name, "exact_semantic_byte_spec": True, "changed_definitions": sorted(changed), "new_definitions": sorted(new)})
    left, right = parse(semantic), parse(imported)
    assert inventory(left) == inventory(right)
    assert ignores(left) == ignores(right)
    for tree in (left, right):
        for item in tree.type_ignores:
            item.lineno = 0
    assert dump(without_imports(left)) == dump(without_imports(right))
    assert comments(semantic) == comments(imported)
    left, right = parse(imported), parse(formatted)
    assert ignores(left) == ignores(right)
    for tree in (left, right):
        for item in tree.type_ignores:
            item.lineno = 0
    assert dump(left) == dump(right)
    assert comments(imported) == comments(formatted)
    assert Path(name).read_bytes() == formatted.read_bytes()
    checks.append({"path": name, "I_only_inventory_and_remaining_AST": True, "format_AST_typecomments_ignore_attachment_comments": True})

for name in PLAN["scope"]["protected_p5_paths"] + [
    "src/cloud_edge_robot_arm/research/operational_time_v1.py",
    "tests/test_operational_time_v1.py",
    "pyproject.toml",
    "configs/research/ced_marker_registration_v1.yaml",
] + list(FIXTURE["registration_payload"]["registration_source_hashes"]):
    pin = next(x for x in PLAN["inputs"] if x["path"] == name)
    data = Path(name).read_bytes()
    assert len(data) == pin["bytes"] and hashlib.sha256(data).hexdigest() == pin["sha256"]
    checks.append({"path": name, "protected_byte_identity": True})

for row in FIXTURE["expected_outputs"]:
    data = Path(row["path"]).read_bytes()
    assert len(data) == row["bytes"] and hashlib.sha256(data).hexdigest() == row["sha256"]
    checks.append({"path": row["path"], "exact_fixture_bytes_and_SHA": True})
for path, payload in [
    (FIXTURE["fixture_paths"][1], FIXTURE["registration_payload"]),
    (FIXTURE["fixture_paths"][2], FIXTURE["provenance_payload"]),
]:
    assert Path(path).read_bytes() == (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
original = Path(FIXTURE["provenance_payload"]["original_frame"]["path"]).read_bytes()
original_pin = FIXTURE["provenance_payload"]["original_frame"]
assert len(original) == original_pin["bytes"] and hashlib.sha256(original).hexdigest() == original_pin["sha256"]
compressed = Path(FIXTURE["fixture_paths"][0]).read_bytes()
assert gzip.decompress(compressed) == original
assert gzip.compress(original, mtime=0) == compressed
marker = definitions(parse(IMP / "format-after/tests/test_operational_windows.py"))["marker_cpu_inputs"]
registry_call = next(n for n in ast.walk(marker) if isinstance(n, ast.Call) and ast.unparse(n.func) == "module.load_marker_registration")
registry_expected = next(k.value for k in registry_call.keywords if k.arg == "expected_registry_sha256")
assert ast.literal_eval(registry_expected) == FIXTURE["expected_outputs"][1]["sha256"]
checks.append({"gzip_decompressed_original_bytes": True, "original_frame_unchanged": True, "helper_registry_expected_is_frozen_spec": True})

def nodes(path):
    result = []
    for n in parse(path).body:
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test_"):
            count = 1
            for decorator in n.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "parametrize":
                    count *= len(ast.literal_eval(decorator.args[1]))
            result.append((n.name, count, [dump(d) for d in n.decorator_list]))
    return result

before_nodes = nodes(IMP / "source-before/tests/test_operational_windows.py")
after_nodes = nodes(IMP / "format-after/tests/test_operational_windows.py")
assert before_nodes == after_nodes and sum(x[1] for x in after_nodes) == 32
result = {
    "status": "AUTHOR_R107_DELTA_FIXTURE_PROOF_PASS",
    "at_utc": datetime.now(UTC).isoformat(),
    "checks": checks,
    "P5_named_cases": 32,
    "no_product_import": True,
    "old_proofs_not_rerun": True,
    "boundary": "Source/fixture proof only; SOFTWARE CPU UTC fixture does not prove actual timing or admission.",
}
with (IMP / "delta-proof-result.json").open("x") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
print(json.dumps({"status": result["status"], "checks": len(checks), "P5_named_cases": 32}))
