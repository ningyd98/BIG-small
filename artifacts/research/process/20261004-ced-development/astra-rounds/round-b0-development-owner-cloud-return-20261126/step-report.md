# B0 开发 owner 的真实发布在首个证据门之前停止

A 用真实 SQLite 作业、租约和采集 claim 提交历史帧作为负控。该图比 claim 早 27 分 50 秒。框架抛出 `source claim is stale or historical; no effect replay allowed`，数据库只保留未完成的采集 claim，尚未规划或生成原合同。现行 SQLite 将底层转换异常折叠为无提交，原外层异常未暴露具体底层文本。A 未重跑，两份封存冷读逐字节一致。[Astra 恢复](stage-a-recovery.md)

B 在隔离网络中使用现役开发编译场景，完成一次真实 RESET、120 个稳定积分步和三次原生曝光。原自动帧在第 0、120 步，第三帧在 owner 的真实 CAPTURE 请求之后，处在第 120 步。原 SQLite 在当前租约下持久化采集、仅本地 RGB 种子的规划响应、原合同和第一条 checkpoint。正常稳定步有 120 次内部 CONTROL 更新，实际原生 COMMAND 记录和动作 span 均为零。两份冷读逐字符一致，租约均已释放。[封存摘要](owner-publication.public.json)

监督初始化无持久记录，CLOUD_RETURN、PRE_SAFETY、PRE_SKILL 均未到达。诊断程序随后在读取 runtime.original 以写摘要时再次报 `coherent current observer source publication unavailable`。这一异常及未落盘的内存日志维持原样。用原 SQLite 行和原发布时间独立复算，checkpoint、版本、预算、原合同身份和发布摘要一致。当前观察源仍被拒。其严格递归检查要求嵌套模型每个字段都在 JSON 中；8 个真实 TaskStep 的可空 `metadata` 都由生产序列器按现行语义省略。仅 ActiveTaskContractRecord 的嵌套精确检查失败，checkpoint 与 retry 均通过。此冲突需要独立 Astra 修复轮。

Raw V3 原状态为 UNBOUND / INCOMPLETE。原帧、两套私有数据库、首次失败与全部派生回执留在 `cache/research/raw/20261126-b0-development-owner-cloud-return-01/`。B 未重跑。未执行新动作、真实远程请求、正式配对或硬件。
