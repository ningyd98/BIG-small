# 真实模型闭环与 Harness 首版实施计划

> For agentic workers: use `superpowers:executing-plans`; independent H0/H1 and UTC work uses `superpowers:dispatching-parallel-agents`. 用户已授权开始四项；不重复请求批准。

**Goal:** 实测现选 Sol＋Molmo＋OpenCV 的完整仿真路径，预登记新 seed 与故障，形成最小安装入口并补充 UTC、Phase 12 开发证据。

**Architecture:** 复用 SimulationWorker、SQLite/CAS、SkillExecutor、安全盾和现有相机/标记。Harness 是配置、启动和证据层；真实 API、软件替身、实际物理读出和正式研究各自记账。

**Tech Stack:** Python 3.12、现有 Molmo BF16 环境、OpenCV、MuJoCo、Memory/SQLite、setuptools wheel。

**Spec:** [实际 Astra 总计划](../../../artifacts/research/process/20261004-ced-development/astra-rounds/round-real-model-harness-20261118/plan.md)。该目录另存最新主仓 Harness 定位摘录，避免把工作树旧版计划当作现行定位。

## Global Constraints

保留已选云模型、Molmo、控制器、安全门和移动相机；不运行真机。每 episode 1 load、4 local generations、1 cloud request、0 repair/retry、原 worker 120 秒；预分配见本轮 `preallocation.json`。当前公开推送继续暂缓。

## Review Focus

- 新帧 TTL、来源/模型/资产身份和跨动作停止必须原样检查，不能把离线回放当作真实模型运行。
- 全部预分配试次及原失败保留；修后新试次不覆盖旧失败或刷新预算。
- 安装包明确区分包内离线资源与外部源码检出、模型、模拟器和凭据。
- Phase 12 生命周期补充不替代默认 RGB-D 阻塞、物理 F20 或正式验收。
- UTC 只有原两个节点在同一次调用合计 600 秒内通过全部断言才通过。

### Task 1: 固定场景真实链路与失败修复

- [x] 逐项核对 Astra 因果输入及运行前提，通过原入口运行预登记试次。
- [x] 新失败先保留原件、实际 Astra 窄计划；用原生回答零 API 回放建立 RED，再作限定修复及正反验证。
- [x] 继续尚未使用的原额度，分别记录计划通过、动作和在线/离线物理结果。修后固定场景2/2完整完成，含原失败为2/3。

### Task 2: 新 seed 与故障

- [x] 冻结 development seeds 44101–44104；按既定顺序、既定位姿采样运行，不替换失败 seed。1/4完整完成、2/4独立物理成功；未授予泛化资格。
- [x] 确定性软件/仿真故障与停止后的命令限制检查留证。
- [ ] 三项真实模型故障注入仍未释放、未执行，原额度未用于重试；真实掉物扰动未验。

### Task 3: H0/H1

- [x] 用 RED→GREEN 完成包内资源准入 helper、严格小配置、CLI 与证据核验。
- [x] 在清洁 venv 安装 wheel，离开源码树、无凭据及 PYTHONPATH 验证离线入口。最终449个Python/JSON包条目与源码逐字节一致。
- [x] 记录六类契约、外部资源边界及现有执行入口映射；H0/H1封装通过不代表正式研究验收。

### Task 4: UTC 与 Phase 12

- [x] 按实际 Astra 性能计划消除重复 codec 工作，保留预算、上下文隔离和原断言；原两个节点同次调用381.627秒，通过600秒门。
- [x] Phase11RuntimeAdapter 默认行为保持，显式 lifecycle-only 通道先 RED→GREEN，再1条初测及18条关联原行的补充记录。18/18软件补充通过；原物理F20阻塞和full profile验收缺口保留。
- [x] 独立审查、相关回归、命令/输入/输出哈希和阶段报告。

交付方式为明确路径的本地研发分支提交，继续暂缓公开推送。最终整库未重跑，真实硬件与正式研究资格未授予。详见[阶段报告](../../../artifacts/research/process/20261118-real-model-harness/report.md)。
