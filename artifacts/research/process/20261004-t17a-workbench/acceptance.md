# T17a 数据与视觉工作台验收

日期：2026-10-04。状态：**DONE（T17a 限定范围）**。T17b 正式研究结果看板未实施，不包含在本验收中。

本轮新增 RGB-D 数据作业的创建、取消、已发布进度、split 计数、正负例及 RGB/深度预览；服务器限制配置、规模与路径，读取 committed 元数据和校验后的样本载荷。原始采集时间保留，模型缺失不影响采集。仿真工作台默认 RGBD/VISUAL_PLANNING，并允许显式选择 CAPTURE_ONLY 或 VISION_CLOSED_LOOP。Live Run 分别显示在线完成和独立物理结果，0 步及 UNKNOWN 不补成任务成功。

## 验证

- 后端数据 API：8 passed，覆盖角色、配置限制、元数据校验、路径/数据集隔离与初始化竞态。
- 前端：12 文件 / 30 测试通过；typecheck、eslint、build 通过。构建仍有既有大 chunk 提示。
- 真实 EGL＋Chromium E2E：3 passed（58.0 秒），没有用 mock 图像替代采集。
- 独立只读代码审查未发现本轮数据路径和界面的阻断问题；初始化竞态另补回归。

## 三条真实路径

1. 无视觉模型的数据作业完成 1 个组，真实 RGB 和米制深度可预览，负例与原因保留，模型请求 0、任务 NOT_EXECUTED。
2. CAPTURE_ONLY 作业完成；另一个 VISUAL_PLANNING 作业因不可用服务如实 BLOCKED，在线/独立物理结果 UNKNOWN，没有物理成功标记。
3. 创建 100 组数据作业，在首次发布后取消。最终 CANCELLED，取消前后均有 1 个已发布组，其样本仍可读，模型请求 0。

证据位于 [e2e-final](e2e-final/)：[采集界面](e2e-final/real-dataset.png)、[模型缺失界面](e2e-final/model-unavailable.png)、[取消保留记录](e2e-final/cancel-preserved-data.json)。顶部历史 Phase10 状态横幅沿用既有 Playwright 启动 fixture；本验收只依据本轮真实数据/作业产物，不将该横幅当作硬件或其他阶段的新证据。

全仓 Python/静态质量门另记于阶段总结；T17a 的定向软件与真实功能验收不能代表整个仓库或 G1—G5 已通过。未操作真实机器人，未提交、推送或外部发布。
