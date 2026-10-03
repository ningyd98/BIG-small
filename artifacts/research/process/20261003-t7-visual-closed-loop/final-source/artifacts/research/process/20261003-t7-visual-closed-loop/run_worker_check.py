"""Real, isolated T7 worker integration check; never substitutes a model or physics."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker
from cloud_edge_robot_arm.simulation_workbench.models import ExperimentDraft
from cloud_edge_robot_arm.vision.frozen_model import load_frozen_planner


def main():
    # The frozen verifier is a repository CLI module, also used by the server.
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    draft = ExperimentDraft(
        backend="MUJOCO",
        input_mode="RGBD",
        execution_scope="VISION_CLOSED_LOOP",
        scenarios=["S01_NORMAL_STATIC"],
        control_modes=["PCSC"],
        seeds=[0],
        user_instruction="Move the red block to the green region.",
    )
    sources = [
        "src/cloud_edge_robot_arm/simulation_runtime/worker.py",
        "src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py",
        "src/cloud_edge_robot_arm/simulation_runtime/state_machine.py",
        "src/cloud_edge_robot_arm/vision/task_semantics.py",
        "src/cloud_edge_robot_arm/vision/execution.py",
    ]
    provenance = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in sources}
    (args.output / "source-sha256.json").write_text(json.dumps(provenance, indent=2) + "\n")
    repo = SQLiteSimulationJobRepository(args.output / "runtime.db")
    job = repo.create_job(
        run_id="real-closed-loop",
        batch_id="",
        backend="MUJOCO",
        scenario_id="S01_NORMAL_STATIC",
        control_mode="PCSC",
        seed=0,
        manifest_id="t7-real-worker",
        reproducibility_hash=hashlib.sha256(
            json.dumps(provenance, sort_keys=True).encode()
        ).hexdigest(),
        draft=draft.model_dump(mode="json"),
        timeout_seconds=120,
        max_attempts=1,
        artifact_root="real-closed-loop",
        source_commit="dirty-workspace-see-source-sha256",
        source_tree_hash="selected-source-sha256.json",
    )
    repo.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.CREATED,
        next_status=RuntimeJobStatus.QUEUED,
        reason_code="T7_REAL_INTEGRATION",
        worker_id="",
        lease_id="",
    )
    worker = SimulationWorker(
        worker_id="t7-real-worker",
        backend="MUJOCO",
        repository=repo,
        artifact_root=args.output,
        planner_factory=lambda: load_frozen_planner(args.frozen_dir),
    )
    assert worker.poll_once()
    current = repo.get_job(job.job_id)
    result = json.loads((args.output / current.artifact_paths["result"]).read_text())
    consistency = json.loads(
        (args.output / current.artifact_paths["evidence_consistency"]).read_text()
    )
    keys = (
        "evaluation_scope",
        "task_success",
        "online_reported_complete",
        "physical_success",
        "semantic_status",
        "executed_actions",
        "model_calls",
        "terminal_reason",
        "task_execution",
        "error",
    )
    verification = {
        "status": current.status.value,
        **{key: result.get(key) for key in keys},
        "consistent": consistency["consistent"],
        "artifact_paths": current.artifact_paths,
    }
    valid = (
        current.status.value in {"SUCCEEDED", "FAILED"}
        and result["status"] == current.status.value
        and not result.get("error")
        and result.get("semantic_status") == "PASS"
        and result.get("model_calls", 0) >= 1
        and result.get("executed_actions", 0) >= 1
        and consistency["consistent"]
        and "verification_state" in current.artifact_paths
        and result.get("task_success") == (current.status.value == "SUCCEEDED")
    )
    verification["integration_valid"] = valid
    (args.output / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    print(json.dumps(verification, indent=2))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
