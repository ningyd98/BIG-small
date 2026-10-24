from pathlib import Path
import ast
import difflib
import hashlib
import json
import symtable

base = Path("artifacts/research/process/20261004-ced-development/astra-rounds/round340-p6-t3-cap-source-proof-convention-20261024")
out = base / "implementation"
path = Path("src/cloud_edge_robot_arm/vision/operational_windows.py")

def select(text):
    module = ast.parse(text)
    owners = [node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "OperationalWindowOwner"]
    assert len(owners) == 1, "unique exact owner class"
    methods = [node for node in owners[0].body if isinstance(node, ast.FunctionDef) and node.name == "_remaining_app_seconds"]
    assert len(methods) == 1, "unique direct remaining cap method"
    return ast.get_source_segment(text, methods[0]).encode("utf-8")

before = path.read_bytes()
text = before.decode("utf-8")
segment_before = select(text)
assert hashlib.sha256(segment_before).hexdigest() == "278da2ca8e6d25b1067a8cc0e7fde56ac1eb6c8b7f3ca5f16bbcf8e298e3e999", "original canonical segment pin"
old = "        if seconds * 1_000_000_000 > remaining:\n"
new = "        numerator, denominator = seconds.as_integer_ratio()\n        if numerator * 1_000_000_000 > remaining * denominator:\n"
assert segment_before.decode("utf-8").count(old) == 1, "single target replacement"
assert text.count(old) == 1, "single whole-source target occurrence"
candidate = text.replace(old, new)
segment_after = select(candidate)
assert segment_after == segment_before.decode("utf-8").replace(old, new).encode("utf-8"), "exact canonical replacement reconstruction"
assert hashlib.sha256(segment_after).hexdigest() == "7fdd632f6bd6e93cb9d5a203cf245217f5bd27e5f336eced66be94d1491d2837", "unchanged canonical successor pin"
assert candidate.replace(new, old) == text, "all non-target source bytes preserved"
symtable.symtable(candidate, str(path), "exec")
assert path.read_bytes() == before, "immediate input still current before surgical write"
out.mkdir(exist_ok=True)
(out / "before-operational_windows.py").write_bytes(before)
(out / "before-cap-segment.txt").write_bytes(segment_before)
path.write_bytes(candidate.encode("utf-8"))
(out / "after-operational_windows.py").write_bytes(candidate.encode("utf-8"))
(out / "after-cap-segment.txt").write_bytes(segment_after)
(out / "minimal.diff").write_text("".join(difflib.unified_diff(text.splitlines(keepends=True), candidate.splitlines(keepends=True), fromfile="before/operational_windows.py", tofile="after/operational_windows.py")))
proof = {"round": "R340", "continues_exact_product_scope": "R339", "actual_author": "/root/p6_t3_sol", "kind": "SOURCE_ONLY_NO_NUMERIC_PROBE_OR_PRODUCT_EXECUTION", "representation": "class-qualified ast.get_source_segment; UTF-8 encode; no normalization", "before": {"bytes": len(before), "sha256": hashlib.sha256(before).hexdigest(), "segment_bytes": len(segment_before), "segment_sha256": hashlib.sha256(segment_before).hexdigest()}, "after": {"bytes": len(candidate.encode("utf-8")), "sha256": hashlib.sha256(candidate.encode("utf-8")).hexdigest(), "segment_bytes": len(segment_after), "segment_sha256": hashlib.sha256(segment_after).hexdigest()}, "predicates": {"unique_owner_and_direct_method": True, "original_canonical_pin": True, "single_exact_replacement": True, "exact_successor_reconstruction": True, "unchanged_successor_pin": True, "outside_bytes_unchanged": True, "AST_and_symbol_table_valid": True, "immediate_input_still_current": True}, "original_R339_command_trace_and_failure_evidence_preserved": True, "runtime_executed": False, "RED": "SPENT1/0; not rerun", "GREEN": "UNUSED_HELD0/1", "acceptance_limit": "Static source convention and exact R339 replacement only"}
(out / "source-proof.json").write_text(json.dumps(proof, indent=2) + "\n")
print(json.dumps(proof, indent=2))
