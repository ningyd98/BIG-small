# Dashboard API

All dashboard routes live under `/api/v1/dashboard`.

## Read Routes

- `GET /capabilities`: pages, supported backends, allowlisted software experiments, write-operation names, and the empty hardware write list.
- `GET /summary`: authoritative console summary, safety summary, latest evidence, active jobs, provenance, and blockers.
- `GET /runtime`: runtime profile, commit, source tree hash, service health, and environment blockers.
- `GET /safety`: current safety gate snapshot. In Phase 10.2B this is dry-run and hardware motion is not authorized.
- `GET /acceptance`: real-robot acceptance ladder. The current level remains `NONE`.
- `GET /comparisons`: Phase 8 baseline metrics loaded from artifact summaries.
- `GET /audit-events`: replayable dashboard events.

## Evidence Routes

- `GET /evidence`: paginated, filterable, sortable evidence index.
- `GET /evidence-errors`: malformed evidence parse records.
- `GET /evidence/{evidence_id}`: redacted evidence detail for an indexed evidence ID.
- `GET /evidence/{evidence_id}/download`: download for an indexed evidence ID only.
- `GET /evidence/{left_evidence_id}/compare/{right_evidence_id}`: record-field diff for two indexed evidence records.

Evidence IDs are generated from artifact-relative paths. The API rejects path traversal and never accepts raw file paths from the browser.

## Write Routes

- `POST /experiments`: starts an allowlisted software experiment. Requires `x-dashboard-role: EXPERIMENT_OPERATOR` and `DASHBOARD_EXPERIMENT_WRITES_ENABLED=true`.
- `POST /experiments/{experiment_id}/cancel`: cancels a non-terminal software job. Terminal jobs are returned unchanged.
- `POST /safety/review-notes`: records a safety review note. Requires `x-dashboard-role: SAFETY_REVIEWER`. It does not change hardware authorization.

## WebSocket

`/api/v1/dashboard/stream` authenticates before accept, replays events after `last_sequence`, emits heartbeat events, rejects oversized messages, and accepts replay requests as JSON:

```json
{"last_sequence": 12}
```

The browser uses the same `/api` path through the Vite proxy; no token is placed in the WebSocket URL.

## Schema

The frontend schema is generated from the FastAPI app:

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
cd dashboard
npm run api:generate
```

CI checks generated schema drift with:

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
cd dashboard
npm run api:check
```
