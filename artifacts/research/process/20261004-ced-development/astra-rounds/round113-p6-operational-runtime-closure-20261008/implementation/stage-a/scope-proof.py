"""Single R113 scope/format/writer proof. No product imports or runtime verdict."""
from pathlib import Path
import ast
import hashlib
import io
import json
import tokenize

ROOT = Path.cwd()
BASE = Path(__file__).resolve().parent
ROUND = BASE.parent.parent
plan = json.loads((ROUND / "plan.json").read_text())
owned = plan["scope"]["owned_paths"]
assert len(owned) == 6
checks = []

def imports(tree):
    result = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            result.extend((type(node).__name__, getattr(node, "module", None),
                           getattr(node, "level", 0), alias.name, alias.asname)
                          for alias in node.names)
    return sorted(result, key=str)

class WithoutImports(ast.NodeTransformer):
    def visit_Import(self, node):
        return None
    def visit_ImportFrom(self, node):
        return None
    def visit_TypeIgnore(self, node):
        node.lineno = 0
        return node

def comments(source):
    return [token.string for token in tokenize.generate_tokens(io.StringIO(source).readline)
            if token.type == tokenize.COMMENT]

for name in owned:
    before = (BASE / "semantic-before-format" / name).read_text()
    after = (ROOT / name).read_text()
    old_tree = ast.parse(before, type_comments=True)
    new_tree = ast.parse(after, type_comments=True)
    assert imports(old_tree) == imports(new_tree), name + " changed import names/aliases"
    assert ast.dump(WithoutImports().visit(old_tree), include_attributes=False) == (
        ast.dump(WithoutImports().visit(new_tree), include_attributes=False)
    ), name + " formatting changed nonimport AST/type comments"
    assert comments(before) == comments(after), name + " changed comments"
    checks.append({"path": name, "nonimport_AST_and_import_aliases_comments": True,
                   "sha256": hashlib.sha256(after.encode()).hexdigest()})

pins = json.loads((ROUND / "input-pins.json").read_text())["pins"]
protected = []
for pin in pins:
    name = pin["path"]
    if name in owned:
        continue
    raw = (ROOT / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pin["sha256"], name + " protected SHA drift"
    if "bytes" in pin:
        assert len(raw) == pin["bytes"], name + " protected bytes drift"
    protected.append(pin)

source = (ROOT / owned[0]).read_text()
worker = (ROOT / owned[3]).read_text()
sql_source = (ROOT / owned[2]).read_text()
repo_tree = ast.parse(sql_source, type_comments=True)
repo_class = next(node for node in repo_tree.body if isinstance(node, ast.ClassDef)
                  and node.name == "SQLiteSimulationJobRepository")
methods = {node.name: node for node in repo_class.body if isinstance(node, ast.FunctionDef)}
writers = ["create_job", "update_status_cas", "request_cancel", "heartbeat_lease", "release_lease",
           "expire_leases", "append_event", "save_metrics", "save_artifacts", "create_batch",
           "start_attempt", "finish_attempt", "finish_open_attempts", "retry_job",
           "terminate_orphaned_operational_attempts"]
writer_map = []
for name in writers:
    function = methods[name]
    assert any(isinstance(d, ast.Name) and d.id == "_job_writer"
               for d in function.decorator_list), name + " missing shared guard wrapper"
    writer_map.append({"method": name, "line": function.lineno,
                       "guard": "_job_writer -> _writer_call -> publication_guard",
                       "transaction": "same registered connection via _connect; operational view/CAS/ack or terminal revoke; legacy explicit BEGIN/COMMIT",
                       "runtime_verified": False})
for name in ["_update_status_cas_unlocked", "_request_cancel_unlocked", "_acquire_lease_unlocked",
             "_retry_job_unlocked"]:
    assert "_require_active_writer" in ast.unparse(methods[name]), name + " helper bypass"
assert "publication_guard" in ast.unparse(methods["acquire_lease"])
assert "BEGIN IMMEDIATE" in ast.unparse(methods["_acquire_operational"])
assert "COMMIT" in ast.unparse(methods["_commit_operational_proposal"])
assert "rowcount != 1" in ast.unparse(methods["_commit_operational_proposal"])
assert "publication_guard" in ast.unparse(methods["_initialize"])
assert "simulation_operational_leases_v1" in sql_source
assert "durable_phase='ACTIVE'" not in sql_source
assert "_transactions.commit" in sql_source and "_make_ack" in sql_source
sql_sites = []
for name, node in methods.items():
    for literal in ast.walk(node):
        if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
            text = literal.value.strip().upper()
            if any(text.startswith(prefix) for prefix in (
                "INSERT ", "UPDATE ", "DELETE ", "CREATE ", "ALTER "
            )):
                sql_sites.append({"method": name, "line": literal.lineno,
                                  "statement": literal.value,
                                  "route": "concrete guarded writer/initialization or private CAS/termination owner",
                                  "runtime_verified": False})
assert sql_sites
lease_tree = ast.parse(source)
lease_class = next(n for n in lease_tree.body if isinstance(n, ast.ClassDef)
                   and n.name == "OperationalLeaseSession")
for node in lease_class.body:
    if isinstance(node, ast.FunctionDef) and node.name in {"_serve", "_decide", "_live"}:
        text = ast.unparse(node)
        for forbidden in ["publication_guard", "_connect(", "connection.execute", "operational_owner", "D_app"]:
            assert forbidden not in text, "broker must not read DB/other owner/locks"
assert '"src/cloud_edge_robot_arm/simulation_runtime/operational_lease.py"' in worker
assert "_heartbeat_lease_scope(session)" in worker and "_worker_lease_scope(session)" in worker
assert "_install_heartbeat_thread(session, heartbeat)" in worker
assert "first_heartbeat.wait" in worker
assert "_prepare_startup(self, job)" in worker and "operational_owner._begin_origin()" in worker
assert "_new_handoff" in worker
assert "LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO" in source

# Exact20 IDs are obtained from source declarations, without pytest collect/import.
tests = (ROOT / owned[5]).read_text()
tree = ast.parse(tests)
nodeids = []
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
        variants = None
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "parametrize":
                variants = ast.literal_eval(next(k.value for k in dec.keywords if k.arg == "ids"))
        nodeids.extend(owned[5] + "::" + node.name + ("[" + value + "]" if value else "")
                       for value in (variants if variants is not None else [None]))
expected = [node for case in plan["A_tests"] for node in case["nodeids"]]
assert nodeids == expected and len(nodeids) == 20
for node in ast.walk(tree):
    if isinstance(node, ast.Attribute):
        assert node.attr not in {"skip", "skipif", "xfail"}, "no qualification skips/xfail"
for forbidden in ["owner.export()", "runtime.operational_owner", "owner.task_deadline", "owner.origin_token"]:
    assert forbidden not in tests
assert "app_clock.begin_event" in tests and "app_clock = runtime._operational_owner.clock" in tests
assert 'owner._startup.job_source + ":task"' in tests and "original_deadline.origin is owner.task_origin" in tests
assert "current.deadline is saved" in tests and "original_token = owner.task_origin_token" in tests
assert "owner = runtime._operational_owner" in tests
assert 'session.propose_locked' in tests and "repo._commit_operational_proposal" in tests
assert '"ROLLBACK"' in tests and "view._connection.close()" in tests
assert '"VALID",' not in tests  # tests may assert genuine verdict, never inject one
# R124: every direct test-owned connect has outer close and inner transaction context.
connection_sites = []
for node in ast.walk(tree):
    if isinstance(node, ast.With):
        for index, item in enumerate(node.items):
            outer = item.context_expr
            if (isinstance(outer, ast.Call) and isinstance(outer.func, ast.Name)
                and outer.func.id == "closing" and len(outer.args) == 1):
                inner = outer.args[0]
                if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                    and isinstance(inner.func.value, ast.Name) and inner.func.value.id == "sqlite3"
                    and inner.func.attr == "connect"):
                    assert isinstance(item.optional_vars, ast.Name) and item.optional_vars.id == "conn"
                    transaction = node.items[index + 1].context_expr
                    assert isinstance(transaction, ast.Name) and transaction.id == "conn"
                    connection_sites.append(node.lineno)
assert len(connection_sites) == 5
assert sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
           and isinstance(n.func.value, ast.Name) and n.func.value.id == "sqlite3"
           and n.func.attr == "connect" for n in ast.walk(tree)) == 5
mapping_paths = [ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds" / round_name / "mapping-change.json"
                 for round_name in ["round122-p6-stage-a-test-api-mapping-20261011",
                                    "round123-p6-test-owner-binding-20261011",
                                    "round124-p6-test-connection-lifecycle-20261011"]]
report = {"status": "PASS_SOURCE_SCOPE_ONLY", "runtime_verdict": False,
          "owned_paths": owned, "semantic_format_checks": checks, "protected_pins": protected,
          "all_writer_mapping": writer_map, "SQL_mutation_sites": sql_sites,
          "special_mapping": [{"method": "acquire_lease", "guard": "publication_guard",
                               "transaction": "_acquire_operational/legacy explicit transaction"},
                              {"method": "_initialize", "guard": "publication_guard",
                               "transaction": "schema initialization; no active writer second connection"}],
          "test_owned_closed_connection_sites": connection_sites,
          "nodeids": nodeids, "count": 20, "mapping_history": [str(p) for p in mapping_paths],
          "original_RED_on_old_draft": True,
          "remaining": ["GREEN20/independent review", "B9 publication migration", "C16 mutation/observer", "D2 native positives"],
          "scope": "LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO; not P6/native/actual/formal"}
(BASE / "scope_proof" / "proof.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "writers": len(writer_map), "SQL_sites": len(sql_sites), "nodes": 20}))
