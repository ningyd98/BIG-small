# R06 startup readout wording correction Implementation Plan

> **For agentic workers:** Follow the existing root execution arrangement; two bounded documentation actions only. No design confirmation, repeated configuration question, source implementation or actual probe.

**Goal:** 将 R06 派生读物中的“四角色请求”纠正为“四次角色 probe 请求”，保留原错误报告及机器证据原字节。

**Architecture:** 仅新增原报告同目录 corrected-report.md，注明勘误来源并复用原正文。原 report.md/report.json 保持冻结；不更改软件、配置、DB、环境、root文档或Git。

**Tech Stack:** Python3 stdlib 文件读取、字符串比较、SHA256与JSON解析；不执行pytest、角色probe或项目代码。

**Spec:** 根 AGENTS.md 的先Astra计划与保留原件要求；原 report.json 的 role_configuration.registered_nominal_attempts=4、next_boundary.actual_prerequisites=cold+3warm；ced_roles.yaml 的 cloud/edge/device 与 probe.warm_runs=3。四项输入SHA/bytes见相邻 plan.json。

## Global Constraints

- 仅措辞纠正；云/边/端是三个架构角色，cold+3warm是四次名义请求，不改实际角色或请求配置。
- 原MD SHA256：876b537f0f44591742c8233db9f1aa5933b53f5d7cbe46055a603bb3f7d8bec1。
- 原JSON SHA256：313d65c53d479d0b862758a63e35778a37127fe98002a6083cba7b3fed4d6c2c。
- 不重读DB/环境、不读secret，不运行probe/network/model/renderer/physics/test，不修改当前OC1计划或运行中的软件。所有exec按当前已知环境使用require_escalated。
- 原JSON的18pins、两DB前后quiet、presence false/0 enabledMax/0calls是原次只读复核结果；本次不声称重新测得，也不推断全局账户/会话没有密钥。
- 无需重复询问配置或设计许可。root后续阶段汇总可引用新准确报告；本计划执行范围不含修改root文档/Stage/Git。

## 原失败、根因及 Review Focus

原MD第3行原文“不能启动新 Max 四角色请求”将请求次数误写为架构角色数。同MD第5行已写cold+3warm=4，第15行写“四次真实 probe 未执行”；机器报告registered_nominal_attempts=4，配置有cloud、edge、device三段和warm_runs=3。根因是单处读物措辞失准，不是配置、模型执行或机器计数错误。

重点核查：只替换首段这一处；原两文件字节不变；新报告明确是原次证据的文案勘误；不扩充角色或把名义请求写成已执行。四项输入均已实际只读并固定，未重新执行原18项审计/DB查询。

## 执行项（最多两项）

- [ ] **1. 新增精确派生报告。** 实施前重算四项输入SHA且与plan.json一致；若相关输入变动，暂停本项并交Astra确认下一轮，不覆盖任何原件。确认目标不存在，只新增 artifacts/research/process/20261004-ced-development/astra-repair-execution/R06/current-startup-revalidation/corrected-report.md。文件开头用简短勘误说明：引用同目录原report.md与report.json并列上述冻结SHA，解释cloud/edge/device三个架构角色、cold+3warm为四次名义请求；明确仅修正原次复核读物、没有重新审计配置或产生请求。说明之后设置“原次复核正文（仅首段措辞勘误）”分隔标题，附原MD完整正文，且只把“不能启动新 Max 四角色请求”精确替换为“不能启动新 Max 四次角色 probe 请求”。原正文其余字节/链接/结论保持，不补写新时间事实，不把其中“本轮”解释为本次执行。
- [ ] **2. 限定文本及原件核验并交root。** 用stdlib读取新文件，取上述分隔标题之后正文，与原MD执行一次指定replace所得字符串逐字节相等；原短语仅在原MD存在、新正文为准确短语且次数1。验证开头两个链接/两个SHA、三角色与四请求说明；重算原MD/JSON/config/AGENTS四SHA仍一致。只输出校验结果与corrected-report.md完整SHA供root保存/汇总，最高TEXT_CORRECTION_VERIFIED。无需编写/运行软件测试、重跑18pins或DB检查。root后续可引用新报告；原错误证据继续保留。若出现计划外内容/范围问题，先保全并Astra下一轮。

## 实际运行前置与验收边界

本计划不允许任何actual probe。原R6实际前置仍为受控enabled compatible Max profile与真实账户endpoint/约束、显式profile选择、secret来源、冻结预算及共享renderer队列；这些仅引用原JSON，不在本次操作，不再次询问用户。当前0请求、current_startup_ready=false、role_acceptance=false、formal_accepted=false保持；文本核验不是当前模型可用性或正式验收。

本次规划仅新增plan.md/json；未修改现有报告、代码、root文档、配置、DB、环境、Stage/Git，未调用网络/model/actual/test。Astra角色依据用户指定派单；运行时模型身份未独立探测。自查已覆盖单处修正、历史原件、角色/请求数量、证据时点、最小范围与无新增许可阻断。
