"""CPU-only OC1 microstudy, with unmodified production clock and local prototype."""

import argparse
import hashlib
import json
import os
import platform
import statistics
import sys
import threading
import time
import uuid
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from cloud_edge_robot_arm.research import operational_time_v1 as clock

BOOT = "/proc/sys/kernel/random/boot_id"
STAT = "/proc/self/stat"
OFFSETS = "/proc/self/timens_offsets"
SOURCE = clock._LinuxBootTimeSource
IDENTITY = SOURCE.identity


def parse_boot(raw):
    try:
        return str(uuid.UUID(raw.strip()))
    except ValueError as error:
        raise clock.OperationalTimeError("boot identity unavailable") from error


def prototype(read, boot_original, offsets_original):
    boot_value = parse_boot(boot_original)
    offsets_value = clock._parse_namespace_offsets(offsets_original)

    def boot(raw):
        return boot_value if raw == boot_original else parse_boot(raw)

    def offsets(raw):
        if raw == offsets_original:
            return offsets_value
        return clock._parse_namespace_offsets(raw)

    def identity(self):
        uname = os.uname()
        pid = os.getpid()
        boot_id = boot(read(BOOT))
        ticks = clock._parse_process_start_ticks(read(STAT), expected_pid=pid)
        namespace = clock._stat_time_namespace()
        parsed_offsets = offsets(read(OFFSETS))
        return clock._StartupIdentity(
            boot_id, pid, ticks, threading.get_ident(), threading.get_native_id(),
            namespace.st_dev, namespace.st_ino, parsed_offsets, uname.sysname,
            uname.release, uname.version, uname.machine, sys.version,
        )

    return identity, boot, offsets


def controls(boot_raw, offsets_raw):
    logs = []
    samples = {BOOT: boot_raw, STAT: clock._read_proc_text(STAT), OFFSETS: offsets_raw}

    def read(path):
        logs.append(path)
        value = samples[path]
        if isinstance(value, Exception):
            raise value
        return value

    candidate, boot, offsets = prototype(read, boot_raw, offsets_raw)
    source = SOURCE()
    assert boot(boot_raw.upper()) == parse_boot(boot_raw)
    assert offsets(offsets_raw) == clock._parse_namespace_offsets(offsets_raw)
    changed_order = "\n".join(reversed(offsets_raw.splitlines()))
    assert offsets(changed_order) == clock._parse_namespace_offsets(offsets_raw)
    assert boot("00000000-0000-0000-0000-000000000001") != parse_boot(boot_raw)
    assert offsets("monotonic 1 0\nboottime 1 0\n") != offsets(offsets_raw)
    cases = [
        (BOOT, boot_raw.upper()),
        (BOOT, "00000000-0000-0000-0000-000000000001"),
        (OFFSETS, changed_order),
        (OFFSETS, "monotonic 1 0\nboottime 1 0\n"),
        (BOOT, "bad"),
        (OFFSETS, "bad"),
        (STAT, FileNotFoundError("injected missing proc stat")),
        (OFFSETS, OSError("injected offset read error")),
    ]

    def observed(method):
        logs.clear()
        try:
            value = method(source)
        except (ValueError, OSError, clock.OperationalTimeError) as error:
            value = (type(error), str(error))
        return value, tuple(logs)

    for path, raw in cases:
        old, samples[path] = samples[path], raw
        with patch.object(clock, "_read_proc_text", read):
            assert observed(IDENTITY) == observed(candidate)
        samples[path] = old
    return len(cases)


def clock_batch(n):
    owner = clock.open_operational_clock()
    try:
        token = owner.begin_event("cpu-only fixture")
        owner.mark_event(token)
        origin = owner.end_event(token)
        deadline = owner.start_deadline(task_key="cpu-only", origin=origin, budget_ns=30 * 10**9)
        start = time.perf_counter_ns()
        for _ in range(n):
            assert owner.before_deadline(deadline, owner.read_current(after=token))
        return time.perf_counter_ns() - start
    finally:
        owner.close()


def profile(n, boot_raw, offsets_raw):
    totals, calls = Counter(), Counter()

    def timed(label, call, *args, **kwargs):
        start = time.perf_counter_ns()
        try:
            return call(*args, **kwargs)
        finally:
            totals[label] += time.perf_counter_ns() - start
            calls[label] += 1

    read, stat = clock._read_proc_text, clock._stat_time_namespace
    process, offsets = clock._parse_process_start_ticks, clock._parse_namespace_offsets
    check, validate = clock.OperationalClockOwner._check, clock._validate_identity
    with (
        patch.object(clock, "_read_proc_text", lambda path: timed(path, read, path)),
        patch.object(clock, "_stat_time_namespace", lambda: timed("namespace_stat", stat)),
        patch.object(clock, "_parse_process_start_ticks",
                     lambda *a, **kw: timed("process_parse", process, *a, **kw)),
        patch.object(clock, "_parse_namespace_offsets",
                     lambda text: timed("offsets_parse", offsets, text)),
        patch.object(clock, "_validate_identity",
                     lambda x: timed("validate_identity", validate, x)),
        patch.object(SOURCE, "identity", lambda source: timed("identity", IDENTITY, source)),
        patch.object(clock.OperationalClockOwner, "_check",
                     lambda owner: timed("check", check, owner)),
    ):
        clock_batch(n)
        setup_totals, setup_counts = totals.copy(), calls.copy()
        totals.clear()
        calls.clear()
        wall = clock_batch(n * 2)
    # Both batches have equal setup/finalization counts.
    totals.subtract(setup_totals)
    calls.subtract(setup_counts)
    assert calls["check"] == calls["identity"] == 9 * n
    timings = {key: {"count": calls[key], "delta_ns": value} for key, value in totals.items()}
    for label, parse, raw in (("boot_parse", parse_boot, boot_raw),
                              ("offsets_parse_replay", offsets, offsets_raw)):
        for _ in range(9 * n):
            timed(label, parse, raw)
        timings[label] = {"count": calls[label], "delta_ns": totals[label]}
    return {"samples_after_subtracting_equal_setup": n, "second_timed_loop_wall_ns": wall,
            "inclusive_components": timings}


def inventory_counts(path):
    raw = path.read_bytes()
    files = json.loads(raw)["files"]
    counts = {}
    for filename in ("rgb.png", "depth.f32"):
        rows = sorted(
            (int(key.split("/")[1].removeprefix("acquisition-")), info["sha256"])
            for key, info in files.items()
            if key.startswith("frames/acquisition-") and key.endswith("/" + filename)
        )
        assert [index for index, _ in rows] == list(range(1, len(rows) + 1))
        digests = [digest for _, digest in rows]
        counts[filename] = {
            "files": len(digests),
            "distinct_inventory_digests": len(set(digests)),
            "equal_adjacent_inventory_digests": sum(
                a == b for a, b in zip(digests, digests[1:], strict=False)
            ),
        }
    return {"inventory_sha256": hashlib.sha256(raw).hexdigest(), **counts}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--samples", type=int, default=150)
    args = parser.parse_args()
    read = clock._read_proc_text
    boot_raw, offsets_raw = read(BOOT), read(OFFSETS)
    candidate, _, _ = prototype(read, boot_raw, offsets_raw)
    assert candidate(SOURCE()) == IDENTITY(SOURCE())
    validated_cases = controls(boot_raw, offsets_raw)
    clock_batch(20)
    pairs = []
    for order in ("AB", "BA", "BA", "AB"):
        row = {"order": order}
        for name in order:
            with patch.object(SOURCE, "identity", IDENTITY if name == "A" else candidate):
                row[name] = clock_batch(args.samples)
        pairs.append(row)
    result = {
        "production_source": clock.__file__,
        "production_source_sha256": hashlib.sha256(Path(clock.__file__).read_bytes()).hexdigest(),
        "python": sys.version, "platform": platform.platform(),
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "samples_per_pair_arm": args.samples, "control_cases": validated_cases, "pairs_ns": pairs,
        "median_paired_saving_ns_per_operation": statistics.median(
            (row["A"] - row["B"]) / args.samples for row in pairs
        ),
        "profile": profile(args.samples, boot_raw, offsets_raw),
        "inventory": inventory_counts(args.inventory),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
