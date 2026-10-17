# P6 实施拆分准备（阶段记录）

NON_ACTIVATABLE_PENDING_P5；READING_PAUSED_FOR_R108。此记录只保留稳定代码读取成果，不构成完整实施计划或新执行授权。R107 产品仍由原 Sol 单写；本轮未读取或 pin 三份活动源，未运行产品/测试/actual/Git。

已确认 master Task6:322–359 原 13 路径与两份既有 readiness；SkillExecutor 的实际 handler 在参数和 preconditions 之后；backend 有三个 mj_step 循环分支、joint 延迟队列与直接 gripper ctrl 两条 mutation 路径，必须分别布门。RawRecorder 现有唯一 observer/_clock_pair/purpose/flush 是 D/S sidecar 落点，不能另设 observer 或用审计回调作 veto。

拟拆分：①私有 broker/具体仓储 LockedLeaseView 与 acquisition/heartbeat/rollback/CAS 生命周期；② event Memory+SQLite 真 bootstrap/publication/grounding/verification 的新 D 路由；③ handler、queue admission/dequeue、gripper 与每 mj_step 真门；④已有 recorder 的完整分母 D/S sidecar；⑤ restart 终止与真实两仓储端到端 CPU 正/负链。所有尚待最终可激活 Astra 固定范围与预算。

后续须明确：新分支 UTC veto 的全部生产调用点/codec 迁移，不能只改当前租约谓词；job SQLite 的 acquire 在 BEGIN 前取 UTC 而 heartbeat 在 BEGIN 后取，D 分支应统一锁后读取。job publication guard→job txn→event txn/Memory lock 顺序，broker 不持仓储锁；两个 DB 的两次 commit 不冒充一个原子提交。service.start 在 dispatcher 前 recovery；recovery 显式 requeue 与 repository retry_job 都要验证旧 operational attempt 不被重建续命。主 D_app 与 broker D_lease 各自原域判断，AND 无跨域 min，父窗口同域规则不变。

测试来源方向：现有 tests/test_visual_worker_runtime.py 的 event Memory/SQLite 真仓储分支可复用构造材料，但其 public WorkerRuntimeSource 不是新 live startup 权限；须使用最终 P5 私有真实工厂入口。synthetic frame/model 明记 CPU，不伪称 actual；后续配方不得用恒 VALID verifier。建议完整正链两后端、失效线程/view/事务、heartbeat 不刷新 task、4.9→5.1 dispatch、queued/gripper/三 physics 分支、partial/e-stop/observer、restart/suspend、D/S 分母各自有可指认节点；具体分母/命令仍未制定，执行额度 0。

稳定输入见 JSON；完成 P5 后绑定十源最终 freeze 和不同作者验收。本文因 R108 优先暂停，不声称准备已经完成。
