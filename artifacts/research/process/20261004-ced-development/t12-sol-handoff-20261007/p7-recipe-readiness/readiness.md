# P7 recipe readiness — accepted R91 mapped to current producers

Status READINESS_ONLY; actual gpt-6-astra. No implementation, imports, tests/static, actual data, Git/network or agents. P5/P6 final interfaces are pending; no active P5 source is pinned here. ROOT accepted R91 for staged implementation, explicitly not actual/native qualification. This mapping reuses that decision and does not add a new recipe or weaken unsupported paths.

## Seven existing physical skills versus eight registered skills

`datasets/rgbd/teacher.py:194–220` NORMAL runs exactly MOVE_ABOVE→APPROACH→GRASP→LIFT→OBSERVE dwell0.5S→MOVE_TO_REGION→PLACE→RELEASE→OBSERVE dwell1.2S. That is seven physical skills plus two observations; no RETREAT. It directly invokes `MuJoCoSkillRobot` using simulator truth for targets. These truth targets and direct calls cannot become online grounder calibration or a claim that the teacher already runs SkillExecutor/Shield.

R91's proposed registered order is MOVE_ABOVE→APPROACH→GRASP→LIFT→MOVE_TO_REGION→PLACE→RELEASE→RETREAT, with registered internal/observation holds and final stable verification. RETREAT implementation already exists at `skill_robot.py:232–250` and deterministic grounding covers it; collector inclusion, fullH and qualification are still new R91 production. ROOT activation must bind this single exact order to the actual original contract. If the original contract differs, resolve registration before execution; never insert/reorder skills while collecting. HOME remains optional/excluded per original rule; OBSERVE/VERIFY are evidence operations, not extra calibrated physical skills.

Old teacher literals: move-above truth(x,y,0.16) timeout8s; approach truth(x,y,z+.01)8s; grasp1s; lift height.10/8s plus internal hold; region truth(x,y,.16)10s; place truth(x,y,halfheight+.01)8s; release1s. They describe old offline behavior only. Current true worker `prepare_worker_step` preserves original step timeout/expected/retry, unlike legacy `resolved_step` which rewrites motion timeout10s and grasp/release1s. No final P7 numeric horizon can be claimed until actual original contract/owner duration is bound.

## Exact source-backed payload recipe

Use actual same-capture grounder inputs `g=grasp_tcp`, `d=destination`, `support=support_height_m`, `u=online.robot_state.tcp_pose`. Current worker policy is `c=.10m`, `hmin=max(.16m, original.minimum_safe_height)`, `v=min(.15m/s, original.max_tcp_velocity)`, `a=.5`; freeze exact policy and source hashes. The original object/region IDs are used, not invented IDs. `owner_registration._resolved_parameters:780–826` is authoritative; original conditions remain in the durable requirement record even when the executor's compiled view clears inline lists. Bind full canonical original/compiled contract JSON and hash, step identity, timeout, expected duration, retry, all conditions and Shield result. If Shield changes payload, recompile/rebind before true dispatch, never retain old reference.

### MOVE_ABOVE

Payload: object_id=original.target.object_id; target=(g.x,g.y,max(hmin,g.z+c)); tcp_velocity=v; acceleration=a.

Reference: p=compiled TCP target; r=offline registered object_to_tcp grasp + same clearance rule; G/U/L/M required.

Full S accounting: B; early success padded to fixed terminal.

### APPROACH

Payload: object_id; target=g; tcp_velocity=v; acceleration=a.

Reference: p=exact contact TCP target; offline r reconstructed from full object pose and registered grasp transform; drift explicit.

Full S accounting: B; no next GRASP before terminal.

### GRASP

Payload: object_id only; NO fake target_pose.

Reference: p=actual captured proprioceptive TCP pose/registered contact points; offline r=correct object contact TCP; true bilateral contacts and fresh online holding conditions separate.

Full S accounting: B; existing _duration_steps floors timeout/dt, new complete horizon must ceil and account residual hold.

### LIFT

Payload: height_m=z_target-u.z; target=(u.x,u.y,max(u.z+c,hmin)); tcp_velocity=v; acceleration=a.

Reference: fixed compiled endpoint M=0 applies only reference, not carried object; full geometry/whole object and true lift score remain.

Full S accounting: B + I_lift + P_lift; I=ceil(.5/dt) already inside skill; P=ceil(.6/dt) current worker POST_HOLD, separate.

### MOVE_TO_REGION

Payload: region_id=original.target.target_region_id; target=(d.x,d.y,max(hmin,g.z+c)); tcp_velocity=v; acceleration=a.

Reference: fixed exact region endpoint; G/U/L and contact/whole-body points, no body velocity zero claim.

Full S accounting: B; preserve gripper holding.

### PLACE

Payload: region_id; target=(d.x,d.y,d.z+g.z-support); tcp_velocity=v; acceleration=a.

Reference: exact PLACE compiled payload + registered full grasp transform needed by RELEASE; complete object geometry, not center-only.

Full S accounting: B; fixed complete terminal before release.

### RELEASE

Payload: {} from current deterministic grounder; no synthetic target parameter.

Reference: new R91 whole-body reference from exact executed PLACE binding and registered grasp rigid transform; eight target/object vertices with rotation; release/no-contact/inside/stability separate.

Full S accounting: B + R_release, R>=ceil(1/dt) complete registered post-release stability window BEFORE RETREAT; command open result is insufficient.

### RETREAT

Payload: distance_m=z_target-u.z; target=(u.x,u.y,max(u.z+c,hmin)); tcp_velocity=v; acceleration=a.

Reference: existing skill/payload support but absent old teacher; fixed endpoint plus body/terminal conditions.

Full S accounting: B + T_terminal when final; T=ceil(1.2/dt) existing worker final observation, not RELEASE retroactive evidence.

## Full horizon without omission or double counting

For each action record a `HorizonBreakdown` containing original/compiled timeout and expected durations, original effective owner-required duration, exact dt, motor/base nominal budget, already-included flags, intrinsic hold, post-effect hold, release stabilization, final dwell, actual operation steps and padding. Let B=ceil(max(original timeout, original expected, compiled timeout, compiled expected)/dt); effective owner duration must cover the full resulting action interval. When owner duration already includes additions, do not add them twice: whole steps are max(B + individually not-yet-included required additions, ceil(owner full-required duration/dt)). If a source field already expresses a complete interval, explicitly identify it and subtract no physical operation. Preserve both requested and realized durations; do not silently mutate original timeout or a receipt after capture.

- LIFT skill already executes ceil(.5/dt) contact-hold steps after controller movement (`skill_robot.py:157–181`). It proves only TCP lift/bilateral contact at that layer; independent evaluator still requires actual object rise>=.05m and stable held interval>=.5S. Worker separately executes `LIFT_OBSERVATION_HOLD_S=.6` (`execution.py:91,1385–1399`). The teacher's extra .5 dwell is a third, different old path: do not substitute it for worker .6 or append it blindly to the new worker recipe.
- Worker final skill separately receives ceil(1.2/dt) TERMINAL steps (`execution.py:1401–1410`). With RETREAT final, those steps occur after RETREAT. They cannot satisfy a claim that RELEASE was fully stable before RETREAT. R91 already requires a new explicit release stabilization interval>=1S before advancing; keep final1.2S separately. If registering a longer release interval, freeze it in advance and account it once.
- Controller may return early; current controller and gripper duration conversions can floor(timeout/dt). R91 horizon session must pad successful actions through the fixed ceil terminal with the existing actuator hold, without new IK/pose writes/control decisions. Original failure/expired/partial action remains failure/infinite; no forced success frame. Retain original result and later completion separately.
- Never let the next action, wait catch-up or unrelated simulator step contaminate an action's complete registered terminal. TTL applies at genuine consumption/submit/effect gates; no invented rule requiring an old frame revalidated as native on every physics step. Original D deadline and hard stop remain checked through P5/P6.

Current config dt=0.0041666667S (`configs/phase9/mujoco.yaml`), not an assumed exact1/240. It is below the .005S maximum gap. As a **conditional arithmetic example only**, if all six motion B values are10S, grasp/release B1S, owner requirements no longer, release extra1S, worker postlift.6S and final1.2S retained, the group needs6*2400+2*240+120+144+240+288+120settle=15,792 physics steps, 65.8000005264S. This is not a frozen contract, capture count or observed run. Per-step RGB-D plus initial/boundary extra captures must be counted separately, along with any registered WAIT; actual full inventory must still fit20,000 allocations/80S. More original duration or waits can invalidate the cap; STOP before run, not shorten H. No disk/runtime estimate follows from this arithmetic.

## Full rigid points and independent scoring

Preserve full geometry G: all eight corners from registered half extents, every registered contact point and object-to-TCP lever point; compare transforms with full rotation, not center error (`native_geometry_calibration.py:80–94`). R91 C=max(G,U+L+M), U=|p-r(c)|, L=|x(t)-p|, M=|r(t)-r(c)|, evaluated for every required control point and all required holding samples, is explicitly the new JOINT_COMPLETION_V2 metric. Old e/v fields stay unchanged; M is not velocity or hidden geometric noise. Fixed-reference M=0 is allowed only from exact immutable target semantics, not object immobility.

GRASP p comes from actual proprioception at the registered capture; bilateral contact and fresh RGB-D holding remain independent evidence. RELEASE target object transform is derived from the exact executed PLACE TCP transform and registered grasp object-to-TCP transform (T_world_object_target = T_world_tcp_place * inverse(T_object_tcp)), with exact orientation/units/frame conventions and source binding. Full PLACE orientation must include the controller's registered orientation, not merely xyz. Missing/inconsistent transform is unsupported, not estimated from a few visible pixels. Truth r/x and object/contact geometry labels are offline only, not inputs to online target choice or permission.

Independent `CompletionCriteria` requires object rise>=50mm, hold>=.5S, placed stable>=1S, sample gap<=.005S, linear speed<=.02m/s, angular speed<=.5rad/s; placed also requires open gripper/no finger contact/whole object inside region and bottom within.005m of table. Preserve those existing rules and all safety checks. A commanded lift, TCP rise, gripper-open return, ACK or C<=.01 alone is not full physical success.

## Unique executor and actual observation seams

Collector must use the real grounder and existing SkillExecutor/SkillRegistry/MuJoCoSkillRobot/motion controller plus Shield; TEACHER_COLLECTION is a fresh app-owned scope from R91, not generic allow_uncertified or online native permission. Reuse teacher only for finite teaching order. `raw_recorder_v3.execute_attempt` wraps that same sole executor and preserves action spans; backend operation source covers RESET/CONTROL/PHYSICS/COMMAND/CAPTURE. Recorder owns the single operation observer. R91/P6 must integrate in that existing stream, no second recorder/physics stepper. Existing audit observer exceptions are swallowed/recorded, so it is not a motion-veto hook. The accepted R91 pre/post operational guard must use the actual execution/horizon seam, preserve stop behavior and partial effects; its P5/P6 private interfaces are not yet frozen.

Capture must share backend/episode and satisfy `capture_step==dispatch_step`; render/decode may consume D while S stays frozen. If cloud wait advances S, take a real new capture and compile/Shield the exact payload again under original D budget. Operational sidecar must be produced concurrently, bind every original raw SHA/allocation to event/owner IDs, and retain old UTC reader conclusions. Old teacher/RawV3 monotonic+UTC pairs cannot be relabelled as OC1 D.

## Nine-component preregistration checklist

Before any group is observed, freeze:

1. Schema/metric/recipe versions; ROOT accepted design/source digests; factory timing mode CHECKPOINT_D_FULL_S, age_S=0, coverage=.9, 10mm threshold, max gap.005; explicit legacy/external/FULL_FUTURE_D_REQUIRED exclusion.
2. Exactly nine assigned group IDs and one attempt each, scene specifications/seeds, component/ancestor graph and original-data fingerprints, asset/geometry/camera/intrinsics/resolution/visible marker/noise/controller/grounder/role sources and versions. IDs or seeds alone do not prove independence. Existing component rule merges shared ancestor or fingerprint; scene hash is a fingerprint, so nine repeats of one scene do not become nine components. Shared asset/config are domain metadata, not permission to erase real shared episode/scene ancestry.
3. Eight skill identities and fixed order, original and compiled payload policy, real owner-required horizons, per-action breakdown, all control points/transforms, exact PLACE→RELEASE lineage, LIFT/RELEASE/terminal hold scopes and condition definitions. Concrete payloads from unseen captures are not invented at prepare: freeze deterministic recipe, then persist each exact produced payload with observation lineage before dispatch.
4. Fresh own app/job/attempt/lease/OC1/P5/P6 source factory and RESET registration; allowed boot/thread/namespace/suspend/restart domain; raw allocation/capture/action/physics/request/WAIT/partial/effect inventories and hash manifest specification; true online versus offline-truth separation.
5. Per-group conservative derived S/step/frame totals and resource guards: <=80S, <=20,000 physics/RGB-D allocations as accepted, <=5,400 D seconds development collection, <=32GiB actual output plus failure flush headroom. These are resource caps, not future H_D/Tcap proof. All nine max288GiB/13.5h is a bound, not reserved space or forecast; recheck current disk before run. Freeze serial renderer, failure/stop rules and complete unexecuted suffix denominator.

Group score is the maximum of every required action/control point/frame/terminal/hold and each joint C. Missing/failed/UNKNOWN/partial or unexecuted required item makes that assigned component infinity. Aggregate components first, then k=ceil((n+1)*.9); n9 gives rank9/max. Eight separate .9 action bounds do not imply .9 whole chain. All nine assigned components remain in the denominator even when the first fails; group001 is not a discardable pilot. First full actual group + independent readout before deciding whether the registered remaining eight may run; no replacement/retry. A finite<=10mm joint bound is empirical domain support, not unconditional safety.

## Existing, proposed and pending

Existing: seven-skill truth teacher, eight robot skill implementations and deterministic payload branches, original physical evaluator, sole executor/recorder/backend stream, old full-rigid geometry and component arithmetic. Proposed in accepted R91 but not present at this read: native_completion.py, native_horizon.py, native_completion_calibration.py, collection module/CLI/config and v2 certification/three-consumer dispatch. Original plan already owns these changes; no new scope is created here.

Pending P5/P6 freeze: true live issuer/windows and typed AGE_CLOSED/HARD_OPEN semantics, lease/transaction/dispatch gates, current D/S operation lineage, restart/suspend capability domain, source activation generation. Follow P6 readiness's concrete seam decisions without editing those active sources. P7 CPU can be separately scheduled under accepted budgets; this readiness grants none. Actual requires reviewed implementation, sources/lifecycle and registered recipe/inputs. Native hot-path qualification and three consumers remain P8/R91 Task4, physical success and final T12 normal-chain/32episode requirements remain distinct. No new impossibility was established; the concrete remaining production gaps are the ones already recognized by R91, plus exact bookkeeping identified here. Do not substitute all-UNKNOWN/all-STOP for the intended positive normal chain.
