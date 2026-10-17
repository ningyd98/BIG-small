# R285：新测试世代的三个有限 once 续接

实际规划模型：gpt-6-astra。仅规划；所有运行保持 HELD。

R281 的 193f 测试世代已经 ROOT 567 项源码核验接受，尚无行为通过。原 R276 memory 是真实 regex mismatch 失败；R283 已以 479 项独立核验结算为 SPENT_UNEXPECTED_FAILURE。原始首个失效原因仍未观测，dual 首因仍 unknown。本轮既不修产品，也不重用原失败预算。

## 三个新身份

| 身份 | 目的 | 次数 |
|---|---|---:|
| R285.wait_memory | 原 memory wait 节点、两 domain 完整行为 | 1 |
| R285.wait_sqlite | 原 sqlite wait 节点、两 domain 完整行为 | 1 |
| R285.dual_first_invalidation | 原 dual 节点，四个原函数事件被动取证 | 1 |

旧 R276 memory 永久 SPENT；旧 sqlite/dual 保留 HELD0/1 审计记录，本轮不释放或重定向它们。新三项串行，逐项 ROOT 完整门、单独 reservation、literal dispatch；失败不自动继续或重试。没有 baseline/Ruff/collection/额外测试/review/Git/SQL 槽。

每 child 600 秒，TERM5、总 cleanup15；outer900、kill-after15；原生 faulthandler540。raw 每流32MiB阈值，实际 overshoot 与不完整证据保留，控制台≤6000UTF8。plan.json 已固定全部 argv、env-i、路径、节点与输出。wait 不加载 trace；dual 即使 PASS 也仅是取证。

## 最小源准备

唯一 Sol 从冻结 R276 runner 78491/50f38… 和 R277 plugin 20953/48e4… 派生 R285 两个新文件。只修改 round/文件/环境/输出名称、真实新 SHA、角色/预算和明确来源代际绑定。保留原受保护 reservation try/finally、进程清理、资源消费者、真实 events.db→case 归属、索引 schema 和四个原函数观察逻辑。worker_id 字符串与 worker_object_id 分开保留。没有产品、测试、原观察器、等待、TTL、权限或原脚本修改。

原件已完整物理/base64/mode归档于 before/manifest.json。新候选先完整持久保存，再 native Add、真实参数/actual、完整 after、有限 diff/report；ROOT 全文验证后才能运行。native{} 没有数字 exit；归档末行 LF 与真正 native 参数是不同表示，只能精确证明单 LF 关系，不能 strip 或伪称逐字相同。

## 输入与代际

input-observation.json 固定33项输入，并记录305项实际普通元数据证明：27源（test193f）、211保护、R268六DB与R276四DB原/档及sidecar。完整表由物理观察引用，不复制历史大表。ed602→D274物理before；ebf1→D281物理before；193f→D281 after/candidate/live。其他26源保持。旧 R276 ROOT reserved 代仅用 R283 acceptance.root_before，不能裸比已合法 SPENT 的 live 文件。

原 R276 accepted authority 的68历史容器不递归重审；保留35缺失/null、90旧 absent、旧30DB、R258十DB（2present/28absent）、R268六DB和R276四DB（12absent）的精确界限。每个新运行仍严格核适用字节和sidecar现态，不恢复或伪造旧缺失数据。角色只选择 ROOT/AUTHOR，文件身份只比较 path/bytes/SHA。

## 上下文与实际门

ROOT可先以完整 physical/base64/mode、即时CAS，仅更新 planning.R276…R285 和追加 PHASE 事实段：原 memory失败/479结算、R277–284实际步骤、R281源码接受但行为未验、新三槽HELD。其他STATE值/历史PHASE前缀不变，不提升T2/T12/native/formal。实际新 context manifest SHA作为不可变 prerequisite supplement，在源最终冻结和运行前绑定；不猜未来hash。三运行期间 context固定，逐项角色/结果另存。

ROOT逐项独立读真实actual、JUnit、case、资源、DB、源前后与角色CAS。缺失 raw marker必须presence=false/value=null/unobserved，不能冒充False/PASS；行为通过仍需原完整显式完成证据。dual原函数事件每session≤64、栈≤12、总128KiB，hook精确恢复，缺失/截断/partial均unknown且不重试。真实分母按当次实际对象，不套旧537等数字。

完成本计划冻结后STOP，等待ROOT完整审阅；本轮规划未实施或运行任何新源码。

