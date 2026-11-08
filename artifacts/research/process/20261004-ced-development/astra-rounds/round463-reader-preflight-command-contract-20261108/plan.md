# R463 只读预检命令契约修正 Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans，由 ROOT 沿当前研发分支执行下面的命令选择修正并继续已授权 R461 P0。本 Astra agent 只制定计划，不实施、不运行测试。

**Goal:** 将解释器及文件路径选择恢复为 R461 已冻结契约，不增加软件修改或验证额度。

**Architecture:** Python 固定使用 `.venv/bin/python`；runner 依据 R461 input-pins 读取并校验后复制；未列入 pins 的源码先通过 `rg --files` 发现真实路径。R461 的产品修复、监督器和验证门槛仍由原计划定义。

**Tech Stack:** 已有虚拟环境、Python 标准库只读 JSON/SHA256、Git 只读检查、rg；零新增依赖。

**Spec:** `AGENTS.md`、R461 `plan.md/plan.json`、R463 intake；ROOT 转交的用户明确“按 R461 启动开发验证”执行授权。

实际规划模型 **gpt-6-astra**，当前 HEAD `fdbf481d3c843c1583d97970f8229b479363c334`，分支 `research/20261004-continuation`。

## 问题、原始证据与根因

`intake/original-failures.json` 保留两次错误：环境中的裸 `python` 不存在（rc127）；猜测 `round458-openai-official-routing-20261108/implementation/run_stage.py` 不存在（rc2）。该记录的首条 command 是带 `[read-only inspection]` 的描述，不将其伪称为完整 stdin 脚本存档。

`intake/additional-same-root-failures.json` 保留新增两次 `sed` rc2：猜测 `tests/test_rgbd_grasp_offsets.py` 与 `src/cloud_edge_robot_arm/vision/grasp_offsets.py`。实际 `rg --files` 返回 `tests/test_rgbd_top_grasp.py` 与 `src/cloud_edge_robot_arm/vision/top_grasp.py`。

这些错误同属只读命令构造未采用明确契约/真实路径；没有执行产品代码、pytest、模型、engine 或 renderer。它们不证明 reader 新缺陷，不是 R461 预期 RED，也没有消耗任何 R461 测试 stage。无需重新触发这些错误。

## 输入与适用性

重新计算 R461 **31/31** 输入 hash 均匹配；`src/tests/scripts/configs/assets` 的已跟踪未暂存与已暂存 diff 均为空。完整工作树含历史未跟踪证据及嵌套工作区状态，不能说全树干净，不能清理它们。

**结论：R461 P0 可继续。** 用户的当前明确执行授权满足 R461 所述未来 P0 授权条件；R461 成文时“本轮仅规划”保留为原始历史事实，不应改写，也不应在已有授权下重新请求确认。当前无阻塞。此结论仅适用于 CPU 开发验证，不放行 P1/P2/P3 实际运行或正式研究验收。

本轮直接输入与 SHA256 如下；31 项原输入完整预期/实测 hash 另嵌入 `plan.json.r461_original_inputs`，原 intake 不覆盖。

| 输入文件 | SHA256 |
|---|---|
| `AGENTS.md` | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round461-sol-evidence-reader-and-mainline-plan-20261108/plan.md` | `65e5f22605e2511f61a056271c194765bee213299e3f3e4f0d64f1bbbb5da261` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round461-sol-evidence-reader-and-mainline-plan-20261108/plan.json` | `35b79fbfe3d302941b3fa73ca90a0b592dff6a3fd2a997552cb590411fa23542` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round461-sol-evidence-reader-and-mainline-plan-20261108/intake/input-pins.json` | `c3f3862830198f76664821e4cfa54821eeaa6bc99d24addef5e58d94cf418533` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round458-inheritable-capture-fixture-20261108/implementation/run_stage.py` | `ab3f8edd8392dda68cbd76c5189ffc19aece0e8b94c3cbf74cc8752127498825` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round463-reader-preflight-command-contract-20261108/intake/original-failures.json` | `10d85108e142db50a9f7378976b7b0c3236fde1e0f66358bb8b4315babd6f570` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round463-reader-preflight-command-contract-20261108/intake/input-pins.json` | `e2abb7d59e90fd047e5907cfc9cfd1e98526cba73d7c1c3ddea9c8697f19765c` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round463-reader-preflight-command-contract-20261108/intake/r461-applicability.json` | `5c61a523d4027693b49c18c5df3227a9b500121ad0260000419d620409cdced1` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round463-reader-preflight-command-contract-20261108/intake/additional-same-root-failures.json` | `30e0e63a48ad25b51bb32a1daee48e3309f6e464b736fa6546c3b7409cbcd371` |
| `tests/test_rgbd_top_grasp.py` | `900eac15293ed8cd2ac411243f139ff35d894cf9fada8c22e367a355f56140c6` |
| `src/cloud_edge_robot_arm/vision/top_grasp.py` | `4726f87207d271dfad133852677a50abdc9b267b7a8688742cc87c6869dbc0ae` |

## 限定范围与前置条件

- R463 只写本目录计划及未来步骤报告/阶段总结；不得因这些错误修改产品、测试、R461 原计划/spec/intake、R458 原 runner 或历史失败。
- 不安装解释器或依赖，不修改 PATH、shell profile 或服务；不联网，不触发模型/renderer/engine/物理。R461 frozen child env 保持原值，禁止为了裸 python 改动环境。
- 所有 Python 工具调用采用 `.venv/bin/python`。本规划阶段仅使用它读取标准库 JSON、计算 hash、保存计划，没有产品 import 或测试。
- runner 只从 R461 pins 的 `round458-inheritable-capture-fixture-20261108/implementation/run_stage.py` 取得；SHA256 必须是 `ab3f8edd8392dda68cbd76c5189ffc19aece0e8b94c3cbf74cc8752127498825`。ROOT 才按 R461 复制至 R461 `implementation/run_stage.py`，进行原计划已要求的本轮 plan/schema/spec 绑定与 RED 门控适配，保留原监督器。不得直接重跑 R458。
- 实施前复核以上 pins、31 原输入和当前分支。R461 自己授权的两路径修改依原门控记录；新根因、意外结果或超范围变化立即停止相关修复，交实际 Astra 下一轮。

## Review Focus

裸解释器/猜测路径通过精确 argv 与 pins/rg 证据核验；错误 runner 通过复制前 hash 核验；历史状态通过限定路径复核并原样保留；测试额度通过 stage 账检查；资格误报通过软件、真实与正式三类状态分别记录。上述均为静态/证据检查，不添加 smoke test 或额外 pytest。

## Task 1：恢复命令契约并交回 R461

- [ ] **Step 1：** ROOT 在实施前以只读 hash/Git 检查复核本计划及 R461 输入仍适用，并保存结论；已有原始失败不覆盖。
- [ ] **Step 2：** Python 命令使用 `.venv/bin/python`；runner 从 input-pins 精确项读取并核对 hash 后，在 R461 原授权范围创建本轮副本；其他文件先 `rg --files` 后读取其实际返回路径。记录解释器、真实路径、来源 hash，不新增“试跑”。
- [ ] **Step 3：** ROOT 继续 R461 P0，唯一 `reader-red`、`reader-green`、`adjacent-green`、`ruff`、`format`、`mypy` 各一次、串行、原预算。预检命令错误不得成为重跑测试、扩大修改范围或重置已有 stage 的理由。R461 原两条格式整理命令及次数亦保持不变。
- [ ] **Step 4：** 在 R463 `implementation/step-report.json` 和 `implementation/phase-summary.md` 记录命令修正、原证据及 R461 后续结果链接。R463 静态接受不替代 R461 软件通过；软件通过不替代真实运行或正式研究。

## 验证与验收边界

本 agent 已独立静态复核 31 pins、准确 runner hash、分支及限定产品 diff，确认虚拟环境可执行和两条真实 top_grasp 路径。测试/API/engine/render/service 执行均为 **0**；没有创建实施 runner，没有产品或测试修改。

R463 接受条件是来源准确的命令选择、原失败保留、零环境/产品修正及零额外验证次数，并有 ROOT 步骤报告。R461 六行为节点、精确预期 RED、完整 GREEN/相邻/静态门槛全部保留；正式研究 **NOT_ACCEPTED**，native **UNKNOWN**，实际新运行 **NOT_RUN**。

Self-review：同根因只读错误已合并；输入无漂移且已有用户授权；无新增测试、依赖、服务操作或资格捷径；原计划与失败字节保留。仅交付计划，实施仍由 ROOT 继续。
