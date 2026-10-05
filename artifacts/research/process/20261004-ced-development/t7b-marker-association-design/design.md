# Marker and requested-color association design

Design only. The assigned scope is immutable saved static640 RGBD from the colored-v2 capture and the initial settled frame of the one motion episode. No source/asset/profile/tracker edits, rendering, task action, model call, synthetic acceptance test, truth/instance input or motion retry occurred. Use the brainstorming skill's bounded exploration to identify the smallest future seam; implementation is not authorized by this document.

## Findings and intended result

Both static frames decode ID7 with the immutable native detector. At diagnostic tag-center pixel `(358,240)`, RGB is white `(255,255,255)`. The two frames contain 150 and152 red pixels respectively in one component≥8px. The existing `validate_grounded_colors` rejects the white center for the canonical requested-red instruction. These are saved-frame inspection results, not fresh online evidence or whole-object proof; exact checksums are in `saved-static-inspection.json`.

`OpenCVTargetTracker` samples target color from the grounded target pixel, requires that pixel to belong to one colored component, and rejects any interior hole in the target contour. That is appropriate for its existing unmarked solid-color scope. A decoded white/black tag and quiet area create intentional non-red surfaces; setting the grounded pixel to a rim pixel only avoids the center-color failure and leaves the hole rejection and center/extent semantics unresolved. Neither marking the tag pixels red nor filling arbitrary holes is valid.

`PoseMarkerRegistration` currently binds only dictionary/ID/marker size/asset hash. `RGBDObservation` binds frame/time/camera/source/episode/scene and bytes but contains no authenticated active asset or marker-to-object mapping. `PoseMarkerEstimate` provides ordered orientation and a single-frame pose estimate with null error/angular bounds; it is not an object identity registry. A caller supplying an arbitrary asset hash to that dataclass cannot establish attachment to a physical object.

The current fixed-S01 pipeline also hardcodes task IDs to `object`/`target_region`, and `native_action_contract` trusts a narrowly shaped `target_visible` fact for identity while always leaving geometric/motion bounds null. `top_grasp` registers only the original v1/v2 assets; colored-v2 is explicitly NOT_REGISTERED. Existing runtime source hashes bind software, not physical marker attachment, color-classification coverage, sensor calibration or method admission. These distinctions must survive any integration.

The intended future result is a typed, source-bound association between a decoded registered marker, the exact requested object/class/color and independently observed object support. It must retain separate outcomes for observed ID/color candidate, complete target identity/extent, geometric calibration and continuous motion. The current saved frames can exercise the candidate diagnostic; they do not supply all acceptance prerequisites.

## Approach and alternatives

Recommended: add one isolated marker-association module first, with typed registration/source context and observation-only results. Keep raw color, decoded marker/quiet area and outer-boundary support as separate measured regions. Integrate it into the existing native tracker only after source registration and negative-case review. Preserve the existing controller, canonical evidence gate and unsupported-bound behavior.

A color-only rim pixel plus existing tracker is cheaper but cannot explain the tag hole, distinguish a surrounding decoy ring or preserve marker/object identity. General silhouette hole filling would defeat the current occlusion guard. A truth/instance-backed mapper would trivially solve simulation identity but violate the online boundary. Neither is recommended.

## Trusted registration and frame provenance

Propose immutable `MarkerObjectRegistration` in NEW `vision/marker_association.py` with exact fields:

```text
schema_version: Literal['marker.object.registration.v1']
registration_id: str
pose_marker: PoseMarkerRegistration
object_id: str
object_class: str
expected_color: str
object_geometry_source_sha256: str
object_half_extent_m: tuple[float,float,float]
marker_to_object: tuple[float,...]  #16 homogeneous right-handed values
appearance_layout: MarkerAppearanceLayout
registration_source_hashes: Mapping[str,str]
admission_scope: Literal['DEVELOPMENT_ONLY','ACCEPTED_IDENTITY_SOURCE']
```

`MarkerAppearanceLayout` is a frozen measured/manufactured face layout: tag/quiet/colored-region polygons in marker coordinates, expected binary pattern/dictionary/ID, and source/version digest. It binds the v2 45 mm tag/60 mm quiet area/70 mm cube instead of an arbitrary inferred shape. For the current XML, exact marker-plane offset is sourced from the portable visual geoms and original object geometry, not frame physics. No zero or invented registration uncertainty is attached. Original empty/unverified fields reject construction; every identity/layout/geometry/source change changes the canonical digest. Deep freeze nested arrays/maps.

The registry loader must verify a reviewed local registration file plus all declared source/asset bytes against a trusted accepted registry digest. It cannot be a caller `VALID` flag, model output, marker ID alone, arbitrary path/hint, ad-hoc dictionary or alias. Current developmental registration can only be DEVELOPMENT_ONLY. A physical deployment needs independently verified attachment/size/color/object registration; there is no such accepted registry today. A copied ID7 affixed to a decoy remains possible without that source assurance. Single-view shape/color pixels alone cannot exclude a hidden different body behind a matching face.

Propose `MarkerFrameContext` with exact frame and runtime binding:

```text
task_id, object_id, object_class, target_region_id: str
instruction_sha256, task_target_sha256, context_hash: str
role_bundle_hash, registration_sha256, active_asset_sha256: str
observation_id, observation_sha256, episode_id, scene_id: str
camera_profile_sha256, calibration_version: str
plan_version, command_seq: int
```

Build this context at the genuine capture/task owner from the active source registry, current complete TaskTarget and current contract/checkpoint. Recheck at the submission boundary. Do not accept model/caller replacement IDs or rewrite a mismatching target to `object`. For the fixed-S01 scope, IDs must already match `object` and `target_region`; unsupported IDs fail closed. `object_class` and canonical requested color come from the exact supported whole instruction and frozen TaskTarget, not substring matching or the registration's expectation alone. Destination identity/color remains independently observed and bound; object association cannot confirm the green destination.

Camera profile digest covers source, width/height, intrinsics, transform, depth convention and calibration version. A crop/resize/resolution/pose/source/episode/scene/calibration change requires a separately registered current profile and fresh context; historical same-camera640 evidence is not automatically current. Verify the entire RGBD model again (including supplied validity mask == finite-positive depth), checksum and current supplied clock/TTL. Do not modify an old timestamp to make saved evidence fresh. Registration/context hashes are provenance, not calibrated bounds.

## Proposed isolated API and result

```python
def associate_marker_target(
    observation: RGBDObservation,
    registration: MarkerObjectRegistration,
    context: MarkerFrameContext,
    *, now: datetime,
) -> MarkerTargetAssociation:
    ...
```

No simulator/backend/model/truth/instance/gateway arguments. The function recomputes its results; callers cannot supply a preaccepted `PoseMarkerEstimate` or calibrated bound. A separately named offline replay mode may use the original capture time for diagnostics, must return DEVELOPMENT_ONLY, and cannot produce an online admission token.

Frozen `MarkerTargetAssociation` fields: `status` (`OBSERVED_CANDIDATE`/`UNKNOWN`/`INVALID`), reasons, immutable exact observation/context/registration/source digests, requested object ID/class/color and destination ID, pose estimate, observed color region samples/coverage descriptors, explicit outer-boundary/depth support, `whole_target_identity_status` (`UNKNOWN` initially), `extent_complete=False` initially, `geometric_error_bound_m=None`, `motion_bound_m_s=None`, `angular_velocity_bound_rad_s=None`, `stability_status='UNKNOWN'`, `admission_status='NOT_ADMITTED'`. No legacy `identity_confirmed=True` fact map is emitted by the initial module. Candidate means measured ID7 plus conditional visible requested color under the registered layout; it does not claim the complete target.

This split is intentional: strict known-marker observation plus nearby red cannot by itself be labeled complete physical object identity. The accepted identity-source path will require its own reviewed registry/frame provider and complete measured support; no input enum/status can activate it by itself. Core native action evidence continues null error/motion bounds even if a future identity-only source is accepted.

## Association procedure and strict negatives

1. Revalidate RGBD bytes/mask/calibration and exact context identity, freshness, active asset/registry/camera source. Missing source/registration/calibration/profile/context returns UNKNOWN; mismatching/tampered immutable identity returns INVALID. Static design replay stays excluded from online admission.
2. Call immutable `detect_pose_marker` at native resolution. Require exactly one expected ID, complete ordered corners and valid depth patches. Missing/foreign/duplicate/clipped/tiny/depth-unavailable tag stays UNKNOWN as in the detector. Never pick the nearest/largest duplicate, decode an enlarged old frame for acceptance, or silently switch tag/asset/profile.
3. Use observed ordered corners and the registered appearance layout to select candidate image regions. Homography is a selection hypothesis from observed marker geometry; it is not a calibrated physical body extent. Never overwrite color pixels. Retain actual observed marker pixels, observed white quiet pixels, requested-color pixels and unknown/conflicting pixels as separate masks with hashes.
4. Measure requested color on multiple separated exterior sides, not on the tag center or one cherry-picked pixel. Reuse the existing canonical color bands, including unavailable hue-boundary bands; insufficient/chromatic-boundary/ambiguous support stays UNKNOWN. A source-qualified fully observed contradictory color returns INVALID. Do not accept a red patch merely adjacent to a tag or ignore disconnected/conflicting supports. Destination color/region evidence is independently checked. Existing150/152 totals are diagnostics, not acceptance thresholds.
5. Distinguish the authorized printed marker/quiet regions from arbitrary missing object surface. A known decoded pattern can explain a non-red tag; measured white quiet area can explain its own pixels. Unknown pixels, holes or foreground outside that exact registered layout cannot be filled or explained by it. The combined support representation contains only actually observed samples; registration-based expected regions remain a separate hypothesis mask. Depth must be available on every region used for geometry and on the complete outer boundary/neighborhood. Clipped/partially missing rim, occlusion, foreign foreground or depth holes return UNKNOWN. Marker plane/size ±30% detector sanity does not certify object dimensions.
6. Full target extent requires complete measured outer contour/depth separation plus validated camera/depth/appearance error support and genuine known marker-to-object geometry. Current pose error bound is null, so reconstructed metric whole-object extents remain unavailable. No minimum ratio, synthetic noise or observed truth error is substituted for calibration. Color boundary/support policy requires a separately frozen validated source; until then only diagnostic coverage descriptors are emitted. A future acceptance test suite must establish strict side/boundary requirements before selecting numeric thresholds; this design does not manufacture those values from two passing frames.
7. Never assert lift/held/placement/stability from a decoded tag alone. Robot feedback may corroborate existing canonical holding/release facts but cannot move the object estimate or replace missing observations. A new frame clears stale association when marker/extent is absent or source changes; frame IDs alone do not constitute progress. Preserve exact complete conditions/targets/tolerances/timing/retry policies in later action grounding.

No full-object acceptance is possible from these two frames alone. The smallest honest first implementation is observation/candidate diagnostics plus qualified rejection cases; acceptance remains unavailable until registration and geometric support are independently qualified.

## Core integration needs after isolated review

`make_target_tracker` currently constructs the color tracker before checking instruction colors, and the cloud selected pixel serves both identity and geometry. A future marker path must separate **identity-support pixels** (observed red rim) from **geometric-reference pixels** (ordered tag plane/center). It must preserve the original task object/class/destination identity rather than mutate it to fit a marker. Do not use a rim point as the object center/TCP, or reuse the old unmarked grasp asset because the controller happens to be physically equivalent.

Future optional `marker_association` input to `OpenCVTargetTracker` must be recomputed/current-source verified, not an unvalidated dict. Keep existing `_geometry` semantics for unmarked targets and green destinations. Marker support should use a focused helper that understands observed tag/quiet/rim masks and rejects unexplained holes; retain canonical UNKNOWN on missing extent or calibration. Pose orientation can distinguish quarter turns when visible, but `_physical_stability_unknown` cannot be removed: marker endpoints still provide no interval-wide angular-speed bound. Missing tag must clear temporal history, not retain last pose or combine a new ring with old tag orientation.

`native_action_contract` must continue to compute the full max(timeout,expected) duration, frozen original ConditionSpecs and source-bound identity, and keep unavailable error/motion values null. Canonical `validate_evidence` remains the submission authority; action admission requires exact current context/versions/time, hard-stop checks and actual sensor bounds. Source hashes/typed association must not create another acceptance oracle. No root lifecycle record is marked VERIFIED_RESOLVED by association alone.

Marked-v2 grasp/profile/semantic acceptance is separate. `GRASP_CALIBRATION_ASSETS` and fixed-S01 semantic asset references currently exclude the new asset; those failures must remain until a reviewed versioned calibration/source registration is separately assigned. Any future role bundle must include the new association implementation, registration/layout bytes and exact asset in DEVICE source inventory, re-freeze all actual source/camera/profile/guard bindings and obtain the required model-role snapshot. Historical Max/bundle probes cannot cover new code/asset by implication.

## Exact proposed files, APIs and future test gates

First, separately authorized diagnostic implementation only:

- NEW `src/cloud_edge_robot_arm/vision/marker_association.py`: three frozen contracts and `associate_marker_target` above, source/profile checks, independent masks and strict candidate/UNKNOWN/INVALID handling.
- NEW `tests/test_marker_association.py`: qualified SOFTWARE_ONLY TDD tests and read-only static replay diagnostics. No mocked-success actual admission.
- NEW `configs/research/ced_marker_registration_v1.yaml`: explicit DEVELOPMENT_ONLY ID7↔object/class/red/layout/geometry/asset/source registration; no global activation/default change. Loading an unaccepted registry cannot issue actual admission.

Only after those reviews and a further root assignment, narrow potential integration files are `vision/execution.py` (typed context/source construction and optional native marker path before action), `vision/tracking.py` (measured marker-aware target support with unchanged unknown stability), `vision/online_intent.py` (whole-instruction extraction and separate observed-color samples), `vision/action_evidence.py` (source-qualified typed identity adapter, still null uncertified bounds), `vision/runtime_binding.py` and `configs/research/ced_roles.yaml` (new implementation/registry/asset inventory). If new grasp/source registration is ever approved, `vision/top_grasp.py` and `vision/task_semantics.py` require separate reviewed asset/profile mappings; they are not part of the first diagnostic module. Planner changes are unnecessary for local association; it must not send full registry/state/condition data remotely. There is no new executor/gateway.

Future test matrix:

| Input/counterexample | Required result |
|---|---|
| Genuine saved two static frames | Candidate diagnostics only; no fresh admission/bounds/physical success |
| Same white center with red rim | Separate color samples and geometry anchor; never call white red |
| Missing/wrong/duplicate ID7, duplicate registry ID or copied marker | UNKNOWN/registration rejection; no nearest-tag choice |
| Correct ID with wrong requested color, destination or object/class/TaskTarget/context | INVALID if qualified conflict; otherwise UNKNOWN; no ID rewriting |
| Arbitrary hole/rim break/foreign patch/foreground inside or outside tag-layout region | UNKNOWN; original pixel mask unchanged |
| Missing/clipped/foreign/tiny tag or invalid corner/center/rim/boundary depth | UNKNOWN; mask inconsistency fails full RGBD validation |
| Different actual object scale/marker attachment/asset/source digest | INVALID binding or UNKNOWN metric support; ±30% sanity not certified extent |
| Camera/source/episode/scene/intrinsics/resolution/calibration/profile changes | Reject old context/registration; no resize fallback |
| HSV boundaries162° and other shared bands, low saturation/value, disconnected same-color decoy | UNKNOWN ambiguity; no classify-either-boundary override |
| Mutated nested registry/layout/context or serialized hash rewrap | Original snapshot isolated; canonical source authority rechecked |
| Model claims VALID/bounds or caller passes accepted-looking fact dict | Cannot override typed recomputation/canonical action gate |
| Hidden tag after holding, old tag + new ring, new frame ID without improved valid conditions | Clear history/UNKNOWN; no inferred stability/progress |
| 90/180/270° tag observations | Ordered orientation differs; no interval speed/stability certificate |
| Software fixture association is passed into lifecycle/completion | Still cannot satisfy ACTUAL_SOURCE+canonical conditions or task acceptance |

Each future behavior change starts with a qualified failing regression and scoped GREEN/static/source freeze; actual testing remains separately scheduled by root. Existing frozen motion SUCCESS/9UNKNOWN is not rerun to make this design pass.

## Occlusion/holding policy

The frozen motion result motivates the policy but this task uses no new motion-frame processing. Holding hides the top tag in the existing physical arrangement. Missing marker evidence remains UNKNOWN; it cannot become object_stable, placement_stable, last-known pose, continuous angular velocity or resolved recovery. A second view/other registered marker placement is a future observability change, not an automatic fallback.

An existing RETREAT/OBSERVE can only run if it has its own current independent valid action submission: robot connected and no estop/collision/cancel, exact active versions/current context, complete original conditions, current geometric/motion bounds for the action horizon and existing safety/transaction guards. Holding geometry may be unobservable, so retreat can itself be unavailable. The design must not infer permission from teacher SUCCESS, controller ACK, TCP endpoints, stale tag pose or the need to recapture. Existing passive reobservation is bounded by the task-wide persistent budget/deadline and cannot reset with event IDs. If a current proof cannot authorize movement, stop/wait under the existing router; do not dispatch retreat to obtain the proof that would authorize it. LOCAL_RECOVER remains disabled. No motion/capture/retry is proposed for the frozen episode.

## Delivery status

This document and `source-hashes.json` freeze the read-only design basis and two saved static inputs. `saved-static-inspection.json` records the concrete white-center/red-rim counterexample. No implementation or acceptance is claimed. Missing accepted object-registration/frame provider, complete measured extent/error support, marked grasp profile and continuous angular-motion source are explicit blockers; software hashes and a source scope enum cannot fill them. Ready for root design review, then wait for a separate assignment.
