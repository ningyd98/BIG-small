# ROOT R91 design acceptance

ROOT reviewed the pinned full design, plan and bounded original quotations. The versioned operational completion recipe is accepted for staged implementation under the existing T12 scope. This does not accept implementation, calibration data, native admission or an actual run.

- Timing: CHECKPOINT_D_FULL_S is limited to the registered single-owner MuJoCo S domain. Original D TTL/deadline checks remain independent. Missing future H_D is explicitly NOT_REQUIRED only for this factory-bound recipe; FULL_FUTURE_D_REQUIRED and external UTC remain strict. No hard deadline completion guarantee follows.
- Quantity: C=max(G,U+L+M) is a new joint empirical endpoint metric, with separately reconstructed drift. It must not populate or masquerade as the old continuous motion bound. This fits the original R4 full-horizon empirical definition and clock review paragraph70; it is not a relaxation of the old schema.
- Geometry: whole-body/contact control points and rotation, complete allocated frames, unknown/incomplete/failed groups, and independent-component joint maxima remain required. Nine independent assigned groups and coverage0.9 do not imply unconditional safety or guarantee a finite 10mm result.
- Chain: GRASP uses actual proprioception without fabricated target_pose; RELEASE requires exact prior PLACE binding and whole-body stability. LIFT extra hold and fixed full-horizon closure are mandatory. Existing controller and unique backend owner remain the only physics executor.
- Lifecycle: original task deadlines never refresh on reobservation/cloud return. Late effects remain recorded; incomplete/expired work cannot be promoted to completion. Current source owner/window authority and all three consumers must close through P5/P6.

Implementation scheduling remains one product writer: finish current P3/P4 repairs, then P5/P6 and the explicitly dependent R91 stages. Recheck affected pins at each handoff and bind the then-accepted P5/P6 interfaces; proposed interfaces are not treated as existing. R91 Task1 CPU types can be scheduled separately once the writer is released.

Actual authorization remains withheld until software/independent review/source/domain gates are satisfied. Before prepare, bind the unique normal action order to the actual original contract; do not select an order during execution. Validate exact dt, each horizon component, full frame inventory and disk headroom against the proposed per-group caps. Resource caps are not Tcap or future wall certificates. First actual group is group001 of all nine assigned components, never a discardable pilot.

P3/P4 repairs are independent of this design acceptance. Existing P2 results and all historical failures stay unchanged. T12 remains incomplete until the original INITIAL, risk/selection, normal-chain and 32-episode requirements have real evidence.
