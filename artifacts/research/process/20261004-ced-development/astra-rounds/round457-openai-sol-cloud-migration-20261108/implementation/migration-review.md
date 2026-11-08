# R457 / R458 云端迁移独立针对性复核

复核结论：**限定范围内代码和软件交付可继续，无新增阻断项。** 本结论覆盖精确 `gpt-6.1-sol` 视觉云端迁移及 R458 测试替身修复，不构成真实运行放行或研究验收。

评审日期：2026-11-08。基线和评审时 HEAD 均为 `c96289351b3e60f8ac183c8f331fbce484ad7340`；本报告针对下表 SHA256 对应的未提交工作树。依据 R457 / R458 Astra 计划进行独立复核，保留原 R457 失败记录。

## 范围与执行边界

检查六个产品源码、角色配置、复现说明及新迁移测试，追踪有效参数 snapshot → wire → summary、两个入口的模型家族绑定、官方路由和密钥边界、legacy 兼容及声明范围。没有扩展重审旧物理全链。

评审仅阅读源码、差异、计划和既有验证记录并核对 SHA。未运行测试、probe、实际 API、引擎、渲染或硬件调用；未读取环境密钥或当前数据库；未派生 agent；未修改产品、index 或 HEAD。执行过只读 `git diff --check`，结果无空白错误，该检查不作为测试通过证据。仅保存本报告与配套 JSON。

## Strengths

- [model_resolver.py:24](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/model_resolver.py:24)：纯 helper 统一 Sol 的 `reasoning_effort` / `max_completion_tokens`，验证类型、范围和精确键集合；不可变 snapshot、实际请求及探针预期摘要共享映射，避免预算或参数语义分叉。
- [planner.py:241](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/planner.py:241)：发送前再次绑定冻结身份与官方 base/path 组合；Sol 拒绝重定向。密钥仍通过现有 secret store 和请求头使用，不进入 snapshot、摘要或提交文档。
- [role_models.py:185](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/role_models.py:185)、[probe_rgbd_roles.py:404](/home/ningyd/文档/ChatGPT/BIGsmall/scripts/probe_rgbd_roles.py:404)、[run_rgbd_pilot.py:687](/home/ningyd/文档/ChatGPT/BIGsmall/scripts/run_rgbd_pilot.py:687)：精确 Sol ID 与 Qwen 家族处理区分清楚；两个真实入口均传入配置家族，旧 Qwen profile 与 Sol 配置不匹配时在渲染和 HTTP 前拒绝。
- [probe_rgbd_roles.py:560](/home/ningyd/文档/ChatGPT/BIGsmall/scripts/probe_rgbd_roles.py:560)：wire observer 从实际序列化请求计算摘要与原始 body 摘要值，并记录实际请求配置；预期参数没有被当作实际请求证据。
- [service.py:477](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/model_control/service.py:477)：Sol profile 使用登记预算，环境入口的默认值和既有 frozen-directory 优先级明确；旧 Qwen/Ollama 分支保留。[复现说明](/home/ningyd/文档/ChatGPT/BIGsmall/docs/research/reproduction.md) 明确本地设置和真实研究尚未验证的边界。

## Critical

无。

## Important

无新增问题；没有尚未闭合的本轮阻断项。

## Minor

无。

## R458 已知失败处置

R457 首次 GREEN 的 7 PASS / 1 FAIL 是相机类被函数替换后，pilot 在导入时继承函数而触发 TypeError。该原始失败及 JUnit 保留，不重复列为新产品 finding。

[test_openai_sol_visual_migration.py:286](/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_openai_sol_visual_migration.py:286) 现使用可继承的 `ForbiddenCapture`，构造即失败；第 305–306 行还保护 pilot 已缓存的两个采集别名。真实 resolver、probe 和 pilot 入口调用及配置家族断言仍保留，修复没有削弱禁止渲染或 HTTP 的约束。R458 的六个产品源码 SHA 与该轮输入相同；变化限定为测试 fixture 和该文件 import 排序。

## 既有软件验证证据

以下结果均来自已保存日志，本评审没有重跑：

| 阶段 | 已保存结果 |
| --- | --- |
| R457 RED | 8 个预期缺策略断言失败 |
| R457 首次 GREEN | 7 PASS / 1 已知 fixture FAIL，原件保留 |
| R458 fixture-green | 8 PASS，pytest 1.23 秒 |
| R458 adjacent-green | 130 PASS，pytest 7.57 秒；1 项第三方 starlette/anyio 弃用警告 |
| R458 Ruff | All checks passed |
| R458 format | 7 files already formatted |
| R458 mypy | 6 源文件无问题；另有既有未使用配置段提示 |

读取了 R458 五阶段的 stdout 与 result.json，全部 `returncode=0`、`reaped=true`、`source_drift=[]`、`remaining_live=[]`。当前下表九文件 SHA 与 fixture-green 的 runtime-source-pins 一致。历史与新通过数不累计为新的独立覆盖数。

证据目录：[R457 validation](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round457-openai-sol-cloud-migration-20261108/validation)；[R458 validation](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round458-inheritable-capture-fixture-20261108/validation)。实施记录：[R457 step-report](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round457-openai-sol-cloud-migration-20261108/implementation/step-report.md)、[R458 step-report](/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round458-inheritable-capture-fixture-20261108/implementation/step-report.md)。

## Declined-to-judge

- 真实 OpenAI 账号及模型可用性、实际图像能力、延迟、token 用量和费用：本轮没有真实 API 调用。
- 用户当前凭据、环境密钥值、现数据库和运行 profile：按要求没有读取。
- 未变更的通用文本 planner 与旧物理完整执行链：不属于此次针对性复核。
- 正式研究验收、现场资源条件和实际运行授权：软件检查不能建立这些事实。

## Ready?

**代码和本轮软件交付：是。** R457 迁移要求在声明的视觉云端范围内实现；R458 关闭已知 fixture 失败，限定软件验证与静态检查均已有通过原件。

**真实运行放行或研究通过：否。** 记录中的真实 API、MuJoCo/渲染、物理、服务和硬件操作均为 0，正式研究仍为 `NOT_ACCEPTED`，native 状态仍为 `UNKNOWN`。后续真实运行须登记新源码来源并满足独立前置条件；旧 R439 冻结协议不因本评审而适用于新源码，R450 服务操作授权也未因迁移而获得。

## 精确评审源码 SHA256

| 路径 | SHA256 |
| --- | --- |
| [src/cloud_edge_robot_arm/vision/model_resolver.py](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/model_resolver.py) | `e75a94929529a4537a980e33fa4645285baee85aaec0b5597b426c347cd41e04` |
| [src/cloud_edge_robot_arm/vision/role_models.py](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/role_models.py) | `cfc28c29856be9cedcb0b8ca626d6e51e83cec8eaf2c0f637a03b71f757b81bf` |
| [src/cloud_edge_robot_arm/vision/planner.py](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/vision/planner.py) | `cc632036242004480e85ae6977cfa4e662ac512b71cd3303c38a0510c7c0b1c5` |
| [src/cloud_edge_robot_arm/model_control/service.py](/home/ningyd/文档/ChatGPT/BIGsmall/src/cloud_edge_robot_arm/model_control/service.py) | `7eeaacd932542feaaf77ad48b71cab5421edb13e827fd27a49879defad94da39` |
| [scripts/probe_rgbd_roles.py](/home/ningyd/文档/ChatGPT/BIGsmall/scripts/probe_rgbd_roles.py) | `36343558606df726e44301822b698e6c7213ad6f3bee1bfdba34ba72d29ad64a` |
| [scripts/run_rgbd_pilot.py](/home/ningyd/文档/ChatGPT/BIGsmall/scripts/run_rgbd_pilot.py) | `7d977bf5e51cd113ecff3fc9660eac2d9cee73d09825e918ba0acad039872ccf` |
| [configs/research/ced_roles.yaml](/home/ningyd/文档/ChatGPT/BIGsmall/configs/research/ced_roles.yaml) | `a8c21a58b28d7850e5d577027409e4e1db18be659219f33c2ed029fc06479e47` |
| [docs/research/reproduction.md](/home/ningyd/文档/ChatGPT/BIGsmall/docs/research/reproduction.md) | `6bf53f1a0f005a44d20a56d9a20f1c71ef824187949c9ba3b8550e36abbb5bb6` |
| [tests/test_openai_sol_visual_migration.py](/home/ningyd/文档/ChatGPT/BIGsmall/tests/test_openai_sol_visual_migration.py) | `3afd8434397f5b0b1147045231be11a073d012f782eb96f9c8e22f3c545c9a80` |

本报告只声明上述源码状态和限定软件证据；提交或推送后的 commit SHA 仍由交付流程单独核对。
