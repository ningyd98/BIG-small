import ast
import copy
import hashlib
import io
import json
import tokenize
from pathlib import Path

OUT = Path(__file__).resolve().parent
RECIPE = json.loads((OUT / "registered-scope-recipe.json").read_text())
NEW_TEST_NAMES = {
    "_r93_repin_json",
    "test_cached_capture_preserves_empty_instance_sidecars_cpu",
    "test_source_inventory_rejects_empty_and_noninteger_bytes_cpu",
    "test_artifact_inventory_preserves_negative_and_geometry_guards_cpu",
    "test_reader_rejects_instance_source_metadata_mismatch_cpu",
}
TEST_PATH = Path("tests/test_operational_capture_v1.py")


def parse(text, path):
    return ast.parse(text, filename=str(path), type_comments=True)


def semantic(tree):
    value = copy.deepcopy(tree)
    # TypeIgnore.lineno is an AST field, rather than an ordinary coordinate.
    # Its binding/tag is checked independently by anchors below before normalizing.
    for item in value.type_ignores:
        item.lineno = 0
    return ast.dump(value, include_attributes=False)


def ignore_anchors(tree, text):
    lines = text.splitlines()
    result = []
    for ignore in tree.type_ignores:
        candidates = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.stmt)
            and node.lineno <= ignore.lineno <= node.end_lineno
        ]
        assert candidates, "type-ignore has no enclosing statement"
        statement = min(candidates, key=lambda node: (node.end_lineno - node.lineno, -node.lineno))
        comment = next(
            token.string for token in tokenize.generate_tokens(io.StringIO(text).readline)
            if token.type == tokenize.COMMENT and token.start[0] == ignore.lineno
            and token.string.startswith("# type: ignore")
        )
        result.append({
            "line": ignore.lineno, "tag": ignore.tag, "comment": comment,
            "statement": ast.dump(statement, include_attributes=False),
            "original_line": lines[ignore.lineno - 1],
        })
    return result


def bound_ignores(records):
    return [{k: v for k, v in item.items() if k not in {"line", "original_line"}} for item in records]


def comments(text):
    return [token.string for token in tokenize.generate_tokens(io.StringIO(text).readline)
            if token.type == tokenize.COMMENT]


def signatures(tree):
    return [
        (node.name, ast.dump(node.args, include_attributes=False),
         ast.dump(node.returns, include_attributes=False) if node.returns else None,
         [ast.dump(value, include_attributes=False) for value in node.decorator_list])
        for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


report = {"status": "PASS", "files": [], "type_ignore_policy": "tags/comments/statement binding compared before coordinate normalization"}
for relative, replacements in RECIPE.items():
    path = Path(relative)
    assert path in {
        Path("src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py"),
        Path("src/cloud_edge_robot_arm/research/operational_prefix_v1.py"), TEST_PATH
    }, "exact Path scope required"
    before = (OUT / "source-before" / path).read_text()
    preformat = (OUT / "semantic-after" / path).read_text()
    after = path.read_text()
    expected = before
    for old, new in replacements:
        assert expected.count(old) == 1, (str(path), "registered replacement not unique")
        expected = expected.replace(old, new, 1)
    expected_tree = parse(expected, path)
    scoped_tree = parse(preformat, path)
    if path == TEST_PATH:
        added = [node for node in scoped_tree.body if isinstance(node, ast.FunctionDef) and node.name in NEW_TEST_NAMES]
        assert len(added) == len(NEW_TEST_NAMES) and {node.name for node in added} == NEW_TEST_NAMES
        scoped_tree.body = [node for node in scoped_tree.body if node not in added]
    expected_ignores = ignore_anchors(expected_tree, expected)
    scoped_ignores = ignore_anchors(scoped_tree, preformat)
    assert bound_ignores(expected_ignores) == bound_ignores(scoped_ignores), (str(path), "scope type-ignore binding changed")
    assert semantic(expected_tree) == semantic(scoped_tree), (str(path), "unregistered AST delta")
    assert comments(before) == comments(preformat), (str(path), "scope comments changed")
    pre_tree = parse(preformat, path)
    after_tree = parse(after, path)
    pre_ignores = ignore_anchors(pre_tree, preformat)
    after_ignores = ignore_anchors(after_tree, after)
    assert bound_ignores(pre_ignores) == bound_ignores(after_ignores), (str(path), "formatter type-ignore binding changed")
    assert semantic(pre_tree) == semantic(after_tree), (str(path), "formatter full AST changed")
    assert comments(preformat) == comments(after), (str(path), "formatter comments changed")
    assert signatures(pre_tree) == signatures(after_tree), (str(path), "formatter signatures changed")
    report["files"].append({
        "path": str(path), "restricted_scope": "PASS", "formatter_full_ast_comments_signatures": "PASS",
        "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
        "semantic_after_sha256": hashlib.sha256(preformat.encode()).hexdigest(),
        "after_sha256": hashlib.sha256(after.encode()).hexdigest(),
        "preformat_type_ignores": pre_ignores, "after_type_ignores": after_ignores,
    })
with (OUT / "scope-proof.json").open("x") as file:
    json.dump(report, file, indent=2)
print(json.dumps(report, indent=2))
