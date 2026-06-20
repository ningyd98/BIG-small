#!/usr/bin/env python
# ruff: noqa: E501
"""生成中文毕业论文 Markdown、LaTeX，并尝试构建 DOCX/PDF。"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

TITLE = "面向边缘智能场景的小型机械臂云边协同控制系统的设计"
EN_TITLE = (
    "Design of a Cloud-Edge Collaborative Control System for Small Robotic Arms "
    "in Edge Intelligence Scenarios"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build thesis deliverables.")
    parser.add_argument("--generated", type=Path, default=Path("thesis/generated"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/thesis_report"))
    args = parser.parse_args()
    metrics = _read_json(args.generated / "thesis_metrics.json")
    trace = _read_json(args.generated / "claim_evidence.json")
    missing = _read_json(args.generated / "missing_data_report.json")
    figure_index = _load_figure_index(args.generated / "figure_index.json")
    table_index = _read_json(args.generated / "thesis_tables.json")
    docs_dir = Path("docs/thesis")
    thesis_dir = Path("thesis")
    chapters_dir = thesis_dir / "chapters"
    docs_dir.mkdir(parents=True, exist_ok=True)
    chapters_dir.mkdir(parents=True, exist_ok=True)
    thesis_dir.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    manuscript = _markdown_manuscript(metrics, trace, missing, figure_index, table_index)
    _write_docs(docs_dir, manuscript, metrics, trace, missing)
    _write_latex(thesis_dir, chapters_dir, metrics, manuscript)
    report_md = args.output / "论文报告.md"
    report_tex = args.output / "论文报告.tex"
    report_md.write_text(manuscript, encoding="utf-8")
    report_tex.write_text((thesis_dir / "main.tex").read_text(encoding="utf-8"), encoding="utf-8")
    build_status = _attempt_external_builds(report_md, report_tex, args.output)
    (docs_dir / "论文自检报告.md").write_text(
        _self_check_report(metrics, build_status),
        encoding="utf-8",
    )
    (args.output / "build_status.json").write_text(
        json.dumps(build_status, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(build_status, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_figure_index(generated_index: Path) -> list[dict[str, str]]:
    """优先使用完整论文图索引，缺失时回退到 evidence 图索引。"""

    thesis_index = Path("thesis/figures/figure_index.json")
    if thesis_index.exists():
        data = _read_json(thesis_index)
        figures = data.get("figures") if isinstance(data, dict) else data
        if isinstance(figures, list):
            return [_normalize_figure(item) for item in figures if isinstance(item, dict)]
    data = _read_json(generated_index)
    if isinstance(data, list):
        return [_normalize_figure(item) for item in data if isinstance(item, dict)]
    return []


def _normalize_figure(item: dict[str, Any]) -> dict[str, str]:
    path = str(item.get("path", ""))
    name = str(item.get("name") or Path(path).stem or "unnamed_figure")
    return {
        "name": name,
        "path": path,
        "type": str(item.get("type", Path(path).suffix.lstrip(".") or "unknown")),
        "data_source": str(item.get("data_source", "unknown")),
    }


def _markdown_manuscript(
    metrics: dict[str, Any],
    trace: list[dict[str, Any]],
    missing: dict[str, Any],
    figure_index: list[dict[str, str]],
    table_index: list[dict[str, Any]],
) -> str:
    mode_rows = metrics.get("by_mode", {})
    backend_counts = metrics.get("backend_counts", {})
    source_counts = metrics.get("source_counts", {})
    llm = metrics.get("llm_only", {})
    rq = _rq_text()
    f_list = _f_list(metrics)
    b_list = _b_list()
    figures = "\n".join(
        f"- {idx + 1}. {item['name']}：{item['path']}（{item['data_source']}）"
        for idx, item in enumerate(figure_index)
    )
    tables = "\n".join(
        f"- {idx + 1}. {item['name']}：{item['path']}，行数 {item['row_count']}"
        for idx, item in enumerate(table_index)
    )
    trace_lines = "\n".join(
        "| {章节} | {结论} | {指标} | {数值} | {source file} | {authority_level} | {limitations} |".format(
            **item
        )
        for item in trace
    )
    return f"""# {TITLE}

## 封面页

- 学校：________
- 学院：________
- 专业：________
- 作者：________
- 学号：________
- 导师：________
- 完成日期：________

## 中文摘要

面向边缘智能场景的小型机械臂通常需要在网络波动、边缘算力受限和物理执行安全约束并存的条件下完成抓取、搬运、故障恢复和任务重规划。单纯依赖云端大模型直接生成底层控制决策，容易引入时延不可控、输出不可复现和安全责任边界模糊等问题。本文基于 BIG-small 仓库已实现的软件、仿真、dry-run、控制台和证据链，设计并实现一套小型机械臂云边协同控制系统：云端负责高层任务规划并生成结构化 TaskContract，边缘端负责契约校验、状态机执行、SafetyShield 安全裁决、本地恢复和局部重规划。

系统提出 PCSC、ETEAC 和 AUTO 三类协同模式。PCSC 通过周期状态上传和轻量云端监督保持全局可观测性；ETEAC 在初始契约下发后由边缘事件驱动执行和恢复；AUTO 根据风险、网络质量、场景动态性和技能缓存状态选择 PCSC 或 ETEAC。本文还实现 Simulation Workbench、Simulation Runtime、Model Control Center 和 Simulation AI Console，形成从实验配置、运行编排、指标统计到论文证据审计的闭环。

当前 clean validation evidence 显示：Phase 12 validation profile 共 {metrics["run_count"]} 条记录，runtime completed 为 {metrics["runtime_completion_count"]}，blocked before runtime 为 {metrics["blocked_before_runtime_count"]}，synthetic sample 为 {metrics["synthetic_sample_count"]}，unsafe command execution count 为 {metrics["unsafe_command_execution_count"]}。验证范围为软件、仿真、dry-run 和 validation 级证据；full profile 尚未执行完成，真实机械臂验证尚未开始，真实本地模型 runtime 和 Ollama runtime 也尚未形成 accepted evidence。本文进一步给出 LLM-Only Decision Baseline 的 B01-B03 对照实验设计和 fake-provider 管线实现，但在没有真实或本地大模型 runtime accepted evidence 前，不报告仅大模型方案的性能数值差异。

关键词：边缘智能；云边协同；小型机械臂；快慢双系统；任务契约；安全盾；局部重规划；大模型；Sim2Real

## Abstract

Small robotic arms in edge-intelligence scenarios must operate under limited edge computation, unstable networks, delayed cloud intelligence, and strict physical-safety constraints. Directly relying on a cloud large language model for low-level robotic decisions may introduce unbounded latency, weak reproducibility, and unclear safety responsibility. Based on the implemented BIG-small repository, this thesis designs a cloud-edge collaborative control system in which the cloud generates high-level structured TaskContracts, while the edge side performs contract validation, state-machine execution, SafetyShield decisions, local recovery, and local replanning.

The system implements three collaboration modes: PCSC, ETEAC, and AUTO. PCSC keeps periodic cloud supervision; ETEAC executes an initial contract with event-triggered edge autonomy; AUTO selects between PCSC and ETEAC according to risk, network quality, scene dynamics, and skill-cache state. The project further implements a Simulation Workbench, Simulation Runtime, Model Control Center, and Simulation AI Console for reproducible experiments and evidence auditing.

The current clean validation evidence contains {metrics["run_count"]} records, {metrics["runtime_completion_count"]} runtime-completed records, {metrics["blocked_before_runtime_count"]} records blocked before runtime, and {metrics["synthetic_sample_count"]} synthetic samples. The evidence is limited to software, simulation, dry-run, and validation-level results. The full profile, real robot validation, accepted local model runtime, and Ollama runtime remain future work. This thesis also defines and implements a pipeline-level LLM-Only Decision Baseline, but no real LLM performance conclusion is reported without accepted real or local model runtime evidence.

Keywords: edge intelligence; cloud-edge collaboration; small robotic arm; task contract; SafetyShield; local replanning; large language model; Sim2Real

# 第一章 绪论

## 1.1 研究背景

具身智能系统正在从离线规划和固定脚本执行转向云端智能与边缘自治协同。小型机械臂常部署在教育、轻量装配、实验室自动化和边缘智能演示场景中，其硬件成本低、工作空间有限、算力和传感条件受限。随着大模型在自然语言理解和任务规划方面表现出较强能力，云端模型可以承担高层语义理解和任务分解；但机械臂执行需要毫秒级状态反馈、确定性安全裁决和可审计控制边界，不能把底层执行权交给非确定性模型。

## 1.2 问题定义

本文关注的问题是：在网络延迟、丢包、云端不可用、场景变化和安全事件出现时，如何让云端智能参与任务规划，同时保证边缘端拥有最终执行权和拒绝权。系统必须支持故障注入、运行恢复、证据追踪和验证报告，不能把仿真结论写成真实机械臂结论。

## 1.3 研究问题

{rq}

## 1.4 技术路线

自然语言任务与场景信息首先由云端规划器转化为结构化 TaskContract；随后根据 PCSC、ETEAC 或 AUTO 模式进入边缘运行时。边缘端执行契约校验、状态机推进、SafetyShield 安全裁决、技能执行和事件检测。出现 STEP_TIMEOUT、GRASP_FAILED、TARGET_MOVED、PATH_BLOCKED 或 SAFETY_REJECTED 时，系统先尝试本地恢复；必要时生成 FailureSummary 并请求云端局部重规划。所有过程写入 artifact、hash、provenance 和 verifier summary。

## 1.5 论文结构

全文共十二章。第二章综述相关技术；第三章给出需求和总体架构；第四章介绍 PCSC、ETEAC 和 AUTO；第五章说明任务契约与安全执行；第六章讨论边缘自治和局部重规划；第七章介绍系统实现和仿真平台；第八章给出实验设计；第九章分析 validation 级结果与 LLM-only 对照设计；第十章从工程管理角度总结阶段路线和质量门禁；第十一章讨论创新点、局限性和后续工作；第十二章给出结论。

# 第二章 相关技术与研究现状

云边协同机器人系统通常把计算密集型规划放在云端，把时延敏感的控制和安全裁决放在边缘端。事件触发控制和快慢双系统思想为本文提供了基础：慢系统负责高层规划和策略更新，快系统负责实时状态约束、故障检测和局部响应。ROS 2 和 MoveIt 提供机器人软件栈与运动规划接口；MuJoCo 和 Isaac Sim 提供物理仿真与跨后端验证能力。大模型机器人规划研究表明，自然语言模型可以生成任务步骤和参数，但其输出需要结构化 schema、语义验证、安全过滤和执行门。本文不编造未核验文献，具体文献缺口见 `docs/thesis/文献缺口清单.md`。

# 第三章 需求分析与总体架构

## 3.1 功能与非功能需求

系统需要支持任务规划、契约验证、协同模式选择、边缘执行、安全拒绝、故障恢复、局部重规划、实验运行、指标分析和证据导出。非功能需求包括实时性、安全性、可恢复性、可复现性、可审计性和环境阻塞可见性。

## 3.2 总体架构

系统由云端规划层、边缘运行层、仿真与 dry-run 层、Dashboard 与模型控制层、证据与验证层组成。云端 API 基于 FastAPI；边缘端包含任务状态机、SafetyShield、技能执行器和事件检测器；实验层包含 Phase 8 runner、MuJoCo、Isaac 环境检查、MoveIt dry-run、Phase 11 Simulation Runtime 和 Phase 11.2 Planner Dry-Run。

## 3.3 安全边界

Dashboard 不直接控制机械臂；planner dry-run 使用 `dispatch=false`；真实硬件写操作为空。当前 evidence 明确 real_controller_contacted={metrics["real_controller_contacted"]}，hardware_motion_observed={metrics["hardware_motion_observed"]}，hardware_write_operations={metrics["hardware_write_operations"]}，highest_real_hardware_acceptance_level={metrics["highest_real_hardware_acceptance_level"]}。

# 第四章 双模式云边协同机制

## 4.1 PCSC

PCSC 是周期云端监督模式。边缘端按序列号上传 Telemetry，云端返回 KEEP、UPDATE、PAUSE、REQUEST_OBSERVATION 或 ABORT。TTL、version、sequence 和 ACK 用于拒绝过期命令和乱序更新。PCSC 适合高风险、高动态或需要频繁云端监督的场景，但通信开销较高。

## 4.2 ETEAC

ETEAC 是初始规划加边缘事件自治模式。云端生成初始 TaskContract 后，边缘端在事件检测、本地恢复和 FailureSummary 机制支持下执行任务。ETEAC 在网络退化或云端中断时更依赖边缘自治，适合风险可控、场景变化可由本地机制处理的任务。

## 4.3 AUTO

AUTO 不是第三类执行器，而是 PCSC 与 ETEAC 的选择器。它根据风险分数、网络质量、场景动态性、技能缓存命中和历史恢复情况做模式选择，并通过防抖和切换约束降低频繁切换风险。

# 第五章 任务契约和安全执行

TaskContract 是云端到边缘端的唯一高层任务接口，包含任务步骤、技能、参数、超时、前置条件和安全约束。边缘端通过 JSON Schema 和语义校验拒绝非法字段、未知技能、缺失参数和不满足场景条件的请求。CloudCommand、CommandAck、EdgeEvent、FailureSummary 与 CompletionSummary 构成闭环通信。

SafetyShield 独立于大模型和 planner provider，对工作空间、可达性、速度、加速度、障碍物、碰撞、最低安全高度、场景新鲜度和急停状态执行 fail-closed 判断。HardwareExecutionGate 在当前阶段保持 hardware_motion_authorized=false；因此即使上层候选动作不安全，也只会产生 rejected action，不会产生 unsafe command execution。

# 第六章 边缘自治和局部重规划

边缘端事件检测器覆盖完成、超时、网络、执行、设备、安全、场景和目标变化。LocalRecoveryExecutor 受 retry budget 约束，避免无限重试。若本地恢复失败，FailureSummary 提供失败类型、已完成步骤、现场状态和重规划约束。CompletedStepsProtectionValidator 和 ReplanMergeValidator 保证局部重规划不覆盖已完成步骤。Phase 11.1 Simulation Runtime 使用 SQLite、worker lease、heartbeat、restart recovery 和 duplicate worker competition evidence 保持运行恢复语义。

# 第七章 系统实现和仿真平台

系统采用 Python、FastAPI、Pydantic、SQLite、Playwright 和 Dashboard 前端实现。Simulation Workbench 支持 S01-S15 场景目录、Batch、Sweep、实时事件、metrics、comparison、export 和 reproduction。Simulation Runtime 将同步实验改为异步队列、持久化 repository、worker lease、cancel、timeout、retry 和 recovery。Model Control Center 支持 Mock、RuleBased、OpenAI-compatible 和 Ollama profile 管理，但本论文当前未发现真实本地模型 runtime accepted evidence。Simulation AI Console 支持 planner dry-run，并保持 dispatch=false 和 hardware_execution=false。

# 第八章 实验设计

## 8.1 RQ1-RQ8

{rq}

## 8.2 F01-F20

{f_list}

## 8.3 LLM-Only 补充实验 B01-B03

{b_list}

LLM-Only Decision Baseline 不是底层物理设备控制方案。为保证安全边界和控制变量一致性，LLM-only 基线仍使用相同 TaskContract、SafetyShield 和 HardwareExecutionGate。对照变量是智能决策机制和云边协同方式，而不是是否保留基本安全保护。

# 第九章 实验结果与分析

## 9.1 总体结果

clean validation 计划记录数为 {metrics["expected_run_count"]}，实际记录数为 {metrics["run_count"]}。runtime completed 为 {metrics["runtime_completion_count"]}，blocked before runtime 为 {metrics["blocked_before_runtime_count"]}，synthetic sample 为 {metrics["synthetic_sample_count"]}。状态分布为 {metrics["status_counts"]}。后端分布为 {backend_counts}；runtime 后端分布为 {metrics["runtime_backend_counts"]}；结果来源分布为 {source_counts}。

## 9.2 PCSC、ETEAC 与 AUTO

按 control mode 聚合的 validation 数据为：{mode_rows}。这些数据可作为 validation 级软件/仿真观察事实，但不能替代 full profile 的最终统计结论。当前 verifier-gated authoritative rows 为 {metrics["verifier_gated_authoritative_thesis_run_count"]}。

## 9.3 安全、恢复和 F20

unsafe_command_execution_count={metrics["unsafe_command_execution_count"]}。F20 覆盖运行时压力、lease expiration、restart recovery 和 duplicate worker competition；对应 evidence 来自 Phase 11 runtime actual run source evidence。该结论属于 validation 级软件运行证据。

## 9.4 MuJoCo、Isaac 和 MoveIt 边界

MuJoCo runtime 在 validation 中有实际运行记录；Isaac 和 MoveIt 部分样本为环境检查阻塞，不计入 runtime completed。F15 paired summary 显示 expected_pair_count={metrics["paired"].get("expected_pair_count")}，usable_authoritative_pair_count={metrics["paired"].get("usable_authoritative_pair_count")}，blocked_pair_count={metrics["paired"].get("blocked_pair_count")}，paired_backend_experiment_accepted={metrics["paired"].get("paired_backend_experiment_accepted")}。因此当前不能声明 MuJoCo 与 Isaac 的性能趋势一致。

## 9.5 本文方案与仅大模型方案对比

LLM-only 当前状态为 {llm.get("status")}，model_runtime_type={llm.get("model_runtime_type")}，runtime_status={llm.get("runtime_status")}。仓库当前已经完成仅大模型决策基线的接口设计、实验管线和 fake-provider 流程验证，但尚未形成可用于性能比较的真实大模型运行证据。因此，本文当前版本不报告仅大模型方案与云边协同方案之间的最终数值差异，相关结果将在获得经验证的 OpenAI-compatible 或本地 Ollama 运行环境后补充。

# 第十章 工程管理分析

项目采用 Phase 0-12 分阶段路线，逐步完成契约、边缘运行时、安全盾、云端规划、监督、恢复、仿真、运行编排、模型控制和论文证据治理。工程管理重点包括需求冻结、质量门禁、风险台账、环境阻塞管理、CI、自检脚本、证据分级和变更管理。Phase 12.2 特别强化了 adapter attempted、environment check、runtime invoked、runtime completed 和 authoritative thesis run 的语义，避免把环境检查或 placeholder 指标写成真实运行。

# 第十一章 创新点、局限性和后续工作

## 11.1 创新点

本文的工程创新体现在：PCSC 与 ETEAC 双模式协同、AUTO 风险感知选择、结构化 TaskContract、不可绕过的边缘 SafetyShield、FailureSummary 驱动局部重规划、已完成步骤保护、技能缓存、软件/仿真/dry-run/真机分级验收、provenance/hash/lease/artifact 证据链，以及面向论文证据的验收语义治理。

## 11.2 局限性

当前 full profile 尚未运行完成；validation 样本量低于 full 设计；Isaac 部分样本环境阻塞；MoveIt 部分样本环境阻塞；真实本地模型 runtime 和 LLM-only 真实模型对比尚未 accepted；真实机械臂验证尚未开始；当前不能支持真实 Sim2Real 成功率结论。

## 11.3 后续工作

后续需要运行 Phase 12 full profile、补充 Isaac runtime、补充 MoveIt 环境、配置真实 OpenAI-compatible 或 Ollama 模型并运行 LLM-only validation，最后在现场安全条件满足后按真实机械臂 Level 0-6 分级验收推进。

# 第十二章 结论

本文完成了一个面向边缘智能场景的小型机械臂云边协同控制系统的软件、仿真、dry-run、控制台和证据链实现。当前 evidence 能够证明系统在 validation 级完成了 PCSC、ETEAC、AUTO、多后端、多故障、运行恢复、模型控制和论文资产管线的工程验证；同时证明真实控制器未接触、无硬件运动、无硬件写操作。本文也定义并实现了仅大模型决策基线的安全对照框架，但在真实模型 runtime accepted 前不报告性能结论。最终 full profile、真实模型和真机实验是后续升级论文结论的必要条件。

# 附录

## 附录 A TaskContract 示例

TaskContract 包含 task_id、steps、skill、parameters、preconditions、timeout、safety_constraints 和 version 等字段；所有候选动作必须通过 schema、语义校验和 SafetyShield。

## 附录 B 状态机

边缘任务状态机覆盖 CREATED、RUNNING、PAUSED、RECOVERING、COMPLETED、FAILED 和 SAFETY_STOPPED；Simulation Runtime job 状态机覆盖 QUEUED、LEASED、RUNNING、FINALIZING、SUCCEEDED、FAILED、CANCELLED、TIMED_OUT、INTERRUPTED 和 RECOVERY_PENDING。

## 附录 C F01-F20 与 B01-B03

{f_list}

{b_list}

## 附录 D 图表索引

{figures}

## 附录 E 表格索引

{tables}

## 附录 F 证据追踪矩阵

| 章节 | 结论 | 指标 | 数值 | source file | authority_level | limitations |
| --- | --- | --- | --- | --- | --- | --- |
{trace_lines}

## 附录 G 文献缺口

正式参考文献只纳入已核验条目。当前需要继续补充云边协同机器人、快慢双系统、事件触发控制、LLM for robotics、LLM-only agent control、机器人安全、Sim2Real、MuJoCo、Isaac Sim、ROS 2、MoveIt、边缘自治和工程证据链相关文献。
"""


def _rq_text() -> str:
    return "\n".join(
        [
            "- RQ1：与 PCSC 相比，ETEAC 是否能在保证成功率和安全性的前提下降低云端调用和通信开销？",
            "- RQ2：AUTO 是否能在不同网络和故障条件下获得更优综合性能？",
            "- RQ3：边缘本地恢复和局部重规划是否能降低任务失败率和云端完整重规划次数？",
            "- RQ4：SafetyShield 和 HardwareExecutionGate 是否能保持 fail-closed？",
            "- RQ5：MuJoCo 和 Isaac Sim 的实验趋势是否一致，gap 来自哪些指标？",
            "- RQ6：不同 planner/provider 是否影响规划成功率、延迟、修复次数和契约有效率？",
            "- RQ7：技能缓存、风险评估、AUTO 选择器和局部恢复分别贡献什么？",
            "- RQ8：与 LLM-Only Decision Baseline 相比，云边协同架构能否在成功率、时延、鲁棒性、通信、安全、恢复和复现性方面取得更好的综合表现？当前 RQ8 是待真实模型运行补充的假设。",
        ]
    )


def _f_list(metrics: dict[str, Any]) -> str:
    experiments = metrics.get("experiment_status", {})
    return "\n".join(f"- {key}：{value}" for key, value in sorted(experiments.items()))


def _b_list() -> str:
    return "\n".join(
        [
            "- B01_LLM_ONLY_ONESHOT：一次模型调用生成完整 TaskContract，异常时失败或整体重试。",
            "- B02_LLM_ONLY_REACTIVE：每一步或异常后调用模型生成下一动作，仍经过契约校验和 SafetyShield。",
            "- B03_PROPOSED_ARCHITECTURE_PAIRED_COMPARISON：LLM-only one-shot、reactive、PCSC、ETEAC、AUTO 在相同场景、seed、后端和安全策略下配对比较。",
        ]
    )


def _write_docs(
    docs_dir: Path,
    manuscript: str,
    metrics: dict[str, Any],
    trace: list[dict[str, Any]],
    missing: dict[str, Any],
) -> None:
    docs = {
        "论文报告_完整版.md": manuscript,
        "论文摘要.md": manuscript.split("# 第一章")[0],
        "论文大纲.md": _outline(),
        "研究问题与实验对应表.md": _rq_mapping(metrics),
        "证据追踪矩阵.md": _trace_markdown(trace),
        "结论边界说明.md": _boundary(metrics),
        "文献缺口清单.md": _literature_gap(),
        "full_profile后续更新说明.md": _full_update_plan(missing),
        "仅大模型基线设计.md": _llm_design(),
        "大模型与云边协同对比实验.md": _llm_comparison_design(),
        "大模型实验环境阻塞说明.md": _llm_blockers(missing),
        "大模型对比结果模板.md": _llm_result_template(),
        "大模型实验复现指南.md": _llm_reproduction(),
    }
    for name, text in docs.items():
        (docs_dir / name).write_text(text, encoding="utf-8")


def _outline() -> str:
    chapters = [
        "绪论",
        "相关技术与研究现状",
        "需求分析与总体架构",
        "双模式云边协同机制",
        "任务契约和安全执行",
        "边缘自治和局部重规划",
        "系统实现和仿真平台",
        "实验设计",
        "实验结果与分析",
        "工程管理分析",
        "创新点、局限性和后续工作",
        "结论",
    ]
    return "# 论文大纲\n\n" + "\n".join(f"{idx + 1}. {name}" for idx, name in enumerate(chapters))


def _rq_mapping(metrics: dict[str, Any]) -> str:
    return "# 研究问题与实验对应表\n\n" + _f_list(metrics) + "\n\n" + _b_list()


def _trace_markdown(trace: list[dict[str, Any]]) -> str:
    lines = [
        "# 证据追踪矩阵",
        "",
        "| 章节 | 结论 | 指标 | 数值 | source file | source field | authority | limitations |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in trace:
        lines.append(
            f"| {row['章节']} | {row['结论']} | {row['指标']} | {row['数值']} | "
            f"{row['source file']} | {row['source field']} | {row['authority_level']} | "
            f"{row['limitations']} |"
        )
    return "\n".join(lines) + "\n"


def _boundary(metrics: dict[str, Any]) -> str:
    return f"""# 结论边界说明

- 当前状态：{metrics["status"]}，项目状态：{metrics["project_status"]}。
- full profile execution：{metrics["full_profile_execution_status"]}。
- 真实控制器接触：{metrics["real_controller_contacted"]}。
- 物理运动：{metrics["hardware_motion_observed"]}。
- 硬件写操作：{metrics["hardware_write_operations"]}。
- 最高真实硬件等级：{metrics["highest_real_hardware_acceptance_level"]}。
- fake provider 不代表真实大模型效果。
"""


def _literature_gap() -> str:
    topics = [
        "云边协同机器人",
        "快慢双系统",
        "事件触发控制",
        "LLM for robotics",
        "LLM-only agent control",
        "机器人安全",
        "Sim2Real",
        "MuJoCo",
        "Isaac Sim",
        "ROS 2",
        "MoveIt",
        "边缘自治",
        "工程证据链",
    ]
    return "# 文献缺口清单\n\n" + "\n".join(
        f"- {topic}：待人工核验后进入 references.bib。" for topic in topics
    )


def _full_update_plan(missing: dict[str, Any]) -> str:
    return "# full_profile 后续更新说明\n\n" + "\n".join(
        f"- {item}" for item in missing.get("required_follow_up", [])
    )


def _llm_design() -> str:
    return """# 仅大模型基线设计

LLM-Only Decision Baseline 包括 B01 one-shot、B02 reactive 和 B03 paired comparison。
所有输出仍转为 TaskContract，并经过 SafetyShield 与 HardwareExecutionGate。当前 fake-provider
仅用于管线验证，不能用于真实大模型性能结论。
"""


def _llm_comparison_design() -> str:
    return """# 大模型与云边协同对比实验

配对组包括 LLM-Only One-Shot、LLM-Only Reactive、PCSC、ETEAC 和 AUTO。控制变量包括场景、seed、repetition、后端、任务目标、安全策略、模型参数和超时时间。
"""


def _llm_blockers(missing: dict[str, Any]) -> str:
    return "# 大模型实验环境阻塞说明\n\n" + json.dumps(
        missing.get("llm_only_runtime", "BLOCKED_BY_ENV"),
        ensure_ascii=False,
        indent=2,
    )


def _llm_result_template() -> str:
    return """# 大模型对比结果模板

| 组别 | runtime type | 有效样本 | 成功率 | 平均时延 | 模型调用 | token | 成本 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LLM-Only One-Shot | 待补充 | 0 | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | 待真实模型运行 |
| LLM-Only Reactive | 待补充 | 0 | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | 待真实模型运行 |
"""


def _llm_reproduction() -> str:
    return """# 大模型实验复现指南

本指南用于复现 LLM-Only Decision Baseline 的软件管线。默认命令只运行 fake provider smoke，
状态只能写为 `LLM_ONLY_BASELINE_PIPELINE_READY`，不得作为真实大模型性能证据。

## Fake Provider Smoke

```bash
# 运行 fake provider smoke，只验证 LLM-only 管线和证据脱敏，不代表真实大模型性能
python scripts/run_llm_only_baseline.py --profile smoke --provider fake
python scripts/analyze_llm_only_baseline.py
python scripts/verify_llm_only_baseline.py
```

输出目录为 `artifacts/thesis_baselines/llm_only/`。其中响应文件只保存 prompt hash、
response hash、运行等级和脱敏摘要，不保存 API key、Authorization header 或模型密钥。

## OpenAI-Compatible Validation

真实 OpenAI-compatible provider 需要用户显式配置 endpoint、model 和 API key。未配置或未授权时，
脚本必须输出 `LLM_ONLY_BASELINE_BLOCKED_BY_MODEL_ENV`，不得自动回退 fake，也不得调用收费服务。

## Ollama Validation

本地 Ollama provider 只在 daemon 可达且指定模型已安装时运行。脚本不会自动下载大型模型；
模型不存在时记录 `BLOCKED_BY_ENV`。所有实验仍然是 simulation-only，并且动作必须经过
TaskContract、SafetyShield 和 HardwareExecutionGate。

## 安全边界

LLM-only baseline 不连接真实控制器，不发送真实机械臂控制命令，不执行 MoveIt execute，
不发布 ROS trajectory。真实模型数据只有在 `REAL_LLM_RUNTIME` 或 `LOCAL_LLM_RUNTIME`
accepted evidence 存在时，才能写入性能比较章节。
"""


def _write_latex(
    thesis_dir: Path,
    chapters_dir: Path,
    metrics: dict[str, Any],
    manuscript: str,
) -> None:
    chapter_titles = [
        "绪论",
        "相关技术与研究现状",
        "需求分析与总体架构",
        "双模式云边协同机制",
        "任务契约和安全执行",
        "边缘自治和局部重规划",
        "系统实现和仿真平台",
        "实验设计",
        "实验结果与分析",
        "工程管理分析",
        "创新点、局限性和后续工作",
        "结论",
    ]
    for idx, title in enumerate(chapter_titles, start=1):
        path = chapters_dir / f"{idx:02d}_{_chapter_slug(idx)}.tex"
        path.write_text(
            f"\\chapter{{{title}}}\n\n"
            f"本章内容见 Markdown 完整稿。关键 validation 记录数为 {metrics['run_count']}，"
            f"runtime completed 为 {metrics['runtime_completion_count']}。"
            "\n",
            encoding="utf-8",
        )
    (thesis_dir / "appendix.tex").write_text(
        "\\appendix\n\\chapter{证据追踪矩阵}\n详见 docs/thesis/证据追踪矩阵.md。\n",
        encoding="utf-8",
    )
    (thesis_dir / "references.bib").write_text(
        "% 仅纳入已核验文献；当前文献缺口见 docs/thesis/文献缺口清单.md。\n",
        encoding="utf-8",
    )
    includes = "\n".join(
        f"\\include{{chapters/{idx:02d}_{_chapter_slug(idx)}}}" for idx in range(1, 13)
    )
    (thesis_dir / "main.tex").write_text(
        "\\documentclass[UTF8]{ctexbook}\n"
        "\\usepackage{geometry}\n"
        "\\geometry{a4paper, margin=2.5cm}\n"
        f"\\title{{{TITLE}}}\n"
        "\\author{________}\n"
        "\\date{________}\n"
        "\\begin{document}\n\\maketitle\n"
        f"\\chapter*{{摘要}}\n本文 validation 级证据包含 {metrics['run_count']} 条记录；full profile 尚未完成。\n"
        f"{includes}\n"
        "\\include{appendix}\n"
        "\\bibliographystyle{plain}\n\\bibliography{references}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )


def _chapter_slug(index: int) -> str:
    names = [
        "introduction",
        "related_work",
        "requirements_architecture",
        "collaboration_modes",
        "contract_safety",
        "recovery_replanning",
        "implementation",
        "experiment_design",
        "results",
        "engineering_management",
        "innovation_limitations",
        "conclusion",
    ]
    return names[index - 1]


def _attempt_external_builds(report_md: Path, report_tex: Path, output: Path) -> dict[str, Any]:
    status: dict[str, Any] = {
        "markdown": str(report_md),
        "latex": str(report_tex),
        "docx": "NOT_BUILT",
        "pdf": "NOT_BUILT",
        "docx_reason": "",
        "pdf_reason": "",
    }
    pandoc = shutil.which("pandoc")
    if pandoc:
        docx = output / "论文报告.docx"
        pdf = output / "论文报告.pdf"
        docx_run = subprocess.run(
            [pandoc, str(report_md), "-o", str(docx)],
            check=False,
            text=True,
            capture_output=True,
        )
        if docx_run.returncode == 0:
            status["docx"] = str(docx)
        else:
            status["docx_reason"] = docx_run.stderr[-500:]
        pdf_run = subprocess.run(
            [pandoc, str(report_md), "-o", str(pdf)],
            check=False,
            text=True,
            capture_output=True,
        )
        if pdf_run.returncode == 0:
            status["pdf"] = str(pdf)
        else:
            status["pdf_reason"] = pdf_run.stderr[-500:]
    else:
        status["docx_reason"] = "pandoc not found"
        status["pdf_reason"] = "pandoc not found"
    return status


def _self_check_report(metrics: dict[str, Any], build_status: dict[str, Any]) -> str:
    return f"""# 论文自检报告

- validation status：{metrics["status"]}
- thesis status：{metrics["thesis_status"]}
- project status：{metrics["project_status"]}
- full profile execution：{metrics["full_profile_execution_status"]}
- unsafe command execution count：{metrics["unsafe_command_execution_count"]}
- DOCX：{build_status["docx"]}
- PDF：{build_status["pdf"]}
- 说明：DOCX/PDF 依赖 pandoc 或 LaTeX 环境；缺失时不伪造输出。
"""


if __name__ == "__main__":
    raise SystemExit(main())
