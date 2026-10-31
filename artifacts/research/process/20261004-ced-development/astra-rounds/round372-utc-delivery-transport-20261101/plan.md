# R372：UTC 已验证成果的传输恢复与交付

实际模型 **gpt-6-astra**，2026-11-01；当前只规划。用户 UTC 修复授权及根 AGENTS 的提交推送要求已经覆盖本轮，无需再确认。

R371 已 **5/5 PASS、exit 0、源前后相同、无证据缺失**。交付前只读 `ls-remote` 却 exit 128：`gnutls_handshake() failed: The TLS connection was non-properly terminated`。原件是 R371 的 `remote-read-failure.json`。暂定为 HTTPS/代理/协议传输故障，尚未证实具体根因；不影响已通过的软件验收。

1. 复核 plan.json 中七个直接证据的 bytes/SHA、当前 HEAD `dd9df375e1d372490145327bcbfee5804352fcc4`、分支 `research/20261004-continuation`、上游及 origin 身份。最终独立审查可继续，未完成报告不冻结；不改产品/测试或重跑验证。
2. 最多 **两次**只读恢复探测，每次 30 秒加 5 秒 kill grace；第一次成功即取消第二次。采用每命令 HTTP/1.1。第二次可重复同命令；只有本地证据已确认存在通向同一仓库的合法替代通道，才可使用它。最多查看既有代理设置是否存在，不输出敏感值。
3. 审查后显式路径提交已验证 UTC helper、product、短合同/新增回归及精选证据。无论传输成功与否，保留这个本地提交。排除 local_temporal 性能候选、其他测试、嵌套工作区和无关文件。
4. 探测成功且远端兼容正常快进时，**最多一次**推送，60 秒加 5 秒 kill grace。之后 **最多一次**只读远端 SHA 核对（它是交付核验，不是第三次恢复探测），与本地 HEAD、上游 ref 比较。推送报错但结果不明时，也只使用该次核验，不自动重推。
5. 两次探测仍失败则跳过推送；推送/核验失败或 SHA 不一致则如实报告本地提交和远端未验证状态，保留原始结果并结束本轮传输尝试。已知传输失败属于本计划预期，不要求每个有限重试再开新轮；新的源码/Git/凭据或分叉问题需重新定范围。

只读探测及最终核验命令：

```sh
/usr/bin/timeout --signal=TERM --kill-after=5s 30s /usr/bin/env GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=Never git -c http.version=HTTP/1.1 ls-remote --heads origin refs/heads/research/20261004-continuation
```

正常推送命令：

```sh
/usr/bin/timeout --signal=TERM --kill-after=5s 60s /usr/bin/env GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=Never git -c http.version=HTTP/1.1 push origin HEAD:refs/heads/research/20261004-continuation
```

全部命令 cwd 为项目根目录。网络操作上限为 2 次恢复探测 + 1 次 push + 1 次交付核验，串行执行；产品/测试/自检预算为 0。不得禁用 TLS 校验、改持久配置、安装软件、暴露凭据、force push、扩大诊断或递归审历史。只记录小型命令结果与一步交付报告；无需新 runner。不得 `git add -A` 或混入已有无关暂存内容。

软件开发验收与远端交付分别记录：仅三 SHA 一致可报告远端交付已核验；否则保留本地已验证提交并明确受阻。完整 UTC、真实运行、性能与正式研究验收未因此改变。输入清单和精确身份在同目录 plan.json；未完成的最终审查报告不在冻结输入中。
