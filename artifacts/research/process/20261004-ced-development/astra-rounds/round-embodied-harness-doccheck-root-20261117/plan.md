# Astra：文档检查脚本仓库根目录修正

- 轮次：`round-embodied-harness-doccheck-root-20261117`；日期：2026-11-17。
- 实际规划模型：`gpt-6-astra`。状态：PLANNED_NOT_IMPLEMENTED。
- 本轮只修复文档验证工具，不修改正文、产品实现或验收断言。

## 原始失败、根因与输入

原轮`implementation/validation-attempt-1.txt`保留首次执行的命令、退出码1、chunk b30361及完整FileNotFoundError。脚本以`Path(__file__).resolve().parents[6]`计算ROOT，实际得到仓库的`artifacts`目录，因此读取`artifacts/AGENTS.md`失败；未生成validation.json。不是文档内容失败。

本实际Astra已用只读`git rev-parse --show-toplevel`与真实脚本绝对路径核对：parents[6]为仓库/artifacts，parents[7]才是仓库根。不存在待安装依赖或产品根因。

八个直接输入（失败脚本、原始失败日志、原轮plan.md/plan.json/input-manifest.json及三份已修改正文）已逐字冻结；路径、SHA256及根目录核对结果见`input-manifest.json`。原件快照仅本地保存，不覆盖或删除。

## 限定修正与步骤

1. 实施前重算八输入SHA，与本轮输入清单一致才继续。原轮计划和输入清单仍保持冻结字节，不为追加轮次修改原计划。
2. 仅修改原轮`implementation/validate_docs.py`一行：`ROOT = Path(__file__).resolve().parents[6]`替换为`ROOT = Path(__file__).resolve().parents[7]`。本轮按固定已核对路径修复；不引入自动上溯、备选分支或新框架。
3. 不改变ROUND、TARGETS、任何验收断言、链接范围、数值阈值、正文或历史文件。三份正文在本轮前后必须SHA一致。
4. 使用python3重新运行该文档检查，保留完整命令/退出码及输出到本轮`implementation/validation-rerun.txt`；检查通过产生原轮`implementation/validation.json`。这是本轮预期修复验证，不运行产品测试、API、模拟器或硬件。
5. 核验脚本diff只有上述ROOT行；八输入除脚本外均未变化，失败日志及快照字节不变。可运行只读Git、`git diff --check`及原轮计划授权的文档检查。
6. 写本轮`implementation/repair-report.md`：原始失败、单行修复、前后脚本SHA、复验结果与边界。原轮步骤报告/阶段总结应链接本追加轮次，不能删除首次失败。

## 精确交付补充

在原轮既定正文和轻量过程文件清单基础上，追加以下路径：

- 原轮`implementation/validation-attempt-1.txt`。
- 本轮`plan.md`、`plan.json`、`input-manifest.json`。
- 本轮`implementation/validation-rerun.txt`、`implementation/repair-report.md`。

本轮`inputs/original/`本地保留，不提交重复正文。原轮delivery-manifest.json可加入以上明确文件及其SHA；自身SHA不递归写入。ROOT按精确文件清单完成原授权提交/推送，并核对本地、上游、远端SHA；不带入无关改动、不强推。

## 验收、实际运行条件与停止规则

本轮通过条件为根目录正确、单行修改限定、正文和原始失败不变、文档脚本退出0且其全部检查通过。不得将工具恢复写成Harness已经实现、物理任务成功或正式研究通过。实际API/仿真/硬件运行仍须另行满足原适用计划、来源、资格、安全和预算要求，本轮无此授权。

若复验出现任何新断言失败、额外异常、输入漂移或需改正文/断言，保留完整原始输出，停止相关修复并交实际Astra制定下一轮计划；不能在此轮顺手改检查。原轮允许的独立人工审阅与文档交付准备可继续。
