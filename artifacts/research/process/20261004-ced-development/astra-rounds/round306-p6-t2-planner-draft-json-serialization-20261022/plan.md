# R306：PlannerDraft 的 JSON 序列化修复与双库接续

实际模型：**gpt-6-astra**。仅规划，未实施或运行测试。

## 真实失败和根因

R302 G1 micro 已通过；新 dual child1/wrapper0，32.973秒，capture完整，11被动事件0丢弃，343资源尝试/343清理。已越过原 reserve_plan RPC失败，实际在 complete_plan→本地 `_transition` 的 `asdict(draft)` 抛出 TypeError，真实commit-loss仍0次。ROOT独立assessment与SPENT结算已存在，两个wait均HELD0/1。

PlannerDraft明确继承Pydantic BaseModel；dataclasses.asdict要求dataclass。附近robot_state/observation和已有bootstrap模型均使用JSON model_dump。修复只需一处表达式，不应放宽LocalEnvelope严格校验。

## 一行产品修复

文件 `src/cloud_edge_robot_arm/vision/worker_runtime.py`：

```python
"draft": None if draft is None else draft.model_dump(mode="json")
```

只替换原唯一 `asdict(draft)` 表达式，None分支及所有其他字节不变。asdict仍有其他用途，不删导入。codec、TTL、wait_cap、权限、事务、原全部测试/观察器保持。

保留原G1与失败；实际TypeError就是本次修复失败基线，不重新运行耗时RED，不改R302 legal_RED标签。新增一个冻结小型回归，验证实际生产表达式的None、sentinel、含嵌套scene/datetime的完整模型、JSON roundtrip、字段保留/无共享变异与无宽松fallback；不得仅测试重复手写的替代表达式。完整真实dual承担实际运行链路证明。

## 额度与顺序

| 身份 | 次数 | child/outer | 前置 |
|---|---:|---:|---|
| 新R306.observer_serialization | 1 | 120/240秒 | G2精确源码/argv已ROOT审阅 |
| 新R306.dual_behavior | 1 | 600/900秒 | 小回归通过 |
| 原R302.wait_memory | 原剩余1 | 原600/900秒 | 新dual通过、G2来源接续 |
| 原R302.wait_sqlite | 原剩余1 | 原600/900秒 | 前一wait通过 |

均0 retry。**不新增wait身份或复制其额度**；旧R302 dual永久SPENT1/0。完整精确调用见plan.json。

Sol直接一行修复并新增回归。ROOT复用当前compact runner和passive插件的新身份副本，仅改R306路径/计划pin/两key集合等身份信息；原runner7bbc、插件bbede及fixture a280保持。保留R304 unit缺目录修正。ROOT一次有限diff/native/source/argv审阅后执行新micro、dual，无新通用工具链或旧gate复跑。

## G2来源和原wait接续

完整归档原产品文件9b94及模式/base64，记录一行diff、新实际hash与新旧映射。其余产品/source pins原样核对；不递归重审68历史容器，不改旧plan期待值。

新dual完整通过后，归档R302当前source-gate/root-source-acceptance及角色原件。按本轮明确授权CAS推进原wait所读取的R302操作gate：仅把vision/worker_runtime.py的当前pin改为G2，追加本轮immutable证明；原round、五命令表、runner7bbc、pluginbbede、fixturea280、87564回归均保持。ROOT重新接受该有限G2映射，然后正常reserve尚HELD的两个原wait。旧已消耗条目不改；历史gate原字节可从归档按pin恢复。不能直接伪装旧源码仍适用。

## 验收和停止

必须实际完成四处真实durable COMMIT后同连接关闭、四次重启无权限证明、same-owner NEW_COMMIT/历史重复/变更拒绝及预算不回填。随后两wait须保留真实阻塞与两个时钟域拒绝。所有原断言、资源分母、hook恢复、0被动丢失、完整raw/实际DB归档和cleanup均必需；wrapper0不是行为通过。

出现下一真实失败保留并停止该链，进入下一Astra计划，不悄悄扩大修复或重跑旧key。选定链闭合后ROOT按既有授权明确路径提交推送；不宣称整个T2/P6/T12/native/formal完成，旧35DB/90sidecar缺口保持。

输入SHA256、ROOT已结算实物和只读观察见plan.json与input-observation.json。
