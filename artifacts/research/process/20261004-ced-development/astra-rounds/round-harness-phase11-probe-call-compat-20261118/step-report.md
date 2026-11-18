# Phase 11 探针调用兼容与格式复验

基线 `3ca2f6415b330d38ddc2d834c5f788a56c0d9517` 的 `suite-07` 退出 1，703 通过、21 失败。20 项在外层探针遇到 `lifecycle_only` 多余关键字，1 项在内层草案调用遇到同一错误。原日志、JUnit 和逐节点结果均已保留。[Astra 计划](plan.md) · [失败摘要](original-failures-summary.json)

修复仅涉及三个探针和三个草案调用。默认值和显式 `False` 继续使用原调用签名。显式 `True` 传入生命周期选项，恢复探针继续使用原 10 ms 延迟。布尔类型检查、产出证据校验和软件生命周期资格保持原样。

首轮 Ruff 检查记录了一个 101 列的调用。按格式计划只拆分该行。修正前后去掉位置的 Python AST SHA256 均为 `acb7cfb0655a448a0b9a587d1df37071a2daf9ac94e64fa22cce72a05ea7b06c`。Ruff 与 Git diff 检查退出 0。最终适配器 SHA256 为 `bfca5138961412f1e6c82ef333303fb918e799d6d49b082f70166b9794dd5de9`。[格式计划](../round-harness-phase11-probe-format-20261118/plan.md) · [AST 对照](../round-harness-phase11-probe-format-20261118/format-ast-equivalence.json)

| 独立检查 | 冻结提交 `02dbaef93246bcfe15d2c51942e87ee06c44f105` |
| --- | --- |
| 两文件专项 | 42 项回执真实性、30 项生命周期，共 72 项通过。退出 0，81.728 s。JUnit SHA256 `53ee1d908f7c0c4c1386211e46fd5db0fd92b801f1afc8387b626b77c4594cd9` |
| 原 `suite-07` | 724 项通过，0 跳过，0 未记账。退出 0，222.152 s。JUnit SHA256 `db1454df5fd701c568e5e9965247c72975a1dbd8d6c2aa58b4ce996464908a6e` |
| 原节点对账 | 新旧节点输入字节相同，SHA256 `40ab4c8ae9fb61bbe9ceb93637265735eec5888a3d856557ed59e179a235e278`。703 项持续通过，21 项由失败转为通过，逐节点核对 SHA256 `acd2a4912267983d5340f679698aa8892909e301c2ab20a2153e2e09a10a937d` |

独立只读查询 SQLite 与适配器回执。显式软件生命周期的三个 `LEGACY_PIPELINE` 探针均成功，共 4 次尝试、4 个已释放租约。恢复探针记录租约到期，两个竞争 worker 中实际调用 runner 一次。默认路径的三个 `RGBD` 探针均因 `RGBD_CAMERA_REQUIRED` 阻塞，执行器调用为零。读回 SHA256 `06f835155e6d0202f0f7f3af678e6be32b063aa02e73a7093208ee50c2abd92e`。

本地原件存放于 `experiments/results/phase9/harness-candidate-validation-20261118/`。折行前独立专项 72 项通过。折行后首次专项被会话中断，在 37 个通过点之后停止，未生成 JUnit。表内数字来自随后在冻结提交完成的专项与分组，各自单列。正式研究与实机资格仍未验收。
