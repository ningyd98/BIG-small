# Bounded independent runtime review

Reviewed this round's supervisor claims, owned initial-plan WAIT, effect-source
getter, and their runtime joins against the Step47 source snapshot at
`t12-worker-live-integration/source/`. Repository review was limited to the
new source-only getter/claims methods. No real model, renderer, physics step or
action episode was run; this is software-source evidence only.

## Findings and targeted fixes

1. **P2 — publication drift silently discarded.** The initial worker response
   path discarded a reply when its publication hash changed, even without TTL
   expiration. Reported before repair. The current path raises
   `WORKER_SUPERVISION_SOURCE_CHANGED`, consumes no new plan completion and
   retains the already allocated claim cost. The exact normal/stale response
   regression now passes both cases.
2. **P2 — provider entry accepted an obsolete current boundary.** The initial
   `assert_supervision_plan_pending` checked the durable old PLAN_PENDING row
   against the frame but did not join the current publication. Independent
   concrete memory and SQLite probes reserved a supervisor frame, published a
   new actual checkpoint through `publish_visual_boundary_if_current`, then
   observed `DID NOT RAISE` at the provider boundary. Reported before repair.
   The current helper joins current publication, full original requirements,
   ledger definition, non-exhausted verification pool, frozen model/role/cloud
   and original source inventory before and after optional-source checks.
   Execution calls this strict boundary before and after the provider; neither
   call reads the backend. Both independent repository probes now pass.
3. **P2 — non-TTL context mismatch discarded by the generic decider.** A reply
   with an altered wire state_version and consistently altered decision was
   silently discarded by the legacy generic decision path before worker frame
   validation. The independent orchestration probe initially observed
   `DID NOT RAISE`. Reported before repair. The current path checks the exact
   owned frame context and captured_at before expiry/decider handling. A generic
   DISCARD must independently classify as EXPIRED; otherwise it raises
   `WORKER_SUPERVISION_CONTEXT_CHANGED`. The independent probe and the added
   wire-context regression now pass.

All three concrete findings above are resolved at the reviewed SHA below.
No further finding remained in this bounded review.

## Source conclusions

- Capture and plan allocations commit before capture/provider work. Durable
  claims join the concrete lease, frozen job configuration and current sources;
  cancellation, source/configuration drift and missing ownership fail closed.
  Rereading a ledger does not restore debited allocations or reconstruct local
  capture/plan/effect handles for replay.
- The source-only memory/SQLite getter checks current original deadline,
  versions, cancellation, checkpoint, original/pool hashes and publication
  boundary under the repository lock/transaction. It omits current grounding
  TTL solely for supervision/effect evidence. The normal publication getter
  and native/action route retain strict grounding validity. The source-only
  frame is not passed as an executor/native action permit.
- Initial-plan passive WAIT is bracketed by the original owned pending PLAN
  claim and current source checks. Supervisor model work uses a frozen frame
  and context; provider-thread source checks use repositories, not backend or
  robot state.
- At the actual action-return boundary, REOBSERVE retains the typed completion
  receipt. It waits for an owned AFTER_EFFECT acquisition with the same receipt
  digest and an acquisition time after the request; successful fresh capture
  clears the request before further action. Historical effect-source handling
  does not authorize a new action.

## Independent CPU evidence

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -m pytest -q /tmp/test_supervision_review_probe.py tests/test_visual_worker_supervision_execution.py::test_supervision_result_completed_once_or_stopped_when_source_changed tests/test_visual_worker_supervision_execution.py::test_changed_supervisor_wire_context_stops_instead_of_discarding_as_old_state
6 passed in 12.44s
```

The temporary probe's provider case uses the real parametrized `configured`
memory/SQLite fixture and `supervisor_source`; advances the actual publication
with `boundary(publication.checkpoint, suffix='review-cp-drift')`, the expected
owner revision/contract/checkpoint hashes and incremented state_generation;
then requires `assert_supervision_plan_pending(frame)` to raise. Its context
case uses `supervised_episode`, lowers the owned wire context state_version by
one, builds a matching CONTINUE decision, polls that concrete response and
requires `_EpisodeStopped` without completing the plan.

Earlier independent probes were RED: 2 provider-boundary cases and 1 non-TTL
wire-context case failed to raise. An initial whole-file run overlapped source
and timestamp-fixture edits (37 passed / 2 failures); it is not final-generation
verification. The two affected expired-grounding cases were independently
rerun on quiet sources and passed (2 passed in 10.47s). A mistyped test node
later produced pytest collection exit 4 with no tests run; the corrected final
command above is the completion evidence. No broad suite was repeated after
the targeted fixes.

## Reviewed SHA-256

```text
bcfd17bbc03aa492394baac99289ff0552dc40d80c998b2d6c6731f7d19ae1fa  src/cloud_edge_robot_arm/vision/execution.py
7f9e255b9d35dbec1226c60ea81f2c0b593225a4930c976bd8f17aa38e9b64f4  src/cloud_edge_robot_arm/vision/evaluation.py
84ea21214453537e0c0d39ebf2da1a8ea3aa8539354089318e6d6398181fdfa1  src/cloud_edge_robot_arm/vision/worker_runtime.py
c73908964542d843c8bc28cc230dc651403dcfdb7c843be500f6644c21f7d162  src/cloud_edge_robot_arm/repositories/event_autonomy/visual_supervision.py
3a02686a0bf89d8ec3943b46d2b2a98792009e0a0374f0faaf184a7c066d4703  src/cloud_edge_robot_arm/repositories/event_autonomy/memory.py
92bc23b61ee7867547a8f4b6304d813f0caec5d3d338371b7bc1dcd1975eae2d  src/cloud_edge_robot_arm/repositories/event_autonomy/sqlite.py
3f53fc60baa1d37fb236ed95e93638ead6a4c3dea2eb3e7a9f252395c5c33278  src/cloud_edge_robot_arm/repositories/event_autonomy/protocol.py
de788353e86fef3be1bbc26c893b58d8ada07a96ab4b6d4ed44a558b38d36382  tests/test_visual_worker_supervision_execution.py
92badeeccd889b629a161081fccf19c5377505fd52a758097289cdbec5dc612e  tests/test_visual_worker_supervision_runtime.py
```

Actual model/action count: **zero**. No INITIAL/METHOD/FINAL acceptance claim.

## Post-integration TTL audit repair

The merged root CPU run later exposed a missing audit field in
`test_actual_repositories_capture_provider_owner_receipt_and_cancellation[sqlite-False]`:
the first frame classification was CURRENT, the generic decider crossed the
TTL boundary, and the independent second classification was EXPIRED. The legal
DISCARD retained PLAN_PENDING and its spent allocation, but its generic audit
row lacked `reason`, producing `KeyError: 'reason'` at the test's line 320.
This was not a source/lease guard failure or a refund. The merged result was
1 failed / 744 passed / 3 skipped / 2 deselected; it is not a passing final run.

Root's qualified two-case RED evidence is retained in `ttl-audit-red.log`:
the EXPIRED case lacked its canonical reason; the CURRENT case stopped but
had already recorded a false DISCARD row. Independent inspection of the tiny
repair confirms that `decision_record` is appended only after the worker's
second classification establishes EXPIRED, with the exact
`original_frame_ttl_expired` reason and owned claim id. A non-TTL mismatch stops
before any DISCARD row. Native/source/TTL/deadline/provider checks and the
LEGACY decision record remain unchanged.

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -m pytest -q tests/test_visual_worker_supervision_execution.py::test_discard_rechecks_ttl_before_recording_its_owned_reason tests/test_visual_worker_supervision_execution.py::test_supervision_result_completed_once_or_stopped_when_source_changed tests/test_visual_worker_supervision_execution.py::test_changed_supervisor_wire_context_stops_instead_of_discarding_as_old_state
5 passed in 0.50s

2770da01bfe1869622b104d763c6852b621158d7aaac4004a04fadfdf2a164de  src/cloud_edge_robot_arm/vision/execution.py
7ad2ca9b6fbde32c60d190ef6cfb872b2bb34cb7143324de51bafbcc97b5926e  tests/test_visual_worker_supervision_execution.py
```

The historical review and SHA above remain intact; these two SHA supersede
their earlier entries for this specific post-integration repair. No source
file was edited by this reviewer. Only these five CPU cases were run; actual
model/action count remains zero.

### Final formatted-test verification — 2026-10-05

At 2026-10-05 06:50 UTC (14:50 Asia/Shanghai), independently reread the
formatted two-case TTL audit regression and reran the same exact five cases
from the post-integration command above: **5 passed in 0.48s**. The change to
the two-case test is line wrapping of the monkeypatched generic decider call;
both EXPIRED and CURRENT assertions remain identical. The implementation SHA
is unchanged. The historical `7ad2ca9b…` test hash above is retained; the final
reviewed test bytes are:

```text
aaaa535392f728227e4ceb900cd57c5d7f004c36f82da7d159357b09f76d5432  tests/test_visual_worker_supervision_execution.py
2770da01bfe1869622b104d763c6852b621158d7aaac4004a04fadfdf2a164de  src/cloud_edge_robot_arm/vision/execution.py
```

No source modification, model call or actual action was performed.
