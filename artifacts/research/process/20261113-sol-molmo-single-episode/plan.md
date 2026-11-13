# Sol+Molmo 单场景统一入口实施计划

> 当前模型规划，非 Astra。用户附件为需求，现有执行资格和安全门继续有效。使用 executing-plans 内联实施；用户既有持续自主开发授权覆盖常规接口修正。

**Goal:** 交付 scripts/run_sol_molmo_single_episode.py，统一单场景配置、标记检查、真实 Sol+Molmo 规划、执行前置检查和可核验结果。
**Architecture:** 复用 marker_family/detect_pose_marker、ModelControlService、build_molmo_grounded_planner 和 PlanningPipeline。所有实际来源来自同一 MuJoCoCaptureSession；不伪造 RoleModelBundle、不使用 LEGACY 绕过 OPENCV worker 资格。
**Tech Stack:** 既有 Python/OpenCV/MuJoCo/Molmo BF16/Sol，零新依赖。
**Spec:** 用户提供的2026-11-13单场景入口计划；附件SHA256另记本地输入。

## Global Constraints
- 默认 dry-run，零模型/渲染/物理调用；标记诊断和模型规划显式启用。输出目录独占，不覆盖旧实验。
- 默认精确 outboard_id7_45mm_v3：ID7、45mm、固定注册资产；支持已登记版本，但 prepare-only 不是执行授权。
- 固定 S01 场景，seed 不冒充独立随机场景。320x240、1/240秒、settle120；既定相机/控制器不改。
- Molmo最多1load/4generation，Sol最多1付费请求、0修复/重试；GPU锁/资源门复用现有实现。原文和RGBD只留local输出。
- execute 必须保留真实 OPENCV worker、标定资产和执行资格；当前缺失时 BLOCKED、0动作，不把规划或诊断成功标成任务成功。
- 仅首尾 OBSERVED 表示两个采样点，不证明全过程可见。失败和异常保留原因及已有证据；错误摘要不含凭据。

## Review Focus
- 缺少 execute/allow-paid 不得触达模型、secret或renderer。
- 输出复用、资产漂移、错误family不得覆盖或启动付费。
- render/planning失败后仍保存已有marker/原始来源和result。
- 可见性未知不得写OCCLUDED；首尾可见不得写continuous=true。
- blocked执行不得经LEGACY/裸控制器回退或调用未放行worker。

### Task 1: CLI 与证据协议
**Files:** scripts/run_sol_molmo_single_episode.py；src/cloud_edge_robot_arm/research/sol_molmo_single_episode.py；tests/test_sol_molmo_single_episode.py；docs/research/sol_molmo_single_episode.md。
**Interfaces:** main(argv)->int；run_single_episode(*,output,seed=42001,marker_family_id=LEGACY_FAMILY,mode='dry-run',...)->dict；validate_marker_visibility(capture,output_dir,registration)->dict。
- [x] 编写 RED：默认零副作用、资产错配、独占目录、UNKNOWN语义、执行拒绝不调用模型、异常归档。
- [x] 最小实现 CLI/模式/当前源码引导、标记帧和来源清单；用真实测试夹具检测 marker，云/权重只替换外部边界。
- [x] 接通现有 service/adapter/pipeline；验证真实profile模型必须Sol，预算及原始wire记录。
- [x] 限定回归、ruff/format、CLI帮助和真实dry-run；EGL标记诊断与执行前置检查，保留实际失败。
- [x] 真实plan-only：首版失败保留；按下方限定更新修复，新版本1load/4gen/1cloud规划通过。不结转额度。
- [ ] 写派生报告，按精确路径提交；公开推送需遵守既有新增载荷授权。

## 用户完整目标核对
- [x] 统一CLI、配置加载、真实Sol/Molmo/OpenCV规划及来源证据。
- [x] 真实标记检测：45mm首尾UNKNOWN，75mm侧置首尾OBSERVED，不能以正例替代原45mm失败。
- [ ] 取得标记资产动作资格，接通真实OpenCV worker与Molmo主线程的新帧/合同交接。
- [ ] 完整抓取、抬升、搬运、放置与释放，并独立验证物理成功。
- [ ] 抓放全过程标记验证；首尾静态检查不满足此项。
- [ ] 至少一次完整任务成功记录；当前仅有规划成功。
- [ ] 可选完整冻结包：当前未生成，资格未成立。

## 已确认的需求修正
RoleModelBundle 不是cloud/local二元模型容器；Molmo是单独的感知provider。借用backend不能apply_scene；由capture拥有backend并RESET固定S01。VerificationBudget字段为max_reobservations/max_retries/max_no_progress/deadline_s；耗时字段elapsed_s。Molmo调用须在专用主线程，PlanningPipeline直接在该线程执行；不可直接交给旧runtime的bounded_model_call后台线程。完整OPENCV物理执行和标记资产资格是独立真实阻塞，不能因本入口存在而宣称完成。

## 实测后的限定更新
首轮真实plan-only完成1load/2gen/1cloud，因本入口refresh推进1物理步违反既有暂停协议而被拒绝。冻结旧原件；仅删除该推进，不修改校验/TTL。允许修复后新版本独立一次1load/4gen/1cloud，0重试；累计上限2load/8gen/2cloud，不结转剩余。另做一次已登记75mm侧置族首尾检测对照，0动作/模型；不修改场景参数、不据此授予执行。
