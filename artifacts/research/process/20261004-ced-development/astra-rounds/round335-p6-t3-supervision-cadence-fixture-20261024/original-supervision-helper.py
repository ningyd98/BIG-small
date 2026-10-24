def _b_t3_supervision(runtime, data, key):
    from cloud_edge_robot_arm.vision.supervision import SupervisionContext, SupervisionDecision

    period, _ = runtime._runtime_option_sources()
    registered = runtime.initialize_supervision(period, data["robot"])
    assert registered.to_payload()["schema_version"] == "visual.supervision.record.local.v1"
    claim = runtime.reserve_supervision_capture(1, data["robot"])
    observation = _b_t3_frame(runtime, key + ":supervision")
    context = SupervisionContext(
        episode_id=runtime.episode_id, plan_version=data["contract"].plan_version,
        state_version=claim.cursor, next_step_id=claim.step_id,
        next_skill=data["original"].requirements[claim.step_id].original_step.skill.value,
        task_instruction=runtime.bootstrap.definition.user_instruction,
        observation_id=observation.observation_id, captured_at=observation.captured_at,
        proprioception={"estop_engaged": False, "collision_detected": False})
    runtime.complete_supervision_capture(claim, observation, context, data["robot"])
    frame = runtime.reserve_supervision_plan(claim, data["robot"])
    decision = SupervisionDecision(
        **{name: getattr(context, name) for name in (
            "episode_id", "plan_version", "state_version", "observation_id", "next_step_id")},
        recommendation="CONTINUE", reason="CPU recorded reply; no model invocation")
    completed = runtime.complete_supervision_plan(frame, decision, data["robot"])
    raw = completed.to_payload()
    assert raw["payload"]["supervisor_calls_reserved"] == 1
    assert raw["original_time"] == data["original"].local_time.to_payload()
    return {"record": raw, "context": context, "decision": decision, "frame": frame}
