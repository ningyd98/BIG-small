"""Read-only CPU comparison of frozen reader and corrected upcoming-step join.

Only one AST lookup is changed in memory. Original source and actual evidence
remain untouched; corrected associations cannot complete the failed horizon.
"""

import ast
import gzip
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent.parent
ACTUAL = HERE / "attempt-1"
SOURCE = HERE / "verify_offline.py"
sha = lambda data: hashlib.sha256(data).hexdigest()
source_hash = sha(SOURCE.read_bytes())
assert source_hash == "19225d13e058cb428b8cf3a99095bde6b46bfd985bcb3290e4824fdd4b0b4e6f"
source = SOURCE.read_text()
spec = importlib.util.spec_from_file_location("independent_frozen_reader", SOURCE)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)


class UpcomingStepJoin(ast.NodeTransformer):
    replacements = 0

    def visit_Call(self, node):
        self.generic_visit(node)
        if (isinstance(node.func, ast.Attribute) and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "actuators"
            and len(node.args) == 1 and isinstance(node.args[0], ast.BinOp)
            and isinstance(node.args[0].op, ast.Sub)
            and isinstance(node.args[0].left, ast.Name) and node.args[0].left.id == "step"
            and isinstance(node.args[0].right, ast.Constant) and node.args[0].right.value == 1):
            node.args = [ast.Name(id="step", ctx=ast.Load())]
            self.replacements += 1
        return node


transform = UpcomingStepJoin()
tree = ast.fix_missing_locations(transform.visit(ast.parse(source)))
assert transform.replacements == 1
corrected = {"__name__": "independent_corrected_reader", "__file__": str(SOURCE)}
exec(compile(tree, str(SOURCE), "exec"), corrected)
evidence_hashes = {str(path.relative_to(ACTUAL)): sha(path.read_bytes())
                   for path in ACTUAL.rglob("*") if path.is_file()}
with gzip.open(ACTUAL / "nominal-journal.jsonl.gz", "rt") as stream:
    rows = [json.loads(line) for line in stream]
operations = {(row["source"]["operation_id"], row["source"]["phase"]): row
              for row in rows if row["event"] == "OPERATION"}
actuators = {row["source"]["physics_step"]: row for row in rows if row["event"] == "ACTUATOR"}
acquisitions = {row["physics_step"]: row for row in rows if row["event"] == "ACQUISITION_BEGIN"}
trace = []
for step in range(1, 11):
    acquisition, actuator = acquisitions[step], actuators[step]
    control_id, physics_id = acquisition["control_operation_id"], acquisition["physics_operation_id"]
    control_begin, control_end = operations[(control_id, "BEGIN")], operations[(control_id, "END")]
    physics_begin, physics_end = operations[(physics_id, "BEGIN")], operations[(physics_id, "END")]
    assert actuator["control_operation_id"] == control_id
    assert control_end["source"]["physics_step"] == physics_begin["source"]["physics_step"] == step - 1
    assert actuator["source"]["physics_step"] == physics_end["source"]["physics_step"] == step
    stamps = [control_begin["clock"]["monotonic_after_ns"], control_end["clock"]["monotonic_before_ns"],
              actuator["clock"]["monotonic_before_ns"], physics_begin["clock"]["monotonic_before_ns"],
              physics_end["clock"]["monotonic_before_ns"], acquisition["clock"]["monotonic_before_ns"]]
    assert stamps == sorted(stamps)
    trace.append({"upcoming_step": step, "control_operation_id": control_id,
                  "physics_operation_id": physics_id, "actuator_source_step": actuator["source"]["physics_step"],
                  "clock_sequence": ["CONTROL_BEGIN_AFTER", "CONTROL_END_BEFORE", "ACTUATOR_BEFORE",
                                     "PHYSICS_BEGIN_BEFORE", "PHYSICS_END_BEFORE", "ACQUISITION_BEGIN_BEFORE"],
                  "monotonic_ns": stamps})
reports = {}
with tempfile.TemporaryDirectory(prefix="actual-actuator-reader-replay-") as temporary:
    for name, reader in (("frozen_reader", old.verify_attempt), ("corrected_reader", corrected["verify_attempt"])):
        directory = Path(temporary) / name
        directory.mkdir()
        for member in ("whole-step", "summary.json", "terminal.json", "nominal-journal.jsonl.gz"):
            (directory / member).symlink_to(ACTUAL / member)
        reports[name] = reader(directory, decode=False)
prefix_errors = lambda report: [failure for failure in report["failures"]
    if "CONTROL/PHYSICS association mismatch" in failure or "CONTROL/actuator/PHYSICS/acquisition clocks mismatch" in failure]
assert len(prefix_errors(reports["frozen_reader"])) == 9
assert prefix_errors(reports["corrected_reader"]) == []
for report in reports.values():
    assert report["integrity_status"] == "INCOMPLETE_OR_INVALID"
    assert report["allocated_steps"] == 11 and report["verified_frames"] == 10
    assert report["failed_or_missing_frames"] == 1
    assert report["formal_accepted"] is False and report["continuous_motion"] == "NOT_CERTIFIED"
    assert report["source_authenticity"] == "UNKNOWN" and report["native_admission"] == "NOT_PROMOTED"
    assert report["external_utc_uncertainty"] == report["future_stability"] == report["calibrated_error_bound"] == "UNAVAILABLE"
assert sha(SOURCE.read_bytes()) == source_hash
assert all(sha((ACTUAL / name).read_bytes()) == expected for name, expected in evidence_hashes.items())
result = {
    "scope": "READ_ONLY_ACTUAL_PREFIX_CPU_REPLAY_NO_RENDER_PHYSICS_RETRY",
    "source_sha256": source_hash, "in_memory_ast_replacements": transform.replacements,
    "change": "actuators.get(step - 1) -> actuators.get(step), upcoming physical step domain",
    "qualified_red": prefix_errors(reports["frozen_reader"]),
    "qualified_green": prefix_errors(reports["corrected_reader"]),
    "full_attempt_still_incomplete": True, "actual_source_trace": trace, "reports": reports,
    "original_actual_file_hashes_unchanged": evidence_hashes,
}
(HERE / "fix-round-2/independent-actuator-replay.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"qualified_old_prefix_errors": len(result["qualified_red"]),
                  "corrected_prefix_errors": 0, "whole_attempt": "INCOMPLETE_OR_INVALID",
                  "allocated": 11, "verified": 10, "failed": 1, "source_and_actual_unchanged": True}))
