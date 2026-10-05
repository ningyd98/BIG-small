"""Safety checks for freezing a real local RGB-D model probe."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import probe_rgbd_model as probe
from scripts.probe_rgbd_model import (
    archive_previous_owned_freeze,
    can_freeze,
    summarize_chat_request,
    write_frozen_if_verified,
)


def _passing_report() -> dict[str, object]:
    request_texts = [
        {"role": "system", "content": "Offline gate fixture"},
        {"role": "user", "content": "pick red cube"},
    ]
    attempt = {
        "transport_two_images": True,
        "parsed": True,
        "grounded": True,
        "target_hit": True,
        "destination_hit": True,
        "inherited_parameters": "presence_penalty 1.5",
        "request_texts": request_texts,
        "capture_path": "offline-fixture",
        "observation": {"source": "mujoco_camera"},
        "loaded_model_after_call": {
            "name": "qwen3.5:4b", "digest": "a" * 64, "size_vram": 1024,
        },
        "observation_evidence": {
            "top_grasp_offset_status": "CALIBRATED_RGBD_TOP_GRASP_V1",
            "resolved_top_grasp_tcp": {"x": 0.4, "y": 0.0, "z": 0.02},
            "grasp_profile": "mujoco_upright_box_v2",
            "grasp_calibration_asset_sha256": (
                "66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2"
            ),
        },
        "request_summary": {
            "model": "qwen3.5:4b", "stream": False, "think": False,
            "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 512},
            "format_sha256": "b" * 64,
            "message_roles": ["system", "user"],
            "message_text_sha256": [
                hashlib.sha256(item["content"].encode()).hexdigest() for item in request_texts
            ],
            "image_count": 2, "distinct_image_count": 2,
            "image_sha256": ["e" * 64, "f" * 64], "image_bytes": [3, 3],
        },
    }
    attempt["expected_request_summary"] = copy.deepcopy(attempt["request_summary"])
    return {
        "source": "mujoco_camera",
        "capture": {"synchronized": True},
        "model": {
            "name": "qwen3.5:4b", "expected_digest": "a" * 64,
            "digest_matches": True, "quantization_matches": True, "vision": True,
            "inherited_parameters": "presence_penalty 1.5",
        },
        "snapshot": _snapshot(),
        "probe_config": {
            "scenario_id": "S01_NORMAL_STATIC", "seed": 0,
            "instruction": "pick red cube", "warm_runs": 3,
        },
        "source_fingerprints": _source_fingerprints(),
        "device": {"cuda": True},
        "attempts": [copy.deepcopy(attempt) for _ in range(4)],
        "timing": {"warm_samples": 3},
    }


def _snapshot() -> dict[str, object]:
    return {
        "provider": "ollama", "model": "qwen3.5:4b",
        "endpoint": "http://127.0.0.1:11434", "weight_digest": "a" * 64,
        "quantization": "Q4_K_M", "image_size": [320, 240],
        "generation_parameters": {
            "temperature": 0, "num_ctx": 8192, "num_predict": 512, "think": False,
        },
        "timeout_s": 180.0,
        "grasp_profile": "mujoco_upright_box_v2",
    }


def _source_fingerprints() -> dict[str, str]:
    root = Path(__file__).resolve().parents[1]
    files = [
        "scripts/probe_rgbd_model.py",
        "assets/robots/franka_panda/scene.xml",
        *[f"src/cloud_edge_robot_arm/vision/{name}.py" for name in
          ("planner", "messages", "observations", "model_resolver", "capture", "top_grasp")],
    ]
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files}


@pytest.mark.parametrize("field,value", [
    ("loaded_model_after_call", None),
    ("loaded_model_after_call", {"name": "qwen3.5:4b", "digest": "a" * 64, "size_vram": 0}),
    ("loaded_model_after_call", {"name": "other", "digest": "a" * 64, "size_vram": 10}),
    ("loaded_model_after_call", {"name": "qwen3.5:4b", "digest": "b" * 64, "size_vram": 10}),
    ("observation_evidence", {}),
    ("observation_evidence", {
        "top_grasp_offset_status": "REQUIRES_OBJECT_AND_TOOL_GEOMETRY",
        "resolved_top_grasp_tcp": {"x": 0.4, "y": 0, "z": 0.02},
    }),
    ("observation_evidence", {
        "top_grasp_offset_status": "CALIBRATED_RGBD_TOP_GRASP_V1",
        "resolved_top_grasp_tcp": {"x": float("nan"), "y": 0, "z": 0.02},
    }),
])
def test_each_attempt_requires_matching_gpu_model_and_calibrated_tcp(field, value) -> None:
    report = _passing_report()
    report["attempts"][1][field] = value
    assert can_freeze(report) is False


def test_changed_source_or_effective_generation_blocks_freeze() -> None:
    report = _passing_report()
    report["source_fingerprints"]["src/cloud_edge_robot_arm/vision/messages.py"] = "0" * 64
    assert can_freeze(report) is False
    report = _passing_report()
    report["attempts"][2]["request_summary"]["options"]["temperature"] = 0.9
    assert can_freeze(report) is False
    report = _passing_report()
    report["attempts"][2]["inherited_parameters"] = "presence_penalty 0"
    assert can_freeze(report) is False


@pytest.mark.parametrize("field,value", [
    ("format_sha256", "0" * 64),
    ("message_text_sha256", ["0" * 64, "1" * 64]),
    ("image_sha256", ["0" * 64, "1" * 64]),
])
def test_legal_but_changed_wire_hash_cannot_freeze(field, value) -> None:
    report = _passing_report()
    report["attempts"][0]["request_summary"][field] = value
    assert can_freeze(report) is False


def test_actual_text_must_reproduce_wire_hashes() -> None:
    report = _passing_report()
    report["attempts"][0]["request_texts"][0]["content"] = "Changed prompt"
    assert can_freeze(report) is False


def test_legacy_unconfigured_grasp_cannot_freeze() -> None:
    report = _passing_report()
    report["snapshot"].pop("grasp_profile", None)
    assert can_freeze(report) is False


@pytest.mark.parametrize("coordinate_system", [None, "pixel", "normalized_1000"])
def test_candidate_reads_legacy_and_explicit_coordinate_protocol(
    tmp_path, coordinate_system,
) -> None:
    payload = _snapshot()
    payload.pop("grasp_profile")
    payload["probe"] = {
        "scenario_id": "S01_NORMAL_STATIC", "seed": 0,
        "instruction": "pick red cube", "warm_runs": 3,
    }
    if coordinate_system is not None:
        payload["coordinate_system"] = coordinate_system
    path = tmp_path / "candidate.yaml"
    path.write_text(json.dumps(payload))
    snapshot, _ = probe._read_candidate(path)
    assert snapshot.get("coordinate_system", "pixel") == (coordinate_system or "pixel")
    assert snapshot.get("grasp_profile", "unconfigured") == "unconfigured"


def test_candidate_rejects_unsupported_scene_instead_of_silently_using_s01(tmp_path) -> None:
    payload = _snapshot()
    payload["probe"] = {
        "scenario_id": "S02_OCCLUDED", "seed": 0,
        "instruction": "pick red cube", "warm_runs": 3,
    }
    path = tmp_path / "candidate.yaml"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="scenario"):
        probe._read_candidate(path)


@pytest.mark.parametrize("coordinate_system", [None, {}, "auto", 1000])
def test_candidate_rejects_unknown_or_inferred_coordinate_protocol(
    tmp_path, coordinate_system,
) -> None:
    payload = {**_snapshot(), "coordinate_system": coordinate_system, "probe": {
        "scenario_id": "S01_NORMAL_STATIC", "seed": 0,
        "instruction": "pick red cube", "warm_runs": 3,
    }}
    path = tmp_path / "candidate.yaml"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="coordinate_system"):
        probe._read_candidate(path)


def test_freeze_preserves_coordinate_protocol_and_binds_source_and_request_evidence(
    tmp_path,
) -> None:
    snapshot = {**_snapshot(), "coordinate_system": "normalized_1000"}
    report = _passing_report()
    report["snapshot"] = snapshot
    target = tmp_path / "model-frozen.json"
    assert write_frozen_if_verified(target, snapshot, report)
    assert json.loads(target.read_text())["coordinate_system"] == "normalized_1000"
    evidence = json.loads((tmp_path / "model-frozen-evidence.json").read_text())
    assert evidence["snapshot_sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert evidence["source_fingerprints"]["src/cloud_edge_robot_arm/vision/messages.py"] == (
        _source_fingerprints()["src/cloud_edge_robot_arm/vision/messages.py"]
    )
    assert evidence["effective_requests"][0]["options"]["temperature"] == 0
    assert evidence["inherited_parameters"] == "presence_penalty 1.5"
    assert evidence["probe_config"]["instruction"] == "pick red cube"
    request_evidence = evidence["request_evidence"][0]
    assert request_evidence["request_texts"][1]["content"] == "pick red cube"
    assert request_evidence["expected_request_summary"] == request_evidence["request_summary"]


@pytest.mark.parametrize("include_original", [False, True])
def test_attempt_scores_original_pixels_under_explicit_coordinate_protocol(
    tmp_path, monkeypatch, include_original,
) -> None:
    from cloud_edge_robot_arm.vision.capture import CapturedFrame
    from cloud_edge_robot_arm.vision.messages import build_visual_messages
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.planner import VisualDecision
    from tests.test_rgbd_observations import observation_payload

    observation = RGBDObservation.model_validate(observation_payload())
    frame = CapturedFrame(
        observation, (0, 11, 12, -1),
        {0: "table", 11: "object_geom", 12: "target_region_geom"}, "state", ("state",) * 3,
    )
    decision = {"target_pixel": [750, 250], "destination_pixel": [250, 750]}
    evidence = {
        "visual_decision": decision, **_passing_report()["attempts"][0]["observation_evidence"],
    }
    if include_original:
        evidence.update(original_pixel_target=[1, 0], original_pixel_destination=[0, 1])
        # Original evidence is authoritative even when the model display coordinate differs.
        decision["target_pixel"] = [0, 0]
    posted = []

    class OfflinePlanner:
        model_snapshot = SimpleNamespace(
            image_size=(2, 2), coordinate_system="normalized_1000",
            generation_parameters=_snapshot()["generation_parameters"],
        )

        def _post(self, path, body):
            posted.append(path)
            if path == "/api/show":
                return {"capabilities": ["vision"], "parameters": "presence_penalty 1.5"}
            return {"message": {"content": "offline validation fixture"}}

        def plan(self, request):
            self._post("/api/show", {"model": "qwen3.5:4b"})
            self._post("/api/chat", {
                "model": "qwen3.5:4b", "stream": False, "think": False,
                "format": VisualDecision.model_json_schema(),
                "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 512},
                "messages": build_visual_messages(
                    request.user_instruction, observation,
                    image_size=(2, 2), coordinate_system="normalized_1000",
                    decision_schema=VisualDecision.model_json_schema(),
                ),
            })
            return SimpleNamespace(
                raw_text="offline validation fixture", parse_error=None,
                observed_scene=object(), parsed_json={"steps": []}, observation_evidence=evidence,
            )

    monkeypatch.setattr(probe, "_gpu_status", lambda: {"used_mib": 0})
    monkeypatch.setattr(probe, "_gpu_compute_processes", list)
    monkeypatch.setattr(probe, "_running_model", lambda *_: {"name": "qwen3.5:4b"})
    record = probe._attempt(
        planner=OfflinePlanner(),
        request=SimpleNamespace(user_instruction="pick", observation=observation),
        frame=frame, index=1,
        output=tmp_path, endpoint="http://127.0.0.1:11434", model_name="qwen3.5:4b",
    )
    assert record["target_hit"] is True
    assert record["destination_hit"] is True
    assert record["observed_scene_present"] is True
    assert record["target_offline_check"]["pixel"] == [1, 0]
    assert record["observation_evidence"]["resolved_top_grasp_tcp"]["z"] == 0.02
    assert record["inherited_parameters"] == "presence_penalty 1.5"
    assert record["expected_request_summary"] == record["request_summary"]
    assert record["request_texts"][1] == {"role": "user", "content": "pick"}
    assert all(set(message) == {"role", "content"} for message in record["request_texts"])
    assert posted == ["/api/show", "/api/chat"]


def test_request_summary_records_distinct_images_without_base64() -> None:
    rgb = "YWJj"
    depth = "ZGVm"
    body = {
        "model": "qwen3.5:4b",
        "stream": False,
        "messages": [
            {"role": "system", "content": "Look at both images"},
            {"role": "user", "content": "pick the red cube", "images": [rgb, depth]},
        ],
    }
    summary = summarize_chat_request(body)
    assert summary["model"] == "qwen3.5:4b"
    assert summary["stream"] is False
    assert summary["image_count"] == 2
    assert summary["distinct_image_count"] == 2
    assert summary["image_sha256"] == [
        hashlib.sha256(b"abc").hexdigest(),
        hashlib.sha256(b"def").hexdigest(),
    ]
    serialized = json.dumps(summary)
    assert rgb not in serialized
    assert depth not in serialized
    assert "pick the red cube" not in serialized


def test_freeze_requires_real_transport_geometry_and_cuda(tmp_path) -> None:
    snapshot = _snapshot()
    target = tmp_path / "model-frozen.json"
    report = _passing_report()
    for path, value in [
        (("source",), "mock_camera"),
        (("capture", "synchronized"), False),
        (("model", "digest_matches"), False),
        (("model", "quantization_matches"), False),
        (("model", "vision"), False),
        (("device", "cuda"), False),
        (("attempts", 0, "transport_two_images"), False),
        (("attempts", 0, "parsed"), False),
        (("attempts", 0, "grounded"), False),
        (("attempts", 0, "target_hit"), False),
        (("attempts", 0, "destination_hit"), False),
        (("timing", "warm_samples"), 0),
    ]:
        broken = copy.deepcopy(report)
        nested = broken
        for key in path[:-1]:
            nested = nested[key]
        nested[path[-1]] = value
        assert can_freeze(broken) is False
        assert write_frozen_if_verified(target, snapshot, broken) is False
        assert not target.exists()
    assert can_freeze(report) is True
    assert write_frozen_if_verified(target, snapshot, report) is True
    assert json.loads(target.read_text(encoding="utf-8")) == snapshot


def test_prior_owned_freeze_is_archived_before_next_probe(tmp_path) -> None:
    target = tmp_path / "model-frozen.json"
    target.write_text('{"model":"qwen3.5:4b"}\n', encoding="utf-8")
    report_path = tmp_path / "probe-report.json"
    report_path.write_text(json.dumps({
        "status": "PASS",
        "frozen_path": str(target),
        "frozen_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    archived = archive_previous_owned_freeze(tmp_path)
    assert archived is not None
    assert not target.exists()
    assert not report_path.exists()
    assert (archived / "model-frozen.json").read_text() == '{"model":"qwen3.5:4b"}\n'
    assert (archived / "probe-report.json").exists()


@pytest.mark.parametrize("tampered", [False, True])
def test_prior_freeze_evidence_is_authenticated_and_archived_together(tmp_path, tampered) -> None:
    target = tmp_path / "model-frozen.json"
    report = _passing_report()
    assert write_frozen_if_verified(target, _snapshot(), report)
    evidence = tmp_path / "model-frozen-evidence.json"
    report.update(
        status="PASS", frozen_path=str(target),
        frozen_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        frozen_evidence_path=str(evidence),
        frozen_evidence_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest(),
    )
    (tmp_path / "probe-report.json").write_text(json.dumps(report))
    if tampered:
        evidence.write_text("unknown replacement")
        with pytest.raises(RuntimeError, match="ownership"):
            archive_previous_owned_freeze(tmp_path)
        assert target.exists()
        assert evidence.read_text() == "unknown replacement"
    else:
        archived = archive_previous_owned_freeze(tmp_path)
        assert archived is not None
        assert (archived / "model-frozen-evidence.json").exists()
        assert not evidence.exists()


def test_unknown_evidence_sidecar_blocks_publication_without_overwrite(tmp_path) -> None:
    target = tmp_path / "model-frozen.json"
    evidence = tmp_path / "model-frozen-evidence.json"
    evidence.write_text("user-owned evidence")
    with pytest.raises(FileExistsError):
        write_frozen_if_verified(target, _snapshot(), _passing_report())
    assert not target.exists()
    assert evidence.read_text() == "user-owned evidence"


def test_writer_rejects_a_different_snapshot_from_the_verified_run(tmp_path) -> None:
    snapshot = {**_snapshot(), "coordinate_system": "normalized_1000"}
    with pytest.raises(ValueError, match="differs"):
        write_frozen_if_verified(tmp_path / "model-frozen.json", snapshot, _passing_report())


@pytest.mark.parametrize("tamper", ["snapshot", "sidecar", "report", "source"])
def test_frozen_bundle_verifies_current_sources_and_all_artifact_hashes(
    tmp_path, monkeypatch, tamper,
) -> None:
    report = _passing_report()
    target = tmp_path / "model-frozen.json"
    sidecar = tmp_path / "model-frozen-evidence.json"
    assert write_frozen_if_verified(target, _snapshot(), report)
    report.update(
        status="PASS", frozen_path=str(target),
        frozen_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        frozen_evidence_path=str(sidecar),
        frozen_evidence_sha256=hashlib.sha256(sidecar.read_bytes()).hexdigest(),
    )
    report_path = tmp_path / "probe-report.json"
    report_path.write_text(json.dumps(report))
    (tmp_path / "probe-report.sha256").write_text(
        hashlib.sha256(report_path.read_bytes()).hexdigest() + "\n"
    )
    assert probe.verify_frozen_bundle(tmp_path) is True
    if tamper == "source":
        changed = _source_fingerprints()
        changed["src/cloud_edge_robot_arm/vision/messages.py"] = "0" * 64
        monkeypatch.setattr(probe, "_source_fingerprints", lambda: changed)
    else:
        altered = {"snapshot": target, "sidecar": sidecar, "report": report_path}[tamper]
        altered.write_text(altered.read_text() + " ")
    assert probe.verify_frozen_bundle(tmp_path) is False


def test_probe_freeze_write_failure_cannot_publish_pass(tmp_path, monkeypatch) -> None:
    import base64
    import io
    import struct

    from PIL import Image

    from cloud_edge_robot_arm.vision import capture, model_resolver
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from tests.test_rgbd_observations import observation_payload

    payload = observation_payload()
    png = io.BytesIO()
    Image.new("RGB", (320, 240), (255, 0, 0)).save(png, format="PNG")
    payload.update(
        width=320, height=240, rgb_png_base64=base64.b64encode(png.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(struct.pack("<f", 2) * (320 * 240)).decode(),
    )
    observation = RGBDObservation.model_validate(payload)

    class OfflineCapture:
        def __init__(self, config):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def capture_with_instances(self):
            return SimpleNamespace(
                observation=observation, physics_state_hash="state",
                pass_state_hashes=("state",) * 3,
            )

    passing = _passing_report()["attempts"][0]
    passing.update(wall_latency_ms=1.0, response={}, gpu_peak_used_mib=1, phase="warm")
    monkeypatch.setattr(capture, "MuJoCoCaptureSession", OfflineCapture)
    monkeypatch.setattr(model_resolver, "resolve_visual_planner", lambda _: object())
    monkeypatch.setattr(probe, "_attempt", lambda **_: copy.deepcopy(passing))
    monkeypatch.setattr(probe, "_model_entry", lambda *_: {
        "digest": "a" * 64, "details": {"quantization_level": "Q4_K_M"},
    })
    monkeypatch.setattr(probe, "_local_json", lambda *_: {
        "capabilities": ["vision"], "parameters": "presence_penalty 1.5", "version": "fixture",
    })
    monkeypatch.setattr(probe, "_gpu_status", lambda: {"used_mib": 1})
    monkeypatch.setattr(probe, "_gpu_compute_processes", list)
    monkeypatch.setattr(probe, "_running_model", lambda *_: passing["loaded_model_after_call"])
    monkeypatch.setattr(probe, "_unload_model", lambda *_: {"unloaded": True})

    def fail_publication(*_):
        raise OSError("freeze publication fixture failure")

    monkeypatch.setattr(probe, "write_frozen_if_verified", fail_publication)
    config = tmp_path / "candidate.yaml"
    config.write_text(json.dumps({**_snapshot(), "probe": {
        "scenario_id": "S01_NORMAL_STATIC", "seed": 0,
        "instruction": "pick red cube", "warm_runs": 3,
    }}))
    output = tmp_path / "probe"
    report = probe.run_probe(config, output)
    assert report["status"] == "BLOCKED"
    assert "freeze publication fixture failure" in report["blocked_reason"]
    assert json.loads((output / "probe-report.json").read_text())["status"] == "BLOCKED"
    assert not (output / "model-frozen.json").exists()


def test_unknown_frozen_file_is_preserved(tmp_path) -> None:
    target = tmp_path / "model-frozen.json"
    target.write_text("user-owned file\n", encoding="utf-8")
    report_path = tmp_path / "probe-report.json"
    report_path.write_text('{"status":"BLOCKED"}\n', encoding="utf-8")
    try:
        archive_previous_owned_freeze(tmp_path)
    except RuntimeError as exc:
        assert "cannot establish" in str(exc)
    else:
        raise AssertionError("unowned freeze must block the probe")
    assert target.read_text(encoding="utf-8") == "user-owned file\n"
    assert report_path.read_text(encoding="utf-8") == '{"status":"BLOCKED"}\n'


def test_verified_writer_never_overwrites_unknown_existing_file(tmp_path) -> None:
    target = tmp_path / "model-frozen.json"
    target.write_text("user-owned file\n", encoding="utf-8")
    snapshot = _snapshot()
    try:
        write_frozen_if_verified(target, snapshot, _passing_report())
    except FileExistsError:
        pass
    else:
        raise AssertionError("verified writer must not replace an unknown file")
    assert target.read_text(encoding="utf-8") == "user-owned file\n"


def test_verified_writer_recovers_after_interrupted_staging(tmp_path) -> None:
    target = tmp_path / "model-frozen.json"
    stale = tmp_path / "model-frozen.json.tmp"
    stale.write_text("interrupted prior write\n", encoding="utf-8")
    snapshot = _snapshot()

    assert write_frozen_if_verified(target, snapshot, _passing_report()) is True
    assert json.loads(target.read_text(encoding="utf-8")) == snapshot
    assert stale.read_text(encoding="utf-8") == "interrupted prior write\n"
