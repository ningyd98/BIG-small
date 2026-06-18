# Simulation Parameter Schema

`GET /api/v1/simulation/parameter-schema` 是 Phase 11 参数编辑器的 schema 入口。它声明权威模型、枚举、数值限制和禁止字段。

## 权威模型

- `ExperimentConfig`
- `ScenarioDefinition`
- `ExperimentDraft`

## 主要枚举

- Backend：`MOCK`、`MUJOCO`、`ISAAC_SIM`、`MOVEIT_DRY_RUN`
- Run type：`SINGLE`、`BATCH`、`SWEEP`、`PAIRED_BACKEND`、`MODE_COMPARISON`
- Run status：`QUEUED`、`VALIDATING`、`STARTING`、`RUNNING`、`FINALIZING`、`SUCCEEDED`、`FAILED`、`CANCELLED`、`BLOCKED_BY_ENV`
- Control mode：`PCSC`、`ETEAC`、`AUTO`

## 禁止字段

`shell`、`command`、`cmd`、`script`、`path`、`module`、`environment`、`env`、`executable`、`runner`、`runner_name` 和 `pythonpath` 都会被后端拒绝。

## 校验原则

前端 builder 会先做客户端校验，但后端必须重新校验。任何 extra 字段都不得进入执行层。

