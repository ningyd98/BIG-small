from pathlib import Path
import ast
import hashlib
import io
import json
import tokenize
from datetime import UTC, datetime

ROOT = Path.cwd()
ROUND = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round103-p5-frozen-reference-codec-20261008/implementation"
BEFORE = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round102-p5-preflight-plan-shape-20261008/implementation/source-before"
FROZEN = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round102-p5-preflight-plan-shape-20261008/implementation/stop-final/source-freeze.json"
owned = [item["path"] for item in json.loads(FROZEN.read_text())["sources"]]
allowed = {
    "worker_runtime.py": {"VisualWorkerRuntime.__init__", "VisualWorkerRuntime.check_active", "VisualWorkerRuntime.initialize_supervision", "VisualWorkerRuntime._supervision_transition", "VisualWorkerRuntime.reserve_supervision_capture", "VisualWorkerRuntime.complete_supervision_capture", "VisualWorkerRuntime.reserve_supervision_plan", "VisualWorkerRuntime.complete_supervision_plan", "VisualWorkerRuntime.classify_supervision_reply", "VisualWorkerRuntime._transition", "VisualWorkerRuntime.reserve_capture", "VisualWorkerRuntime.complete_capture", "VisualWorkerRuntime.reserve_plan", "VisualWorkerRuntime.complete_plan", "VisualWorkerRuntime.route", "VisualWorkerRuntime.publish_grounding", "VisualWorkerRuntime.reserve_effect_capture"},
    "supervision.py": {"decide_supervision"},
    "marker_association.py": {"MarkerFrameContext.__post_init__", "MarkerFrameContext.digest", "marker_frame_context", "_associate"},
    "visual_bootstrap.py": {"VisualBootstrapDefinition.__post_init__", "VisualBootstrapDefinition.to_payload", "VisualBootstrapDefinition.from_payload", "VisualBootstrapTransitionInput.__init__", "VisualBootstrapTransitionInput.from_payload", "derive_bootstrap"},
    "visual_supervision.py": {"VisualSupervisionDefinition.__init__", "VisualSupervisionDefinition._validate", "VisualSupervisionTransitionInput.__init__", "VisualSupervisionTransitionInput._validate", "derive_supervision"},
    "models.py": {"VisualEvidence.__post_init__"},
    "conditions.py": {"_evaluate"},
    "worker.py": {"SimulationWorker.poll_once", "SimulationWorker._execute", "SimulationWorker._run_visual_closed_loop"},
}

def parse(path):
    return ast.parse(path.read_text(), filename=str(path), type_comments=True)

def dump(node):
    return ast.dump(node, include_attributes=False)

def functions(tree, prefix=""):
    result = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result[prefix + node.name] = node
        elif isinstance(node, ast.ClassDef):
            result.update(functions(node, prefix + node.name + "."))
    return result

def comments(path):
    return [token.string for token in tokenize.generate_tokens(io.StringIO(path.read_text()).readline) if token.type == tokenize.COMMENT]

def ignores(tree):
    statements = sorted((node for node in ast.walk(tree) if isinstance(node, ast.stmt)), key=lambda node: (node.lineno, -node.end_lineno))
    bindings = []
    for ignore in tree.type_ignores:
        candidates = [node for node in statements if node.lineno <= ignore.lineno <= node.end_lineno]
        anchor = min(candidates, key=lambda node: node.end_lineno - node.lineno) if candidates else None
        bindings.append((ignore.tag, dump(anchor) if anchor is not None else None))
    return bindings

checks = []
changed = {}
for name in owned:
    current = parse(ROOT / name)
    old_path = BEFORE / name
    if Path(name).name in {"operational_windows.py", "test_operational_windows.py"}:
        continue
    old = parse(old_path)
    old_functions, new_functions = functions(old), functions(current)
    modified = []
    for key, node in old_functions.items():
        assert key in new_functions, (name, "removed definition", key)
        if dump(node) != dump(new_functions[key]):
            assert key in allowed[Path(name).name], (name, "out-of-scope function", key)
            modified.append(key)
    changed[name] = modified
    checks.append({"path": name, "unchanged_nonowned_functions": len(old_functions) - len(modified), "modified_functions": modified})
    # Original repository writes, lease reads, source guards and pool/claim calls
    # retain their exact AST and their source-order subsequence in changed paths.
    protected = {"release_lease", "update_status_cas", "finish_attempt", "start_attempt", "_read_lease", "_validate_role_sources", "_raise_if_cancelled_or_timed_out", "transition_visual_bootstrap_if_current", "transition_visual_supervision_if_current", "route_visual_verification_if_current", "publish_visual_owner_if_current", "_owned_supervision_handle"}
    for key in modified:
        def calls(node):
            nodes = sorted((child for child in ast.walk(node) if isinstance(child, ast.Call)), key=lambda child: (child.lineno, child.col_offset))
            return [dump(child) for child in nodes if isinstance(child.func, ast.Attribute) and child.func.attr in protected]
        old_calls, new_calls = calls(old_functions[key]), iter(calls(new_functions[key]))
        for call in old_calls:
            assert any(candidate == call for candidate in new_calls), (name, key, "changed original guarded/write call")

for path in (ROUND / "semantic-before-hand-wrap").rglob("*.py"):
    relative = path.relative_to(ROUND / "semantic-before-hand-wrap")
    old, new = parse(path), parse(ROOT / relative)
    assert ignores(old) == ignores(new), (str(relative), "TypeIgnore bindings")
    for tree in (old, new):
        for ignore in tree.type_ignores:
            ignore.lineno = 0
    assert dump(old) == dump(new), (str(relative), "hand wrap AST changed")
    assert comments(path) == comments(ROOT / relative), (str(relative), "hand wrap comments changed")
    checks.append({"path": str(relative), "hand_wrap_AST_typecomments_comments_equivalent": True})

# R103 itself has only two semantic files; adapters retain the exact frozen AST
# (marker has separately attributed R101 hand wrapping).
r103 = json.loads((ROUND.parent / "plan.json").read_text())
for item in r103["author_final_source_freeze"]:
    if item["path"] in r103["allowed_R103_semantic_paths"]:
        continue
    before, after = parse(ROOT / item["snapshot"]), parse(ROOT / item["path"])
    assert dump(before) == dump(after), (item["path"], "non-R103 semantic drift")
    checks.append({"path": item["path"], "R103_semantics_unchanged": True})

tests = parse(ROOT / "tests/test_operational_windows.py")
nodes = []
for node in tests.body:
    if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
        continue
    count = 1
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "parametrize":
            values = ast.literal_eval(decorator.args[1])
            count *= len(values)
    nodes.append({"name": node.name, "cases": count})
assert sum(node["cases"] for node in nodes) == 32, nodes
assert len(nodes) == 21
module = (ROOT / "src/cloud_edge_robot_arm/vision/operational_windows.py").read_text()
assert "self._clock.within_age" in module and "self._clock.before_deadline" in module
assert "record.role != \"event\"" in module
assert "actual UTC lease/attempt veto" in module
worker = (ROOT / "src/cloud_edge_robot_arm/simulation_runtime/worker.py").read_text()
assert worker.index("operational_owner._begin_origin()") < worker.index("self._active_task_origin = (")
assert "with _worker_scope(self):" in worker
assert "_new_handoff(self, runtime_source, verification_limits)" in worker
assert "_operational_handoff=operational_handoff" in worker
sources = []
for name in owned:
    data = (ROOT / name).read_bytes()
    target = ROUND / "source-after" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)
    sources.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "snapshot": str(target.relative_to(ROOT))})
result = {"status": "AUTHOR_SCOPE_PROOF_PASS", "at_utc": datetime.now(UTC).isoformat(), "checks": checks, "changed_functions": changed, "test_nodes": nodes, "P5_cases": 32, "sources": sources, "limits": "AST/source-preservation proof, not product runtime success or independent review. Typed semantics and genuine consumer paths still need the original GREEN command."}
with (ROUND / "scope-proof-result.json").open("x") as stream:
    json.dump(result, stream, indent=2)
    stream.write("\n")
print(json.dumps({"status": result["status"], "checks": len(checks), "P5_cases": 32}))
