# R370：request_id 合同收口计划

实际模型 **gpt-6-astra**，agent `/root/astra_r367_sha_review`，2026-10-26。本次只规划，不修改、运行或提交。**现有 r369-report 足够，用户无需另写正式交回文档。**输入SHA/大小、映射和命令见 `plan.json`。

## 裁决与根因

保留 `updated_at=external.captured_at`，仅在原 helper 的 `InitialPlanningRequest` 中增加 **`request_id="external-utc-contract"`**。此非空标识与轮号无关。

内层 SceneSummary 先求值，原缺 updated_at 遮住了外层 request_id；上一轮静态审阅漏查了外层模型。**不撤销 updated_at、不重取旧 RED。**旧具名 RED 对原源码 `54b988…` 仍有效；当前源码 `bfe5e2…` 上的真实 GREEN 失败就是本轮 request_id RED，JUnit 已记录1failure/0error/0skip。

已逐字段核对：SceneSummary 两个必填字段现已提供；请求的两个必填字段补齐后为非空字符串。CommitContext/DecisionEnvelope 的 identity 相同，version/sequence/mode 为合法整数，mode 来自双方相同的 scene_version；CONTINUE 经真实枚举转换。时间带时区，valid_until==at 应由真实 validator 判 expired。这是静态判断，不保证不存在后续问题。

## 最小步骤与预算

- [ ] 复核输入hash，只补上述 request_id。合同文件保持4006B、SHA `e691e8d907a0efc863fcc700b86fb36f8dc22708c6fe8d6f30cf71428da8025b`；原断言、fixture、时钟输入及产品不改。
- [ ] 若需runner适配，只在新R370文件调整字面round/key/path/plan pin与单GREEN选择，静态对比核心逻辑不变；不为标签重复7项自检。真正capture/cleanup逻辑变化另定范围。
- [ ] 获本轮执行授权后，新目录、新ledger仅运行一次原短合同GREEN：**child30/outer60秒**，无重试；cleanup总15秒含TERM5，capture10。RED、自检、worker/DB/model、长跑预算均0；旧SPENT槽不退款复用。

验收：精确原node 1pass/0fail/error/skip、退出0，无超时；真实执行四个时间边界、expired-decision及输入timestamp/checksum未变断言。保留源前后、raw/JUnit、runner版本、清理和结果证据。短合同不代表完整UTC通过；600秒标准不变，不开放长跑或产品优化。

## 历史边界与收口

三条最终slot不等于仅三次尝试：runner与RED各有此前失败和用户授权reprovision。RED attempt1有JUnit，child实际执行；runner attempt1只有目录结构，原错误trace未见，不能声称失败原件全部完整。不为补历史元数据重跑。

旧7/7记录缺同版runner invocation/hash绑定，不能自动证明当前 `1f90b4…` 版自检通过。旧duration_seconds的0.856704/0.863552实际为wrapper区间，标签含capture，区别于原计划纯launch-to-reaped；只加注，不覆写原件。

新失败保留并交实际Astra，不预设第三缺陷已排除。回滚只撤新增request_id，保留updated_at与全部账证，不回退制造RED。`_sha`及copy→sha拆提交策略沿用，本次无Git写入。
