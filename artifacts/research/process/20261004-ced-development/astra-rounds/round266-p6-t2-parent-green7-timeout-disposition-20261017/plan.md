# R266：父 GREEN7 两次实际失败与超时处置

实际作者 `/root/astra_status_plan`，模型 `gpt-6-astra`。仅计划，等待 ROOT 门。29个精确输入 pin 见 plan.json 与 input-observation.json。

原唯一 GREEN7 已消耗：initial7e40f3/session5384，9次同session等待后22551b exit2；child -15、wrapper2、timed_out=true、accepted=false，runner elapsed600.7672149199934秒。stdout原字节FF、stderr0；JUnit不存在。不能按poll等待总和替代时长，不能记7项结果或软件通过。

两个 wait 节点确有实际失败：memory/sqlite侧车均第二poll抛 Failed: DID NOT RAISE any of (RuntimeError, ValueError)，assertions_completed=false，observer/method恢复true、各cleanup_errors空。第一poll正常，两个D_app文件保存完整真实锁等待、counter由0到60e9、释放/reacquire顺序及无job COMPLETE；这支持D_app子场景已过而D_lease随后失败，不是整节点PASS。D_lease无case/history和精确异常栈，不能判断原4310 operation与4338 reserve_capture哪个raise期望未满足。

源码实际在job view与event lock之后调用_check_local_locked，再session.evaluate_locked；broker检查当前active segment的_live。fixture D_lease使用session.ttl_ns作为counter目标，产品deadline来自事件origin加TTL。实际失败时是否推进/推进到当前deadline、是否续段或holder观察未成功，均没有足够原始证据；不能据此猜改app、lease、heartbeat、wait、TTL或原断言。

600秒终止是另一未定边界：dual_database/commit-seam-0有新DB路径，但无第三完成sidecar/栈。不能推断死锁、CPU耗时或阻塞函数。JUnit缺失及exact7/19资源案例拒绝是失败/终止后的结果；case binder因侧车行为失败拒绝建立成功归属，不是已确认新consumer缺陷。1059 attempts/1055 initialized/1059 cleanup仅两份已完成sidecar分母；第三节点可能未报告分配，不能宣称全子进程资源闭合。进程leader已reaped、group不存在、cleanup errors空仅保留为真实进程事实，未知OS/native/network保持null。

**本轮可落实动作仅原键failure结算。** 已全文读ROOT未执行脚本root-parent-green7-failure-settlement-gate.py，6630 B /34da62aafb833023f2828bde338144734987e7614e7f4e9480d40fb01f5e5ece。ROOT完成原件/源码/argv门后，用原R258.post_run权限一次120s有限标准库元数据调用：完整before/base64/mode归档、即时CAS，将原R158.t2_green ROOT RESERVED_BY_ROOT1/0记SPENT_UNEXPECTED_FAILURE1/0；author当前SPENT1/0不动；其他条目/模式不变，真实result/tool引用保留。不是新产品验证槽、不退款、不重试。plan.json列精确argv、finite env、输出与前提。任何失败保全后STOP，不能把未执行草稿当已结算。STATE/PHASE不由本计划改动。

R266规划器7c28c8字段错误原件保留，R267已接受弃用；复用成功源码输出，不重放。control_before必须按original/archive/base64解析精确历史代际，不把当前角色硬比旧original。

当前证据尚不足以选择可靠源码修法。本轮不修改产品/fixture/observer/runner，不运行产品、SQL、测试、AST/编译/静态/Git或诊断，不延长原600+15，不新建运行槽。后续决策缺少D_lease准确raise栈及当时deadline/counter/holder状态，以及第三节点终止前真实线程进度。若现存证据和有限源码仍不足，下一真实Astra计划须明确最小原始观测方法和新的独立一次诊断边界；它不能冒充已耗尽GREEN7的续跑。用户持续开发授权允许随后有依据地规划修复及必要有限新验证，不引入无依据的人工再批准流程。

保全所有原raw、当前10个新DB及其archive/sidecar、旧35missing/null与历史DB边界；清单不冒充新DB语义或完整旧字节。fresh12仍未启动，Git0，T2/T12/native/formal均不完成。冻结计划后STOP，不由planner执行结算或修复。
