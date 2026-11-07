# R450 — GPU 独占资源前置与可恢复服务方案

实际规划模型 **gpt-6-astra**；2026-11-08 Asia/Shanghai。仅规划与只读主机元数据调查；未改产品、未执行测试、服务操作、模型请求、engine、physics 或 render。

## 已确认事实和原始证据

R449 软件已通过：expected RED4；GREEN86 PASS（pytest27.16s / supervisor28.034s）；ruff/format/mypy child rc0。fresh whole-change reviewer 尚在独立工作，软件通过不等于实际放行。

原 host-preflight-observation.json 记录 RTX4070TiSUPER 总16376MiB、已用15666MiB、快照利用率0%；PID2296 strata 占15028MiB。磁盘剩余490457927680bytes，超过原32GiB要求。已将其及相关计划/步骤报告逐字复制 intake，10个输入的 SHA256/字节数/副本路径见 inputs.json 和 plan.json。

本轮允许的只读主机调查已经完成，原结果为 intake/host-owner-observation.json 和 service-owner-observation.json：

- PID2296 的父进程1592，均 UID1000，同属用户 unit `qwen38-flash-strata.service`；父管理器1520为用户systemd。unit文件位于 `/home/ningyd/.config/systemd/user/qwen38-flash-strata.service`。
- 该服务 enabled/active/running，自2026-11-07 21:23:09 CST启动，MainPID1592、NRestarts0、Restart=on-failure。无 TriggeredBy/Triggers/PartOf/BindsTo/反向RequiredBy；WantedBy=default.target。
- KillMode=control-group、KillSignal15、TimeoutStop=60s、SendSIGKILL=yes；TimeoutStart=15min。允许手工start/stop。
- 18201当时仅有127.0.0.1 LISTEN、owner1592，没有观察到已建立连接。ready.json只记录文件大小/mtime/UID/mode，没有读取内容。
- Ollama1585属另一个 ollama.service，原GPU compute表未列它；本轮不触碰它。

沙箱/proc看不到这些宿主PID，不能因此声称服务退出。本轮通过获得执行许可的只读宿主元数据命令确认归属；没有auto-review拒绝，也没有读取环境、日志正文、模型profile、请求或凭据。

## 判定与授权边界

**当前原 R439“无并行GPU/physics任务”前置未满足，full实际保持NOT_RUN。** 常驻模型服务即使当刻0%也持有GPU分配并可立即接受工作。无ESTABLISHED连接也不能证明无内部队列或未来请求。这里不推断一定OOM、不发明EGL最低显存值，不更换renderer、设备、依赖或偷偷降低图像/采样预算。

服务由用户拥有且独立长期运行；一般研发授权不能自动扩大为中断该服务的授权。准备工作可以继续：完成现有review、冻结未来source overlay及准备可审阅的操作命令；GPU冲突不需要另跑任何模型/renderer探针。零physics的原prepare-only可在原软件/review前置满足后独立进行，但不由此放行full。

在最终询问用户前，本计划已经把确切unit、影响、停止/恢复命令和失败出口具体化。需要明确的人类授权是：暂时中断这个unit、可能清除其临时缓存/中断未完成请求、结束后按原配置重新启动，并在研究窗口内不启动其他GPU/模型/physics工作。观察到同UID不等于此授权。询问时说明授权来自该长期服务不属于当前已授权研究资源，而非声称AGENTS或skill一律要求确认。

可用的一次简短确认文本见 plan.json.authorization_prompt；本轮不实际提问或执行；ROOT可在独立源码修复/复核期间先就这份具体方案征求授权，但在所有软件、fresh review及实际前置通过之前不得停止服务。后续reader发现的任何源码问题独立下一轮处理，不归入本资源计划。

## 仅获授权后的具体可恢复步骤

1. 原操作之前最多一轮只读复核：使用 plan.json 的 systemctl show 白名单属性、GPU与compute-app查询、18201socket元数据；每命令timeout10s。再次关联服务MainPID/UID/cgroup/starttime，避免PID复用；service配置/状态变化则停止本方案，不操作旧PID。保存带UTC原输出与SHA。活动请求归属仍不读取正文；若已有连接/任务或用户不能确认排空，则延期NOT_RUN，不擅自中断。
2. 仅对该unit一次 `systemctl --user stop --no-block qwen38-flash-strata.service`。每5s读取白名单状态，最多75s，每次等待不超过5s。明确现systemd配置会先SIGTERM，60s仍未结束可对该cgroup SIGKILL；用户授权必须覆盖这一具体行为。禁止额外kill、disable、mask、reload、改unit或改profile。若用户不接受默认超时行为，不执行这条命令，等待其自行处理或另行授权方案。
3. 确认inactive/dead、MainPID0/原cgroup无进程，GPU列表不再有该模型分配、没有其他并行GPU/physics工作，当前磁盘仍≥32GiB；只读观测无法证明未来无外部工作，明确结合用户保留研究窗口的确认，不能写成连续独占证明。正常桌面显示进程不是并行模型/研究任务，保留记录，不杀桌面。如果有新外国compute/physics进程或释放不完整，full不启动，进入恢复。最多再读一次GPU/进程元数据验证退出，不进行CUDA/EGL探针。
4. 只有 fresh review PASS、完整R439/R449源码/时钟/lease/资源前置全部满足后，执行原已批准唯一full组。沿用原wall1800s/outer1920s、读出900s、RSS8GiB、raw16GiB、磁盘32GiB与原physics/render精确预算；不重试，不补样，不启动第二组。GPU方案不改这些数值。研究期间若已知出现资源冲突，沿既有取消/安全停止路径终止并保留partial，不能硬抢资源。
5. 在唯一实际采集子进程退出且完成回收后立即进入finally恢复路径，不为独立CPU读出继续占用GPU窗口；采集失败、超时或取消也一样先确认子进程回收再恢复。随后按原计划进行不占GPU的独立reader，其软件前置/配额保持不变。只恢复“本流程实际停掉且原先active”的这一unit；首先核对当前状态/归属，避免覆盖其他人的变更。仅一次 `systemctl --user start --no-block qwen38-flash-strata.service`，原enabled配置保持，不执行enable/disable。按原TimeoutStart15min，每15s检查一次，最多900s；15秒粒度允许ROOT继续沟通。此步骤会重新加载既有模型，是明确授权的服务恢复，不是研究新增推理请求，不查询模型接口。
6. 恢复核验仅用元数据：active/running、正确unit/cgroup新MainPID、18201原owner listener、ready文件mtime/大小/属主、GPU分配重新出现。它们不能冒称模型推理已验证；不HTTP/健康请求、不发送prompt。恢复配置不保证恢复内存缓存、请求上下文或中断的工作。若启动失败/超时/被外部改变，不反复启动、不偷偷更改配置；原始结果另记为RESTORE_FAILED/UNCONFIRMED并向用户明确报告。若整个ROOT进程被终止，finally不能保证运行，必须保留恢复命令与已停状态供接续者执行。

服务停止和恢复状态独立于研究状态：研究失败仍应恢复；服务恢复失败不能被研究成功掩盖。所有状态转换与原输出保存在R450新implementation目录，历史commands/spec/results/baseline不覆盖。不因停止操作未被完全确认而盲目启动或重复stop；先只读核对，无法判定交用户处理。

## 未授权或无法满足前置的出口

没有明确授权、用户选择保留服务、存在活跃/未知工作，或无法完成资源释放/归属核验，则不执行stop/start，不运行full，也不伪造reader成功；保存 `RESOURCE_PRECONDITION_NOT_SATISFIED`，实际full/read为NOT_RUN。软件86PASS及历史失败原件继续保留，native/full-H研究状态仍UNKNOWN/未验收。用户可以自行安排空闲窗口后再按原前置复核，不默认获得另一次实际配额。

本轮不授权额外actual：physics0、render0、模型推理0、组数0、服务动作0。仅在后续显式授权成立时，条件方案最多一stop、一start；它们不增加R439首组配额。没有新产品修改、pytest、GPU负载探针或整套验证任务。

自审：已确认原服务归属及停止超时语义；没有把idle快照当独占/排空证明；确认前已形成可审阅具体方案；恢复与NOT_RUN路径明确；用户授权边界与资源前置未被静默放宽。
