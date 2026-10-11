# R138 — ROOT 可选中间文本读取的无重试收束

实际模型 gpt-6-astra；规划者 /root/astra_status_plan；2026-10-11。纯元数据计划，待 ROOT 核对记录后收束；不暂停正在执行 R137 的同一 sole author。

## 原问题、原件与独立核实

工具 exec_command chunk 925f27，cwd /home/ningyd/文档/ChatGPT/BIGsmall，exit 2。ROOT 可选 rg 查询使用猜测的冻结叶路径 sources/worker.py，实际返回 No such file or directory。独立完整读取以下原件，SHA 与派发值一致：
- /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round137-p6-sql-layout-patch-recovery-20261011/implementation/root-read-path-failure/command.txt — 9c4b11731898ca6cc4a547e19b57336a40f48e48c00ffd8429bed9503b63cb94
- /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round137-p6-sql-layout-patch-recovery-20261011/implementation/root-read-path-failure/combined-output.txt — 1a421dc945a414c08ac477b295bc3d78767897ca466f95ee2571935e37cf0789
- /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round137-p6-sql-layout-patch-recovery-20261011/implementation/root-read-path-failure/finding.json — 46e129683f4927d13c35718146829b6bb99ec46b2dfbb3392ccdb786f2fe65af

原件只捕获 combined output，没有独立 stdout/stderr，不补造分流。失败属于路径假设导致的元数据读取失败，不是产品、SQL 或 pytest 失败；没有源修改或产品命令消费。根因是未从 authoritative index 取得确切路径便发起查询。本轮无需找到替代叶路径来完成任务，禁止重跑失败命令或修后重跑。

## 唯一恢复动作与范围

ROOT 明确放弃这次非必要的“中间冻结 worker 文本搜索”，保存本轮收束记录即可。没有需要实施的代码修复，也没有新 metadata 查询脚本。原命令和失败证据保留，不改成成功状态。

同一作者按已激活 R137 继续原有工作，本轮不干预、不暂停、不提出新实现指令。ROOT 等待作者实际完成有限最终冻结并交付完整绝对路径、SHA 和权威索引，再按 R127/R134/R137 原 source/fixture/proof 审查门禁读取真实最终文件；该未来审查是原门禁，不是重试本轮可选中间查询。路径未知时只使用作者交付的确切路径/索引或请求元数据，不猜叶名。

## 输入、前置与验证

本 JSON 固定 6 个元数据输入：上述三原件、R137 plan.md/plan.json/root-activation.json。正在变化的六条产品路径不读取、不冻结、不 pin，本轮不宣称它们保持某个中间 SHA。R137 激活记录表明作者已恢复，recovery3 与四终门仍 held、新产品预算 0。

ROOT 核对六输入与本计划后，仅新建本轮 input-check.json、root-activation.json（或 disposition.json）、validation.json、step-report.md/json、phase-summary-addendum.md，记录 optional read abandoned / no retry / author unaffected。验证限标准库文本/JSON/hash 读取这些元数据与记录无重试事实；不通过再次执行 rg 证明收束。所有旧历史/账本保留，不改写原失败。

## 预算与验收边界

新产品、测试、static、AST、import、compile、collect、probe、Git、actual/native/model/GPU 预算全部 0；原消费、剩余额度及 held 门禁全部沿用 R137/R134，不刷新。验收仅为忠实保存失败并放弃可选读取，作者继续、最终审查仍待最终冻结；不晋升任何软件、真实运行或正式研究状态。若后续确需这项可选中间查询，须另有真实依据及 Astra 计划，本轮不授权恢复它。

所有交接使用完整绝对路径及 SHA。

