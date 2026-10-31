# R372 UTC 交付传输结果（2026-11-01）

实际gpt-6-astra限定计划的7项直接输入及HEAD/分支/上游/origin身份均匹配。两次各30秒上限的HTTP/1.1只读探测均exit128，错误均为gnutls_handshake/TLS连接异常终止；原工具结果分别保存为probe-1-result.json及probe-2-result.json。没有更改TLS验证或持久配置，没有暴露凭据、安装软件或切换通道。

两个探测额度已用完。按计划跳过push及post-push核验，保留明确路径的本地已验证成果。R371五节点PASS和独立审查READY不受影响；远端交付未验证，不能宣称三方SHA一致。Git提交结果及未纳入改动另记本目录local-commit-receipt.json；回执保留本地，避免追逐自引用提交。

研发边界仍为UTC场景新鲜度和helper构造修复；完整UTC、性能和正式研究未验收。无产品/测试重跑，无新诊断工具，历史失败和未交付性能候选保持。
