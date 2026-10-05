# DEVELOPMENT_ONLY marker association handoff

The isolated diagnostic implementation is complete and frozen for independent review. Two genuine saved static640 frames produce OBSERVED_CANDIDATE: a strict registered ID7 plus a measured requested-red ring under the supported whole instruction. Every result always retains whole identity UNKNOWN, extent false, all geometric/motion/angular bounds null, stability UNKNOWN and admission NOT_ADMITTED. This is not native evidence, actual object-registration acceptance, fresh online evidence or physical task success.

## Scope and interfaces

Only three new files are owned:

- `src/cloud_edge_robot_arm/vision/marker_association.py`
- `tests/test_marker_association.py`
- `configs/research/ced_marker_registration_v1.yaml`

No existing tracker/execution/native/top_grasp/default/roles/v1/v2/motion source or asset was edited. No model/network request, capture, renderer or controller action occurred. The original motion episode's nine UNKNOWN results remain immutable and are not inputs to this implementation's tests; the only motion-package image used is its initial settled static frame.

Public APIs:

```text
load_marker_registration(path: Path, *, expected_registry_sha256: str, root: Path) -> MarkerObjectRegistration
camera_profile_hash(observation: RGBDObservation) -> str
marker_frame_context(observation, registration, *, task_id, task_target: TaskTarget,
                     instruction, context_hash, role_bundle_hash, active_asset_sha256,
                     plan_version, command_seq) -> MarkerFrameContext
associate_marker_target(observation, registration, context, *, now: datetime) -> MarkerTargetAssociation
replay_marker_target_development(observation, registration, context) -> MarkerTargetAssociation
```

The replay is explicitly named and marked DEVELOPMENT_REPLAY. It uses the original capture time for this excluded diagnostic without rewriting timestamps. The ordinary API is LIVE_DIAGNOSTIC and recomputes supplied-clock age (0..5 seconds); neither mode can issue admission.

Registration is deep-frozen and source-bound. The first version supports only the exact existing colored-v2 asset/ID7/45 mm tag/object cube/red/target_region/70 mm cube/known 35.05 mm marker attachment/60 mm quiet layout. ACCEPTED_IDENTITY_SOURCE and any changed object/layout/attachment/size binding reject, rather than creating a future accepted path. Loader validates the expected registry file bytes and current source/asset hashes; association rechecks those hashes each call. Symlink/escape/unavailable source cannot validate. Required source inventory includes the actual association module, immutable detector, RGBD validator, canonical instruction/color source, immutable asset builder and colored asset.

`MarkerFrameContext` freezes the complete TaskTarget payload and all ID/class/destination, instruction, frame/checksum/episode/scene/calibration/camera, active-asset/registration, version/sequence and context/role-hash carriers. Association recomputes instruction and target equality. These carriers demonstrate internal binding consistency; they do not prove that the caller is a genuine accepted capture/RoleRuntimeBinding provider or that a physical tag was attached correctly. Those source/admission seams remain unavailable; scope cannot be promoted by a caller flag or enum.

## Measured support versus hypotheses

The immutable decoder sees only revalidated RGBD and known marker registration, with strict native-resolution ID checks. Requested color uses the existing whole-sentence allowlist and exact `_matches` color classification, source-hashed as an isolated private helper dependency. No remote model color claim or substring parser is used.

The diagnostic requires one observed requested-color ring contour with one central hole containing every decoded tag corner. Duplicate/foreign/missing tags, extra same-color components, broken rim or unexplained topology return UNKNOWN. This topology only proposes an association; it does not confirm every expected face pixel or complete physical shape. Registered polygons produce separate `region_hypotheses` (tag/quiet/face), never filled red or observed silhouettes. `support_masks` contain only measured requested-color samples, available tag depth samples and observed neutral quiet samples. Masks are immutable bytes; descriptors are recursively frozen. No arbitrary color-hole filling occurs.

All layout regions require available depth and remain interior to the image. The quiet region uses median3×3 interior patches and the immutable detector's existing 2 mm plane **sanity** limit to reject gross foreground despite intact marker/color. The descriptor explicitly says this is not a calibrated bound; outer boundary remains unverified. This sampling/sanity policy is conditional diagnostic support, not comprehensive occlusion detection or measured sensor-error coverage. No numerical coverage ratio is used to admit a target.

`saved-static-results.json` preserves exact masks/hypothesis hashes and coverage. Colored static frame yields150 requested-color pixels and max quiet patch residual0.00106647 m; motion initial static yields249 canonical-color pixels and residual0.00001990795 m. The earlier design inspection used its separate HSV saturation/value diagnostic and counted152 pixels in the motion initial frame. The current249 is the exact existing canonical `_matches` policy, which admits darker pixels under its value>.1/saturation>.25 rules; it is not a reclassification of the original saved pixels or a new acceptance threshold. Both original frame/checksum/capture times remain unchanged.

## TDD and verification

`red-initial.log`: 20 qualified absent-module failures before implementation. After initial implementation, `green-first-attempt.log` retained one test exception-type mismatch (dataclasses.replace correctly raises ValueError for init=False fields, while the test expected TypeError); the test expectation was corrected, not the invariant. `red-asset-binding.log`: six qualified changed-object/attachment/layout failures before the exact fixed-asset guard. `red-mask-separation.log`: one failure before projected masks were separated. `red-quiet-foreground.log`: one failure with an intact decoded marker and finite-positive quiet foreground before diagnostic plane sanity. All RED evidence is preserved.

Final37 new tests pass in `green-foreground.log`. They exercise the two saved static candidates, immutable nested registration/result payloads, explicit replay/freshness, unsupported whole instructions/wrong requested color, exact object/class/destination/context/frame/asset/source/camera/version tampering, accepted scope and forged invariants, broken rim/missing tag/wrong color, invalid mask/depth hole/quiet foreground, qualified decodable ID8 and duplicated ID7 patterns. Synthetic mutations are SOFTWARE_ONLY negatives; they are not rendered or treated as physical acceptance.

Final scoped command:

```text
.venv/bin/python -m pytest -q tests/test_marker_association.py tests/test_pose_marker_evidence.py tests/test_pose_marker_assets.py tests/test_rgbd_top_grasp.py
```

`green-final.log`: 91 passed, 9.33 s. The old marker/asset/grasp regressions are CPU-only and include passive compiled-model equivalence, not rendering. `ruff-final.log`: two owned Python files pass. `mypy-final.log`: new module passes. No full suite, model call, renderer test or actual episode was run. Earlier lint formatting and a NumPy reshape type inference issue were corrected before final verification; bound config source hashes were refreshed to the exact final module bytes.

The first artifact freeze stopped during environment metadata lookup because distribution name `opencv-python` was absent although installed cv2 was available; `freeze-first-failure.log` records it. Environment inventory now uses the actual imported modules' versions, without installation or source changes. This was an artifact-only correction, not a simulation/test acceptance retry.

## Immutable package and limitations

`source/` and `source-hashes.json` freeze39 files: three new owned,20 read-only source/test/asset references and16 saved fixture bytes (the two static frames plus old detector's320/640 replay fixtures). Manifest SHA256 `a3e6b97a1a06651bde41cf64260d4009e9e9bd7e03e812aeb9668ff24e259614`. `ownership.json` lists scope; `review-package.diff` contains only the three new files against their absent task-start baseline. `freeze.log` verifies archive/live/AST identity and unchanged v1/v2/motion manifests. No more writes to the three owned files are planned during independent review.

The new registry is excluded development configuration and is not referenced by defaults or ced_roles. It registers no grasp profile and activates no pipeline. Current full-object extent/identity, genuine accepted frame/physical-object registry, calibrated error/motion source, marked grasp asset and continuous angular observability remain unavailable. The diagnostic neither produces legacy target_visible acceptance facts nor calls canonical action/lifecycle producers; native submission remains unchanged and unavailable without genuine bounds. It cannot resolve a recovery, infer motion from ACK/step-start, or turn hidden markers into stability. Holding occlusion still requires UNKNOWN/stop/wait, with any future retreat or observation independently authorized under existing submission and budget guards.

Ready for scoped independent review. No real-role or physical acceptance is claimed from these software checks and saved diagnostic results.
