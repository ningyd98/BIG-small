# Independent risk review scope erratum

The original independent-review.md/hash43bcbf741c55708705e0cbae7a57dacc14029e604f19d1fff46a982c1d292c1d is preserved unchanged. Its recorded related59 PASS scope includes two existing software unit tests: test_compiled_marker_preserves_mass_inertia_joint_controller_camera_and_existing_contacts and test_compiled_colored_marker_has_identical_physical_dynamics_controller_and_camera. These tests construct MjData and call passive mj_step to compare existing asset dynamics. Therefore the original phrase “no simulator step” was too broad and should not be reused as the current scope claim.

Those were software unit checks, not newly collected research episodes, renderer/camera acquisition, model/provider inference or robot controller/action dispatch. They do not add formal physical acceptance or risk/INITIAL evidence. Original raw archives and verdict/findings remain unchanged.

The current fix1 independent review uses the explicit read-only/compile-constants scope with both dynamics tests deselected:109 passed,2 deselected18.38s. Its reader may compile MjModel source constants but never creates MjData, steps, renders or dispatches. All source probes create disposable SOFTWARE_ONLY files. Legacy probe text “no model” denotes no ML/provider inference request; it is not a claim that the fixed reader did not compile an MJCF model's constants.
