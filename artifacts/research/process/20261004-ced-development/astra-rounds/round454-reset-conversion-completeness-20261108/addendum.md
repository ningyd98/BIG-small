# R454 附录：原 RawInterval 完成标签更正

实际 gpt-6-astra，2026-11-08；实施前计划更正，未改产品、未运行测试/physics/render。

已核对原冻结副本及当前 `vision/raw_recorder_v3.py`，两者 SHA256 均为 `4eabd3bf9cdf15b3942c4a740781a95c22ea684f410853c853d0336952d7a303`。`_close_interval` 原文为 `disposition="ABORTED" if error else "COMPLETE"`，正常原采集区间因此是 **COMPLETE 且 error=None**；转换异常仍改为 ABORTED 并保留原 ValueError。补充逐行证据保存于 `intake/interval-disposition-evidence.txt`。

本附录更正原 plan.md 步骤5及 plan.md/plan.json 所有涉及 RawInterval 成功状态的 RETURNED：实施时必须使用 **ACQUISITION / COMPLETE / error=None**。RETURNED 不能用于该区间校验；action disposition 不在本修复范围内，不改其语义。原计划文件及冻结输入不覆盖。

除此之外全部不变：两个允许路径；真实 RESET/原 converter 短 RGB 的唯一 RED 节点；该测试文件四节点 GREEN；五个阶段的命令、次数、超时和静态范围；原始 ABORTED/null 帧保留；已返回 pass exact=2；先于 guard/sampler/physics 的 veto；原实际额度和 R450 授权边界。无需新增测试节点或重新执行 R453 final。

ROOT 已报告 R453 final-focused 为50 PASS且已回收、保存报告；这是收到的前轮状态，本规划未重跑。实施者继续先复核本附录及原计划 pins，再执行原 R454 有界步骤。
