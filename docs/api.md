# API 说明

仓库提供一个 FastAPI 应用，覆盖云端规划、周期监督、事件触发自治、重规划和完成证据上报。接口说明只描述软件边界，不表示浏览器或云端模型可以直接控制机械臂。

## 规划接口

- `GET /api/v1/planning/capabilities`
- `GET /api/v1/planning/schemas/task-contract`
- `POST /api/v1/plans`
- `GET /api/v1/plans/{planning_id}`
- `POST /api/v1/plans/{planning_id}/dispatch`

当前 API 对外声明的规划控制模式是：

```json
[
  "PERIODIC_CLOUD_SUPERVISION",
  "EVENT_TRIGGERED_EDGE_AUTONOMY"
]
```

`AUTO` 是后续策略层，不在 Phase 6.1 的规划能力里对外声明。

## 周期监督接口

- `GET /api/v1/supervision/capabilities`
- `POST /api/v1/robots/{robot_id}/status`
- `POST /api/v1/plans/{plan_id}/supervise`
- `GET /api/v1/plans/{plan_id}/supervision/decisions`
- `POST /api/v1/plans/{plan_id}/supervision/start`
- `POST /api/v1/plans/{plan_id}/supervision/stop`
- `GET /api/v1/plans/{plan_id}/supervision/status`

监督状态通过配置好的 repository 持久化，版本更新使用 compare-and-set，避免旧结果覆盖新状态。

## 事件自治接口

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

这些接口使用明确的 Pydantic 请求模型，并校验 URL 与 body 中的身份字段。找不到持久化对象时返回 `404`，版本冲突或身份不一致返回 `409`，依赖服务未配置返回 `503`。

## 错误码

- `400`：请求格式或字段不合法。
- `404`：持久化对象不存在。
- `409`：URL/body 身份不一致，或版本冲突。
- `503`：必要服务或 repository 未配置。

## 验证来源

Phase 6 验收脚本和 Phase 6 E2E 测试覆盖这些接口的关键行为。后续新增 dashboard API 时，应单独说明只读能力、写操作 allowlist 和硬件写入禁令。
