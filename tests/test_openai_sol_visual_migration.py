"""R457 software contracts: no real credentials, model calls, or physical evidence."""

from __future__ import annotations

import base64
import io
import json
import urllib.request
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from scripts import probe_rgbd_roles as probe

from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
from cloud_edge_robot_arm.model_control.service import ModelControlService
from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository
from cloud_edge_robot_arm.vision import model_resolver as resolver
from cloud_edge_robot_arm.vision import role_models as roles
from cloud_edge_robot_arm.vision.capture import CapturedFrame
from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable, RGBDPlannerAdapter
from tests.test_rgbd_normalized_protocol import REQUIRED_SKILLS, _request

MODEL = "gpt-6.1-sol"
SECRET = "r457-fictional-credential"
CONFIG = Path("configs/research/ced_roles.yaml")


def _policy():
    assert callable(getattr(resolver, "sol_generation_parameters", None)), (
        "R457 Sol request policy missing"
    )


def _snapshot(**changes):
    values = dict(
        provider="openai_compatible",
        model=MODEL,
        endpoint="https://api.openai.com",
        weight_digest=None,
        quantization=None,
        image_size=(320, 240),
        generation_parameters=resolver.sol_generation_parameters(),
        timeout_s=180,
        coordinate_system="normalized_1000",
    )
    return resolver.ModelConfigSnapshot(**(values | changes))


def _service(tmp_path, **changes):
    service = ModelControlService(
        repository=SQLiteModelProfileRepository(tmp_path / "profiles.db"),
        secret_store=InMemorySecretStore(),
    )
    values = dict(
        display_name="R457 software only",
        provider_kind=PlannerProviderKind.OPENAI_COMPATIBLE,
        model_name=MODEL,
        base_url="https://api.openai.com",
        api_key=SECRET,
        max_tokens=4096,
        timeout_seconds=180,
    )
    return service, service.create_profile(**(values | changes))


def _reply(content=None, finish_reason="stop"):
    if content is None:
        content = json.dumps(
            dict(
                target_pixel=[250, 250],
                destination_pixel=[750, 750],
                target_label="red cube",
                reported_confidence=0.9,
                skills=REQUIRED_SKILLS,
                reason="software visible surfaces",
            )
        )
    return json.dumps(
        {"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]}
    ).encode()


def _wire(monkeypatch, raw=None):
    rows = []
    response = _reply() if raw is None else raw

    def opener(*handlers):
        class Boundary:
            def open(self, request, timeout):
                rows.append(
                    dict(
                        url=request.full_url,
                        body=json.loads(request.data),
                        headers=dict(request.header_items()),
                        handlers=handlers,
                        sent=request.data,
                        received=response,
                        timeout=timeout,
                    )
                )
                return io.BytesIO(response)

        return Boundary()

    monkeypatch.setattr(urllib.request, "build_opener", opener)
    return rows


def _role(planner):
    return roles.RoleProviderSnapshot(
        role="CLOUD",
        provider_id="software-sol",
        provider_location="REMOTE_SERVICE",
        model_id=MODEL,
        revision=None,
        weight_digest=None,
        quantization=None,
        request_config_hash=roles.configuration_hash(roles.cloud_request_settings(planner)),
        source_hashes=probe.source_fingerprints(),
    )


def _frame():
    observation = _request().observation
    count = observation.width * observation.height
    return CapturedFrame(observation, (0,) * count, {0: "table"}, "software", ("software",) * 3)


def test_sol_snapshot_strict_generation_and_hash():
    _policy()
    snapshot = _snapshot()
    assert dict(snapshot.generation_parameters) == {
        "reasoning_effort": "low",
        "max_completion_tokens": 4096,
    }
    digests = set()
    for effort in ("low", "medium", "high", "xhigh", "max"):
        digests.add(
            replace(
                snapshot, generation_parameters=resolver.sol_generation_parameters(4096, effort)
            ).digest()
        )
    assert len(digests) == 5
    assert (
        replace(snapshot, generation_parameters=resolver.sol_generation_parameters(8192)).digest()
        != snapshot.digest()
    )
    for effort in ("none", "minimal", "unknown", True, 3):
        with pytest.raises(ValueError):
            resolver.sol_generation_parameters(4096, effort)
    for tokens in (True, 1.0, 0, -1, 32769, "4096"):
        with pytest.raises(ValueError):
            resolver.sol_generation_parameters(tokens)
    for generation in (
        {"temperature": 0},
        {"reasoning_effort": "low"},
        dict(snapshot.generation_parameters) | {"think": False},
    ):
        with pytest.raises(ValueError):
            replace(snapshot, generation_parameters=generation)
    with pytest.raises(ValueError):
        replace(snapshot, model="qwen3.8-max")
    with pytest.raises(ValueError):
        replace(snapshot, provider="ollama", weight_digest="", quantization="UNKNOWN")
    with pytest.raises(TypeError):
        snapshot.generation_parameters["reasoning_effort"] = "high"


def test_sol_official_route_and_paid_guard_before_transport(monkeypatch):
    _policy()
    rows = _wire(monkeypatch)
    for base, path in (
        ("https://api.openai.com", "/v1/chat/completions"),
        ("https://api.openai.com/v1", "/chat/completions"),
    ):
        adapter = resolver.resolve_visual_planner(
            _snapshot(endpoint=base), chat_path=path, allow_paid=True, api_key=SECRET
        )
        adapter._request_visual([], {})
        assert rows[-1]["url"] == "https://api.openai.com/v1/chat/completions"
        handlers = [
            h for h in rows[-1]["handlers"] if isinstance(h, urllib.request.HTTPRedirectHandler)
        ]
        assert len(handlers) == 1
        assert (
            handlers[0].redirect_request(
                urllib.request.Request(rows[-1]["url"]),
                None,
                302,
                "redirect",
                {},
                "https://example.invalid",
            )
            is None
        )
    for base, path in (
        ("http://api.openai.com", "/v1/chat/completions"),
        ("https://api.openai.com.invalid", "/v1/chat/completions"),
        ("https://x.api.openai.com", "/v1/chat/completions"),
        ("https://api.openai.com:443", "/v1/chat/completions"),
        ("https://user@api.openai.com", "/v1/chat/completions"),
        ("https://api.openai.com?x=1", "/v1/chat/completions"),
        ("https://api.openai.com#x", "/v1/chat/completions"),
        ("https://api.openai.com/wrong", "/v1/chat/completions"),
        ("https://api.openai.com/v1", "/v1/chat/completions"),
        ("https://api.openai.com", "/chat/completions"),
    ):
        with pytest.raises(ValueError):
            resolver.validate_sol_route("openai_compatible", MODEL, base, path)
    with pytest.raises(ValueError):
        resolver.validate_sol_route(
            "ollama", MODEL, "https://api.openai.com", "/v1/chat/completions"
        )
    blocked = resolver.resolve_visual_planner(_snapshot())
    with pytest.raises(RGBDModelUnavailable):
        blocked._request_visual([], {})
    for field, value in (
        ("model_name", "qwen3.8-max"),
        ("provider", "ollama"),
        ("base_url", "https://example.invalid"),
        ("chat_path", "/chat/completions"),
    ):
        adapter = resolver.resolve_visual_planner(_snapshot(), allow_paid=True)
        setattr(adapter, field, value)
        with pytest.raises((ValueError, RGBDModelUnavailable)):
            adapter._request_visual([], {})
    assert len(rows) == 2


def test_sol_role_family_profile_and_entry_binding(tmp_path, monkeypatch):
    _policy()
    config = probe.read_role_config(CONFIG)
    assert config["cloud"]["model_family"] == MODEL
    assert config["cloud"]["profile_id"] is None
    assert roles.select_cloud_model_id(MODEL, [MODEL + "-2026-11-08", "qwen3.8-max"]) == MODEL
    assert (
        roles.select_cloud_model_id("qwen3.8-max", ["qwen3.8-max-2026-09-01"])
        == "qwen3.8-max-2026-09-01"
    )
    with pytest.raises(ValueError):
        roles.select_cloud_model_id(MODEL + "-2026-11-08")
    service, sol = _service(tmp_path)
    planner, cloud = roles.resolve_cloud_role(
        service, sol.profile_id, source_hashes={"test": "a" * 64}, expected_model_family=MODEL
    )
    assert cloud.model_id == MODEL and cloud.weight_digest is None
    assert planner.model_snapshot.generation_parameters["max_completion_tokens"] == 4096
    qwen = service.create_profile(
        display_name="legacy",
        provider_kind=PlannerProviderKind.OPENAI_COMPATIBLE,
        model_name="qwen3.8-max",
        base_url="https://example.invalid",
        api_key=SECRET,
    )
    original = roles.resolve_cloud_role
    with monkeypatch.context() as patch:
        patch.setattr(
            service.secret_store,
            "get_secret",
            lambda *a: pytest.fail("secret read before family rejection"),
        )
        with pytest.raises(ValueError, match="family"):
            original(
                service,
                qwen.profile_id,
                source_hashes={"test": "a" * 64},
                expected_model_family=MODEL,
            )
    assert service.repository.get_active_profile_id() == ""
    assert (
        original(service, qwen.profile_id, source_hashes={"test": "a" * 64})[1].model_id
        == "qwen3.8-max"
    )
    calls = []

    def checked(*args, **kwargs):
        calls.append(kwargs.get("expected_model_family"))
        return original(*args, **kwargs)

    monkeypatch.setattr(probe, "resolve_cloud_role", checked)
    from cloud_edge_robot_arm.vision import capture

    class ForbiddenCapture:
        def __init__(self, *args, **kwargs):
            pytest.fail("renderer started")

    monkeypatch.setattr(capture, "MuJoCoCaptureSession", ForbiddenCapture)
    rows = _wire(monkeypatch)
    report = probe.run_probe(
        CONFIG,
        tmp_path / "probe",
        service=service,
        profile_id=qwen.profile_id,
        execute=True,
        allow_paid=True,
    )
    assert report["status"] == "BLOCKED" and report["attempts"] == [] and rows == []
    from scripts import run_rgbd_pilot as pilot

    from cloud_edge_robot_arm.research import freeze_evidence

    monkeypatch.setattr(pilot, "MuJoCoCaptureSession", ForbiddenCapture)
    monkeypatch.setattr(pilot, "PerturbedCapture", ForbiddenCapture)

    monkeypatch.setattr(roles, "resolve_cloud_role", checked)
    monkeypatch.setattr(
        freeze_evidence,
        "verify_role_probe_evidence",
        lambda *a: {
            "available": True,
            "report": {"bundle": {"cloud_snapshot": {"source_hashes": {"test": "a" * 64}}}},
        },
    )
    monkeypatch.setattr(pilot, "_ced_pools", lambda *a: [])
    monkeypatch.setattr(
        pilot, "run_pilot_stage", lambda *a, **kw: {"actual_research_status": "NOT_RUN"}
    )
    settings = yaml.safe_load(Path("configs/research/ced_selection.yaml").read_text())
    settings["role_probe"] = "software-prerequisite"
    path = tmp_path / "pilot.yaml"
    path.write_text(yaml.safe_dump(settings))
    output = tmp_path / "pilot"
    output.mkdir()
    result = pilot.run_ced_pilot(
        path,
        output,
        "selection",
        service=service,
        profile_id=qwen.profile_id,
        execute=True,
        allow_paid=True,
    )
    assert result["actual_research_status"] == "NOT_RUN" and rows == []
    assert calls == [MODEL, MODEL]


def test_sol_two_image_json_wire_and_grounding(monkeypatch):
    _policy()
    rows = _wire(monkeypatch)
    planner = resolver.resolve_visual_planner(_snapshot(), allow_paid=True, api_key=SECRET)
    draft = planner.plan(_request())
    assert len(rows) == 1
    body = rows[0]["body"]
    assert set(body) == {
        "model",
        "messages",
        "response_format",
        "reasoning_effort",
        "max_completion_tokens",
    }
    assert body["model"] == MODEL and body["reasoning_effort"] == "low"
    assert body["max_completion_tokens"] == 4096 and body["response_format"] == {
        "type": "json_object"
    }
    images = [
        base64.b64decode(p["image_url"]["url"].split(",", 1)[1])
        for m in body["messages"]
        if isinstance(m["content"], list)
        for p in m["content"]
        if p["type"] == "image_url"
    ]
    assert len(images) == 2 and images[0] != images[1]
    assert all(b.startswith(b"\x89PNG") for b in images)
    assert "SECRET_ORACLE" not in json.dumps(body)
    assert draft.parse_error is None and draft.observed_scene is not None
    assert draft.observation_evidence["original_pixel_target"] == [2, 1]
    assert draft.observation_evidence["original_pixel_destination"] == [6, 3]


def test_sol_active_and_environment_effective_budget(tmp_path, monkeypatch):
    _policy()
    service, profile = _service(tmp_path, max_tokens=8192)
    service.activate_profile(profile.profile_id)
    active = service.visual_planner()
    assert dict(active.model_snapshot.generation_parameters) == {
        "reasoning_effort": "low",
        "max_completion_tokens": 8192,
    }
    service.update_profile(profile.profile_id, model_name="other-model")
    assert active.model_name == MODEL and active.model_snapshot.model == MODEL
    monkeypatch.delenv("BIGSMALL_VLM_FROZEN_DIR", raising=False)
    monkeypatch.setenv("BIGSMALL_VLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("BIGSMALL_VLM_MODEL", MODEL)
    monkeypatch.setenv("BIGSMALL_VLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("BIGSMALL_VLM_API_KEY", SECRET)
    monkeypatch.setenv("BIGSMALL_VLM_ALLOW_PAID_CALL", "true")
    rows = _wire(monkeypatch)
    RGBDPlannerAdapter.from_environment().plan(_request())
    assert rows[0]["body"]["max_completion_tokens"] == 4096
    assert rows[0]["body"]["reasoning_effort"] == "low"
    assert rows[0]["url"] == "https://api.openai.com/v1/chat/completions"
    from cloud_edge_robot_arm.vision import frozen_model

    frozen = object()
    monkeypatch.setattr(frozen_model, "load_frozen_planner", lambda path: frozen)
    monkeypatch.setenv("BIGSMALL_VLM_FROZEN_DIR", "software-old-freeze")
    assert RGBDPlannerAdapter.from_environment() is frozen


def test_sol_probe_summary_and_source_drift_binding(tmp_path, monkeypatch):
    _policy()
    rows = _wire(monkeypatch)
    planner = resolver.resolve_visual_planner(_snapshot(), allow_paid=True, api_key=SECRET)
    cloud = _role(planner)
    attempt = probe._attempt(planner, _request(), _frame(), tmp_path, 0, cloud)
    assert attempt["request_summary"] == attempt["expected_request_summary"]
    assert attempt["request_summary"]["generation_parameters"] == dict(
        planner.model_snapshot.generation_parameters
    )
    assert attempt["actual_request_settings"] == roles.cloud_request_settings(planner)
    assert attempt["request_summary"] == probe.summarize_role_request(rows[0]["body"])
    assert "src/cloud_edge_robot_arm/vision/model_resolver.py" in cloud.source_hashes
    assert (
        not probe.can_accept_role_probe(attempt) and not (tmp_path / "roles-frozen.json").exists()
    )
    original = roles.configuration_hash(roles.cloud_request_settings(planner))
    for params in (
        resolver.sol_generation_parameters(8192),
        resolver.sol_generation_parameters(4096, "high"),
    ):
        changed = resolver.resolve_visual_planner(
            _snapshot(generation_parameters=params), allow_paid=True
        )
        assert roles.configuration_hash(roles.cloud_request_settings(changed)) != original
    alternate = resolver.resolve_visual_planner(
        _snapshot(endpoint="https://api.openai.com/v1"),
        chat_path="/chat/completions",
        allow_paid=True,
    )
    assert roles.configuration_hash(roles.cloud_request_settings(alternate)) != original
    for name, value in (
        ("model_name", "other"),
        ("provider", "ollama"),
        ("chat_path", "/chat/completions"),
    ):
        changed = resolver.resolve_visual_planner(_snapshot(), allow_paid=True)
        setattr(changed, name, value)
        assert roles.configuration_hash(roles.cloud_request_settings(changed)) != original


def test_sol_rejects_truncated_response_without_authority(tmp_path, monkeypatch):
    _policy()
    raw = _reply('{"target_pixel": [', "length")
    rows = _wire(monkeypatch, raw)
    planner = resolver.resolve_visual_planner(_snapshot(), allow_paid=True)
    attempt = probe._attempt(planner, _request(), _frame(), tmp_path, 0, _role(planner))
    assert len(rows) == 1 and attempt["parsed"] is False and attempt["grounded"] is False
    assert attempt["serialized_received_bytes"] == len(raw)
    assert (tmp_path / "attempt-00/response.raw").read_bytes() == raw
    assert attempt["cost_ledger"]["summary"]["cloud_model_requests"] == 1
    assert not (tmp_path / "roles-frozen.json").exists() and not probe.can_accept_role_probe(
        attempt
    )


def test_sol_qwen_and_secret_boundary_compatibility(tmp_path, monkeypatch):
    _policy()
    assert resolver.compatible_chat_generation(
        "qwen3.8-max",
        {
            "temperature": 0.2,
            "num_predict": 777,
            "think": False,
        },
    ) == {"temperature": 0.2, "max_tokens": 777, "enable_thinking": False}
    from tests.test_rgbd_role_models import _p3_snapshot_for_wire, _p3_wire_boundary

    captured = _p3_wire_boundary(monkeypatch, tmp_path)
    local = resolver.resolve_visual_planner(_p3_snapshot_for_wire("ollama", True))
    local._request_visual([], {})
    local_body = json.loads(captured[-1]["sent"])
    assert local_body["think"] is True
    assert local_body["options"] == {"temperature": 0, "num_predict": 512}
    rows = _wire(monkeypatch)
    planner = resolver.resolve_visual_planner(_snapshot(), api_key=SECRET, allow_paid=True)
    planner.plan(_request())
    assert rows[0]["headers"]["Authorization"] == "Bearer " + SECRET
    assert SECRET not in json.dumps(_role(planner).evidence())
    assert SECRET not in json.dumps(probe.summarize_role_request(rows[0]["body"]))
    _wire(monkeypatch, _reply(SECRET))
    attempt = probe._attempt(planner, _request(), _frame(), tmp_path, 0, _role(planner))
    assert attempt["wire_artifact_suppressed"] is True
    assert not (tmp_path / "attempt-00/response.raw").exists()
    assert SECRET not in json.dumps(attempt)
    service, profile = _service(tmp_path)
    service.secret_store.delete_secret(profile.profile_id)
    report = probe.run_probe(
        CONFIG,
        tmp_path / "missing",
        service=service,
        profile_id=profile.profile_id,
        execute=True,
        allow_paid=True,
    )
    assert report["status"] == "BLOCKED" and report["attempts"] == []
