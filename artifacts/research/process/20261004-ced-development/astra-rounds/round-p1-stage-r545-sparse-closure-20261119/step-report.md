# 同一冻结产品的 R545 预检闭包

首次 stage 在 R545 打开同提交的固定证明时退出 1。旧部分准备目录与首次日志已留存，原调用没有正式 owner 或 BEGIN。补充了 sparse checkout 的一项 Git 物化，Git HEAD 和 tree 仍为 `4bdb64ebd220b37b728de193706fed83a9813791` 对应的原对象。核对了证明、overlay 和真实委托脚本的 mode、blob、文件长度和 SHA。证明是原 4,426 字节，运行时自身核验原摘要。 [首次失败](../round-p1-development-readiness-20261119/development/first-stage-r545-missing.log) · [物化与原版本逐项核对](sparse-closure-readback.json)

真实 r505 解释器以 `-I -B` 调用预检退出 0，核对 9 个模块。CUDA 初始化、本地模型加载、生成和付费调用均为零。用同一离线安装 wheel 在新准备目录重跑完整 stage 退出 0。22 份配置及角色已逐件冻结，owner 原件与公开摘要分别核验，stage 结束时仍为零 BEGIN。 [CPU 预检摘要](native-cpu-closure.json) · [运行冻结及角色摘要](../round-p1-development-readiness-20261119/development/live-freeze-public.json)
