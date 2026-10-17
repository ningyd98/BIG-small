# R268 — 有界失败取证计划

实际作者：`/root/astra_status_plan`；实际模型：`gpt-6-astra`。本次仅冻结计划；未创建或运行诊断源码。

原 R158.t2_green 已由 R266 结算为 SPENT_UNEXPECTED_FAILURE（ROOT/author 均1/0）。实际 stdout 为 `FF`；两个 wait 后端有 DID NOT RAISE，第三 dual 节点600.767秒后终止且无JUnit。两份完整侧车不能代表被终止节点的全部资源。现有证据尚不能选择产品修复。

本轮新增两个独立、各一次的取证身份：`R268.wait_memory_failure` 仅原 memory wait 节点；`R268.dual_progress` 仅原 dual 节点。每个 child 上限600秒，完整清理总额15秒。不是旧GREEN7退款、续跑或新标签验收；无 baseline、Ruff、SQL、Git、新review槽。

两个精确 argv、有限环境、launcher、路径和角色协议均在 plan.json.commands。保留原 R235 import-only 插件；新被动插件不导入产品、不包装poll、不改profile/trace、不调用clock/authority。pytest 原生 `--tb=long --maxfail=1 --show-capture=all -o faulthandler_timeout=540` 保存失败文本及单次超时前线程栈；不使用会repr任意对象的 --showlocals。

异常位置绑定真实 `tb_lineno`，另列 unwind 后 `frame.f_lineno`。小插件在真实 makereport 的 call.excinfo 上仅取指定失败frames、有限内置primitive/history/state；原 `_Counter.now` 只在精确已加载类身份与内置dict成立时旁观。所有局部状态明确为unwind后、可能closed/revoked/已变，不是故障瞬间原子快照；不能调用getter、identity/read_ns、_live或产品方法。完整细节、深度/事件/UTF8上限见 JSON。

新插件不创建Python采样线程；原生faulthandler watchdog仅按已读pytest源码配置一次并在正常finally取消。进程被终止时不能补造hook恢复/看门狗取消或部分资源关闭。实际栈仅证明采样位置，不证明CPU占比、死锁因果或产品超时原因。

唯一Sol准备新 `implementation/r268_failure_evidence.py` 与 `run-diagnostic.py`，候选先持久化再native保存；旧产品27、保护211、原测试/observer、所有旧脚本均不改。ROOT全文/native/输入/argv门后逐槽预留并发literal。新ROOT/author账本位于R268，旧R158两账本保持spent原字节；fixture仍使用BIGSMALL_R158_COMMAND=t2_green仅为冻结资源格式，不是消费旧预算。

所有新stream/JUnit（若有）/prerequisite/被动证据/sidecar/case/资源/索引/源before-after/工具初始与同session完成原件保存在每个独立workspace目录。console≤6000 UTF8；原始流不裁改，越过32MiB阈值则终止采集并保留实际字节及不完整边界。任何child退出值或timeout都仅为诊断事实。

原R258十DB及两present/二十八absent sidecar、此前workspace三十DB/九十sidecar、历史三十五精确missing和旧九十absent分别严格处理。新运行保全真实DB字节，不SQL读取、不把新bytes冒充旧恢复。原R266中旧ROOT reserved pin仅经原receipt完整archive解析；不对当前spent逻辑路径硬比旧代，不建立全path豁免。

ROOT可在接受计划后以完整physical/base64 before和即时CAS，将R258失败、R264源码处置、R267元数据处置、R266结算与R268pending/实际证据追加到限定planning项和PHASE末尾。原STATE139128/ae2bc7…与PHASE90577/cc1745…为时间点输入；其他字段、历史和T2/T12/formal/native不晋升。旧角色不改，新控制每代完整映射。

输入观测实际固定45项完整path/bytes/SHA，30项既有pin/代际检查全匹配；原raw及完整源索引继续为权威，不重复巨量base64。`input-observation.json`：25321字节，SHA256 `b9bf488904254377daf32daa0ddaca61aafc5f24194c10605a1983e42a00c03e`。

验收只认原始证据完整性及可决策信息：wait准确raises行/已存在值，dual实际线程栈/进度；缺失仍null/unknown。observer/基础设施新失败立即STOP，不重试。取得证据后另由实际Astra制定精确修复；本轮不修源、不运行计划、不放行GREEN/review/Git。
