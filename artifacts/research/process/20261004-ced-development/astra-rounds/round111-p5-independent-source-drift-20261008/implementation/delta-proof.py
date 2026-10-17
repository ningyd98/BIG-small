from pathlib import Path
from datetime import datetime, UTC
from copy import deepcopy
import ast
import hashlib
import io
import json
import tokenize
import xml.etree.ElementTree as ET

ROUND = Path("artifacts/research/process/20261004-ced-development/astra-rounds/round111-p5-independent-source-drift-20261008")
IMP = ROUND / "implementation"
PLAN = json.loads((ROUND / "plan.json").read_text())
NAME = "tests/test_operational_windows.py"
TARGET = "test_source_and_budget_changes_invalidate_window"
PRIOR = ROUND.parent / "round110-p5-consumer-fixture-api-20261008/implementation"

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

old = parse(IMP / "source-before" / NAME)
semantic = parse(IMP / "semantic-after" / NAME)
formatted = parse(IMP / "format-after" / NAME)
assert ignores(semantic) == ignores(formatted)
for tree in (semantic, formatted):
    for item in tree.type_ignores:
        item.lineno = 0
assert dump(semantic) == dump(formatted)
assert comments(IMP / "source-before" / NAME) == comments(IMP / "semantic-after" / NAME) == comments(IMP / "format-after" / NAME)
assert Path(NAME).read_bytes() == (IMP / "format-after" / NAME).read_bytes()
old_defs = {n.name: n for n in old.body if isinstance(n, ast.FunctionDef)}
new_defs = {n.name: n for n in formatted.body if isinstance(n, ast.FunctionDef)}
assert set(old_defs) == set(new_defs)
assert {key for key in old_defs if dump(old_defs[key]) != dump(new_defs[key])} == {TARGET}
restored = deepcopy(formatted)
restored.body = [deepcopy(old_defs[TARGET]) if isinstance(n, ast.FunctionDef) and n.name == TARGET else n for n in restored.body]
assert ignores(old) == ignores(restored)
for tree in (old, restored):
    for item in tree.type_ignores:
        item.lineno = 0
assert dump(old) == dump(restored), "Every other helper, class, import, assertion, decorator and test body must remain exact"

node = new_defs[TARGET]
loop = next(n for n in node.body if isinstance(n, ast.For))
assert ast.literal_eval(loop.iter) == ("budget", "source")
assert ast.unparse(loop.target) == "mutation"
assert ast.unparse(loop.body[0]) == "case_root = tmp_path / mutation"
assert ast.unparse(loop.body[1]) == "case_root.mkdir()"
context = loop.body[2]
assert isinstance(context, ast.With)
assert ast.unparse(context.items[0].context_expr) == "monkeypatch.context()"
assert ast.unparse(context.items[0].optional_vars) == "local_patch"
callback = next(n for n in context.body if isinstance(n, ast.FunctionDef))
assert callback.name == "run"
assert [n.arg for n in callback.args.args] == ["module", "runtime", "raw", "worker", "repo", "job", "mutation"]
assert [ast.unparse(n) for n in callback.args.defaults] == ["mutation"]
callback_text = ast.unparse(callback)
assert "nonce = owner.clock.domain.startup_nonce" in callback_text
assert "owners.append(owner)" in callback_text and "nonces.append(nonce)" in callback_text
assert "repositories.append(Path(repo.database_path))" in callback_text
assert "baseline = owner.check(window, after=token).status" in callback_text
expected_baseline = dump(ast.parse("assert baseline == 'VALID' and not owner._closed").body[0])
assert any(isinstance(n, ast.Assert) and dump(n) == expected_baseline for n in callback.body)
assert "expected_sha = runtime.source.source_hashes['device.py']" in callback_text
assert "assert hashlib.sha256(original).hexdigest() == expected_sha" in callback_text
assert "assert raw.now == original_counter" in callback_text
assert not any(isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign)) and "_closed" in ast.unparse(n) for n in ast.walk(callback))
branch = next(n for n in callback.body if isinstance(n, ast.If))
assert ast.unparse(branch.test) == "mutation == 'budget'"
budget_try = branch.body[0]
assert isinstance(budget_try, ast.Try) and not budget_try.handlers
assert len(budget_try.finalbody) == 1 and isinstance(budget_try.finalbody[0], ast.With)
budget_text = ast.unparse(budget_try)
assert "(original_timeout + 1, job.job_id)" in budget_text
assert "(original_timeout, job.job_id)" in ast.unparse(budget_try.finalbody[0])
assert "UPDATE simulation_jobs SET timeout_seconds=? WHERE job_id=?" in budget_text
assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "write_bytes" for n in ast.walk(budget_try))
source_try = next(n for n in branch.orelse if isinstance(n, ast.Try))
assert not source_try.handlers
assert "path.write_bytes(original + b'# drift\\n')" in ast.unparse(source_try)
assert "assert changed_sha != expected_sha" in ast.unparse(source_try)
assert ast.unparse(source_try.finalbody[0]) == "path.write_bytes(original)"
assert ast.unparse(source_try.finalbody[1]) == "assert path.read_bytes() == original"
assert not any(isinstance(n, ast.Call) and ast.unparse(n.func) == "sqlite3.connect" for n in ast.walk(source_try))
assert "assert repo.get_job(job.job_id).timeout_seconds == original_timeout" in callback_text
for trial in (budget_try, source_try):
    before_check = next(i for i, n in enumerate(trial.body) if isinstance(n, ast.Assign) and ast.unparse(n).startswith("rejected = owner.check("))
    assert ast.unparse(trial.body[before_check - 1]) == "assert not owner._closed"
    assert ast.unparse(trial.body[before_check + 1]) == "assert rejected == 'UNKNOWN'"
assert "exercise(local_patch, case_root, run)" in ast.unparse(context)
assert "assert counter.close_call_count == 1" in ast.unparse(context)
assert "assert owners[-1]._closed" in ast.unparse(context)
tail = "\n".join(ast.unparse(n) for n in node.body[2:])
assert "assert owners[0] is not owners[1]" in tail
assert "assert nonces[0] != nonces[1]" in tail
assert "assert repositories[0] != repositories[1]" in tail
assert "drift-case-result.json" in ast.unparse(context) and "case-pair.json" in tail

def nodes(tree):
    result = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test_"):
            count = 1
            for decorator in n.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "parametrize":
                    count *= len(ast.literal_eval(decorator.args[1]))
            result.append((n.name, count, [dump(d) for d in n.decorator_list]))
    return result

assert nodes(old) == nodes(formatted) and sum(x[1] for x in nodes(formatted)) == 32
protected = []
for row in PLAN["frozen_delivery_inputs"]:
    if row["path"] == NAME:
        continue
    data = Path(row["path"]).read_bytes()
    assert len(data) == row["bytes"] and hashlib.sha256(data).hexdigest() == row["sha256"]
    protected.append(row)
legacy = json.loads((PRIOR / "explicit-paths.json").read_text())["required_legacy_codec_test_dependency_paths"]
for row in legacy:
    data = Path(row["path"]).read_bytes()
    assert len(data) == row["bytes"] and hashlib.sha256(data).hexdigest() == row["sha256"]
prior_reuse = json.loads((PRIOR / "reuse-applicability.json").read_text())
oc1 = prior_reuse["OC1_prior_60"]
for path, key in [("src/cloud_edge_robot_arm/research/operational_time_v1.py", "source_sha256"), ("tests/test_operational_time_v1.py", "test_sha256")]:
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == oc1[key]
original_plan = json.loads((ROUND.parent / "round107-p5-boundary-fixture-recovery-20261008/plan.json").read_text())
config = next(x for x in original_plan["inputs"] if x["path"] == "pyproject.toml")
assert hashlib.sha256(Path(config["path"]).read_bytes()).hexdigest() == config["sha256"]
old29 = [x for x in prior_reuse["reused_30_nodeids"] if x != NAME + "::" + TARGET]
assert len(old29) == 29
old2 = []
for c in ET.parse(PRIOR / "green/junit.xml").getroot().iter("testcase"):
    assert c.find("failure") is None and c.find("error") is None and c.find("skipped") is None
    old2.append(NAME + "::" + c.get("name"))
assert len(old2) == 2 and len(set(old29 + old2)) == 31
reuse = {"status": "PRIOR31_APPLICABLE_BY_SINGLE_NODE_DELTA_PROOF", "R107_prior29_nodeids": old29, "R110_prior2_nodeids": old2, "combined_prior31_nodeids": old29 + old2, "prior_C1_PASS_preserved_but_not_reused": NAME + "::" + TARGET, "shared_helpers_other_nodes_AST_exact": True, "protected_product_fixture_count": len(protected), "protected": protected, "legacy_sources": legacy, "OC1_prior60": oc1, "claim": "New1 node with2 independent lifecycles plus prior31, never new32/92"}
with (IMP / "reuse-applicability.json").open("x") as f:
    json.dump(reuse, f, ensure_ascii=False, indent=2)
    f.write("\n")
result = {"status": "AUTHOR_R111_SINGLE_NODE_DELTA_PROOF_PASS", "at_utc": datetime.now(UTC).isoformat(), "single_changed_definition": TARGET, "all_other_AST_exact": True, "named_cases": 32, "two_fresh_case_roots_and_patch_contexts": True, "baseline_before_single_mutation": True, "check_not_closed_before_each_mutation_check": True, "SQL_only_budget_file_only_source": True, "try_finally_exact_restore": True, "distinct_owner_nonce_repository_assertions": True, "format_AST_typecomments_ignores_comments": True, "old31_applicability_nodeids": old29 + old2, "limits": "Source proof only; unique1 GREEN and actual2 lifecycle artifacts still required"}
with (IMP / "delta-proof-result.json").open("x") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(json.dumps({"status": result["status"], "old31_applicable": 31, "new_node": 1, "planned_fresh_lifecycles": 2, "products_fixtures_protected": len(protected)}))
