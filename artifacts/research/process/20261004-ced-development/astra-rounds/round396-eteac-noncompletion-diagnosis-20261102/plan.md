# R396 — ETEAC 不结束的单次有界诊断计划

实际规划模型：gpt-6-astra。状态：PLANNED_NOT_EXECUTED。基线 `9abf127ab0d7d64fb02670eb278519f8d3bde5e9`，研发分支 `research/20261004-continuation`。精确输入及 SHA256 见 `input-audit.json`；机器执行条款以 `plan.json` 为准。

## 问题与静态假设

R390 已批准证据中，PCSC 约 1.503 秒结束；ETEAC `job-ee8c30f834344668` / `sim-6364857a907b` 维持 RUNNING 430.964974 秒，原 timeout=30 秒，attempt end / completed / lease release 空。原内部栈未知。本轮回答为何不返回，不修产品、不重跑浏览器。

已静态确认具体假设：ETEAC 的 TaskExecutor → initialize_task → RetryBudgetService.initialize → SQLite initialize_retry_budget_if_absent。后者持有普通 `threading.Lock` 时调用 `self.get_retry_budget`；该 reader 经 `local_event_repository` 包装，在 scope=None 时再次 `with` 同一锁。待以真实栈和对象身份确认同线程自锁，不能仅凭猜测定案。MOCK timeout 在同步 runner 前后检查，heartbeat 独立；若 runner 不返回，后置超时检查和后续 dispatcher 任务都到不了。关闭阶段仍作为需排除的替代位置。

## 唯一复现与观察边界

从原 E2E07 trace 精确请求取输入，保持 PCSC→ETEAC 原顺序及 S01、seed0、NORMAL、缓存、retry2、supervision300、timeout30000、LEGACY_PIPELINE。采用新隔离真实 SQLiteSimulationJobRepository，原 create_job / CREATED→QUEUED CAS、同一个真实 MOCK worker.poll_once。每种模式一次；不启动 HTTP/dispatcher、不运行 AUTO。新 run/manifest 标明 DEVELOPMENT_ONLY 和当前源码，原 manifest 仅作为历史输入，不能冒充当前源码证据。

只在诊断 driver 内用过滤 sys.setprofile 记录进入/返回，覆盖 worker、runner、harness、TaskExecutor、重试初始化和 repository 装饰器；不包裹或替换产品函数、不改锁。定时 faulthandler 全线程栈加只读 frame 标量，记录嵌套两层 self/lock ID、scope/name、locked 状态；不调用 getter/SQL/repr，不取得产品锁。至少两次分离栈与相同锁身份，配合原普通 Lock 代码，才可确认复现的自锁链。

## 命令、前置与预算

固定命令见 JSON argv：`.venv/bin/python3 -B -s diagnostic/diagnose.py --run-root diagnostic/run --input-audit input-audit.json`（JSON 为绝对路径）。先实现并冻结 driver、完成独立静态审查；不允许准备阶段 smoke import/探针。默认 workspace-write / restricted network / .git readonly 环境，无需 socket 或升级；仅新目录 DB。显式最小环境、模型/硬件/MuJoCo 动作和网络均为 0。普通 import 或权限失败保留为 INFRA_BLOCKED，禁止自动重试。

一次 supervisor / 一个子进程：READY≤10秒，PCSC≤30秒，ETEAC≤75秒，子进程总≤125秒，owned cleanup≤10秒，supervisor≤140秒，轮 wall≤600秒，不重置。PCSC 栈 5/15/25秒，ETEAC 栈 5/15/35/65秒。PCSC 不正常结束则停止，不继续盲试。cap 后只按 PID+starttime 终止/reap 自有进程，不从监控线程关闭活跃 harness；新 DB/WAL/SHM 和失败原样保留。主动截断不伪装产品 terminal。

## 验收、移交与交付

诊断成功需要原语义真实路径、多个栈的停点、同线程同锁身份、进入未返回/close 未进入证据和超时/排队解释。若不同位置或证据不够，明确 UNKNOWN/LOCATION_PARTIAL/NOT_REPRODUCED；不自动追加尝试。新复现能强支持历史同根因，但不能声称读到了原 R377 栈。预期 ETEAC cap RED 是定位证据，不是软件 PASS。产品修复必须下一实际 Astra 轮。

独立审查后仅明确路径提交 R396 小计划、driver、栈/边界、摘要和审查；DB/raw/cache/旧重复输入不交付。保护两原 dirty gitlink、main 和其它 refs。新配额仅普通 commit 一次≤60秒、push 一次≤60秒、exact research ls-remote 一次≤60秒，三 SHA 一致才报告交付；不复用已耗 R393 配额。后置回执 local-only。失败即停，无额外网络/force/amend。

本次规划未执行产品导入、测试、诊断、SQLite、Git 写入或网络。
