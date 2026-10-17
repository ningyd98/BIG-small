# R148：放弃多余账本预检，恢复原 new19 单次授权

实际规划者：gpt-6-astra（/root/astra_status_plan），2026-10-12。状态：冻结，待 ROOT 复核激活。本轮仅元数据处置，完整绝对输入路径、字节数及 SHA256 见同目录 plan.json 的 inputs。

## 原问题与独立核查

原工具 912a9e 实际 exit 1。额外文本预检把 runner 与 author ledger 都放在 R127/implementation 下读取；正确账本位于 R127 轮次根目录。失败命令成功读取并打印 runner 源文后，在错误账本路径产生 FileNotFoundError，后面的 fixture index 读取未到达。runner 只被当作文字读取，没有执行；pytest 未启动、源码未变、new19 未消费。

原 command.txt、完整 combined-output.txt、tool-result.json、finding.json 和 source-index.json 已保留；只有工具返回的完整 combined output，独立 stdout/stderr 不可得，不重构。不得将此错误记作产品或测试失败，也不得重跑以补捕获。

独立读取正确 author ledger 与 R147 frozen plan 的 inherited_new_green19，均为 authorized 1 / used 0 / remaining 1，argv/cwd/env/输出一致。原 runner 已正确使用 parent.parent 定位轮次根账本，无须修复。ROOT 原 release receipt 记录 252 checks、foreign 实际 1PASS、真实事务/拒绝/生命周期、原 runner 与额度核对，已释放原 new19。失败取证 index 也记录输出与 basetemp 尚不存在。

## 最窄处置与范围

**ABANDON_OPTIONAL_PREFLIGHT：放弃该多余预检；零重试、零替代预检读取、零脚本修改、零产品/测试修改、零新增产品验证预算。**

ROOT 复核本计划及有限元数据 pins 后，新增本轮 input-check.json、root-activation.json、disposition.json、step-report.md/json，并在现有阶段总结追加事实即可。旧计划、原错误、raw、index、账本快照全部保留。无需重新检查整棵 fixture 或产品正文。

同一作者 /root/p6_stage_a_sol 在 ROOT 激活后，沿原 R147 已批准流程调用原 runner 的 new_green 一次。精确授权为：

- 原计划：/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round147-p6-foreign-repository-fixture-lock-recovery-20261012/plan.json，/inherited_new_green19。
- 原账本：/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round127-p6-private-authority-lifecycle-repair-20261011/command-ledger.json，/commands/new_green。
- 原 runner：/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round127-p6-private-authority-lifecycle-repair-20261011/implementation/run-budgeted-command.py。
- cwd：/home/ningyd/文档/ChatGPT/BIGsmall。
- 调用：.venv/bin/python 加上述完整 runner 路径，再加 new_green。

原 pytest 精确 argv/env、输出路径、预留后执行机制与生命周期 cap 22≤64 全部继承，不复制成新额度。不存在新的 R148 pytest 命令。原 GREEN20 的 19PASS1FAIL、foreign 单节点 1PASS、CPU positive 1PASS 及各 spent1/0 历史均不改写、不重跑。

## 前置、验证与验收

ROOT 必须先复核计划与输入仍适用并写激活；继续依赖既有 R147 source/fixture/proof 放行，不允许中途源码漂移、已消费命令或证据目录冲突。意外变化则停止相关流程，不自行再猜路径或增加预检。

本轮只做 stdlib 元数据文本/JSON/hash 和结构化计划保存。激活后的 disposition 不需要任何替代 reader。原 new19 运行及其 raw/result/JUnit、真实资源关闭验证继续受原合同约束；出现新失败先停并交实际 Astra。

本轮完成只表示元数据问题已处置，不代表 A 软件验收。原 new19 的实际结果与新鲜独立终审仍待完成；Stage A 上限仍是 LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO。不激活 B/C/D，不声称 native、physics、actual 或 formal 通过。CPU 注入结果的 positive control 仍仅为软件证据。

