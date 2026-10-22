# R302：选择性生命周期观察器修复与真实双库行为验证

实际模型：**gpt-6-astra**。本轮先生成计划；由已绑定 `/root/runtime_repair_sol` 实施，ROOT 独立复核。目标是修复当前已定位的观察器高频工作，并实际完成双库 4 个 commit-loss 与 1 个 same-owner 场景；不开展正式实验。

## 证据与根因边界

R296 唯一诊断已结束并完成 ROOT CAS 结算，ROOT/AUTHOR 均 SPENT 1/0。child 1 / wrapper 0，409.352 秒，完整诊断18条、0丢弃、65333字节；369次资源尝试、368初始化、369清理。仍在 commit-seam-0 的 reserve_plan 前失败，真实故障注入0次。已存在的 R300 assessment 与 settlement 是直接前置，不重跑旧 gates。

真实 record[3] 的 heartbeat confirm 在非原子取样中 completed/cancelled 均 true；broker 已在 queue.get，main 在 profile→local_temporal→history 重复校验路径。**不能认定已证明 false timeout**。

源码确定的问题是 `_b_t2_observe.profile` 每个 Python/C 事件都扫描所有历史 worker、取得 guard、调用 is_alive。其工作随业务事件量与历史 worker 数相乘。先修这一条可独立定位的问题。产品 semantic_projection/history 重复递归是次级候选，尚无复杂度测量，本轮不删 codec 校验、不修改产品。

所有实际输入 SHA256、原失败、已完成门禁与结算 pins 见 plan.json；input-observation.json 保存 witness 和本席位只读发现。

## 最小修改

仅修改 `tests/test_operational_runtime_closure.py` 的 `_b_t2_observe`；新增 `tests/test_t2_observer_lifecycle.py` 与本轮证据/简明 runner。其他既有测试正文、wait逻辑、四处真实 COMMIT后同连接关闭、全部断言逐字保持。产品文件全部保持原 hash。

- profile 首先按精确 code object/event 分派；无 wait callback 的无关事件直接返回，不扫描 worker、不取 observer guard、不调 is_alive、不逐事件计数/采时。
- 生命周期仅在真实 poll、session 构造、线程 start、heartbeat 安装、原 cleanup 边界采样；保存构造失败和 worker 尚未安装 session 时的实际关联。只用真实对象身份，不能按线程名猜归属。
- 不删除未poll/部分初始化/结束线程的分母。保留原资源字段、实际峰值观察口径、构造/cleanup事实与全部原上限；未知不写0。
- wait_observer 存在时保持每个原事件及 frame/event/arg 原样转发，尤其真实锁 c_call/c_return。恢复 profile/trace 原身份，无新增采样线程、sleep或GIL调参。

## 执行顺序与额度

| 新 R302 key | 次数 | child / outer | 出口 |
|---|---:|---:|---|
| observer_red | 1 | 60 / 180秒 | 仅原无条件采样的指定断言失败 |
| observer_green | 1 | 120 / 240秒 | 相同回归测试通过 |
| dual_behavior | 1 | 600 / 900秒 | 四个真实commit-loss+同owner行为完整通过 |
| wait_memory | 1 | 600 / 900秒 | 原memory节点两种时钟域通过 |
| wait_sqlite | 1 | 600 / 900秒 | 原sqlite节点两种时钟域通过 |

全部0 retry。完整 child argv、独立目录、环境和 launcher 已在 plan.json 固定。先仅准备小型确定性回归并跑RED，不再重复耗时双库RED；RED必须指向真实的无条件采样缺陷，不能仅断言新函数不存在。然后修复观察器，冻结新G1源码与新SHA，ROOT一次完整差异/native/argv审阅；GREEN通过才跑dual，dual通过才依次跑两个受影响wait。

旧额度永久spent。本轮五个新key单独ROOT/AUTHOR ledger，fullbefore/base64/mode+CAS，ROOT逐次reserve、实际Sol消费并settle；未知执行状态不退款。用户已授权连续解决，无需重复用户逐步确认。

## 源码世代与有限运行工具

G0=原193f测试，完整before存档；新回归在RED前冻结。G1只改变 `_b_t2_observe`，区域外逐字核对。原27/211沿已完成的有限检查与manifest进行新世代比较，不递归重审68历史容器。原lease f71d、codec、worker均不改。

双库使用原08df被动插件的新副本，仅调整本轮身份、路径、KEY、PLAN_SHA、新TEST_SHA及gate round；保持全部观察逻辑、TARGETS、原lease偏移、事件/字节上限及非原子说明。两个wait用原资源与场景证据，不加新被动插件。新gate只绑定本轮实际源码/argv，旧source-gate及prerequisite不改。

runner采用标准库和已审阅cleanup/resource/index helpers，不复制94KB authority流水线。只允许选定key、精确clean env、shell=False、DEVNULL、新process group、原32MiB raw阈值、TERM5/KILL/reap总15秒和真实cleanup。ROOT审阅一次准备源码即可，不另加通用gate框架。保留真实PID、原R235启动导入前置；显式禁用非指定pytest插件，记录此环境差异，不据耗时单独下因果结论。

每次保留完整raw、JUnit、实际工具回执、资源/cases、源码前后pin、所有新数据库及存在的WAL/SHM/journal原件与归档。只读索引不执行SQL修复。35原DB/90sidecar缺口不抵销。

## 验收和停止点

dual必须真实完成四种durable phase、原顺序、真实关闭错误、四次重启无权限证明，以及same-owner NEW_COMMIT、历史重复与变更请求拒绝。wait须保留真实阻塞后原时钟越界拒绝与预算不回填。必须 observed.assertions_completed=true、完整资源清理、线程/钩子恢复和双库被动证据0drops/errors；child0本身不够。

任何新失败或缺失证据停止受影响链、保留原样并进入下一次真实Astra根因计划。若dual仍失败，不消耗wait额度，不重试或改TTL；使用新witness及采样计数继续定位codec或其他原因。只接受本轮选定RPC/执行链路的软件行为，不宣称整个T2/P6/T12/native/formal完成。

HEAD保持b6b3至本轮冻结/运行结束；随后ROOT依既有授权按明确路径commit/push并核对SHA。规划不构成实施或通过结论。
