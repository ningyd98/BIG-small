# 证据溯源

Phase 10.2A 的证据把源码溯源和 artifact 提交分开记录。主要的不可变源码标识是 `source_tree_hash`，计算范围包括已跟踪的源码、脚本、配置、测试和文档，但排除 `artifacts/**`。

必填字段包括：

- `generated_from_commit`
- `source_tree_hash`
- `worktree_clean`
- `diff_hash`
- `verifier_version`
- `command`
- `config_hash`
- `environment_hash`
- `generated_at`

验证器 artifact 只有在记录的 source tree hash 与当前源码树匹配时才可接受。开发过程中可以在 dirty worktree 下生成临时证据，但最终权威性取决于源码树身份，而不是 artifact 文件本身是否已提交。
