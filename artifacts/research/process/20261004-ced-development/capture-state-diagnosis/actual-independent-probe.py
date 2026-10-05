"""Read only saved original diagnostic bytes; import no execution/backend module."""

from __future__ import annotations

import base64
import gzip
import hashlib
import importlib.metadata
import json
import math
import struct
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
ACTUAL = HERE / "diagnostic-1"
PRIOR = HERE.parent / "t7b-continuous-visibility"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def jbytes(value):
    return json.dumps(value, sort_keys=True, allow_nan=False).encode()


def read_json(path):
    return json.loads(path.read_text())


def saved_bytes(reference):
    zipped = (ACTUAL / reference["file"]).read_bytes()
    raw = gzip.decompress(zipped)
    assert sha(zipped) == reference["compressed_sha256"]
    assert sha(raw) == reference["original_sha256"]
    assert len(zipped) == reference["compressed_bytes"]
    assert len(raw) == reference["original_bytes"]
    return raw


def snapshot(path):
    payload = json.loads(gzip.decompress(path.read_bytes()))
    members = payload["data_arrays"]["members"]
    assert members.keys() == payload["array_bytes_base64"].keys()
    assert members.keys() == payload["data_array_topology"].keys()
    digest = hashlib.sha256()
    raw_members = {}
    for name, described in sorted(members.items()):
        raw = base64.b64decode(payload["array_bytes_base64"][name], validate=True)
        assert len(raw) == described["bytes"] == math.prod(described["shape"]) * int(
            described["dtype"][2:]
        )
        assert sha(raw) == described["sha256"]
        digest.update(jbytes((name, described["shape"], described["dtype"])))
        digest.update(raw)
        raw_members[name] = raw
    assert digest.hexdigest() == payload["data_arrays"]["aggregate_sha256"]
    assert digest.hexdigest() == payload["state"]["data_arrays_sha256"]
    return payload, raw_members


def differences(left, right):
    before, before_raw = left
    after, after_raw = right
    assert before_raw.keys() == after_raw.keys()
    return {
        name: {
            "before": before["data_arrays"]["members"][name],
            "after": after["data_arrays"]["members"][name],
            "before_topology": before["data_array_topology"][name],
            "after_topology": after["data_array_topology"][name],
            "different_byte_positions": sum(
                a != b for a, b in zip(before_raw[name], after_raw[name], strict=True)
            ),
        }
        for name in before_raw
        if before_raw[name] != after_raw[name]
        or before["data_arrays"]["members"][name] != after["data_arrays"]["members"][name]
    }


def observation(reference):
    payload = json.loads(saved_bytes(reference))
    rgb, depth, mask = (
        base64.b64decode(payload[name], validate=True)
        for name in ("rgb_png_base64", "depth_float32_base64", "valid_mask_base64")
    )
    assert rgb[:8] == b"\x89PNG\r\n\x1a\n" and rgb[12:16] == b"IHDR"
    assert struct.unpack(">II", rgb[16:24]) == (payload["width"], payload["height"])
    assert rgb[24:26] == b"\x08\x02"  # Eight-bit RGB; no pixel/marker decoder called.
    assert len(depth) == payload["width"] * payload["height"] * 4
    depths = [value[0] for value in struct.iter_unpack("<f", depth)]
    assert all(math.isfinite(value) and value >= 0 for value in depths)
    assert mask == bytes(int(value > 0) for value in depths)
    fields = {
        name: payload[name]
        for name in (
            "frame_id", "sim_time_s", "source", "depth_convention", "scene_id", "episode_id",
            "calibration_version", "width", "height", "intrinsics", "camera_to_world",
        )
    }
    fields["captured_at"] = datetime.fromisoformat(payload["captured_at"]).astimezone(UTC).isoformat()
    fields.update(rgb_sha256=sha(rgb), depth_sha256=sha(depth), mask_sha256=sha(mask))
    checksum = sha(json.dumps(fields, sort_keys=True).encode())
    assert checksum == payload["checksum_sha256"] == reference["observation_checksum_sha256"]
    assert payload["frame_id"] == payload["observation_id"]
    return payload, {"rgb.png": sha(rgb), "depth.f32": sha(depth), "mask.u8": sha(mask)}


def main():
    frozen = read_json(HERE / "diagnostic-1-file-hashes.json")
    files = frozen["files"]
    assert len(files) == frozen["file_count"] == 142
    actual_names = {str(path.relative_to(HERE)) for path in ACTUAL.rglob("*") if path.is_file()}
    assert actual_names == {row["file"] for row in files}
    for row in files:
        raw = (HERE / row["file"]).read_bytes()
        assert len(raw) == row["bytes"] and sha(raw) == row["sha256"]
    assert sum(row["bytes"] for row in files) == frozen["total_bytes"] == 7876865
    inventory = read_json(ACTUAL / "files.json")
    assert len(inventory) == 141
    assert all(sha((ACTUAL / name).read_bytes()) == row["sha256"] for name, row in inventory.items())
    header = read_json(HERE / "header.json")
    assert sha((HERE / "header.json").read_bytes()) == frozen["source_header_sha256"]
    assert sha((HERE / "execution-source-hashes.json").read_bytes()) == header[
        "source_manifest_sha256"
    ] == frozen["source_manifest_sha256"]
    assert sha((HERE / "execution-archive-index.json").read_bytes()) == header[
        "source_archive_index_sha256"
    ]
    manifest = read_json(HERE / "execution-source-hashes.json")
    archive = read_json(HERE / "execution-archive-index.json")
    assert len(manifest) == header["source_count"] == 33
    assert manifest.keys() == archive.keys()
    for name, expected in manifest.items():
        assert sha((ROOT / name).read_bytes()) == expected == archive[name]["sha256"]
        assert sha((HERE.parent / archive[name]["archive"]).read_bytes()) == expected
        assert (ROOT / name).stat().st_size == archive[name]["bytes"]
    assert sum(row["bytes"] for row in archive.values()) == header["source_bytes"] == 441826
    assert sha((HERE / "test_cpu.py").read_bytes()) == header["cpu_test_sha256"]
    dependencies = header["environment"]["files"]
    assert len(dependencies) == 19
    assert all(sha(Path(row["path"]).read_bytes()) == row["sha256"] for row in dependencies.values())
    assert importlib.metadata.version("mujoco") == header["environment"]["mujoco_version"]
    assert importlib.metadata.version("numpy") == header["environment"]["numpy_version"]
    protection = read_json(HERE.parent / "t7b-continuous-visibility-v2/input-protection.json")
    assert all(sha((PRIOR / "attempt-1" / name).read_bytes()) == row["expected_sha256"] for name, row in protection["prior_attempt_files"].items())
    assert all(sha((PRIOR / name).read_bytes()) == row["expected_sha256"] for name, row in protection["protected"].items())
    assert sha((PRIOR / "execution-source-hashes.json").read_bytes()) == header[
        "inherited_32_reference_manifest_sha256"
    ]

    records = [json.loads(line) for line in gzip.decompress((ACTUAL / "journal.jsonl.gz").read_bytes()).splitlines()]
    event_counts = dict(Counter(row["event"] for row in records))
    last_ns = last_utc = None
    for sequence, row in enumerate(records, 1):
        assert row["record_seq"] == sequence
        clock = row["clock"]
        start, end = clock["monotonic_before_ns"], clock["monotonic_after_ns"]
        utc = datetime.fromisoformat(clock["utc"])
        assert start <= end and (last_ns is None or last_ns <= start)
        assert last_utc is None or last_utc <= utc
        assert clock["external_utc_uncertainty"] == "UNAVAILABLE"
        last_ns, last_utc = end, utc
    summary, terminal = read_json(ACTUAL / "summary.json"), read_json(ACTUAL / "terminal.json")
    assert summary["status"] == "DIAGNOSTIC_PARTIAL_OR_FAILED"
    assert summary["physical_steps"] == terminal["physical_step"] == 10
    assert summary["captures_started"] == summary["capture_attempts_allocated"] == summary["camera_calls_started"] == summary["captures_completed"] == 11
    assert summary["captures_failed"] == event_counts.get("CAPTURE_FAILED", 0) == 0
    assert summary["captures_started"] == summary["captures_completed"] + summary["captures_failed"]
    assert summary["counts"]["terminal_copy_attempts"] == 1
    assert summary["counts"]["terminal_copy_rejected"] == 0
    assert summary["counts"]["terminal_clone_capture_calls"] == 0
    assert not any("DETACHED" in row["event"] or row.get("detached") for row in records)
    assert not terminal["commands"] and not terminal["operation_observer_failures"]
    assert summary["teacher_actions"] == summary["motion_commands"] == summary["decoder_calls"] == 0
    assert summary["formal_accepted"] is False and not summary["independent_calibration_group"]
    assert summary["native_admission"] == "NOT_PROMOTED"
    assert summary["continuous_motion"] == "NOT_CERTIFIED"
    assert summary["future_stability"] == "UNAVAILABLE"
    assert not summary["original_attempt_retried"]
    assert "RuntimeError: copy.copy changed original live state" in (ACTUAL / "failure.txt").read_text()

    snapshots = {str(path.relative_to(ACTUAL)): snapshot(path) for path in sorted((ACTUAL / "snapshots").glob("*-snapshot.gz"))}
    assert len(snapshots) == 101
    phases_by_capture = {}
    for row in records:
        if row["event"] == "DATA_SNAPSHOT":
            value = row["snapshot"]
            original = json.loads(saved_bytes(value["saved"]))
            assert all(original[key] == value[key] for key in original if key != "array_bytes_base64")
            phases_by_capture.setdefault(row["capture_ordinal"], {})[value["phase"]] = snapshots[value["saved"]["file"]]
            assert value["monotonic_begin_ns"] <= value["monotonic_end_ns"] <= row["clock"]["monotonic_before_ns"]
    assert len(phases_by_capture) == 11 and all(len(v) == 9 for v in phases_by_capture.values())
    repeated = []
    render_files = []
    for row in records:
        if row["event"] == "REPEATED_BEFORE":
            phases = phases_by_capture[row["capture_ordinal"]]
            diff = differences(phases["CAPTURE_BEFORE"], phases["BEFORE_REPEAT"])
            assert sorted(diff) == row["changed_members"]
            if diff:
                repeated.append({"capture_ordinal": row["capture_ordinal"], "fields": diff})
        elif row["event"] == "RENDER_PHASE":
            before, after = snapshots[row["before_snapshot"]["file"]], snapshots[row["after_snapshot"]["file"]]
            assert not differences(before, after)
            assert row["before_state"] == row["after_state"] == before[0]["state"] == after[0]["state"]
            assert not row["changed_members"] and row["error_type"] is None
            if row["render_payload"]:
                saved = row["render_payload"]
                raw = saved_bytes(saved)
                assert len(raw) == math.prod(saved["shape"]) * int(saved["dtype"][2:])
                render_files.append(saved["file"])
    assert len(render_files) == len(set(render_files)) == 22
    assert event_counts["RENDER_PHASE"] == 33
    assert len(repeated) == 1 and repeated[0]["capture_ordinal"] == 1
    assert sorted(repeated[0]["fields"]) == ["dof_island", "iLD", "iM", "map_dof2idof", "map_idof2dof"]
    assert all(v[side]["owns_data"] and v[side]["base_type"] == "builtins.NoneType" for v in repeated[0]["fields"].values() for side in ("before_topology", "after_topology"))

    copy_before = next(v for v in snapshots.values() if v[0]["phase"] == "COPY_LIVE_BEFORE")
    copy_after = next(v for v in snapshots.values() if v[0]["phase"] == "COPY_LIVE_AFTER")
    copy_diff = differences(copy_before, copy_after)
    assert sorted(copy_diff) == ["efc_AR_rowadr", "efc_AR_rownnz"]
    protected = set(copy_before[0]["state"]) - {"data_arrays_sha256"}
    assert all(copy_before[0]["state"][key] == copy_after[0]["state"][key] for key in protected)
    assert all(v[side]["owns_data"] and v[side]["base_type"] == "builtins.NoneType" for v in copy_diff.values() for side in ("before_topology", "after_topology"))

    operations = {(row["source"]["operation_id"], row["source"]["phase"]): row for row in records if row["event"] == "OPERATION"}
    physical = {row["source"]["physics_step"]: row for row in records if row["event"] == "PHYSICAL_SOURCE"}
    actuators = {row["source"]["physics_step"]: row for row in records if row["event"] == "ACTUATOR"}
    begins = {row["physics_step"]: row for row in records if row["event"] == "CAPTURE_BEGIN"}
    ends = {row["physics_step"]: row for row in records if row["event"] == "CAPTURE_END"}
    assert sorted(physical) == sorted(begins) == sorted(ends) == list(range(11))
    assert sorted(actuators) == list(range(1, 11))
    joins, observation_members = [], []
    context = None
    previous_time = None
    max_gap = 0.0
    for step in range(11):
        begin, end, source = begins[step], ends[step], physical[step]
        obs, member_hashes = observation(end["saved"])
        identity = (terminal["episode_id"], step, source["source"]["sim_time_s"])
        assert (begin["episode_id"], begin["physics_step"], begin["sim_time_s"]) == identity
        assert (end["episode_id"], end["physics_step"], end["sim_time_s"]) == identity
        assert (obs["episode_id"], obs["sim_time_s"]) == (identity[0], identity[2])
        assert begin["capture_ordinal"] == end["capture_ordinal"] == step + 1
        assert end["monotonic_begin_ns"] <= begin["clock"]["monotonic_before_ns"] <= end["monotonic_end_ns"] <= end["clock"]["monotonic_before_ns"]
        assert datetime.fromisoformat(begin["clock"]["utc"]) <= datetime.fromisoformat(obs["captured_at"]) <= datetime.fromisoformat(end["clock"]["utc"])
        assert end["renderer_counts"] == {"render": 2, "update_scene": 1}
        assert len(end["pass_state_hashes"]) == 2 and len(set(end["pass_state_hashes"])) == 1
        before, after = phases_by_capture[step + 1]["CAPTURE_BEFORE"], phases_by_capture[step + 1]["CAPTURE_AFTER"]
        assert end["before_state"] == before[0]["state"] and end["after_state"] == after[0]["state"]
        assert sorted(differences(before, after)) == end["changed_members"]
        assert end["original_whole_step_guard_would_accept"] == (before[0]["state"] == after[0]["state"])
        assert all(before[0]["state"][key] == after[0]["state"][key] for key in protected)
        current = {key: obs[key] for key in ("width", "height", "intrinsics", "camera_to_world", "source", "scene_id", "calibration_version")}
        assert context is None or current == context
        context = current
        if previous_time is not None:
            gap = obs["sim_time_s"] - previous_time
            assert 0 < gap <= 0.005
            max_gap = max(max_gap, gap)
        previous_time = obs["sim_time_s"]
        observation_members.append({"step": step, "saved_file": end["saved"]["file"], "raw_member_sha256": member_hashes})
        if step:
            control_id, physics_id = source["control_operation_id"], source["physics_operation_id"]
            control_begin, control_end = operations[(control_id, "BEGIN")], operations[(control_id, "END")]
            physics_begin, physics_end = operations[(physics_id, "BEGIN")], operations[(physics_id, "END")]
            actuator = actuators[step]
            assert control_begin["source"]["kind"] == control_end["source"]["kind"] == "CONTROL"
            assert physics_begin["source"]["kind"] == physics_end["source"]["kind"] == "PHYSICS"
            assert control_begin["source"]["physics_step"] == control_end["source"]["physics_step"] == physics_begin["source"]["physics_step"] == step - 1
            assert physics_end["source"]["physics_step"] == step
            assert actuator["source"]["episode_id"] == terminal["episode_id"]
            assert actuator["source"]["sim_time_s"] == control_end["source"]["sim_time_s"]
            assert physics_end["source"]["sim_time_s"] == source["source"]["sim_time_s"]
            ordered = [control_begin, control_end, actuator, physics_begin, physics_end, source, begin]
            assert all(a["clock"]["monotonic_after_ns"] <= b["clock"]["monotonic_before_ns"] for a, b in zip(ordered, ordered[1:]))
            joins.append({"step": step, "control_operation_id": control_id, "physics_operation_id": physics_id, "record_sequences": [row["record_seq"] for row in ordered], "actuator_operation_pointer": actuator.get("control_operation_id"), "clock_order_valid": True})
    assert previous_time == terminal["sim_time_s"]
    assert summary["captures_with_state_differences"] == 1
    bootstrap = next(row for row in records if row["event"] == "BOOTSTRAP_SAVED")
    observation(bootstrap["saved"])
    setup = read_json(ACTUAL / "setup-members.json")
    assert len(setup) == summary["counts"]["setup_capture_calls"] == 1
    observation(setup[0])
    # Recheck the frozen original byte inventory after the read-only probe.
    assert all(sha((HERE / row["file"]).read_bytes()) == row["sha256"] for row in files)
    report = {
        "scope": "READ_ONLY_ORIGINAL_DIAGNOSTIC_BYTE_AND_SOURCE_AUDIT",
        "status": "SCOPED_PASS_ACTUAL_DIAGNOSTIC_REMAINS_PARTIAL",
        "actual_exit_code": frozen["actual_exit_code"], "wall_elapsed_s": summary["wall_elapsed_s"],
        "frozen_raw_file_count": 142, "frozen_raw_bytes": 7876865,
        "all_raw_pins_match_before_and_after": True,
        "source_pins": {"count": 33, "bytes": 441826, "live_archive_match": True, "dependency_files": 19, "dependency_match": True, "header_sha256": sha((HERE / "header.json").read_bytes()), "manifest_sha256": sha((HERE / "execution-source-hashes.json").read_bytes())},
        "parent_protection": {"old_attempt_files": 23, "protected_reports_and_pins": 7, "all_match": True},
        "denominator": {"passive_physics_steps": 10, "live_allocated": 11, "live_camera_calls_started": 11, "live_completed": 11, "live_failed": 0, "copy_attempts": 1, "copy_rejected_published": 0, "copy_validated_published": 0, "clone_camera_calls": 0, "copy_result": "ABORTED_BY_LIVE_SNAPSHOT_HASH_GUARD_BEFORE_VALIDATION_OR_REJECTION_PUBLICATION"},
        "event_counts": event_counts, "nominal_monotonic_and_utc_order_valid": True,
        "journal_array_snapshots": 99, "terminal_copy_array_snapshots": 2, "raw_member_count_per_snapshot": 154,
        "all_snapshot_member_bytes_and_aggregate_hashes_recomputed": True,
        "render_phases": 33, "unchanged_render_phase_snapshots": 33, "original_render_array_files": 22,
        "full_rgbd_payloads": {"live": 11, "setup": 1, "bootstrap": 1, "member_checksums_and_lengths_match": True},
        "step0_repeat_original_byte_differences": repeated,
        "terminal_copy_original_byte_differences": copy_diff,
        "other_protected_copy_state_fields_unchanged": sorted(protected),
        "upcoming_step_joins": joins,
        "diagnostic_actuator_operation_pointer_limit": "ACTUATOR has no explicit operation pointer; joins above independently reconstruct the unique PHYSICAL_SOURCE-bound CONTROL/PHYSICS operations using episode/step/time and strict clocks.",
        "raw_rgbd_member_hashes": observation_members,
        "observed_max_sim_sample_gap_s": max_gap, "original_max_sample_gap_s": 0.005,
        "teacher_actions": 0, "motion_commands": 0, "marker_decoder_calls": 0,
        "new_execution_calls_by_this_review": 0,
        "classification": "UNRESOLVED_NO_GUARD_RELAXATION",
        "authority": {"formal_accepted": False, "native_admission": "NOT_PROMOTED", "continuous_motion": "NOT_CERTIFIED", "future_stability": "UNAVAILABLE", "calibrated_error_bound": "UNAVAILABLE", "external_utc_uncertainty": "UNAVAILABLE"},
        "limits": ["Recorded public accessor owning-array byte differences are not proof of changed live simulation storage or render causality.", "The detached-copy contract was not published or validated; zero rejection events cannot imply validity.", "This 10-step diagnostic does not replace the old failed 11/10/1 attempt or complete original action horizons."]
    }
    with (HERE / "actual-independent-audit.json").open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "raw_files": 142, "source_pins": 33, "dependencies": 19, "live": "11/11/0", "copy": "1 attempt / 0 clone / not validated", "render_phases_unchanged": 33, "upcoming_joins": 10}, indent=2))


if __name__ == "__main__":
    main()
