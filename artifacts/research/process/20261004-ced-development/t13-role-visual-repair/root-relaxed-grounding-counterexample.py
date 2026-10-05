"""Root SOFTWARE_ONLY counterexample: real provider, MockTransport, zero live calls."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch

from cloud_edge_robot_arm.cloud.replanning.role_visual_repair import GroundedRepairStep
from cloud_edge_robot_arm.contracts.models import replan_payload_hash
from tests.test_role_visual_repair import setup

with TemporaryDirectory(prefix='bigsmall-relaxed-grounding-') as name:
    with MonkeyPatch.context() as patch:
        adapter, wire, planner, binding, source, request, window, observation, ledger = setup(Path(name), patch)

        def relaxed_grounding(intent, original, observation, context, binding_hash):
            proof = source.action_evidence[original.step_id]
            # Original frozen allowed error is 0.01 m. Candidate claims a 0.05 m
            # bound, increases error budget to 0.1 m and removes required sensors.
            proof = replace(proof, allowed_error_m=0.1, sensor_requirements=(),
                            evidence=replace(proof.evidence, geometric_error_bound_m=0.05))
            return GroundedRepairStep(original, proof, binding_hash, replan_payload_hash(original))

        adapter.grounding_provider = relaxed_grounding
        result = adapter.replan(request)
        print('scope=SOFTWARE_ONLY live_calls=0 controller_commands=0')
        print('original_allowed_error_m=', source.action_evidence['grasp'].allowed_error_m)
        print('candidate_bound_m=0.05 candidate_allowed_error_m=0.1 candidate_required_sensors=[]')
        print('outcome=', result.outcome, 'mock_transport_attempts=', len(wire.requests))
        print('steps=', [item.step_id for item in result.new_steps])
        assert result.outcome != 'REPLANNED', 'frozen error and sensor policy weakened by local grounder'
