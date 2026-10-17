# R229 有限只读 Git 盘点计划

> 实际规划作者：gpt-6-astra /root/astra_status_plan。仅计划，ROOT 完整审核后才能运行。

目的：为后续已验证交付取得真实本地 Git 状态，不提前选择提交路径、分支或执行交付。用户 AGENTS 的明确路径提交、推送和三 SHA 核验要求继续有效；旧 R155 的 28 次 Git 已全部耗用。

普通文件观察确认主树 .git 为目录，HEAD 指向 refs/heads/research/20261004-continuation，loose ref 当前为 34c7a5595b72a3b23f4d0ca4d31aa4154cd6f24e。这不是新 Git 核验。STATE/PHASE 仅保存本时点 pin；R222/R228 只证明源码范围及元数据，T2 仍未完成。

## 唯一新增范围

ROOT 可在独立源门通过后执行三个本地只读命令，各一次、60 秒：C1 porcelain-v2 NUL status（未跟踪目录仅摘要）；C2 本地 heads/remotes 的 SHA 与上游引用映射；C3 registered worktree 元数据列表。精确 argv、有限环境和输出路径见 plan.json。一个 240 秒标准库 driver 只编排这三条，不提供额外 Git 权限。

不运行 stage/commit/push/fetch/ls-remote，不读取或打印完整 Git 配置、凭据、数据库、SDK 或权重内容，不递归展开未跟踪 raw 树，不进入其他 worktree。禁用可选 index 刷新与外部 fsmonitor；不 reset/stash 主树。

## 门禁与结果

- [ ] ROOT 全文读取计划，正常核实固定历史 pins；当前 HEAD/index/状态文件按真实时点重新记录，不要求永久等于规划快照。
- [ ] ROOT 先保存 implementation/run-census.py，再全文审源、SHA、三个 argv/env 与独占输出路径；协调短暂无源码/Git并发写入窗口。
- [ ] 每条实际调用前预留自身一次额度；独立保存完整二进制 stdout/stderr、result 与外层 actual tool return。任一失败或超限立即停止，不重试。
- [ ] 每条 stdout 上限 32 MiB、stderr 2 MiB、记录最多 100000；超过即保留部分输出并标不完整。用户显示仅 ≤6000 UTF8 字节摘要。
- [ ] 正确解析 NUL 路径、重命名及空上游，核 main HEAD/index 前后不变。其他 worktree 不宣称 clean；cached remote ref 不宣称 live remote 验证。
- [ ] 保存 census.json 和步骤报告，ROOT 根据实际结果另立有限交付计划；不在本轮更新产品状态或验收。

路径归属默认 UNATTRIBUTED。只有和真正历史接受凭据相符才能说明来源，不能据目录名称判断用户原有工作。未跟踪目录摘要不是完整文件清单；选定清单也不能冒充完整远端 raw/数据库复现包。

本轮实际规划执行 Git 0、网络 0、产品/测试 0。三个新 Git 槽和编排均 HELD，T2 原 GREEN7、R223 与所有旧预算不变；任何意外需保全后新 Astra 计划。
