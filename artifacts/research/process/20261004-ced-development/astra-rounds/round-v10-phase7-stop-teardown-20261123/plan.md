# Phase 7 停止写者收尾与 LIFT 步内故障补充计划

gpt-6.2-astra · 2026-11-23 · 研发 Git 基线 `2ec0c98f82a6cab7fb1f9abbec37631226d3d605`。已核实 backend `9db2c208…`、skill_robot `2c782158…`、reader `408502ad…`。机器可读计划列出候选、前序计划、原探针、读取器和验证输入的 SHA256。

## 原始事实和待验证根因

- 原 review-release-guard-exit-closeable 使用零步软件后端，外来线程调用 step 触发线程归属错误并开始 fail-closed。在实际 hold 前用 Event 暂停后恢复原 hold；未注入 hold 故障。合法 owner 先得到 guard 正常退出及 guard_exited=true，随后 shutdown 正常返回、_data 已清空，写者尚未结束。实际最终命令 0、ESTOP=false，制动错误是 backend is not initialized。跨线程 recorder entry 的来源拒绝是另一个实际事实，不能声称产生过合法 TERMINATION 父。
- 实际 LIFT 的已完成第一物理步在 observer 回调抛 MotionGuardViolation。原 guard 包住 hold/stop 并记录 FAILURE、TERMINATION ABORTED，控制器再往仍展开的普通 HOLD 发第三条 hold。对照的 post-step controller 也返回 GRASP_LOST 与 1 held_step，命令为普通 HOLD 专用 hold，随后正常 TERMINATION 的 hold/stop。两种情形的三个命令顺序、父区间及意义不同。
- 当前同步逻辑区分显式重叠请求；guard exit 和 shutdown 的隐式关闭可提前返回。应用在 guard 之后快照计数、freeze、recorder_close、capture_close、backend_shutdown，再由外层 owner 结束 clock/作业资源。当前 LIFT 的域异常分支无条件尝试保护性 hold。本轮只修复这些已定位的收尾问题。

## 修改与验收

- [ ] **固定输入/RED。** 在隔离候选快照核 plan.json 的原始与产品指纹。保持原脚本/日志不变，独立目录先复跑 shutdown 探针和 LIFT 的两条路径。用 Event/Barrier 在写者持有后端而尚未完成 hold、控制写完成但操作/记账尚未返回两个位置建立可控交错；释放事件由独立线程或 finally 保证，join 有界。把首次物理失败、仅审计失败与成功分别观测，比较每一步的使用者、指针存活、命令/CONTROL、闩锁、guard 与各层 closed 标志。实际 collector E2E 使用临时 DB/worker 和原 recorder，而非用 mock 的关闭顺序代替。
- [ ] **协调 guard exit 与资源寿命。** 在 backend 现有同步状态内标记本次唯一写者与代次，写者完成实际控制、相关操作回调/interval 结尾和终态记录后才发布完成并通知；区分物理停止已成功、正在收尾和可重试的物理失败。在 owner 正常退出、异常展开、公共 shutdown 和 worker 清理中复用同一收尾判定，避免仅依据 _execution_guard_closed 或 ESTOP/命令数释放资源。有限等待/显式进行中错误或 owner 接管均可，但 guard_exited/shutdown_complete 只有在其真实边界完成后才可置真。若 writer 未结束或停止仍未完成，显式失败/延后并保留重试所需资源，写者结束后由同一拥有者或明确的一次清理续行完成释放，不能泄露资源或误报已经完成。无需持锁调用物理、recorder、用户回调或 join，拒绝同线程递归、回调重入和相互等待，保留之前显式重叠请求的可观察结果。
- [ ] **贯穿真实收尾。** 合法 owner、外来非法 step、显式停止、guard exit 与独立 shutdown 同时到达时，只允许一位物理写者，一组必要的 hold→stop/CONTROL；在实际 writer 完成前不得清 _data/model/camera、先移除 observer、冻结尚在追加的原件或关闭捕获/recording clock。把收尾协调用在计数快照/冻结之前；若一次退出因重叠被拒绝，调整 _close_body_resources 等调用者按依赖重试或保留未完成状态，不能继续分步拆毁后又宣传 owner closure 成功。检查作用域允许的 owner 子路径精确关联 BEGIN/END、命令父、时钟；跨线程的实际来源拒绝继续记录，禁止让非 owner 写入 recorder 或虚构父。首错、次错、后续成功和各层资源一次完成都有据。测试普通无 guard/无 recorder 的 shutdown 与重复清理、首次制动确实失败后仍可恢复、外来写者结束后最终资源释放。允许产品路径 backend.py、native_collection_application.py 及其直接 stop/cleanup 测试；无证据不动 recorder、reader、SQLite 实现。
- [ ] **仅消除已制动的多余 LIFT hold。** 在 skill_robot.py 的 MotionGuardViolation 处理处使用后端与同一 episode 对应的可靠制动完成状态/窄操作，避免「查询后才发命令」的竞争。实际 hold 与控制均完成，才可跳过普通保护性 hold。正在制动或部分失败必须通过现有安全序列处理，不能只查闩锁、复用过期状态或和现有写者重叠发命令。用真实步内 observer 复现并核只剩 abort 的 TERMINATION 下 hold、stop，各一次，没有返回普通 HOLD 的第三笔；步外 post-step 对照仍应产生原普通专用 hold 和正常退出的两条命令。普通 LIFT、不同域码、专用 hold 失败后的应急制动、应急制动再次失败、observer 抛错前后 held_steps、原 cause 与回执/次错误均沿用先前契约。
- [ ] **最终冻结、复审、登记。** 修改完成后冻结最终源码清单，将两条原探针、交叉并发/顺序兼容矩阵、专项、真实 worker→SQLite→recorder→公共 reader E2E、健康与故障读回在最终静态源上运行；复审必须记录最终三个产品指纹和命令/步数/资格。依主计划执行冻结 v9/v10 原结论比对、用最终源重做私有 --prepare-only 与单帧预检、空登记读回，核所有 SHA 和旧 claim。已完成的全库分片可以按原样引用，但必须列其真实源码 SHA、选择器/分母、与最终源 diff、未覆盖与追加的最终集成/专项。不能把旧分片写成全部基于最终 SHA；若差分影响原分片且最终专项未覆盖，补跑受影响项。所有真实失败/未验证范围进入阶段报告。
- [ ] **授权。** 本轮限定研发收尾、软件夹具和已有允许的短非正式后端测试，产品限定于上述三个文件；必要测试用例归入既有 authority、guard、stop E2E、LIFT 测试。正式仿真 0、新正式 claim 0、真实硬件/模型调用 0。前序计划、正式 raw/数据库/协议和 claim 均保留。若证据显示新独立根因，先另轮计划。

## 验证命令

在最终冻结工作树设置 PYTHONPATH=src:.、PYTHONDONTWRITEBYTECODE=1、MUJOCO_GL=egl，PY 为相邻已核对 Python，E 为本轮私有证据目录。以下列出最终核验；RED 请另用全新文件名。

```bash
"$PY" "$E/review-release-guard-exit-closeable.py" > "$E/teardown-final-exit.log"
"$PY" "$E/lift-secondary-guarded-observer.py" > "$E/teardown-final-lift.log"
"$PY" "$E/review-final-advanced.py" > "$E/teardown-final-advanced.log"
"$PY" "$E/review-stop-probe.py" > "$E/teardown-final-original.log"
"$PY" -m pytest -q tests/test_native_collection_authority.py tests/test_native_collection_stop_e2e.py tests/test_mujoco_execution_guard_v1.py tests/test_mujoco_full_horizon_sampling.py tests/test_native_harness_stop_diagnostics.py
"$PY" -m pytest -q tests/test_visual_servo_control.py -k lift_hold
"$PY" -m pytest -q tests/test_native_full_horizon_originals.py tests/test_native_registered_teacher_release.py
```

对新增交错用例重复运行、核线程退出和真实资源销毁；沿主计划 C 运行归档 CLI 与最终登记预检。成果限于已测软件/后端层级。
