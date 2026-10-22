"""R313 bounded stack observation only; no product imports or hook installation."""
import json
import os
from pathlib import Path
import resource
import sys
import threading
import time

ROOT = "/home/ningyd/文档/ChatGPT/BIGsmall/"
INTERVAL = 2
MAX_SAMPLES = 96
RECORD_CAP = 4096
PAYLOAD_CAP = 393216
METADATA_CAP = 131072
TOTAL_CAP = 524288
_state = None


def _encoded(value):
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n").encode()


def _metadata(state, name, value):
    raw = _encoded(value)
    if state["metadata_bytes"] + len(raw) > METADATA_CAP:
        raise ValueError("sampler metadata cap")
    if state["metadata_bytes"] + state["payload_bytes"] + len(raw) > TOTAL_CAP:
        raise ValueError("sampler total cap")
    with (state["directory"] / name).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    state["metadata_bytes"] += len(raw)


def _scalar(frame):
    name = frame.f_code.co_filename
    if name.startswith(ROOT):
        name = name[len(ROOT):]
    function = frame.f_code.co_qualname
    return {"file": name[:360], "function": function[:160], "line": frame.f_lineno,
            "name_truncated": len(name) > 360 or len(function) > 160}


def _stacks(main_ident):
    own = threading.get_ident()
    frames = sys._current_frames()
    selected = ([main_ident] if main_ident in frames else [])
    selected += [ident for ident in sorted(frames) if ident not in (own, main_ident)][:16-len(selected)]
    result = []
    try:
        for ident in selected:
            current = frames[ident]
            top, tests = [], []
            depth = 0
            limit = 128 if ident == main_ident else 4
            while current is not None and depth < limit:
                if depth < (16 if ident == main_ident else 4):
                    top.append(_scalar(current))
                if ident == main_ident and len(tests) < 4 and "/tests/" in current.f_code.co_filename:
                    item = _scalar(current)
                    if item not in top and item not in tests:
                        tests.append(item)
                depth += 1
                current = current.f_back
            truncated = current is not None
            del current
            result.append({"ident": ident, "main": ident == main_ident,
                           "walk_depth": depth, "walk_truncated": truncated,
                           "frames": top, "closest_test_frames": tests})
        return result, max(0, len(frames) - 1 - len(selected))
    finally:
        frames.clear()
        del frames


def _bounded_record(record):
    record["encoding_trimmed_frames"] = 0
    raw = _encoded(record)
    while len(raw) > RECORD_CAP:
        # Preserve main test-stage frames preferentially; retain thread coordinates.
        candidates = [item for item in reversed(record["threads"]) if not item["main"] and item["frames"]]
        if not candidates:
            candidates = [item for item in record["threads"] if item["frames"]]
        if candidates:
            candidates[0]["frames"].pop()
        else:
            candidates = [item for item in record["threads"] if item["closest_test_frames"]]
            if not candidates:
                raise ValueError("sampler scalar record exceeds cap")
            candidates[0]["closest_test_frames"].pop()
        record["encoding_trimmed_frames"] += 1
        raw = _encoded(record)
    return raw


def _observe(state):
    state["started"] = True
    state["ident"] = threading.get_ident()
    state["native_id"] = threading.get_native_id()
    previous = None
    try:
        with (state["directory"] / "frames.jsonl").open("xb") as stream:
            while not state["stop"].is_set():
                now = time.monotonic_ns()
                threads, omitted = _stacks(state["main_ident"])
                record = {"seq": state["samples"] + 1, "pid": os.getpid(),
                          "sampler_ident": state["ident"], "sampler_native_id": state["native_id"],
                          "main_ident": state["main_ident"], "monotonic_ns": now,
                          "process_time_ns": time.process_time_ns(),
                          "sampler_thread_time_ns": time.thread_time_ns(),
                          "maxrss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                          "interval_ns": None if previous is None else now - previous,
                          "lag_ns": None if previous is None else max(0, now - previous - INTERVAL * 1000000000),
                          "omitted_threads": omitted, "threads": threads}
                raw = _bounded_record(record)
                if (state["samples"] >= MAX_SAMPLES or state["payload_bytes"] + len(raw) > PAYLOAD_CAP
                        or state["metadata_bytes"] + state["payload_bytes"] + len(raw) > TOTAL_CAP):
                    state["cap_hit"] = True
                    state["dropped"] += 1
                    break
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
                state["samples"] += 1
                state["payload_bytes"] += len(raw)
                previous = now
                if state["samples"] == MAX_SAMPLES:
                    state["cap_hit"] = True
                    break
                if state["stop"].wait(INTERVAL):
                    break
    except BaseException as error:
        state["exception_type"] = type(error).__name__
    finally:
        state["thread_finished"] = True


def pytest_sessionstart(session):
    global _state
    state = {"directory": Path(os.environ["BIGSMALL_R313_SAMPLER_DIR"]),
             "main_ident": threading.get_ident(), "stop": threading.Event(),
             "started": False, "ident": None, "native_id": None, "thread_finished": False,
             "samples": 0, "payload_bytes": 0, "metadata_bytes": 0,
             "cap_hit": False, "dropped": 0, "exception_type": None, "ended": False,
             "sys_profile": sys.getprofile(), "sys_trace": sys.gettrace(),
             "thread_profile": threading.getprofile(), "thread_trace": threading.gettrace()}
    _state = state
    _metadata(state, "start.json", {"round": "R313", "pid": os.getpid(), "attempted": True,
              "main_ident": state["main_ident"], "role": "stdlib stack observer",
              "interval_seconds": INTERVAL, "max_samples": MAX_SAMPLES,
              "record_cap": RECORD_CAP, "payload_cap": PAYLOAD_CAP,
              "metadata_cap": METADATA_CAP, "total_cap": TOTAL_CAP,
              "monotonic_ns": time.monotonic_ns(), "product_imports": False,
              "profile_or_trace_installed": False})
    thread = threading.Thread(target=_observe, args=(state,), name="r313-stack-observer", daemon=True)
    state["thread"] = thread
    try:
        thread.start()
    except BaseException as error:
        state["exception_type"] = type(error).__name__


def _finish():
    state = _state
    if state is None or state["ended"]:
        return
    state["ended"] = True
    state["stop"].set()
    thread = state["thread"]
    join_attempted = thread.ident is not None
    if join_attempted:
        thread.join(timeout=2)
    _metadata(state, "end.json", {"round": "R313", "pid": os.getpid(),
              "normal_pytest_end_observed": True, "stop_set": state["stop"].is_set(),
              "join_attempted": join_attempted, "join_seconds_bound": 2,
              "started": state["started"], "ident": state["ident"], "native_id": state["native_id"],
              "thread_alive": thread.is_alive(), "thread_finished": state["thread_finished"],
              "exception_type": state["exception_type"], "samples": state["samples"],
              "payload_bytes": state["payload_bytes"], "metadata_bytes_before_end": state["metadata_bytes"],
              "cap_hit": state["cap_hit"], "dropped": state["dropped"],
              "hooks_equal": sys.getprofile() is state["sys_profile"] and sys.gettrace() is state["sys_trace"]
                and threading.getprofile() is state["thread_profile"] and threading.gettrace() is state["thread_trace"],
              "monotonic_ns": time.monotonic_ns()})


def pytest_sessionfinish(session, exitstatus):
    _finish()


def pytest_unconfigure(config):
    _finish()
