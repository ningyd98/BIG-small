"""Software-only hard-state probe: backend, capture and skill calls are stubs."""

import json
import time
from datetime import UTC, datetime
from types import SimpleNamespace

from cloud_edge_robot_arm.edge.recovery.verification_router import (
    VerificationBudget,
    VerificationBudgetState,
)
from cloud_edge_robot_arm.vision.execution import _EpisodeStopped, _VisualEpisode
from tests.test_native_action_submit import sample


def main():
    results = []
    for field, value in (("estop_engaged", True), ("collision_detected", True), ("connected", False)):
        online, contract, step = sample()
        episode = _VisualEpisode.__new__(_VisualEpisode)
        episode.policy = SimpleNamespace(
            device_pipeline="OPENCV", cancelled=None, output_dir=None,
            role_binding=SimpleNamespace(bundle=SimpleNamespace(digest=lambda: "source-role")),
        )
        episode.observation = online.observation
        hard_state = online.robot_state.model_copy(update={field: value}, deep=True)
        episode.robot = SimpleNamespace(get_state=lambda: hard_state)
        episode.tracker = SimpleNamespace(facts=lambda *args: online.visual_facts)
        episode.validate_role_boundary = lambda: None
        episode.records = []
        episode.budget = VerificationBudgetState.start(
            VerificationBudget(2, 2, 10, 60), now=datetime.now(UTC)
        )
        episode.deadline = time.monotonic() + 60
        touched = []
        episode.backend = SimpleNamespace(step=lambda **kwargs: touched.append("backend_step"))
        episode.recapture = lambda: touched.append("capture_request")
        episode.shield = SimpleNamespace(pre_check=lambda *args: touched.append("safety"))
        episode.executor = SimpleNamespace(execute_attempt=lambda **kwargs: touched.append("skill"))
        try:
            episode.execute(contract, step)
        except _EpisodeStopped as error:
            reason = str(error)
        results.append({
            "hard_state": {field: value},
            "stopped_reason": reason,
            "requested_stub_operations": touched,
            "remaining_reobservations": episode.budget.remaining_reobservations,
            "routes": [row["route"] for row in episode.records
                       if row["layer"] == "ONLINE_VERIFICATION"],
        })
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
