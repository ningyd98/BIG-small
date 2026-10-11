"""Single R126 lexical/alpha source check; no product execution."""
from pathlib import Path
import ast
import hashlib
import io
import json
import tokenize

BASE = Path(__file__).resolve().parent
ROOT = Path.cwd()
plan = json.loads((BASE.parent / "plan.json").read_text())
name = plan["allowed_edit"]["path"]
old_path = ROOT / plan["original_failure"]["canonical_freeze"] / "source" / name
old = old_path.read_text()
new = (ROOT / name).read_text()
ot = ast.parse(old, type_comments=True)
nt = ast.parse(new, type_comments=True)
ow = next(n for n in ot.body if isinstance(n, ast.FunctionDef) and n.name == "_job_writer")
nw = next(n for n in nt.body if isinstance(n, ast.FunctionDef) and n.name == "_job_writer")
assert len(ow.type_params) == len(nw.type_params) == 2
assert isinstance(nw.type_params[0], ast.ParamSpec) and nw.type_params[0].name == "P"
assert isinstance(nw.type_params[1], ast.TypeVar) and nw.type_params[1].name == "R"
assert nw.type_params[1].bound is None
assert all(getattr(p, "default_value", None) is None for p in nw.type_params)

# No conflicting local, argument, class, function or nested type binding can hide P/R.
for scope in (ow, nw):
    for node in ast.walk(scope):
        assert not (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id in {"P", "R", "_P", "_R"})
        assert not (isinstance(node, ast.arg) and node.arg in {"P", "R", "_P", "_R"})
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node is not scope:
            assert node.name not in {"P", "R", "_P", "_R"} and not node.type_params

before_tokens = list(tokenize.generate_tokens(io.StringIO(old).readline))
after_tokens = list(tokenize.generate_tokens(io.StringIO(new).readline))
assert len(before_tokens) == len(after_tokens)
changes = []
old_lines = old.splitlines(True)
expected_lines = old_lines.copy()
replacements = {}
for a, b in zip(before_tokens, after_tokens, strict=True):
    assert a.type == b.type
    if a.string != b.string:
        assert a.type == tokenize.NAME and a.string in {"_P", "_R"}
        assert b.string == a.string[1:]
        assert ow.lineno <= a.start[0] <= ow.end_lineno
        assert nw.lineno <= b.start[0] <= nw.end_lineno
        replacements.setdefault(a.start[0] - 1, []).append((a.start[1], a.end[1], b.string))
        changes.append({"line": a.start[0], "column": a.start[1], "old": a.string, "new": b.string})
for row, edits in replacements.items():
    text = expected_lines[row]
    for start, end, replacement in reversed(edits):
        text = text[:start] + replacement + text[end:]
    expected_lines[row] = text
assert "".join(expected_lines) == new, "whitespace/comment/literal or unapproved token changed"
assert changes

for node in ast.walk(nw):
    if isinstance(node, ast.Name) and node.id in {"P", "R"}:
        node.id = "_" + node.id
for parameter in nw.type_params:
    parameter.name = "_" + parameter.name
assert ast.dump(ot, include_attributes=False) == ast.dump(nt, include_attributes=False)
old_constants = [n.value for n in ast.walk(ot) if isinstance(n, ast.Constant) and isinstance(n.value, (str, bytes))]
new_constants = [n.value for n in ast.walk(nt) if isinstance(n, ast.Constant) and isinstance(n.value, (str, bytes))]
assert old_constants == new_constants
preserved = []
for pin in plan["inputs"]:
    if pin["path"] == name:
        continue
    raw = (ROOT / pin["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pin["sha256"] and len(raw) == pin["bytes"]
    preserved.append(pin)
owned_unchanged = [p for p in preserved if p["path"].startswith(("src/", "tests/"))]
assert len(owned_unchanged) == 5
prior_delta_pin = next(p for p in plan["inputs"] if p["path"].endswith("stopped-up049/delta_proof/proof.json"))
prior_delta = json.loads((ROOT / prior_delta_pin["path"]).read_text())
scope_pin = prior_delta["original_scope_proof_unchanged"]
scope_raw = (ROOT / scope_pin["path"]).read_bytes()
assert hashlib.sha256(scope_raw).hexdigest() == scope_pin["sha256"] and len(scope_raw) == scope_pin["bytes"]
sql = [{"repr": repr(s), "utf8_sha256": hashlib.sha256(s.encode()).hexdigest()}
       for s in old_constants if isinstance(s, str) and any(w in s.upper() for w in ("SELECT ", "UPDATE ", "INSERT ", "CREATE TABLE"))]
report = {"status": "PASS_ALPHA_TOKEN_DELTA_ONLY", "old_sha256": hashlib.sha256(old.encode()).hexdigest(),
          "new_sha256": hashlib.sha256(new.encode()).hexdigest(), "token_changes": changes,
          "whitespace_comments_literals_unchanged": True, "alpha_normalized_full_AST_type_comments_equal": True,
          "ordered_constants_equal": True, "SQL_constant_UTF8": sql, "preserved_inputs": preserved,
          "original_R113_scope_proof_preserved": scope_pin,
          "held_original_commands": plan["early_review_hold"]["effect"], "runtime_verdict": False,
          "reflective_type_names_intentionally_changed": True}
(BASE / "delta_proof" / "proof.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "name_changes": len(changes), "unchanged_other_sources": 5}))
