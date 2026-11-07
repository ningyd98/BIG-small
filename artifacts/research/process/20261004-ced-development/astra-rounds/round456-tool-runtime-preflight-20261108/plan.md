# R456 — 工具运行时前置恢复

实际 gpt-6-astra，2026-11-08。仅规划与静态文件核对；未启动测试、physics/render/model或服务操作。收到的原失败报告逐字段保存在 `intake/received-root-report.json`：ROOT 使用 `python - <<'PY'` 做R454 pins校验与before归档，shell返回127、`python: command not found`。完整heredoc正文和原运行输出文件未提供，不能把收到的报告称为原stdout文件。报告指出解释器未启动、脚本没有文件写入/测试启动；同次编排后续独立apply_patch已添加获批R454测试。

## 根因与当前证据

前置脚本选择了不存在的未限定解释器命令。已知项目运行时为 `/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python`，只读检查确认它可执行且解析为 `/usr/bin/python3.12`；没有运行版本探针或安装任何工具。此为工具前置问题，不是R454测试失败，不消耗其唯一RED额度。

静态重新读取R454的24项冻结pins：**23项一致，唯一差异是获批测试文件**。该差异仅添加 dataclasses.replace 导入和 `test_reset_conversion_failure_vetoes_first_step_and_keeps_original`，原三节点未变；recorder产品未变。逐项当前SHA、该差异原文与本轮8份输入副本分别保存于 `intake/read-only-observation.json`、`approved-test-delta.diff`、`input-pins.json`。总数是24，故“其他不变项”为23，不虚报24项全相同。

## 唯一前置恢复

本轮不允许产品/测试编辑。ROOT保存一个仅使用标准库且不导入项目产品的前置归档脚本到R456 implementation，使用精确运行时命令：

```sh
/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python artifacts/research/process/20261004-ced-development/astra-rounds/round456-tool-runtime-preflight-20261108/implementation/check_inputs.py
```

单次≤30s，不运行pytest、不做版本probe。脚本应先完整读取并校验，全部通过后再写证据：

1. 重新校验R456八份输入与完整副本SHA，以及R454原24 pins。23项必须仍匹配；唯一test例外必须与本轮冻结当前test SHA完全一致，其diff为获批新节点/必要导入。不得将任意测试差异列为allowlist豁免。
2. 原test before来源使用R454 `intake/originals/tests/test_native_observer_failures.py`，先校验它与R454原pin的SHA和字节数一致，再以独占创建方式复制到R454 `implementation/before/tests/test_native_observer_failures.py`。该路径若已有正确同SHA证据则只核验并记录；若不同则停止，不覆盖。**不覆盖工作树测试，不从当前新增测试反推旧内容。** recorder原before同理可直接从当前已匹配原pin字节保存到对应before路径；已有同SHA则复用。只归档R454两批准修改路径，不复制整仓。
3. 保存R456 preflight-result与R454 applicability：每项冻结SHA/当前SHA、23一致+1批准差异、运行时、命令、before来源和SHA，注明test before为“在前置失败后，从已冻结的修改前原件恢复的证据副本”，不能声称在本次apply_patch之前现场捕获。保留原失败report与原plans/addendum，禁止覆盖原冻结输入。
4. 确认脚本正常退出且before/applicability原件完整后才继续R454原唯一conversion-red；命令/节点/预期失败/额度仍由R454及其COMPLETE附录控制。R456本身没有新测试阶段，也不重跑旧测试。R455仍按独立计划在R454完成后启动其测试阶段。

任何新漂移、脚本失败或before冲突停止依赖启动并交实际Astra，不在本轮增加修复或重试。保存本轮step-report，区分收到的shell报告与实际前置恢复结果。

## 边界

本轮验收仅是正确运行时的来源复核与before证据可追溯恢复；无产品修复、0测试/实际调用。R454/R455所有测试预算、原R439首组实际额度、R450服务授权均不变。不得安装/修改PATH、系统解释器、服务或将未运行记为通过。
