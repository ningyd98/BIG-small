# R98：P4 资源进程 guard 的最小修复计划

规划者：本轮实际调用的 gpt-6-astra（/root/astra_oc2_residual）。只规划 ROOT 本地编排工具，一项任务；不修产品、不运行实际采集。

## 原失败与确定性边界

原工具 chunk `48c791` exit 1：PID 2761145 同时命中七个 substring needle，随后 stdin line 10 `assert not live` 触发 AssertionError。原 argv/starttime 未保存，后来 PID 已消失。原 guard 对所有小于 1024 字节的 argv token 做 substring 匹配，因此会把 shell `-c` 命令正文和普通数据参数错判为实际脚本；这是确定的算法缺陷。十个内存 argv 正反例均符合预期。**旧 PID 是否就是自身 bash 祖先进程仍是未证假设**，不能补造 argv 或称其为终端实采。

本轮已完成一次当前 UID 的有限 /proc 观察：没有精确命名的 capture program 候选；这不是“系统没有 renderer”的证明。GPU 4070 Ti SUPER / 15449 MiB free / 0% 为 ROOT 提供的快照，规划者未重采。

## 唯一任务：结构化 argv 识别与资源归属

新建 `implementation/process-guard.py`，仅 stdlib；原 guard/失败字节不改。实现下面明确接口，不调用产品代码：

1. Read NUL-delimited /proc/<pid>/cmdline bytes; parse actual argv structure, never substring-search shell source or ordinary payload arguments. Record PID, PPID, /proc stat start_ticks, UID, basename classification, argv SHA256/argc and observation time; never emit full shell source, credentials or private chat content.

2. Exact known program basenames: run_operational_prefix_v1.py, collect_native_calibration.py, run_rgbd_pilot.py, probe_rgbd_roles.py, generate_rgbd_protocol_evidence.py. collect_native_calibration.py remains a declared legacy name, not proof a current file exists. Direct executable basename or Python script operand may produce KNOWN_CAPTURE_PROGRAM candidate; exact Python module stem or scripts.<stem> equivalent is allowed. Candidate name is not proof of actual --execute-once rendering.

3. Python interpreter detection uses a precise basename pattern (python, python3, python3.<digits> and documented python alternatives only). Parse recognized options before script: -W/-X/--check-hash-based-pycs consume their next argument when separate; attached forms consume no next argument; recognized no-argument flags and -- are handled. -m consumes only its module operand, -c is OPAQUE_PYTHON_CODE, - or no script is OPAQUE_PYTHON_STDIN. Unrecognized/ambiguous options become UNRESOLVED_INTERPRETER rather than guessing.

4. Shell -c/-lc text is OPAQUE_SHELL_COMMAND. Shell script operands are classified as shell scripts, not parsed as Python code. env/timeout/nice or other wrappers stay UNRESOLVED_WRAPPER unless an explicitly tested argv parser is provided. visible_marker/marker_observ are unresolved marker-family hints only when present in an actual program basename; never search all arguments for them.

5. Collect observer self and ancestor chain by PPID and start_ticks. Mark only the actual guard process SELF; preserve ancestor rows. An ancestor matching a real capture program remains a candidate. Observer shell code is not a capture program, but ancestry alone must not silently suppress a real renderer. Detect PID reuse/races by checking start_ticks before/after relevant reads.

6. Enumerate readable /proc once in --observe. Record denied/disappeared/truncated entries and UID coverage. Planning snapshot was limited to current UID1000 and does not establish whole-host absence. Do not log unrelated argv. Output named_program_candidates, unknowns, observer_chain, coverage_and_races, resource_evidence and readiness_decision=ROOT_RESOURCE_REVIEW. Unknown is a classification, not a universal busy condition.

7. For project-relevant unknowns/candidates only, read bounded stat/cwd/children and FD symlink targets for /dev/nvidia*, /dev/dri*, P4 output roots and own temp DB ownership; never open DB/raw/stdout content or attach/debug/signal. Device FDs indicate a holder needing attribution, not automatically an active renderer. Record resource-query coverage and limitations. ROOT uses renderer/task/GPU evidence to decide single-renderer conflict, not a requirement for a host with no Python/shell.

8. Exit0 certifies valid observation JSON only. Actual conflict is a structured BUSY result for ROOT, not a fabricated software failure. Relevant ambiguity is WAITING_RESOURCE_EVIDENCE; unrelated known desktop/other-chat/CPU activity is recorded without automatic blocking. An observation cannot promise future resource inactivity.

ROOT 已补充未知进程定向证据：项目 PID 2006579 是 pytest，父 2006578 是等待 shell；本次未观察到 nvidia/dri FD，children=[]，23 threads，DB/锁仅属自己的 pytest 临时目录，因此标 `PROJECT_CPU_TEST_OWN_TEMP_NO_OBSERVED_GPU`。这不说明它终止或未来绝不使用 GPU，也不把它永久当 P4 blocker。另一个 shell 属其他聊天，5847 属桌面 gnome-terminal；都保留分类，不读聊天内容、不停止进程、不凭 Python/shell 身份虚构 renderer。单 renderer 合同不等于全主机无其他程序。

## 一次性验证与失败即停

实现自测复用 `bounded-diagnosis.json` 十例的输入/预期，再加入最小内存控制：真实 capture 祖先不得隐藏；未知 wrapper 不得猜测；同名数据参数不得成为程序；不支持的 Python 选项保持 unresolved。自测只执行内存函数，不扫描 /proc、不启动捕获。单次自测内部可覆盖全部这些案例，无产品测试预算。

- `.venv/bin/python artifacts/research/process/20261004-ced-development/astra-rounds/round98-p4-readiness-process-guard-20261008/implementation/process-guard.py --self-test`：最多一次；exit 0。全部内存断言通过；不导入产品。
- `.venv/bin/python artifacts/research/process/20261004-ced-development/astra-rounds/round98-p4-readiness-process-guard-20261008/implementation/process-guard.py --observe --output artifacts/research/process/20261004-ced-development/astra-rounds/round98-p4-readiness-process-guard-20261008/implementation/process-observation.json`：最多一次；exit 0。Scan completed only; ROOT decides resource readiness from structured evidence. No actual authorization from exit0.

每个命令独立捕获原始 stdout/stderr/start/result；先保存 returncode，再检查并停止，不能异常后继续下一命令。只允许一次新的纠正后真实进程观察，作为 ROOT 启动窗口的新证据。必要的定向 FD/children 查询并入这次观察；不重复运行旧 guard、不无限轮询。报告工具通过与 ROOT resource decision 分开。

## 实施前置、剩余实际额度和验收

- ROOT verifies plan MD linkage and eight immutable pins; does not pin active P3/P4 product sources or require repository-wide quiet. All old failure files remain immutable.
- Implement only a new ROOT-local stdlib process guard and receipt harness under this round implementation directory. No product/config/test edits, Git, process cleanup, signal or kill. Create outputs exclusively and retain every original command stdout/stderr/start/result; do not backfill missing old times or argv.
- Run commands sequentially with subprocess.run(check=False), write exact returncode, then stop immediately on nonzero or failed self-test; never concatenate subsequent commands after an unhandled failure. New unexpected failure/scope goes to next Astra; no retry budget reset.
- Use one fresh corrected observation at ROOT resource window, plus bounded targeted resource attribution in that observation if necessary. Parent supplied earlier targeted observations remain historical and must not be overwritten. No repeated global scans/polling or old guard rerun.
- ROOT alone activates P4 after relevant resource evidence supports existing single-renderer contract and current task source freeze is stable. Preserve other tasks; unknown software classes do not create an all-host-idle precondition.

本轮不启动 `/tmp/bigsmall-p4-r93-command.py`。R93 新 default preflight / actual / external public readout 各一的原未用额度原样继承，本轮不新增 trial。原 P4 首败和 guard 失败都保留；旧 actual 不覆盖、不重试。ROOT 按已绑定 R93 计划另行授权新 source freeze 与独占 `actual-round93`，实际成功后才可读真实新 catalog。软件工具通过、资源观测、真实运行和正式研究验收分别记录；本轮不产生 actual PASS 或研究验收。

验收：十例及新增内存控制通过；新观察能区分真正脚本 operand 与 shell/source/data，并保留 ancestry/unknown/覆盖限度；ROOT 对关联资源作有限证据判断，无进程停止、产品更改、测试、网络模型请求或 Git。本轮步骤报告列出已用/未用额度和原失败链接。遇到新根因/非预期失败先停再交 Astra。

## 实际输入 SHA256（八项）

- `AGENTS.md` — 1774 B — `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649`
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/readiness-round93-failure/original-guard.py` — 663 B — `be14095fc2d47623134e89e83451a5070a7c4ae8439ee50f4b255752af52ad65`
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/readiness-round93-failure/tool-output.txt` — 328 B — `eae0fdcb0a98121d067fa29bfc25cea34c04c6f2e091e7721a108c20ddadaa32`
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/readiness-round93-failure/failure.json` — 469 B — `e5621548b7e648e350561f313e0eed5f30dda1a07342ac6e4392eb7e5b6fef38`
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/readiness-round93-failure/root-unknown-process-observation.json` — 1851 B — `bf585213fb3329d7d34ece877b8899f964a41a4685afdbb72c04c6dd3db5b993`
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/readiness-round93-failure/root-project-pytest-resources.json` — 1661 B — `3ab127f94bbf93cdbde564e9507b36cea8740be3892ac703b1015ffb463c3db3`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round98-p4-readiness-process-guard-20261008/bounded-diagnosis.json` — 6517 B — `eb00539853a69a260a021a0e742bf735c9ce26f8be80053372fa85636d701ffe`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round93-p4-empty-instance-inventory-20261007/plan.json` — 37590 B — `fde9eb4ea5dc173032b44a94929aed002faac1975b86854a31451f514fce1ba6`
