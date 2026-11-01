"""软件工厂合同：持久任务必须可由真实公共服务读取，无 worker 执行。"""

from copy import deepcopy

import pytest

from cloud_edge_robot_arm.dashboard.event_stream import DashboardEventStream
from cloud_edge_robot_arm.simulation_runtime.service import SimulationRuntimeService
from cloud_edge_robot_arm.simulation_workbench.models import ExperimentManifest
from tests.test_phase11_1_simulation_runtime import _draft
from tests.test_rgbd_runtime_control import _queued_closed_loop_worker
from tests.test_visual_worker_factory import software_factory


@pytest.mark.parametrize(
    "variant", ["queued_default", "queued_custom", "inherited_software_factory"]
)
def test_queued_fixture_has_complete_manifest(monkeypatch, tmp_path, variant):
    """缺少创建时 manifest 或调用方嵌套配置别名会破坏公共读出。"""
    events = None
    caller_draft = None
    service = None
    if variant == "inherited_software_factory":
        repo, job, worker, calls, _, _, events = software_factory(monkeypatch, tmp_path)
        assert calls == []
    else:
        if variant == "queued_custom":
            caller_draft = _draft(
                backend="MUJOCO", input_mode="RGBD", execution_scope="VISION_CLOSED_LOOP"
            )
            caller_draft["parameter_overrides"]["timeout_seconds"] = 17
        repo, job, worker = _queued_closed_loop_worker(tmp_path, caller_draft)
    try:
        persisted = repo.get_job(job.job_id)
        expected_draft = deepcopy(persisted.draft)
        manifest = ExperimentManifest.model_validate(persisted.manifest)
        assert manifest.manifest_id == persisted.manifest_id == "manifest"
        assert manifest.reproducibility_hash == persisted.reproducibility_hash == "hash"
        assert manifest.source_commit == persisted.source_commit == "test"
        assert manifest.source_tree_hash == persisted.source_tree_hash == "test"
        assert manifest.run_count == 1
        assert manifest.schema_version == "phase11.simulation.v1"
        assert manifest.normalized_config == expected_draft
        assert expected_draft["input_mode"] == "RGBD"
        assert expected_draft["execution_scope"] == "VISION_CLOSED_LOOP"
        if caller_draft is not None:
            assert manifest.normalized_config["parameter_overrides"]["timeout_seconds"] == 17
            caller_draft["parameter_overrides"]["timeout_seconds"] = 999
            caller_draft["scenarios"].append("S14_EMERGENCY_STOP")
        detached = manifest.model_dump(mode="json")
        manifest.normalized_config["input_mode"] = "mutated-caller-copy"
        assert repo.get_job(job.job_id).manifest == detached
        assert repo.get_job(job.job_id).draft == expected_draft
        service = SimulationRuntimeService(
            artifact_root=tmp_path,
            database_path=repo.database_path,
            event_stream=DashboardEventStream(),
        )
        starts = []
        monkeypatch.setattr(service.dispatcher, "start", lambda: starts.append("suppressed"))
        public = service.get_run(job.run_id)
        assert public.manifest.model_dump(mode="json") == detached
        assert public.status.value == "QUEUED"
        assert public.run_id == "terminal-test"
        assert starts == ["suppressed"]
        assert service.dispatcher._thread is None
        assert worker._operational_lease_session is None
    finally:
        if service is not None:
            service.dispatcher.stop()
        if events is not None:
            events.close()
