"""Reproduction checks bytes and assignment coverage without inventing acceptance."""

import hashlib
import importlib
import json

import pytest


def api():
    return importlib.import_module("cloud_edge_robot_arm.research.reproducibility")


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def bundle(tmp_path):
    files = {"source/example.py": "x = 1\n", "assets/scene.xml": "<mujoco/>\n",
             "records/failed.json": '{"assignment":{"assignment_id":"a"},'
                                    '"run_status":"FAILED"}\n',
             "records/blocked.json": '{"assignment":{"assignment_id":"b"},'
                                     '"run_status":"BLOCKED"}\n'}
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    index = {"schema_version": "ced.reproduction-index.v1", "assignments": ["a", "b"],
             "records": {"a": "records/failed.json", "b": "records/blocked.json"}}
    (tmp_path / "assignments.json").write_text(json.dumps(index))
    hashes = {name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
              for name in [*files, "assignments.json"]}
    sources = {"source/example.py": hashes["source/example.py"]}
    manifest = api().ReproductionManifest(
        digest(sources), {}, {"assets/scene.xml": hashes["assets/scene.xml"]}, "", "", {},
        [20261004], [["python", "diagnostic.py"]], hashes, source_hashes=sources,
        assignment_index_path="assignments.json", scope="SOFTWARE_ONLY",
    )
    api().write_reproduction_manifest(manifest, tmp_path)
    return manifest


def test_bundle_keeps_failed_and_blocked_assignments(tmp_path):
    bundle(tmp_path)
    report = api().verify_reproduction_bundle(tmp_path)
    assert report["integrity_valid"] is True
    assert report["assignment_count"] == report["record_count"] == 2
    assert report["research_accepted"] is False
    assert report["scope"] == "SOFTWARE_ONLY"


def test_bundle_hash_mismatch_blocks_reproduction(tmp_path):
    bundle(tmp_path)
    (tmp_path / "records/failed.json").write_text('{"run_status":"SUCCESS"}\n')
    report = api().verify_reproduction_bundle(tmp_path)
    assert report["integrity_valid"] is False
    assert any("hash" in reason for reason in report["errors"])


def test_rehashed_index_cannot_omit_a_failed_assignment(tmp_path):
    manifest = bundle(tmp_path)
    path = tmp_path / "assignments.json"
    index = json.loads(path.read_text())
    del index["records"]["a"]
    path.write_text(json.dumps(index))
    payload = manifest.to_payload()
    payload["artifact_hashes"]["assignments.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "reproduction-manifest.json").write_text(json.dumps({
        "schema_version": "ced.reproduction-manifest.v1", "manifest": payload,
        "content_hash": digest(payload),
    }))
    assert api().verify_reproduction_bundle(tmp_path)["integrity_valid"] is False


def test_rehashed_index_cannot_delete_both_assignment_and_failed_record_reference(tmp_path):
    manifest = bundle(tmp_path)
    path = tmp_path / "assignments.json"
    index = json.loads(path.read_text())
    index["assignments"].remove("a")
    del index["records"]["a"]
    path.write_text(json.dumps(index))
    payload = manifest.to_payload()
    payload["artifact_hashes"]["assignments.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "reproduction-manifest.json").write_text(json.dumps({
        "schema_version": "ced.reproduction-manifest.v1", "manifest": payload,
        "content_hash": digest(payload),
    }))
    assert api().verify_reproduction_bundle(tmp_path)["integrity_valid"] is False


def test_bound_original_assignment_list_survives_dual_index_and_record_deletion(tmp_path):
    manifest = bundle(tmp_path)
    payload = manifest.to_payload()
    for name in ("records/failed.json", "records/blocked.json"):
        del payload["artifact_hashes"][name]
    runs = tmp_path / "runs"
    runs.mkdir()
    original = {"schema_version": "ced.assignments.v1", "protocol_hash": "a" * 64,
                "assignments": [{"assignment_id": "a"}, {"assignment_id": "b"}]}
    original["content_hash"] = digest(original)
    (runs / "assignments.json").write_text(json.dumps(original))
    records = runs / "records.jsonl"
    records.write_text("\n".join(json.dumps({"assignment": {"assignment_id": value},
                                           "run_status": "BLOCKED"}) for value in ("a", "b")))
    index_path = tmp_path / "assignments.json"
    index = {"schema_version": "ced.reproduction-index.v1", "assignments": ["a", "b"],
             "records": {"a": "runs/records.jsonl", "b": "runs/records.jsonl"}}
    index_path.write_text(json.dumps(index))
    payload["runs_path"] = "runs"
    def republish():
        for path in (runs / "assignments.json", records, index_path):
            payload["artifact_hashes"][path.relative_to(tmp_path).as_posix()] = (
                hashlib.sha256(path.read_bytes()).hexdigest())
        (tmp_path / "reproduction-manifest.json").write_text(json.dumps({
            "schema_version": "ced.reproduction-manifest.v1", "manifest": payload,
            "content_hash": digest(payload),
        }))
    republish()
    assert api().verify_reproduction_bundle(tmp_path)["integrity_valid"] is True
    index["assignments"].remove("a")
    del index["records"]["a"]
    index_path.write_text(json.dumps(index))
    records.write_text(json.dumps({"assignment": {"assignment_id": "b"},
                                   "run_status": "BLOCKED"}))
    republish()
    assert api().verify_reproduction_bundle(tmp_path)["integrity_valid"] is False


@pytest.mark.parametrize("unsafe", ["../outside", "/tmp/outside", "source/../../outside"])
def test_manifest_paths_cannot_escape_bundle(tmp_path, unsafe):
    manifest = bundle(tmp_path)
    payload = manifest.to_payload()
    payload["artifact_hashes"][unsafe] = "a" * 64
    (tmp_path / "reproduction-manifest.json").write_text(json.dumps({
        "schema_version": "ced.reproduction-manifest.v1", "manifest": payload,
        "content_hash": digest(payload),
    }))
    assert api().verify_reproduction_bundle(tmp_path)["integrity_valid"] is False


def test_source_tree_aggregate_is_checked(tmp_path):
    manifest = bundle(tmp_path)
    payload = manifest.to_payload()
    payload["source_tree_hash"] = "f" * 64
    (tmp_path / "reproduction-manifest.json").write_text(json.dumps({
        "schema_version": "ced.reproduction-manifest.v1", "manifest": payload,
        "content_hash": digest(payload),
    }))
    assert api().verify_reproduction_bundle(tmp_path)["integrity_valid"] is False


def test_unexecuted_extension_is_not_accepted(tmp_path):
    bundle(tmp_path)
    report = api().verify_reproduction_bundle(tmp_path)
    assert report["physical_reproduction"] == "NOT_RUN"
    assert report["research_accepted"] is False


def test_rebuild_refuses_corrupted_bundle_before_any_output(tmp_path):
    bundle(tmp_path)
    (tmp_path / "source/example.py").write_text("changed\n")
    output = tmp_path / "reproduced"
    with pytest.raises(ValueError, match="integrity"):
        api().rebuild_analysis(tmp_path, output)
    assert not output.exists()


def test_declared_shell_arguments_are_never_executed(tmp_path):
    manifest = bundle(tmp_path)
    payload = manifest.to_payload()
    payload["command_arguments"] = [["touch", str(tmp_path / "sentinel")]]
    (tmp_path / "reproduction-manifest.json").write_text(json.dumps({
        "schema_version": "ced.reproduction-manifest.v1", "manifest": payload,
        "content_hash": digest(payload),
    }))
    assert api().verify_reproduction_bundle(tmp_path)["integrity_valid"] is True
    assert not (tmp_path / "sentinel").exists()


def test_jsonl_record_index_checks_actual_assignment_ids(tmp_path):
    manifest = bundle(tmp_path)
    path = tmp_path / "records/all.jsonl"
    path.write_text('\n'.join(json.dumps({"assignment": {"assignment_id": value},
                                          "run_status": "BLOCKED"}) for value in ("a", "b")))
    index_path = tmp_path / "assignments.json"
    index = json.loads(index_path.read_text())
    index["records"] = {"a": "records/all.jsonl", "b": "records/all.jsonl"}
    index_path.write_text(json.dumps(index))
    payload = manifest.to_payload()
    for file in (path, index_path):
        payload["artifact_hashes"][file.relative_to(tmp_path).as_posix()] = (
            hashlib.sha256(file.read_bytes()).hexdigest())
    (tmp_path / "reproduction-manifest.json").write_text(json.dumps({
        "schema_version": "ced.reproduction-manifest.v1", "manifest": payload,
        "content_hash": digest(payload),
    }))
    assert api().verify_reproduction_bundle(tmp_path)["integrity_valid"] is True
    path.write_text(json.dumps({"assignment": {"assignment_id": "a"}}))
    payload["artifact_hashes"]["records/all.jsonl"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "reproduction-manifest.json").write_text(json.dumps({
        "schema_version": "ced.reproduction-manifest.v1", "manifest": payload,
        "content_hash": digest(payload),
    }))
    assert api().verify_reproduction_bundle(tmp_path)["integrity_valid"] is False


@pytest.mark.parametrize("value", [[], {"schema_version": "ced.reproduction-index.v1",
    "assignments": ["a"], "records": {"a": 12}}])
def test_malformed_index_returns_invalid_instead_of_crashing(tmp_path, value):
    manifest = bundle(tmp_path)
    path = tmp_path / "assignments.json"
    path.write_text(json.dumps(value))
    payload = manifest.to_payload()
    payload["artifact_hashes"]["assignments.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "reproduction-manifest.json").write_text(json.dumps({
        "schema_version": "ced.reproduction-manifest.v1", "manifest": payload,
        "content_hash": digest(payload),
    }))
    assert api().verify_reproduction_bundle(tmp_path)["integrity_valid"] is False


def test_rehashed_json_record_must_belong_to_its_indexed_assignment(tmp_path):
    manifest = bundle(tmp_path)
    path = tmp_path / "records/failed.json"
    path.write_text(json.dumps({"assignment": {"assignment_id": "other"},
                                "run_status": "FAILED"}))
    payload = manifest.to_payload()
    payload["artifact_hashes"]["records/failed.json"] = (
        hashlib.sha256(path.read_bytes()).hexdigest())
    (tmp_path / "reproduction-manifest.json").write_text(json.dumps({
        "schema_version": "ced.reproduction-manifest.v1", "manifest": payload,
        "content_hash": digest(payload),
    }))
    assert api().verify_reproduction_bundle(tmp_path)["integrity_valid"] is False


def test_recomputed_metrics_match_saved_results(tmp_path):
    from dataclasses import asdict

    from cloud_edge_robot_arm.datasets.rgbd.models import canonical_json, content_digest
    from cloud_edge_robot_arm.research.acceptance import analyze_research_runs
    from cloud_edge_robot_arm.research.assignments import build_assignments
    from cloud_edge_robot_arm.research.protocol import FrozenProtocol, ProtocolSpec
    from cloud_edge_robot_arm.research.runner import run_assignment
    from tests.test_research_assignments import scene_pool

    pools = {"formal": scene_pool.__wrapped__()}
    methods = ("JOINT", "B0", "B1", "B2", "NO_UNCERTAINTY", "NO_TIME_VALIDITY",
               "NO_LOCAL_REPAIR")
    spec = ProtocolSpec(selected_n=600, tcap_s=120,
        pool_hashes={"formal": content_digest(pools["formal"])}, model_snapshot_hash="a" * 64,
        method_hashes={key: content_digest(key) for key in methods},
        initial_protocol_hash="b" * 64, opportunity_hash="c" * 64,
        recovery_fault_manifest_hash="d" * 64)
    frozen = FrozenProtocol(spec=spec, stage="FINAL", content_hash=content_digest({
        "spec": spec.model_dump(mode="json"), "stage": "FINAL"}))
    runs, protocol = tmp_path / "runs", tmp_path / "protocol"
    runs.mkdir()
    protocol.mkdir()
    (protocol / "protocol.json").write_text(frozen.model_dump_json())
    assignments = build_assignments(frozen, methods, scene_pool=pools["formal"])
    assigned = {"schema_version": "ced.assignments.v1", "protocol_hash": frozen.content_hash,
                "assignments": [asdict(row) for row in assignments]}
    assigned["content_hash"] = content_digest(assigned)
    (runs / "assignments.json").write_text(canonical_json(assigned))
    (runs / "pools.json").write_text(canonical_json(pools))
    (runs / "records.jsonl").write_text("\n".join(
        canonical_json(run_assignment(row, frozen).to_payload(protocol=frozen))
        for row in assignments) + "\n")
    saved = tmp_path / "saved"
    original = analyze_research_runs(runs, protocol, saved, software_only=True)
    assert original["status"] == "SOFTWARE_ONLY"
    assert json.loads((saved / "metrics.json").read_text())["assignment_denominator"] == 4200
    source = tmp_path / "source/example.py"
    source.parent.mkdir()
    source.write_text("# explicitly blocked software fixture\n")
    index = {"schema_version": "ced.reproduction-index.v1",
             "assignments": [row.assignment_id for row in assignments],
             "records": {row.assignment_id: "runs/records.jsonl" for row in assignments}}
    (tmp_path / "index.json").write_text(canonical_json(index))
    hashes = {p.relative_to(tmp_path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in tmp_path.rglob("*") if p.is_file()}
    sources = {"source/example.py": hashes["source/example.py"]}
    manifest = api().ReproductionManifest(digest(sources), {}, {}, "a" * 64,
        frozen.content_hash, {}, [20261004], [["never", "execute"]], hashes,
        source_hashes=sources, assignment_index_path="index.json", runs_path="runs",
        protocol_path="protocol", analysis_path="saved", scope="SOFTWARE_ONLY")
    api().write_reproduction_manifest(manifest, tmp_path)
    output = tmp_path / "rebuilt"
    api().rebuild_analysis(tmp_path, output, software_only=True)
    rebuilt = json.loads((output / "reproduction.json").read_text())
    assert rebuilt["matches_saved_analysis"] is True
    assert rebuilt["numeric_rebuild"] == "SOFTWARE_ONLY"
    assert rebuilt["physical_reproduction"] == "NOT_RUN"
    assert rebuilt["research_accepted"] is False
    assert json.loads((saved / "metrics.json").read_text()) == json.loads(
        (output / "metrics.json").read_text())
    payload = manifest.to_payload()
    payload["model_snapshot_hash"] = "f" * 64
    (tmp_path / "reproduction-manifest.json").write_text(json.dumps({
        "schema_version": "ced.reproduction-manifest.v1", "manifest": payload,
        "content_hash": digest(payload),
    }))
    assert api().verify_reproduction_bundle(tmp_path)["integrity_valid"] is False
    with pytest.raises(ValueError, match="model"):
        api().rebuild_analysis(tmp_path, tmp_path / "wrong-model", software_only=True)
    assert not (tmp_path / "wrong-model").exists()
