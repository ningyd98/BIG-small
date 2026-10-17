"""Bounded semantic and independent formatter proof; no product writes."""
import ast
import copy
import difflib
import hashlib
import io
import json
import tokenize
from pathlib import Path

import yaml

out = Path(__file__).resolve().parent
plan = json.loads((out.parent / "plan.json").read_text())
owned = plan["scope"]["owned"]


def dump(node):
    return ast.dump(node, include_attributes=False)


def comments(text):
    return [t.string for t in tokenize.generate_tokens(io.StringIO(text).readline) if t.type == tokenize.COMMENT]


def signatures(tree):
    return [(n.name, dump(n.args), dump(n.returns) if n.returns else None,
             [dump(d) for d in n.decorator_list], n.type_comment)
            for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


new_names = {
    "_p3_snapshot_for_wire", "_p3_wire_boundary",
    *[test["node"].split("::")[1] for test in plan["tests"]],
}
rows = []
diff = []
for name in owned:
    before = (out / "source-before" / name).read_text()
    semantic = (out / "semantic-after" / name).read_text()
    after = Path(name).read_text()
    destination = out / "source-after" / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(Path(name).read_bytes())
    diff.extend(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                   fromfile="before/" + name, tofile="after/" + name))
    if name.endswith(".yaml"):
        a, b = yaml.safe_load(before), yaml.safe_load(after)
        assert a["cloud"]["coordinate_system"] == "pixel" and b["cloud"]["coordinate_system"] == "normalized_1000"
        restored = copy.deepcopy(b)
        restored["cloud"]["coordinate_system"] = "pixel"
        assert restored == a and after == semantic
        rows.append({"path": name, "parsed_delta_only": "cloud.coordinate_system: pixel -> normalized_1000"})
        continue
    a, s, b = [ast.parse(text, type_comments=True) for text in (before, semantic, after)]
    assert dump(s) == dump(b) and comments(semantic) == comments(after) and signatures(s) == signatures(b)
    reverted = copy.deepcopy(b)
    registered = []
    if name.endswith("role_models.py"):
        function = next(n for n in reverted.body if isinstance(n, ast.FunctionDef) and n.name == "resolve_cloud_role")
        generation = next(keyword.value for n in ast.walk(function) if isinstance(n, ast.Call)
                          for keyword in n.keywords if keyword.arg == "generation_parameters")
        i = next(i for i, key in enumerate(generation.keys) if isinstance(key, ast.Constant) and key.value == "think")
        assert isinstance(generation.values[i], ast.Constant) and generation.values[i].value is False
        del generation.keys[i], generation.values[i]
        registered.append("remove exact factory generation think=False key")
    elif name.endswith("planner.py"):
        exact = ast.parse('if "think" in generation:\n    body["enable_thinking"] = generation["think"]').body[0]
        found = []
        for n in ast.walk(reverted):
            for field, value in ast.iter_fields(n):
                if isinstance(value, list):
                    for i, entry in enumerate(value):
                        if isinstance(entry, ast.If) and dump(entry) == dump(exact):
                            found.append((value, i))
        assert len(found) == 1
        del found[0][0][found[0][1]]
        registered.append("remove exact compatible think->enable_thinking conditional")
    else:
        additions = [n.name for n in reverted.body if isinstance(n, ast.FunctionDef) and n.name in new_names]
        reverted.body = [n for n in reverted.body if not (isinstance(n, ast.FunctionDef) and n.name in new_names)]
        registered.append({"remove_only_registered_appended_functions": additions})
    assert dump(a) == dump(reverted)
    assert comments(before) == comments(after)
    rows.append({"path": name, "registered_reversions": registered,
                 "whole_module_AST_type_comments_restored": True,
                 "original_comments_unchanged": True,
                 "formatter_whole_AST_comments_signatures_equivalent": True,
                 "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
                 "semantic_after_sha256": hashlib.sha256(semantic.encode()).hexdigest(),
                 "formatted_after_sha256": hashlib.sha256(after.encode()).hexdigest()})
proof = {"whole_business_before_after_equivalent": False,
         "intended_semantic_changes": plan["scope"]["product_semantic_allowlist"],
         "rows": rows, "all_other_semantic_AST_original_tests_preserved": True}
with (out / "restricted-scope-proof.json").open("x") as stream:
    json.dump(proof, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
(out / "source.diff").write_text("".join(diff))
with (out / "progress.md").open("a") as stream:
    stream.write("\nformatter唯一exit0。独立formatter前后整模块AST/comments/signatures均相同；仅回退factory thinkFalse、compatible conditional、新追加命名tests/helpers即恢复原整模块AST；所有原comments/断言/helpers保持。YAML解析唯一坐标差异。明确三项意图变化，不声称整个业务前后等价。source-after/完整diff/范围证明保存。下一步静态各一次。\n")
print(json.dumps({"scope_proof": True, "formatter_equivalence": True, "old_tests_preserved": True}, ensure_ascii=False))
