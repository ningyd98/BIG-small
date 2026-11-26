# B0 基线筛选预检与当前名义探针状态

恢复旧名义探针 47 件私有原件，归档及文件摘要均与原清单相符。当前独立消费者返回 reconstructed nominal role probe gate rejected source/settings/wire。云和端角色源指纹唯一差异为 vision/capture.py。旧探针归属源码摘要 f8121afbed70cb1ed8fa182c0b5595c54e12b88989c591878ac9987d8fe7ec7b。当前文件摘要为 12424f34802d1b08c32624c423e3f113760b26ad6302736df17e968b9216e5a7，变化首次见于 e20d228d。[原探针清单](../round-p1-development-readiness-20261119/b0/nominal-role-probe-manifest.json) · [换代登记](plan.json)

现行工作树的历史排除索引缺少完整 episode，原入口在建分配前拒绝。用临时配置指向持久工作区内的三份完整原数据，按 100、100、1,000 条复核历史排除，复得 120 个组、四种周期、480 个 NOT_EXECUTED 分配。分配摘要 17908a2e3dbead3c6353434fa0a453f6556f743796584d9b8f240a57db8a103f，与历史分配一致。正式配置及源索引原样保留。[原登记及分配摘要](../round-p1-development-readiness-20261119/b0/prerequisite-readback.json)

原模型配置及加密凭据可用，原 GPU 可见。自动审批拒绝启动新版探针，理由是当前轮尚缺少将模拟 RGB 与深度发送到原付费模型服务的明确授权。探针启动零次，新增图像与模型请求均为零。当前合格 B0 周期和 G2 比较仍缺实测。目标汇报以固定周期及事件触发各自的完整远程发送总数和同任务二元结局为据，保留真实失败和超时。
