# B0 前置与费用对账

`ced_selection.yaml` 已绑定经原始数据重建的六池与当前名义角色探针。真实 selection 与完整协议证据还未取得。本轮资格来源记录 native 为 `UNKNOWN`，可用权威 `UNAVAILABLE`，合格组 `0/9`。真实 B0 selection `NOT_RUN`，供应商实际发送仅发生在独立的名义探针。 [前置读回](prerequisite-readback.json) · [资格原始记录](../../round-harness-candidate-generalization-20261118/implementation/qualification.md)

| 字段 | 状态 | 真实消费者与取得方式 |
| --- | --- | --- |
| `pools_path` | `READY` | `_ced_pools` 读取明确文件，再验证六池完整、组互斥及开发数据排除。读取三组完整目录的 100、100、1000 条已发布记录，加历史 pilot 和冻结开发排除，重建 3,260 个不同组。重建文件与绑定文件逐字节一致。 |
| `role_probe` | `READY_PRIVATE_ORIGINALS_PRESENT` | 探针以当前现有加密 profile 实际运行 `gpt-6.1-sol`、320×240、`normalized_1000`。1 次 first 和 3 次 warm 全部通过，`verify_role_probe_evidence` 也独立复核通过。按真实 selection 的消费者复核模型快照、edge、OpenCV 源与角色包一致。R498 和此前 66 种扫描记录均未被用作该证据。 |
| `selection_evidence` | 等待真实 selection | selection 自身不消费此字段。后继 foundation 要求可独立审计的完整原始 selection，在同池、同角色下取得有效周期。原干跑被独立审计拒绝。 |
| `protocol_evidence` | `INCOMPLETE` | `run_rgbd_pilot` 仅将已提供目录随原件复制。`initial` 消费阶段调用 `verify_protocol_evidence`，对照 foundation 的池及独立资源回执。现有记录完整性有效、恢复 `1/200`、机会证据 `0`，总体 `valid=false`。 |

绑定文件来自历史干跑目录的 `pools.json`，内容是可从 1,200 条实际数据索引和所列排除原件重建的分配集合。该目录的运行摘要经实际 selection 审计为不可用。原路径的 SHA256 为 `e86ac4858fffb0040301c38a0481da7261bece6070e3531cfe9fc2e863c10618`。原工作树中此前缺失的开发数据已按本机归档核对 1,547 个文件和索引 SHA，完整数据保存在本机。 [池文件](../../../t8b-module/fix-round-1-dry-selection/pools.json) · [本机数据与入口核对](prerequisite-readback.json)

### 已执行的入口核对

在待验证的冻结工作树根目录执行。`B0_PY` 指向已有应用 Python。给每条命令传入独立的新输出目录。

```bash
PYTHONPATH=src:. "$B0_PY" scripts/run_rgbd_pilot.py --stage selection \
  --config configs/research/ced_selection.yaml --output "$B0_DRY_DIR"
PYTHONPATH=src:. "$B0_PY" scripts/probe_rgbd_roles.py \
  --config configs/research/ced_roles.yaml --output "$B0_ROLE_DRY_DIR"
PYTHONPATH=src:. "$B0_PY" scripts/prepare_rgbd_protocol_evidence.py --verify \
  --output artifacts/research/process/20261004-ced-development/t8-real-raw-development/verified-development
```

实际 selection CLI 绑定前后保存相同的 `assignments.json`，120 组分别配对 `0.5/1/2/5 s`，480 个已记录终态均为 `NOT_EXECUTED`，退出 3。以 `--execute` 请求但未提供已准入的服务、付费开关与角色探针时，同样保存 480 个未执行终态并退出 3。将完整配置副本的 `pools_path` 指向不存在的文件时，CLI 在建立任何分配目录前以 `FileNotFoundError` 退出 3，证明显式文件确经真实入口读取。角色探针干跑 `NOT_STARTED`，协议独立复核 `INCOMPLETE` 并退出 3。 [入口证据](prerequisite-readback.json)

### 后续真实入口的顺序

在已验证的同一源码与角色下消费现有探针。名义探针通过 `scripts/probe_rgbd_roles.py` 的 `run_probe` 复用加密 profile 的只读服务，再用 `verify_role_probe_evidence(Path(...))` 审核原件。真实 selection 前置全部满足后，以 `scripts/run_rgbd_pilot.py` 的 `run_ced_pilot(config, output, "selection", service=…, profile_id=…, execute=True, allow_paid=True)` 复用该只读服务。CLI 形式由已有授权凭据配置提供等效服务。运行配置副本放在 `configs/research/` 之外。审计会绑定该目录的 YAML 和应用源码，源码与已归档内容必须一致。

通过 `audit_ced_pilot_stage(Path(...), "selection")` 独立读取所有真实终态、原始请求和费用，只有获得有效周期才生成 foundation 配置副本并绑定 selection。foundation 继续用相同池及角色。协议目录须通过独立审计并绑定相同池。资源回执须由实际原件和已授权额度计算，再由 `scripts/freeze_rgbd_protocol.py --stage initial --expected-protocol-version ced.research.v2 --pilot … --output …` 复核；当前任何一项缺失都保持未取得状态。

### 真实费用与停止预算

历史四槽的 `costs.json`、worker 终态和供应商原响应按每槽唯一发送关联。3 次发送均有响应，供应商 usage 合计 2,069 token，另 1 槽没有发送。账单金额、币种和 3 条供应商发票关联均未取得，金额保持 `null`。公开证据以应用账本 ID、供应商响应 ID 和原件的 SHA256 关联，原始 ID 与原响应留在既有归档。 [逐条对账](historical-ledger-reconciliation.json)

当前角色探针独立记账。4 次实际发送、4 次成功、0 次重试，实际供应商 usage 合计 3,073 token。每条应用账本及供应商响应 ID 均以 SHA256 登记，4 条金额及币种仍为 `null`。用户已授权 B0 和新增开发批次云调用的请求次数与金额均无上限，账单仍以供应商实际回执为准。真实 selection 仍等待教师资格等前置，名义角色探针不授予物理或 edge 资格。 [本次实发台账](nominal-role-probe.json)

现行 selection 每个 assignment 本机任务限时 120 秒。角色策略设定 `max_reobservations=2`、`max_retries=0`、`max_no_progress=3` 和 `deadline_s=120`。网络条件按分配固定，发送和响应损失如实记账。后续执行按请求写入 `costs.json` 与 `wire-index.json`，已发送的异常、超时与迟到均计入。任务截止或原有安全、资格条件拒绝时停止对应执行并保留终态。供应商故障只按既有入口处理，保留已发及未执行的记录。

### 私有原件恢复

仓内相对探针目录由 `ced_selection.yaml` 绑定为 `cache/research/raw/20261119-b0-role-probe/current-nominal`。完整 47 件原件在 Git 忽略区，另有 BIGsmall 顶层持久工作区的私有 `cache/research/private-evidence/20261119-b0-role-probe/current-nominal.tar`。公开文件记录压缩前原件路径、字节数、逐件 SHA256 及私有归档 SHA256。

新检出先从私有归档恢复至同一相对目录，按清单逐项核对，再运行 `verify_role_probe_evidence`。还原后的独立复验已实际通过。历史部署数据目录同样按已记录清单恢复，实际 selection 继续验证池与排除。 [原件清单](nominal-role-probe-manifest.json) · [恢复复验](nominal-role-probe.json)

对 R07 已有的三份生成协议按分池、assignment、场景 SHA 与 group ID 重新核对。每份均含 3,260 个分配，与本次绑定池的精确匹配均为 0/3,260，恢复分配匹配均为 0/200。沿用这些生成器执行更多试次无法补足当前池。现行新建生成器会自行分池，机会证据生成入口仍标为 `NOT_IMPLEMENTED`；下一轮协议开发需接受此次冻结池并输出可由独立 reader 审计的原件。 [分池独立核对](protocol-pool-crosscheck.json)
