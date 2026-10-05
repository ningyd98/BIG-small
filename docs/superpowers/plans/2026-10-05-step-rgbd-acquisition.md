# 逐物理步RGB-D采集实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 保存一次独立排除的开发搬运中每个物理状态的真实RGB-D，重放整个动作窗口的姿态可观测性和采样误差。

**Architecture:** 在既有教师逐步观察回调内，由同一相机暂停物理时采集原始双通道；新的研究记录器核对连续step/episode/sim-time、相机pass-state一致性和同进程时钟括号，写无损gzip观测及完整BEGIN/END/FAILED。姿态检测与真值误差比较均在动作结束后离线执行，真值不进入检测器。

**Tech Stack:** 现有Python、gzip、MuJoCo/EGL、OpenCV及RGBDObservation；无新增依赖。

**Spec:** [已授权的整体计划T7b](2026-10-04-cloud-edge-device-research-roadmap.md)，继承[原量化设计](../specs/2026-10-03-rgbd-evidence-research-design.md)。

## Global Constraints

- 原相机、控制器、执行器和outboard-v3开发资产不变；不改默认资产、现有脚本或旧报告。
- 逐物理步采集，保留step0及完整终态；最大模拟采样间隔0.005秒，不能以0.1秒探针代替稳定性要求。
- 每次采集保留两pass同一physics-state、开始/结束monotonic_ns及名义UTC；外部UTC不确定度仍UNAVAILABLE。
- 一次新排除组、一次attempt，不重试、不补失败分母；所有源先冻结，渲染/物理串行。
- 每个原始RGBDObservation完整无损保存；gzip仅改变存储形式，不降低像素、精度或采样频率。
- 逐步观测不授予连续未来运动证书或native权限；真实硬件/Max调用为0，边缘型号后置。
- 用户已于2026-10-05授权Git管理与推送：经验证的实现、相关测试和报告按范围提交并推送研发分支；保留本地未交付资料，不覆盖已有工作区改动。

## Review Focus

1. 缺step、逆向sim时间或跨episode必须在新capture前拒绝，不能继续拼接。
2. RGB/depth各pass的physics-state不同、帧episode/sim时间错绑，保存失败并停止该attempt。
3. 相机或文件失败时保留已发生采集和失败分母；重新调用不得重复capture。
4. 终态必须与完整实际step数/时刻一致，不能截短horizon宣称COMPLETE。
5. 无损还原须核对原checksum、RGB/depth/mask；离线decoder没有PhysicsStepObservation输入。

---

### Task 1: 研究逐步记录器

**Files:** Create `src/cloud_edge_robot_arm/research/step_rgbd.py`; Test `tests/test_step_rgbd.py`.

**Interfaces:** `StepRGBDRecorder(directory: Path, capture: Callable[[], tuple[RGBDObservation, tuple[str, ...]]], *, episode_id: str, max_sample_gap_s: float = 0.005)`；`record_step(*, episode_id: str, physics_step: int, sim_time_s: float) -> dict`；`finish(*, final_step: int, final_sim_time_s: float) -> dict`。目录不可覆盖，任一拒绝后禁止再次采集。输出研究原始来源，无执行或正式验收字段。

- [x] 编写连续完整步、缺步/大gap/跨episode、错pass/错帧、失败重放、完整终态和gzip往返反例。
- [x] 运行新测试，保存合格缺模块RED。
- [x] 实现该接口，核对原始内容、pass和时钟括号后写COMPLETE；失败保留事件并reraise。
- [x] 新测试、源码/测试Ruff/format和源码mypy通过；独立定向审查。

### Task 2: 单次实际采集

**Files:** Create `artifacts/research/process/20261004-ced-development/t7b-continuous-visibility/run_once.py`、准备header/限定source manifest。

**Interfaces:** 原 `run_teacher_episode(..., physical_observer=callback)`；callback记录完整原PhysicsStepObservation，再调用Task 1元数据入口。capture闭包只调用同相机原 `_capture(include_instances=False)` 和原observation converter，返回原pass hashes，不读取body真值。公共backend capture对callback拒绝的原防护保留。

- [ ] 从旧28必要来源派生新限定清单；场景物理相同但另立明确开发排除group，预先冻结源码和一次attempt。
- [ ] 先独立审查script/observer/相机/源，不运行渲染；确认不step、不改cached sensor、不创建第二执行器。
- [ ] 串行运行一次完整原教师动作，保存全部命令、actuator、physics、action、逐步采集及所有失败。
- [ ] 不发生retry；实际结束后冻结原始file hashes及执行时脚本，不改执行字节来消除样式问题。

### Task 3: 原始重放及报告

**Files:** Create同目录 `verify_offline.py`、`report.md`、离线机器结果；Update阶段总结/current状态。

**Interfaces:** 输入Task 2冻结原始资料，输出全部allocated/observed/UNKNOWN、完整source/step/action/frame关联、原评分和独立误差。原始decoder仍只接收RGBDObservation与marker登记。

- [ ] 核对所有来源/原始hash、step0至实际终态逐步对应，重新评分并核对完整物理路径。
- [ ] 每一帧gzip无损还原、重新严格decode；关联原动作窗口，报告中途UNKNOWN和最大原sim采样gap。
- [ ] 只在decode之后使用离线真值计算marker/object误差和SO3采样差；区分模拟时钟速度和wall时钟观测。
- [ ] 独立原始重放审查后输出局部报告与下一步校准限制；汇入阶段总结，不将离散序列或开发组晋升为native/INITIAL/METHOD/FINAL。
