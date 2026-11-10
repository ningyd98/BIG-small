# R547 Bounded Native-Point Component Association Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task. Steps use checkbox (`- [ ]`) syntax. Existing user authorization covers this bounded repair; no extra review, architecture approval or sub-agent dispatch is required.

**Goal:** Allow an approximate native target point on nearby achromatic background to associate with one complete, explicitly color-consistent local component, while preserving the raw native prediction and all existing geometry/safety gates.

**Architecture:** Insert one target-only CPU helper between the unchanged normalized-coordinate conversion and existing ground_observation. It can propose a bounded interior pixel from RGB components; the existing metric-depth, top-grasp, OpenCV tracker and freshness checks still determine whether any draft may proceed. Destination points and direct colored target points are not shifted.

**Tech Stack:** Existing Python 3.12, NumPy/OpenCV/Pillow, pytest; unchanged Molmo2-ER BF16 runtime through R545 launcher.

**Spec:** R547 request.json and R542 selected architecture. This plan explicitly supersedes R542's original no-pixel-refinement restriction only for the narrow target association below. Actual planner_model: `gpt-6-astra`.

## Global Constraints

- Verify all 13 request inputs before implementation; matched during actual Astra planning. All 26 native-01 raw-manifest files also matched (880711 bytes). Preserve native-01 report exit2 and all original bytes permanently.
- Native parsing, image_id, normalized_1000 mapping, original RGB/depth/checksum/time and SDK/model assets remain unchanged. No rerendering or retiming archived observations.
- Do not lower support relief, depth validity, calibration, top-grasp/3x3, tracker uniqueness, contour, outer-ring or TTL gates. No fabricated confidence/depth-error bound. No global-nearest search or repeated widening until an object is found.
- Scope remains fixed-camera, colored upright rigid boxes under existing MuJoCo calibration. New rescue supports only an explicit narrow color/object descriptor grammar stated below; it is not generic object recognition.
- Modify only grounded_planner.py and its test; create one association helper and focused test. No changes to tracker.py, planner.py, observations.py, top_grasp.py, native provider, CLI, runtime or SDK.
- No external upload/public push in this round. Keep raw local/ignored; derived plans/reports and explicitly reviewed code may be locally committed. No cloud/hardware calls.

## Review Focus

1. A point near two supports must reject before depth/color filtering can conveniently select one.
2. A single wrong-color or unsupported-semantic candidate must not replace the requested target.
3. Small, cropped, occluded, boundary-adjacent or depth-incomplete components must remain rejected, even if their center looks plausible.
4. Native and associated pixels must have distinct provenance; original normalization and timestamps cannot change.
5. A successful archived static replay must not become a fresh integration PASS, or reset the consumed model budget.

---

## Original failure and actual read-only diagnosis

native-01 completed **1 load / 2 generation starts / 2 completions**, zero paid calls/hardware, then failed closed with `selected target pixel is not a raised visible top surface`. Queries took 1.21838486 s and 0.837593536 s end-to-end. Target raw `(562,458)` maps to `(179,109)` on 320x240; destination `(408,302)` maps to `(130,72)`. Published coordinate scale remains 1000; this is not evidence of a scaling bug.

The planner viewed the actual RGB and checked RGB/depth bytes against the immutable request. At `(179,109)`, RGB=(225,225,225), world z=-0.00126514435 m and relief=-0.00154471397 m: the existing gate correctly selected table and rejected. The red component has bbox `(172,113,14,14)`, area195 at RGB peak-to-peak>35, centroid `(178.5333,119.5333)`, minimum separation4 px from the native point. Its deterministic deepest interior pixel `(179,119)` moves10 px and has world z=0.0700737476 m, relief0.0700452328 m. The green region is >=39.115 px from the native target and outside the proposed19 px neighborhood.

Without altering archived timestamp `2026-11-10T00:46:55.387268+00:00`, a **static-only CPU diagnostic** passed the existing ground_observation and original tracker._geometry target/destination calculations at `(179,119)/(130,72)`. This diagnostic deliberately did not call live tracker constructor/freshness or produce a pipeline contract; its uninitialized tracker shell was used solely to execute the unchanged stateless geometry calculation with support_z and no depth error bound. This is not a production path or permission to bypass constructor/TTL. Top patch span0.0030210 m and fingertip clearance0.0150226 m passed existing thresholds. Full extent remains false and depth error bound remains null. Tracker's existing lower chroma threshold includes196 pixels; the new nomination mask's195 pixels do not replace tracker segmentation.

The evidence supports a bounded **spatial-association hypothesis**, not verified semantic accuracy or a calibrated model localization-error distribution. The fixed search bound below is a development policy chosen conservatively for a small component, not a probability/confidence or metre error bound. Another near component can still be the wrong real object; explicit descriptor color, uniqueness and existing geometry narrow this risk without claiming physical acceptance.

The earlier offline invocation attempted a nonexistent module-level world_point import. The actual API `observation.world_point(pixel)` was used successfully here; correcting that round-local command is authorized, with no production API change.

## Bounded interfaces and algorithm

Create `src/cloud_edge_robot_arm/vision/point_association.py`:

```python
@dataclass(frozen=True)
class PointAssociation:
    pixel: tuple[int, int]
    evidence: dict[str, object]

class PointAssociationError(ValueError):
    # Carry .evidence so rejected nominations preserve native pixel/candidate reasons.
    ...

def associate_target_point(
    observation: RGBDObservation,
    native_pixel: tuple[int, int],
    *,
    target_phrase: str,
) -> PointAssociation: ...
```

`native_pixel` is already an original-image pixel; helper never sees normalized units. It uses only bound observation RGB/raw depth and explicit task.target_phrase. Never consult raw output label, scene truth, dataset labels or future outcomes. New evidence schema/version `bounded_local_component.v1` includes status, observation checksum, RGB/depth hashes, original native pixel/world measurement, selected pixel, radius/window, all local candidate count/bboxes, candidate area/mask hash, selected RGB/HSV, displacement, descriptor-color status, policy parameters and rejection reason. Evidence contains no success probability.

**Pinned policy, applied once:**

1. Validate integer in-bounds native point and require its existing positive finite raw depth/valid-mask sample. Invalid native depth rejects before nomination; no hole filling. Existing adapter performs its normal source/profile/context/freshness prechecks before calling the helper.
2. Decode original RGB without resizing. For direct points with `max(R,G,B)-min(R,G,B) >=35`, keep native pixel exactly unchanged. For supported explicit descriptor grammar below, reject direct pixel of a different declared hue; do not move it to another object. For unsupported descriptors, existing direct colored-point behavior remains unchanged; **rescue** is prohibited.
3. Rescue is available only for a low-chroma native pixel (peak-to-peak<35) and task.target_phrase matching, case-insensitively, exactly `^(red|green|blue|yellow) (block|box|cube)$` after stripping outer whitespace. This narrow grammar prevents interpreting negated/ambiguous phrases as a color instruction; no schema/default phrase invention. OpenCV HSV hue bounds are conservative development bins: red H0..10 or170..179, green35..85, blue100..130, yellow20..34. All rescue-component pixels must match the declared hue and satisfy RGB peak-to-peak>35. Unsupported color/phrase yields explicit rejection, not guessed semantics.
4. Set `radius_px=min(24,max(8,round(0.08*min(width,height))))` once (19 on this320x240 frame). Form the square native-centered ROI intersected with the image. Compute 8-connected components of **all** pixels with RGB peak-to-peak>35; full-frame labels may be computed solely to detect actual component extent. A local candidate has area>=8 and at least one pixel within Euclidean radius. Count every such local component, irrespective of hue or depth validity, before filtering. Require exactly one. Do not choose the nearest, rank by model score, discard an invalid competitor, or search outside this fixed radius.
5. Require that sole component's full bbox lies strictly inside both the untruncated ROI and image boundary; any touching/crossing of either boundary rejects. Reject a cropped ROI that reaches the image boundary in a way that prevents this containment check. Require hue consistency for every component pixel, every component raw-depth/mask sample positive/finite, and complete 3x3 interior at the selected pixel. No erosion/dilation filling, component merging or removing troublesome pixels to make these checks pass.
6. Choose a point by maximum OpenCV Euclidean distance transform of the full binary component (`DIST_L2`, `DIST_MASK_PRECISE`); for equal maxima choose the point with minimum squared distance to native, then row(y), then column(x). It must lie within Euclidean radius, have max-interior-distance>=2 px and all nine 3x3 mask pixels present. This yields `(179,119)` for the archived component. Do not retry alternate pixels if later depth/top-grasp/tracker tests reject.
7. This only nominates RGB support; immediately pass the resulting target pixel and unchanged destination pixel to existing ground_observation and then the unchanged normal OpenCVTargetTracker constructor. Those original global color-uniqueness/contour/outer-ring checks remain decisive, including duplicate same-colored objects outside the local ROI. Existing freshness/context checks still run before cloud and contract. No rescue of an invalid destination.

Modify only `grounded_planner.py` to import/call helper after both native results pass binding/conversion. Store `native_original_pixel_target` and `native_original_pixel_destination` before association, `associated_pixel_target` and detailed `target_point_association` after; retain native_results normalized/raw hashes. Existing `original_pixel_target` remains the geometry-input original-image coordinate and must be explicitly documented as associated when applicable, not model output. Attach nomination evidence on failures too; do not falsely promote helper success to geometry readiness. Add helper source path to this adapter factory's current source-hash inventory. No cloud prompt or trust-field change is needed.

## Task 1 — Negative-first CPU association and integration

**Files:** Create `point_association.py`, `tests/test_molmo_point_association.py`; modify `grounded_planner.py`, `tests/test_molmo_grounded_planner.py` only.

- [ ] **Step 1 — Write meaningful RED tests.** Use synthetic source-backed RGBD fixtures; no raw archive in public tests. Test unchanged on-component colored point; low-chroma point4px above a complete14px red box in320x240 nominates deterministic interior10px away. Assert original point/raw normalized result remain intact and selected source is `RGB_LOCAL_COMPONENT_ASSOCIATION`, not a new model prediction. Add negative matrix: zero candidates; candidate beyond radius; two local candidates same or different colors; one valid plus one wrong-color/invalid-depth component (still ambiguous); unique wrong color; negated/multiple/unknown descriptor; high-chroma wrong-color point cannot jump to another object; image/ROI crossing; tiny area<8; no full3x3; zero depth at native, center, or another component pixel; hole/occluded/concave contour; unresolved outer boundary; duplicate matching object elsewhere (must still fail original tracker); unsupported calibration/source; stale/future observation; destination invalid; fresh context replaced during query. Separate helper nominations from adapter's subsequent rejection assertions.
- [ ] **Step 2 — Run RED.** Existing app interpreter with `-m pytest tests/test_molmo_point_association.py tests/test_molmo_grounded_planner.py -q -p no:cacheprovider`. New helper absent and unsupported association path are expected RED; prior tests remain GREEN. Preserve logs. Add no redundant tests for literal constants; test boundary behavior and provenance.
- [ ] **Step 3 — Implement the pinned helper/insertion.** Do not relax an unrelated gate to make a positive fixture pass. Preserve error evidence and exact native original pixels even when association or later geometry fails. Hash the helper in factory provenance. No whole-frame nearest fallback, target reclassification or destination refinement.
- [ ] **Step 4 — Run GREEN/regression.** Run association/native/grounded/CLI tests plus `tests/test_rgbd_planning.py tests/test_rgbd_top_grasp.py tests/test_rgbd_role_models.py tests/test_opencv_target_evidence.py`; retain all existing R544/R546 behavior. Run existing Ruff on changed files and `git diff --check`. Required: all selected tests pass, negatives produce no cloud/contract, original tracker/geometry/source files remain byte-identical. No extra independent reviewer requested.

## Task 2 — Immutable offline replay and separately admitted real local smoke

**Files:** Round-local `implementation/replay_association.py`, derived reports/logs and local ignored native-02 directory. No CLI/runtime change.

- [ ] **Step 1 — Reproduce old failure then evaluate new nomination offline.** Read original native-01 request/RGB/depth/results by verified hash; exact original geometry call still rejects native(179,109). Evaluate helper on unchanged archived observation, then static shared geometry and original tracker geometry as in planner proof; label every output `OFFLINE_STATIC_DIAGNOSTIC`. Preserve acquisition time and input checksum. Expected nomination(179,119), displacement10px; native(562,458)/(179,109) remains original. Full production adapter must continue to reject this archived frame as stale; test/assert this separately, never patch clock to produce a real acceptance. No rerender or new capture masquerading as old. If replay differs, retain raw failure and seek a new Astra plan before altering policy.
- [ ] **Step 2 — Record baseline and software results.** Keep native-01 exit2/geometry failure and1load/2completed generations in cumulative report. Associate offline results and candidate masks as derived evidence, not corrected raw. Distinguish helper success, metric/contour success, unknown full extent and no executed contract. Verify native-01's26 raw files again unchanged; keep total880711 bytes/hash inventory as local completeness evidence only.
- [ ] **Step 3 — Optional new-round real validation, only after GREEN/admission.** A fresh run is warranted to determine whether the new association composes with actual provider latency and fresh capture; archived replay cannot demonstrate that. R547 explicitly grants **one additional load start and at most two additional generation starts**, both including failures, solely for one target/destination pair. Across R542+R547 the authorized maxima become **2 load starts and4 generation starts**, with baseline1/2 already spent; this is an additive allocation, not a reset or reuse of old remaining6 generation allowance. If any intervening actual start changes the ledger, reduce remaining allowance accordingly or stop. No second retry/reload in R547.

  Recheck all unchanged model assets, R545 exact imports/CPU ABI, current source manifest, shared GPU lock, no foreign compute processes, >=12000MiB GPU, >=8GiB RAM and>=60GiB disk, and original timeouts before starting. Use R545 launcher only, existing CLI with one bound task/template, `--mode native --capture-fresh --generation-limit 2`, new exclusive `native-02` output and **no --allow-paid**. Use the existing genuine post-load sensor capture; do not reuse archived timestamp or trigger another capture to select a favorable outcome. If resource/admission checks fail before load, record NOT_RUN; after a load/generation begins, consume its start budget even on failure. Keep0paid/0hardware. Software native smoke may report local geometry readiness only; no real cloud PLAN or physical success is implied.
- [ ] **Step 4 — Report actual status without further tuning.** Save exact local raw model replies, prompts/tokens, fresh capture, native/associated coordinates, candidate reasons, geometry outcomes, timing and ledger. If nominal point lands correctly, report unchanged association; do not force exercise of rescue. Any failed output/negative geometry remains a failure, not a reason for ad hoc radius/threshold changes or rerun. phase-summary separates SOFTWARE, OFFLINE_REPLAY, REAL_LOCAL, REAL_CLOUD=NOT_PERFORMED, PHYSICAL=NOT_PERFORMED, FORMAL=NOT_PERFORMED. Local commit only explicit verified code/tests/derived evidence; no upload/public push.

## Preconditions and stop boundaries

Use correct `observation.world_point()` API. App CPU/stdin diagnostics require `PYTHONPATH=/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src`; use existing original app .venv interpreter. Native runtime remains R545 launcher-managed, with no extra PYTHONPATH precedence overriding validated packages. Managed-worktree writes/host GPU checks require established scoped permissions. No package install is permitted.

The new search policy is development-only, bounded to explicit descriptor colors and current calibrated scene family. It does not prove native point accuracy, arbitrary object identity, complete 3D extent or physical success. Any new failure/root cause, source drift invalidating assumptions, need to change threshold/coordinate interpretation, ambiguous semantics requiring broader parsing, tracker or geometry change, missing runtime dependency, or exceeded budget pauses affected repair for the next actual Astra plan. Expected RED/negative tests and explicit stale archived-frame rejection are already covered here.

## Verified exact inputs

- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/grounded_planner.py` — 15428 bytes — SHA256 `f0928910590869fbcb12c3afaa4bc2b1787dde553ee83fddb7810cade68e980d`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/molmo_pointing.py` — 15828 bytes — SHA256 `ee03fa55259b44e6cdb697baa557464db5ed086cc342a7cb3e4f11c0c439056e`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/planner.py` — 31544 bytes — SHA256 `45d4fa9a194db46e098550625b6b48a871c2aa0a200302c809c6b5e8522399f9`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src/cloud_edge_robot_arm/vision/tracking.py` — 35038 bytes — SHA256 `1a34ac6aa012cd58ab9016387310ebea044169b05b59286f4c5a8c540d3c6afc`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/tests/test_molmo_grounded_planner.py` — 21102 bytes — SHA256 `48420c857e64894adcc0b6045b87abcc868137c103d8d64600e02789987b3ecf`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/scripts/probe_molmo_grounded_planner.py` — 20965 bytes — SHA256 `3ed2056152940ede47b6e8970c7c0c1e13b397ae9bae761f43e96f4b794d51d7`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/datasets/model-cache/molmo-grounded-r542-20261110/native-01/report.json` — 6397 bytes — SHA256 `a5b683fff2ac834ebb3963ed08630b44aa3b6e4c39505f4d6f927e25e2b5414a`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/datasets/model-cache/molmo-grounded-r542-20261110/native-01/raw/capture-01/request.json` — 538417 bytes — SHA256 `5c3191c7ea9cb63827da43c3a404c4a1a2a683550e2cab6dc4822a7cb9bb43aa`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/datasets/model-cache/molmo-grounded-r542-20261110/native-01/raw/capture-01/rgb.png` — 18408 bytes — SHA256 `c1efbfd07be6320c50b00bc778dda415ec8a5189a28d463cf135718382d5ba43`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/datasets/model-cache/molmo-grounded-r542-20261110/native-01/raw/capture-01/depth.f32` — 307200 bytes — SHA256 `bccc3c0d3ec5a4e1c49ddd871b9c24505556328217919338823eed20b813f30c`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/datasets/model-cache/molmo-grounded-r542-20261110/native-01/raw/native/request-0001/result.json` — 1053 bytes — SHA256 `135d8a556e304be335a722ebc9ef07be44d40ab42d673e0112a1e49830a62be5`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/datasets/model-cache/molmo-grounded-r542-20261110/native-01/raw/native/request-0002/result.json` — 1047 bytes — SHA256 `16b1f841278e6db1bc1334df61a63af404872fc95a879f0c42947dacee7a1c97`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/datasets/model-cache/molmo-grounded-r542-20261110/native-01/raw-manifest.local.json` — 4442 bytes — SHA256 `e30238698a7ba5ae96531a974964fb33e0d386ee2f80e0668388a7e21520f78f`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/AGENTS.md` — 1774 bytes — SHA256 `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649`
- `/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/datasets/model-cache/molmo-grounded-r542-20261110/native-01/raw/inputs/task-01.json` — 166 bytes — SHA256 `e7b77613fc8942bc626ba6869c847458203c9f8122d48cbe7ee1d52d33d4be1e`

Planner static diagnostic proof:

- `planner-r547-offline-diagnosis.py` — 3473 bytes — SHA256 `dd826feff298440f6526b350411237cb86f1ed42679405216cc97bb045e7434f`
- `planner-r547-offline-diagnosis.stdout` — 8224 bytes — SHA256 `55a14b3d6dda27ef95691649b59d26d1da4bd5e3585b7e834c667f130aa3a837`
- `planner-r547-offline-diagnosis.stderr` — 0 bytes — SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

Self-review: all requested rejection classes and provenance are covered; no legacy geometry change; original failed run preserved; optional allocation explicitly additive; no unresolved design choice or extra review. This planner used only CPU diagnosis and changed no production source.
