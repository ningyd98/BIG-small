"""Instrumentation contracts only; delegate spies confer no live lease authority."""
from types import SimpleNamespace

import pytest

from cloud_edge_robot_arm.simulation_runtime.operational_lease import OperationalLeaseSession
from tests.test_operational_runtime_closure import (
    _b_t3_observe_invalidation,
    _b_t3_terminal_fault,
    _b_t3_terminal_patch_owner,
)


@pytest.mark.parametrize("exceptional_exit", [False, True])
def test_terminal_diagnostic_and_fault_restore_identity(monkeypatch, exceptional_exit):
    calls = []

    def delegate(actual, reason):
        calls.append((actual, reason))

    monkeypatch.setattr(OperationalLeaseSession, "invalidate", delegate)
    original = OperationalLeaseSession.invalidate
    session = SimpleNamespace(wait_cap=0.1)
    worker = SimpleNamespace(_operational_lease_session=session)
    sentinel = RuntimeError("original body exception")
    for _ in range(2):
        diagnostics = {"invalidations": []}
        observed = SimpleNamespace(release_events=[])
        evidence = {}
        caught = None
        try:
            with _b_t3_terminal_patch_owner(monkeypatch) as (owner, configure):
                with monkeypatch.context() as scoped:
                    _b_t3_observe_invalidation(scoped, worker, diagnostics)
                    configure(scoped, worker, None, None, None, {})
                    _b_t3_terminal_fault(owner["scoped"], observed, None, session, {},
                                         "confirm_timeout", evidence)
                    OperationalLeaseSession.invalidate(session, "unit diagnostic delegate")
                    assert evidence["fired"] is False  # This unit contract does not execute a broker.
                    if exceptional_exit:
                        raise sentinel
        except RuntimeError as error:
            caught = error
        assert OperationalLeaseSession.invalidate is original
        assert caught is (sentinel if exceptional_exit else None)
        if caught is not None:
            assert any(frame.tb_frame.f_code.co_name == "test_terminal_diagnostic_and_fault_restore_identity"
                       for frame in _traceback_frames(caught))
        assert diagnostics["invalidations"] == [
            {"reason": "unit diagnostic delegate", "active_exception": None}
        ]
    assert calls == [(session, "unit diagnostic delegate")] * 2


def _traceback_frames(error):
    frame = error.__traceback__
    while frame is not None:
        yield frame
        frame = frame.tb_next


def test_diagnostic_delegates_once_and_preserves_return_and_original_exception(monkeypatch):
    session, other, returned = object(), object(), object()
    worker = SimpleNamespace(_operational_lease_session=session)
    diagnostics = {"invalidations": []}
    calls = []
    sentinel = RuntimeError("delegate failure")

    def delegate(actual, reason):
        calls.append((actual, reason))
        if reason == "delegate failure":
            raise sentinel
        return returned

    monkeypatch.setattr(OperationalLeaseSession, "invalidate", delegate)
    original = OperationalLeaseSession.invalidate
    with monkeypatch.context() as scoped:
        _b_t3_observe_invalidation(scoped, worker, diagnostics)
        assert OperationalLeaseSession.invalidate(other, "other receiver") is returned
        try:
            raise LookupError("active original exception")
        except LookupError:
            assert OperationalLeaseSession.invalidate(session, "target receiver") is returned
        with pytest.raises(RuntimeError) as raised:
            OperationalLeaseSession.invalidate(session, "delegate failure")
        assert raised.value is sentinel
        assert any(frame.tb_frame.f_code is delegate.__code__ for frame in _traceback_frames(sentinel))
    assert OperationalLeaseSession.invalidate is original
    assert calls == [(other, "other receiver"), (session, "target receiver"), (session, "delegate failure")]
    assert len(diagnostics["invalidations"]) == 2
    active = diagnostics["invalidations"][0]["active_exception"]
    assert active["type"] == "LookupError" and active["message"] == "active original exception"
    assert "raise LookupError" in active["traceback"]
    assert diagnostics["invalidations"][1] == {"reason": "delegate failure", "active_exception": None}
