"""Software-only independent probes; run with the released overlay on PYTHONPATH."""

import json
from datetime import timedelta

from tests.test_visual_repair_builder import NOW, api, fixture, provider


def main():
    results = []
    for field in ("observation", "context_observation", "window", "dependency"):
        request, context, window, observation = fixture()
        before = (
            observation.model_dump(mode="json"),
            tuple(window.replace_step_ids),
            context.dependencies[1].physical_effect_id,
        )

        def mutate(provider_request, provider_window, provider_observation, provider_context):
            proposal = provider(
                provider_request, provider_window, provider_observation, provider_context
            )
            if field == "observation":
                provider_observation.__dict__["calibration_version"] = "provider-mutated"
            elif field == "context_observation":
                provider_context.online_evidence.observation.__dict__[
                    "calibration_version"
                ] = "provider-mutated"
            elif field == "window":
                object.__setattr__(provider_window, "replace_step_ids", ("grasp", "telemetry"))
            else:
                object.__setattr__(
                    provider_context.dependencies[1], "physical_effect_id", "provider-mutated"
                )
            return proposal

        result = api().build_visual_repair(
            request, window, observation, context=context, provider=mutate,
            clock=lambda: NOW + timedelta(seconds=.2),
        )
        after = (
            observation.model_dump(mode="json"),
            tuple(window.replace_step_ids),
            context.dependencies[1].physical_effect_id,
        )
        results.append({
            "probe": field,
            "outcome": result.outcome,
            "reason": result.reason,
            "caller_inputs_changed": before != after,
            "caller_calibration": observation.calibration_version,
            "caller_window": after[1],
            "caller_dependency": after[2],
        })
    request, context, window, observation = fixture()
    times = iter([
        NOW + timedelta(seconds=.2), NOW + timedelta(seconds=.3),
        NOW + timedelta(seconds=7),
    ])
    result = api().build_visual_repair(
        request, window, observation, context=context, provider=provider,
        clock=lambda: next(times),
    )
    results.append({
        "probe": "final-created-time",
        "outcome": result.outcome,
        "reason": result.reason,
        "frame_age_at_creation_s": (result.created_at - observation.captured_at).total_seconds(),
        "contract_valid_until": context.active_contract.valid_until.isoformat(),
        "created_at": result.created_at.isoformat(),
        "steps": [step.step_id for step in result.new_steps],
    })
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
