# R368 sizing 结果交回 Astra（2026-10-26 00:05 +08:00）

- 触发：用户 23:38 授权执行 `runner_contract_01` 与 `utc_memory_sizing_01`
- 边界：两条命令各一次、无重试、无新诊断器、未改产品或测试、未推送

## 1. 执行摘要

| 命令 | 结果 | 关键数字 |
| --- | --- | --- |
| `runner_contract_01` | **PASS**（5/5） | 缺 JUnit 收口、TERM、KILL、输出超限、预检拒绝全部通过 |
| `utc_memory_sizing_01` | **NOT_PASSED**，非超时 | pytest **1,113.62 s**，1 test / **1 failure** |

runner 自检确认了六个缺口的修复（原子消费、PID/PGID/starttime、deadline、限额、finally 收口、TERM/KILL 总账 15 s）。

## 2. 决定性发现：该 UTC 节点在当前产品上不可能通过

失败不是 UTC 断言，也不是超时，而是构造请求时缺必填字段：

```
E  pydantic_core.ValidationError: 1 validation error for SceneSummary
E  updated_at  Field required
tests/test_operational_runtime_closure.py:5612
```

测试代码：

```python
scene=SceneSummary(scene_version=contract.scene_version)   # 缺 updated_at
```

产品模型 `src/cloud_edge_robot_arm/cloud/planning/models.py:42-46`：

```python
class SceneSummary(BaseModel):
    scene_version: int = Field(ge=0)
    updated_at: datetime          # 必填，无默认值
```

时间线（`git blame`）：

- `updated_at: datetime` 自 **2026-06-13**（`335a65d4`）起即必填；
- 该测试行最后修改于 **2026-10-24**（`dd9df375`），仍未传。

**含义**：无论把 cap 调到 3,600 秒还是 36,000 秒，这个节点都会在第一个 exercise 结尾崩掉。之前两次 600 秒超时把该缺陷完全遮住了。

## 3. 成本修正（外推，非实测）

| 范围 | 估计 |
| --- | --- |
| 单个 exercise（含走到失败点前的全部断言） | **1,113 s**（实测） |
| memory backend 3 个 exercise | ≈ 3,300 s |
| 双 backend 6 个 exercise | ≈ 6,600 s |

后两个 exercise 未执行，所以是外推。结论：原"双 backend 合计 600 秒"比实际需求小一个数量级。

## 4. 修复语义分析（供裁定，不是执行建议）

`check_scene_sufficiency()`（`cloud/planning/pipeline.py:67-83`）在
`request.observation is not None` 时**提前返回**，只用 observation 的 `captured_at`
判断新鲜度；本用例传入了 `observation=external`，因此 `scene.updated_at`
**不参与任何新鲜度判定**，只受 Pydantic schema 约束。

生产侧同构写法（两处）：

```python
SceneSummary(scene_version=1, updated_at=observation.captured_at)   # vision/evaluation.py:229
SceneSummary(scene_version=1, updated_at=self.observation.captured_at)  # vision/execution.py:1099
```

因此三个候选：

| 候选 | 语义 | 评价 |
| --- | --- | --- |
| `updated_at=external.captured_at` | 与生产调用点一致 | 与现行代码同构，改动最小 |
| `updated_at=datetime.now(UTC)` | "构造时刻" | 与生产不一致，但在本分支不被使用 |
| 固定常量 | 完全确定 | 可读性差，且掩盖真实语义 |

本执行方不代填，交由 Astra 裁定。

## 5. 需要 Astra 决定

**Q1 `updated_at` 的取值语义**（上表三选一，或另定）。

**Q2 修复后的测量顺序**：建议先跑单个 exercise（约 1,100 s，确认修复后行为正确），再谈完整节点；避免又一次小时级空跑。

**Q3 600 秒验收标准**：在 ~6,600 秒量级下必须被正式替代（按 backend 拆分 / 提高 cap / 该节点退出验收），三选一都需要明确记录。

**Q4 下一次长跑前的 runner 修补**：
- `result.json` 的 `duration_seconds` 为 `null`（v2 未写入 supervise 起止时长）；
- 输出限额检查间隔 2 s，合成用例中 1 MiB 上限被写到 40 MiB 才终止。

修则 runner 哈希变化、`runner_contract_01` 需重跑（当前槽位已 SPENT）；不修则以现有缺口继续。

## 6. 当前状态

| 项 | 值 |
| --- | --- |
| 产品 | `local_temporal.py` `c8a5a5a4…`，121,341 B（`_copy` + `_sha`），**未提交** |
| 合同测试 | `tests/test_local_temporal_sha_contract.py` `990aa654…`，**未跟踪** |
| R368 账本 | `runner_contract_01` SPENT PASS；`utc_memory_sizing_01` SPENT NOT_PASSED |
| R365 旧 UTC 槽 | 已退役，保持 HELD 0/1 |
| HEAD | `dd9df375…` 未变，未推送 |

## 7. 建议

先 Q1（一行语义决定）→ 修测试 → 单 exercise 复测 → 再谈 Q3 的预算替代。
`_sha` 按前次裁决保留；它既不是本次失败的原因，也不影响该节点的通过与否。

## 8. 证据

- `implementation/runner_contract_01/{result.json,completion.json,cases/}`
- `implementation/utc_memory_sizing_01/{result.json,completion.json,junit.xml,stdout.txt,source-before.json,source-after.json,resources/}`
- `sizing-report-20261025.md`、`implementation/r368-ledger.json`
