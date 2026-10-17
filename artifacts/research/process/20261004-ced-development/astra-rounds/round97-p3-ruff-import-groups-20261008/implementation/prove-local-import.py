"""One full-file byte replacement proof; immutable R94 AST proof reused."""
import ast
import hashlib
import json
import sys
from pathlib import Path

out = Path(__file__).resolve().parent
plan = json.loads((out.parent / "plan.json").read_text())
old = out.parent.parent / "round94-p3-scope-proof-import-order-20261008/implementation"
test = Path("tests/test_rgbd_role_models.py")
old_block = b'''    import io
    import struct
    from pathlib import Path

    from PIL import Image

    from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
    from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
    from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository
    from cloud_edge_robot_arm.vision.messages import model_to_observation_pixel
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from scripts.probe_rgbd_roles import read_role_config
'''
new_block = old_block.replace(b"    from scripts.probe_rgbd_roles import read_role_config\n", b"").replace(
    b"    from PIL import Image\n", b"    from PIL import Image\n    from scripts.probe_rgbd_roles import read_role_config\n")


def pin(path):
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def prove():
    before = (old / "source-after" / test).read_bytes()
    current = test.read_bytes()
    assert hashlib.sha256(before).hexdigest() == plan["source_scope"]["before_sha256"]
    assert before.count(old_block) == 1, "exact old block must exist once"
    tree = ast.parse(before.decode(), filename=str(test), type_comments=True)
    owners = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == plan["source_scope"]["function"]]
    assert len(owners) == 1, "target function must exist once"
    imports = []
    for node in owners[0].body:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            break
        imports.append(node)
    assert imports, "target import block missing"
    lines = before.splitlines(keepends=True)
    assert b"".join(lines[imports[0].lineno - 1:imports[-1].end_lineno]) == old_block, "old block not at exact target function"
    expected = before.replace(old_block, new_block, 1)
    assert current == expected, "entire file bytes differ from exact permitted replacement"
    assert hashlib.sha256(current).hexdigest() == plan["source_scope"]["after_sha256_proposed_not_executed"]
    assert len(current) == plan["source_scope"]["after_bytes_proposed"]
    reference = plan["r94_full_proof_reused"]
    reused = pin(Path(reference["path"]))
    assert reused == reference, "reused R94 proof pin mismatch"
    previous = json.loads(Path(reference["path"]).read_text())
    assert previous["status"] == "PASS" and len(previous["negative_self_controls"]) == 4
    assert all(row["rejected"] for row in previous["negative_self_controls"])
    protected = []
    freeze = json.loads((old / "source-freeze.json").read_text())
    for row in freeze["sources"]:
        path = Path(row["path"])
        if path == test:
            continue
        assert path in {Path("configs/research/ced_roles.yaml"), Path("src/cloud_edge_robot_arm/vision/role_models.py"),
                        Path("src/cloud_edge_robot_arm/vision/planner.py"), Path("tests/test_ced_runtime_binding.py")}
        actual = pin(path)
        assert actual == row and path.read_bytes() == (old / "source-after" / path).read_bytes(), "protected source bytes changed"
        protected.append(actual)
    assert len(protected) == 4
    result = {"status": "PASS", "whole_file_exact_byte_replacement": True, "path": str(test),
              "function": owners[0].name, "old_block_start_line": imports[0].lineno,
              "old_block_end_line": imports[-1].end_lineno, "old_block_byte_offset": before.index(old_block),
              "new_block_byte_offset": current.index(new_block), "before_sha256": hashlib.sha256(before).hexdigest(),
              "after": pin(test), "old_block": old_block.decode(), "new_block": new_block.decode(),
              "protected_four_sources": protected, "reused_R94_proof": reused, "reused_R94_proof_verified": True,
              "R94_proof_and_negative_controls_rerun": 0, "product_imports_or_writes": 0}
    with (out / "local-import-proof.json").open("x") as file:
        json.dump(result, file, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        prove()
    except Exception as error:
        failure = {"status": "FAIL", "stage": "exact local byte proof", "path": str(test), "error_type": type(error).__name__, "error": str(error)}
        with (out / "local-import-proof-failure.json").open("x") as file:
            json.dump(failure, file, indent=2)
        print(json.dumps(failure), file=sys.stderr)
        sys.exit(1)
