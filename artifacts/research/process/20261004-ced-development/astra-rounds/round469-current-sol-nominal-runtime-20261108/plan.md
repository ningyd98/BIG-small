# R469：fresh current-v2 Sol 基础场景 nominal 真实运行计划

实际规划模型 `gpt-6-astra`。本次仅规划，产品 import、API、render、physics、测试、服务操作均0。用户已明确“开始真实运行”，授权已具备；当前缺失的是本地进程内密钥。先完成无密钥准备，不新增确认循环；零云 R468 教师链独立推进，两链 GPU 实际阶段串行，彼此不以 PASS 为前置。

## 证据、输入与目标

P0 R465 已通过 reader6、adjacent134、静态及独立审查，交付 HEAD `ae3b88370276ebe0b2782720588c0b52d6c8e1d8`。真实 reader 路径是 `src/cloud_edge_robot_arm/research/freeze_evidence.py`，SHA `f1ca40dc4a7016940ef4547d45269b4650f8a079e339af35fdc97aab1ecd81a4`；任务消息中的 currentfreeze_evidence.py 是拼写简称。R466 主机快照 GPU total16376/used513/free15431MiB、compute空、Qwen inactive/dead；原受限 rc9 保留。R467 已从原 bytes 修复报告，未再诊断。快照不代替执行时资源准入。

本轮补齐的缺口是新 v2 图和实际 Sol nominal，R460 的历史 v1 回放不能冒充 fresh。直接输入 SHA 见 `plan.json.inputs`；`source-pins.json` 249项由当前 probe/reader/backend/配置 edge/device 的静态本地 import 闭包加配置、资产、依赖描述生成，不复制旧原件。每个 SHA 要在准备、输入密钥后、每次 capture/API 前后和独立 reader 前复核。生产 `source_fingerprints()` 必须保持原精确 map；额外输入、runner/plan/config/profile hash 在新的 `source-generation.json` 绑定，不塞入 production map 破坏 reader 等式。

唯一场景：`assets/robots/franka_panda/scene.xml`，SHA `66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2`，与注册 grasp v2 匹配。原顶视 rgbd、320×240、S01_NORMAL_STATIC、seed0、domain_randomization=false、normalized_1000、`mujoco_upright_box_v2`。原指令 `pick the red cube and place it in the green target region`。准确标注基础场景，不称 marker full-H；主线可见标记/相机/控制器方案不变。

## ROOT 产物及命令

只创建 `implementation/run_nominal.py` 一次性 runner，冻结 config/profile/source-generation 及本轮派生报告。实际 raw 独占新目录 `cache/research/r469-current-sol-nominal-20261108`；不修改产品、测试、配置、资产，不建通用框架。config 从当前 ced_roles.yaml 派生，仅选定非密 profile_id；其余场景、edge、device绑定按原配置冻结。

在仓库根目录运行：

```bash
env MUJOCO_GL=egl PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 /usr/bin/timeout --signal=TERM --kill-after=2s 90s .venv/bin/python artifacts/research/process/20261004-ced-development/astra-rounds/round469-current-sol-nominal-runtime-20261108/implementation/run_nominal.py --preflight
env MUJOCO_GL=egl PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 .venv/bin/python artifacts/research/process/20261004-ced-development/astra-rounds/round469-current-sol-nominal-runtime-20261108/implementation/run_nominal.py --execute
env MUJOCO_GL=egl PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 /usr/bin/timeout --signal=TERM --kill-after=2s 210s .venv/bin/python artifacts/research/process/20261004-ced-development/astra-rounds/round469-current-sol-nominal-runtime-20261108/implementation/run_nominal.py --read
```

CPU preflight 唯一一次：内部60秒/外层90秒。可纯 CPU import schema/config/binding，不构造 backend/session/Renderer/MjModel，不 HTTP、不读 secret/DB。校验全部 pins、配置、官方 route、source map/bundle、VisualDecision schema、body字段、报告字段和预算；空 InMemorySecretStore 可做 resolver 构造但不得 plan。完整 body 的图像只能来自未来真实 capture，在每次发送前用生产 build_visual_messages/compatible_messages/compatible_chat_generation 构建并校验；不伪造 fresh 输入来冒充 preflight 已验证真实图。静态发现尚未运行的 runner 拼写/接口错误可在范围内修正；preflight 或实际执行出现意外失败后不边改边重试，先下一实际 Astra。

非密 profile 固定 `profile-a6a0273a17da4934`、OPENAI_COMPATIBLE、`https://api.openai.com` + `/v1/chat/completions`、精确 `gpt-6.1-sol`、enabled/config_version1、max4096/timeout180/retry0。历史 `secret_present=true` 不导入；preflight 明确未取得 secret。profile只用 ModelProviderProfile + 只读 selected-profile view，无数据库或 activation。

本地 Codex 终端 `--execute` 使用 getpass 隐藏输入，必须 TTY，GetPassWarning 直接拒绝回退；先禁 core。key只在内存和子进程 InMemorySecretStore，不进入 argv/env/日志/聊天/文件；fork后父进程丢引用，子进程 finally delete_secret/退出，不声称内存安全擦除。等待输入不持 GPU 锁、不启动900/960秒 workload计时、不消耗调用额度。准备完成但未输入时记 `READY_WAITING_HIDDEN_TTY_SECRET`，把上面具体命令交用户执行并继续不依赖 key 的教师工作。

## 一次准入与串行监督

输入后获取共同 `cache/research/.r468-r469-gpu.lock` 非阻塞 flock，与 R468一致。忙则删除本进程key引用并记录等待，不开 renderer/API，不终止其他 owner。持锁直到自身 worker彻底退出回收。输入后再次核对 pins，然后按 JSON 中三条精确只读命令各查询一次 GPU、compute 和既有 Qwen user unit（每条8秒）。需rc0、compute空、Qwen loaded/inactive/dead且MainPID/ControlPID0、磁盘free≥2GiB，GPUfree≥2048MiB保守准入；后者不是实证显存需求。失败只保存，不启动/停止任何服务，不自动再查。成功后才以 exclusive-create 写唯一 execution-start 标记，已有运行痕迹禁止 --execute 重放。

四次串行请求：first1+warm3，low/max_completion_tokens4096，合计 completion ceiling16384（含推理，不是总token或价格上限）；JSONformat由生产代码构造、180秒/次、retries0、模型列表0、fallback0、physics/dispatch0。请求/响应原件各≤2000000字节。完整 usage原样保留，缺失或不合法停止，费用/pure inference duration没有则null。

真实阶段 child wall≤900秒、outer≤960秒（仅准入后启动）；请求watchdog185秒；RSS峰值≤4GiB、raw≤1GiB、diskfree≥2GiB。父进程每0.2秒监督本次子进程/真实子树的 `/proc/<pid>/stat` 与 `statm` 仅PID/starttime/ppid/pgid/state/RSS，不读环境、cmdline、mem或其他服务内容；wait4记录rusage。记录采样可能的超限，超阈立即终止且该次不验收，不声称采样是绝对硬内存隔离。SIGINT/SIGTERM、超限或异常时仅本组TERM、等2秒、必要KILL并wait4回收，PID/starttime核对防误杀，finally释放锁；始终保留partial/raw与实际rc。

## backend计数与每次早停

1. admitted child显式创建唯一 production backend，initialize一次，无render/physics。核验当前v2资产与生产 matches_calibrated_gripper；不向planner输入对象真值。
2. initialize后进入只读 `observe_operation_boundaries`，唯一reset(S01seed0)。reset的mj_resetData/mj_forward不推进physics；`_update_sensor_frame -> _capture_cached_observed(include_instances=False)`完成一次隐式RGB+depth，即2pass。
3. reset后借用 `MuJoCoCaptureSession(simulator, backend=backend)`，不二次initialize/reset。四次 `capture_with_instances` 各RGB/depth/instance三pass，成功路径 2+4×3=14。observer只保存小型operation边界/physics step/time/pass hashes，事件与clock不改，不写整帧到日志、不反馈真值控制。
4. capture前核对pins/resource/剩余额度；帧必须为本轮新episode、新frameID/实际captured_at、S01/320×240、source=mujoco_camera、三pass与physics hash同步，sim_time0。不刷新或改写旧clock，不继承R460图。同步或capture错误时保存已有证据即停。
5. 构造生产 request ID `cloud-role-probe-{index:02d}`，原指令、scene_version1、新observation。发送前验证真实body、两个不同PNG、有效settings与体积。调用生产 `_attempt` 一次，原返回对象先append并另存唯一progress snapshot，再评判；原attempt.json/raw/cost/status一字不改。
6. 任一门失败，下一frame/API不再发生。门包括COMPLETE；transport_two_images/parsed/grounded/双mask hit全true；parse_errorNone；summary/body与实际帧设置相等；无 `_sentinel` 且合法完整steps（八个核心技能、HOME仅可在两端）；grounded_target/destination有限xyz和合法像素坐标；校准状态/assethash正确；response无error/refusal、finish_reason=stop、完整usage且completion合规；唯一settled SUCCESS PLANNER/REMOTE_SERVICE cost记录与raw bytes/source snapshot对应；source/resource/sync/settings保持。
7. 四次且所有门通过后，以生产 `can_accept_role_probe` 决定report PASS，写final settings与生产schema/bundle/hash；仅PASS写roles-frozen。observer内无PHYSICS/CONTROL/COMMAND且failure ledger空。退出borrowed capture后backend.shutdown一次关闭renderer；finally删除secret。

成功的计数来自RESET/CAPTURE BEGIN/END及pass hashes长度2/3，不仅靠静态乘法。失败中的隐式capture未知pass记[0,2]、显式记[0,3]并加已完成值，不写精确0。planned4和unexecuted=4-len(returned attempts)按原report保留，另记录started/sent/settled/inflight-unknown，以免被kill中的调用冒充未执行；所有剩余分母保留。外层强杀导致final report缺失时，只留termination receipt/partials，不拼造完整report。

## 独立读出、验收及交付

原 `run_probe` 的schema与所有 config/source/bundle/settings/capture/attempts字段完整保留，report的physical/edge/dispatchfalse、scope NOMINAL_PROBE_ONLY；额外resource/freshness在单独receipt绑定。每次完整保留request/response原bytes、PNG、floatdepth、mask、instances、observation、attempt/cost/usage。 `_safe_attempt_record` 的原保密行为保留，不输出任意异常文字。

worker已退出回收、renderer关闭、secret消失且原件seal后，另进程 `--read` 仅一次调用 `freeze_evidence.verify_role_probe_evidence(raw_root)`，内部180秒/outer210秒、RSS4GiB、无网络/模型/渲染/物理；保存其原返回，不改available。failed/partial报告可能诚实unavailable；若final report不存在，记NOT_RUN_MISSING_FINAL_REPORT，不造report骗reader。reader失败绝不触发重跑。

仅4次原件+生产门+独立reader.available+额外几何/refusal/usage/resource/source门全过，才接受本基础场景/源码的nominal资格；物理、edge、full-H、remote weights、native、formal均不由此提升。ROOT写step-report/phase-summary，保留所有失败；只按明确路径提交推送计划、manifest、runner和选定派生报告，核对local/upstream/remote SHA。完整raw留本地cache，不提交凭据、运行DB、权重或SDK；清单不是完整远端复现包。
