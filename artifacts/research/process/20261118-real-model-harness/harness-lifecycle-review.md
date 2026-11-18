# H0/H1 与 Phase 12 软件生命周期审查

基线 `318a546dd3a945bddc076cc06bc3528966a4051a`，审查对象为该基线上的未提交工作树。结论为需要修改。发现 5 项 Important、2 项 Minor，未发现 Critical。以下建议均未实施。

## Important

1. **原生启动缺少已登记 Molmo 环境的准入判定。** `src/cloud_edge_robot_arm/harness/cli.py:31`、`:128`、`:202`。CPU 调用实际 `_native_identity`，给同一应用 site-packages 和本机两个真实解释器。登记的 `molmoer-r505/bin/python` 通过，`groundingpi-r505/bin/python` 也通过。后者的 Torch 来自 `.venv-taichu-round473/runtime-b`，Transformers 来自 GroundingPI 的 vendor 目录。返回路径存在即视作可启动。写入 executable SHA 未与批准值比较。随后子进程直接执行原 episode 脚本，未调用 R545 的解释器、baseline.pth、依赖来源、哈希和 CPU ABI 检查。原 provider 仍会检查 Torch/Transformers 版本及模型，所以此发现证明错误环境获准进入运行，不证明已在错误环境付费或加载成功。最小修复是在启动 episode 的**同一原生子进程**中复用已登记 R545 检查，核验所选 checkout 的实际项目模块，再委派给原 main。CPU 回归使用正确和错误的两个解释器，正确者到达原 `--help`，错误者在创建期次前退出。本机正规脚本与 R545 启动路径的 `--help` 均实测退出 0。
2. **子进程已启动但缺清单时被报告为未启动。** `src/cloud_edge_robot_arm/harness/cli.py:213`。子进程在创建输出并预订云请求后被杀、或在 finally 写清单时发生磁盘错误，会返回非零且没有最终 manifest。父进程统一返回 `NOT_STARTED` 和 2，无法据此判定已消耗额度。外部超时本身有独立分支。最小修复是保留子进程退出码或信号，把启动后的未知结局记为未完成、成本待核，保留已有原件。测试用普通 CPU 子进程写一个阶段原件后以非零码退出并缺清单，再覆盖启动前校验失败。
3. **补充入口未验证旧行是否属于待补的独立阻塞试次。** `scripts/run_phase12_runtime_lifecycle.py:39`、`:62`。输入两份相同 F20/MOCK 行、`count=2`，均会进入执行；将旧状态改成 SUCCESS 或删去状态，筛选结果也相同。来源文件哈希无法证明其不同 ID 和阻塞状态。最小修复是在输出目录创建前验证选择的旧行有唯一非空 ID、原 BLOCKED_BY_ENV、未调用执行器、原 RGBD_CAMERA_REQUIRED 原因和必需场景字段。无来源单条初测保留独立语义。以重复 ID、原 SUCCESS 和不完整行测试均在 adapter 前拒绝，另以原件结构正例核验映射。实际这 18 个 ID、状态和哈希已复核正确。
4. **准备记录的有效场景与所报配置可能不一致。** `src/cloud_edge_robot_arm/harness/cli.py:163`、`:195`。合法 `scene_split="development"` 会进入报告及其配置哈希；prepare 命令实际只传 seed、marker 和 output，原 dry-run 选择固定场景。连包内默认配置所报 camera_position 和 visual_servo 也没有写进原准备期次。使用者可能将该次 PREPARED 当作后来 seed/相机布局的准备证据。最小修复是在保持零调用原 dry-run 的同时明确输出计划设置与实际准备字段，或对于不能表示的场景拒绝生成该配置的准备记录。测试开发 seed、相机覆盖与最终实际 assignment 的对应关系。
5. **证据索引可接受没有阶段的结果。** `src/cloud_edge_robot_arm/harness/evidence.py:104`、`src/cloud_edge_robot_arm/harness/cli.py:223`。用内存文件流输入只含正确 schema 的 result、只有这一项且哈希和大小均正确的清单，实际返回 `VERIFIED`、`episode={}`。同一结果进入启动器会因读取缺失 status 引发未捕获的 KeyError。最小修复是验证该 schema 的必需阶段字段及类型，并对宣称 PREPARED 且来源 COMPLETE 的结果要求原 scene-assignment 和 source-hashes 条目。保留原 FAILED/INTERRUPTED 的部分证据语义；无需追认研究资格或把清单索引扩大为完整远端包。正反测试包括上述最小输入、实存准备目录和有效的失败原件。

## Minor

1. **启动目录决定 Phase 12 补充的源码 commit。** `scripts/run_phase12_runtime_lifecycle.py:128`。从 /tmp 调用当前 git_commit() 得 UNKNOWN，传脚本所属 ROOT 得正确基线，在另一 Git 仓中则会记录对方 HEAD。此运行是脏树，HEAD 单独也不能绑定新增脚本字节。本批独立 verification.json 另有源码指纹。最小修复是 `git_commit(ROOT)` 并在摘要中绑定实际脚本和 adapter 哈希，或引用对应指纹。回归在源树外 cwd 检查相同的 source commit 和源码身份。
2. **严格布尔配置接受 JSON 数字。** `src/cloud_edge_robot_arm/harness/config.py:45`。实测 `visual_servo: 1` 和 `1.0` 都被 Literal[True] 归一为 true，与合法布尔得到相同配置指纹。最小修复为在常量匹配前校验 JSON 值类型，在配置拒绝参数表加入这两个数字。

## 已核实的验收证据

- 独立读取上轮 single-proof 所指原 raw_runs.jsonl，SHA256 为 `1bc6f6975cef1a23e58e6805ce725b1b96ed1cdebdaceebfa4ba248a6300419a`。筛得 18 个唯一 F20/MOCK ID，均为 BLOCKED_BY_ENV、runtime_invoked=false，顺序与本次 18 个 original_run_id 完全一致。新回执的文件哈希、内部哈希、恢复和竞争判据、终态路径判据及实际 SQLite 文件哈希，初测 1/1、补充 18/18 均匹配。初测和补充的首个新 ID 在各自目录内均为 phase12-lifecycle-00001，跨目录引用时需保留摘要或目录身份。正式研究与物理结果仍无新增资格。
- clean wheel 的现存 CLI 实测 version 0.1.0，evidence 对保存的 PREPARED 三文件清单校验成功。19 项 Harness、50 项原 CLI 和 17 项 Phase 12 测试为已有运行记录，本次没有重跑。保留原 helper 的 flock、空 GPU 进程检查、空闲显存至少 **12000 MiB**、RAM 8 GiB 和磁盘 60 GiB 的既有阈值。H1 清除 PYTHONPATH/PYTHONHOME，原入口将所选 checkout 的 src 加到首位。诊断只读取环境、源码及本地工作产物，未启动模型、GPU 计算、渲染器、付费 API 或硬件。
