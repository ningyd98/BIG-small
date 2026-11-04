"""Prove the one R430 explicit-default zip keyword is the only AST difference."""

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
ROUND = Path(__file__).resolve().parents[1]
BASE = ROUND.parent
SOURCE = "src/cloud_edge_robot_arm/research/native_completion_horizon_originals.py"
PREVIOUS = BASE / "round429-t7b-full-horizon-evidence-20261104"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def adjacent(tree):
    shape = ast.dump(ast.parse("zip(seqs, seqs[1:])", mode="eval").body)
    matches = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        clean = ast.Call(func=node.func, args=node.args, keywords=[])
        if ast.dump(clean) == shape:
            matches.append(node)
    assert len(matches) == 1, "one exact adjacent-pair zip required"
    return matches[0]


def main():
    before = (PREVIOUS / "implementation/pre-green-source-originals" / SOURCE).read_bytes()
    after = (ROOT / SOURCE).read_bytes()
    plan = json.loads((ROUND / "plan.json").read_text())
    pin = next(row for row in plan["input_pins"] if row["path"] == SOURCE)
    assert sha(before) == pin["sha256"] and len(before) == pin["bytes"]
    old_tree, new_tree = ast.parse(before), ast.parse(after)
    old_node, new_node = adjacent(old_tree), adjacent(new_tree)
    assert not old_node.keywords
    assert len(new_node.keywords) == 1
    keyword = new_node.keywords[0]
    assert keyword.arg == "strict" and isinstance(keyword.value, ast.Constant)
    assert keyword.value.value is False
    before_normalizing = ast.dump(new_tree, include_attributes=False)
    new_node.keywords = []
    old_dump = ast.dump(old_tree, include_attributes=False)
    new_dump = ast.dump(new_tree, include_attributes=False)
    assert old_dump == new_dump, "unapproved AST difference"
    unchanged = []
    for name in (
        "src/cloud_edge_robot_arm/vision/native_completion_horizon.py",
        "tests/test_native_completion_horizon_v1.py",
        "tests/test_native_completion_horizon_originals_v1.py",
    ):
        expected = next(row for row in plan["input_pins"] if row["path"] == name)
        raw = (ROOT / name).read_bytes()
        assert sha(raw) == expected["sha256"] and len(raw) == expected["bytes"]
        unchanged.append(expected)
    report = {
        "old_sha256": sha(before), "snapshot_sha256": sha(before),
        "new_sha256": sha(after), "allowed_difference_count": 1,
        "target": "zip(seqs, seqs[1:]) -> zip(seqs, seqs[1:], strict=False)",
        "old_ast_sha256": sha(old_dump.encode()),
        "new_ast_before_normalizing_sha256": sha(before_normalizing.encode()),
        "new_ast_after_normalizing_sha256": sha(new_dump.encode()),
        "ast_equal": True, "unchanged_files": unchanged,
    }
    target = ROUND / "validation/ast-equivalence.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
