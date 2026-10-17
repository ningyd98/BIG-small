"""R233 single bounded read-only retained SQLite diagnostic; no product imports."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import sqlite3
import sys
import traceback

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round233-p6-t2-recovery-red-bootstrap-path-20261015"
PLAN_SHA = "f1999ce3e5f2740614f162d6d869b2e498a641d576c0b38aa22190e62ef0200b"
SLOT = "R233-retained-database-diagnostic-once"
CAP = 8388608
CHECKS = []
QUERIES = []
CONNECTIONS = []
BODY = {"schema_version": "bigsmall.r233.retained-diagnostic.v1", "databases": [],
        "checks": CHECKS, "queries": QUERIES, "connections": CONNECTIONS,
        "errors": [], "root_cause": "unresolved; persisted rows are evidence, not a causal verdict",
        "product_execution": False, "T2_complete": False, "legal_RED": False}


class BoundExceeded(RuntimeError):
    pass


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def pin(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def identity(record):
    return {key: record[key] for key in ("path", "bytes", "sha256")}


def require(name, passed):
    CHECKS.append({"name": name, "passed": bool(passed)})
    if not passed:
        raise ValueError(name)


def verify(record, label):
    require(label, pin(Path(record["path"])) == identity(record))


def write(path, value):
    data = encoded(value)
    if len(data) > CAP:
        raise BoundExceeded("output exceeds 8 MiB: " + str(path))
    with path.open("xb") as stream:
        stream.write(data)
    return pin(path)


def checked_append(target, value):
    target.append(value)
    if len(encoded(BODY)) > CAP - 65536:
        target.pop()
        raise BoundExceeded("diagnostic output budget; final 64 KiB reserved for outcome")


def cell(value):
    if isinstance(value, bytes):
        return {"sqlite_type": "BLOB", "bytes": len(value),
                "sha256": hashlib.sha256(value).hexdigest(), "content_inspected": False}
    if isinstance(value, str):
        if len(value.encode("utf-8")) > 65536:
            raise BoundExceeded("TEXT field exceeds 65536 UTF-8 bytes")
        return value
    if value is None or type(value) is int:
        return value
    if type(value) is float:
        return value if math.isfinite(value) else {"sqlite_type": "REAL", "exact_hex": value.hex()}
    raise TypeError("unexpected SQLite scalar: " + type(value).__name__)


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def sidecars_absent(observation, stage):
    for database in observation["databases"]:
        for row in database["sidecars"]:
            path = Path(row["path"])
            require(stage + ".sidecar_absent." + str(path),
                    row["exists"] is False and not path.exists() and not path.is_symlink())


def fixed_inputs(gate, stage):
    for index, record in enumerate(gate["input_records"]):
        verify(record, stage + ".fixed." + str(index))


def statement(connection, sql):
    if len(QUERIES) >= 66:
        raise BoundExceeded("66 SQL statement maximum")
    record = {"ordinal": len(QUERIES) + 1, "sql": sql, "execute_attempted": True,
              "execute_returned": False, "error": None}
    QUERIES.append(record)
    try:
        cursor = connection.execute(sql)
    except BaseException as error:
        record["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    record["execute_returned"] = True
    return cursor


def fetched(connection, sql, maximum):
    cursor = statement(connection, sql)
    try:
        if len(cursor.description or ()) > 64:
            raise BoundExceeded("64 columns maximum")
        return cursor.fetchmany(maximum)
    finally:
        cursor.close()


def authorizer_for(allowlist):
    readable = set(allowlist) | {"sqlite_master", "sqlite_schema"}
    def authorize(action, first, second, database, trigger):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ and first in readable and database == "main":
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_PRAGMA and first.lower() == "table_info" and second in allowlist:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    return authorize


def diagnose_database(database, plan):
    path = Path(database["pin"]["path"])
    require("regular_exact_database." + str(path),
            path.is_file() and not path.is_symlink() and path.resolve() == path)
    verify(database["pin"], "database_before." + str(path))
    allowlist = plan["database_contract"]["allowed_tables"][database["kind"]]
    result = {"case_ordinal": database["case_ordinal"], "kind": database["kind"],
              "database": database["pin"], "schema": [], "tables": []}
    BODY["databases"].append(result)
    lifecycle = {"path": str(path), "open_attempted": True, "opened": False,
                 "closed": False, "progress_callbacks": 0, "exception": None,
                 "close_exception": None, "query_only": None}
    CONNECTIONS.append(lifecycle)
    connection = None
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1",
                                     uri=True, timeout=0.0)
        lifecycle["opened"] = True
        def progress():
            lifecycle["progress_callbacks"] += 1
            return int(lifecycle["progress_callbacks"] > 1000)
        connection.set_progress_handler(progress, 1000)
        cursor = statement(connection, "PRAGMA query_only=ON")
        cursor.close()
        lifecycle["query_only"] = "ON set by the exact connection-local pragma"
        connection.set_authorizer(authorizer_for(allowlist))
        schema_rows = fetched(connection, plan["database_contract"]["schema_query"], 129)
        for row in schema_rows[:128]:
            checked_append(result["schema"], [cell(value) for value in row])
        if len(schema_rows) > 128:
            raise BoundExceeded("128 schema records maximum")
        schema = {row[0]: row for row in schema_rows}
        for name in allowlist:
            table = {"name": name, "status": "MISSING", "columns": [], "rows": []}
            result["tables"].append(table)
            if name not in schema:
                continue
            entry = schema[name]
            if entry[1] != "table" or not isinstance(entry[2], str) or not entry[2].lstrip().upper().startswith("CREATE TABLE"):
                table["status"] = "PRESENT_NOT_ORDINARY_TABLE_NOT_EXECUTED"
                continue
            table["status"] = "READ_STARTED"
            columns = fetched(connection, "PRAGMA table_info(" + quote(name) + ")", 65)
            for row in columns[:64]:
                checked_append(table["columns"], [cell(value) for value in row])
            if len(columns) > 64:
                raise BoundExceeded("64 table columns maximum: " + name)
            rows = fetched(connection, "SELECT * FROM " + quote(name) + " LIMIT 65", 65)
            for row in rows[:64]:
                checked_append(table["rows"], [cell(value) for value in row])
            if len(rows) > 64:
                table["status"] = "ROW_LIMIT_EXCEEDED"
                raise BoundExceeded("64 rows maximum: " + name)
            table["status"] = "COMPLETE_BOUNDED_READ"
    except BaseException as error:
        lifecycle["exception"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        if connection is not None:
            try:
                connection.close()
                lifecycle["closed"] = True
            except BaseException as error:
                lifecycle["close_exception"] = {"type": type(error).__name__, "message": str(error)}
                raise


def main():
    gate_bytes = (D / "script-gate.json").read_bytes()
    ledger_bytes = (D / "root-command-ledger.json").read_bytes()
    gate = json.loads(gate_bytes)["commands"][SLOT]
    ledger = json.loads(ledger_bytes)["commands"][SLOT]
    plan = json.loads((D / "plan.json").read_bytes())
    observation = json.loads((D / "input-observation.json").read_bytes())
    complete = False
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("R233 diagnostic inner 110 seconds")))
    signal.alarm(110)
    try:
        require("cwd", Path.cwd() == ROOT)
        require("plan_SHA", pin(D / "plan.json")["sha256"] == PLAN_SHA)
        require("exact_actual_argv", sys.argv == plan["execution"]["argv"][1:])
        require("fully_reviewed_source", gate["state"] == "APPROVED" and gate["full_source_reviewed"] is True)
        require("single_ROOT_reservation", ledger["state"] == "RESERVED_BY_ROOT" and ledger["used"] == 1 and ledger["remaining"] == 0 and ledger["reservation_id"] == gate["reservation_id"])
        require("finite_argv_env", gate["argv"] == plan["execution"]["argv"] and gate["finite_env"] == plan["execution"]["finite_env"] and {k: os.environ.get(k) for k in gate["finite_env"]} == gate["finite_env"])
        require("own_source", gate["source"]["path"] == str(Path(__file__).absolute()))
        verify(gate["source"], "own_source_pin")
        fixed_inputs(gate, "before")
        require("six_exact_databases", len(observation["databases"]) == 6)
        require("fixed_output_paths_absent", all(not Path(plan["execution"]["outputs"][name]).exists() for name in ("invocation", "diagnostic", "result")))
        sidecars_absent(observation, "before")
        invocation = {"schema_version": "bigsmall.r233.diagnostic-invocation.v1",
                      "argv": gate["argv"], "cwd": str(ROOT), "finite_env": gate["finite_env"],
                      "reservation_id": gate["reservation_id"], "source": gate["source"],
                      "gate_before_base64": base64.b64encode(gate_bytes).decode(),
                      "ledger_before_base64": base64.b64encode(ledger_bytes).decode(),
                      "transport": gate["transport"], "attempt": 1, "retry": 0,
                      "independent_tool_stdout": None, "independent_tool_stderr": None}
        write(Path(plan["execution"]["outputs"]["invocation"]), invocation)
        require("immediate_gate_ledger_CAS", (D / "script-gate.json").read_bytes() == gate_bytes and (D / "root-command-ledger.json").read_bytes() == ledger_bytes)
        for database in observation["databases"]:
            diagnose_database(database, plan)
        complete = True
    except BaseException as error:
        BODY["errors"].append({"type": type(error).__name__, "message": str(error),
                               "traceback": traceback.format_exc()})
    finally:
        signal.alarm(0)
        try:
            fixed_inputs(gate, "after")
            sidecars_absent(observation, "after")
            require("gate_ledger_unchanged", (D / "script-gate.json").read_bytes() == gate_bytes and (D / "root-command-ledger.json").read_bytes() == ledger_bytes)
            require("all_opened_connections_closed", all(not row["opened"] or row["closed"] for row in CONNECTIONS))
        except BaseException as error:
            complete = False
            BODY["errors"].append({"phase": "post_invariance", "type": type(error).__name__,
                                   "message": str(error), "traceback": traceback.format_exc()})
    complete = complete and not BODY["errors"] and all(row["passed"] for row in CHECKS)
    BODY.update(complete=complete, status="COMPLETE_BOUNDED_READ_CAUSE_UNRESOLVED" if complete else "INCOMPLETE_NO_RETRY",
                SQL_statements_attempted=len(QUERIES), connection_attempts=len(CONNECTIONS))
    diagnostic = write(Path(plan["execution"]["outputs"]["diagnostic"]), BODY)
    exit_code = 0 if complete else 1
    result = write(Path(plan["execution"]["outputs"]["result"]),
                   {"schema_version": "bigsmall.r233.diagnostic-result.v1",
                    "exit_code": exit_code, "attempt": 1, "retry": 0,
                    "diagnostic": diagnostic, "complete_bounded_read": complete,
                    "SQL_statements_attempted": len(QUERIES), "connections_opened": sum(row["opened"] for row in CONNECTIONS),
                    "connections_closed": sum(row["closed"] for row in CONNECTIONS),
                    "all_checks_passed": all(row["passed"] for row in CHECKS),
                    "checks": len(CHECKS), "product_execution": False, "T2_complete": False})
    summary = json.dumps({"status": BODY["status"], "exit_code": exit_code,
                          "diagnostic": diagnostic, "result": result,
                          "cause": "unresolved pending evidence review", "T2_complete": False},
                         ensure_ascii=False)
    if len(summary.encode("utf-8")) > 6000:
        raise BoundExceeded("stdout summary exceeds 6000 bytes")
    print(summary)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
