# R433 原始失败逐行保留 Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans inline；只处理独立评审 R431-F4，不扩大其他门的语义。

**Goal:** 前置畸形 action result 不再中断后续原始失败的保留。
**Architecture:** 只改 `_Audit.retain_failures` 的逐行扫描健壮性，并加一个组合反例；原覆盖门、输出schema、authority不变。
**Tech Stack:** 现有 Python/pytest、R431 runner、R413 supervisor/R235 plugins。
**Spec:** 本轮 intake/observation.json 和 pinned R431/review/final-astra-review.json F4。

## 证据与根因

F4 是静态路径发现，尚未运行反例。retain_failures 直接对 returned_result 调 .get；前一行 result=[] 时 AttributeError 被外层阶段处理器接住，整组/后续组扫描退出。strict_records 保留第一条畸形原件，却不会替它补回后续结构完整的失败记录。结果仍 INCOMPLETE；这是失败库存丢失，不是成功判定或 live authority 逃逸。

已核对20项 intake pins及四份 source preimage；当前 reader SHA=8f780dae109db7f276674081256b1683d144f495554308e414fc3ed723bb242a。R431原91 PASS、R432五Name alpha等价及三静态PASS均保留各自归属，R432没有重跑91。HEAD aecf1fd836ff08819edb053a2e87b4b2a83235b0，研发分支 research/20261004-continuation，实施者开始前再确认当前上下文与全部pins。

允许修改两个文件：`src/cloud_edge_robot_arm/research/native_completion_horizon_originals.py`（仅 retain_failures 方法体）、`tests/test_native_completion_horizon_originals_v1.py`（只增下述单项测试，不改fixture/正例/既有测试）。其他三门、strict_records、failure helper、rational kernel、其他测试及输出字段不改；不清空/去重/裁剪原失败或原始列表。

## Task 1：单个组合反例、逐行修复、原91回归

- [ ] 新增 `test_malformed_result_does_not_hide_later_original_failure`。deepcopy既有完整source，先复制完整action用于第二条，再将第一条 returned_result=[] 且 error=None。第二条保持所有完整字段、disposition=RETURNED，设唯一span_id=`span-2`和唯一record_seq；完整ActionResult改success=False、error_code=`R431_LATER_ACTION_FAILURE`，row.error同marker。追加第二条action与allocated_action_ids中的span-2，其他原件不变，仅pack新测试字节。
- [ ] 断言结果 INCOMPLETE、allocated_action_count=2、SOFTWARE_ONLY/UNKNOWN/UNAVAILABLE/NOT_PROVEN不变。解析original_failures JSON，确认畸形第一条**完整原行**被保留（可在existing `original` envelope内），并确认完整第二失败行含span-2、error和result.error_code marker原值；不能只断言任意通用gap字符串或第二动作被拒绝。保存输入deepcopy/encoded摘要以确认audit未修改传入原数据。断言顺序先保留现有有效INCOMPLETE/畸形断言，再断言后来失败行，以得到明确预期RED。
- [ ] 一次RED只跑新负例和既有 `test_complete_handwritten_originals_keep_unknown`：预期负例call FAIL于缺第二原失败，正例PASS，setup/teardown全PASS。任何其他失败不是预期RED，暂停交下一Astra。先留原始日志，再改产品。
- [ ] retain_failures 保留原ledger failure/pending扫描和判失败条件；将四组改成可标识group名与逐行index遍历，在每行内先确认row为dict，returned_result若存在且非None须为dict，再读取success。disposition等被读取字段若会因畸形类型触发异常也必须限定在本行处理；不尝试修复/coerce值。已识别失败仍保留整条原行及顺序。
- [ ] 对畸形本行，将 `group`、`index`、`original` 原值及稳定错误描述通过现有 failure helper保存，增加 `malformed_failure_scan_record:<group>:<index>` 结构理由，然后继续下一行及下一组。可使用显式type guards或本行有限异常边界（ValueError/TypeError/KeyError/AttributeError/IndexError）；禁止捕获BaseException/吞系统失败，不用整个组try-except重建同一缺口。JSON来自已解码输入，保存原值不对外部对象求值。已经存在的 malformed记录可以重复保存，但不得删除之前证据；末尾仍执行 original_failures_or_pending_operations 检查。
- [ ] 通过限定diff确认方法外代码完全不变、原fixture/既有测试不变、rational模块及其测试SHA不变。一次GREEN按plan.json既有选择（原91+新1，同一测试文件不可重复加入），共92项setup/call/teardown全PASS，无skip/drift/live。随后原三条聚焦静态每条一次60s，全部exit0，不修改配置或拓宽修复。

## 前置条件、冻结及证据

使用现有.venv，不安装、不启动模型/网络/硬件/MuJoCo或全suite。RED/GREEN均固定timeout_s=600、attempt=1，fresh R433目录/basetemp，显式JUnit；沿pinned R431 runner和不变R413 supervisor/R235 startup/event plugin。已有baseline1317保持原SHA；input_pins留作preimage，两个允许变更文件按phase追加当前pin（RED原reader+新增测试，GREEN修复reader+同一冻结测试）。旧logical preimage不混入当前运行表造成冲突，旧snapshot/plan/manifest仍按历史路径固定SHA；绝不覆盖旧manifest或冲突后静默取后值。

冻结本轮plan/runner、测试原件、phase source pins，保存spec/stdout/stderr/events/JUnit/result和静态输出、post-pins、限定diff与步骤/阶段报告。实际预期：RED1失败1通过；GREEN92通过；静态三条通过。当前F4此前没有运行失败日志，报告不得声称已有复现。

## 验收与停止边界

软件验收仅为畸形行与后续合法失败均完整保留、分配分母不变、既有正例及91项回归通过；其他覆盖语义未改。原件审计仍SOFTWARE_ONLY，实际full-H producer、deadline/hard-stop执行闭包与独立校准未交付，actual NOT_STARTED、formal UNKNOWN。保留R431事实纠正：COMMAND含physics_state及command_records；本轮没有live验证，不重复旧错误原因。

任何新根因、额外范围、RED偏离、GREEN/静态失败、超时或pin漂移必须停止相关修复交下一实际Astra，保留原始证据，不重试/加时/删测试。计划完成后的明确路径提交推送及local/upstream/remote SHA核对由已获授权父任务执行，受保护dirty gitlinks不动。本planner仅写计划，不实施、不跑测试或Git。
