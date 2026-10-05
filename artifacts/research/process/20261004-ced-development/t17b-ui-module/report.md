# T17b 研究结果页面与只读前端接口

状态：软件验证通过，等待独立审查及 root 的全前端回归/浏览器 smoke。实际研究仍为 NOT_RUN，formal_accepted=false，独立接受的物理成功为0。本模块没有模型请求、实验调度、GPU/物理执行或正式结果验收。

## 范围与契约

仅创建 `ResearchEvidencePage.tsx`、页面测试、`researchResultsApi.ts`、client测试四个文件。API 实现、App/sidebar/router由 runner 负责；root 串行生成 OpenAPI，前端最终直接引用生成的 ResearchRunView/List/Goal/Method 类型，没有另维护响应模型。七文件 source snapshot 保存四 owned 源及只读 OpenAPI/schema/backend API 契约；具体 hash 见 `source-hashes.json`，完整四文件差异见 `review-package.diff`。现有 T11 和共享执行/安全实现未改动。

页面路由 `/simulation/research` 支持登记记录选择及 `run_id` 查询参数，仅执行 viewer GET。client 对同一运行 ID 编码后读取 evidence/export，不接受路径或 shell body，AbortSignal 传到 fetch；409等来源拒绝显示错误且不生成空成功结果。API allowlist/原始来源重算由后端负责，前端不以 hash、状态字符串或软件 PASS 开启实际验收。

页面显示协议 hash、冻结 N、全部分配与配对组分母、全部终止状态和分层，失败记录仅分页显示但完整保留在 JSON。目标的 diagnostic_status 与 actual_status 分列，无绿色物理成功徽标。原始95%区间、单侧界、原始p、完整冻结假设族的Holm校正p分列；显示统计值保留原精度，三位小数只用于数值可精确还原的短值。云请求总量包括远程 JUDGE，分角色计数与应用层字节、惩罚后P95及provider版本分别呈现。

候选、接受、启动和独立物理结果分列；规则分数和候选概率分别展示并说明规则分数不等于概率、不能充当校准风险。缺少条件判断和决策轮次来源时 canonical UNKNOWN/fallback 显示未记录N/A，episode指标另列。缺 source 的协议与分母保持N/A，不补0。完整 JSON 来自同一个加载响应，导出链接使用同一运行ID和后端同一 view 契约，包含失败/阻塞记录和完整分母。

当前 backend 未提供 B0 candidate 曲线、完整 G3机会/G4重复提交、校准风险及实际决策事件链。这些未补成虚构数据；页面仅显示已有记录与 NOT_RECORDED，后续实际 T16b 来源和扩展 typed契约齐备后才能验收其一致性。

## 验证

runner转交两个测试文件时尚无产品TS模块。使用已安装 Node `v24.19.0`（`/home/ningyd/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin`）记录预期 RED：两个目标模块不存在，日志 `red-ui.log`；未把旧 system Node 的 styleText 工具错误当作 RED。随后扩展分母、角色成本、缺失来源、JSON一致性及拒绝路径。初次 GREEN 有两处查询多匹配，改为精确生命周期文字/可访问列头；jsdom 无伪元素样式的桥接仅放在页面测试，不改产品或全局测试 setup。

最终命令：

```bash
npm --prefix dashboard test -- src/simulation/pages/ResearchEvidencePage.test.tsx src/simulation/api/researchResultsApi.test.ts
```

13 passed，2.52s，exit0（9页面＋4client）；相关 RGBDDatasetPage/VisualRunEvidence 同时回归共16 passed，2.66s。两者有重叠，不能相加当独立测试数。dashboard typecheck、四文件 ESLint/Prettier、最终 build均exit0，日志 `green-ui.log`、`build.log`；build仍报告既有antd/echarts大chunk警告。第一次从仓库根调用ESLint找不到dashboard配置，改在dashboard目录执行通过；schema切换时一处可选source_missing类型问题已按实际生成契约处理。

本模块未运行全前端suite或浏览器E2E，也没有 mock截图冒充真实结果验收。root负责后续全前端suite、浏览器smoke及独立审查，真实研究结果一致性仍等待T16b。原始测试日志、starting baseline和root生成日志保留。
