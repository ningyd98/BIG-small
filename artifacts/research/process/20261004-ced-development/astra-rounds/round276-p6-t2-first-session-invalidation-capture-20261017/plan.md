# R276 首次会话失效取证与独立 wait 验证计划

实际模型：gpt-6-astra。仅冻结计划；源码准备与三个新 once 命令均须 ROOT 全文门控。唯一作者仍原 Sol。

## 目的与已知边界

R268 dual 在故障注入前 reserve_plan→_check_ingress:471 拒绝，首次失效原因未知。cleanup 会覆盖 reason，不能从 unwind 后状态猜修产品。R274 五替换现已实际生成 ebf1，但本次读取时 ROOT 独立源验收尚待完成；旧 ed602 完整物理档保持。238 项当前源/保护核对匹配这一精确世代解释。

本轮新增三个独立一次身份：wait_memory、wait_sqlite 行为验证，以及 dual_first_invalidation 诊断。全部 child≤600秒、cleanup≤15秒、540秒原生 faulthandler；逐槽预留、串行 literal dispatch。原 GREEN7、R268 两槽永久已花费，不退款。无新 baseline/Ruff/SQL/Git/reviewer。

## 有限被动观察

仅 dual 加载新 r276_session_evidence；wait 不加载 trace 插件。观察四个已读真实函数：lease __init__:417（注册后455）、invalidate:640（改状态前 call）、_check_ingress:468（原 raise 前471和exception）、_close_worker_lease_session:982（call、closed赋值后987、return）。

用 sys/threading trace 覆盖本次 call 与新建真实线程；不改 profile、不 wrap 产品 callable、不调用 clock/Event/权限方法、不发额外请求、不干预锁或同步。配置前 trace 必须为空，finally 恢复原身份；不使用 all-threads 改写。只读 exact session dict 的指定 primitive、exact Event 内部 bool _flag、同 globals 注册映射身份。多字段观察非原子；注册变化只声明在选定事件观察到。

每 session≤64事件、最多6sessions、栈≤12、全部被动文件≤128KiB；超限明确 incomplete，不重试。回调内无文件写、JSON序列化或新增锁线程，及时丢弃 frame/对象引用。实际 session/worker id 与同 PID 原资源侧车关联。第一次 reason 保留，后续 cleanup 不能覆盖。时钟和权限完全不变。

## 源码与运行合同

同 Sol 只新增本轮 plugin/runner；完整物理 template before、持久 candidate、native原参数/真实返回、limited diff 和报告先保存。原 R268/R235 sources、产品、冻结 observer/dual/原断言不改。runner 复用原实际资源/index语义，限定适配本轮三个命令、trace消费和明确世代。plan.json 给出全部 literal argv、finite env、路径及结果标准。

wait 必须各自实际一节点 PASS、两domain与全部原断言完成、资源清理可信；dual 无论0/1均仅诊断，未抓到首因必须 unknown。每轮独立资源实际分母保留，包括 partial/未poll对象；不能以caps替代。输出永久 workspace，原raw/JUnit/source/newDB归档，绝不SQL。

## 世代与上下文

旧 test ed602 仅经 D274 before/fullbase64解析；新 ebf1绑定实际 after/native/report及ROOT独立接受。26其余源和211保护不变。R268现有精确历史映射沿用，不递归扩张或整路径豁免。旧35缺失、old90、旧30DB、R25810DB以及新R2684+2DB分别保全，新增运行不冒充恢复旧字节。

ROOT可 fullbefore/base64/mode+即时CAS 更新 STATE 的 planning.R268至R276指定事实，PHASE仅append。链接实际R268两诊断及R269-275步骤、R274实际source状态；其他字段/旧结论不动，T2/T12/native/formal不晋升。更新后的精确 context manifest 成为新运行固定输入。

## 执行顺序与停止

1. ROOT审本计划、输入与R274实际源接受；保存上下文精确映射。
2. Sol仅准备两新source并STOP；ROOT全文/native/input/argv门。
3. ROOT依次独立预留 wait_memory、wait_sqlite、dual_first_invalidation，每次只发一个literal。
4. 实际失败停止受影响项回Astra；其余独立项必须ROOT另判适用，禁止自动续跑或重试。
5. ROOT逐项独立完整性/资源/角色结算。首次失效原因和后续修复仅根据新原始证据决定。

完整输入SHA、事件约束、命令与验收在 plan.json/input-observation.json。规划完成后 STOP。
