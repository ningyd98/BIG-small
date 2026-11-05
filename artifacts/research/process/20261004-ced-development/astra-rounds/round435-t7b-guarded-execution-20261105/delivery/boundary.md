# R435–R437 交付边界

目的地是既有公开 origin `https://github.com/ningyd98/BIG-small.git` 的 `research/20261004-continuation`，沿用用户 AGENTS.md 对已验证交付提交推送的指令；只做普通非 force 推送，不改 main 或两个受保护 gitlinks。原目标所有权与授权证据延续 R434，当前 fetch/push URL 未变。

交付 manifest.json 中明确列出的四个源码/测试文件、三轮计划、冻结输入、原始失败与最终验证日志、派生报告，以及 manifest 本身。原始计划/失败/冻结文件不改写。所有 payload 记录 SHA256/长度；暂存和 commit 再逐项核对。

不包含完整批量 raw、实际诊断 actual-diagnostic 目录、运行数据库、缓存、凭据、模型权重、SDK、其他历史未跟踪文件和受保护 gitlinks。actual-diagnostic 原件留在本地，remote 只有 trace-summary 与 local-raw-manifest；它们不是完整远端复现包。spec/日志来自限定验证；本次仅对交付边界核对，不声称通用 secret 审计。

推送后的 delivery-receipt.json、stage/commit/push 原始输出与路径清单保留本地，不纳入其所验证 commit，避免自引用和循环提交。报告中的 Git pending 是生成时状态，最终交付状态以本地回执及实际三方 SHA 为准。
