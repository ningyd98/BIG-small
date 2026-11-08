# R459 — 冻结证据交付的检查范围

实际 gpt-6-astra，2026-11-08。本轮是交付检查范围判定，不是产品修复。17份当前输入/完整副本/SHA在intake/input-pins.json；现有138软件测试、五项验证全通过及 APPROVED_FOR_SCOPED_SOFTWARE_DELIVERY 审查原件已核对，无需重跑。

## 原问题与授权只读复现

ROOT报告此前 `git diff --cached --check` 子命令rc2，外层assert脚本rc1，原工具输出未另存。本轮按明确授权仅复现同一Git命令一次，stdout/stderr完整原字节与rc保存在intake/full-staged-check.*。不能把本轮复现输出冒充之前那次运行的原stdout。

复现rc2，恰3个证据文件、50条结构性空白，逐条原文件行内容分类见intake/whitespace-classification.json：

- R457 implementation/product-diff.patch：26个单空格patch空上下文行，原patch语法。
- R457 intake/static-incompatibility.txt：16个带行号前缀的空源代码行。
- R458 intake/static-evidence.txt：8个带行号前缀的空源代码行。

三个文件当前字节与暂存blob相同，各SHA在复现result及input-pins。无产品源码、测试、配置或说明告警。原manifest有189个entries，加manifest自身共190个暂存路径；本轮已逐个核验path/bytes/SHA，无遗漏、额外项或差异，结果见intake/staged-manifest-check.json。

复现前后index tree均为 `ff0589c1695bb74d6ee19947a042914e0014de60`。该SHA通过只读git ls-files --stage -z及标准Git tree对象编码计算，不使用会写Git对象的write-tree；方法和索引条目hash保存在result。索引/HEAD未修改。

## 判定

根因是把冻结patch/带行号证据当作产品文本做全范围格式检查。保留rc2为真实交付检查记录；不标成全范围通过。不trim、重写、重新格式化这些证据，不修改原实验字节，不改gitattributes或全局whitespace规则。新R459中复制的原证据/原stdout仍可含同样结构性空白，亦应按证据原样保留，而非再次要求整个归档变绿。

## ROOT的一次限定检查与交付

1. 复核本轮17pins和原190项暂存index未变。若tree仍为上述值，可以直接复用本轮190项完整核验报告，避免重复扫描。
2. 仅一次执行以下产品暂存检查，保存原stdout/stderr/rc（≤30s），必须rc0：

```sh
git diff --cached --check -- configs/research/ced_roles.yaml docs/research/reproduction.md scripts/probe_rgbd_roles.py scripts/run_rgbd_pilot.py src/cloud_edge_robot_arm/model_control/service.py src/cloud_edge_robot_arm/vision/model_resolver.py src/cloud_edge_robot_arm/vision/planner.py src/cloud_edge_robot_arm/vision/role_models.py tests/test_openai_sol_visual_migration.py
```

没有新产品修改授权。若这九路径出现告警、原件SHA变化或新增不属于三类证据的现有告警，停止并交新Astra，不自动修复或扩大豁免。
3. 保存R459实施核对/步骤报告，明确全范围rc2与产品范围rc0的不同结论。原R457 delivery-manifest.json保持原字节。另建R459 implementation/delivery-manifest-final.json：包含原190个文件（其中旧manifest也作为一项）及明确选定的R459计划/复现/原件副本/核对报告；每项path/bytes/SHA。为避免自引用，其自身不进入自身entries，声明最终暂存集合=entries+最终manifest自身；另校核该manifest工作字节等于staged blob。报告先保存、最终manifest最后生成，此后不再悄悄追加交付文件。
4. 只对最终清单枚举的新R459路径显式git add；不使用git add -A，不进入或暂存两个历史脏gitlink。原190blob应全部不变。核验最终staged路径集合、每项staged blob bytes/SHA及九产品与既有review的源hash一致，最终manifest生成后的核验结果通过用户可见工具输出报告，不再改动已列入manifest的报告文件，避免自引用循环。
5. ROOT按用户既有授权正常commit并push研发分支research/20261004-continuation。不得force或修改远端历史；沿现remote/upstream配置。推送后核对本地HEAD、upstream tracking和远端refs/heads/research/20261004-continuation三个SHA相同，向用户报告。若发生新的Git冲突/拒绝，保留原因停止，不强推。

本规划者只进行了授权只读复现/清单核验和本轮证据写入，没有stage、commit或push。实际提交由ROOT执行。

## 验收边界

允许原样交付结构性空白证据的条件：已分类全范围输出真实保留；九产品路径检查0；原190字节不变；新最终清单覆盖准确；现验证/审查源码hash无漂移；推送三SHA一致。无需重跑138测试、ruff/mypy/format或审查。真实API、physics、render、服务、硬件均0，正式研究NOT_ACCEPTED；旧研究source-generation要求不变。
