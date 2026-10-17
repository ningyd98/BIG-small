"""R125 single bounded source delta proof; never import or execute product."""
from pathlib import Path
import ast
import hashlib
import io
import json
import tokenize

BASE = Path(__file__).resolve().parent
ROUND = BASE.parent
ROOT = Path.cwd()
plan = json.loads((ROUND / "plan.json").read_text())
OLD = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round113-p6-operational-runtime-closure-20261008/implementation/stage-a/stopped-ruff/source"
allowed = plan["allowed_paths"]


def digest(value):
    return hashlib.sha256(value).hexdigest()


def tree(source):
    return ast.parse(source, type_comments=True)


def dump(node):
    for item in ast.walk(node):
        if isinstance(item, ast.TypeIgnore):
            item.lineno = 0
    return ast.dump(node, include_attributes=False)


def anchors(source):
    parsed = tree(source)
    scopes = [n for n in ast.walk(parsed) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    result = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        owners = sorted((n for n in scopes if n.lineno <= token.start[0] <= n.end_lineno), key=lambda n: n.lineno)
        result.append({"scope": [n.name for n in owners], "text": token.string})
    return result


def constants(node):
    return [(type(n.value).__name__, repr(n.value)) for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, (str, bytes))]


def sql_constants(node):
    result = []
    for item in ast.walk(node):
        if isinstance(item, ast.Constant) and isinstance(item.value, str):
            text = item.value
            if any(word in text.upper() for word in ("SELECT ", "UPDATE ", "INSERT ", "DELETE ", "CREATE TABLE", "ALTER TABLE")):
                result.append({"repr": repr(text), "utf8_sha256": digest(text.encode()), "bytes": len(text.encode())})
    return result


def normalize_old_sqlite(parsed):
    expected = {"_P": 'ParamSpec("_P")', "_R": 'TypeVar("_R")'}
    removed = set()
    body = []
    for node in parsed.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in expected:
            name = node.targets[0].id
            assert dump(node.value) == dump(ast.parse(expected[name], mode="eval").body)
            assert name not in removed
            removed.add(name)
            continue
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            aliases = [a for a in node.names if a.name in {"ParamSpec", "TypeVar"}]
            assert {(a.name, a.asname) for a in aliases} == {("ParamSpec", None), ("TypeVar", None)}
            node.names = [a for a in node.names if a.name not in {"ParamSpec", "TypeVar"}]
        body.append(node)
    assert removed == set(expected)
    parsed.body = body
    writer = next(n for n in body if isinstance(n, ast.FunctionDef) and n.name == "_job_writer")
    assert writer.type_params == []
    return parsed


def normalize_new_sqlite(parsed):
    assert not any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {"_P", "_R"} for t in n.targets) for n in parsed.body)
    typing = next(n for n in parsed.body if isinstance(n, ast.ImportFrom) and n.module == "typing")
    assert [(a.name, a.asname) for a in typing.names] == [("Any", None), ("cast", None)]
    writer = next(n for n in parsed.body if isinstance(n, ast.FunctionDef) and n.name == "_job_writer")
    assert len(writer.type_params) == 2
    p, r = writer.type_params
    assert isinstance(p, ast.ParamSpec) and p.name == "_P"
    assert isinstance(r, ast.TypeVar) and r.name == "_R" and r.bound is None
    assert getattr(p, "default_value", None) is None and getattr(r, "default_value", None) is None
    writer.type_params = []
    return parsed


records = []
for name in allowed:
    before = (OLD / name).read_text()
    after = (ROOT / name).read_text()
    preformat = (BASE / "preformatter" / name).read_text()
    assert dump(tree(preformat)) == dump(tree(after)), name + " formatter AST/type-comments drift"
    assert anchors(preformat) == anchors(after), name + " formatter comment anchor drift"
    old, new = tree(before), tree(after)
    old_sql, new_sql = sql_constants(old), sql_constants(new)
    assert old_sql == new_sql, name + " SQL UTF8 constant drift"
    if name.endswith("sqlite_repository.py"):
        old = normalize_old_sqlite(old)
        new = normalize_new_sqlite(new)
    assert dump(old) == dump(new), name + " forbidden AST/type-comments drift"
    assert constants(old) == constants(new), name + " ordered string/bytes constant drift"
    assert anchors(before) == anchors(after), name + " anchored comments/type-ignore drift"
    records.append({"path": name, "old_sha256": digest(before.encode()), "new_sha256": digest(after.encode()),
                    "formatter_AST_type_comments": True, "normalized_full_AST_equal": True,
                    "ordered_constants_equal": True, "anchored_comments_equal": True,
                    "old_SQL_constants": old_sql, "new_SQL_constants": new_sql})

untouched = []
for pin in plan["inputs"]:
    name = pin["path"]
    if name.startswith("src/") and name not in allowed:
        raw = (ROOT / name).read_bytes()
        assert digest(raw) == pin["sha256"] and len(raw) == pin["bytes"]
        untouched.append(pin)
assert len(untouched) == 4
proof_pin = next(p for p in plan["inputs"] if p["path"].endswith("stage-a/scope_proof/proof.json"))
assert digest((ROOT / proof_pin["path"]).read_bytes()) == proof_pin["sha256"]
report = {"status": "PASS_BOUNDED_SOURCE_DELTA_ONLY", "records": records, "four_other_sources_unchanged": untouched,
          "original_scope_proof_unchanged": proof_pin, "original_RED_old_draft": True,
          "runtime_verdict": False, "acceptance": "LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO pending remaining checks and independent review"}
(BASE / "delta_proof" / "proof.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "repaired_sources": len(records), "unchanged_sources": len(untouched)}))
