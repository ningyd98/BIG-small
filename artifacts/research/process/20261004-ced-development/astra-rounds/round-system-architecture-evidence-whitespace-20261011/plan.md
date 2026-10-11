# Astra 本轮计划：归档 diff 的 whitespace 检查与交付续接

- 日期：2026-10-11；规划模型：gpt-6-astra（按用户要求委派）。
- 状态：计划已生成；本轮仅规划和只读检查，尚未实施、commit 或 push。
- 目标：保留已经完成的系统架构图、4 页 Word 及历史失败证据的全部字节，安全续接已经暂存的 25 文件交付。

## 问题与原始证据

冻结交付脚本执行到 `git diff --cached --check` 时退出 2。`raw-git-check.json` 完整保存原始响应：唯一报告为旧轮 `implementation.diff:10: trailing whitespace.`，后接显示新增文件行的 `+` 与一个空格。其真实第 10 行为 `b' \n'`：这是 unified diff 的空白 context 行，其一个空格是格式标记。

根因是把归档的 unified diff 当作普通新增源码逐行进行 whitespace 检查。去掉该空格会改变历史证据，并破坏标准 diff context 表达。另一个续接约束是冻结脚本只适用于初始 clean worktree；当前 25 文件已复制和暂存，不能原样重跑它的 clean/target-not-exists 断言或复制阶段。

## 输入及 SHA256

输入清单 `inputs.json` 的原有三条记录必须复核。完整 25 文件清单及各自 SHA 位于 `/tmp/bigsmall-system-architecture-20261011/delivery-manifest.json`；实施时将该清单原字节冻结归档至本轮以便持久审计，不重建或覆盖原清单。

| 输入 | SHA256 |
| --- | --- |
| `deliver_git.frozen.py`，与原 `/tmp/.../deliver_git.py` 相同 | `ff17770c0530c7ab6762f77d4785a5e7c9366f2d349b3c20253a8a4ff420772b` |
| `/tmp/bigsmall-system-architecture-20261011/delivery-manifest.json` | `d300803c240ae554cc4df6a4d0c7ac411c7ba7a6c4fd24c234e3479437e5d56f` |
| 旧轮 `implementation.diff` | `4124e3e01c47ddb720b3e2698b18b80673d825477326dc9c6c6cdc80989cebc1` |
| 旧轮 `build_diagram.frozen.mjs` | `c533081c0a993da069f2f91183b3553fa8396ad227e16536af7172819e2b6611` |
| 成果 `build_diagram.mjs` | `6ea917c1b3cd373cdefb88ae480c3cc0c4293159ee272cc77429c07a9709c1d8` |
| 本轮 `raw-git-check.json` | `239f3b585ba850ae8d0a1f286072c91c6e17b6cf758ca497c1b1c2c2283f07d6` |

旧轮路径前缀为 `artifacts/research/process/20261004-ced-development/astra-rounds/round-system-architecture-sharp-entry-20261011/`；成果脚本路径前缀为 `artifacts/research/process/20261004-ced-development/system-architecture-word-20261011/`。

## 已完成的只读核查

真实 delivery worktree 为 `/home/ningyd/.codex/worktrees/t12-p1-delivery/BIGsmall`，branch 为 `codex/research-20261007-p1-delivery`，HEAD 为 `0bb613a6e927ae817e70abfc8b9ecaeb8f88d1c1`。状态恰有 25 个 staged additions，没有额外路径。逐一读取 `git show :<path>`，index、delivery worktree、主工作区来源的 SHA 均与原 manifest 相同。

使用冻结与实施脚本的 `splitlines(keepends=True)`，以 `difflib.unified_diff(..., fromfile='frozen', tofile='implemented')` 重建，结果与归档 diff 字节完全相同；第 10 行精确为 `b' \n'`。其余 24 个路径逐一执行 `git diff --cached --check -- <path>` 均退出 0。实施前必须重新执行上述核查并持久保存结果。

## 限定实施步骤

1. 冻结原 manifest 到本轮，新增专用续接脚本和验证报告，不改冻结脚本、原始失败、旧轮 diff、原 25 文件或现有阶段总结。新建本轮步骤报告及阶段补充总结即可。
2. 在任何写入前复核上述输入 SHA、branch、HEAD、index 的 25 路径及字节、delivery worktree 与 index 一致且无额外 tracked/untracked 路径。使用 `-z` 处理中文路径。检查不符时停止，不执行 reset、清理或批量 add。
3. 记录全量 cached check 的预期退出 2，确认诊断仍只有该精确路径第 10 行；这是已知失败的复核，不是修复后的全局通过声明。独立重建 diff 并核对其完整 SHA 和第 10 行字节。仅在全部相等时，对这一份精确路径设局部验证例外。
4. 对其余原 24 路径及本轮所有拟交付文本逐一执行 cached whitespace 检查，全部必须退出 0。不设置全局 whitespace 忽略、不改 `.gitattributes`、不通配排除所有 `.diff`。
5. 为本轮新增文件建立显式增量清单及 SHA。仅复制这些尚不存在的新增证据/脚本/计划/报告到 delivery worktree；保留已 staged 的原 25 文件，不重复复制。使用明确路径 add，确认最终 index 恰等于原 25 路径与增量清单并集，逐一核对 SHA；无混入主工作区其他脏文件。
6. 完成步骤报告，区分文档视觉验证（已完成且字节未变）、交付流程验证（本轮）、真实系统运行/研究验收（本轮未做）。提交前用 index 字节再次核验，普通 `git commit` 提交已精确验证的 index；如采用 `--only`，须另证 worktree 与 index 完全相同。
7. 推送现有分支，核对本地 HEAD、上游和 `git ls-remote origin refs/heads/codex/research-20261007-p1-delivery` 实时 SHA 三者相等，并确认 delivery worktree clean。推送结果写到外部 `/tmp` 验证文件及主工作区本轮后验报告，避免在已提交工作树内制造未提交追记或自指 commit SHA；不得声称后验报告已包含在前一提交。若要交付后验报告，另行明确文件提交并核对最终 SHA。

## 运行前置条件与停止边界

只使用 bundled Python `/home/ningyd/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`。只读检查无需更改外部工作树；复制、stage、commit、push 由主代理以适用的 `require_escalated` 自动审批执行。Git 身份、origin、上游和远端权限必须可用；push 前不得改远端配置或强推。如 HEAD/index 漂移、诊断变化、新 whitespace 失败、权限失败或 push 冲突，保留原始结果，暂停相关修复并交由下一轮 Astra，不扩大本计划。

验收必须满足：原 25 文件字节不变；唯一已证明是格式标记的精确 diff 被局部单独验证；其余文件 whitespace 检查通过；最终 index/commit 清单和 SHA 完全可审计；推送及三方 SHA 一致有真实证据。不重新渲染图/Word，不以开发检查替代真实运行、科研验收或完整远端复现包。
