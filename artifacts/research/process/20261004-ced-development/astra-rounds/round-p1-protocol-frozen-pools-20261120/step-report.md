# B0 冻结池协议准备 · 2026-11-20

普通 `--prepare` 已能按文件导入 B0 现有六池。GPT-6.2 Astra 制定本轮方案，GPT-6.2 Sol 实施和验证。独立协议复核显示完整性和池拓扑均通过，正式证据状态为 `INCOMPLETE`。本轮模型、付费、渲染、物理试次和正式采样均为 0。实际配置中的 `selection_evidence` 与 `protocol_evidence` 保持 `null`。[方案](plan.md) · [验证回执](readback.json)

## 原始失败与修复

实施前，33 项计划输入及 31 件历史原件的字节均与登记 SHA256 一致。实际运行原普通入口带 `--pools` 得到退出 2，stderr 为 `unrecognized arguments: --pools …`，stdout 为空。原独立证据读者再以旧排除集复核，因 7,563 个排除组漏登记 `g-0411d40a765c14987e48c552eb61af80` 拒绝归档。父件原字节 SHA、场景 SHA 和重算的 canonical group 均相符。该别名与两个历史重命名组、原物理键归入同一分量。新显式历史清单包含 7,564 组、6,361 个 scene SHA 和 7,440 个 physical key，未闭合组为 0。输入池与此清单在三类身份上的交集均为 0，池内物理身份重复为 0。排重覆盖登记的 31 件本地历史来源。[计划输入指纹](plan.json) · [原失败回执](readback.json)

参数只用于普通 `--prepare`。生成头把原文件 SHA256、解析后的完整内容摘要和来源路径绑定到原有六个生成 payload，导入的生成 seed 为空。系统复用原候选、故障、eligibility、证据审计及冻结规则。preflight 和合法 successor 均复核导入来源及派生六池，successor 继续共享原 allocation 命名空间。无参数路径沿用 seed 生成，实跑默认 seed 2026100507 通过 prepare 和 preflight，首条分配与导入池确实不同。[验证回执](readback.json)

## 持久目录实测

在私有持久归档相对目录 `20261119-harness/b0-frozen-pools-20261120/` 原位运行，`final-imported/` 和 `final-evidence/` 分别绑定本次真实生成头和证据清单。临时试跑原件也已留存。CLI 命令和完整 stdout、stderr、退出码在私有目录中。下面为对应重跑形式，使用新输出位置并将 `FROZEN`、`CATALOG` 指向登记原件。

```bash
python scripts/generate_rgbd_protocol_evidence.py --prepare --protocol "$PROTOCOL" --pools "$FROZEN" --history-catalog "$CATALOG"
python scripts/generate_rgbd_protocol_evidence.py --protocol "$PROTOCOL" --assignment recovery-0001 --attempt 1
python scripts/prepare_rgbd_protocol_evidence.py --pools "$PROTOCOL/pools.json" --output "$EVIDENCE"
python scripts/prepare_rgbd_protocol_evidence.py --verify --output "$EVIDENCE"
```

| 入口 | 退出码 | 实际结果 |
| --- | --- | --- |
| 导入 prepare | 0 | `READY_FOR_REVIEW` |
| 原 preflight | 0 | `PREFLIGHT_ONLY`。读取原池 `recovery-0001` 第 1 次序号，0 已尝试、200 未尝试，allocation 目录未创建 |
| 原独立证据 prepare | 3 | `INCOMPLETE`。完整性、拓扑通过，恢复 0/200，机会 0/2,400 |
| 原独立证据 verify | 3 | 原样复算同一结果。共 2,400 个机会尚无物理来源，`valid=false` |

独立读回逐池比较原文件、生成池和 `evidence-pools.json`，按原序核对 3,260 行内容摘要，逐条重算 2,400 个候选、200 份故障与 eligibility。六池大小依次为 selection 120、foundation 120、power 120、formal 2,400、recovery 200、OOD 300。用 B0 selection 的正常池读者载入现行配置，再给 foundation 读者在内存中指定同一冻结来源。两次读回与证据的整池对象精确相等，配置文件和 foundation 实际运行状态均未写入。[验证回执](readback.json)

同版五个专项模块共 295 项通过，无跳过。新增 19 项涵盖普通入口、顺序与来源绑定、历史重命名和同物理不同 camera/noise、跨池物理重复、额外 `_evidence`、残缺池、版本和字节漂移、派生重封行及历史父件缺失或伪造。原 seed、successor 同一账本、独立证据和 pilot/freeze 消费回归均运行。Ruff 检查和格式检查通过。[验证回执](readback.json)

## 正式采集边界

历史独立协议的实测为恢复 1/200、机会 0。本次导入池的独立证据为恢复 0/200、机会 0/2,400。正式机会采集器仍待实现。实际 recovery 仍需评审协议 hash、合格正式教师及真实执行窗口。后续须按原入口取得正式协议证据与实际 selection、foundation 来源，才可绑定相应配置。[执行前置与采集规则](plan.md)
