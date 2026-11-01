# R368 memory sizing 结果（2026-10-26 00:00 +08:00）

- 命令：`utc_memory_sizing_01`，单节点
  `tests/test_operational_runtime_closure.py::test_local_new_schema_ignores_utc_jump_but_external_does_not[memory]`
- 预算：child 3,600 s / outer 3,900 s，一次、无重试
- 结果：**未通过**（`NOT_PASSED`），但**不是超时**——测试跑完第一个 exercise 后因产品/测试 schema 漂移失败

## 1. 实测数字

| 项 | 值 |
| --- | --- |
| pytest 总耗时 | **1,113.62 s**（junit `time="1113.625"`，testcase `1112.862`） |
| child 退出码 | 1（断言/异常失败，非超时） |
| JUnit | 1 test / **1 failure** / 0 error / 0 skip |
| 节点匹配 | `nodeids_exact=true`，源身份前后一致 |
| 资源侧车 | 1 个 sidecar，1,015,169 B |
| runner closure | `reason=null`，进程正常回收 |

**1,113 秒只跑到第一个 exercise 的结尾**，不是整个节点。

## 2. 失败根因（与 `_sha`、与 600 秒无关）

```
E   pydantic_core._pydantic_core.ValidationError: 1 validation error for SceneSummary
E   updated_at
E     Field required
tests/test_operational_runtime_closure.py:5612
```

测试构造：

```python
value = InitialPlanningRequest(
    user_instruction=contract.user_instruction,
    observation=external,
    scene=SceneSummary(scene_version=contract.scene_version),   # 缺 updated_at
)
```

产品模型 `cloud/planning/models.py:42-46`：

```python
class SceneSummary(BaseModel):
    scene_version: int = Field(ge=0)
    updated_at: datetime      # 无默认值，必填
```

`git blame`：

- `updated_at: datetime` 自 **2026-06-13**（`335a65d4`）起就是必填；
- 该测试行最后修改于 **2026-10-24**（`dd9df375`），仍未传该字段。

结论：**这个 UTC 节点在当前产品上不可能通过**，与 600 秒预算、与 `_sha` 改动都无关。此前的两次 600 秒超时把这个问题完全遮住了。

## 3. 对成本量级的修正

- 单个 exercise ≈ **1,113 s**（含全部断言，直到构造返回值时才失败）；
- memory backend 共 3 个 exercise → 约 **3,300 s**；
- 双 backend 共 6 个 → 约 **6,600 s**。

即 600 秒预算比实际需求小一个数量级；3,600 秒也不够。以上是外推，不是实测——因为测试在第一个 exercise 结束就失败了，后两个 exercise 没有执行。

## 4. runner 的已知缺口（如实记录）

- `result.json` 的 `duration_seconds` 为 `null`：v2 只记录了终止原因与进程链，没有把 supervise 的起止时长写进去；pytest 自己的耗时可从 JUnit/`stdout.txt` 读到。
- 输出限额仍有 2 秒检查间隔的过冲（自检用例中 1 MiB 上限被写到 40 MiB 才终止）。

两项都不影响本次"失败原因"的判读。

## 5. 建议（交实际 Astra）

1. **先修测试缺陷**：在 `SceneSummary(...)` 中补 `updated_at`。取值语义需要裁定（用 `observation.captured_at`？`contract` 里的时间？还是显式固定值），这决定该用例检查的是什么，属于产品/测试语义决定，不应由执行方顺手填。
2. **再重估预算**：即使修好，双 backend 也在 6,600 秒量级；600 秒验收标准需要正式替代（Astra 的 B 方案）或更大幅度的性能改造。
3. **重测顺序**：先跑单 exercise（约 1,100 s）确认 schema 修复后行为正确，再谈完整节点，避免又一次小时级空跑。
4. 修复测试后，`_sha` 的 20% 收益才有意义；在那之前它不影响结论。

## 6. 证据

- `implementation/utc_memory_sizing_01/{result.json,completion.json,junit.xml,stdout.txt,source-before.json,source-after.json}`
- 资源：`implementation/utc_memory_sizing_01/resources/*.json`
- 账本：`implementation/r368-ledger.json`（两项 SPENT，sizing `validation_pass=false`）
