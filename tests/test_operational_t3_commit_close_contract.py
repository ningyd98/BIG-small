"""Real threaded SQLite instrumentation; stand-ins grant no live lease authority."""
import sqlite3
import threading
import traceback
from types import SimpleNamespace

import pytest

from tests import test_operational_runtime_closure as closure


@pytest.mark.parametrize("query_error", [False, True])
def test_commit_close_observer_keeps_thread_affinity_and_closes_resources(
    monkeypatch, tmp_path, query_error
):
    path = tmp_path / "real-observer.db"

    class JobConnection(sqlite3.Connection):
        pass

    main = sqlite3.connect(path, factory=JobConnection)
    main.row_factory = sqlite3.Row
    if query_error:
        main.execute("CREATE TABLE unrelated(value INTEGER)")
        main.execute("INSERT INTO unrelated VALUES(0)")
    else:
        main.execute("CREATE TABLE simulation_operational_leases_v1(job_id TEXT, terminal_reason TEXT)")
        main.execute("INSERT INTO simulation_operational_leases_v1 VALUES('unit-job', 'running')")
    main.commit()
    repo = SimpleNamespace(database_path=path, _transactions=threading.local())
    session = SimpleNamespace(job_id="unit-job")
    observations, results, evidence = [], {}, {}
    original_execute = JobConnection.execute
    original_module = closure.sqlite3

    def tracking_connect(*args, **kwargs):
        connection = sqlite3.connect(*args, **kwargs)
        observations.append((threading.get_ident(), connection))
        return connection

    def threaded_sql():
        writer = sqlite3.connect(path, factory=JobConnection)
        repo._transactions.connection = writer
        try:
            if query_error:
                writer.execute("BEGIN")
                writer.execute("UPDATE unrelated SET value=1")
                try:
                    writer.execute("COMMIT")
                except sqlite3.OperationalError as error:
                    results["observer_query_error"] = str(error)
                else:
                    raise AssertionError("real observer SELECT should fail for missing lease table")
                assert evidence["fired"] is False
                assert writer.execute("SELECT 1").fetchone()[0] == 1
            else:
                # A real committed terminal row on a foreign connection cannot trigger this writer's fault.
                with sqlite3.connect(path, factory=JobConnection) as foreign:
                    foreign.execute("BEGIN")
                    foreign.execute("UPDATE simulation_operational_leases_v1 SET terminal_reason=?",
                                    ("owned publication completed",))
                    foreign.execute("COMMIT")
                    assert evidence["fired"] is False
                    assert foreign.execute("SELECT 1").fetchone()[0] == 1
                foreign.close()
                writer.execute("BEGIN")
                writer.execute("UPDATE simulation_operational_leases_v1 SET terminal_reason='running'")
                writer.execute("COMMIT")
                assert evidence["fired"] is False
                assert writer.execute("SELECT 1").fetchone()[0] == 1
                writer.execute("BEGIN")
                writer.execute("UPDATE simulation_operational_leases_v1 SET terminal_reason=?",
                               ("owned publication completed",))
                try:
                    writer.execute("COMMIT")
                except sqlite3.ProgrammingError as error:
                    results["terminal_close_error"] = str(error)
                    assert "closed database" in str(error).lower()
                else:
                    raise AssertionError("same committed writer must really be closed")
                assert evidence["fired"] is True
                event, = evidence["events"]
                assert event["resource_id"] == id(writer)
                assert event["thread"] == threading.get_ident()
                assert event["in_transaction_after_commit"] is False
                assert event["durable_operational_row"]["terminal_reason"] == "owned publication completed"
                assert evidence["actual_closed_connection_error"]["message"] == results["terminal_close_error"]
            # Probe in the creating thread: an affinity error must never count as evidence of closure.
            assert len(observations) == (1 if query_error else 2)
            for owner_thread, observer in observations:
                assert owner_thread == threading.get_ident()
                with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
                    observer.execute("SELECT 1")
            results["observer_closed_on_owner_thread"] = True
        except BaseException as error:
            results["unexpected"] = {"type": type(error).__name__, "message": str(error),
                                     "traceback": traceback.format_exc()}
        finally:
            for _, observer in observations:
                observer.close()
            writer.close()

    try:
        with monkeypatch.context() as scoped:
            # Replace this test module's binding only; the global sqlite3 module and defaults stay real.
            scoped.setattr(closure, "sqlite3", SimpleNamespace(
                connect=tracking_connect, Row=sqlite3.Row, ProgrammingError=sqlite3.ProgrammingError
            ))
            closure._b_t3_terminal_fault(scoped, None, repo, session, {"job": main},
                                          "commit_close", evidence)
            thread = threading.Thread(target=threaded_sql, name="unit-real-commit-observer")
            thread.start()
            thread.join(timeout=10)
            assert not thread.is_alive(), "real SQLite instrumentation thread did not finish"
            assert "unexpected" not in results, results.get("unexpected")
            assert results["observer_closed_on_owner_thread"] is True
            assert main.execute("SELECT 1").fetchone()[0] == 1
            if query_error:
                assert "no such table" in results["observer_query_error"]
                assert main.execute("SELECT value FROM unrelated").fetchone()[0] == 1
            else:
                row = main.execute("SELECT * FROM simulation_operational_leases_v1").fetchone()
                assert row["terminal_reason"] == "owned publication completed"
    finally:
        main.close()
        assert JobConnection.execute is original_execute
        assert closure.sqlite3 is original_module
