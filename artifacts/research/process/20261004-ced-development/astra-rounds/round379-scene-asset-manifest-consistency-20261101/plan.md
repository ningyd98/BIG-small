# R379 Scene Asset Manifest Consistency Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans；用户已授权登记一致性修复，无需追加设计审批。

**Goal:** 将当前已提交参考 MJCF 正确登记为 phase9.reference.v3，并证明其真实 load/reset/step 与资产校验。

**Architecture:** 保存旧 manifest/历史模型来源快照，只同步清单 SHA/version，不改模型。保持旧数据各自版本及 marker XML 独立登记。

**Tech Stack:** 现有 Python/pytest/PyYAML/MuJoCo；CPU 仿真，不涉及真实硬件/云端。

**Spec:** 用户恢复来源/资产一致性的授权、根 AGENTS、同目录 plan.json 的历史对象 pins、输入 SHA、命令与交付额度。

## 原失败与权威来源

R374 `test_phase9_asset_manifest_records_hash_and_license` 在真实 AssetRegistry.require 中拒绝：登记 `6a793870…`，当前 `66a0e270…`。原始 events/stdout/JUnit/结果及审计均 pin，复用为 RED，不再原样重跑。

已只读核对 Git 对象和精确 bytes：

- 2026-10-03 `a33b32af…`：scene4924字节，SHA `6a7938709366801ed6e36c7c504da64a48b7b16bbc02adda2a31417c7ad5b1d1`；新增相机/光源，manifest升为 phase9.reference.v2。
- 2026-10-04 `d2afb0d9…`：scene4978字节，SHA `182fb2bc068ba44de394622f819ae444eb7fbe51df5c5311591a8abb97bf6a08`；默认控制增益12/3→20/5、指部偏移45→40mm、指摩擦1.5、指控制增益25/4→250/10，清单未更新。
- 2026-10-05 `d3472a56…`：指部偏移40→9mm，scene4980字节，SHA `66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2`，与当前完全相同；清单仍旧版。

权威源是已提交的小型 BIG-small Phase9 参考 MJCF；项目文档明确不是官方 Franka 模型。审查到的生成脚本生成数据集/使用该模型，未找到另一个权威“当前scene生成器”；marker builder只派生独立visual资产，不能拿它重生成基础scene。版本是 AssetRegistry 的登记标签，不是物理验收版本。

## 最小变更

只将 `assets/manifest.yaml` 对应条目 SHA 改为当前66a0…、version 改为 **phase9.reference.v3**，schema/id/path/source/license/SI不变。`docs/phase9_assets.md` 加简短历史/来源及旧数据不可重标说明。

`tests/test_phase9_asset_registry.py` 保留原正例，补当前版本/精确场景路径断言；增加两个真实注册表反例：临时布局中旧6a hash搭配当前模型拒绝、当前hash搭配被改临时模型字节拒绝。仅改tmp_path副本，不 mock require/hash、不改仓库模型。原 load/reset/step 测试不变。

修改前在本轮 inputs 保存旧 manifest 原485字节（SHA `4a07b0f7d46795684bc449b2e8942e21ed3320c0a2680093ab6f8084ab0f8e66`）及明确源路径/对象清单，读取历史 Git 对象保存6a与182场景快照。它们是归档，不是当前运行资产；归档 manifest 的旧相对路径不能冒充活动清单。

**不改 scene.xml、任何 marker XML、相机/几何/控制器/物理参数，不联动刷新 marker hash，不升级旧数据或形式研究状态。**

## 实施与验证

- [ ] 等 R376/R377/R378 对应整批终态、清理和源写入交接；不并行测试。复核 27 项当前直接 pins及历史对象，保存旧原件。前序获授权的测试/config改动不列本轮依赖，不因 HEAD正常推进误报；记录实际HEAD。
- [ ] 应用两字段清单更新、窄文档说明及真实拒绝回归；确认模型/marker原字节不变。
- [ ] 一次 registry 模块 GREEN，60秒；随后一次 `tests/test_phase9_mujoco_load.py tests/test_phase9_mujoco_physics_step.py`，120秒。精确argv/env在JSON，使用现有venv、独立basetemp/JUnit/cache，不安装、不假后端。
- [ ] 原后端必须真实加载当前路径、S01 reset、七关节、reset后simtime0；80steps推进时间/状态、160steps改变FK TCP。保存完整stdout/stderr/JUnit/退出/耗时/清理及实际scene路径/hash/version，不只记录“测试绿”。
- [ ] 原scene及三个marker XML前后SHA一致；原manifest归档不变。新失败冻结相关修复并交下一轮Astra，独立阶段可完成诊断，禁止无界重试或改模型追旧hash。
- [ ] 通过后审查精确diff和显式stage列表，仅交付已验证manifest/doc/test及精选来源证据，不纳入性能候选、未跟踪temporal测试、嵌套工作区或其他用户文件。

测试最大60+120+两次15秒清理=**210秒**，本轮测试/报告墙钟**600秒**，每阶段一次，零自动重试；TERM宽限5秒并回收所属组。实际权限/依赖不可用记录 BLOCKED_ENV，不当产品失败，不更改环境或安装补救。

## 有限交付

新验证交付获得单独额度：**一次普通非force push（60秒）＋一次精确远端分支 ls-remote核验（60秒）**，比较本地HEAD、上游ref、远端SHA并留回执。不先作额外远端探测，不重置旧R373/R372传输账。TLS失败保留本地已验证commit与原失败，停止网络重试；不改Git配置、代理、TLS、安装软件或force。push成功但verify失败只能报告已推送但远端核验未确认。后续传输修复另轮规划。

## 验收边界

原asset registry正例和两个拒绝反例通过，真实load/reset/step断言完成且无skip/error/timeout；清单v3与当前66a0…严格匹配，模型/marker无字节变化，旧快照和旧数据身份保留。软件仿真登记与CI通过不等于抓取任务成功、真实硬件、官方模型、重采样、标定或正式研究验收。

本次实际Astra只读文件与Git log/show历史并写计划，未测试、产品导入、发信号、联网或修改Git。
