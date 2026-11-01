# R377 Browser Mock Draft Input Contract Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans 按本计划执行；用户方向与修复范围已明确，无需追加设计审批。

**Goal:** 让通用控制台 Mock 草稿明确选择 LEGACY_PIPELINE，恢复关键场景的真实 API/页面断言。

**Architecture:** 仅补 console.spec.ts 的草稿输入字段；保留产品默认 RGBD 和严格 blocker。复用旧 RED，完整执行默认 40 项和研究 3 项，输出全部迁到新 R377 目录。

**Tech Stack:** 已有 Node22.23.3、Playwright/Chromium、Vite、FastAPI、临时 SQLite、MuJoCo/EGL 捕获环境。

**Spec:** 用户恢复测试输入与版本一致性的授权、根 AGENTS，以及同目录 plan.json 的直接输入 pins/运行命令/验收。

## 原失败与根因

R374 默认套件 40 项：21 PASS、5 FAILURE、13 ERROR、1 原有 E2E06 MuJoCo 环境 SKIP；研究套件 3 PASS。默认约 305 秒结束。18 个失败/错误的名称和原 JUnit/stdout/invocation/source/audit pins 已记录；不把原 SKIP 混作这 18 项。

console `draft()` 的 MOCK base 缺 input_mode；ExperimentDraft 默认 RGBD，validator 明确拒绝 MOCK+RGBD，任务在 QUEUED 之前被记为 BLOCKED_BY_ENV。Python phase11.1 `_draft()` 已显式 LEGACY_PIPELINE，是正确对照。仅此证据不能保证全部 18 项只有同一原因，修后以真实全套结果为准。

## 最小修改与前置互斥

仅在 `dashboard/tests/e2e/console.spec.ts::draft()` 的 backend 旁加 `input_mode: "LEGACY_PIPELINE"`，保留 overrides 优先级与所有合并、断言、时间和 skip。无需新增测试；旧 18 项失败是实际行为 RED，完整重跑是 GREEN，不用源码 grep 代替测试。

不修改 RGBD 专用 suite、产品模型/validator/service、marker/资产、研究 formal/admission。R376 的 rgbd_runtime_control、closure、新 fixture contract 不放入本轮直接 pins，避免独立授权改动误报漂移。

**必须等 R376 整批终态、进程清理和源写入结束，才可改 console 或运行浏览器。** 现在只读规划与新 artifact 准备可并行；源代码写入互斥，测试期间无源写入。等待后记录实际 HEAD/源基线，已知 R376 提交可作为前序变化。保留 local_temporal 性能候选、两份未跟踪测试、嵌套 workspace，不切工作树、不重置。

## 执行步骤

- [ ] 核验 plan.json 的 56 项直接输入 SHA，记录实际权限、R376 完成/清理和源写入释放。
- [ ] 应用一个字段修改，审查 diff；原失败直接复用，不再跑未修旧代码。
- [ ] 从已冻结 R373 path-only adapter 建新 R377 adapter，使用 `R377_STAGE_DIR`。默认只排除研究 spec，仍收集原 40 项；研究复制 spec 只换 evidenceRoot，仍原 3 项。研究 backend.py 与 19 文件 fixture 字节复制并核对 SHA，不重造结果。
- [ ] 可各一次 `--list`（每次 30 秒）核对 40/3，记录输出；配置初始化只可写新目录。不得运行 npm e2e，因为 prepare-e2e-tests 会修改测试源码。
- [ ] 按 JSON 的精确 Node+现有 Playwright CLI 命令，`--workers=1 --retries=0`，默认一次 600 秒，然后研究一次 300 秒；各保留 15 秒所属进程清理。默认失败不取消独立研究阶段，也不重试行为。
- [ ] 保存全部 stdout/stderr/JUnit、失败 trace/error context、截图/下载导出、实际 server/browser 身份与清理、源前后；逐项映射旧 18 项到新断言完成情况。新失败不在本轮扩修。
- [ ] 独立审查后仅选择已验证 console 改动及精选报告证据提交/推送研发分支，核对本地/上游/远端 SHA。无 force/TLS/gitconfig 改动，其他用户文件不纳入。

## 环境与写入边界

Node 使用 cache/node-v22.23.3-linux-x64/bin/node（满足 >=22.12），Python 使用现有 .venv；已有 node_modules、Chromium cache，不安装升级、不整份 source env.sh。默认端口 8000/5173，研究 8123/5199，reuseExistingServer=false、Vite strictPort。只在真实执行权限内检查/启动，端口被占时阻塞，不杀陌生进程或复用外部服务。

parent 报告 workspace-write/network restricted；执行时记录实际权限，不能照搬上一轮 full-access。若端口/Chromium 被明确环境拒绝，只有工具允许且行为尚未开始时才能一次 escalation 后新目录替代，保留旧回执并计入总额；行为开始后零重试。禁止凭空改变浏览器 sandbox 参数。

每套使用独立新 runtime/artifact/model DB。默认 E2E 后端在本套内共享其真实持久库是预期，不等同 pytest 每测试 tmp_path 的覆盖问题；不得继承全局 DB。移除环境凭据/远端模型配置，保留 LOCAL_ONLY、真实无硬件写入防护、ISAAC disabled。默认3项 RGBD capture 本来使用 MuJoCo/EGL，不能降级为 Mock；模型不可用的负例保持原断言。研究3项固定 SOFTWARE_ONLY、NOT_RUN、formal=false，4200 BLOCKED 原样保留，不运行旧硬编码证据路径。

预算：行为及清理 **930 秒**，可选两次 listing 共 60 秒，本轮总墙钟 **1200 秒**。独立于旧 R373/R374 八小时账；不借 R376 测试并发。清理记录所属 browser/webserver 子树（含另建 session），TERM5秒后必要时 KILL/reap，15秒界内保留活进程检查，不遗留服务。

## 验收边界

默认须原 40 项完整记账，目标 **39 PASS + 原 E2E06 1 SKIP**，无新增 skip/failure/error/timeout；不能宣称 40 PASS。原 18 项须走完 queued/success/batch、metrics/events/replay、cancel、timeout/recovery/retry 原断言。E2E31 原断言只证明 retry 返回 QUEUED，不宣称未验证的重试终态。仅“不再 BLOCKED”不足。

RGBD3项及研究3项分别按原完整断言验收，研究导出须等于真实页面 payload，formal 状态不变。需要退出码、JUnit、完整目标断言、源未漂移和进程清理共同支持。若仍有新失败，只报告部分修复和剩余问题，后续 Astra 后再修；不升级为全流程、真实硬件或正式研究通过。

规划者实际 `gpt-6-astra`；本次只读调查及写计划，未执行测试/服务器/浏览器、信号、网络或 Git 修改。
