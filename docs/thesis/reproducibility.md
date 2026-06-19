# 可复现性

Phase 12 每个 run 保存 run_id、experiment_id、RQ、commit SHA、source tree hash、worktree clean、config hash、environment hash、backend、planner provider、scenario、seed、control mode、result、metrics 和 artifact hash。

Full profile 的正式结论要求 worktree clean 且 source tree hash 匹配。
