"""Independent SOFTWARE_ONLY probes, using the frozen real provider and fake transport."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from pytest import MonkeyPatch

from cloud_edge_robot_arm.cloud.replanning.role_visual_repair import GroundedRepairStep
from cloud_edge_robot_arm.contracts.models import replan_payload_hash
from cloud_edge_robot_arm.edge.evidence.validator import validate_evidence
from tests.test_role_visual_repair import setup


for change in ("error_tolerance", "required_sensors", "ttl", "duration"):
    with TemporaryDirectory(prefix="independent-role-policy-") as directory:
        with MonkeyPatch.context() as patch:
            adapter, wire, _, _, source, request, *_ = setup(Path(directory), patch)
            observed = []

            def grounder(intent, original, observation, context, binding_hash):
                del intent
                proof = source.action_evidence[original.step_id]
                if change == "error_tolerance":
                    proof = replace(
                        proof, allowed_error_m=0.1,
                        evidence=replace(proof.evidence, geometric_error_bound_m=0.05),
                    )
                elif change == "required_sensors":
                    proof = replace(proof, sensor_requirements=())
                elif change == "ttl":
                    proof = replace(proof, ordinary_ttl_s=proof.ordinary_ttl_s * 2)
                else:
                    proof = replace(proof, expected_duration_s=proof.expected_duration_s + 1)
                verdict = validate_evidence(
                    proof, adapter.clock(), context.online_evidence.context_hash,
                    observation.calibration_version, online_evidence=context.online_evidence,
                )
                observed.append(verdict.status)
                assert verdict.status == "VALID", (change, verdict)
                return GroundedRepairStep(
                    original, proof, binding_hash, replan_payload_hash(original),
                )

            adapter.grounding_provider = grounder
            result = adapter.replan(request)
            assert observed == ["VALID"]
            assert len(wire.requests) == 1
            assert result.outcome != "REPLANNED" and not result.new_steps
            print({
                "scope": "SOFTWARE_ONLY", "change": change,
                "otherwise_canonical_proof": observed[0], "outcome": result.outcome,
                "candidate_steps": len(result.new_steps), "mock_attempts": len(wire.requests),
                "live_calls": 0, "controller_commands": 0,
            })
