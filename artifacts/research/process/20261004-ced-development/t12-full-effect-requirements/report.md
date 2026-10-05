# Full original effects, hold and terminal requirements

Scope: SOFTWARE_ONLY / SOURCE_ROUTE_ONLY. Actual model calls: 0. Actual action
episodes: 0. No actualMax, native geometric-bound, INITIAL, METHOD, FINAL or
physical-success claim is made.

The original TaskContract, step timings, retry limits, safety constraints and
criterion names remain frozen. The source-worker compiler registers the explicit
`visual.worker.full-effects.v1` allowlist from the actual cloud pick/place
templates in `cloud/planning/adapter.py` and `vision/planner.py`; TaskContract
condition fields are strings rather than a schema enum. Unmapped original
preconditions, success conditions and completion criteria fail registration.
The final step now includes every original task completion criterion. LIFT adds
the complete `object_held`, `object_lifted`, `object_stable` hold set.

Worker `object_held` requires its current RGB-D identity/depth fact together with
connected proprioception, closed gripper, the exact held object identity, and no
hard safety fault. The compiler enables this via
`holding_feedback_required=True`; unversioned LEGACY conditions retain their
historical behavior. `object_placed`, emitted by existing cloud templates, is now
accepted by the canonical registry and keeps its existing region-plus-release
composite semantics.

`grounded_worker_execution_effect_conditions(original, execution_contract,
grounding=..., step_id=...)` resolves registered TCP templates from the full typed
execution payload only after exact original-policy and grounding-receipt
comparison. Original templates remain unchanged. Route input v2 carries an
optional concrete `grounding_receipt`; v1 source history remains readable.
Current checkpoint receipt hashes, original identity/version/sources, exact
full execution payload, successful typed completion and a later distinct frame
are all checked. A historical receipt is effect-only and cannot authorize a
fresh native action. Reobservation consumes the existing pool without refunds,
retry resets or deadline extension.

An already completed effect remains inspectable after grounding TTL if its
typed completion proves the execution started within the original binding
interval. `current_publication` remains strict by default; the router derives
its explicit `grounding_source_time` only from a fully checked completion. All
current checkpoint, original deadline, pool and source requirements still apply.
Native/front-of-action conditions use the present clock. Native geometric and
motion bounds remain unavailable (`None`); this change enables no execution.

RED evidence: the initial new tests observed five expected failures (missing
`object_held`, omitted/unmapped terminal criterion, and visual-only held PASS
with open/wrong/disconnected feedback). The complete-route test first failed
on the absent receipt API. The elapsed-TTL positive case then failed because
the repository returned no route for a valid already-started completion.
Those failures were corrected before the final verification.

Final verification (2026-10-05):

- Relevant CPU suite: **337 passed, 4 skipped**, 54.48 s.
- Ruff: **All checks passed** for four runtime sources and both affected tests.
- Mypy: **Success: no issues found in 4 source files**. Existing unused override
  notes for `ament_index_python.*` and `rclpy.*` remain informational.

Test command:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -m pytest -q tests/test_visual_full_effect_requirements.py tests/test_visual_worker_owner.py tests/test_visual_verification_repository.py tests/test_visual_owner_registration.py tests/test_rgbd_online_verification.py tests/test_visual_owner_repository.py
```

The new tests use actual in-memory and SQLite repositories with synthetic
software fixtures. They cover full terminal and hold sets, each missing hold
effect, missing terminal placement evidence, distinct later frames, failed
completion binding, exact TCP target rejection, receipt continuity, unchanged
budgets, elapsed TTL and rejection of native/late-start/wrong-result inputs.
No saved actual frame was retimestamped. A missing effect remains UNKNOWN and
cannot become CONTINUE. Device evidence acceptance and broader root integration
remain outside this software-only report.
