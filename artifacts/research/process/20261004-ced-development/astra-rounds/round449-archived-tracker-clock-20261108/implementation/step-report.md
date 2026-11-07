# R449 步骤报告

实际 Astra 计划的 37 项输入及原副本在实施前全部一致。原 R447/R448 日志与失败原件保留。

旧 tracker 仅提取原时刻判断函数，实时入口仍自行读 UTC，仍执行 -0.05～5 秒 freshness。新的私有离线适配器每次只接受原判断时间；普通 facts 调用拒绝，精确实时类型门拒绝该适配器。采集入口保存 B/E 初始化、8 次 grounding、17 次 admission 的实际 UTC 和前后 OC1 消费原件。reader 核对文件哈希、帧身份、来源生成、租约、原 D、S、TTL 和顺序后重算，缺失原件拒绝，不补写历史时间。

验证：预期 RED 恰四个缺 API 断言；ruff/format/mypy 全部 rc0；六文件 CPU 回归 **86 PASS**，27.16 秒 pytest，28.034 秒监督。所有进程已回收，无源漂移或残留。R446 两个目标节点及 R448 marker 实测尺寸/深度断言此次真正通过。未重新运行完整 230 项；跨轮不受影响结果分别保留在 R447 等报告。

四个新增节点覆盖历史真实像素在数日后回放、24 类错误原始时间/身份/消费输入、原件字节篡改、单次上下文与异常清理、实例隔离、实时类型拒绝，以及全部 27 个判断时间、原 binding、canonical UNKNOWN 和 Shield 输入/结果重算。软件 stub 明确 SOFTWARE_ONLY，不形成真实 lease/physics 证书。

本轮实际 physics/render/模型/硬件调用均 0。首组实际采集尚未运行；native UNKNOWN，正式研究未验收。后续仅在完整代码审查和实际前置条件满足后，使用新的未来阶段 source overlay 进行 fresh prepare 与原先批准的一次首组采集及独立读取。
