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
