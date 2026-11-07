# R440 采集资产注册纠正 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: 沿 R439 的 superpowers:executing-plans inline 执行；本轮是限定计划纠错，不新增产品任务或运行额度。

**Goal:** 将 R439 collector 的错误基础资产引用纠正为既有可见姿态标记 outboard_v3 资产，并明确抓取 profile、相机和零实际 CPU 验证的衔接。

**Architecture:** 新 collector 显式冻结已存在的标记资产路径/SHA；当前 v2 gripper profile 的基础资产 SHA 与标记后完整资产 SHA 分开登记。保持单一后端/grounder/controller/Shield、既有完整H与独立reader合同。

**Tech Stack:** 现 Python/MuJoCo/OpenCV；本规划只做 XML/源码/JSON 元数据读取。

**Spec:** R439 plan.md/json（原件保留）；R91 design.md；当前 `NativeGeometryRegistration.validate_asset`。

## 原始失败与根因

这是启动前发现的静态前置冲突，不是新实际运行失败。R439 的 T2 补充错误指定 `assets/robots/franka_panda/scene.xml` 同时要求36格 outboard marker；该资产实际有0个marker cell。当前注册读取器明确要求 `pose_marker_outboard_v3_r[0-5]c[0-5]`，现既有注册测试使用 `scene_pose_marker_outboard_v3.xml`。

`intake/asset-conflict.json` 保存直接由原 XML 得出的原始证据：基础资产SHA=`66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2`；标记资产SHA=`ddc34b13d8df403f3fdeeab94be75ca988541f2eac0a3e534704f68200c39a23`；marker cells=36、边长=.045m、刚体表面中心=(.1,0,.03505)。仅删除标记visual geoms后，标记资产与基础资产 XML 结构/属性完全相同，证明本次沿用现相机/机器人/控制结构；这不是物理或native资格证明。测试fixture本身不是实际校准数据。

## 限定替代规则

1. **R439 中所有 collector-specific 资产假设以本条为准**：`model_path`/`geometry.asset_path`/protocol/RESET实际模型都显式等于 `assets/robots/franka_panda/scene_pose_marker_outboard_v3.xml`，并固定上述完整SHA；不依赖SimulatorConfig默认。scene.xml与outboard XML都只读，不修改标记、质量、碰撞、相机、控制器或全局默认。旧R439计划原件不改写，复核报告引用R440覆盖错误假设。
2. `CURRENT_GRASP_PROFILE`仍为`mujoco_upright_box_v2`，`calibration_asset_sha256(profile)`仍返回基础资产SHA，不改映射为outboard SHA。collector分别保存 `grasp_profile_base_asset_sha256` 与 `marked_asset_sha256`，验证现profile的compiled gripper几何（既有`matches_calibrated_gripper`）及标记资产完整注册；不能拿二者全文SHA相等作为条件，也不能广泛跳过资产检查。新collector固定两项和本次静态结构等价证据，不授权任意扩展XML。
3. 现标记合同保持 DICT_4X4_50/id7/size .045，marker_to_object为单位旋转+(.1,0,.03505)，object half extent=(.035,.035,.035)，object_to_tcp=(0,0,.01)，tool_to_tcp=(.105,0,0)。marker表面36 cell+quiet区域是原资产视觉附件、无新物理安装认证。离线完整geometry/八顶点和注册接触点按R439，不能只保留中心。
4. 顶视相机源来自同outboard XML `rgbd`: pos(.35,0,1.4)、quat(1,0,0,0)、fovy50°，320×240。沿现camera.py公式 `f=120/tan(25°)`、intrinsics=(f,f,159.5,119.5)，optical_to_world的旋转diag(1,-1,-1)、平移(.35,0,1.4)。camera calibration hash按现 `<f8`20数公式派生；元数据记录的期望hash=`f33940579c533afe`，正式prepare使用同公式/原编码并与首个真实frame核对，不事后回填。target region body(.2,.25,.002)+geom半高.002使注册表面(.2,.25,.004)，table表面z=0。
5. physics dt继续由本collector显式设为float(1/240)，与注册rational和backend实际config核对；不修改XML原timestep文本，也不从原XML近似小数猜分母。原R439固定12960步、fullH、5s TTL、1800s、内存/磁盘、一次0001采集和独立read全部不变。

## 具体实施/验证衔接

- [ ] ROOT在 `R439/implementation/plan-revalidation.json` 另存或新增不覆盖式续接记录，引用R440 plan/source pins与上述冲突；已通过T1、已发生T2 RED结果原样保留。无需重跑T1或T2 RED。
- [ ] 继续R439已允许的新文件：`research/native_calibration_collection.py`负责固定注册/config；`native_collection_application.py`负责工厂；`native_collection_grounding.py`负责仅像素/本体grounding；`native_full_horizon_recorder.py`负责唯一记录器；`native_full_horizon_originals.py`负责独立reader。配置仍 `configs/research/native_operational_calibration.yaml`。现 `simulation/mujoco/native_horizon.py` 的 `FullHorizonExecutionReceipt`/`NativeHorizonSession`/内部runner名称保持；辅助内部函数可在同文件按现风格命名，不增加新模块或公开授权参数。类/CLI/API命名仍以R439 RED与计划为准。
- [ ] 在尚未运行的T2 GREEN原测试文件内加入注册断言：正确outboard路径/SHA、错误base fallback拒绝、profile base/marked两种SHA分别绑定、相机/marker/region数据精确校核；所有使用静态XML或fake backend。compiled gripper真实核查随原唯一actual startup完成，不新增probe初始化。无需单独RED/额外GREEN次数。
- [ ] R439 `implementation/commands.json` 的 `t2-green.argv` 末尾追加精确参数：`--deselect=tests/test_visual_raw_recorder_v3.py::test_real_render_disabled_passive_two_steps_have_ordered_actual_begin_end_and_old_observers`。这是已要求CPU=0actual的明确选择，不删除测试、不宣称该节点本轮PASS。
- [ ] `final-regression.argv` 同样追加上述 `--deselect`。现有 `-k not actual_mujoco_guarded_diagnostic_no_render`可保留；更精确的等价选择为移除该`-k`对而追加 `--deselect=tests/test_guarded_execution_v1.py::test_actual_mujoco_guarded_diagnostic_no_render`。不得两种选择意外覆盖其他节点。其它文件清单、stage ID、timeout、max_runs及测试插件不变。
- [ ] 入口仍 `.venv/bin/python <R439>/implementation/run_stage.py t2-green`，后接原t3-red/t3-green/final-regression/static/prepare/first-full/independent-read。runner如从plan重新构建commands，应读R440精确argv overlay而非临时手工裸跑pytest；输出冻结最终argv、原R439+R440 pins和变更理由。已存在stage不可覆盖/重跑。
- [ ] static沿R439原一次Ruff/format/mypy完整清单；不增加排除产品范围，不改mypy配置来使未检查源码通过。整体新改动仍只一次fresh reviewer。

## 允许范围、前置和验收

本R440代理只写本目录计划/证据，产品修改/测试/physics/render/Git写均0。ROOT可在R439已允许的新collector/config/test与runner衔接中实施本修订；无新增既有产品编辑、无资产改动、无top_grasp映射改动、无新actual、无九组批量、无云模型调用。

已知当前状态由原R439工件保留：T1 2个预期RED、59 GREEN；T2 2个预期RED；actual=0。输入pins包括当前T1产品generation和原验证result，不把T1已授权差异误判回滚为R439初始输入。实施前对照本清单；未覆盖的新冲突/失败依旧下一实际Astra。

验收只是asset-registration冲突已正确解决并能继续R439 T2；它不证明marker真实可见、fullH成功、finite q、native VALID或正式研究验收。新首组实际仍按R439原一次额度，失败保留并停止扩组。

**自审：** 改正的是本规划者R439错误引用；明确base与marked两层SHA，保留profile、固定顶视与用户标记方案，完整记录原冲突，未扩大运行/文件边界，已给CPU阶段两个真实节点精确排除和后续可执行入口。
