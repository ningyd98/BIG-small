# R174：旧预算条件的夹具 JSON 边界恢复

实际规划者：gpt-6-astra（/root/astra_status_plan），2026-10-14。本轮仅制定计划，未改测试/产品，未执行验证或启动审阅者。

## 实际失败与独立诊断

原 R158 t1_green 已消费 1/0。真实 pytest exit 1，外层 runner tool exit 2；JUnit 为 7 tests、5 PASS、2 FAIL、0 error、0 skip。失败节点为 roundtrip[route_completion_budget] 与 cannot_mint_live_authority，都在 strict LocalEnvelope._copy 遇到 ('UNKNOWN', None)。六份实际 raw 已逐一与原件核对，完整 SHA 见 plan.json；原5 PASS不能称整体通过。

独立源码证据说明这是 fixture 跳过持久 JSON 边界：VerificationBudgetState.previous_conditions 本来就是 tuple；它本身没有独立 to_payload/from_payload，实际 lifecycle._state_payload/asdict 保留 tuple，_state_from_payload 刻意从 JSON 数组还原 tuple。_b_local_cases 却把内存 to_payload 直接 deepcopy 到严格新 JSONValue envelope。真实 R166 golden 将同条件保存为 ["UNKNOWN",null]。route record 自身已经过 _plain/canonical/json.loads，不能把这个生产 codec 误报为失败。trace 未记录当前 loop tag，具体失败迭代来源属于上述源码推导，不伪造帧数据。

## 最小修复

只准 sole Sol 修改 tests/test_operational_runtime_closure.py 内 _b_local_cases；起止准确 marker 已列入 JSON。先保留真实旧 codec 原始返回，再使用 json.dumps（allow_nan=False、sort_keys=True、紧凑 separators、ensure_ascii=False、无 default 转换）及 json.loads，得到持久 JSON 形式，再提取 body/diagnostics。

原 source 未变断言继续与未归一化旧返回比较；另保留 JSON 等价断言。预算 limits/counters/previous_conditions/revision/hash 断言继续检查真实归一化内容。不能删除断言，不能归一化负例、任意 caller/local payload、原 decision 或 live 对象。

全部23生产源、strict _copy、R170 raw receipt、R173 typed-history 接口、211 protected、七测试正文/装饰器、A80556、原23 before、16-tag golden、原runner及旧raw不变。

## 精确顺序与有限额度

1. ROOT 校验本计划55项输入、两角色父账本真实3 spent / 12 HELD，全文审读 helper diff 与两个新脚本。作者原 t1_green 是 SPENT，ROOT 是 SPENT_ACTUAL_UNEXPECTED_T1_GREEN_FAILURE，均1/0；剩余12项各自 HELD/HELD_PENDING_ROOT_GATE，不重置。
2. 新 preparation_metadata 一次（120秒，纯标准库文本/hash/JSON）：先完整归档13旧报告，从已 pin semantic.sources 取得真实 before-test，证明只有 helper 变化，再生成24源完整候选快照/限定diff/范围证明并刷新工作报告为真实3/12。旧报告2/13仅是当时快照，R172/R173原轮证据不得覆盖。
3. ROOT 实读准备证明、源码、新runner及明确 argv/env/SHA 后，才释放独立 R174 recovery7 一次（600秒）。精确七节点、顺序、finite environment、golden controls、resource caps 全沿真实原 invocation；只换新 basetemp、JUnit与原始输出目录，使用独立R174预算/command_id，不调用已耗原runner槽。
4. ROOT 新 settlement_metadata 一次（120秒，纯标准库）核实际raw/JUnit/输入不变与资源证据，结算R174本轮账本和步骤报告。所有三个执行槽均单次，禁止隐含helper或retry。父15 commands对象保持3/12，不改旧结果。
5. 仅真实恢复7 PASS且ROOT结算合格后，使用原R158尚未消费的T1 fresh review额度（12批、每批最多600源行、0产品命令）；若该额度并非未用则停止，不补造/重置。规划阶段不启动审阅者。

原环境含 BIGSMALL_R158_COMMAND=t1_green，只作为现有测试读取 golden 的选择器；不代表释放旧命令。新输出为本轮 implementation/recovery7，独立临时目录 /tmp/bigsmall-p6-r174-t1-green-recovery。资源上限为每pytest最多64 worker lifecycles、同时最多2 workers、每worker最多1 broker和1 heartbeat线程，0外部模型/网络/GPU/native。新runner须记录真正 child/runner退出码、独立stdout/stderr/JUnit与timeout/cleanup；未证实资源关闭不能填true。

## 验收边界

恢复结果属于全新单次七节点运行；原5 PASS/2 FAIL、先前RED和control、golden均保留。R173 history accessor未有定向实际执行仍明确为false，不能由roundtrip成功推断。T1完成还需ROOT真实核验和fresh review；本计划不授予B9/T12/native/actual/formal验收。任何新根因、范围扩大、guard不符或执行失败都停止，保留证据后另交实际Astra，不做试跑或重置。
