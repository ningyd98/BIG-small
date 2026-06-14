# API

This repository exposes a FastAPI application for planning, supervision, event autonomy, replanning, and completion reporting.

## Planning API

- `GET /api/v1/planning/capabilities`
- `GET /api/v1/planning/schemas/task-contract`
- `POST /api/v1/plans`
- `GET /api/v1/plans/{planning_id}`
- `POST /api/v1/plans/{planning_id}/dispatch`

Supported planning control modes currently advertised by the API:

```json
[
  "PERIODIC_CLOUD_SUPERVISION",
  "EVENT_TRIGGERED_EDGE_AUTONOMY"
]
```

`AUTO` is not advertised in Phase 6.1.

## Supervision API

- `GET /api/v1/supervision/capabilities`
- `POST /api/v1/robots/{robot_id}/status`
- `POST /api/v1/plans/{plan_id}/supervise`
- `GET /api/v1/plans/{plan_id}/supervision/decisions`
- `POST /api/v1/plans/{plan_id}/supervision/start`
- `POST /api/v1/plans/{plan_id}/supervision/stop`
- `GET /api/v1/plans/{plan_id}/supervision/status`

Supervision uses the configured repository for persistence and version compare-and-set.

## Event autonomy API

- `GET /api/v1/event-control/capabilities`
- `POST /api/v1/robots/{robot_id}/events`
- `GET /api/v1/tasks/{task_id}/events`
- `GET /api/v1/events/{event_id}`
- `POST /api/v1/tasks/{task_id}/failure-summaries`
- `GET /api/v1/failure-summaries/{summary_id}`
- `POST /api/v1/plans/{plan_id}/replan`
- `GET /api/v1/replanning/requests/{request_id}`
- `GET /api/v1/replanning/requests/{request_id}/result`
- `POST /api/v1/tasks/{task_id}/completion`
- `GET /api/v1/tasks/{task_id}/completion`

These endpoints use explicit Pydantic request models, URL/body identity checks, repository-backed persistence, and 404/409/503 responses where appropriate.

## Error handling

- `404`: missing persisted entity.
- `409`: body/URL identity mismatch or version conflict.
- `503`: required service or repository not configured.
- `400`: malformed request input.

## Verification

Behavior is covered by the Phase 6 acceptance script and the Phase 6 E2E tests.
