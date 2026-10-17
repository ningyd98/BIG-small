# R160：T1 夹具路径与读取记录恢复计划

> 实际规划者：gpt-6-astra（`/root/astra_status_plan`）。待 ROOT 激活，由已明确配置的 `/root/p6_stage_b_sol` 执行一次元数据动作。

原 `rg` 因猜测不存在的 `test_visual_owner.py`、`test_visual_verification.py` 返回真实 exit 2。之后作者未按要求停止，继续 19 次只读调用；完整输出未保存，两项数值返回被截断遮蔽。原准确命令、可见错误及缺口保持原样，不重建、不重放，不将这些读取追认为 B 验证证据。

已从冻结 R158 清单独立确认真实路径分别为 `tests/test_visual_owner_repository.py`、`tests/test_visual_verification_repository.py`。plan.json 列出七项所需现存夹具的完整绝对路径、字节数、SHA，以及六项本轮元数据输入。清单的 all_inputs/protected/owned_existing 均为 record 列表，记录字段为 path/relative_path/bytes/sha256；不复用错误 basename。

ROOT 核对激活后，作者只执行 plan.json.command.argv 中的一次直接标准库动作：核对六输入、七夹具、23 个既有 owned 文件字节和一个新模块仍不存在，独占新建 exactfixture-authorities.json。不会导入产品、扫描源码内容或执行测试、AST、静态、SQL、Git。输出仅短摘要；实际完整工具返回立即保存到本轮 step-report，缺乏独立 stdout/stderr 时如实说明，不伪造。

这不是新 helper 执行层。原失败和 19 次调用零重试；R158 的24路径、23节点和15条命令全部不变，仍0已用/HELD。恢复成功后仅回到 T1 测试和 runner 准备，实际 RED 与生产实现仍经过 ROOT 原门。任何新异常立即停并交下一实际 Astra 计划。

本轮仅确认元数据路径与字节连续性，不授予 B9 软件、native、实际、formal 或 Git 验收。
