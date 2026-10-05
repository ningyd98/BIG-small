# T11 independent software review

Verdict: **REQUEST CHANGES**. Three concrete counterexamples remain in the released software boundary. No live selection, provider calls, GPU/rendering, or physical execution was attempted.

## Snapshot and scope

Reviewed after the implementer explicitly released the immutable snapshot: eight owned files in `ownership.json`, their scoped `review-package.diff`, report, and eleven read-only dependency snapshots. All nineteen saved file hashes match `source-hashes.json`; all nineteen working files matched the saved copies during review. Base/head is `ddbeb92a1aa1dfa8039f6260d6b5887c58072383`. Root's separate API/harness change is reviewed in `../mode-runtime-integration/review.md`. No production/test/shared-document changes were made; only review reports were written.

Read exact original roadmap Task 11 (`docs/superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md:354`) and v2 T11 (`docs/superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md:155`). Review covers shared online gates, original B2 rules, selection provenance, prepared/commit/abort CAS, strict checkpoints, restart/idempotency, and the stated missing actual integration. Requesting-code-review applies through root's existing independent reviewer dispatch.

## Findings

### P1 — PREPARED records can change the authorized request while retaining its payload hash

Location: `src/cloud_edge_robot_arm/auto_mode/repository.py:781–796`; reachable through both repositories' public `save_transition`.

The save guard checks the transition ID and declared payload hash, but only compares the entire record for terminal states. While PREPARED, changing request fields under the same hash is accepted. This breaks both payload/checkpoint binding and prepare idempotency, and allows commit to activate a destination different from the original request.

CPU reproduction, independently run against in-memory and temporary SQLite repositories:

```python
initialize(repo)  # PCSC, mode_version=1
service = ModeTransitionService(repository=repo, clock=lambda: NOW)
original = service.prepare(request())  # PCSC -> ETEA
repo.save_transition(original.model_copy(update={"to_mode": ControlMode.AUTO}))
assert service.prepare(request()).to_mode == ControlMode.AUTO
assert service.commit(original.transition_id).to_mode == ControlMode.AUTO
```

Both printed `requested=EVENT_TRIGGERED_EDGE_AUTONOMY`, `repeated_original_request=AUTO`, `committed=AUTO`, `same_payload_hash=True`. No guard mocking or direct SQLite modification was used.

Requested correction: make the stored PREPARED request immutable (allow only an identical save), or explicitly validate all request fields against an immutable canonical payload and prohibit rebinding. Protect task/from/to/version/idempotency/decision/reason/preparation identity, not just a caller-supplied hash. Add both repository regressions, including the original prepare retry and later commit; reject without changing the original transition/status/checkpoint.

### P2 — Selection verification accepts an impossible mode chain with valid version numbers

Location: `src/cloud_edge_robot_arm/auto_mode/baseline_policies.py:638–685`.

The selection verifier tracks previous version and time but does not track the previous committed mode. It therefore accepts two adjacent transitions whose numeric versions are contiguous even though the second `from_mode` is not the first `to_mode`. Such logs could not have passed the actual repository CAS and cannot demonstrate valid mode-switch selection.

Reproduction used `mode_policy_snapshot()` exclusively under a temporary directory. In one case, append a second COMMITTED transition and checkpoint: first PCSC->ETEA, versions 1->2; second PCSC->ETEA, versions 2->3; second commit/checkpoint at `2026-10-04T00:10:00Z`, prepared one second earlier. This satisfies frozen confirmation, dwell/cooldown, version, identity, and switch limits. The unchanged selection snapshot then returned:

```json
{"first_to_mode":"EVENT_TRIGGERED_EDGE_AUTONOMY","second_from_mode":"PERIODIC_CLOUD_SUPERVISION","verdict":{"accepted":true,"errors":[]}}
```

Requested correction: reconstruct and validate the full mode state chain, requiring each subsequent `from_mode` to match the previous `to_mode`; bind the initial state when available rather than treating version continuity alone as complete CAS evidence. Add the impossible-chain regression. These are synthetic log fixtures, not claimed real selection evidence.

### P2 — Duplicate-event cache returns CONTINUE after B1 calibrated risk becomes UNKNOWN

Location: `src/cloud_edge_robot_arm/auto_mode/baseline_policies.py:122–142`.

The cache rejects changed inputs only when they occur in its partial key. It omits the `RiskEstimate` used by B1. After a valid low-risk event is cached as CONTINUE, the same event and observation with UNKNOWN risk and no CONTINUE probability still returns cached CONTINUE, bypassing B1's required UNKNOWN reobservation/stop behavior.

Independent CPU reproduction:

```python
policy = ThresholdPolicy(0.5)
first = context()  # VALID, CONTINUE probability=.1
unknown = replace(first, risk_estimate=RiskEstimate(None, {"CONTINUE": None}, None, None, "UNKNOWN"))
assert policy.decide(first) == DecisionAction.CONTINUE
assert policy.decide(unknown) == DecisionAction.CONTINUE  # stale cache
assert ThresholdPolicy(0.5).decide(unknown) == DecisionAction.REOBSERVE
```

Requested correction: bind the complete policy-relevant frozen input to the event cache, including risk status/action probabilities and B2's relevant legacy evidence; a changed duplicate must fail closed or be explicitly revalidated without charging an allowance twice. Keep the current hard-stop/deadline check before cache lookup. Add the UNKNOWN transition regression, rather than only checking a new policy instance or mutation of an external input mapping.

## Confirmed behavior and limits

- DecisionContext binds episode/observation/plan/command/mode versions, freezes its probability and fact/measurement mappings, and rejects explicit oracle/future/offline fields. All shared event classes enter the policies; successful skills and failed final verification do not bypass evidence checks.
- Shared hard-stop, capability, atomic-action, UNKNOWN/INVALID and verification-budget gates run before ordinary policy choice. LOCAL_RECOVER is unavailable to these baselines. B0 reuses the existing bounded single-inflight supervisor and counts merged ticks. B1 uses the calibrated CONTINUE probability, not total score or self-reported confidence, except for the cache finding above.
- B2 directly uses the original RiskEvaluator/AutoModeSelector and freezes their source/policy parameters; strict B2 selection cannot rewrite auto-v1 120-second dwell, 300-second cooldown, five switches or two confirmations. Missing online legacy evidence fails closed. Legacy confidence is not represented as a new calibrated probability.
- B0 selection requires all four periods and all 120 unique groups/12 strata, independently reconstructs physical outcomes and final cost, compares common assignments/role/device/provider summaries, and applies the same .9 static/.8 overall/.01 safety gates before request/latency ranking. Missing sources remain INCOMPLETE; no feasible baseline disables a savings claim. Actual request-to-role snapshot identity is expressly left for strict T8/role integration, not accepted from summary hashes.
- SQLite commit uses BEGIN IMMEDIATE and reads the current persisted status inside that transaction; stale cross-connection commits fail. Transition and status update together, increments/time remain stable on retries, aborted/committed states cannot be reversed, and ordinary save cannot create a terminal state. The PREPARED immutability finding remains.
- Strict research commit requires the selection snapshot, live guard, durable matching checkpoint and current mode/version. It revalidates source/policy and raw selection data, enforces atomic completion, confirmations, dwell/cooldown and switch limits. Current saved configuration stays SOFTWARE_ONLY with no selected period/threshold/selection hash. No actual research-mode selection or commit has been enabled or accepted by this review.

## Independent validation

- `.venv/bin/python -m pytest -q tests/test_runtime_auto_baselines.py tests/test_mode_transition_cas.py tests/test_phase8_1_mode_transition_commit.py tests/test_phase9_auto_safe_transition.py tests/test_phase7_auto_mode.py tests/test_phase7_auto_mode_repository.py tests/test_research_supervision.py`: **76 passed in 50.37s**, exit 0.
- Root's narrow integration tests: **6 passed in 0.93s**, documented separately.
- Scoped Ruff over T11 and root integration Python files: **All checks passed**, exit 0.
- The three counterexamples above were independently exercised in temporary CPU-only fixtures. They are not new repository tests and do not alter the released baseline.
- An initial collection command named nonexistent `tests/test_periodic_supervision.py` (exit 4, no tests ran); the corrected documented supervisor test was then used. No broad project suite, network/model/GPU/render run, INITIAL/FINAL freeze, or real credential/role/physical acceptance was attempted.
