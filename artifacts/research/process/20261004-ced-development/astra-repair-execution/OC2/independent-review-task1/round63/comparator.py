"""Round63 one-shot stdlib AST-only metadata recertification; never import product."""
from __future__ import annotations
import ast
import copy
import hashlib
import json
import os
import sys
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()
OUTPUT_ROOT = Path(__file__).absolute().parent
RESULT_PATH = OUTPUT_ROOT / "comparison-result.json"
ARCHIVE = ROOT / "artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/round61"
PATHS = {
    "before": ARCHIVE / "source-before/src/cloud_edge_robot_arm/research/operational_prefix_v1.py",
    "after": ARCHIVE / "source-after/src/cloud_edge_robot_arm/research/operational_prefix_v1.py",
    "current": ROOT / "src/cloud_edge_robot_arm/research/operational_prefix_v1.py",
}
EFFECTS = {"source_write_attempts": 0, "metadata_result_write_opens": 0, "product_import_attempts": 0, "other_effect_attempts": 0}

def audit(event, args):
    if event == "import" and str(args[0]).startswith("cloud_edge_robot_arm"):
        EFFECTS["product_import_attempts"] += 1
        raise RuntimeError("product import forbidden in metadata recertification")
    if event == "open":
        mode, flags = args[1], args[2]
        writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if writing:
            target = Path(args[0]).absolute() if isinstance(args[0], (str, bytes, os.PathLike)) else None
            if target == RESULT_PATH:
                EFFECTS["metadata_result_write_opens"] += 1
            else:
                EFFECTS["source_write_attempts"] += 1
                raise RuntimeError("only exclusive new comparison-result.json write allowed")
    if event in {"os.mkdir", "os.remove", "os.rmdir", "os.rename", "os.link", "os.symlink", "os.truncate", "sqlite3.connect", "socket.__new__", "socket.connect", "socket.bind", "subprocess.Popen"}:
        EFFECTS["other_effect_attempts"] += 1
        raise RuntimeError("runtime/filesystem effect forbidden: " + event)

sys.addaudithook(audit)

def dump(node):
    return ast.dump(node, include_attributes=False)

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def pin(raw):
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

def find_method(tree, label):
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == "OperationalPrefixApplicationV1"]
    require(len(classes) == 1, label + ": exactly one application class required")
    methods = [node for node in classes[0].body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "check_active"]
    require(len(methods) == 1 and isinstance(methods[0], ast.FunctionDef), label + ": exactly one synchronous check_active required")
    return classes[0], methods[0]

def import_node(node):
    return isinstance(node, (ast.Import, ast.ImportFrom))

def alias_rows(node):
    return [{"name": alias.name, "asname": alias.asname} for alias in node.names]

def import_fingerprint(node):
    item = copy.deepcopy(node)
    item.names.sort(key=lambda alias: (alias.name, alias.asname or ""))
    return dump(item)

def import_row(node, position):
    return {"position": position, "line": node.lineno, "end_line": node.end_lineno,
            "kind": type(node).__name__, "module": getattr(node, "module", None),
            "level": getattr(node, "level", None), "aliases_in_original_order": alias_rows(node),
            "original_AST": dump(node), "same_binding_fingerprint": import_fingerprint(node)}

IMPORT_SCOPES = []

def constrain_import_order(left, right, path):
    """Only same-scope contiguous import runs; all non-import slots stay fixed."""
    if isinstance(left, ast.AST) and isinstance(right, ast.AST):
        if type(left) is not type(right):
            return
        for field in left._fields:
            constrain_import_order(getattr(left, field), getattr(right, field), path + "." + field)
    elif isinstance(left, list) and isinstance(right, list):
        left_slots = [index for index, node in enumerate(left) if import_node(node)]
        right_slots = [index for index, node in enumerate(right) if import_node(node)]
        if left_slots or right_slots:
            require(len(left) == len(right) and left_slots == right_slots, path + ": changed import/non-import positions")
            runs = []
            for index in left_slots:
                if runs and index == runs[-1][-1] + 1:
                    runs[-1].append(index)
                else:
                    runs.append([index])
            for positions in runs:
                old_nodes = [left[index] for index in positions]
                new_nodes = [right[index] for index in positions]
                old_multiset = Counter(import_fingerprint(node) for node in old_nodes)
                new_multiset = Counter(import_fingerprint(node) for node in new_nodes)
                require(old_multiset == new_multiset, path + ": import module/level/aliases/bindings or conditional placement differs")
                changed = [dump(node) for node in old_nodes] != [dump(node) for node in new_nodes]
                scope_report = {"scope": path, "contiguous_import_positions": positions,
                    "same_exact_import_multiset_modulo_alias_member_order": True,
                    "non_import_positions_preserved": True,
                    "scope_and_conditional_placement_preserved": True,
                    "order_changed": changed,
                    "before_imports": [import_row(node, position) for node, position in zip(old_nodes, positions)],
                    "after_imports": [import_row(node, position) for node, position in zip(new_nodes, positions)],
                    "multiset": [{"fingerprint": key, "count": count} for key, count in sorted(old_multiset.items())]}
                IMPORT_SCOPES.append(scope_report)
                # These two explicitly verified equal multisets are the entire normalization authority.
                for nodes, target in [(old_nodes, left), (new_nodes, right)]:
                    ordered = sorted(nodes, key=import_fingerprint)
                    for position, node in zip(positions, ordered):
                        node.names.sort(key=lambda alias: (alias.name, alias.asname or ""))
                        target[position] = node
        for index, (old, new) in enumerate(zip(left, right)):
            if import_node(old) or import_node(new):
                continue
            constrain_import_order(old, new, path + "[" + str(index) + "]")

def compare():
    raw = {label: path.read_bytes() for label, path in PATHS.items()}
    require(raw["current"] == raw["after"], "current app differs from frozen source-after bytes")
    trees = {label: ast.parse(data, filename=str(PATHS[label])) for label, data in raw.items()}
    methods = {label: find_method(tree, label)[1] for label, tree in trees.items()}
    assignment = ast.parse("origin = record.origin").body[0]
    guard = ast.parse('if origin is None:\n    raise RuntimeError("actual RUNNING assignment/lease/origin not established")').body[0]
    before_method, after_method = methods["before"], methods["after"]
    require(len(before_method.body) >= 2 and len(after_method.body) == len(before_method.body) + 1, "method statement-count change is not exactly one guard")
    require(dump(before_method.body[-2]) == dump(assignment), "before original final origin assignment differs")
    require(dump(after_method.body[-3]) == dump(assignment), "after original final origin assignment differs")
    require(dump(after_method.body[-2]) == dump(guard), "after newly added guard is not the exact authorized None guard")
    require(isinstance(before_method.body[-1], ast.Return) and dump(before_method.body[-1]) == dump(after_method.body[-1]), "original return AST differs")
    guard_counts = {label: sum(dump(node) == dump(guard) for node in ast.walk(method)) for label, method in methods.items()}
    require(guard_counts == {"before": 0, "after": 1, "current": 1}, "exact newly-added guard count differs")
    require(dump(methods["current"]) == dump(after_method), "current method AST differs from source-after")
    residual_after = copy.deepcopy(trees["after"])
    residual_method = find_method(residual_after, "residual_after")[1]
    removed = residual_method.body.pop(-2)
    require(dump(removed) == dump(guard), "residual transformation removed anything other than exact new guard")
    exact_residual_equal = dump(trees["before"]) == dump(residual_after)
    normalized_before, normalized_after = copy.deepcopy(trees["before"]), copy.deepcopy(residual_after)
    if not exact_residual_equal:
        constrain_import_order(normalized_before, normalized_after, "Module")
    modulo_import_equal = dump(normalized_before) == dump(normalized_after)
    require(modulo_import_equal, "whole-app residual canonical AST inequality remains after disclosed import-order constraints")
    require(EFFECTS["source_write_attempts"] == EFFECTS["product_import_attempts"] == EFFECTS["other_effect_attempts"] == 0, "forbidden effect observed")
    return {"status": "PASS_SCOPED_STATIC_METADATA_RECERTIFICATION", "run_count": 1,
        "input_sources": {label: {"path": str(PATHS[label]), **pin(data)} for label, data in raw.items()},
        "current_equals_after_exact_bytes": True, "exact_class_count_each": 1, "exact_method_count_each": 1,
        "exact_guard_count": guard_counts, "original_assignment_unchanged": True, "original_return_unchanged": True,
        "assignment_AST": dump(assignment), "added_guard_AST": dump(guard), "return_AST": dump(before_method.body[-1]),
        "provenance": {label: {"method_line": method.lineno, "tail": [{"line": node.lineno, "end_line": node.end_lineno, "AST": dump(node)} for node in method.body[-(2 if label == "before" else 3):]]} for label, method in methods.items()},
        "transformation": "deep-copy after tree; remove only exact new guard; preserve assignment/return/names/attributes/all other non-import statements",
        "whole_app_exact_residual_AST_equal": exact_residual_equal,
        "whole_app_residual_AST_equal_modulo_disclosed_import_order": modulo_import_equal,
        "canonical_AST_sha256_before": hashlib.sha256(dump(normalized_before).encode()).hexdigest(),
        "canonical_AST_sha256_after": hashlib.sha256(dump(normalized_after).encode()).hexdigest(),
        "import_normalization_used": not exact_residual_equal,
        "import_scope_reports": IMPORT_SCOPES,
        "changed_import_scope_count": sum(item["order_changed"] for item in IMPORT_SCOPES),
        "source_write_count": 0, "product_import_count": 0, "runtime_or_test_execution_count": 0,
        "preplan_corrected_or_provisional_retroactively_authorized": False,
        "audit": dict(EFFECTS)}

try:
    result = compare()
    exit_code = 0
except Exception as error:
    result = {"status": "REQUEST_NEXT_ASTRA_PLAN", "run_count": 1, "error_type": type(error).__name__,
              "error": str(error), "import_scope_reports": IMPORT_SCOPES, "audit": dict(EFFECTS),
              "source_write_count": EFFECTS["source_write_attempts"], "product_import_count": EFFECTS["product_import_attempts"]}
    traceback.print_exc()
    exit_code = 1
with RESULT_PATH.open("x", encoding="utf-8") as handle:
    result["audit"] = dict(EFFECTS)
    json.dump(result, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
print(json.dumps(result, ensure_ascii=False))
raise SystemExit(exit_code)
