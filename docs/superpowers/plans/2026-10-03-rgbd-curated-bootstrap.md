# RGB-D 精选集先用实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** 按用户“给我找精选集先用”部署可直连的小规模真实 RGB-D，形成可读样本、预览及 CPU batch。

**Architecture:** 延用 datasets.external 的固定来源、预算账本、离线契约、JSONL、预览和回放入口，增加独立 graspclutter6d_curated 变体和轻量 FiftyOne 导出读取器；保留原完整数据目标与断点。精选验收不能替代原完整数据目标。

**Tech Stack:** 现有 Python 3.12、NumPy、Pillow、httpx/httpcore；标准库 JSON/base64/zlib/zipfile，不安装 FiftyOne/Mongo 或大模型。

**Spec:** 现有 external-rgbd-deployment-design 与用户最新精选授权。原规模门槛仅对原完整目标保留；精选独立实际规模、能力、用途报告。

## Global Constraints

- 大陆 ModelScope/CDN 物理网卡直连，TLS 校验、独立 DNS、域名门禁；不回退 TUN。
- 全局新增网络250GiB、RoboMIND家族累计10GiB、至少50GiB空闲；探测字节计入账本。
- 只真数据；源 float32 毫米深度保留，缺 K、时间戳、动作、基座外参不补造。
- GT 独立；未知官方 split 保留未知，参考完整协议的 scene 标签另留来源，不能宣称精选有官方 split。
- 不下载完整200GiB包、不训练模型、不驱动硬件、不混卷、不自动提交推送。

## Review Focus

- 热力图导出究竟为 numeric depth 还是彩色预览；禁止二次乘 BOP scale。
- base64/zlib/NPY 解码上限、pickle、路径和校验绑定。
- cropped mask 必须与 normalized bbox 像素尺寸相符，重复实例不合并。
- 导出日期不能冒充采集时间，缺内参不能声称几何已验。
- 选择实际10个不同scene、4camera全部到齐；正式完整目标不升级。

## Tasks

- [x] 固定魔搭精选源 revision/files/SHA，通过直连下载 samples.json 与10场景RGB；实际检查小 Robo 样例，缺 depth 拒绝RGBD。
- [x] TDD实现 fiftyone_curated.py 的安全解码、记录切片、GT及未知能力；ZIP正式安全提取支持。
- [x] 接入独立 CLI 变体、原子文件发布和 CURATED_RGBD_VERIFIED 门禁，复用索引/预览/0及2worker。
- [x] 实际全部样本校验、5组预览、CPU batch和独立复核，交付中文说明与机器报告。

Result: 40真实RGB-D/10场景/669可见实例/0隔离/5预览，CPU0及2 worker、重复deploy复用通过；228软件测试通过、2原目标真实用例跳过，Ruff/mypy及独立复核通过。缺K与对齐保持未知。验收见 `artifacts/research/process/20261003-curated-rgbd/acceptance.json`。

Ruling: 用户最新指令已授权精选替代及必要的可逆代码/下载工作，按现有工作区连续执行；不追加设计或执行确认，不提交推送。
