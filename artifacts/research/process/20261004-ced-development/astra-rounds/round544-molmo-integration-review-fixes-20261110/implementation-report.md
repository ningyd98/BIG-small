# R544 实施报告

实际计划模型：gpt-6-astra；原始审查、输入 SHA256 与失败证据保留于 review.md / review-request.json / original/，未改写。实施前已复核8项输入。

## 修复与证据

- I1：规划期间固定 request 与任务描述副本及其哈希；两次定位、云端返回、合同构建各边界复核。12项上下文漂移回归覆盖 observation、instruction/control context、descriptor 在三个阶段的替换；不再产生旧观测/新请求合同。
- I2：技能 JSON 拒绝任何深度重复键、转义等价键及非有限数；5项重复键回归，空技能与严格白名单保持原语义。
- I3：native paid 必须真实 transport start、非空完整尝试、几何 READY 且管线 PLANNED 才通过；timeout、malformed、empty、pipeline rejection 均返回2。no-paid 几何检查与付费云端接受分开。
- I4：只读取并保存实际解析的输入原始字节；fresh 模板/新采集 request、RGB、float32 depth 分开保存；云端请求/响应正文及实际 content 独立留存，不写认证头。成功或异常都生成 raw manifest；加载失败也从持久化 start 记录计数。模型/角色快照与 digest 写入观测证据。
- I5：generate+synchronize 完成即持久化 output token IDs、耗时并计 completed；解码失败仍有 starts1/completed1，保留失败记录，未伪造文本。
- M1：CLI 路径 bootstrap 所需 E402 限定豁免，其他 Ruff 规则保持启用。

repair-red.log：26 failed / 101 passed，属于计划预期 RED。repair-green.log：127 passed。scoped-regression.log：249 passed（含120项原接口回归与2项 R545 launcher 测试），1项既有 anyio 弃用警告。均使用原 app .venv Python，纯 CPU 夹具，无实际模型或外部请求。

最终 lint 另发现 observer 循环变量绑定问题，先保存证据并由实际 Astra 制定 R546 计划，随后修复；未越过计划直接修改。最终250项回归、Ruff及 diff check 全通过，详见 R546/final-command-results.json 及对应 stdout/stderr。本报告最终源码 SHA 位于 implementation-input-output.json。

## 审查未评估项的裁定

- 原生模型准确率与延迟：独立 R542 有界诊断记录；CPU 夹具不作模型能力证据。
- 真实付费云端能力/成本：本轮 NOT_PERFORMED；服务工厂仅证明身份/传输/默认权限的软件边界。
- 连续控制、物理安全与任务完成：NOT_PERFORMED，无硬件派发。
- heldout/G1/G2 与正式研究：NOT_PERFORMED，不继承历史接受状态。
- 全量套件：基线23 failed / 49 errors，后续 EGL 部分运行同样失败后按进程身份停止；FULL_SUITE_FAILED_AND_INCOMPLETE，原始日志保留，不用250项相关回归替代全量结果。

一次独立审查及本次限定修复已完成；无第二次审查要求。R546 为审查后新 lint 的单独计划。所有真实运行与软件验证在 R542 phase-summary.md 分列。
