# G1 optical RELEASE and RETREAT qualification repair plan

Author: gpt-6.2-astra  
Base commit: `a81c23fc05a9ab28aa0b5e68452c2ed78de622b4`  
Intended directory: `artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-release-optical-separation-20261125`  
Status: Proposed offline shadow development. No qualification or RETREAT authorization.

## Inputs and original evidence

The companion `plan.json` records the locally computed SHA256 of each of the 15 permitted inputs. Paths in its manifest are relative to `experiments/results/g1-continuous-payload-observation-20261125`. The local HEAD matched the base commit. Plan preparation used read-only inspection. No files were edited, robot commands issued, external integrations invoked, tests started or formal runs performed.

Historical context is identified by `round-g1-continuous-payload-observation-20261125`, `round-g1-print-pose-uncertainty-20261125` and `round-g1-complete-cv-repair-20261125`. The independent dense-check and reserved cvfix-e01/02 captures remain sealed.

Each original fit has 33 RELEASE records, including 31 distinct DWELL frames spanning ticks 0 through 240. Optical counts below use all 33 records. The chain length uses the 31 DWELL frames. None of the three qualifies as released.

| Fit | Current support/rim | Current two-pad separation | Longest stable chain | Available shadow lower range, mm | Offline tighter-side minimum gap, mm |
|---|---:|---:|---:|---:|---:|
| dense-fit-01 | 33/33 | 27/33 | 10/31 | 0.05244 to 0.88392 | 3.151614 |
| dense-fit-02 | 0/33 | 0/33 | 0/31 | −2.16278 to −0.82029 | 3.295481 |
| dense-fit-03 | 32/33 | 0/33 | 0/31 | −3.01321 to −1.43107 | 0.493612 |

The local predictions confirm the optical counts, chain maxima and first DWELL IDs recorded in `plan.json`. In fit 02, 15 records lack pose. The remaining 18 show the current table and destination but have only one red-side sample. Table visibility alone cannot establish payload support.

All 93 physical DWELL labels contain only object–table contacts. Within each capture the largest recorded center-coordinate span is below 1.6 × 10⁻¹⁶ m, consistent with a stationary payload. The shadow ranges and offline gap minima above are supplied calculations. They were not recomputed during plan preparation. The minima use the true shape and exposure-synchronized joint and finger measurements projected onto the original wrist jaw axes. Fit 03 has only 0.243612 mm of physical margin above the 0.25 mm requirement. That margin is a feasibility diagnostic, never an allowance to subtract from uncertainty.

## Hypothesis and bounded changes

Current local silhouette and exposed rim measurements may constrain payload extent along the two jaw directions more tightly than the existing pose estimate. Fit 01 requires continuous evidence through the interrupted chain. Fit 02 requires usable current pose and affirmative payload support as well as separation. Fit 03 requires a conservative bound on the tighter side despite its small margin. The three fits need not all become certifiable.

1. Limit implementation to a shadow path associated with `scripts/graduation/g1_complete_cv_payload_observation.py`. Retain the existing shadow output for comparison. Keep the single-ID8-plus-red certificate disabled after its independent interval failure. Never use it as a valid pose certificate, fallback or prior that excludes otherwise feasible geometry.
2. For each exposure, bind the frame ID, image checksum, calibration, accepted open command and exposure-synchronized measured joint and finger positions. Use genuine current optical measurements. If the permitted inputs do not expose a required raw measurement, record it as unavailable. Do not reconstruct a silhouette from a prediction, simulator pose or contact label. Access to additional raw image files requires separate scope.
3. Use the observed calibrated model, current silhouette and visible rim to construct a feasible set of payload poses and extents. Retain original dimensional uncertainty and bounds for calibration, depth, pixel localization, pose, wrist/pad geometry and synchronization. An independently identified partial second mark may constrain pose only where the current pixels support its identity and geometry. Hidden surfaces remain possible. A small residual, a single pose fit or empty image space behind an occluder cannot bound them.
4. For each pad, project its inner face and the most adverse feasible payload extent onto the corresponding original wrist jaw axis. Compute the infimum and supremum of the signed clearance over the feasible set. Record side, units, feature provenance and uncertainty terms. An empty or unbounded feasible set yields unknown. Each lower bound must strictly exceed 0.25 mm. A valid upper bound at or below 0.25 mm establishes inadequate clearance on that side. An interval crossing the threshold leaves clearance uncertifiable.
5. Preserve the existing live decision path, overhead RGB-D, controller, original asset and dimensions in `assets/robots/franka_panda/scene_g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1.xml`, SafetyShield, 1 mm path, 8+240 stop, 100 ms per feedback and all eight skills. Preserve frozen records byte-for-byte. Add no physical step or scene/camera change.

## Verification order and acceptance

1. Verify commit and all input hashes. Keep `offline-physics.json`, simulator contact identities and true geometry/state labels inaccessible to the predictor. The published fit summaries are already known. These are development cases.
2. Predict one row for each of the 99 RELEASE records, retaining missing measurements and explicit failure reasons. Record episode, frame ID, checksum, step, DWELL tick, command evidence, both measured finger positions, optical support/rim evidence, pose validity, both gap intervals, gate decision, stable count and feedback time. Freeze the rows, code identity, calibration, configuration and their digests before the scoring process reads frame labels.
3. A shadow RELEASE qualifies only with a real open command, measured minimum finger position strictly above 0.035 m, affirmative current stable table support, verified current rim and bounded pose error, and both optical lower gaps strictly above 0.25 mm. Require the original joint gate throughout 31 distinct DWELL exposures at eight-step cadence spanning 240 ticks. A failed or missing frame breaks the chain. Enforce the existing 100 ms limit separately on each feedback. No force-only admission, online oracle or online pad/contact identity.
4. In a separate offline scorer, join frozen rows to labels by episode, frame ID and checksum and verify exposure-step alignment. Report per-side interval coverage against the independently derived offline clearance, false certifications, unknowns, failed support checks, longest valid chain and individual deadline misses. A case-level minimum alone cannot verify frame-level interval coverage. Record any coverage that cannot be checked as unverified.
5. Check rejection of hovering, one-pad contact, foreign objects, stale/missing/repeated exposures and wrong calibration. Use only separately identified available evidence or explicitly labeled offline input-corruption checks within scope. The 93 stationary table-supported labels cannot validate physical negative cases. Report any unavailable negative case as unverified.
6. Accept a fitting result only as shadow evidence. A positive fitting claim requires the entire original chain, covered intervals on the claimed frames, zero false certifications and no timing failure. An unknown is a valid development outcome. RETREAT remains subject to its original prerequisites, including a qualified RELEASE. Shadow output cannot authorize motion.

## Stop conditions

Stop scoring on a digest or exposure-join mismatch, label leakage or an unfrozen prediction set. Withdraw any affected certificate on interval undercoverage, a false positive, unsupported geometry, failed negative control or deadline miss. Preserve the evidence and failure reason. If original optical observations cannot prove support or dual separation, retain unknown and stop that qualification attempt. Do not relax gates, infer missing observations, add physical steps or tune against holdouts. Operational promotion and formal research acceptance require separate independent verification of the complete original joint gate.
