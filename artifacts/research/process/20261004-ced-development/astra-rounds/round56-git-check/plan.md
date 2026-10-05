# Round56 Git check 最小修改计划（仅计划）

只读复核：当前 HEAD 为 `24ddf13193a1547edeab39165846ff716a0b5f3d`，分支为 `research/20261004-continuation`。原 scope 固定 377 路径、19,863,389 bytes，SHA256 为 `c78c28e37b41ec7b63e36a1f3d0407ffd36938447a0be138b7604197b7b1f937`；当前 staged 精确为这些路径加 scope，共 378 路径，全部工作区与 staged blob 均匹配冻结 pins。

`git diff --cached --check` 仍退出 2，共 264 条 trailing whitespace：19 份原始 pytest 日志 258 条，2 份冻结 diff 6 条。没有代码、文档或其他文件类型诊断。输出 SHA256 为 `4b96a3f2cbecf8208c2580e16bb3c2160daec04178176b8a52eca9918bc4dc0c`。日志中包含历史失败输出，其历史事实必须保留。

`R03/implementation/worker.diff` 的第 8、44 行及 `R07/producer/duration-fix/successor/implementation.diff` 的第 5、6、311、312 行均是统一补丁上下文空行所需的单字节空格 `0x20`。两份 SHA 分别为 `d95dab2f9df08c0e5beba1e0fe46dc234c96bf2fd8c906f5bf7ffefb49127aaa`、`da97e74817f550c5b4bbdb911b5ff58a3f9813f998c016eab1af8a5dd5cdf2a7`；原归档哈希和独立评审冻结记录均支持，详见 JSON input_pins。不能修改这些原件以满足外层 whitespace 检查。

1. **只修 root checker。** 保留首次失败及其断言，不改写为成功。逐条解析诊断及 `+` 内容；仅允许 JSON `exact_whitelist` 中固定的 21 路径、SHA/bytes、行号、诊断类型。diff 的六行还须验证为补丁 hunk 中的 `0x20`。本冻结基线须精确覆盖全部 264 条；任何新增、未解析或不匹配项均失败。保留 raw exit 2，另记严格分类通过；禁止全局关闭 whitespace、按扩展名放行或清理原日志/diff。
2. **重核交付边界。** 原 377 路径、总 bytes、scope SHA 及独审 source/archive pins 保持不变。两份计划及 root 检查/交付元数据另行显式登记，保留元数据自身不递归计算哈希规则；核对 staged 精确路径集和每个 staged blob。新增计划/元数据须正常检查且零未分类诊断。首次失败与修复后的分类结果分别记录；有偏差即停。
3. **root 完成交付。** 仅在上述全部通过后按既有授权提交显式 staged 集、推送目标分支，并核对本地 commit SHA 与 remote branch SHA。一并说明原始 check exit 2 与冻结原件分类结果，不声称原始 check 返回 0。

本代理只生成这两份计划，不实施 checker、不修改源码/raw/log/diff/原 scope/rootdocs/Stage/Git，不运行 actual、新测试或外部网络。结论仅覆盖这份固定 staged whitespace 输出，不新增运行正确性结论。
