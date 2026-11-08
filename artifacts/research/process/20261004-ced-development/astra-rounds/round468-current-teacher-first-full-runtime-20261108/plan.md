# R468 当前源码首组 teacher full-H 实际运行计划

实际规划者：`gpt-6-astra`。状态：`PLAN_FROZEN_NOT_EXECUTED`。用户已授权“开始真实运行”。本轮仅运行 `native-r439-0001`，seed439001；其余8组保持分母、不运行。P2不依赖P1凭据或成功。

## 问题、原始证据与输入

R465已完成CPU软件验证和独立审阅，当前源码full-H尚未实际执行。受限上下文GPU/compute查询rc9原样保留；R466唯一host诊断三条rc0，2026-11-08T07:00:01.082347+00:00记录RTX4070TiSUPER、16376/513/15431MiB、compute空、Qwen loaded/inactive/dead/MainPID=ControlPID=0。它支持上下文访问差异，不能证明具体机制或资源预约。R467报告键误用已独立验证，未重复query。

HEAD `ae3b88370276ebe0b2782720588c0b52d6c8e1d8`，产品diff为空。全部32项输入路径/字节数/SHA256及所有423项src/**/*.py、固定config、base/marked XML、生产script、pyproject哈希均列于plan.json。当前source_generation：`e5795af5d1a7b90a7dcb442da0f37c0ec9fe4fad04d13e3696c4a5cf609fdd55`。reader SHA `f1ca40dc4a7016940ef4547d45269b4650f8a079e339af35fdc97aab1ecd81a4`。

规划时pin构造发现R449计划指向的独立future overlay文件缺失，产生只读FileNotFoundError，未写文件或运行产品。实际Astra本轮限定处理：保留缺失事实，pin R449计划和现存R439综合source-overlay-r453（含批准轮次439..456），不补写旧overlay。当前完整源码重新prepare，禁止向旧协议重贴哈希。

## 限定范围

不修改产品/测试/config/assets/pyproject。保留scene_pose_marker_outboard_v3.xml、mujoco_upright_box_v2、marker7、顶视camera、controller、OC1、TTL5秒、guard/lease/worker与UNKNOWN。provider/model=null，cloud请求0。允许路径只在plan.json列明的本轮artifact/raw目录及共享锁。完整raw和runtime数据库保留本地，不提交。

## 精确执行

工作目录 `/home/ningyd/文档/ChatGPT/BIGsmall`。清洁环境详见plan.json `stages`，不继承密钥或额外Python注入；MUJOCO_GL=egl、REAL_MOTION_DISPATCH_ENABLED=false。protocol/raw/readout叶目录由生产入口exclusive创建，runner只能预建父目录及专用tmp/cache。

### prepare

```sh
'/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python' '/home/ningyd/文档/ChatGPT/BIGsmall/scripts/collect_native_calibration.py' --prepare-only --config '/home/ningyd/文档/ChatGPT/BIGsmall/configs/research/native_operational_calibration.yaml' --output '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round468-current-teacher-first-full-runtime-20261108/actual/protocol'
```

上下文 `use_default`；child 120秒，outer 240秒，最多一次、retry0。外层冻结命令：

```sh
/usr/bin/timeout --signal=TERM --kill-after=10s 240s '/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python' '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round468-current-teacher-first-full-runtime-20261108/implementation/run_stage.py' --stage prepare
```

### full

```sh
'/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python' '/home/ningyd/文档/ChatGPT/BIGsmall/scripts/collect_native_calibration.py' --collect-once --protocol '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round468-current-teacher-first-full-runtime-20261108/actual/protocol' --assignment-id native-r439-0001 --output '/home/ningyd/文档/ChatGPT/BIGsmall/cache/research/r468-teacher-first-full-20261108/native-r439-0001'
```

上下文 `require_escalated`；child 1800秒，outer 1920秒，最多一次、retry0。外层冻结命令：

```sh
/usr/bin/timeout --signal=TERM --kill-after=10s 1920s '/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python' '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round468-current-teacher-first-full-runtime-20261108/implementation/run_stage.py' --stage full
```

### read

```sh
'/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python' '/home/ningyd/文档/ChatGPT/BIGsmall/scripts/collect_native_calibration.py' --verify --protocol '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round468-current-teacher-first-full-runtime-20261108/actual/protocol' --output '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round468-current-teacher-first-full-runtime-20261108/actual/readout'
```

上下文 `use_default`；child 900秒，outer 1020秒，最多一次、retry0。外层冻结命令：

```sh
/usr/bin/timeout --signal=TERM --kill-after=10s 1020s '/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python' '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round468-current-teacher-first-full-runtime-20261108/implementation/run_stage.py' --stage read
```

## 前置条件与一次性监督

ROOT先重验全部pins/source/HEAD/产品diff及目录新鲜性；无额外测试或产品预热。仅实现本轮固定run_stage.py，AST解析runner及plan列明七个产品文件，并静态核对精确命令、清洁env、exclusive开始标记、源哈希、资源限制和所有退出清理；冻结runner SHA及调用后执行CPU prepare。新protocol必须独立stdlib校验完整source_generation、config、8个horizon、唯一release、9个分母、角色、marker/camera/profile/TTL和预算；prepare子进程组清理且无claim/raw才进入full。

GPU实际阶段与R469共享 `cache/research/.r468-r469-gpu.lock`，fcntl非阻塞独占，持锁从一次资源准入到唯一child及子树退出清理。锁忙直接NOT_RUN、不等待/重试/删锁。按plan.json gpu_admission精确argv/env各执行一次gpu/compute/Qwen只读查询，每条8秒上限，保存原始stdout/stderr/rc/时钟。必须rc0、正确GPU、free≥8192MiB、compute空、Qwen loaded/inactive/dead且两PID0；否则停止，不启动或停止服务，不循环诊断。此fresh准入与R466历史snapshot分别记录。

full仅一个require_escalated调用；理由为执行用户已授权的唯一teacher GPU采集，EGL及R468资源/清理边界内、无模型/服务启动。实际阶段串行，禁止与P1 GPU子进程并行。

runner在Popen前保存计划/runner/argv/env/source SHA及UTC/monotonic，exclusive阶段开始标记；Popen(shell=False,start_new_session=True)，stdout/stderr原始二进制文件。每≤1秒记录进程树RSS、相关目录字节及free disk、elapsed；仅/proc stat/statm读取pid/starttime/ppid/pgid/state/RSS，不读env/cmdline/memory。明确采样峰值/间隔局限；产品原有每blob raw检查/fsync与checkpoint self-RSS检查保留。输出统计含DB/WAL/SHM，不扫描无关树。

预算/信号/异常/监控不可读立即停止：仅TERM自有进程组，≤10秒必要时KILL，wait/reap并证明后代消失；leader退出不能替代清理。PID/starttime防误杀，try/finally及signal handler覆盖全部路径。记录primary/secondary错误、原始rc/signal、日志哈希、source before/after及清理证据。只有清理确认才释放共享GPU锁。ROOT等待工具session时不重启阶段。

## 预算和失败边界

源码计算physics=120+12840=12960、explicit=12960+16=12976、implicit≤12960+2=12962、render≤3×12976+2×12962=64852。均为上限，绝非实际计数。full wall1800秒/outer1920秒，treeRSS8GiB、raw16GiB、free≥32GiB、guard_event_limit500000、retry0；prepare120秒、reader900秒。真实计数依赖原始counter/provenance，初始化或渲染失败时unknown/null/LOWER_BOUND/UNAVAILABLE禁止写成精确0。

full partial/nonzero后，如prepare有效、source未变、唯一child及子树已清理且资源安全，本计划授权生产--verify独立读取一次；保留diagnostics/groups/原始stdout/stderr/rc、全部9组和null/infinity。不可补帧、改clock、重封raw、调用替代reader或重试。prepare失败、source漂移或清理不明则read NOT_RUN。read新失败保存并停止。

新根因/计划外失败先保留原件，实际Astra下一轮后才能修复/重试；上述一次partial独立读是已批准的取证。不得清claim重跑、扩大预算/TTL、更换相机/controller、启停服务或运行其余8组。

## 验收与交付

软件验证、实际运行和正式研究分别记录。只有生产final lifecycle/worker/owner closure、8个完整horizon及实际计数与独立原件重建共同支持，才称COLLECTION_COMPLETE_WITH_UNRESOLVED_EFFECTS；否则PARTIAL/FAILED/NOT_RUN与原始原因。缺失8组及UNKNOWN仍令联合bound为infinity（JSON null）；有限group diagnostic不是qualified score。native UNKNOWN、formal NOT_ACCEPTED、real hardware NOT_RUN。

ROOT写步骤报告并汇入阶段总结，记录完整raw本地位置及哈希，显式路径提交/推送已验证plan/runner/protocol/diagnostics/reports，核对本地/上游/远端SHA。raw/DB/WAL/SHM、凭据、权重和SDK不提交；派生报告/清单不是完整远端复现包。

本规划阶段产品import、tests、engine、render、API、服务操作均0。机器执行细节与全部输入哈希以plan.json为准。

监督补充：允许读本次自有PID的 `/proc/<pid>/task/<pid>/children` 和本轮supervisor/subreaper自身children发现后代，仅再读其stat/statm；清理限定同starttime的owned进程/本次PGID。可设置本supervisor为Linux子收割器，不作全机扫描。任何阶段启动前，ROOT可修正尚未运行的一次性runner的语法/接口/契约细节并重复stdlib AST/JSON/hash静态检查，再冻结最终SHA；不增加测试，不授权运行失败后的修复/重试。
