# RoboMIND 版本核查更正

旧完整目标的 `be28d59219430dc8796f221f7fc4c23e113d6a4e` 固定版本有效。直接向魔搭查询该版本的 `benchmark1_0_compressed/h5_franka_1rgb`，返回 68 个文件；所有路径、大小和上游 SHA256 都与已有完整目标配置一致。完整目标仍因 10 GiB 预算不足而阻塞，本次没有改它的来源配置。

这一版本是 batch 1 上传提交，并非当前整个仓库 HEAD；后来上传的 `example_data` 不在它的目录树中。精选 ZIP 应固定在 `b6ccc32d861713fdf786b9f237a1bcfb51a1063b`。仅凭旧版本不含 example_data 而推断旧完整目标失效是错误的，已由目标目录的直接核查纠正。

证据：`previous-pin-franka-target.json` 与 `previous-pin-franka-target-request.json`（完整目标核查）；`pinned-example-tree.json` 与 `tree-request.json`（旧版本无精选样例）；`example-tree-b6ccc32d861713fdf786b9f237a1bcfb51a1063b.json`（新精选固定版本）。
