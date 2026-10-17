# R173：本地 publication 预算历史接口限定修复

实际规划者：gpt-6-astra（/root/astra_status_plan），2026-10-14。计划冻结，必须先等 R172 实际动作成功且 ROOT 完成 settlement，再激活本轮产品修改。

## 独立判定

这是 T1 的 typed-history 接口缺口，不是已发生的运行失败，也不能只列为 T2 消费者待办。R158 T1 明确要求独立本地预算记录与新 retry envelope；shared _audit_publication 已接受两种 nested local envelope，但 LocalVisualOwnerPublicationRecord 两个 getter 分别只调用 v1 VerificationBudgetRecord decoder 和完整值的旧 RecoveryBudget parser。后者不能把新 envelope 的 payload 填进旧模型，因为旧模型会生成 UTC created_at/updated_at，形成不真实的旧类型实例。

原 finding 4477B，SHA256 27d341ef4e281aa6e4a8a7f753a48d9e48778a2b2ab21a4a81ffc4e3769cae50。31 项完整输入 pins 见 plan.json；24 owned 当前源冻结，211 protected 已独立核对。R172 正在变动的结果/账本没有被当作不可变输入。

## 两文件最小接口方案

只改 visual_owner.py 的 LocalVisualOwnerPublicationRecord 预算接口和必要类型导入，以及 lifecycle.py 新增 LocalRetryBudgetRecord 与必要精确类型导入。其余 22 owned、测试全文、共享 raw receipt codec、legacy decoder、models.py、golden 和所有保护输入不动。

新增 verification_budget_history 属性，明确返回 VerificationBudgetRecord | LocalVerificationBudgetRecord；按 exact local/legacy tag 分派，未知 tag 和已识别但无效的 envelope 直接拒绝，不降级重试。新增 retry_budget_history 属性，返回 RecoveryBudget | LocalRetryBudgetRecord；新 envelope 完整进入独立 carrier，旧完整预算继续原严格模型路径。

旧 verification_budget / retry_budget 保持旧返回类型；遇 exact local envelope 明确 fail-closed 并指向 history 接口。这样不扩大 legacy override，不改 publication 继承层级，也不波及尚未激活的 worker/Memory/SQLite 路径。ROOT 已明确采用此接口边界。T2 新路径必须使用 typed-history 接口并另获真实锁内权限。

LocalRetryBudgetRecord 仅继承 LocalDomainEnvelope，exact tag 为 recovery.retry-budget.local.v1。payload 精确沿用 R158 的 **15 项**：budget_id、task_id、per_step_retry_limit、per_skill_retry_limit、task_total_retry_limit、retry_count_used、task_retry_count、step_retry_counts、skill_retry_counts、event_retry_counts、retry_cooldown_ms、retry_backoff_policy、effective_retry_limit、remaining_retries、scene_version。字符串、非负计数和计数字典逐项使用精确类型访问，字典返回副本；original_recovery_reference 只能从原 envelope.original_time 取得，不能加到 payload、创建新 origin 或补充额度。不存在 UTC 属性、live registry、NEW_COMMIT 或可变预算初始化。

## 门、元数据与额度

R172 实际成功与 ROOT settlement 是硬前置；之后 ROOT 将实际 R172 结果、十三报告及源 snapshot pins 加入 R173 激活。未出现的收据不造 pin。核对本计划 31 输入及 211 protected 后，sole Sol 才改两文件。其余新问题、类型兼容扩域或消费端改动需求均停止另交 Astra。

只新增一次 .venv/bin/python 标准库 metadata 动作，最长 120 秒，执行前 ROOT 全文审读并 pin 新脚本。从已成功冻结的 R172 semantic.sources 获取真实两份 before 字节并与本计划 pin 比对；在同一动作中归档旧十三报告、两源 before、完整限定 diff，保留所有原 23 before / 24 current / 15 later unchanged / 211 protected / A80556 / 七 T1 正文 / golden / runner / 两角色账本核查，再刷新原候选十三输出。R172 动作已耗用后绝不重放。

R158 仍 2 spent / 13 HELD，原 T1 GREEN 0/1，零新增 pytest、static、Git 或 review 额度。未改七测试正文；原 GREEN 与 fresh review 仍走父计划。新 history accessor 本身尚无定向实际测试证据，报告不得因 codec roundtrip GREEN 就声称其访问路径已执行。需要追加测试时必须另有明确计划。

## 验收边界

本轮只产出候选源码修复及真实元数据范围证据。最终仍需 ROOT 新 source/fixture/runner gate、原未用 GREEN 和独立 T1 审查；不授予 T1、B9、T12、native、actual 或 formal 验收。原 finding、所有失败、legacy goldens、R170 receipt 恢复及 R172 修前冻结原件全部保留。
