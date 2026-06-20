# 面向边缘智能场景的小型机械臂云边协同控制系统的设计

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

当前 clean validation evidence 显示：Phase 12 validation profile 共 {{ run_count }} 条 validation row，其中 runtime completed 为 {{ runtime_completion_count }}，blocked before runtime 为 {{ blocked_before_runtime_count }}，synthetic sample 为 {{ synthetic_sample_count }}，unsafe command execution count 为 {{ unsafe_command_execution_count }}。验证范围为软件、仿真、dry-run 和 validation 级证据；full profile 尚未执行完成，真实机械臂验证尚未开始，真实本地模型 runtime 和 Ollama runtime 也尚未形成 accepted evidence。本文进一步给出 LLM-Only Decision Baseline 的 B01-B03 对照实验设计和 fake-provider 管线实现，但在没有真实或本地大模型 runtime accepted evidence 前，不报告仅大模型方案的性能数值差异。

关键词：边缘智能；云边协同；小型机械臂；快慢双系统；任务契约；安全盾；局部重规划；大模型；Sim2Real

## Abstract

Small robotic arms in edge-intelligence scenarios must operate under limited edge computation, unstable networks, delayed cloud intelligence, and strict physical-safety constraints. Directly relying on a cloud large language model for low-level robotic decisions may introduce unbounded latency, weak reproducibility, and unclear safety responsibility. Based on the implemented BIG-small repository, this thesis designs a cloud-edge collaborative control system in which the cloud generates high-level structured TaskContracts, while the edge side performs contract validation, state-machine execution, SafetyShield decisions, local recovery, and local replanning.

The system implements three collaboration modes: PCSC, ETEAC, and AUTO. PCSC keeps periodic cloud supervision; ETEAC executes an initial contract with event-triggered edge autonomy; AUTO selects between PCSC and ETEAC according to risk, network quality, scene dynamics, and skill-cache state. The project further implements a Simulation Workbench, Simulation Runtime, Model Control Center, and Simulation AI Console for reproducible experiments and evidence auditing.

The current clean validation evidence contains 540 validation rows, including 466 runtime-completed rows, 74 rows blocked before runtime, and 0 synthetic samples. The evidence is limited to software, simulation, dry-run, and validation-level results. The full profile, real robot validation, accepted local model runtime, and Ollama runtime remain future work. This thesis also defines and implements a pipeline-level LLM-Only Decision Baseline, but no real LLM performance conclusion is reported without accepted real or local model runtime evidence.

Keywords: edge intelligence; cloud-edge collaboration; small robotic arm; task contract; SafetyShield; local replanning; large language model; Sim2Real
