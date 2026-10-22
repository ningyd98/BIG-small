"""R302 observer bookkeeping contract; real authority remains covered by dual/wait nodes."""

import sys
import threading
from types import SimpleNamespace

from tests import test_operational_runtime_closure as fixture


class _Workers(list):
    def __init__(self, values):
        super().__init__(values)
        self.scans = 0

    def __iter__(self):
        self.scans += 1
        return super().__iter__()


class _Guard:
    def __init__(self, actual):
        self.actual = actual
        self.entries = 0

    def __enter__(self):
        self.entries += 1
        return self.actual.__enter__()

    def __exit__(self, *args):
        return self.actual.__exit__(*args)


class _Worker:
    def __init__(self, *, installed_field):
        self.active_job_id = ""
        self.session_reads = 0
        if installed_field:
            self._operational_lease_session = None

    def __getattribute__(self, name):
        if name == "_operational_lease_session":
            count = object.__getattribute__(self, "session_reads")
            object.__setattr__(self, "session_reads", count + 1)
        return object.__getattribute__(self, name)


class _Thread:
    """Only observer identity/liveness input, never a substitute for a live broker."""

    def __init__(self, ident):
        self.ident = ident
        self.native_id = ident
        self.name = "same-name-does-not-establish-ownership"
        self.alive = True
        self.alive_reads = 0

    def is_alive(self):
        self.alive_reads += 1
        return self.alive

    def join(self, timeout):
        assert timeout == 2


def _cell(function, name):
    return dict(zip(function.__code__.co_freevars, function.__closure__))[name]


def _unrelated():
    return None


def _frame(code, **locals_):
    return SimpleNamespace(f_code=code, f_locals=locals_)


def test_observer_selective_lifecycle_contract(monkeypatch):
    # Catches unselected profile events doing worker/lock/liveness work, dropped
    # wait events, and losing sessions constructed before worker installation.
    # The callback is the real fixture closure. Automatic hooks are paused so
    # these explicit events test bookkeeping without creating authority or RPCs.
    from cloud_edge_robot_arm.simulation_runtime import operational_lease as lease

    original_profile = sys.getprofile()
    original_thread_profile = threading.getprofile()
    value = {"resources": [], "worker_lifecycles": [], "cleanup_errors": [],
             "observations": {"scenarios": []}}
    with fixture._b_t2_observe(monkeypatch, value) as observed:
        profile = sys.getprofile()
        sys.setprofile(None)
        threading.setprofile(None)

        workers = _Workers(observed.workers)
        _cell(observed.add, "worker_refs").cell_contents = workers
        observed.workers = workers
        guard_cell = _cell(observed.add, "guard")
        guard = _Guard(guard_cell.cell_contents)
        guard_cell.cell_contents = guard
        worker = _Worker(installed_field=True)
        observed.add(worker, "worker")
        idle_broker = _Thread(10)
        session = SimpleNamespace(worker=worker, _broker=idle_broker,
                                  _heartbeat_thread=None, _sealed=True, _closed=True)
        worker._operational_lease_session = session
        frame = _frame(_unrelated.__code__)
        lock = threading.Lock()
        argument = lock.acquire
        events = ("call", "return", "c_call", "c_return", "c_exception")
        workers.scans = guard.entries = worker.session_reads = idle_broker.alive_reads = 0
        for event in events:
            profile(frame, event, argument)
        # This is the sole predeclared G0 RED assertion: old profile always
        # iterates tuple(worker_refs), even for an unrelated Python/C event.
        assert workers.scans == 0, "unrelated profile events scanned worker history"
        assert guard.entries == 0, "unrelated profile events acquired observer guard"
        assert worker.session_reads == 0, "unrelated profile events sampled worker state"
        assert idle_broker.alive_reads == 0, "unrelated profile events sampled thread liveness"

        forwarded = []
        observed.wait_observer = lambda f, e, a: forwarded.append((f, e, a))
        for event in events:
            profile(frame, event, argument)
        assert [row[1] for row in forwarded] == list(events)
        assert all(row[0] is frame and row[2] is argument for row in forwarded)
        assert workers.scans == guard.entries == worker.session_reads == idle_broker.alive_reads == 0

        error = RuntimeError("wait-observer-sentinel")

        def reject(f, e, a):
            assert f is frame and e == "c_call" and a is argument
            raise error

        observed.wait_observer = reject
        try:
            profile(frame, "c_call", argument)
        except RuntimeError as caught:
            assert caught is error
        else:
            raise AssertionError("wait observer exception was swallowed")
        observed.wait_observer = None

        # The worker field is absent during a real constructor entry; owner is
        # available as the actual constructor argument, before self.worker exists.
        preinstall = _Worker(installed_field=False)
        observed.add(preinstall, "worker")
        partial = SimpleNamespace(_closed=True)
        constructor = _frame(lease.OperationalLeaseSession.__init__.__code__,
                             self=partial, worker=preinstall)
        profile(constructor, "call", None)
        partial_record = observed.objects[id(partial)][1]
        owner_record = observed.objects[id(preinstall)][1]
        assert partial_record["worker_resource_id"] == id(preinstall)
        assert id(partial) in owner_record["session_resource_ids"]
        broker = _Thread(11)
        partial.worker = preinstall
        partial._broker = broker
        partial._heartbeat_thread = None
        start = _frame(threading.Thread.start.__code__, self=broker)
        profile(start, "call", None)
        profile(start, "return", None)
        assert id(broker) in owner_record["broker_resource_ids"]
        assert owner_record["broker_peak_alive"] == 1
        assert observed.objects[id(broker)][1]["session_resource_id"] == id(partial)

        heartbeat = _Thread(12)
        partial._heartbeat_thread = heartbeat
        installation = _frame(lease._install_heartbeat_thread.__code__,
                              session=partial, thread=heartbeat)
        profile(installation, "return", None)
        heartbeat_start = _frame(threading.Thread.start.__code__, self=heartbeat)
        profile(heartbeat_start, "call", None)
        profile(heartbeat_start, "return", None)
        assert id(heartbeat) in owner_record["heartbeat_resource_ids"]
        assert owner_record["heartbeat_peak_alive"] == 1
        assert observed.objects[id(heartbeat)][1]["worker_resource_id"] == id(preinstall)

        # An unrelated thread with the same name must acquire no owner identity.
        foreign = _Thread(13)
        profile(_frame(threading.Thread.start.__code__, self=foreign), "call", None)
        profile(_frame(threading.Thread.start.__code__, self=foreign), "return", None)
        assert id(foreign) not in observed.objects

        profile(constructor, "return", None)
        assert partial_record["initialized"] is False
        assert partial_record["initialization_error"]["type"] == "IncompleteConstructor"
        assert sum(row["resource_id"] == id(partial) for row in value["resources"]) == 1
        assert sum(row["resource_id"] == id(preinstall) for row in value["resources"]) == 1
        assert preinstall not in [observed.objects[call["worker_resource_id"]][0]
                                  for call in value["worker_lifecycles"]]
        idle_broker.alive = broker.alive = heartbeat.alive = foreign.alive = False

    assert sys.getprofile() is original_profile
    assert threading.getprofile() is original_thread_profile
    assert value["observations"]["observers_restored"] is True
    assert value["cleanup_errors"] == []
