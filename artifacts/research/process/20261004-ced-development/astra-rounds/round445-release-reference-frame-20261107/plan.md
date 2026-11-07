# R445 — RELEASE reference frame and hold boundaries

Actual `gpt-6-astra`, PLAN_ONLY. This is a narrow source/coordinate clarification plus repair of a real missing registration convention. No product edits, tests, MuJoCo initialization, physics, rendering or Git writes. Twenty pinned inputs and original excerpts are in intake. ROOT's independently evolving reader is deliberately not pinned as an original definition; its implementation generation must be frozen before its original T3 GREEN.

## What existing sources establish

R91 defines RELEASE through the actually executed preceding PLACE exact payload and a registered complete rigid grasp transform, with corresponding eight object vertices. R439/R440 registered object_to_tcp as identity rotation plus (0,0,.01), and tool_to_tcp as identity rotation plus (.105,0,0). Existing native_calibration and full_rigid_geometry_errors use **only the translation** of object_to_tcp to locate a contact/TCP point relative to the object. They do not validate that its identity rotation is the physical TCP orientation. NativeGeometryRegistration validates tool_to_tcp against the actual TCP site, but does not validate object_to_tcp orientation against a grasp.

MuJoCoSkillRobot._move defaults to `_DOWNWARD=(sqrt(.5),0,sqrt(.5),0)` in wxyz order. PLACE invokes that same default. MotionController targets the actual `tcp` site's position and orientation, not a hand origin. Thus the command rotation in world coordinates is the +90 degree y rotation:

```text
R_down = [[ 0, 0, 1],
          [ 0, 1, 0],
          [-1, 0, 0]]
```

TCP site is an identity-rotation child at hand-local (.105,0,0), as checked by current v2 grasp profile and marked XML. The local +x axis points down. Top_grasp's named calibrated scalar places the desired TCP .01 m above the estimated center of an upright box. S01 default scene has identity object geom/body rotation; actual backend reset explicitly sets object free-joint quaternion to (1,0,0,0). This supplies a **nominal upright reference convention**, not evidence that the subsequently grasped object remains at that orientation.

PhysicsStepObservation contains actual object center/rotation and TCP position but no TCP rotation. This does not prevent computing a commanded RELEASE target from a fixed orientation command. It does prevent claiming an actual TCP-relative grasp measurement from that observation alone. Do not use controller target rotation as measured TCP rotation or infer zero angular tracking error.

The old geometry's I object_to_tcp cannot directly be used as a complete physical grasp transform: `T_WTCP @ inverse(old_object_to_tcp)` would make the desired object rotate 90 degrees and offset its center along world x, contradicting the current upright reference. This is a real registration gap, not a reason to change assets/controller or to silently guess a placement frame.

## Exact new registration and formulas

Keep old geometry and schemas byte-semantically unchanged. Add a separate new top-level `release_reference` descriptor in this new collector's protocol, generated during preparation, before original plan/assignment execution. Implement a pure helper in the new native_collection_grounding module and call it from new native_calibration_collection._protocol; reader independently validates its complete content against pinned sources.

Use column homogeneous vectors: `^A T_B` maps coordinates expressed in B into A. Freeze descriptor schema/version, source paths/hashes for skill_robot/motion_controller/top_grasp/backend/models/assets, source generation, frame convention, fixed nominal `R_WO=I`, source quaternion `_DOWNWARD` and its proper rotation, `.01` object contact offset, existing tool_to_tcp, exact profile/asset identities, eight ordered vertices, and formula version. Derive the quaternion matrix consistently from its source values; the displayed exact matrix is its analytic value. Tolerances are only existing floating representation tolerances, never physical qualification relaxations.

The newly explicit nominal complete grasp is:

```text
^O T_TCP = [ R_down, (0,0,.01) ]
            [   0,        1    ]
```

This is a registered nominal controller/profile reference. It is **not** obtained from actual later truth and not a certificate of achieved grasp orientation. No truth is injected into controller commands.

For the actually executed successful immediately preceding PLACE, verify exact original plan, binding, executed payload, step/action order, receipt, same episode/assignment, full H, and registered controller source. Let `p_tcp` be its exact target_pose (already a TCP-site target), and `R_cmd=R_down`. Then:

```text
^W T_TCP,p = [ R_cmd, p_tcp ]
^W T_O,p   = ^W T_TCP,p @ inverse(^O T_TCP)
R_O,p     = R_cmd @ R_down.T = I
c_O,p     = p_tcp - R_O,p @ (0,0,.01)
p_i       = c_O,p + R_O,p @ v_i
```

Use the registered lexicographic eight object-local vertices `v_i in product((-hx,hx),(-hy,hy),(-hz,hz))`. Each vertex retains its identity; do not minimize over vertex permutations or cube symmetries. Actual `x_i(t)=actual_center(t)+actual_rotation(t)@v_i` comes only from the retained physical originals for offline scoring. Rotation errors remain observable through all vertices even with a cube.

Apply the same transform to the **independently reconstructed, source-validated preceding PLACE correct reference**, yielding the RELEASE r_i. The prior PLACE reference's construction, original capture and fixed-reference provenance must be retained; do not simply set r=p because PLACE returned success, and do not substitute release-time observed object pose or an arbitrary desired orientation. Under the registered fixed PLACE reference, r(c) and r(t) are that same fixed reference (M=0); U and L remain computed per corresponding point and can be nonzero. If the independently correct PLACE reference is unavailable, retain UNKNOWN/infinity. This plan resolves the coordinate composition; it does not excuse a missing correct-reference construction.

Do not subtract tool_to_tcp again: PLACE's target is already the TCP site. If an offline derivation starts at a hand/tool pose, first `T_WTCP=T_WTool @ T_ToolTCP`; then apply the same inverse grasp exactly once. Both routes must agree in a software test. Top camera uses its already-registered optical-to-world transform; it is not another rotation to apply to world-coordinate PLACE targets. The marker transform remains the existing object/marker attachment convention and is used only when independently reconstructing object geometry from images.

Missing/wrong PLACE, unregistered source orientation, unregistered full descriptor, identity/episode mismatch, improper rotation, or altered offset is a stop/UNKNOWN, not a fallback to I or measured terminal truth. New protocol's complete canonical comparison already rejects descriptor mutation. Existing protocols without this descriptor are preserved as old/incomplete source, never silently upgraded. Regenerate only new future software fixtures and not-yet-run actual preregistration from current sources.

## Exact holding windows

Let d be actual dispatch step, a actual controller-return step, t=d+N registered full terminal step. States at integer steps describe completed physics effects; a duration of n steps uses n consecutive transitions and n+1 boundary states. Include boundary states wherever available from joined originals, and reject missing required per-step acquisitions. Do not confuse 120 samples with 120 intervals.

- LIFT: successful controller performs a 120-step built-in bilateral hold immediately before return at dt=1/240. Check original `contact_hold_s=.5`, controller step totals, original PHYSICS sequence and action success; a scalar alone is not proof. Holding domain is [a-120,t], with 120 controller-tail intervals plus all padding. Actual object lift ≥.05 m is measured against original pre-LIFT object height, not TCP height; maintain the original physical stability/holding checks throughout the required domain. No double-added tail.
- RELEASE: start the required stable/open domain at the actual successful open return a, not dispatch or first open command. Require t-a≥240 actual consecutive physics intervals, with actual released/contact/stability evidence under existing thresholds. This conservative start excludes opening latency. Include terminal. Do not count earlier opening steps as the 1 S tail.
- GRASP: p is the same capture's actual proprioceptive TCP position. The controller issues only a gripper command and steps; its TCP hold starts at d, so numeric TCP hold error uses [d,t], including controller closing and any padding. **Bilateral object holding is not required during initial closing**; that physical condition starts only after successful controller return a and persists through padding. Restricting TCP error to [a,t] would omit the controller's real hold interval. Do not invent target_pose or use return-time TCP as p.
- Other fixed endpoint motions retain terminal-only U/L/M evaluation. Existing required physical/safety/grasp conditions and raw per-step geometry G remain unchanged; this clarification does not turn motion-to-target transients into endpoint failures or claim all-path collision freedom.

All metrics use R91's original corresponding-point U+L+M then max, and original component max/G. No rotation-only measurement is fabricated where the raw lacks it. Required calibration UNKNOWN still forces qualified infinity despite finite diagnostics.

## Scope and verification

Only new native_calibration_collection.py, native_collection_grounding.py and native_full_horizon_originals.py may be edited for the descriptor/independent formulas; only their already scoped new grounding/reader test files may change. No product edits were made by this planner. Do not change old geometry/asset/config/controller/backend or expand physical observation schema.

Add three CPU cases, using case loops to avoid uncontrolled collection growth:

1. `test_release_full_transform_from_registered_place_tcp`: actual source quaternion/nominal transform yields c=p-(0,0,.01), R=I; all eight ordered vertices; alternate hand-pose route gives identical result with tool offset exactly once. Perturb actual object rotation with center fixed and verify nonzero vertex error. Confirm no actual TCP rotation is claimed.
2. `test_release_reference_rejects_missing_or_wrong_frame_sources`: absent/failed/wrong-order PLACE, old I-only descriptor, altered orientation/offset/source, duplicated tool offset and missing independently reconstructed PLACE reference remain UNKNOWN/rejected, never copied p into r.
3. `test_original_grasp_lift_release_hold_windows`: synthetic integer sequences cover LIFT a-120 through t and release a through t; deleting a required interval or counting pre-open time fails. GRASP TCP drift during closing is counted while missing bilateral contact before successful return is not mislabeled as hold loss. Terminal-only motion transient errors stay excluded from endpoint U/L/M; G and required checks remain.

Put reader cases in the original T3 test file for its not-yet-run GREEN (600 s inner/720 outer); any pure registration case in the existing grounding file is covered by original final-regression (900/1020). No extra stage, collect-only or repeated GREEN; R444's eight additional cases stay in final as planned. Run original static checks and final reviewer once at the previously specified point. Unexpected failure requires new Astra; no retries. Actual physics/render/model-call allocation is zero in this round. Original first-group budget, source freezing, late remaining stages and no-nine-group rule remain unchanged.

Acceptance is an explicit source-derived nominal full transform with strict independent joins and correct holding endpoints, software cases passing at their original stage, and unchanged UNKNOWN/actual limits. The corrected definition is not evidence that real PLACE/RELEASE succeeds. Report any missing reference as such rather than label-only completeness.
