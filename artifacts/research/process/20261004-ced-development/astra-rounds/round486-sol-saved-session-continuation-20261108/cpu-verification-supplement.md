# R486 CPU verification command supplement

Actual gpt-6-astra static correction to Task B4; the original plan remains immutable. All other scope, gates and acceptance boundaries remain in force.

Static evidence: `tests/test_rgbd_planning.py::test_model_control_default_dry_run_does_not_return_fake_contract` calls real `ModelControlService.planner_dry_run()` without replacing `capture_simulated_observation`. The RGBD branch initializes and renders MuJoCo before resolving the planner. Including this case conflicts with phase B's CPU-only/no-render scope, even though its final contract is null.

Replace only the adjacent pytest command in original B4 with:

```bash
.venv/bin/python -m pytest -q tests/test_rgbd_grasp_scope.py tests/test_rgbd_normalized_protocol.py tests/test_rgbd_planning.py tests/test_rgbd_project_defaults.py tests/test_rgbd_gripper_calibration.py::test_repaired_gripper_planner_records_its_own_calibration tests/test_openai_sol_visual_migration.py -k 'not test_model_control_default_dry_run_does_not_return_fake_contract'
```

The `-k` filter excludes exactly the named capture test; the other selected files and the single gripper-calibration node remain selected. Do not run the original unfiltered command or compensate with another renderer test. Preserve the actual command, output, return code and source hashes. The focused RED/GREEN command is unchanged.

Parent-reported phase A outcome: PAID_GATE_BLOCKED, HTTP200, PLANNER_FAILED, reason `Planner exception: RGBD_MODEL_UNAVAILABLE: compatible provider requires BIGSMALL_VLM_ALLOW_PAID_CALL=true`; elapsed 0.254s, no dispatch or contract. The successful saved profile was activated and remains active. This is parent-provided execution evidence, not a new execution by this planner. Independent phase B remains authorized.

Self-review: correction changes only test selection and closes the identified render path; no product/test implementation, API action, execution or delegation performed. Original plan and affected test SHA256 pins are recorded in the companion JSON. Input hash drift before execution requires review against the original plan's permitted changes.
