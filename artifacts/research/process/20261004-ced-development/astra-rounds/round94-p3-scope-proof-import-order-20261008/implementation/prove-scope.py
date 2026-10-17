"""R94 exact-path proof, strict type-ignore binding, and four detached controls."""
import ast
import copy
import hashlib
import io
import json
import sys
import tokenize
from pathlib import Path

import yaml

OUT = Path(__file__).resolve().parent
PLAN = json.loads((OUT.parent / "plan.json").read_text())
OLD = OUT.parent.parent / "round92-p3-compatible-thinking-wire-20261007/implementation"
YAML = Path("configs/research/ced_roles.yaml")
ROLE = Path("src/cloud_edge_robot_arm/vision/role_models.py")
PLANNER = Path("src/cloud_edge_robot_arm/vision/planner.py")
TEST = Path("tests/test_rgbd_role_models.py")
BINDING = Path("tests/test_ced_runtime_binding.py")
PATHS = (YAML, ROLE, PLANNER, TEST, BINDING)
NEW = {
    TEST: {"_p3_snapshot_for_wire", "_p3_wire_boundary", "test_ced_max_reuses_successful_normalized_transport",
           "test_role_cost_delta_preserves_all_sent_requests", "test_role_compatible_thinking_reaches_serialized_request",
           "test_role_thinking_provider_controls"},
    BINDING: {"test_existing_max_success_is_not_new_source_freeze", "test_role_thinking_change_invalidates_request_binding"},
}
CTX = {"path": "", "stage": ""}


class ProofFailure(Exception):
    pass


def check(condition, message):
    if not condition:
        raise ProofFailure(json.dumps({**CTX, "difference": message}, ensure_ascii=False))


def dump(node):
    return ast.dump(node, include_attributes=False)


def difference(left, right, trail="Module"):
    if type(left) is not type(right):
        return f"{trail}: types {type(left).__name__} != {type(right).__name__}"
    if isinstance(left, ast.AST):
        for field in left._fields:
            result = difference(getattr(left, field), getattr(right, field), trail + "." + field)
            if result:
                return result
    elif isinstance(left, list):
        if len(left) != len(right):
            return f"{trail}: lengths {len(left)} != {len(right)}"
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            result = difference(a, b, f"{trail}[{index}]")
            if result:
                return result
    elif left != right:
        return f"{trail}: {left!r} != {right!r}"
    return None


def equal(left, right):
    delta = difference(left, right)
    check(delta is None, delta)


def parse(text, path):
    return ast.parse(text, filename=str(path), type_comments=True)


def one(values, description):
    check(len(values) == 1, f"{description}: count {len(values)} != 1")
    return values[0]


def function(tree, name):
    return one([node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name], name)


def comments(text):
    return [token.string for token in tokenize.generate_tokens(io.StringIO(text).readline)
            if token.type == tokenize.COMMENT]


def signatures(tree):
    return [(node.name, dump(node.args), dump(node.returns) if node.returns else None,
             [dump(item) for item in node.decorator_list], node.type_comment)
            for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]


def ignore_bindings(tree, text, original):
    owner = function(tree, "resolve_cloud_role")
    expected = [(206 if original else 207, "planner.role_config_version = profile.config_version"),
                (224 if original else 225, "planner.role_snapshot = snapshot")]
    check(len(tree.type_ignores) == 2, "exactly two role type-ignores required")
    tokens = [token for token in tokenize.generate_tokens(io.StringIO(text).readline)
              if token.type == tokenize.COMMENT and "type: ignore" in token.string]
    check(len(tokens) == 2, "exactly two type-ignore comment tokens required")
    rows = []
    for ignore, token, (line, statement) in zip(tree.type_ignores, tokens, expected, strict=True):
        wanted = ast.parse(statement, type_comments=True).body[0]
        assignment = one([node for node in ast.walk(owner) if isinstance(node, ast.Assign) and dump(node) == dump(wanted)], statement)
        check(ignore.tag == "[attr-defined]", f"type-ignore tag changed: {ignore.tag}")
        check(token.string == "# type: ignore[attr-defined]", "type-ignore token changed")
        check(ignore.lineno == token.start[0] == assignment.lineno == assignment.end_lineno == line,
              f"type-ignore binding/position differs: {ignore.lineno}/{token.start[0]}/{assignment.lineno}, expected {line}: {statement}")
        check(owner.lineno <= assignment.lineno <= owner.end_lineno, "type-ignore owner differs")
        rows.append({"line": line, "tag": ignore.tag, "comment": token.string,
                     "function": owner.name, "assignment": statement, "assignment_AST": dump(assignment)})
    return rows


def revert(tree, path):
    restored = copy.deepcopy(tree)
    if path == ROLE:
        owner = function(restored, "resolve_cloud_role")
        target = one([node for node in owner.body if isinstance(node, ast.Assign)
                      and len(node.targets) == 1 and dump(node.targets[0]) == dump(ast.Name(id="model_snapshot", ctx=ast.Store()))], "model_snapshot assignment")
        check(isinstance(target.value, ast.Call) and isinstance(target.value.func, ast.Name)
              and target.value.func.id == "ModelConfigSnapshot", "exact snapshot call required")
        generation = one([keyword.value for keyword in target.value.keywords if keyword.arg == "generation_parameters"], "generation_parameters")
        check(isinstance(generation, ast.Dict), "generation_parameters literal dict required")
        index = one([i for i, key in enumerate(generation.keys) if isinstance(key, ast.Constant) and key.value == "think"], "think key")
        check(isinstance(generation.values[index], ast.Constant) and generation.values[index].value is False, "think must be exact False")
        del generation.keys[index]
        del generation.values[index]
        return restored, "one exact model_snapshot generation think=False entry"
    if path == PLANNER:
        cls = one([node for node in restored.body if isinstance(node, ast.ClassDef) and node.name == "RGBDPlannerAdapter"], "RGBDPlannerAdapter")
        owner = function(cls, "_request_visual")
        branch = one([node for node in owner.body if isinstance(node, ast.If)
                      and dump(node.test) == dump(ast.parse('self.provider == "ollama"', mode="eval").body)], "provider branch")
        conditional = ast.parse('if "think" in generation:\n    body["enable_thinking"] = generation["think"]', type_comments=True).body[0]
        index = one([i for i, node in enumerate(branch.orelse) if dump(node) == dump(conditional)], "compatible exact think conditional")
        path_assignment = ast.parse("path = self.chat_path", type_comments=True).body[0]
        check(index == len(branch.orelse) - 2 and dump(branch.orelse[index + 1]) == dump(path_assignment), "conditional not immediately before exact path assignment")
        del branch.orelse[index]
        return restored, "one complete compatible conditional at exact class/method/else/path anchor"
    if path in NEW:
        wanted = NEW[path]
        additions = [node for node in restored.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
        check(len(additions) == len(wanted) and {node.name for node in additions} == wanted, "registered test/helper cardinality differs")
        restored.body = [node for node in restored.body if node not in additions]
        return restored, sorted(wanted)
    raise ProofFailure(f"unknown exact Path dispatch: {path}")


def restored_equal(before, after, path, before_text, after_text):
    restored, removed = revert(after, path)
    mappings = []
    if path == ROLE:
        initial = ignore_bindings(before, before_text, True)
        final = ignore_bindings(after, after_text, False)
        for old_row, new_row, ignored in zip(initial, final, restored.type_ignores, strict=True):
            check(old_row["assignment_AST"] == new_row["assignment_AST"], "bound assignment AST differs")
            mappings.append({"before": old_row["line"], "after": new_row["line"], "tag": new_row["tag"], "assignment": new_row["assignment"]})
            ignored.lineno = old_row["line"]
    equal(before, restored)
    return {"removed_only": removed, "type_ignore_mappings": mappings}


def import_block(text):
    tree = parse(text, TEST)
    owner = function(tree, "test_ced_max_reuses_successful_normalized_transport")
    nodes = []
    for node in owner.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            break
        nodes.append(node)
    check(bool(nodes), "local import block missing")
    lines = text.splitlines(keepends=True)
    return "".join(lines[nodes[0].lineno - 1:nodes[-1].end_lineno]), nodes, owner, tree


def validate(data):
    check(set(data) == set(PATHS), "exact five-path input dispatch required")
    rows = []
    for path in PATHS:
        CTX.update(path=str(path), stage="A authorized R92 semantic delta")
        before, semantic, formatted, current = (data[path][stage] for stage in ("before", "semantic", "formatted", "current"))
        if path == YAML:
            a, b = yaml.safe_load(before), yaml.safe_load(semantic)
            check(a["cloud"]["coordinate_system"] == "pixel" and b["cloud"]["coordinate_system"] == "normalized_1000", "coordinate delta differs")
            restored = copy.deepcopy(b); restored["cloud"]["coordinate_system"] = "pixel"
            check(restored == a, "other YAML semantic delta")
            CTX["stage"] = "B/C YAML frozen bytes"
            check(semantic == formatted == current, "YAML stage bytes differ")
            rows.append({"path": str(path), "A": "coordinate-only", "B_C_D": "PASS"})
            continue
        a, s, f, c = [parse(text, path) for text in (before, semantic, formatted, current)]
        record = restored_equal(a, s, path, before, semantic)
        check(comments(before) == comments(semantic), "original comments changed")
        CTX["stage"] = "B complete R92 formatter equivalence"
        equal(s, f)
        check(comments(semantic) == comments(formatted), "formatter comments changed")
        check(signatures(s) == signatures(f), "formatter signatures changed")
        CTX["stage"] = "C R94 exact local import permutation"
        if path == TEST:
            old_block, old_nodes, _, _ = import_block(formatted)
            new_block, new_nodes, current_owner, current_tree = import_block(current)
            check(new_block == PLAN["scope"]["exact_new_import_block"], "new local imports differ from exact approved block")
            check(sorted(map(dump, old_nodes)) == sorted(map(dump, new_nodes)), "import identity/name/alias/level changed")
            check(formatted.count(old_block) == 1 and current == formatted.replace(old_block, new_block, 1), "non-import byte delta")
            restored_current = copy.deepcopy(current_tree)
            restored_owner = function(restored_current, "test_ced_max_reuses_successful_normalized_transport")
            restored_owner.body[:len(new_nodes)] = copy.deepcopy(old_nodes)
            equal(f, restored_current)
            check(signatures(f) == signatures(c), "import permutation signatures changed")
        else:
            check(current == formatted, "protected frozen bytes changed")
            equal(f, c)
        check(comments(formatted) == comments(current), "R94 comments changed")
        CTX["stage"] = "D current exact reversion to original"
        final_record = restored_equal(a, c, path, before, current)
        check(comments(before) == comments(current), "original current comments changed")
        rows.append({"path": str(path), "A": record, "B": "full AST/comments/signatures PASS", "C": "local permutation only" if path == TEST else "byte-identical", "D": final_record})
    return rows


def replace_node(text, node, replacement):
    check(node.lineno == node.end_lineno, "control requires single-line node")
    lines = text.splitlines(keepends=True)
    index = node.lineno - 1
    lines[index] = lines[index][:node.col_offset] + replacement + lines[index][node.end_col_offset:]
    return "".join(lines)


def main():
    data = {path: {"before": (OLD / "source-before" / path).read_text(), "semantic": (OLD / "semantic-after" / path).read_text(),
                   "formatted": (OLD / "source-after" / path).read_text(), "current": path.read_text()} for path in PATHS}
    controls = []
    for name in ("changed_ignore_tag", "retargeted_ignore", "modified_ordinary_annotation", "modified_old_assertion"):
        variant = copy.deepcopy(data)
        text = variant[ROLE]["semantic"]
        if name == "changed_ignore_tag":
            variant[ROLE]["semantic"] = text.replace("# type: ignore[attr-defined]", "# type: ignore[assignment]", 1)
        elif name == "retargeted_ignore":
            old = "planner.role_config_version = profile.config_version  # type: ignore[attr-defined]"
            new = "planner.role_config_version = profile.config_version"
            text = text.replace(old, new, 1)
            variant[ROLE]["semantic"] = text.replace("request_settings = cloud_request_settings(planner)", "request_settings = cloud_request_settings(planner)  # type: ignore[attr-defined]", 1)
        elif name == "modified_ordinary_annotation":
            owner = function(parse(text, ROLE), "resolve_cloud_role")
            arg = one([item for item in owner.args.args if item.arg == "service"], "service annotation")
            variant[ROLE]["semantic"] = replace_node(text, arg.annotation, "object")
        else:
            text = variant[TEST]["semantic"]
            tree = parse(text, TEST)
            originals = [node for node in tree.body if not (isinstance(node, ast.FunctionDef) and node.name in NEW[TEST])]
            candidates = [node for parent in originals for node in ast.walk(parent) if isinstance(node, ast.Assert)
                          and node.test.lineno == node.test.end_lineno and dump(node.test) != dump(ast.Constant(value=False))]
            check(bool(candidates), "old assertion control candidate absent")
            variant[TEST]["semantic"] = replace_node(text, candidates[0].test, "False")
        try:
            validate(variant)
        except ProofFailure as failure:
            controls.append({"control": name, "rejected": True, "diagnostic": str(failure)})
        else:
            raise ProofFailure(f"negative control unexpectedly accepted: {name}")
    rows = validate(data)
    report = {"status": "PASS", "negative_self_controls": controls, "rows": rows,
              "whole_business_before_after_equivalent": False, "three_R92_intended_deltas_retained": True,
              "type_comments_policy": "Only the two verified role Assign TypeIgnore.lineno fields on detached reverted copies map to original positions; tags/comments/type_comments/ordinary annotations and every other AST field retained",
              "product_imports_or_writes": 0, "test_or_formatter_runs": 0}
    with (OUT / "restricted-scope-proof.json").open("x") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        failure = {"status": "FAIL", **CTX, "error_type": type(error).__name__, "error": str(error)}
        with (OUT / "scope-proof-failure.json").open("x") as file:
            json.dump(failure, file, ensure_ascii=False, indent=2)
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
