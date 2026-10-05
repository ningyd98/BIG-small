# Bounded independent source review

Reviewed source generation below. No model calls, real renderer, physical
`mj_step`, or action episode was run. No execution/worker_runtime review.

## Findings

- **P2 — startup lease leak:** `PilotWorkerAttempt._abort_start` returns when
  `_attempt` is absent without releasing an already acquired lease. A concrete
  SQLite attempt fixture with `start_attempt` throwing before persistence leaves
  `status=LEASED`, `open_leases=1`, `attempts=0`. Cleanup must fence current
  worker/lease ownership, preserve any committed attempt, and release its own
  acquired lease. Reported to root and the pilot implementer before this report.
- **P2 — ended attempt evidence overwritten:** `PilotWorkerAttempt.__exit__`
  joins job worker/lease/attempt numbers but does not require the persisted
  attempt to remain uniquely open. Closing that attempt through the concrete
  repository before exit results in `EXTERNAL_TERMINAL -> FAILED`, rewritten
  `ended_at`, and replacement of `{'previous': 'retained.json'}` with
  `{'raw_episode_v3': 'raw_episode_v3'}`. Require current open-attempt fencing
  and retain existing terminal evidence. Reported to root and the implementer.
- The new derived recorder path allocates its ONLINE denominator before the
  transform, retains the clean SOURCE, checks pinned transform source bytes and
  fixed-recipe byte replay, and propagates failures without returning clean
  pixels. CPU tests confirm one camera acquisition, no controller command,
  shared original interval/camera state, and both allocations on transform
  failure. Source-derived provenance is not a physical-accuracy certificate.
- The pilot uses concrete SQLite queue/lease/attempt sources before backend
  setup, checks cancellation/deadline/source drift around initialize/reset/
  settle, and borrows one backend/capture/SkillExecutor. The fixed SENSOR recipe
  is applied once to the already captured frame; DYNAMIC motion remains an
  explicit recorded backend fault. Compiling all 120 assigned SceneSpecs kept
  **one camera** and identical arm/actuator XML while retaining assigned object,
  distractor, camera and light parameters. Backend explicit model XML evidence
  stores the SHA of the actual supplied UTF-8 XML. Terminal acceptance remains
  blocked by the two findings above for this reviewed generation.

## Commands and results

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -m pytest -q tests/test_visual_raw_recorder_transform.py tests/test_pilot_visual_worker.py tests/test_visual_raw_recorder_v3.py -k 'not real_render_disabled'
40 passed, 1 deselected in 17.80s

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -m ruff check src/cloud_edge_robot_arm/research/pilot_worker.py scripts/run_rgbd_pilot.py tests/test_visual_raw_recorder_transform.py tests/test_pilot_visual_worker.py
All checks passed!
```

CPU reproduction commands used Python heredocs under the same environment,
`TemporaryDirectory(dir='/tmp')`, and `tests.test_pilot_visual_worker.attempt`
with `assignments.__wrapped__()`:

```python
# Startup storage failure: replace only the unavailable persistence operation.
def fail_start(job_id, *, worker_id):
    raise RuntimeError('SOFTWARE_ONLY start storage failure')
owner.jobs.start_attempt = fail_start
try:
    with owner:
        raise AssertionError('startup failure was not raised')
except RuntimeError:
    pass
# Inspect concrete list_jobs/list_leases/list_attempts: LEASED / 1 open / 0.

# Existing terminal evidence: concrete repository mutation inside current owner.
with owner:
    source = owner.source
    owner.jobs.finish_attempt(source.job_id, attempt=1,
        result='EXTERNAL_TERMINAL', error='SOFTWARE_ONLY retained evidence',
        artifact_paths={'previous': 'retained.json'})
    before = owner.jobs.list_attempts(source.run_id)[0]
after = owner.jobs.list_attempts(source.run_id)[0]
# Results: FAILED; ended_at changed; prior artifact replaced.
```

The scene-only Python command compiled each unique assigned SceneSpec and
compared camera count, `ET.tostring(actuator)` and the complete
`panda_link0` body against the original asset. Result:
`unique_scene_specs=120`, `camera_count_unchanged=1`,
`arm_and_actuator_xml_unchanged=True`.

## Reviewed SHA-256

```text
4eabd3bf9cdf15b3942c4a740781a95c22ea684f410853c853d0336952d7a303  src/cloud_edge_robot_arm/vision/raw_recorder_v3.py
5c197d68afc7524507e40f28ace63ce0d9ef53584b8aecff5c6c34c3c2536a97  tests/test_visual_raw_recorder_transform.py
eda255682a2c1b6732ddaab99cfff7d120a62c4db448d27c7059c89a9af60fbe  src/cloud_edge_robot_arm/research/pilot_worker.py
478e5a4d856e1ec4a7b53e15f824ec1cf9136569ef88b7777cf0399dae65db49  scripts/run_rgbd_pilot.py
b7b6026b1173448de826e53253ae74f92b6b70ea46a404e10054c5cd451a62a6  src/cloud_edge_robot_arm/simulation/mujoco/backend.py
7e0835c58be96594240973060c6b53bd462bf3d773b525dcee14e06b3099d3cc  tests/test_pilot_visual_worker.py
```

## Targeted post-fix verification

The two historical P2 findings above are **resolved in the post-fix sources
below**. Startup cleanup now joins the original lease identity and the persisted
unique current open attempt, including a committed row whose start response was
lost. A failed start with no persisted row creates no synthetic attempt; it ends
the owned job through existing legal states and releases only that original
lease. A replacement lease and its new actual attempt remain unchanged.

Terminal cleanup now joins the unique open attempt before status transition or
`finish_attempt`. If the original attempt has already ended, it retains the
complete row (including timestamp, result, error and artifact paths), releases
only its own unchanged lease, and raises a source-unavailable error. It does not
publish success or rewrite that terminal evidence. Inspection was limited to
these cleanup/join helpers, terminal path, and four added regressions.

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -m pytest -q tests/test_pilot_visual_worker.py::test_start_attempt_storage_failure_releases_owned_lease_and_closes_only_actual_attempt tests/test_pilot_visual_worker.py::test_aborted_start_preserves_replaced_lease_and_new_actual_attempt tests/test_pilot_visual_worker.py::test_exit_preserves_already_ended_actual_attempt_evidence
4 passed in 4.01s

81dd1d02e4b264adba731eec07d6921042f933b795af4e68726e29f03b7ee3e2  src/cloud_edge_robot_arm/research/pilot_worker.py
629cb8e4bdbb0b54101547616818433ab3abc6f2b24549ceef18ce7d074a6510  tests/test_pilot_visual_worker.py
478e5a4d856e1ec4a7b53e15f824ec1cf9136569ef88b7777cf0399dae65db49  scripts/run_rgbd_pilot.py
b7b6026b1173448de826e53253ae74f92b6b70ea46a404e10054c5cd451a62a6  src/cloud_edge_robot_arm/simulation/mujoco/backend.py
```

Only those two concrete source findings are closed by this result. No real
model, renderer, physics/action episode, INITIAL/METHOD/FINAL acceptance or
execution/worker_runtime review was performed.
