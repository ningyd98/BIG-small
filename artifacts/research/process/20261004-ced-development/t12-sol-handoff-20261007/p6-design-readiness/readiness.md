# P6 真实 D lease 与最终动作入口设计补充

**NON_ACTIVATABLE_PENDING_P5**。实际 gpt-6-astra；只读设计，不是实施派单。承接 p6-readiness，本文只补足租约线程、事务与真正 mutation 的设计，不读取/pin 活动 P5 草稿。不证明软件、actual、suspend 或 formal 通过。

## 合同与代码依据

master Task6:345 要求“事务内与真正dispatch前分别当前read”，:349–352 要求真实 Memory/SQLite 正链、4.9 秒返回/5.1 秒 dispatch 拒绝，以及“完整新路径不能部分D部分UTC却宣称同域”。R100:42 的原文为“Parents must be issued in the same live context and cannot be imported/cyclic.”；:44 要求 current 配各自原 origin；:46 明确“Lease clamp is an intersection: D constraints AND the actual current UTC lease/unique-attempt/fencing veto.”；:48 把真正 dispatch、事务和跨线程闭包留给 P6。因此父窗口同域不可放宽，而 lease 原本就是类型化交集，不要求或允许跨域数值 min。

OC1 `operational_time_v1.py:258–275` 精确检查原 PID、boot/namespace、Python/native thread。job SQLite `publication_guard:53–79` 已有按 DB 的 RLock+flock；acquire:358–366 先 UTC now/expires 后 BEGIN IMMEDIATE，heartbeat:427–471 则锁后取 now。新 D acquisition 必须锁后 fresh read。当前 heartbeat/release 没有统一使用 publication_guard；新版本所有相关写者需统一。event Memory:278–350 的实际锁、event SQLite:2882–2925 的实际 BEGIN 是持久链入口；job InMemory 实际继承临时 SQLite，不能冒充 event Memory 分支。

`skill_executor.py:113` 左右 handler 在参数及 preconditions 之后。backend:765–795 joint 可只入队，:799–812 gripper 直接写 ctrl；:975–995 的 `_apply_control` 才应用到期队列；:554–608 三种 step 循环与:613–617 的观察分支都实际推进 S。R91 design:65 明确每步 PRE/POST、晚返回保留事实并禁止后续成功，不声称 precheck 消除任意阻塞间隙。本文是源审查，不是运行故障；有限输入 SHA/bytes 在 JSON。

## 主方案：两 authority 的真实 D 合取

拟支持版本 `OPERATIONAL_LOCAL_CONJUNCTION_V1`：主线程保留 P5 D_app；专用 lease broker 线程自己创建、持有、读取原生 OC1 D_lease。心跳线程走实际 repository 到 broker，不读取主 owner，不复制 context 冒充线程。broker 不是第二物理执行者。

许可是 `AppWindowVerdict(original app domain/windows/current receipts)` AND `LeaseVerdict(original lease domain/epoch/current receipts)` AND actual source/job/唯一 attempt/fencing/payload/CAS。两个谓词各在原域真比较；记录两个 domain，不导出伪公共 deadline_ns、不跨域减/min/clamp、不把未知改名 VALID。P5 的 parent/age/task/verification 继续在 D_app 原域配对句柄；D_lease 只判断它真实生产的 acquisition/heartbeat。任一 UNKNOWN/expired/缺项都拒绝后续受限操作，并注明原 authority。

完整新标签要求本地 task/verification/publication/lease 全部完成真实 D 授权迁移；P5 的 UTC_LEGACY_VETO 过渡分支仍保留原名和未闭包边界。新本地 schema 不能由旧 UTC expire 逻辑重新授权或被称 UTC-independent 却继续以 UTC 判本地许可。外部 UTC frame/证书/第三方 lease 仍原路由、1000ms 规则及无桥 UNKNOWN；不伪装 D。这是有据的合同解释，不是产品验收。

### 预算与真正 heartbeat

broker 在实际 factory/仓储生命周期、首次相关 acquisition 前建立，注册具体 repository/DB 和 epoch；公开 worker 构造、job 字符串、描述对象不能自授权。真实 acquire 锁后读取 D_lease，保留原 TTL 政策和原 acquisition。真正 heartbeat 只有在旧 segment 未到期、实际 lease/fence 仍有效时，才按冻结 TTL 生成新心跳事件和新 lease segment。这保留原有续租语义，不把 retry/晚启动/重建对象当心跳，不改写旧事件/deadline。等值过期、取消、释放、重分配、UNKNOWN 不得复活。

每个 segment 的政策预算不扩大；记录完整 heartbeat 链与当前 segment CAS。合法续租不能更新 D_app 原 task/verification/recovery deadline、retry/no-progress。若原 lease 政策另有硬上限，只能从 D_lease 的原始事件生产并保持，不能事后跨域换算或晚开时钟刷新；本文不自增一个原合同没有的 task ceiling。测试应分别证明合法 heartbeat 续活与禁止原任务续命，既不能用无限心跳越过任务 deadline，也不能把正常可续租链改成必然 STOP。

## 一次性 LockedLeaseView 与真实事务

拟新增 `simulation_runtime/operational_lease.py` 容纳 broker、typed obligations、私有 registry。以下是待绑定设计接口，不是已有代码。

1. 具体仓储 `_open_operational_view(purpose, exact_operation_digest)` 只在真实 publication guard 和 job BEGIN IMMEDIATE 后直接读取 job/lease/唯一 attempt/fence/revision。实际注册 entry 绑定不可复制对象 identity、具体 repo/DB、txn nonce、持锁线程、epoch、原 row revision、operation digest。nonce/hash/调用方填入 view 只是描述，不能登记权限。event 事务绑定同次真实 job view 与本次 event CAS。
2. `broker.evaluate_locked(view_handle, operation_kind)` 在自身域 fresh read；broker 不取 repository/SQLite/physics 锁，不回调需要调用者锁的方法。它只读由已登记具体仓储实际签发的 view。registry 短 mutex 不跨 RPC 等待。已关闭 txn、错误对象/线程/purpose/digest/epoch 均拒绝。
3. view 一次性状态：OPEN→DECIDED→CONSUMED→COMMITTED→CLOSED；rollback/exception/CAS!=1/connection close→INVALIDATED。实际 holder finally 关闭并提升 generation；结果只能在原 guard 内消费一次。提交后的序列化收据不可当许可，不允许同 token 重新 open。
4. acquire/heartbeat 的 temporal mutation 使用 PENDING proposal；仓储实际 CAS+commit 后，以私有同事务回执确认 exact row digest，才 ACTIVE。rollback/CAS 失败撤销；commit 成功但确认丢失/进程退出保持 UNKNOWN 并终止旧 attempt，不猜成功、不恢复预算。broker 从不阻塞等待仓储回调 commit。
5. 新版本 cancel/reassign/release/expire/attempt close 及最终物理门全部服从同一跨进程 publication/fencing guard。无本进程 live broker epoch 的其他进程不能产生 positive，但正常受控终止可以撤销任务。内存 registry 不冒充跨进程权限。

锁序固定：job publication guard→job transaction→event transaction/Memory lock（如需）→短 registry 操作→broker RPC→主线程 D_app fresh read→本次更新/短物理操作→commit/失效/close→释放。任何调用点不允许反向 event→job。broker 不碰这些锁，防止 main 等 broker、broker 等 main。跨两个 SQLite DB 不声称分布式原子提交：publication 在持有 job 稳定 guard/事务时 commit event DB；若确需双 DB 写，下一计划列显式 fail-closed 阶段/幂等记录，不能把两次 commit 称为一次。

RPC 失败或等待超限拒绝本次操作、不生成新期限。每个短单元之间释放锁让 heartbeat/cancel 可进入；不得跨 cloud/render/整个技能或 N 步轨迹持锁。一个 native mj_step 本身不可回滚且可能阻塞，只持有本次单元的锁，晚返回后处理超期，不臆造它的 wall 上界。

## 真正 mutation 的全部接点

| 接点 | 新分支行为 |
|---|---|
| publication/PRE_SAFETY/PRE_SKILL | 原 source/window/budget/geometry/payload/CAS 门保留；锁后当前读，不复用早期 VALID。 |
| SkillExecutor handler 前 | 参数/precondition 后消费一次绑定 action/step/payload 的私有 HandlerIntent，再调用原 handler；不跨整技能持锁，不新增 executor。 |
| apply_joint_targets | clip 后、入队或更新 target 前短 guard；队列保存原 action/step/payload/fence/epoch/generation/window IDs，但描述不授予永久权限。ACK 只代表接受。 |
| apply_gripper_command | `_gripper_open` 和 data.ctrl[7:9] 实际写入前同一短 guard；不能只护 joint。 |
| _apply_control dequeue | 到期项先按原 context fresh gate，再 pop/apply；已取消/过期项不更新 target。首次实际 start 重新通过原帧消费/TTL/native 门，不能以新窗口替换原队列来源。 |
| step 三分支 | 每次循环一个短 guard 包含到期应用、ctrl 更新与一个 mj_step；观察分支的 `_advance_observed_physics_step` 在同一门内。不能只 check chunk 开头，不能多推进一次。 |
| continuation | 每步原 task/lease/硬停止与登记 action horizon/owner；按 R91 不把旧 frame native TTL 强加每个后续控制步。真正新观测消费/新动作仍完整 TTL。 |
| POST/terminal | 真 D_app PRE/POST、broker 引用、S_BEGIN/S_END、实际 effect。晚返回保留已发生的 step/ctrl，标 partial/incomplete，拒绝后续和成功，不抹除事实。 |

这里的原子性是同一 ownership/fencing 快照内的离散 admission 与 mutation，不是跨域“同一时刻”，不是任意 host pause 下硬期限前必完成。broker/main pre-read 的真实顺序要记录；晚 post 不可倒推补造 pre 合法。正常链仍须在各原门有效时完成 R91 完整 S 终态；abort 不算正常完成。

e-stop/safe hold/清队列始终独立可达，现有 emergency_stop→hold_current_joints→_apply_control 不能被新过期门递归阻塞。不给 caller skip_guard flag；内部停止旁路只停/保持/清命令，不能发新目标。不能声称可强行中断阻塞中的 native 调用。operation audit observer 仍只记录，异常不充当 admission veto；显式 gate 在 mutation 路径。既有 step observer 异常行为也不暗改。

## 路径与支持边界

沿用原 Task6 的 13 路径。下一可激活计划需精确追加：NEW `simulation_runtime/operational_lease.py`；MODIFY `simulation_runtime/repository.py`（真实 job 协议，区别原 event 协议）、`edge/runtime/skill_executor.py`、`simulation/mujoco/backend.py`。`vision/raw_recorder_v3.py` 沿既有 readiness S2 接唯一 segment sink，不新增 recorder。全部路径均在 src/cloud_edge_robot_arm/ 下。OC1 不改，控制器/阈值/顶视/标记不改。

P5 最终 worker.py/worker_runtime.py/operational_windows.py 的私有 startup、original source、scope、live check 接口待冻结验收后逐项绑定；本补充不猜最终签名。service.py/recovery.py 仅为条件追加：若最终真实 factory/仓储不能覆盖 broker startup 或全部旧 attempt requeue，下一计划列确切入口；不默认扩大整树。新 typed records 可放新模块，不预设 models 改动。

当前可支持目标是同进程真实 worker 主线程+专用 broker+唯一受控 MuJoCo S；event Memory/SQLite 与真实 job repo 均需闭包。重启/boot/namespace/source 丢失终止旧 attempt 和所有 view/epoch，不能从持久数字恢复 live handle。显式 requeue 不能刷新同一任务预算；真正新任务必须有真实新任务授权。自动同 boot 恢复、实际 suspend、任意硬件均不宣称。未测 scope 不晋升，但不把普通受支持 CPU 正链一律 UNKNOWN。

尚待未来计划绑定：最终 P5 registry/scope API、原预算来源与撤销、broker RPC 等待策略、schema/每个 writer 及锁序清单。这些不要求正在实施 P5 的 Sol 停工。

## 后续 CPU 验收定义，本轮执行为零

下面是行为组，不是已批准新节点/次数；具体节点、参数分母、RED/GREEN/static 一次性预算待 P5 冻结后新 Astra 计划确定，不重置 R100–R104 额度。

1. event Memory/SQLite 各有真 startup→bootstrap→publication→grounding→PRE_SAFETY→PRE_SKILL→handler→ACK→start→effect 正链，不用恒 VALID verifier。
2. 两实际线程各自 OC1 可通过；跨线程句柄/复制 view/context/假 epoch/domain/payload 拒绝，两个计数数值相同也不能跨域比较。
3. acquisition/publication/heartbeat 锁等待越过原期限拒绝；合法 heartbeat 正常续 segment，原 task/verification 不变，晚 heartbeat 不复活。
4. 一次消费、rollback、CAS失败、connection close、commit close、pending/确认丢失/旧 epoch 各有失效断言；自填 view 不授予权限。
5. precondition 后 5.1 秒拒绝实际 handler；ACK 后到期/重分配的队列不能更新 target/ctrl，立即 gripper 同等受保护。
6. 正常 chunk N 真走 N；第 k 步后失效只保留 k、拒绝 k+1。native 单步晚返回保留 partial、禁止完成；覆盖三个 loop 分支。
7. publication/heartbeat/cancel/mutation 并发用确定 barrier 检查锁序与 fencing，不用 sleep 猜顺序或模拟 timeout 冒充 wall。
8. broker 失联/租约过期时 e-stop 可达；audit observer 异常不改变许可；合法心跳不能越过原 task deadline。
9. 重启终止、不重建权限/刷新预算；缺 suspend scope 拒绝、真实 suspend NOT_RUN；完整 D/S、partial/missing 分母保留，CPU 不替代 R91 九组/正常全链 actual。

激活前重验稳定输入、P5 最终 freeze/独审，固定 exact 源、验证分母/额度和 actual 门。本文只形成设计依据；不批准任何产品、测试或 actual 动作。
