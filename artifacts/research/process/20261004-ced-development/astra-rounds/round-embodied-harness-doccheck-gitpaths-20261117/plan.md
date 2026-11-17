# Astra：文档范围检查的Git路径读取修正

实际模型：`gpt-6-astra`；日期：2026-11-17；状态：PLANNED_NOT_IMPLEMENTED。
轮次：`round-embodied-harness-doccheck-gitpaths-20261117`。

## 原始证据与根因

上一轮ROOT单行修正后，完整文档检查35项中34项通过，唯一失败为`tracked_change_scope`。原轮`implementation/validation.json`保存完整35项结果，上一轮`implementation/validation-rerun.txt`保存完整输出/退出码1（chunk 691d9d）。两者及当前脚本、三份正文、上一轮计划和清单共9输入已逐字冻结，SHA256见本轮`input-manifest.json`；上一轮正在编写的repair-report不作为输入。

根因：`git diff --name-only`默认对中文路径作C风格引用，splitlines得到带引号/转义字节的字符串，与原Unicode白名单不等价。实际Astra已只读核对`git diff --name-only -z`输出，中文报告路径正确且无引用。属于路径传输解码错误，不是白名单过窄或正文越界。

## 限定修改与实施

1. 实施前重算9输入及冻结副本SHA；全部一致才继续。
2. 仅将原轮`implementation/validate_docs.py`中`changed = ...`一行替换为plan.json精确给出的after：为Git添加`-z`，按NUL分割并去除结束分隔造成的空项。继续使用现有subprocess/text=True，无新依赖，不设置全局Git配置。
3. 保留ROOT=parents[7]、TARGETS、initial白名单、`tracked_change_scope`布尔断言及其余检查完全不变；不改三份正文、原计划、旧日志和快照。
4. 一次完整重跑现有python3文档脚本，保存完整stdout/stderr、命令、退出码到本轮`implementation/validation-rerun.txt`。允许脚本重新生成原轮`implementation/validation.json`，因为旧FAIL结果已逐字冻结；应另将旧FAIL结果复制为本轮`implementation/prior-validation-failure.json`作为轻量远端失败证据并验证SHA相同。
5. 检查只有该changed行变更、其余输入除预期重新生成的validation.json外SHA保持；35项必须全部通过且退出0。可用只读Git及git diff --check。写本轮`implementation/repair-report.md`说明单行修复、前后SHA、验证与边界。原轮步骤报告/阶段总结引用本追加轮次。

## 交付补充与验收边界

在两轮既定精确交付清单上追加本轮`plan.md`、`plan.json`、`input-manifest.json`、`implementation/prior-validation-failure.json`、`implementation/validation-rerun.txt`、`implementation/repair-report.md`。本轮inputs/original仅本地保留不重复上传，原日志不删除；根代理更新原轮delivery-manifest.json精确记录。原授权Git提交/推送及三SHA核对继续适用，无关改动不带入。

文档检查通过仅证明限定文档交付及检查工具正常；实际API、物理仿真、硬件、产品测试、正式研究均未执行/未新增验收。未来真实运行仍须满足适用Astra计划、当前来源/角色/资格、安全、资源与预算条件，此轮不授权运行。

若出现新异常、新断言失败、输入漂移或需改白名单/正文，保存完整失败并停止相关修复，转实际Astra下一轮；不得继续放宽检查。独立人工审阅可继续。
