# Astra 活动状态检查等价修复计划

模型：`gpt-6-astra`。基线：`e20d228d5220c49b0194c4d2563ba23c2a3fde80`。状态：仅计划，未改产品、未启动真实试次。

31,238 owner checks cost 78.719s within real PRE–POST 150.403384s; unchanged Shield limit 8s failed STEP_TIMEOUT. Remaining 71.685s prevents claiming this repair alone meets 8s.

## 源码确认与测量边界

- NativeCollectionApplication.check_active calls policy and protocol; each reparses private protocol_json. _job_basis canonicalizes assignment each call, backend config model_dump/canonical repeats. These costs are not separately measured.
- _teacher_checkpoint_read opens/closes a read-only SQLite connection per check despite its docstring. It has one explicit read transaction, publication guard, before/after original DB identity checks.
- Within that snapshot get_job executes three times (initial, cancellation guard, lease reader); list_leases/list_attempts once each. Existing checks share a snapshot but fresh UTC and monotonic reads remain at original guard locations.
- publication_guard resolves path, uses PID/path RLock and flock; nested lease guard resolves again but recognizes held lock. DB lstat/resolve occurs before and after checkpoint. No measured per-subcomponent attribution yet.
- check_active also reads current owner clock/deadline, RSS, backend configuration and physics count. _guard then checks current robot hard stop and diagnostic watchdog at original point. Disk free-space check is preflight, not each check_active.

## 限定范围

- Diagnostic-only isolated profiling of the exact UTC teacher check path using temporary SQLite and fixed app inputs, no real physical trial.
- Primary repair: explicit teacher-lifecycle, thread/PID/database-bound reusable read-only SQLite connection; retain fresh BEGIN/rollback every checkpoint, original publication lock and both DB identity checks, every SQL and every clock/check at original location.
- Benchmark-gated SQL coalescing is permitted only within one existing read-only checkpoint transaction: snapshot-owned job_id -> immutable raw row cache, get_job constructs a fresh SimulationJobRecord on every call. Clear at exit before rollback; no reuse outside snapshot or writer path. Keep the cancellation and lease-reader calls, fresh time reads and original check order; only identical SELECT execution may be shared.
- Optional measured immutable scalar parse optimization only: private validated rss_bytes and physical_budget derived from original protocol bytes, with equality binding to same bytes on use; public protocol/policy remain fresh dicts. If immutability cannot be proved simply, omit.
- Tests and scoped process artifacts; explicit lifecycle close/invalidation; fix misleading read docstring.

## 不可改变

- No guard/check/capture decimation, no activity/lease/clock/config/RSS/disk permission-result caching. Only identical job raw-row SELECT in the same read-only snapshot may be coalesced as scoped; no SQL removal outside it.
- No modification to 8s PRE–POST gate, watchdog/deadline anchors, physical protections, per-step capture, raw bytes or historical evidence.
- No cache across transactions, tasks, PID, thread, database identity, or error-poisoned connection. No new repository-wide pooling or LOCAL_TEMPORAL behavior change.

## 实施顺序

- Revalidate all source hashes and dirty tree; record pre-existing modifications separately. Read existing tests first.
- Capture baseline component counts and paired offline benchmark (connection, transactions, SQL, protocol parse, path checks, clocks, total). Instrumentation cannot alter product path/order. Record environment and raw timing, never subtract probes from historical run.
- Add expected RED tests for connection reuse + fresh snapshots/current time, cleanup and errors; run prior authority suite baseline.
- Implement narrowly scoped owned reader, attach at teacher lifecycle preparation, close in all finalizers including preparation failure; no open transaction outside checkpoint. On exception rollback then invalidate/close; preserve primary exception and release flock even if rollback/close fails. Nested authenticated writer path stays unchanged; reject nested reader as today. Choose connection reuse, same-transaction row reuse and frozen scalar derivation individually from measured CPU benchmark; do not combine unmeasured claims. Private caches bind to exact original immutable bytes and expose no mutable objects. _job_basis/config live serialization remain unless a later Astra plan proves broader equivalence.
- Run fault matrix and adjacent suites; inspect diff then paired baseline/candidate offline benchmark. Produce step-report and phase-summary with software performance separated from real qualification.

## 负控与拒绝时点

- Separate process/connection writer between checkpoints: renewal visible, cancel rejected on next original checkpoint, release/finish attempt/status/fencing change rejected. Use synchronization rather than sleeps. Writer blocked only during active checkpoint, not across checkpoints.
- Advance UTC beyond lease while job rows unchanged; advance monotonic beyond task/deadline/watchdog. Retain original fresh clock reads and rejection locations. Heartbeat-failed flag between checkpoints rejects.
- Database replacement/unlink/symlink/path reassignment before entry and during body fails closed; corrupt/missing schema/SQL error/BEGIN failure/yield exception/rollback failure releases guard and leaves no active snapshot or reusable poisoned handle.
- Different PID/thread, nested reader and lifecycle close cannot reuse connection. Existing writer transaction still uses authenticated writer without reader connection.
- Robot disconnected/estop/collision, RSS and physical-budget excess, backend config mutation rejected at same original checkpoint; protocol binding mutation rejected or reparsed without stale permission.
- Disk preflight under 32GiB fails at original preflight; file write/ENOSPC remains recorded failure through existing path. Do not invent per-check disk guard or weaken existing guard.
- Diagnostic authorize watchdog rejects at original _guard call and original anchor, including PRE+8s accounting unchanged; no skipped capture/guard count or operation-ID changes.
- Within same checkpoint call get_job, mutate the returned record/draft, then get_job again: fresh record must reflect original row, not caller mutation. Repeated calls keep identical failure semantics for missing rows. Next checkpoint rereads committed job changes; nested writer never accesses row cache. Trace exact SELECT counts (3 -> 1 only per same job snapshot), lease/attempt remain queried, UTC/monotonic/check call counts unchanged.

## 验证

- Targeted tests in tests/test_native_collection_authority.py and tests/test_native_checkpoint_diagnostic.py; adjacent native registered/calibration collection and visual worker owner/repository suites.
- Verify connection and identical job SELECT counts reflect selected repairs, while BEGIN/rollback, lease/attempt SQL and guard/check/clock counts remain per checkpoint; outside checkpoint _teacher_checkpoint_connection is None. Row-derived records are distinct including nested mutable fields.
- Run alternating baseline/candidate offline pairs with fresh temporary DB fixtures, report median/range and total wall time, not synthetic pass against 8s. No hardware speedup conclusion from offline benchmark.
- Ruff/type checks appropriate to changed files with baseline comparison for existing failures; any new unexpected failure or broader root cause requires next Astra round.

## 真实运行前置

- No real trial authorized by this plan execution alone. Before separately registered fresh trial: all negative controls pass, source inventory renewed, artifact budget/disk/EGL/clock/worker prerequisites checked, single lease zero retry, immutable fresh output and normal cleanup.
- Preserve exact original action recipe, 8s gate, per-step capture and physically equivalent controller; keep formal research and development ledgers separate.

## 计划生成过程

- Planning command python was unavailable (exit 127); used installed python3 to serialize artifacts. No product code or test ran, no product failure inferred.

## 验收边界

This round succeeds only as equivalent software repair with fresh-state safety evidence and measured local overhead improvement; real action completion, <=8s, stop-effect evidence and formal acceptance remain UNKNOWN/NOT_ACCEPTED until separately evidenced.

Historical round and private archived raw remain untouched. Reference retention/readback hashes; do not present public manifests as full remote reproduction package. New failures, RED/GREEN logs, benchmark raw and step report retained. Implementer must recheck input manifest before editing; changed applicable inputs require reconciliation/new plan as needed.

## 输入 SHA256

| 路径 | SHA256 |
| --- | --- |
| `src/cloud_edge_robot_arm/research/native_collection_application.py` | `409911c4e218d3b070ea1eed9ddf3682bcd382332e5352bb3da09cb1e221fb32` |
| `src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py` | `cdd3c626c15331dfef43771619e958158c55ba75f664f39a976516cdcebbb7c1` |
| `src/cloud_edge_robot_arm/simulation_runtime/worker.py` | `35844661596f08b704ee4b5a04a16c487f2d708e8283918e4353208e318b433e` |
| `src/cloud_edge_robot_arm/vision/worker_owner.py` | `8128f8253e82deef5fab75fe5d24e79cd896c5588b9548b5ea4afe563731a21c` |
| `src/cloud_edge_robot_arm/research/native_checkpoint_diagnostic.py` | `3d09907a8dadf5f9510971765d065cb511556328e1636ba9689f88a3ae5b3d11` |
| `tests/test_native_collection_authority.py` | `09f886bd68597a8e40ce00e1737cd59f356ca6a02d43a2b1b0492a211f157412` |
| `tests/test_native_checkpoint_diagnostic.py` | `f89afc10c80a3a9c34d96b5934bcdf2610c8e454a918b03cd8def51aea2a86da` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-whole-action-20261120/step-report.md` | `1e6491cbd15139ac2debad32ba84b4b19abf665115433dd690d3dd449f962cd2` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-whole-action-20261120/phase-summary.md` | `f0be70dc15ebb4336abfb4eabf3948a1d4b54a8258d0406411a020ee476282cf` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-whole-action-20261120/action-timing.md` | `5788ac34229122ffe94e52d78ace4ba904b646ea8c4497f023725786a2e8138a` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-whole-action-20261120/action-timing-readback.json` | `4012915b35fc6a1a7e8fdf6f173e373a94375cd0a2b8eced1c1f8dcab8decbf3` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-whole-action-20261120/retention.json` | `9b64b5ff8d013c8b41b61741a89b388dbffc0ec561fd048fdc035f9fe86a6cd2` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-whole-action-20261120/run-registration.json` | `4a31cc0705ee761942967503fbe3c7ae9bc2e9e442bcb069eb0bea943541e305` |
