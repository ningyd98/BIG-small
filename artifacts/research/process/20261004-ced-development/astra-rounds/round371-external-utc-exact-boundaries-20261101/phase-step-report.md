# R371 UTC 场景时间边界修复步骤报告（2026-11-01）

## 问题与本轮依据

用户授权修复问题1（UTC）。R370按原Astra计划补齐request_id后真实短GREEN出现新的边界断言失败；原JUnit/输出/源身份保持在R370目录，槽位SPENT不复用。实际gpt-6-astra制定R371，31/31直接输入在实施前复核匹配，未递归绑定历史。

根因是用int(delta.total_seconds()*1000)进行新鲜度判定：浮点误差可把未来1001ms转换并截断为1000ms；整数截断还会吞掉超TTL的微秒。原JUnit未直接显示循环offset，此定位来自源码顺序与计划内stdlib算术；新回归实际验证对应边界。

## 修改

- pipeline.py的check_scene_sufficiency两分支改用精确timedelta比较；整数毫秒仅保留在错误文案。RGB-D未来1秒容忍、默认5秒TTL及等号有效不变；summary分支保持原有不拒绝未来时间的语义。深度、对象、区域等检查顺序不变。
- 原helper的updated_at与request_id两处必填构造修复纳入本次交付；R371期间helper字节未变。
- 短合同原4006字节完整保留，先追加两个具名测试，再修改产品；每分支12个边界行，覆盖默认/自定义TTL、等号、微秒越界和1001ms浮点反例。
- 复用R370真实失败作为RED，按Astra计划不另跑RED。runner只更换轮号、plan pin及描述，核心定义AST归一比较相同。

## 实际验证

唯一命令R371:external_utc_green_01：**5 passed / 0 failed / 0 error / 0 skip，child与外层exit0**。精确nodeids与计划一致；原四个毫秒边界、过期决策、输入timestamp/checksum不变、24个新增边界和两个既有stale拒绝用例全部执行通过。

wrapper（含capture）1.300467秒；pytest JUnit时间1.045秒，stdout显示1.04秒及1项Starlette依赖弃用警告，不作为产品性能测量。child30秒、outer60秒、cleanup15秒和capture10秒上限保留。无超时、输出截断或缺失；source-before==source-after，捕获完整、子进程已回收。单槽SPENT，无重试。原始证据位于implementation/external_utc_green_01/，工具回执为implementation/transport-result.json。

## 验收边界及交付

仅验收UTC场景新鲜度边界与测试helper构造。未运行完整UTC/九节点T3、worker/DB/模型/物理或真实机械臂；未宣称性能改善或正式研究验收，原600秒标准不变。历史runner自检版本绑定不足等限制不升级。

当前local_temporal.py及copy/sha测试、嵌套工作区改动保持原样，不纳入本次提交。源身份记录包含这些在场但未交付的输入，因此精选证据不是完整远端复现包。提交范围为三个源码/测试路径、R369/R370/R371精选小证据及阶段记录。独立审查和Git核对另存本目录；冻结原件不改写。

独立最终审查：实际gpt-6-astra `/root/utc_final_review` 只读复核后判定READY，无Critical/Important/Minor；详见independent-review.json。Git只读远端预检TLS失败原件保存于remote-read-failure.json，限定传输接续交实际Astra R372，未修改产品或持久网络设置。
