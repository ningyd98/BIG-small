# T15–T17 actual source/provider audit

This is a read-only design audit, not an implementation or research acceptance. The inspected source snapshot contains31 files; `source-ref-hashes.json` SHA256 is `5282d53795151adbdde23f45be75f02f4ad8aef08288f224d20d61b32f70ca69`. `static-boundary-checks.json` verifies five source-level facts without running a renderer, model or experiment. Actual research remains **NOT_RUN**.

## Implementation gaps that valid future data cannot resolve by itself

| Boundary | Current exact behavior | Required implementation |
|---|---|---|
| `assignments.EpisodeRecord.accepted_task_success` | Always returnsFalse; formal records must therefore retain full Tcap | Independently verified outcome view with raw-source recomputation and an exact assignment/record/source binding |
| `runner.run_assignment` | No actual adapter seam; absent adapter produces BLOCKED; the only injected adapter must be MOCK | Stage-aware actual executor and read-only verifier, keeping every original failed assignment |
| `run_rgbd_research.py` | Always calls the closed runner and publishes BLOCKED | Resolve a source-admitted frozen method registry and actual adapter; retain append-only originals/resume checks |
| `metrics.compute_research_metrics` / `acceptance.evaluate_goals` | Physical count/formal acceptance fixedFalse; default goals always NOT_RUN | Consume independently verified episode/G3/G4 source views, recompute canonical counts/costs and apply the existing fixed statistics |
| Power stage | Even supplied INITIAL/method files produce “not integrated”; method JSON is only parsed | Strict method reader; execute all120×7 originals; verify every source; derive the120 JOINT/B0 paired outcomes |
| `power.choose_formal_n_from_pilot` | Checks shape/group/hash strings, never accepts their physical provenance | A separate raw-source power reader, reusing the unchanged conditional zero-effect power calculation |
| `protocol.freeze_protocol(stage='FINAL')` | Unconditional exception | FINAL reader reconstructing actual INITIAL, methods, isolated power, smallest valid N and revised source-bound resource plan |
| Actual G3 CLI | Always raises after FINAL check | Recompute full frozen opportunity sources/labels offline; rerun JOINT/B3 under each original clock/calibration/online snapshot |
| `JointEvidencePolicy.decide` | Every actual call stops before its supplied admission provider is used | Source-derived stage admission integrated before ordinary decisions, followed by unchanged candidate/TTL/budget/commit checks |
| `RuntimeCompositionAdapter` | Actual evaluation and submission always closed after source revalidation | Integrate read-only admission result; keep fresh owner-thread snapshot and final commit revalidation separate from dispatch |

The statistics, complete paired scene assignment, raw-cost parsing, evidence gate numerical replay, candidate isolation, deadline checks, mode CAS and recovery lifecycle are reusable software. Their passing tests do not mean that the above execution/acceptance branches can currently accept valid actual data.

## Foundation order and baseline certificate

The approved order is T7b→B0 four-period selection→120 foundation→INITIAL→T9 risk→T10/B3. The current `_RoleBoundPilotExecutor` always sets OPENCV; `_VisualEpisode.execute` then requires `native_action_contract` at PRE_SAFETY and PRE_SKILL. That constructor unconditionally sets geometric/motion bounds toNone, so the canonical validator returns UNKNOWN. There is no certified-bound provider parameter. Supplying only post-INITIAL T9 bounds would create a circular prerequisite for INITIAL.

The smallest honest resolution is a **separate T7b baseline certificate reader/provider**, independently derived before INITIAL from excluded development RGB-D/pose-marker sources and conservative sensor/controller/motion assumptions. It must bind camera/gripper/marker assets, observation source, geometry, controller and hard safety versions, covered task/velocity/depth ranges, measured residuals and the full action duration. Unsupported motion, identity, occlusion or coverage stays UNKNOWN. A provider may then supply actual bounds to the existing native gate; it must not supply a caller VALID flag or switch to LEGACY. The existing nominal `top_grasp` asset and gripper checks do not establish these bounds.

Later T9 adds source-qualified probabilities and independently calibrated residual bounds; JOINT/B3 share the basic OpenCV and SafetyShield behavior. B3 may ablate the prescribed uncertainty/time component but cannot remove hard safety, identity or ordinary freshness. Baseline B0 need not require a learned failure probability. Root is implementing the user's visible pose marker; this audit makes no marker/source or safety edits.

Pre-INITIAL resource calibration/data cost measurements can be separate excluded development measurements, not an accepted T9 model or formal calibration result. The new compiler has no INITIAL requirement for such cost-only inputs. Actual auxiliary publishers and measurements are still absent; a CALIBRATED flag or an empty request table cannot resolve that absence.

The actual planner currently records remote `monetary_cost=None`, and there is no provider-billing settlement reader/publisher. `CostLedger` allows the original IN_FLIGHT→settled update but refuses changing an already settled attempt. Genuine runs therefore keep unknown billing and cannot meet complete monetary-budget readiness today. A future source-bound billing artifact must join the original provider/request IDs, actual usage/invoice and frozen tariff/version; it should derive a separate verified charge view while preserving original rows. Editing a raw fee field or declaring a ceiling is not an independent billing measurement.

## Additional source-reader incompatibility

`_VisualEpisode.supervise_frame` records actual requests under SUPERVISOR. The inspected `_audit_ced_case` rejects every sent request whose role differs from PLANNER. Thus a genuine periodic B0 episode with a supervisor call cannot pass the source reader, resource compiler or INITIAL. The source AST check confirms both sides. Root has authorized a bounded T8 fix2; the released fix1 snapshot remains unchanged. This is a software defect, separate from missing credentials or physical certificates.

## Smallest proposed source verifier

Add `research/episode_evidence.py`, initially read-only. It exposes the proposed functions below; these APIs are a design, not existing callable implementations.

```python
verify_episode_sources(case: Path, assignment: EpisodeAssignment,
                       admission: VerifiedMethodAdmission) -> EpisodeSourceVerdict
verify_run_sources(runs: Path, admission: VerifiedMethodAdmission,
                   stage: Literal['power', 'formal', 'recovery']) -> VerifiedRunSet
verify_gate_sources(opportunities: Path,
                    admission: VerifiedMethodAdmission) -> VerifiedGateSet
```

`EpisodeSourceVerdict` contains exact assignment/record/raw inventory/method/protocol/role hashes, scope (`UNAVAILABLE`, `INVALID`, `VERIFIED_SIMULATION_SOURCE`), independently recomputed physical outcome, online completion, terminal reason, safety, complete measured duration, canonical decision/condition/fallback counts, costs and verification errors. These are recomputed values. Persisted verdict booleans are never an admission authority; all loads/resumes/API/reproduction re-run the reader against the original files. Simulation source consistency does not authenticate remote model weights or certify physical hardware.

The verifier should extract public read-only helpers from existing `freeze_evidence` and `protocol_evidence`, preserving their original checks. Reuse reset-complete `_trace`, exact evaluation start120, reset/controller reconstruction, registered RGB/depth/instance frame reconstruction, canonical conditions, `sample_physical_observation`/`evaluate_evidence`, role-probe/settings reader and original settled-cost/wire reader. Do not reuse a teacher success as a method outcome.

Additional mandatory joins are missing from the formal source contract: every request's globally unique ID and role to original request/response wire; every online round to exact observation/context/mode/plan/command versions; candidate set→selected decision→accepted decision→started skill→typed backend command→actuator range→fresh effect/online postcondition→independent raw outcome. ACK and accepted decision are not actuator start or verified completion. Preserve all cancelled, late, partial, failed and UNKNOWN rows. Reject both omitted failures and duplicate/foreign identities. Fault schedules, raw oracle labels and future events remain offline-only; the online context gets only registered images/proprioception/derived facts.

Retain `EpisodeRecord` v1 as conservative historical input. Introduce an independently derived `VerifiedEpisodeView` for analysis/accepted duration rather than trusting `source_verified` or changing a persisted flag into authority. Any future v2 raw record/penalty contract should be versioned explicitly; successful duration is derived only after source verification, all other outcomes use frozen Tcap and failed recovery60. Old records and frozen artifacts remain immutable.

## Method admission and actual adapter

A separate strict `research/method_evidence.py` reader should construct `VerifiedMethodAdmission` from the read-only INITIAL admission auditor (currently delegated), actual role sources, baseline certificate, source-accepted T9 artifacts/parameter selection, finite joint weight exploration/results, frozen B0/B1/B2 rules and enabled recovery capability evidence. Freeze exact common controller, sensors, parser, safety, budgets, capabilities, thresholds, source tree and role/provider hashes. Method registration cannot be a config ACCEPTED field. Main formal registry must contain the exact seven methods; G3 adds JOINT/B3, G4 adds JOINT/B4. Every baseline/ablation uses the same common execution and accounting.

Stage-aware admission must permit bounded SELECTION_EXPLORATION after INITIAL plus actual calibration and preregistered candidates, without circularly requiring its own winning selection. POWER requires accepted selected methods; FORMAL additionally requires FINAL. SOURCE_VALIDATED is distinct from EXECUTION_ADMITTED. The current role binding explicitly recognizes only CONTINUE/REOBSERVE/STOP and the verification-router policy; enabling common adaptive/recovery methods needs a versioned capability/provider binding, fresh probes and independent evidence, not an expanded capability set supplied by the caller.

Proposed actual adapter:

```python
class ActualEpisodeAdapter:
    def run(self, assignment: EpisodeAssignment,
            admission: VerifiedMethodAdmission, output: Path) -> RawEpisodeBundle: ...
```

It reuses the existing owner-thread capture, `RoleRuntimeBinding`, ledger/network schedule, OpenCV tracker, `SafetyShield` and `edge.runtime.skill_executor.SkillExecutor.execute_attempt`. The existing visual `route` is still fixed to verification-router behavior and does not route through the frozen JOINT/B1/B2 policies; a narrow policy-provider hook must connect these decisions at the same skill/supervision boundaries. Keep atomic execution, STOP/cancel, fresh final submit checks, durable mode/recovery CAS and audit-before-charge behavior. The adapter writes raw sources first and invokes the independent reader afterward; execution cannot declare success for itself.

## Power, FINAL and analysis reuse

Power source verification reconstructs the full isolated120×7 assignments and records, exact12 strata, complete scenes/seeds/schedules and frozen methods, then derives JOINT/B0 success/safety pairs. The existing `choose_formal_n` remains unchanged: observed discordance only, assumed effect0, family alpha.01, candidate Ns600/1200/1800/2400 and target.8; upper uncertainty bounds remain reporting only. No formal p-values or optional stopping enter this stage.

`final_spec_from_evidence(Path)` should independently reverify INITIAL/admission/methods/power, recompute chosen N and the resource plan for that N, require all original groups and unchanged protocol fields and publish a new immutable FINAL generation only when every prerequisite passes. The full formal/G3/G4 verifier then feeds the same `analyze_research_runs` production entry point, existing score/Holm/bootstrap math, API view/export and T18 reproduction. Actual goals need source-qualified counts for each G0–G5 component; any missing component remains NOT_RUN, rather than converting an entire synthetic suite into acceptance.

## Independent work available now and remaining actual inputs

Independent software work can implement the raw verifier/negative source fixtures, exact request/decision identity publisher, stage-aware method registry, policy-provider hook, actual adapter, verified power/FINAL reader and T16/T17/T18 verified-source consumers. Positive algorithm fixtures must remain SOFTWARE_ONLY; no fixture can issue actual admission or publish INITIAL/FINAL.

Actual completion still needs fresh explicitly authorized cloud service/settings/role probe, the independently accepted T7b baseline geometry/motion certificate, real four-period480 selection and120 foundation passing their fixed quality gates, complete fixed opportunity and200 fault sources, source-qualified cost/ceiling evidence, current train/calibration/selection provenance, accepted method/recovery capability evidence, isolated120 power and FINAL. Current data do not meet these conditions. The overall work is therefore software modules verified with remaining integration gaps and actual research blocked; it is not “all software DONE” or a positive physical result.

A meaningful future RED/GREEN matrix must include rehashed omitted failures, shifted raw evaluation prefixes, changed frames/controller/method/roles, zero-byte wire SHA drift, swapped request roles/IDs, candidate-only acceptance, accepted-without-start, command-without-effect, late/cancelled/UNKNOWN, repeated nonrepeatable steps, partial costs, tampered method admissions and blocked power/FINAL. Tests verify the contract, while actual acceptance requires genuine source bundles and independent review.
