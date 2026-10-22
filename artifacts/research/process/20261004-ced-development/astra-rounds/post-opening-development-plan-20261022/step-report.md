# 2026-10-22 后续开发计划步骤报告

状态：规划文档核对完成；研发仍未验收。

## 交付

- ROOT 主计划：`docs/superpowers/plans/2026-10-22-post-opening-development-plan.md`，9 项任务及至 2027 年 5 月的条件排期。
- 本目录 `plan.md/json`：实际 gpt-6-astra 的 11 个工作包、失败证据、输入 SHA256、前置门与验收边界。
- `scope-clarification.md/json`：ROOT 新文档 Git 交付与旧运行额度、原诊断 SQLite 范围的区分。

## 实际工作与核对

只读取已有状态和修订开题材料，并新建规划文档。当前事实区分 R289 行为失败与 R299 源码准备通过；P6 内部 T2 与历史总任务 T2 分开。明确消融首次登记在 INITIAL 前、精确实现 METHOD 冻结，以及 exploration 不等待自身 selection。

文档核对实际 exit 0（tool chunk `d42d48`）：43 份输入 SHA256 全匹配，44 处源码引用存在，7 个本地链接有效，10 个当时已有 JSON 可解析，依赖无环。新主稿修改可由精确 old/new 映射重建；产品测试、旧 gate、模型、物理运行均为 0。完整结果见 `root-document-checks.json`。

## 保留的文档失败

一次新稿 apply_patch 因末尾 hunk 指向前一 hunk 之前的段落而未匹配；主稿前后 SHA 相同。原工具错误保存在 `root-document-patch-failure.json`；不声称已保存完整原 patch 字节。实际 Astra 的限定恢复计划位于 `document-edit-recovery/`，ROOT 按原文顺序预核全部替换后单次写入，保存完整 before、映射、diff 与 after SHA。未改产品或历史输入。

## 后续

下一项为 Task 1 / Astra WP0 的实施适用性、HEAD、真实角色及额度复核。计划本身不释放 R298/R296，不重置旧 spent 次数。Git 交付按用户既有授权与 AGENTS 执行，实际提交后 SHA 核对回执单独保留。
