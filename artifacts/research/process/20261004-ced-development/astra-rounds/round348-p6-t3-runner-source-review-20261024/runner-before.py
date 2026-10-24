"""R346 reserved single-node runner. Preparation never executes this module.

Only the nine literal plan commands are executable. Capture reads inert new
artifacts, never opens a database engine, and never imports application code.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
import traceback

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = Path(__file__).absolute().parent.parent
IMPL = D / "implementation"
HELPER = IMPL / "resource-evidence-helpers.py"
AUTHOR = IMPL / "author-command-ledger.json"
BINDING = IMPL / "author-binding.json"
PLAN_SHA = "637ad6e58d1659724add1fd99f6e79726577aced809c2bd836673bf69f3a4ce7"
HELPER_SHA = "bc13daf2a87ff80606c62ed3628e63c1c700ac3000803efa5b20d3c3392cb98b"
HEAD = "729bce11bbd55a4a869e25e52174da3d0db1825b"
BRANCH = "research/20261004-continuation"
KEYS = tuple("t3_%02d" % number for number in range(1, 10))
HELD = "HELD_PENDING_ROOT_SOURCE_GATE_AND_INDIVIDUAL_RESERVATION"
RAW_CAP = 33554432
TREE_CAP = 1073741824
ENTRY_CAP = 10000
FREE_MIN = 3221225472
ROUND_CAP = 21474836480
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


class DeadlineExpired(TimeoutError):
    pass


def require(ok, message):
    if not ok:
        raise ValueError(message)


def error_record(stage, error):
    return {"stage": stage, "type": type(error).__name__, "message": str(error),
            "traceback": traceback.format_exc()}


@contextmanager
def bounded(seconds, absolute=None):
    """Main-thread timer; nested budgets restore the earlier timer's elapsed time."""
    started = time.monotonic()
    limit = min(seconds, absolute - started) if absolute is not None else seconds
    if limit <= 0:
        raise DeadlineExpired("monotonic stage budget exhausted")
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)

    def expired(signum, frame):
        raise DeadlineExpired("bounded operation exceeded %.3fs" % limit)

    signal.signal(signal.SIGALRM, expired)
    inherited = previous_timer[0] if previous_timer[0] > 0 else limit
    signal.setitimer(signal.ITIMER_REAL, min(limit, inherited))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL,
                             max(0.000001, previous_timer[0] - (time.monotonic() - started)),
                             previous_timer[1])


def coordinates(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns]


def stable(path):
    """Stable regular-file bytes, no final symlink; source pins are absolute."""
    path = Path(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode), "regular nofollow file required: " + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        opened = os.fstat(fd)
        require(coordinates(before) == coordinates(opened), "file changed before read")
        chunks = []
        while chunk := os.read(fd, 1024 * 1024):
            chunks.append(chunk)
        raw = b"".join(chunks)
        require(coordinates(opened) == coordinates(os.fstat(fd)) == coordinates(path.lstat())
                and len(raw) == opened.st_size, "file changed during read: " + str(path))
        return raw
    finally:
        os.close(fd)


def bytes_pin(path, raw):
    return {"path": str(Path(path).absolute()), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


def pin(path):
    return bytes_pin(path, stable(path))


def check(record):
    require(pin(record["path"]) == {name: record[name] for name in ("path", "bytes", "sha256")},
            "pin changed: " + record["path"])


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()


def read_json(path):
    value = json.loads(stable(path))
    require(type(value) is dict, "JSON object required")
    return value


def write(path, value):
    path = Path(path)
    raw = value if isinstance(value, bytes) else encoded(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    actual = pin(path)
    require(actual == bytes_pin(path, raw), "exclusive write readback differs")
    return actual


def full(path):
    raw = stable(path)
    return {**bytes_pin(path, raw), "mode": stat.S_IMODE(Path(path).lstat().st_mode),
            "base64": base64.b64encode(raw).decode("ascii")}


def cas(path, before, after, receipt):
    """Compare exact bytes/mode under a nonblocking owned ledger lock; no retry."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    temporary = path.with_name(path.name + ".r346-next")
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        check(before)
        require(coordinates(os.fstat(descriptor)) == coordinates(path.lstat()), "ledger inode changed")
        require(stat.S_IMODE(os.fstat(descriptor).st_mode) == before["mode"], "ledger mode changed")
        require(stable(path) == base64.b64decode(before["base64"]), "ledger CAS bytes changed")
        write(receipt.with_name(receipt.stem + "-before.json"), before)
        write(temporary, after)
        os.chmod(temporary, before["mode"])
        check(before)
        require(coordinates(os.fstat(descriptor)) == coordinates(path.lstat()), "ledger inode changed")
        os.replace(temporary, path)
        require(stable(path) == encoded(after), "ledger CAS after differs")
        return write(receipt, {"before": before, "after": full(path)})
    finally:
        os.close(descriptor)


def git_value(*arguments):
    return subprocess.check_output(["/usr/bin/git", *arguments], cwd=ROOT,
                                   text=True, timeout=2, stderr=subprocess.PIPE).strip()


def observe_sources(gate, target):
    """Mismatch is data. A single bad pin never gates later pin observations."""
    for expected in gate.get("pins", []):
        row = {"expected": expected, "actual": None, "missing": False, "error": None, "match": False}
        target["pins"].append(row)
        try:
            row["actual"] = pin(expected["path"])
            row["match"] = row["actual"] == expected
        except DeadlineExpired:
            raise
        except Exception as error:
            row["missing"] = isinstance(error, FileNotFoundError)
            row["error"] = error_record("source pin", error)
    for field, arguments in (("HEAD", ("rev-parse", "HEAD")),
                             ("branch", ("branch", "--show-current"))):
        try:
            target[field] = git_value(*arguments)
        except DeadlineExpired:
            raise
        except Exception as error:
            target[field + "_error"] = error_record(field, error)
    target["complete"] = len(target["pins"]) == len(gate.get("pins", []))
    target["accepted"] = bool(target["complete"] and target["pins"]
                              and all(row["match"] for row in target["pins"])
                              and target.get("HEAD") == gate.get("HEAD") == HEAD
                              and target.get("branch") == gate.get("branch") == BRANCH)


def walk(root, rows, *, content=False, archive=None):
    """Bounded nofollow traversal with per-path errors and independent orphan copies.

    Directory-relative descriptors avoid following links in descendant ancestors.
    content=False performs metadata only while the child is alive.
    """
    root = Path(root)
    result = {"root": str(root), "complete": False, "entries": 0, "regular_bytes": 0,
              "errors": [], "files": rows, "consistent_database_backup": False}
    visited = set()

    def visit(directory_fd, relative):
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                require(len(rows) < ENTRY_CAP, "finite inventory entry cap reached")
                rel = relative / entry.name
                row = {"path": str(root / rel), "relative": rel.as_posix(), "error": None}
                rows.append(row)
                result["entries"] += 1
                try:
                    info = entry.stat(follow_symlinks=False)
                    row.update(mode=info.st_mode, bytes=info.st_size, coordinates=coordinates(info))
                    if stat.S_ISLNK(info.st_mode):
                        row.update(type="symlink", link_target=os.readlink(entry.name, dir_fd=directory_fd))
                    elif stat.S_ISDIR(info.st_mode):
                        row["type"] = "directory"
                        descriptor = os.open(entry.name, DIR_FLAGS, dir_fd=directory_fd)
                        try:
                            require(coordinates(info) == coordinates(os.fstat(descriptor)), "directory changed")
                            identity = (info.st_dev, info.st_ino)
                            require(identity not in visited, "duplicate directory identity")
                            visited.add(identity)
                            visit(descriptor, rel)
                            require(coordinates(os.fstat(descriptor)) == coordinates(os.stat(
                                entry.name, dir_fd=directory_fd, follow_symlinks=False)), "directory path changed")
                        finally:
                            os.close(descriptor)
                    elif stat.S_ISREG(info.st_mode):
                        row["type"] = "regular"
                        result["regular_bytes"] += info.st_size
                        if content:
                            row.update(read_regular(directory_fd, entry.name, info, root / rel,
                                                    archive / rel if archive is not None and database_name(entry.name)
                                                    else None))
                    else:
                        row["type"] = "special"
                except DeadlineExpired:
                    raise
                except Exception as error:
                    row["error"] = error_record("inventory path", error)
                    result["errors"].append(row["error"])

    descriptor = None
    try:
        descriptor = os.open(root, DIR_FLAGS)
        info = os.fstat(descriptor)
        require(coordinates(info) == coordinates(root.lstat()), "root directory changed")
        visited.add((info.st_dev, info.st_ino))
        visit(descriptor, Path())
        require(coordinates(os.fstat(descriptor)) == coordinates(root.lstat()), "root path changed")
        result["complete"] = not result["errors"]
    except DeadlineExpired:
        raise
    except Exception as error:
        result["errors"].append(error_record("inventory traversal", error))
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return result


def database_name(name):
    base = name
    for suffix in ("-wal", "-shm", "-journal"):
        if name.endswith(suffix):
            base = name[:-len(suffix)]
            break
    return Path(base).suffix.lower() in {".db", ".sqlite", ".sqlite3"}


def read_regular(parent, name, expected, original, destination=None):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    output = None
    row = {"sha256": None, "stable": False, "archive": None, "archive_error": None}
    try:
        opened = os.fstat(fd)
        require(coordinates(expected) == coordinates(opened), "regular file changed before read")
        if destination is not None:
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                output = destination.open("xb")
            except DeadlineExpired:
                raise
            except Exception as error:
                row["archive_error"] = error_record("exclusive DB byte copy", error)
        digest = hashlib.sha256()
        size = 0
        while chunk := os.read(fd, 1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
            if output is not None:
                output.write(chunk)
        require(coordinates(opened) == coordinates(os.fstat(fd)) == coordinates(os.stat(
            name, dir_fd=parent, follow_symlinks=False)) and size == opened.st_size,
                "regular file changed during read")
        row.update(sha256=digest.hexdigest(), stable=True, read_bytes=size)
        if output is not None:
            output.flush()
            os.fsync(output.fileno())
            output.close()
            output = None
            row["archive"] = pin(destination)
            require((row["archive"]["bytes"], row["archive"]["sha256"]) == (size, digest.hexdigest()),
                    "DB destination byte readback differs")
        return row
    finally:
        if output is not None:
            output.close()
        os.close(fd)


def storage_observation(command, *, round_tree=False):
    with bounded(2):
        root = D if round_tree else Path(command["output"]) / "persistent-basetemp"
        if not root.exists() and not root.is_symlink():
            census = {"root": str(root), "complete": True, "entries": 0, "regular_bytes": 0, "errors": []}
        else:
            census = walk(root, [])
        space = os.statvfs(D)
        census["free_bytes"] = space.f_bavail * space.f_frsize
        require(census["complete"], "storage scan incomplete")
        require(census["free_bytes"] >= FREE_MIN, "minimum free storage crossed")
        require(census["regular_bytes"] <= (ROUND_CAP if round_tree else TREE_CAP), "storage byte threshold crossed")
        require(census["entries"] <= ENTRY_CAP, "storage entry threshold crossed")
        return {key: value for key, value in census.items() if key != "files"}


def verify_gate(command, plan, gate, acceptance, root_ledger, key):
    require(gate["round"] == "R346" and gate["HEAD"] == HEAD and gate["branch"] == BRANCH,
            "gate generation differs")
    require(gate["commands"] == plan["commands"], "exact nine command table differs")
    require(gate["sources"]["runner"] == pin(__file__) and gate["sources"]["helper"] == pin(HELPER),
            "runner/helper not bound")
    require(gate["executor_binding"] == pin(BINDING) == acceptance["executor_binding"], "actor binding differs")
    binding = read_json(BINDING)
    require(binding["actual_actor"] == "/root/p6_t3_sol" and binding["acknowledged_by_actual_live_seat"] is True,
            "actual same-seat author acknowledgment required")
    require(acceptance["reviewed"] is True and acceptance["source_gate"] == pin(D / "source-gate.json"),
            "ROOT source acceptance differs")
    require(acceptance["runtime_implementation"] == gate["sources"], "ROOT implementation identity differs")
    require(type(gate["interpreter_evidence"]) is dict and gate["interpreter_evidence"],
            "existing interpreter identity evidence required")
    require(len(command["nodes"]) == 1 and [arg for arg in command["child_argv"] if "::" in arg] == command["nodes"],
            "single exact selected node required")
    require(pin(HELPER)["sha256"] == HELPER_SHA, "whole helper changed")
    previous_polls = 0
    for other in KEYS:
        slot = root_ledger["commands"][other]
        if other < key:
            require(slot["state"] == "SPENT" and slot["used"] == 1 and slot["remaining"] == 0,
                    "predecessor is not spent")
            check(slot["disposition"])
            disposition = read_json(slot["disposition"]["path"])
            require(disposition["ROOT_accepted"] is True and disposition["command_id"] == "R346:" + other,
                    "predecessor not independently accepted")
            check(disposition["result"])
            prior = read_json(disposition["result"]["path"])
            require(prior["command_id"] == "R346:" + other and prior["behavior_candidate_pass"] is True
                    and prior["source_gate"] == pin(D / "source-gate.json"), "predecessor generation differs")
            polls = prior["resource_counts"]["attempted_poll_lifecycles"]
            require(type(polls) is int and 0 <= polls <= plan["commands"][other]["max_worker_poll_lifecycles"],
                    "predecessor actual poll count invalid")
            previous_polls += polls
        elif other > key:
            require(slot["state"] == HELD and slot["used"] == 0 and slot["remaining"] == 1,
                    "later ROOT slot not HELD")
    require(previous_polls + command["max_worker_poll_lifecycles"] <= 15, "aggregate poll budget exceeded")
    return previous_polls


def spend(author_before, key, reserved, out):
    author = json.loads(base64.b64decode(author_before["base64"]))
    require(tuple(author["commands"]) == KEYS and author["actor"] == "/root/p6_t3_sol"
            and author["plan_sha256"] == PLAN_SHA, "AUTHOR ledger identity differs")
    for other, slot in author["commands"].items():
        if other >= key:
            require(slot["state"] == HELD and slot["used"] == 0 and slot["remaining"] == 1,
                    "AUTHOR selected/later slot not HELD")
        else:
            require(slot["state"] == "SPENT" and slot["used"] == 1 and slot["remaining"] == 0,
                    "AUTHOR predecessor not spent")
    author["commands"][key].update(state="CONSUMED_BEFORE_START", used=1, remaining=0,
                                  reservation_id=reserved["reservation_id"])
    return cas(AUTHOR, author_before, author, out / "author-consumed.json")


def reconcile(key, reserved, out):
    before = full(AUTHOR)
    after = json.loads(base64.b64decode(before["base64"]))
    slot = after["commands"][key]
    require(slot["state"] == "CONSUMED_BEFORE_START" and slot["reservation_id"] == reserved["reservation_id"],
            "AUTHOR consumed state changed; ROOT must reconcile")
    slot["state"] = "SPENT"
    return cas(AUTHOR, before, after, out / "author-spent.json")


def main():
    require(len(sys.argv) == 2 and sys.argv[1] in KEYS, "one literal R346 command key required")
    key = sys.argv[1]
    out = IMPL / key
    command = gate = helper = reserved = None
    process = None
    errors, signals, monitor, stages = [], [], [], {}
    source_before = {"pins": [], "complete": False, "accepted": False}
    cleanup = {"leader_reaped": None, "group_remaining": None, "cleanup_errors": [], "no_child_started": True}
    data = {"round": "R346", "command_id": "R346:" + key, "source_gate": None,
            "child_exit": None, "pid": None, "pgid": None, "timed_out": False,
            "output_limited": False, "storage_limited": False, "previous_actual_polls": None,
            "behavior_candidate_pass": False, "ROOT_accepted": False,
            "formal_accepted": False, "whole_B_accepted": False, "errors": errors,
            "signals": signals, "cleanup": cleanup, "monitor": monitor,
            "unobserved": {"RSS": None, "OS_handles": None, "GPU_native": None,
                           "external_models": None, "network_calls": None}}
    previous_signals = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}

    def interrupted(signum, frame):
        signals.append({"signal": signum, "monotonic": time.monotonic()})

    for sig in previous_signals:
        signal.signal(sig, interrupted)
    overall_start = time.monotonic()
    output_created = False
    try:
        try:
            with bounded(35):
                require(pin(D / "plan.json")["sha256"] == PLAN_SHA, "actual Astra plan changed")
                plan = read_json(D / "plan.json")
                command = plan["commands"][key]
                require(command["output"] == str(out) and command["cwd"] == str(ROOT), "literal output/cwd differs")
                root_ledger = read_json(D / "root-command-ledger.json")
                require(tuple(root_ledger["commands"]) == KEYS and root_ledger["plan_sha256"] == PLAN_SHA,
                        "ROOT nine-slot ledger identity differs")
                reserved = root_ledger["commands"][key]
                require(reserved["state"] == "RESERVED" and reserved["used"] == 1 and reserved["remaining"] == 0
                        and type(reserved["reservation_id"]) is str and reserved["reservation_id"],
                        "ROOT individual reservation required")
                out.mkdir(mode=0o700, exist_ok=False)
                output_created = True
                write(out / "invocation.json", {"command_id": "R346:" + key, "command": command,
                      "root_reservation": reserved, "root_ledger_observed": full(D / "root-command-ledger.json"),
                      "monotonic": overall_start})
                # Reservation already spends ROOT. Consume AUTHOR before all remaining prelaunch guards.
                spend(full(AUTHOR), key, reserved, out)
                gate = read_json(D / "source-gate.json")
                acceptance = read_json(D / "root-source-acceptance.json")
                require(reserved["source_gate"] == pin(D / "source-gate.json")
                        and reserved["acceptance"] == pin(D / "root-source-acceptance.json")
                        and reserved["executor_binding"] == pin(BINDING), "reservation source/actor identity differs")
                data["source_gate"] = pin(D / "source-gate.json")
                data["previous_actual_polls"] = verify_gate(command, plan, gate, acceptance, root_ledger, key)
                observe_sources(gate, source_before)
                write(out / "source-before.json", source_before)
                require(source_before["accepted"], "before HEAD/source observation rejected")
                monitor.append({"stage": "prelaunch round storage", **storage_observation(command, round_tree=True)})
                require(not signals, "interrupted before child start")
                spec = importlib.util.spec_from_file_location("r346_frozen_helpers", HELPER)
                helper = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(helper)  # Only the new whole frozen stdlib helper; reserved attempt only.
                write(out / "helper-import-identity.json", {"helper": pin(HELPER), "module": "r346_frozen_helpers",
                      "product_imported_in_parent": False, "interpreter_evidence": gate["interpreter_evidence"]})
                (out / "resources").mkdir()
        except BaseException as error:
            errors.append(error_record("prelaunch", error))

        if not errors:
            try:
                with (out / "stdout.txt").open("xb") as stdout, (out / "stderr.txt").open("xb") as stderr:
                    start = time.monotonic()
                    deadline = start + command["child_seconds"]
                    with bounded(command["child_seconds"]):
                        process = subprocess.Popen(command["child_argv"], cwd=ROOT, env=command["child_env"],
                                                   stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                                   shell=False, start_new_session=True)
                        data.update(pid=process.pid, pgid=process.pid, child_start_monotonic=start,
                                    child_deadline_monotonic=deadline)
                        cleanup["no_child_started"] = False
                        write(out / "actual-child-start.json", {"pid": process.pid, "pgid": os.getpgid(process.pid),
                              "argv": command["child_argv"], "env": command["child_env"],
                              "monotonic_start": start, "deadline": deadline})
                        next_head = next_storage = start
                        while process.poll() is None:
                            now = time.monotonic()
                            if now >= deadline:
                                data["timed_out"] = True
                                break
                            sizes = {name: (out / name).lstat().st_size for name in ("stdout.txt", "stderr.txt")}
                            if any(size > RAW_CAP for size in sizes.values()):
                                data["output_limited"] = True
                                monitor.append({"stage": "raw threshold", "monotonic": now, "bytes": sizes})
                                break
                            if signals:
                                raise InterruptedError("TERM/INT received; enter owned cleanup")
                            if now >= next_head:
                                observed = git_value("rev-parse", "HEAD")
                                monitor.append({"stage": "HEAD", "monotonic": now, "HEAD": observed})
                                require(observed == HEAD, "observed HEAD drift during child")
                                next_head = now + 1
                            if now >= next_storage:
                                try:
                                    monitor.append({"stage": "persistent storage", "monotonic": now,
                                                    **storage_observation(command)})
                                except BaseException:
                                    data["storage_limited"] = True
                                    raise
                                next_storage = now + 5
                            time.sleep(min(0.1, max(0, deadline - time.monotonic())))
            except DeadlineExpired as error:
                data["timed_out"] = True
                errors.append(error_record("child wall deadline", error))
            except BaseException as error:
                errors.append(error_record("child/monitor", error))
    finally:
        # This finally surrounds source guards, ledger CAS, Popen, monitoring and signals.
        # No ledger reconciliation or capture validator can bypass owned-group cleanup.
        if process is not None:
            try:
                cleanup.update(helper._t2_cleanup(process))
            except BaseException as error:
                cleanup["cleanup_errors"].append(error_record("owned cleanup", error))
                # Immediate fail-closed signal; no second polling/test attempt or cleanup budget reset.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except OSError as kill_error:
                    cleanup["cleanup_errors"].append(error_record("emergency KILL", kill_error))
            data["child_exit"] = process.returncode
            data["child_elapsed_seconds_through_cleanup"] = time.monotonic() - data["child_start_monotonic"]

        if output_created:
            capture_start = time.monotonic()
            capture_deadline = capture_start + 240

            def stage(name, seconds, action, *, state=None):
                entry = {"state": "STARTED", "seconds_bound": seconds, "started_monotonic": time.monotonic(),
                         "error": None, "persistence_error": None}
                stages[name] = entry
                partial = {} if state is None else state
                try:
                    with bounded(seconds, capture_deadline):
                        action(partial)
                    entry["state"] = "COMPLETE"
                except BaseException as error:
                    entry["state"] = "TIMEOUT" if isinstance(error, DeadlineExpired) else "FAILED"
                    entry["error"] = error_record(name, error)
                    errors.append(entry["error"])
                finally:
                    entry["elapsed_seconds"] = time.monotonic() - entry["started_monotonic"]
                    data[name] = partial
                    # Bookkeeping uses the shared 30s reserve, never an unbounded finally write.
                    try:
                        with bounded(2, capture_deadline):
                            write(out / (name + ".json"), {"stage": entry, "observations": partial})
                    except BaseException as error:
                        entry["persistence_error"] = error_record(name + " persistence", error)
                        errors.append(entry["persistence_error"])

            def raw_process(partial):
                partial.update(cleanup=cleanup, signals=signals, streams={}, ledger=None)
                for name in ("stdout.txt", "stderr.txt"):
                    try:
                        actual = pin(out / name)
                        partial["streams"][name] = {"pin": actual, "overshoot_bytes": max(0, actual["bytes"] - RAW_CAP)}
                        data["output_limited"] |= actual["bytes"] > RAW_CAP
                    except DeadlineExpired:
                        raise
                    except Exception as error:
                        failure = error_record(name, error)
                        partial["streams"][name] = {"error": failure}
                        errors.append(failure)
                try:
                    partial["ledger"] = reconcile(key, reserved, out)
                except DeadlineExpired:
                    raise
                except Exception as error:
                    failure = error_record("AUTHOR spent reconciliation", error)
                    partial["ledger"] = {"error": failure, "ROOT_reconciliation_required": True,
                                         "reservation_already_spent": reserved, "no_refund": True}
                    errors.append(failure)
                partial.update(child_started=process is not None, pid=data["pid"], pgid=data["pgid"],
                               child_exit=data["child_exit"], monitor=monitor, original_errors=list(errors))

            def sources(partial):
                partial.update(pins=[], complete=False, accepted=False)
                if gate is None:
                    raise ValueError("source gate unavailable after prelaunch rejection")
                observe_sources(gate, partial)
                if partial["accepted"]:
                    write(out / "source-after.json", partial)

            def inventory(partial):
                partial.update(files=[], complete=False, requested_copies_complete=False,
                               consistent_database_backup=False, originals_deleted=False)
                observed = walk(out / "persistent-basetemp", partial["files"], content=True,
                                archive=out / "retained-databases")
                partial.update(observed)
                candidates = [row for row in partial["files"] if row.get("type") == "regular"
                              and database_name(Path(row["path"]).name)]
                partial["database_and_sidecar_files"] = candidates
                partial["requested_copies_complete"] = all(row.get("archive") and not row.get("error")
                    and not row.get("archive_error") for row in candidates)
                require(partial["complete"] and partial["requested_copies_complete"], "partial inventory/DB retention")

            def resources(partial):
                partial.update(original_sidecar_copies=[], facts={}, summary=None, behavior_complete=False)
                directory = out / "resources"
                # Retain every actual sidecar first, even when parser/provenance validation will reject it.
                for path in directory.iterdir():
                    require(len(partial["original_sidecar_copies"]) < ENTRY_CAP, "sidecar entry cap")
                    row = {"path": str(path), "pin": None, "copy": None, "error": None}
                    partial["original_sidecar_copies"].append(row)
                    try:
                        raw = stable(path)
                        row["pin"] = bytes_pin(path, raw)
                        row["copy"] = write(out / "retained-sidecars" / path.name, raw)
                    except DeadlineExpired:
                        raise
                    except Exception as error:
                        row["error"] = error_record("sidecar byte retention", error)
                require(helper is not None, "new frozen helper unavailable")
                summary = helper.diagnostic_resources(directory, "R346:" + key, command["child_argv"], data["pid"])
                partial["summary"] = summary
                partial["behavior_complete"] = helper.behavior_resources_complete(summary, facts=partial["facts"])
                data["resource_counts"] = summary["counts"]
                require(summary["complete_sidecar_set"] and summary["all_records_valid"], "resource sidecars invalid/incomplete")
                counts = summary["counts"]
                require(counts.get("constructed_worker_attempts", 0) <= 64, "inherited actual worker construction64 cap")
                polls = counts.get("attempted_poll_lifecycles", 0)
                require(polls <= command["max_worker_poll_lifecycles"]
                        and data["previous_actual_polls"] is not None
                        and data["previous_actual_polls"] + polls <= 15, "per-node/aggregate actual poll cap")
                require(summary["peak_active_polls_per_node"] <= 2, "concurrent poll cap")
                require(partial["behavior_complete"] is True, "genuine nested assertions did not complete")
                require(all(not row["error"] for row in partial["original_sidecar_copies"]), "sidecar bytes incomplete")

            def junit(partial):
                require(helper is not None, "new frozen helper unavailable")
                partial.update(helper.junit_observation(out / "junit.xml", command["nodes"]))
                require(partial["available"] and partial["tests"] == 1 and partial["failures"] == 0
                        and partial["errors"] == 0 and partial["skips"] == 0, "one genuine passing JUnit required")

            def cases(partial):
                partial.update(files=[], scan=[])
                scanned = walk(out / "persistent-basetemp", partial["scan"])
                require(helper is not None, "new frozen helper unavailable")
                for row in partial["scan"]:
                    path = Path(row["path"])
                    if path.name not in helper.CASE_NAMES:
                        continue
                    item = {"path": str(path), "pin": None, "data": None, "error": None}
                    partial["files"].append(item)
                    try:
                        require(row.get("type") == "regular", "actual case must be regular")
                        raw = stable(path)
                        item["pin"] = bytes_pin(path, raw)
                        write(out / "retained-cases" / row["relative"], raw)
                        value = json.loads(raw)
                        item["data"] = value
                        require(path.name == command["expected_case_filename"]
                                and value["schema_version"] == "bigsmall.r331.t3-case.v1"
                                and value["nodeid"] == command["nodes"][0]
                                and value["command_id"] == "R346:" + key
                                and value["pid"] == data["pid"] and data["pid"] is not None,
                                "case schema/family/node/command/actual PID differs")
                        require(value["observers_restored"] is True and value["cleanup_errors"] == [],
                                "case observer/cleanup unavailable")
                    except DeadlineExpired:
                        raise
                    except Exception as error:
                        item["error"] = error_record("actual case", error)
                require(scanned["complete"] and len(partial["files"]) == 1
                        and partial["files"][0]["error"] is None, "exact one genuine case required")
                summary = data.get("resources", {}).get("summary")
                require(summary is not None and len(summary["records"]) == 1, "case/resource join unavailable")
                case = partial["files"][0]["data"]
                sidecar = summary["records"][0]["data"]
                require(case["resources"] == sidecar["resources"]
                        and case["worker_lifecycles"] == sidecar["worker_lifecycles"]
                        and sidecar["observations"]["assertions_completed"] is True,
                        "case/actual resource lifecycle and nested assertion join differs")

            def prerequisite(partial):
                require(helper is not None, "new frozen helper unavailable")
                partial.update(helper.prerequisite(out / "prerequisite.json", {"module": helper.MODULE_PIN}, data["pid"]))
                require(partial["accepted"] is True, "genuine R235 prerequisite rejected")

            stage("raw-process-ledger", 15, raw_process)
            stage("source-after-observed", 30, sources)
            stage("persistent-inventory", 90, inventory)
            stage("resources", 30, resources)
            stage("junit", 10, junit)
            stage("cases", 10, cases)
            stage("prerequisite", 10, prerequisite)

            def final_summary(partial):
                required_stages = tuple(stages)
                complete = all(stages[name]["state"] == "COMPLETE" and not stages[name]["persistence_error"]
                               for name in required_stages if name != "final-summary")
                inventory_data = data.get("persistent-inventory", {})
                data["artifact_retention_complete"] = bool(complete and not errors
                    and inventory_data.get("complete") is True and inventory_data.get("requested_copies_complete") is True)
                clean = (process is not None and cleanup.get("leader_reaped") is True
                         and cleanup.get("group_remaining") is False and not cleanup["cleanup_errors"])
                data["required_evidence_complete"] = bool(complete and source_before["accepted"]
                    and data.get("source-after-observed", {}).get("accepted") is True and clean
                    and data.get("resources", {}).get("behavior_complete") is True)
                data["behavior_candidate_pass"] = bool(data["artifact_retention_complete"]
                    and data["required_evidence_complete"] and data["child_exit"] == 0
                    and not data["timed_out"] and not data["output_limited"] and not data["storage_limited"]
                    and not signals and not errors)
                data["capture_elapsed_seconds_before_final_write"] = time.monotonic() - capture_start
                data["elapsed_seconds"] = time.monotonic() - overall_start
                missing = {"command_id": "R346:" + key, "artifacts": {}, "errors": list(errors),
                           "source_before_accepted": source_before["accepted"], "ROOT_accepted": False}
                for name in ("invocation.json", "author-consumed.json", "author-spent.json", "source-before.json",
                             "actual-child-start.json", "stdout.txt", "stderr.txt", "source-after.json", "junit.xml",
                             "prerequisite.json", "raw-process-ledger.json", "source-after-observed.json",
                             "persistent-inventory.json", "resources.json", "junit.json", "cases.json", "prerequisite.json"):
                    try:
                        missing["artifacts"][name] = {"status": "present", "pin": pin(out / name)}
                    except DeadlineExpired:
                        raise
                    except Exception as error:
                        missing["artifacts"][name] = {"status": "missing" if isinstance(error, FileNotFoundError)
                                                     else "invalid", "error": error_record(name, error)}
                missing["stage_outcomes"] = {name: row["state"] for name, row in stages.items()}
                write(out / "missingness.json", missing)
                # This stage is COMPLETE only after these exclusive outputs actually exist.
                statuses = {name: dict(row) for name, row in stages.items()}
                statuses["final-summary"]["state"] = "WRITING_FINAL_RESULT"
                write(out / "stage-status.json", {"stages": statuses, "capture_seconds_bound": 240,
                      "bookkeeping_reserve_seconds": 30, "ROOT_acceptance_required": True})
                partial["result"] = write(out / "result.json", data)

            stage("final-summary", 15, final_summary)
        for sig, previous in previous_signals.items():
            signal.signal(sig, previous)
    return 0 if data["behavior_candidate_pass"] and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
