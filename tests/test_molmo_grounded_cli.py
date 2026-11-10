"""诊断入口必须明确区分空运行、回放与真实推理，并保留失败计数。"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from cloud_edge_robot_arm.cloud.planning.models import PlanningOutcome
from tests.test_molmo_grounded_planner import SKILLS, FixturePoints, request_scene


def inputs(tmp_path):
    request = request_scene()
    task = {
        "instruction": request.user_instruction,
        "target_phrase": "red block",
        "destination_phrase": "green region",
        "target_label": "red block",
    }
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json())
    task_path = tmp_path / "task.json"
    task_path.write_text(json.dumps(task))
    return request, task, request_path, task_path


def args(tmp_path, request_path, task_path):
    return [
        "--request",
        str(request_path),
        "--task-descriptor",
        str(task_path),
        "--output",
        str(tmp_path / "out"),
    ]


def test_cli_dry_run_has_zero_calls(tmp_path):
    from scripts.probe_molmo_grounded_planner import main

    _, _, request_path, task_path = inputs(tmp_path)
    assert main(args(tmp_path, request_path, task_path)) == 0
    report = json.loads((tmp_path / "out/report.json").read_text())
    assert report["status"] == "NOT_STARTED"
    assert report["model_loads_started"] == report["generation_calls_started"] == 0
    assert report["paid_cloud_calls_started"] == 0 and report["hardware_dispatch"] is False


def replay_files(tmp_path, request, task):
    task_hash = hashlib.sha256(
        json.dumps(task, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    points = []
    for phrase, coords in [
        ("visible top center of red block", "150 410"),
        ("interior of green region", "650 425"),
    ]:
        points.append(
            {
                "observation_checksum": request.observation.checksum_sha256,
                "rgb_sha256": request.observation.evidence()["rgb_sha256"],
                "query_sha256": hashlib.sha256(phrase.encode()).hexdigest(),
                "raw_text": f'<points coords="1 1 {coords}">support</points>',
            }
        )
    p = tmp_path / "points.json"
    p.write_text(json.dumps(points))
    c = tmp_path / "cloud.json"
    c.write_text(
        json.dumps(
            {
                "observation_checksum": request.observation.checksum_sha256,
                "task_descriptor_sha256": task_hash,
                "content": json.dumps({"skills": SKILLS}),
            }
        )
    )
    return p, c


def test_cli_replay_is_labelled_and_no_network(tmp_path, monkeypatch):
    import socket

    from scripts.probe_molmo_grounded_planner import main

    request, task, r, t = inputs(tmp_path)
    p, c = replay_files(tmp_path, request, task)

    def no_network(*a, **k):
        raise AssertionError("replay attempted network")

    monkeypatch.setattr(socket, "socket", no_network)
    assert (
        main(
            args(tmp_path, r, t)
            + ["--mode", "replay", "--replay-points", str(p), "--replay-cloud", str(c)]
        )
        == 0
    )
    report = json.loads((tmp_path / "out/report.json").read_text())
    assert report["execution_mode"] == "REPLAY"
    assert report["attempts"][0]["pipeline_outcome"] == "PLANNED"
    assert report["generation_calls_started"] == report["paid_cloud_calls_started"] == 0
    assert report["api_fixture_calls"] == 1


def test_cli_replay_binding_mismatch_is_rejected(tmp_path):
    from scripts.probe_molmo_grounded_planner import main

    request, task, r, t = inputs(tmp_path)
    p, c = replay_files(tmp_path, request, task)
    rows = json.loads(p.read_text())
    rows[0]["query_sha256"] = "0" * 64
    p.write_text(json.dumps(rows))
    assert (
        main(
            args(tmp_path, r, t)
            + ["--mode", "replay", "--replay-points", str(p), "--replay-cloud", str(c)]
        )
        != 0
    )


def test_cli_preexisting_output_is_untouched(tmp_path):
    from scripts.probe_molmo_grounded_planner import main

    _, _, r, t = inputs(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep").write_text("original")
    assert main(args(tmp_path, r, t)) != 0
    assert (out / "keep").read_text() == "original"
    assert sorted(p.name for p in out.iterdir()) == ["keep"]


@contextmanager
def admitted(*args, **kwargs):
    yield {"evidence_scope": "CPU_RESOURCE_FIXTURE"}


class NativeFixture(FixturePoints):
    def __init__(self, **kwargs):
        super().__init__()
        self.model_loads_started = 1
        self.generation_calls_started = 0
        self.generation_calls_completed = 0
        self.raw = Path(kwargs["raw_directory"])
        self.raw.mkdir(parents=True)

    def point(self, observation, phrase):
        self.generation_calls_started += 1
        value = super().point(observation, phrase)
        self.generation_calls_completed += 1
        return value


def test_cli_native_no_paid_default(tmp_path, monkeypatch):
    import scripts.probe_molmo_grounded_planner as cli

    _, _, r, t = inputs(tmp_path)
    monkeypatch.setattr(cli, "MolmoPointProvider", NativeFixture)
    monkeypatch.setattr(cli, "_admit_resources", admitted)
    model = tmp_path / "model"
    model.mkdir()
    manifest = tmp_path / "manifest"
    manifest.write_text("{}")
    assert (
        cli.main(
            args(tmp_path, r, t)
            + [
                "--mode",
                "native",
                "--model-directory",
                str(model),
                "--asset-manifest",
                str(manifest),
            ]
        )
        == 0
    )
    report = json.loads((tmp_path / "out/report.json").read_text())
    assert report["model_loads_started"] == 1 and report["generation_calls_started"] == 2
    assert report["paid_cloud_calls_started"] == 0 and report["api_fixture_calls"] == 0
    assert report["attempts"][0]["local_geometry_status"] == "READY"
    assert report["real_cloud_status"] == "NOT_PERFORMED"


def test_cli_invalid_config_precedes_load(tmp_path, monkeypatch):
    import scripts.probe_molmo_grounded_planner as cli

    _, task, r, t = inputs(tmp_path)
    task["instruction"] = "different task"
    t.write_text(json.dumps(task))

    def forbidden(**kwargs):
        raise AssertionError("invalid config loaded model")

    monkeypatch.setattr(cli, "MolmoPointProvider", forbidden)
    assert cli.main(args(tmp_path, r, t) + ["--mode", "native"]) != 0


def test_cli_accounting_keeps_failed_attempt(tmp_path, monkeypatch):
    import scripts.probe_molmo_grounded_planner as cli

    _, _, r, t = inputs(tmp_path)

    class FailingNative(NativeFixture):
        def point(self, observation, phrase):
            self.generation_calls_started += 1
            (self.raw / "failure.json").write_text('{"generation_calls_started":1}')
            raise RuntimeError("CPU_FIXTURE_FAILURE")

    monkeypatch.setattr(cli, "MolmoPointProvider", FailingNative)
    monkeypatch.setattr(cli, "_admit_resources", admitted)
    model = tmp_path / "model"
    model.mkdir()
    manifest = tmp_path / "manifest"
    manifest.write_text("{}")
    assert (
        cli.main(
            args(tmp_path, r, t)
            + [
                "--mode",
                "native",
                "--model-directory",
                str(model),
                "--asset-manifest",
                str(manifest),
            ]
        )
        != 0
    )
    report = json.loads((tmp_path / "out/report.json").read_text())
    assert report["generation_calls_started"] == 1 and report["generation_calls_completed"] == 0
    assert (tmp_path / "out/raw/native/failure.json").exists()


def native_arguments(tmp_path, request_path, task_path):
    model = tmp_path / "model"
    model.mkdir()
    manifest = tmp_path / "manifest"
    manifest.write_text("{}")
    return args(tmp_path, request_path, task_path) + [
        "--mode",
        "native",
        "--model-directory",
        str(model),
        "--asset-manifest",
        str(manifest),
    ]


@pytest.mark.parametrize("case", ["timeout", "malformed", "empty", "rejected"])
def test_paid_diagnostic_requires_planned_pipeline(tmp_path, monkeypatch, case):
    import scripts.probe_molmo_grounded_planner as cli

    from tests.test_molmo_grounded_planner import adapter_fixture

    _, _, r, t = inputs(tmp_path)
    monkeypatch.setattr(cli, "MolmoPointProvider", NativeFixture)
    monkeypatch.setattr(cli, "_admit_resources", admitted)
    reply = (
        {"skills": []} if case == "empty" else {"skills": ["FLY"]} if case == "malformed" else None
    )
    adapter, _, _ = adapter_fixture(monkeypatch, reply=reply, fail=case == "timeout")
    monkeypatch.setattr(cli, "_selected_cloud", lambda *a: adapter)
    if case == "rejected":
        pipeline = cli.PlanningPipeline

        class RejectingPipeline(pipeline):
            def process(self, request):
                value = super().process(request)
                return value.model_copy(
                    update={"outcome": PlanningOutcome.REJECTED, "contract": None}
                )

        monkeypatch.setattr(cli, "PlanningPipeline", RejectingPipeline)
    assert cli.main(native_arguments(tmp_path, r, t) + ["--allow-paid"]) == 2
    report = json.loads((tmp_path / "out/report.json").read_text())
    assert report["diagnostic_passed"] is False
    assert report["paid_cloud_calls_started"] == 1
    assert report["real_cloud_status"] == "FAILED"


def test_raw_input_cloud_and_content_survive_parse_failure(tmp_path, monkeypatch):
    import scripts.probe_molmo_grounded_planner as cli

    from tests.test_molmo_grounded_planner import adapter_fixture

    _, _, r, t = inputs(tmp_path)
    request_bytes = r.read_bytes()
    task_bytes = t.read_bytes()
    monkeypatch.setattr(cli, "MolmoPointProvider", NativeFixture)
    monkeypatch.setattr(cli, "_admit_resources", admitted)
    adapter, _, _ = adapter_fixture(
        monkeypatch, reply={"skills": ["FLY"], "reason": "raw invalid intent"}
    )
    monkeypatch.setattr(cli, "_selected_cloud", lambda *a: adapter)
    assert cli.main(native_arguments(tmp_path, r, t) + ["--allow-paid"]) == 2
    out = tmp_path / "out"
    assert (out / "raw/inputs/request-01.json").read_bytes() == request_bytes
    assert (out / "raw/inputs/task-01.json").read_bytes() == task_bytes
    assert json.loads((out / "raw/attempt-01/cloud-content.txt").read_text())["skills"] == ["FLY"]
    assert list((out / "raw/cloud/attempt-01").glob("request-*.json"))
    assert list((out / "raw/cloud/attempt-01").glob("response-*.json"))
    manifest = json.loads((out / "raw-manifest.local.json").read_text())
    for row in manifest["files"]:
        data = (out / row["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == row["sha256"]
        assert b"test-only-cloud-secret" not in data
    assert r.read_bytes() == request_bytes and t.read_bytes() == task_bytes


def test_failed_load_has_manifest_and_start_count(tmp_path, monkeypatch):
    import scripts.probe_molmo_grounded_planner as cli

    _, _, r, t = inputs(tmp_path)

    def failed_load(**kwargs):
        raw = Path(kwargs["raw_directory"])
        raw.mkdir(parents=True)
        (raw / "load-started.json").write_text('{"model_loads_started":1}')
        (raw / "load-failure.json").write_text('{"error_type":"RuntimeError"}')
        raise RuntimeError("CPU load fixture failure")

    monkeypatch.setattr(cli, "MolmoPointProvider", failed_load)
    monkeypatch.setattr(cli, "_admit_resources", admitted)
    assert cli.main(native_arguments(tmp_path, r, t)) == 2
    report = json.loads((tmp_path / "out/report.json").read_text())
    assert report["model_loads_started"] == 1
    rows = json.loads((tmp_path / "out/raw-manifest.local.json").read_text())["files"]
    assert any(x["path"].endswith("load-failure.json") for x in rows)


def test_fresh_capture_template_loads_before_sensor(tmp_path, monkeypatch):
    import scripts.probe_molmo_grounded_planner as cli

    _, _, r, t = inputs(tmp_path)
    data = json.loads(r.read_text())
    data["observation"] = None
    r.write_text(json.dumps(data))
    original_bytes = r.read_bytes()
    order = []

    class OrderedNative(NativeFixture):
        def __init__(self, **kwargs):
            order.append("load")
            super().__init__(**kwargs)

    def capture():
        order.append("capture")
        return request_scene().observation

    monkeypatch.setattr(cli, "MolmoPointProvider", OrderedNative)
    monkeypatch.setattr(cli, "_admit_resources", admitted)
    monkeypatch.setattr(cli, "_fresh_capture", capture)
    assert cli.main(native_arguments(tmp_path, r, t) + ["--capture-fresh"]) == 0
    assert order == ["load", "capture"]
    assert (tmp_path / "out/raw/inputs/request-01.json").read_bytes() == original_bytes
    assert json.loads((tmp_path / "out/raw/capture-01/request.json").read_text())["observation"]


def test_missing_observation_without_fresh_capture_is_rejected(tmp_path, monkeypatch):
    import scripts.probe_molmo_grounded_planner as cli

    _, _, r, t = inputs(tmp_path)
    data = json.loads(r.read_text())
    data["observation"] = None
    r.write_text(json.dumps(data))

    def forbidden(**kwargs):
        raise AssertionError("invalid template loaded model")

    monkeypatch.setattr(cli, "MolmoPointProvider", forbidden)
    assert cli.main(args(tmp_path, r, t)) != 0


def test_cloud_observers_keep_attempt_binding_when_callbacks_are_delayed(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import scripts.probe_molmo_grounded_planner as cli

    request, _, r, t = inputs(tmp_path)
    second = tmp_path / "request-second.json"
    second.write_text(request.model_copy(update={"request_id": "cpu-second"}).model_dump_json())
    adapters = [SimpleNamespace(cloud=SimpleNamespace()) for _ in range(2)]
    selected = iter(adapters)
    observers = []
    bodies = {
        "first_request": b'{"cpu_fixture":"attempt1 request1"}',
        "delayed_request": b'{"cpu_fixture":"attempt1 request2"}',
        "first_response": b'{"cpu_fixture":"attempt1 response1"}',
        "second_request": b'{"cpu_fixture":"attempt2 request1"}',
        "second_response": b'{"cpu_fixture":"attempt2 response1"}',
    }

    class CPUFixturePipeline:
        def __init__(self, *, planner):
            self.planner = planner

        def process(self, request):
            observer = self.planner.cloud.raw_transport_observer
            observers.append(observer)
            if len(observers) == 1:
                observer("REQUEST", "/cpu-fixture", bodies["first_request"])
            else:
                observer("REQUEST", "/cpu-fixture", bodies["second_request"])
                observers[0]("REQUEST", "/cpu-fixture", bodies["delayed_request"])
                observers[0]("RESPONSE", "/cpu-fixture", bodies["first_response"])
                observer("RESPONSE", "/cpu-fixture", bodies["second_response"])
            draft = SimpleNamespace(
                observation_evidence={"opencv_initial_geometry": {"scope": "CPU_FIXTURE"}},
                raw_text="",
                parse_error=None,
            )
            return SimpleNamespace(
                outcome=PlanningOutcome.PLANNED,
                attempts=[SimpleNamespace(draft=draft)],
                reason="CPU_FIXTURE; no actual model/cloud execution",
            )

    monkeypatch.setattr(cli, "MolmoPointProvider", NativeFixture)
    monkeypatch.setattr(cli, "_admit_resources", admitted)
    monkeypatch.setattr(cli, "_selected_cloud", lambda *a: next(selected))
    monkeypatch.setattr(cli, "PlanningPipeline", CPUFixturePipeline)
    argv = native_arguments(tmp_path, r, t) + [
        "--request",
        str(second),
        "--task-descriptor",
        str(t),
        "--allow-paid",
    ]
    assert cli.main(argv) == 0
    out = tmp_path / "out"
    expected = {
        "raw/cloud/attempt-01/request-0001.json": bodies["first_request"],
        "raw/cloud/attempt-01/request-0002.json": bodies["delayed_request"],
        "raw/cloud/attempt-01/response-0001.json": bodies["first_response"],
        "raw/cloud/attempt-02/request-0001.json": bodies["second_request"],
        "raw/cloud/attempt-02/response-0001.json": bodies["second_response"],
    }
    for name, body in expected.items():
        assert (out / name).read_bytes() == body
    assert sorted(p.name for p in (out / "raw/cloud/attempt-02").iterdir()) == [
        "request-0001.json",
        "response-0001.json",
    ]
    report = json.loads((out / "report.json").read_text())
    assert len(report["attempts"]) == 2 and report["paid_cloud_calls_started"] == 3
    assert report["diagnostic_passed"] is True
    manifest = json.loads((out / "raw-manifest.local.json").read_text())
    hashes = {row["path"]: row["sha256"] for row in manifest["files"]}
    for name, body in expected.items():
        assert hashes[name] == hashlib.sha256(body).hexdigest()
