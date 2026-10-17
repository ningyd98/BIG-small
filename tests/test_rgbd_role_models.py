"""Software contracts only; these tests supply no real cloud acceptance evidence."""

from __future__ import annotations

import base64
import hashlib
import importlib
import importlib.util
import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest


def roles():
    assert importlib.util.find_spec("cloud_edge_robot_arm.vision.role_models") is not None, (
        "T3b role bindings are missing"
    )
    return importlib.import_module("cloud_edge_robot_arm.vision.role_models")


def cloud(**overrides):
    values = dict(
        role="CLOUD",
        provider_id="max-profile",
        provider_location="REMOTE_SERVICE",
        model_id="qwen3.8-max",
        revision=None,
        weight_digest=None,
        quantization=None,
        request_config_hash="a" * 64,
        source_hashes={"vision/messages.py": "b" * 64},
    )
    return roles().RoleProviderSnapshot(**(values | overrides))


def test_cloud_alias_does_not_invent_weight_digest():
    snapshot = cloud()
    assert snapshot.evidence()["weight_digest"] is None
    assert snapshot.evidence()["revision"] is None
    assert snapshot.evidence()["quantization"] is None
    assert snapshot.evidence()["model_id"] == "qwen3.8-max"


def test_cloud_and_edge_versions_cannot_be_swapped():
    module = roles()
    edge = replace(
        cloud(), role="EDGE", model_id=None, provider_id="rules-v1", provider_location="LOCAL_HOST"
    )
    with pytest.raises(ValueError, match="CLOUD"):
        module.RoleModelBundle(edge, "rules-v1", "c" * 64, "d" * 64)
    bundle = module.RoleModelBundle(cloud(), "rules-v1", "c" * 64, "d" * 64)
    bundle.validate_bindings(
        cloud_snapshot_hash=cloud().digest(),
        edge_provider_hash="c" * 64,
        device_pipeline_hash="d" * 64,
    )
    with pytest.raises(ValueError, match="binding"):
        bundle.validate_bindings(
            cloud_snapshot_hash="c" * 64,
            edge_provider_hash=cloud().digest(),
            device_pipeline_hash="d" * 64,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"request_config_hash": ""},
        {"source_hashes": {}},
        {"source_hashes": {"vision/messages.py": "not-a-digest"}},
        {"role": "PLANNER"},
        {"provider_location": "DEVICE"},
        {"provider_id": ""},
        {"model_id": None},
        {"weight_digest": "UNKNOWN"},
        {"revision": ""},
    ],
)
def test_role_snapshot_rejects_unbound_or_invalid_identity(overrides):
    with pytest.raises(ValueError):
        cloud(**overrides)


def test_source_and_request_hashes_affect_role_binding():
    original = cloud()
    changed_source = replace(original, source_hashes={"vision/messages.py": "e" * 64})
    changed_request = replace(original, request_config_hash="f" * 64)
    module = roles()
    digests = {
        module.RoleModelBundle(item, "rules-v1", "c" * 64, "d" * 64).digest()
        for item in (original, changed_source, changed_request)
    }
    assert len(digests) == 3


def test_source_mapping_cannot_mutate_frozen_identity():
    sources = {"vision/messages.py": "b" * 64}
    snapshot = cloud(source_hashes=sources)
    before = snapshot.digest()
    sources["vision/messages.py"] = "c" * 64
    assert snapshot.digest() == before
    with pytest.raises(TypeError):
        snapshot.source_hashes["vision/messages.py"] = "d" * 64


def test_edge_rules_provider_requires_no_model():
    snapshot = cloud(
        role="EDGE", provider_id="rules-v1", provider_location="LOCAL_HOST", model_id=None
    )
    assert snapshot.evidence()["model_id"] is None


def test_profile_resolution_preserves_nulls_and_existing_secret_boundary(tmp_path):
    from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
    from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository

    module = roles()
    service = ModelControlService(
        repository=SQLiteModelProfileRepository(tmp_path / "models.db"),
        secret_store=InMemorySecretStore(),
    )
    profile = service.create_profile(
        display_name="max",
        provider_kind=PlannerProviderKind.OPENAI_COMPATIBLE,
        model_name="qwen3.8-max",
        base_url="https://dashscope.aliyuncs.com",
        api_key="test-only-secret",
        max_tokens=777,
    )
    adapter, snapshot = module.resolve_cloud_role(
        service,
        profile.profile_id,
        source_hashes={"messages.py": "b" * 64},
        allow_paid=True,
        grasp_profile="mujoco_upright_box_v2",
    )
    assert adapter.model_name == "qwen3.8-max"
    assert adapter.model_snapshot.weight_digest is None
    assert adapter.model_snapshot.quantization is None
    assert adapter.model_snapshot.generation_parameters["num_predict"] == 777
    assert adapter.model_snapshot.image_size == (320, 240)
    assert snapshot.evidence()["weight_digest"] is None
    assert "test-only-secret" not in json.dumps(snapshot.evidence())
    assert service.repository.get_active_profile_id() == ""


def test_cloud_plan_uses_real_two_image_transport(monkeypatch, tmp_path):
    # Only the external HTTP operation is replaced. Production message construction,
    # compatible serialization, _post and strict parsing execute. No model was queried.
    import io
    import urllib.request

    from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
    from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
    from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from tests.test_rgbd_observations import observation_payload

    module = roles()
    service = ModelControlService(
        repository=SQLiteModelProfileRepository(tmp_path / "models.db"),
        secret_store=InMemorySecretStore(),
    )
    profile = service.create_profile(
        display_name="max",
        provider_kind=PlannerProviderKind.OPENAI_COMPATIBLE,
        model_name="qwen3.8-max",
        base_url="https://dashscope.aliyuncs.com",
    )
    adapter, snapshot = module.resolve_cloud_role(
        service, profile.profile_id, source_hashes={"messages.py": "b" * 64}, allow_paid=True
    )
    payloads = []

    class ExternalBoundary:
        def open(self, request, timeout):
            payloads.append(json.loads(request.data))
            return io.BytesIO(
                json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "target_pixel": None,
                                            "destination_pixel": None,
                                            "target_label": "missing",
                                            "reported_confidence": 0,
                                            "skills": [],
                                            "reason": "target absent",
                                        }
                                    )
                                }
                            }
                        ]
                    }
                ).encode()
            )

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: ExternalBoundary())
    observation = RGBDObservation.model_validate(observation_payload())
    draft = adapter.plan(
        InitialPlanningRequest(
            request_id="software-transport-contract",
            user_instruction="pick missing target",
            scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
            observation=observation,
        )
    )
    body = payloads[0]
    image_parts = [
        part
        for message in body["messages"]
        if isinstance(message["content"], list)
        for part in message["content"]
        if part["type"] == "image_url"
    ]
    blobs = [
        base64.b64decode(part["image_url"]["url"].split(",", 1)[1], validate=True)
        for part in image_parts
    ]
    assert len(blobs) == 2
    assert all(blob.startswith(b"\x89PNG") for blob in blobs)
    assert hashlib.sha256(blobs[0]).digest() != hashlib.sha256(blobs[1]).digest()
    assert body["model"] == snapshot.model_id
    assert draft.parse_error is None
    assert draft.parsed_json == {
        "_sentinel": "REQUEST_MORE_OBSERVATION",
        "_reason": "target absent",
    }


def test_probe_summary_reads_actual_compatible_image_bytes():
    assert importlib.util.find_spec("scripts.probe_rgbd_roles") is not None, "role probe missing"
    probe = importlib.import_module("scripts.probe_rgbd_roles")
    body = {
        "model": "qwen3.8-max",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "pick"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,YWJj"}},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,ZGVm"}},
                ],
            }
        ],
    }
    summary = probe.summarize_role_request(body)
    assert summary["image_count"] == 2
    assert summary["image_bytes"] == [3, 3]
    assert summary["image_sha256"] == [
        hashlib.sha256(b"abc").hexdigest(),
        hashlib.sha256(b"def").hexdigest(),
    ]
    assert summary["serialized_sent_bytes"] == len(json.dumps(body).encode())
    assert "YWJj" not in json.dumps(summary)


def test_probe_cannot_accept_software_or_missing_real_evidence():
    assert importlib.util.find_spec("scripts.probe_rgbd_roles") is not None, "role probe missing"
    probe = importlib.import_module("scripts.probe_rgbd_roles")
    assert (
        probe.can_accept_role_probe({"status": "PASS", "source": "software_test", "attempts": []})
        is False
    )
    assert (
        probe.can_accept_role_probe(
            {
                "source": "mujoco_camera",
                "transport": "REAL_HTTP",
                "capture": {"synchronized": True},
                "attempts": [],
            }
        )
        is False
    )


def test_date_snapshot_selection_uses_only_advertised_family_versions():
    module = roles()
    assert (
        module.select_cloud_model_id(
            "qwen3.8-max",
            ["qwen3.8-max-2026-09-01", "qwen3.8-max-2026-09-15", "qwen3.5-max-2026-10-01"],
        )
        == "qwen3.8-max-2026-09-15"
    )
    assert module.select_cloud_model_id("qwen3.8-max", []) == "qwen3.8-max"
    assert module.select_cloud_model_id("qwen3.8-max-2026-09-01", []) == "qwen3.8-max-2026-09-01"


def test_api_model_snapshot_preserves_unavailable_weight_identity():
    from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot

    snapshot = ModelConfigSnapshot(
        provider="openai_compatible",
        model="qwen3.8-max",
        endpoint="https://dashscope.aliyuncs.com",
        weight_digest=None,
        quantization=None,
        image_size=(320, 240),
        generation_parameters={"temperature": 0},
        timeout_s=30,
    )
    assert snapshot.evidence()["weight_digest"] is None
    assert snapshot.evidence()["quantization"] is None
    assert snapshot.digest() != replace(snapshot, weight_digest="a" * 64).digest()


@pytest.mark.parametrize("field", ["weight_digest", "quantization"])
def test_local_snapshot_does_not_accept_null_weight_identity(field):
    from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot

    values = dict(
        provider="ollama",
        model="qwen3.5:4b",
        endpoint="http://127.0.0.1:11434",
        weight_digest="a" * 64,
        quantization="Q4_K_M",
        image_size=(320, 240),
        generation_parameters={"temperature": 0},
        timeout_s=30,
    )
    values[field] = None
    with pytest.raises(ValueError):
        ModelConfigSnapshot(**values)


def test_probe_dry_run_never_touches_supplied_service(tmp_path):
    from pathlib import Path

    from scripts.probe_rgbd_roles import run_probe

    class ForbiddenService:
        def get_profile(self, profile_id):
            raise AssertionError("dry run contacted a profile service")

    report = run_probe(
        Path("configs/research/ced_roles.yaml"), tmp_path / "dry", service=ForbiddenService()
    )
    assert report["status"] == "NOT_STARTED"
    assert report["attempts"] == []
    assert not (tmp_path / "dry" / "roles-frozen.json").exists()


def test_missing_profile_secret_blocks_before_transport_or_renderer(tmp_path):
    from pathlib import Path

    from scripts.probe_rgbd_roles import run_probe

    from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
    from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository

    service = ModelControlService(
        repository=SQLiteModelProfileRepository(tmp_path / "models.db"),
        secret_store=InMemorySecretStore(),
    )
    profile = service.create_profile(
        display_name="max",
        provider_kind=PlannerProviderKind.OPENAI_COMPATIBLE,
        model_name="qwen3.8-max",
        base_url="https://dashscope.aliyuncs.com",
    )
    report = run_probe(
        Path("configs/research/ced_roles.yaml"),
        tmp_path / "missing-secret",
        service=service,
        profile_id=profile.profile_id,
        execute=True,
        allow_paid=True,
    )
    assert report["status"] == "BLOCKED"
    assert report["transport"] is None
    assert report["attempts"] == []


def test_role_probe_keeps_actual_response_bytes_and_refusal_without_freeze(tmp_path, monkeypatch):
    import io
    import urllib.request

    from scripts.probe_rgbd_roles import _attempt

    from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
    from cloud_edge_robot_arm.vision.capture import CapturedFrame
    from cloud_edge_robot_arm.vision.model_resolver import (
        ModelConfigSnapshot,
        resolve_visual_planner,
    )
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from tests.test_rgbd_observations import observation_payload

    raw = b'  {"choices": []}  \n'

    class ExternalBoundary:
        def open(self, request, timeout):
            return io.BytesIO(raw)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: ExternalBoundary())
    model = ModelConfigSnapshot(
        provider="openai_compatible",
        model="qwen3.8-max",
        endpoint="https://dashscope.aliyuncs.com",
        weight_digest=None,
        quantization=None,
        image_size=(320, 240),
        generation_parameters={"temperature": 0, "num_predict": 512},
        timeout_s=30,
    )
    planner = resolve_visual_planner(model, api_key="credential-marker", allow_paid=True)
    observation = RGBDObservation.model_validate(observation_payload())
    frame = CapturedFrame(
        observation,
        (0, 11, 12, -1),
        {0: "table", 11: "object_geom", 12: "target_region_geom"},
        "fixture",
        ("fixture",) * 3,
    )
    request = InitialPlanningRequest(
        request_id="software-byte-contract",
        user_instruction="pick red cube",
        scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
        observation=observation,
    )
    attempt = _attempt(planner, request, frame, tmp_path, 0, cloud())
    assert attempt["serialized_received_bytes"] == 20
    assert len(raw) == 20
    assert attempt["parsed"] is False
    assert attempt["grounded"] is False
    assert attempt["target_hit"] is False
    assert planner.cost_ledger is None
    assert not (tmp_path / "roles-frozen.json").exists()
    assert "credential-marker" not in (tmp_path / "attempt-00" / "request.json").read_text()


def test_cli_missing_profile_database_writes_machine_readable_blocked(tmp_path):
    import subprocess
    import sys

    output = tmp_path / "missing-profile"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.probe_rgbd_roles",
            "--execute",
            "--model-control-db",
            str(tmp_path / "absent.db"),
            "--profile-id",
            "absent-profile",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout.startswith("{")
    assert json.loads(result.stdout)["status"] == "BLOCKED"
    report = json.loads((output / "role-probe-report.json").read_text())
    assert report["attempts"] == []
    assert report["transport"] is None


def _nominal_gate_fixture_for_rejection_only():
    """In-memory predicate fixture; never saved, executed, or used as real acceptance."""
    from scripts import probe_rgbd_roles as probe

    from cloud_edge_robot_arm.vision.model_resolver import (
        ModelConfigSnapshot,
        resolve_visual_planner,
    )

    model = ModelConfigSnapshot(
        provider="openai_compatible",
        model="qwen3.8-max",
        endpoint="https://dashscope.aliyuncs.com",
        weight_digest=None,
        quantization=None,
        image_size=(320, 240),
        generation_parameters={"temperature": 0, "num_predict": 512},
        timeout_s=30,
    )
    planner = resolve_visual_planner(model, allow_paid=True)
    settings = model.evidence() | {
        "chat_path": planner.chat_path,
        "config_version": 1,
        "response_format": {"type": "json_object"},
        "allow_paid": True,
    }
    cloud_snapshot = cloud(
        request_config_hash=roles().configuration_hash(settings),
        source_hashes=probe.source_fingerprints(),
    )
    edge_sources = probe._hash_sources(["src/cloud_edge_robot_arm/vision/role_models.py"])
    device_sources = probe._hash_sources(["src/cloud_edge_robot_arm/vision/tracking.py"])
    edge_policy = {"dispatch": False}
    edge = cloud(
        role="EDGE",
        provider_id="rules-v1",
        provider_location="LOCAL_HOST",
        model_id=None,
        request_config_hash=roles().configuration_hash(edge_policy),
        source_hashes=edge_sources,
    )
    bundle = roles().RoleModelBundle(
        cloud_snapshot, edge.provider_id, edge.digest(), roles().configuration_hash(device_sources)
    )
    summary = {
        "model": cloud_snapshot.model_id,
        "image_count": 2,
        "distinct_image_count": 2,
        "serialized_sent_bytes": 100,
    }
    attempt = {
        "transport_two_images": True,
        "parsed": True,
        "grounded": True,
        "target_hit": True,
        "destination_hit": True,
        "request_summary": summary,
        "expected_request_summary": summary.copy(),
        "serialized_received_bytes": 50,
        "actual_request_settings": settings.copy(),
        "observation_evidence": {
            "top_grasp_offset_status": "CALIBRATED_RGBD_TOP_GRASP_V1",
            "cloud_snapshot_hash": cloud_snapshot.digest(),
        },
    }
    config_path = probe.ROOT / "configs/research/ced_roles.yaml"
    return {
        "config_path": str(config_path),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "source": "mujoco_camera",
        "transport": "REAL_HTTP",
        "capture": {"synchronized": True, "image_size": [320, 240]},
        "bundle": bundle.evidence(),
        "bundle_hash": bundle.digest(),
        "edge_snapshot": edge.evidence(),
        "edge_policy": edge_policy,
        "device_source_hashes": device_sources,
        "request_settings": settings,
        "final_request_settings": settings.copy(),
        "probe_config": {"warm_runs": 3},
        "attempts": [dict(attempt) for _ in range(4)],
    }


@pytest.mark.parametrize(
    "drift",
    [
        "config_source",
        "device_source",
        "edge_source",
        "bundle_hash",
        "edge_hash",
        "device_hash",
        "endpoint",
        "chat_path",
        "timeout",
        "allow_paid",
    ],
)
def test_nominal_freeze_rejects_full_role_and_actual_transport_drift(drift):
    from scripts import probe_rgbd_roles as probe

    report = _nominal_gate_fixture_for_rejection_only()
    if drift == "config_source":
        report["config_sha256"] = "0" * 64
    elif drift == "device_source":
        report["device_source_hashes"]["src/cloud_edge_robot_arm/vision/tracking.py"] = "0" * 64
    elif drift == "edge_source":
        report["edge_snapshot"]["source_hashes"][
            "src/cloud_edge_robot_arm/vision/role_models.py"
        ] = "0" * 64
    elif drift == "bundle_hash":
        report["bundle_hash"] = "0" * 64
    elif drift == "edge_hash":
        report["bundle"]["edge_provider_hash"] = "0" * 64
    elif drift == "device_hash":
        report["bundle"]["device_pipeline_hash"] = "0" * 64
    else:
        key = {
            "endpoint": "endpoint_hash",
            "chat_path": "chat_path",
            "timeout": "timeout_s",
            "allow_paid": "allow_paid",
        }[drift]
        value = {
            "endpoint": "0" * 64,
            "chat_path": "/chat/completions",
            "timeout": 10,
            "allow_paid": False,
        }[drift]
        report["attempts"][0]["actual_request_settings"] = report["request_settings"] | {key: value}
    assert probe.validate_role_probe_bindings(report) is False
    assert probe.can_accept_role_probe(report) is False


@pytest.mark.parametrize(
    "response_kind", ["whitespace_json", "benign_escaped_json", "non_json", "http_error"]
)
def test_probe_preserves_exact_wire_response_and_error_body(tmp_path, monkeypatch, response_kind):
    import io
    import urllib.error
    import urllib.request

    from scripts.probe_rgbd_roles import _attempt

    from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
    from cloud_edge_robot_arm.vision.capture import CapturedFrame
    from cloud_edge_robot_arm.vision.model_resolver import (
        ModelConfigSnapshot,
        resolve_visual_planner,
    )
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from tests.test_rgbd_observations import observation_payload

    raw = {
        "whitespace_json": b'  {"choices": []}  \n',
        "benign_escaped_json": b'{"choices":[],"info":"\\u006eot-secret"}',
        "non_json": b"not-json\x00\r\n",
        "http_error": b"error response\r\n",
    }[response_kind]
    sent = []

    class ExternalBoundary:
        def open(self, request, timeout):
            sent.append(request.data)
            if response_kind == "http_error":
                raise urllib.error.HTTPError(
                    request.full_url, 503, "unavailable", {}, io.BytesIO(raw)
                )
            return io.BytesIO(raw)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: ExternalBoundary())
    model = ModelConfigSnapshot(
        provider="openai_compatible",
        model="qwen3.8-max",
        endpoint="https://dashscope.aliyuncs.com",
        weight_digest=None,
        quantization=None,
        image_size=(320, 240),
        generation_parameters={"temperature": 0, "num_predict": 512},
        timeout_s=30,
    )
    planner = resolve_visual_planner(model, api_key="credential-marker", allow_paid=True)
    observation = RGBDObservation.model_validate(observation_payload())
    frame = CapturedFrame(
        observation,
        (0, 11, 12, -1),
        {0: "table", 11: "object_geom", 12: "target_region_geom"},
        "fixture",
        ("fixture",) * 3,
    )
    request = InitialPlanningRequest(
        request_id="software-raw-contract",
        user_instruction="pick red cube",
        scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
        observation=observation,
    )
    attempt = _attempt(planner, request, frame, tmp_path, 0, cloud())
    directory = tmp_path / "attempt-00"
    assert (directory / "response.raw").is_file(), "exact response bytes were not archived"
    assert (directory / "response.raw").read_bytes() == raw
    assert (directory / "request.raw").read_bytes() == sent[0]
    assert attempt["response_sha256"] == hashlib.sha256(raw).hexdigest()
    assert attempt["request_sha256"] == hashlib.sha256(sent[0]).hexdigest()
    assert attempt["serialized_received_bytes"] == len(raw)
    assert all(
        b"credential-marker" not in path.read_bytes()
        for path in directory.iterdir()
        if path.is_file()
    )


def test_unchanged_role_bindings_validate_without_claiming_nominal_acceptance():
    from scripts import probe_rgbd_roles as probe

    report = _nominal_gate_fixture_for_rejection_only()
    assert probe.validate_role_probe_bindings(report) is True
    # No real/raw transport evidence exists for this in-memory predicate fixture.
    assert probe.can_accept_role_probe(report) is False


@pytest.mark.parametrize("source_kind", ["edge", "device"])
def test_current_edge_and_device_source_drift_rejects_original_report(monkeypatch, source_kind):
    from scripts import probe_rgbd_roles as probe

    report = _nominal_gate_fixture_for_rejection_only()
    key = (
        "src/cloud_edge_robot_arm/vision/role_models.py"
        if source_kind == "edge"
        else "src/cloud_edge_robot_arm/vision/tracking.py"
    )
    original = probe._hash_sources

    def changed_current_source(paths):
        result = original(paths)
        if paths == [key]:
            result[key] = "0" * 64
        return result

    monkeypatch.setattr(probe, "_hash_sources", changed_current_source)
    assert probe.validate_role_probe_bindings(report) is False


@pytest.mark.parametrize("phase", ["REQUEST", "RESPONSE"])
def test_raw_observer_failure_preserves_actual_call_count_and_exact_costs(monkeypatch, phase):
    import io
    import urllib.request

    from cloud_edge_robot_arm.research.cost_ledger import CostLedger
    from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable, RGBDPlannerAdapter

    raw = b'  {"choices": []}\n'
    sent = []

    class ExternalBoundary:
        def open(self, request, timeout):
            sent.append(request.data)
            return io.BytesIO(raw)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: ExternalBoundary())
    observed = []

    def failing_observer(actual_phase, path, body):
        observed.append((actual_phase, path, body))
        if actual_phase == phase:
            raise RuntimeError("private observer failure")

    ledger = CostLedger()
    adapter = RGBDPlannerAdapter(
        base_url="https://dashscope.aliyuncs.com",
        model="qwen3.8-max",
        provider="openai_compatible",
        api_key="credential-marker",
        allow_paid=True,
        cost_ledger=ledger,
        raw_transport_observer=failing_observer,
    )
    with pytest.raises(RGBDModelUnavailable, match="observer"):
        adapter._post("/chat/completions", {"model": "qwen3.8-max"})
    rows = ledger.requests()
    assert len(rows) == (1 if phase == "RESPONSE" else 0)
    if rows:
        assert rows[0].status == "ERROR"
        assert rows[0].serialized_received_bytes == len(raw)
    assert len(sent) == (1 if phase == "RESPONSE" else 0)
    assert all(b"credential-marker" not in item[2] for item in observed)


def test_raw_observer_is_bounded_and_oversized_error_keeps_byte_count(monkeypatch):
    import io
    import urllib.error
    import urllib.request

    from cloud_edge_robot_arm.research.cost_ledger import CostLedger
    from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable, RGBDPlannerAdapter

    captured = []

    class ExternalBoundary:
        def open(self, request, timeout):
            raise urllib.error.HTTPError(
                request.full_url, 503, "error", {}, io.BytesIO(b"x" * 2_000_010)
            )

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: ExternalBoundary())
    ledger = CostLedger()
    adapter = RGBDPlannerAdapter(
        base_url="https://dashscope.aliyuncs.com",
        model="qwen3.8-max",
        provider="openai_compatible",
        allow_paid=True,
        cost_ledger=ledger,
        raw_transport_observer=lambda phase, path, body: captured.append((phase, len(body))),
    )
    with pytest.raises(RGBDModelUnavailable):
        adapter._post("/chat/completions", {"model": "qwen3.8-max"})
    assert captured[-1] == ("RESPONSE", 2_000_001)
    assert ledger.requests()[0].serialized_received_bytes == 2_000_001


def test_credential_echo_is_withheld_and_cannot_create_freeze(tmp_path, monkeypatch):
    import io
    import urllib.request

    from scripts.probe_rgbd_roles import _attempt

    from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
    from cloud_edge_robot_arm.vision.capture import CapturedFrame
    from cloud_edge_robot_arm.vision.model_resolver import (
        ModelConfigSnapshot,
        resolve_visual_planner,
    )
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from tests.test_rgbd_observations import observation_payload

    raw = b'{"error":"credential-marker"}'

    class ExternalBoundary:
        def open(self, request, timeout):
            return io.BytesIO(raw)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: ExternalBoundary())
    model = ModelConfigSnapshot(
        provider="openai_compatible",
        model="qwen3.8-max",
        endpoint="https://dashscope.aliyuncs.com",
        weight_digest=None,
        quantization=None,
        image_size=(320, 240),
        generation_parameters={"temperature": 0, "num_predict": 512},
        timeout_s=30,
    )
    planner = resolve_visual_planner(model, api_key="credential-marker", allow_paid=True)
    observation = RGBDObservation.model_validate(observation_payload())
    frame = CapturedFrame(
        observation,
        (0, 11, 12, -1),
        {0: "table", 11: "object_geom", 12: "target_region_geom"},
        "fixture",
        ("fixture",) * 3,
    )
    request = InitialPlanningRequest(
        request_id="software-secret-boundary",
        user_instruction="pick red cube",
        scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
        observation=observation,
    )
    attempt = _attempt(planner, request, frame, tmp_path, 0, cloud())
    assert attempt.get("wire_artifact_suppressed") is True
    assert attempt["status"] == "BLOCKED"
    assert attempt["serialized_received_bytes"] == 29
    assert not (tmp_path / "attempt-00" / "response.raw").exists()
    assert not (tmp_path / "attempt-00" / "response.json").exists()
    assert all(
        b"credential-marker" not in path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    )


@pytest.mark.parametrize(
    "raw,secret,http_error",
    [
        (b'{"error":"\\u0063redential-marker"}', "credential-marker", False),
        (
            b'{"outer":[{"inner":"prefix \\u0063redential-marker suffix"}]}',
            "credential-marker",
            False,
        ),
        (b'{"\\u0063redential-marker":{"ordinary":"value"}}', "credential-marker", False),
        (b'{"error":"slash\\/credential"}', "slash/credential", False),
        (b'{"error":"quote\\u0022credential"}', 'quote"credential', False),
        (b'{"error":"backslash\\u005ccredential"}', "backslash\\credential", False),
        (b'{"error":"\\ud83d\\ude80-token"}', "🚀-token", False),
        (b"not JSON: \\u0063redential-marker\x00\r\n", "credential-marker", False),
        (b"not JSON: slash\\/credential\r\n", "slash/credential", False),
        (b'{"error":"\\u0063redential-marker"}', "credential-marker", True),
        (b'{"outer":[{"\\u0063redential-marker":"bad"}]}', "credential-marker", True),
        (b"HTTP error: \\u0063redential-marker\r\n", "credential-marker", True),
        (b'{"error":"\\\\u0063redential-marker"}', "credential-marker", False),
        ("HTTP error: \\u0063redential-marker".encode("utf-16"), "credential-marker", True),
    ],
)
def test_alternate_escaped_credential_echo_withholds_all_artifacts(
    tmp_path, monkeypatch, raw, secret, http_error
):
    import io
    import urllib.error
    import urllib.request

    from scripts.probe_rgbd_roles import _attempt

    from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
    from cloud_edge_robot_arm.vision.capture import CapturedFrame
    from cloud_edge_robot_arm.vision.model_resolver import (
        ModelConfigSnapshot,
        resolve_visual_planner,
    )
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from tests.test_rgbd_observations import observation_payload

    class ExternalBoundary:
        def open(self, request, timeout):
            if http_error:
                raise urllib.error.HTTPError(request.full_url, 503, secret, {}, io.BytesIO(raw))
            return io.BytesIO(raw)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: ExternalBoundary())
    model = ModelConfigSnapshot(
        provider="openai_compatible",
        model="qwen3.8-max",
        endpoint="https://dashscope.aliyuncs.com",
        weight_digest=None,
        quantization=None,
        image_size=(320, 240),
        generation_parameters={"temperature": 0, "num_predict": 512},
        timeout_s=30,
    )
    planner = resolve_visual_planner(model, api_key=secret, allow_paid=True)
    observation = RGBDObservation.model_validate(observation_payload())
    frame = CapturedFrame(
        observation,
        (0, 11, 12, -1),
        {0: "table", 11: "object_geom", 12: "target_region_geom"},
        "fixture",
        ("fixture",) * 3,
    )
    request = InitialPlanningRequest(
        request_id="software-escaped-secret",
        user_instruction="pick red cube",
        scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
        observation=observation,
    )
    attempt = _attempt(planner, request, frame, tmp_path, 0, cloud())
    assert attempt.get("wire_artifact_suppressed") is True
    assert attempt["status"] == "BLOCKED"
    assert attempt["response_sha256"] == hashlib.sha256(raw).hexdigest()
    assert attempt["serialized_received_bytes"] == len(raw)
    assert not (tmp_path / "attempt-00" / "response.raw").exists()
    assert not (tmp_path / "attempt-00" / "response.json").exists()
    assert "parsed_json" not in attempt
    assert "observation_evidence" not in attempt
    assert secret not in json.dumps(attempt, ensure_ascii=False)
    assert all(
        secret.encode() not in path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()
    )


@pytest.mark.parametrize(
    "detail",
    [
        {"failure_type": "credential-marker"},
        {"parse_error": {"nested": ["\\u0063redential-marker"]}},
        {"credential-marker": "innocent"},
    ],
)
def test_sensitive_readable_failure_details_are_hash_only(detail):
    from scripts.probe_rgbd_roles import _safe_attempt_record

    record = detail | {"serialized_sent_bytes": 7, "serialized_received_bytes": 9}
    safe = _safe_attempt_record(record, "credential-marker")
    assert safe["status"] == "BLOCKED"
    assert safe["details_suppressed"] is True
    assert safe["serialized_sent_bytes"] == 7
    assert safe["serialized_received_bytes"] == 9
    assert len(safe["suppressed_details_sha256"]) == 64
    assert "credential-marker" not in json.dumps(safe)
    assert not (set(detail) & set(safe))


def test_sensitive_malformed_failure_count_cannot_escape_suppression():
    from scripts.probe_rgbd_roles import _safe_attempt_record

    safe = _safe_attempt_record(
        {"serialized_sent_bytes": "credential-marker", "serialized_received_bytes": 9},
        "credential-marker",
    )
    assert "credential-marker" not in json.dumps(safe)
    assert safe["serialized_sent_bytes"] is None
    assert safe["serialized_received_bytes"] == 9


def test_profile_failure_name_containing_credential_is_never_persisted(tmp_path, monkeypatch):
    from pathlib import Path

    from scripts.probe_rgbd_roles import run_probe

    from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
    from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository

    secret = "credential-marker"
    service = ModelControlService(
        repository=SQLiteModelProfileRepository(tmp_path / "models.db"),
        secret_store=InMemorySecretStore(),
    )
    profile = service.create_profile(
        display_name="max",
        provider_kind=PlannerProviderKind.OPENAI_COMPATIBLE,
        model_name="qwen3.8-max",
        base_url="https://dashscope.aliyuncs.com",
        api_key=secret,
    )
    failure = type(secret, (RuntimeError,), {})

    def failed_profile(_):
        raise failure(secret)

    monkeypatch.setattr(service, "get_profile", failed_profile)
    output = tmp_path / "blocked-profile"
    report = run_probe(
        Path("configs/research/ced_roles.yaml"),
        output,
        service=service,
        profile_id=profile.profile_id,
        execute=True,
        allow_paid=True,
    )
    assert report["status"] == "BLOCKED"
    assert report.get("details_suppressed") is True
    assert secret not in json.dumps(report, ensure_ascii=False)
    assert all(
        secret.encode() not in path.read_bytes() for path in output.rglob("*") if path.is_file()
    )


def test_secret_store_failure_name_is_opaque_before_key_can_be_read(tmp_path):
    from pathlib import Path

    from scripts.probe_rgbd_roles import run_probe

    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository

    secret = "credential-marker"
    failure = type(secret, (RuntimeError,), {})

    class FailedSecretStore:
        def has_secret(self, _):
            raise failure(secret)

    service = ModelControlService(
        repository=SQLiteModelProfileRepository(tmp_path / "models.db"),
        secret_store=FailedSecretStore(),
    )
    output = tmp_path / "blocked-secret-store"
    report = run_probe(
        Path("configs/research/ced_roles.yaml"),
        output,
        service=service,
        profile_id="unavailable-profile",
        execute=True,
        allow_paid=True,
    )
    assert report["status"] == "BLOCKED"
    assert secret not in json.dumps(report, ensure_ascii=False)
    assert all(
        secret.encode() not in path.read_bytes() for path in output.rglob("*") if path.is_file()
    )


def _p3_snapshot_for_wire(provider="openai_compatible", think=None):
    from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot

    generation = {"temperature": 0, "num_predict": 512}
    if think is not None:
        generation["think"] = think
    local = provider == "ollama"
    return ModelConfigSnapshot(
        provider=provider,
        model="qwen3.5:4b" if local else "generic-vision-model",
        endpoint="http://127.0.0.1:11434" if local else "https://example.invalid",
        weight_digest="b" * 64 if local else None,
        quantization="Q4_K_M" if local else None,
        image_size=(320, 240),
        generation_parameters=generation,
        timeout_s=30,
    )


def _p3_wire_boundary(monkeypatch, tmp_path, timeout_attempts=0):
    """Replace only external HTTP; keep exact CPU request/response bytes."""
    import io
    import urllib.request

    captured = []
    inference_count = 0

    class ExternalBoundary:
        def open(self, request, timeout):
            nonlocal inference_count
            endpoint = request.full_url.rsplit("/", 1)[-1]
            sent = request.data or b""
            directory = tmp_path / f"wire-{len(captured):02d}"
            directory.mkdir()
            (directory / "request.raw").write_bytes(sent)
            row = {"endpoint": endpoint, "sent": sent, "received": b"", "status": "SUCCESS"}
            captured.append(row)
            if endpoint == "show":
                response = {"capabilities": ["vision"], "details": {"quantization_level": "Q4_K_M"}}
            elif endpoint == "tags":
                response = {"models": [{"name": "qwen3.5:4b", "digest": "b" * 64}]}
            else:
                inference_count += 1
                response = {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "target_pixel": None,
                                        "destination_pixel": None,
                                        "target_label": "missing",
                                        "reported_confidence": 0,
                                        "skills": [],
                                        "reason": "software boundary reply",
                                    }
                                )
                            }
                        }
                    ]
                }
                if inference_count <= timeout_attempts:
                    row["status"] = "TIMEOUT"
                    (directory / "response.raw").write_bytes(b"")
                    (directory / "receipt.json").write_text(
                        json.dumps(
                            {
                                "scope": "CPU_SIMULATED_HTTP",
                                "endpoint": endpoint,
                                "sent_bytes": len(sent),
                                "received_bytes": 0,
                                "status": "TIMEOUT",
                            }
                        )
                    )
                    raise TimeoutError("software-only timeout")
            raw = json.dumps(response).encode()
            row["received"] = raw
            (directory / "response.raw").write_bytes(raw)
            (directory / "receipt.json").write_text(
                json.dumps(
                    {
                        "scope": "CPU_SIMULATED_HTTP",
                        "endpoint": endpoint,
                        "sent_bytes": len(sent),
                        "received_bytes": len(raw),
                        "status": "SUCCESS",
                    }
                )
            )
            return io.BytesIO(raw)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: ExternalBoundary())
    return captured


def test_ced_max_reuses_successful_normalized_transport(monkeypatch, tmp_path):
    import io
    import struct
    from pathlib import Path

    from PIL import Image
    from scripts.probe_rgbd_roles import read_role_config

    from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
    from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
    from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository
    from cloud_edge_robot_arm.vision.messages import model_to_observation_pixel
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    config = read_role_config(Path("configs/research/ced_roles.yaml"))
    assert config["cloud"]["coordinate_system"] == "normalized_1000"
    service = ModelControlService(
        repository=SQLiteModelProfileRepository(tmp_path / "models.db"),
        secret_store=InMemorySecretStore(),
    )
    profile = service.create_profile(
        display_name="P3 software-only Max",
        provider_kind=PlannerProviderKind.OPENAI_COMPATIBLE,
        model_name="qwen3.8-max",
        base_url="https://example.invalid",
        temperature=0,
        max_tokens=512,
    )
    planner, snapshot = roles().resolve_cloud_role(
        service,
        profile.profile_id,
        source_hashes={"software-fixture.py": "a" * 64},
        allow_paid=True,
        image_size=tuple(config["cloud"]["image_size"]),
        coordinate_system=config["cloud"]["coordinate_system"],
        grasp_profile=config["cloud"]["grasp_profile"],
        available_model_ids=config["cloud"]["available_model_ids"],
    )
    rgb = io.BytesIO()
    Image.new("RGB", (320, 240), (255, 0, 0)).save(rgb, format="PNG")
    observation = RGBDObservation(
        frame_id="P3-synthetic-camera",
        captured_at=datetime.now(UTC),
        sim_time_s=0,
        width=320,
        height=240,
        rgb_png_base64=base64.b64encode(rgb.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(struct.pack("<76800f", *([0.4] * 76800))).decode(),
        intrinsics=(320, 320, 160, 120),
        camera_to_world=(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
        source="mujoco_camera",
    )
    captured = _p3_wire_boundary(monkeypatch, tmp_path)
    draft = planner.plan(
        InitialPlanningRequest(
            request_id="P3-software-normalized",
            user_instruction="pick missing target",
            scene=SceneSummary(scene_version=1, updated_at=datetime.now(UTC)),
            observation=observation,
        )
    )
    assert draft.parse_error is None
    body = json.loads(captured[0]["sent"])
    assert body["model"] == "qwen3.8-max" == snapshot.model_id
    assert body["temperature"] == 0
    assert body["max_tokens"] == 512
    assert body.get("enable_thinking") is False
    assert body["response_format"] == {"type": "json_object"}
    images = [
        part["image_url"]["url"]
        for message in body["messages"]
        if isinstance(message["content"], list)
        for part in message["content"]
        if part["type"] == "image_url"
    ]
    blobs = [base64.b64decode(image.split(",", 1)[1], validate=True) for image in images]
    assert len(blobs) == 2 and blobs[0] != blobs[1]
    assert all(Image.open(io.BytesIO(blob)).size == (320, 240) for blob in blobs)
    assert "normalized integer coordinates 0 to 1000" in body["messages"][0]["content"]
    assert model_to_observation_pixel(
        (500, 500),
        observation,
        image_size=planner.model_snapshot.image_size,
        coordinate_system=planner.model_snapshot.coordinate_system,
    ) == (160, 120)
    assert planner.model_snapshot.grasp_profile == "mujoco_upright_box_v2"
    assert snapshot.weight_digest is None and snapshot.revision is None
    assert snapshot.request_config_hash == roles().configuration_hash(
        roles().cloud_request_settings(planner)
    )
    assert service.repository.get_active_profile_id() == ""


def test_role_cost_delta_preserves_all_sent_requests(monkeypatch, tmp_path):
    from cloud_edge_robot_arm.research.cost_ledger import CostLedger
    from cloud_edge_robot_arm.vision.model_resolver import resolve_visual_planner
    from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable

    captured = _p3_wire_boundary(monkeypatch, tmp_path, timeout_attempts=2)
    ledger = CostLedger()
    planner = resolve_visual_planner(_p3_snapshot_for_wire(), allow_paid=True)
    planner.cost_ledger = ledger
    for _ in range(2):
        with pytest.raises(RGBDModelUnavailable):
            planner._request_visual([{"role": "user", "content": "software-only retry"}], {})
    planner._request_visual([{"role": "user", "content": "software-only retry"}], {})
    rows = ledger.requests()
    assert len(rows) == len({row.request_id for row in rows}) == 3
    assert [row.status for row in rows] == ["TIMEOUT", "TIMEOUT", "SUCCESS"]
    assert all(row.sent_at is not None and row.finished_at is not None for row in rows)
    assert all(
        row.monetary_cost is None and row.provider_location == "REMOTE_SERVICE" for row in rows
    )
    assert [row.serialized_sent_bytes for row in rows] == [len(row["sent"]) for row in captured]
    assert [row.serialized_received_bytes for row in rows] == [
        len(row["received"]) for row in captured
    ]
    summary = ledger.snapshot()
    assert summary.cloud_model_requests == summary.model_requests == 3
    assert summary.requests_by_role == {"PLANNER": 3}
    assert summary.application_bytes == sum(
        len(row["sent"]) + len(row["received"]) for row in captured
    )
    assert all(row["monetary_cost"] is None for row in ledger.export()["requests"])
    (tmp_path / "cost-export.json").write_text(json.dumps(ledger.export()))


@pytest.mark.parametrize("think", [False, True], ids=["false", "true"])
def test_role_compatible_thinking_reaches_serialized_request(monkeypatch, tmp_path, think):
    from cloud_edge_robot_arm.vision.model_resolver import resolve_visual_planner

    snapshot = _p3_snapshot_for_wire(think=think)
    frozen = snapshot.evidence()
    planner = resolve_visual_planner(snapshot, allow_paid=True)
    captured = _p3_wire_boundary(monkeypatch, tmp_path)
    planner._request_visual([{"role": "user", "content": "software-only thinking"}], {})
    body = json.loads(captured[0]["sent"])
    assert "enable_thinking" in body
    assert body["enable_thinking"] is think
    assert "think" not in body
    assert body["max_tokens"] == 512
    assert snapshot.evidence() == frozen


@pytest.mark.parametrize(
    "case",
    [
        "compatible_without_setting",
        "compatible_without_snapshot",
        "ollama_default",
        "ollama_true",
        "paid_disabled",
    ],
)
def test_role_thinking_provider_controls(monkeypatch, tmp_path, case):
    from cloud_edge_robot_arm.research.cost_ledger import CostLedger
    from cloud_edge_robot_arm.vision.model_resolver import resolve_visual_planner
    from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable, RGBDPlannerAdapter

    captured = _p3_wire_boundary(monkeypatch, tmp_path)
    ledger = CostLedger()
    if case == "compatible_without_snapshot":
        planner = RGBDPlannerAdapter(
            base_url="https://example.invalid",
            model="generic-vision-model",
            provider="openai_compatible",
            allow_paid=True,
        )
    elif case.startswith("ollama"):
        planner = resolve_visual_planner(
            _p3_snapshot_for_wire(
                provider="ollama",
                think=True if case == "ollama_true" else None,
            )
        )
    else:
        planner = resolve_visual_planner(
            _p3_snapshot_for_wire(), allow_paid=case != "paid_disabled"
        )
    planner.cost_ledger = ledger
    if case == "paid_disabled":
        with pytest.raises(RGBDModelUnavailable, match="requires"):
            planner._request_visual([{"role": "user", "content": "software-only"}], {})
        assert captured == [] and ledger.requests() == ()
        return
    frozen = planner.model_snapshot.evidence() if planner.model_snapshot is not None else None
    planner._request_visual([{"role": "user", "content": "software-only"}], {})
    body = json.loads(captured[-1]["sent"])
    assert "enable_thinking" not in body
    if case.startswith("ollama"):
        assert body["think"] is (case == "ollama_true")
        assert "think" not in body["options"]
        assert body["options"]["num_predict"] == 512
    else:
        assert set(body) == {"model", "messages", "temperature", "max_tokens", "response_format"}
    assert planner.model_snapshot is None or planner.model_snapshot.evidence() == frozen
