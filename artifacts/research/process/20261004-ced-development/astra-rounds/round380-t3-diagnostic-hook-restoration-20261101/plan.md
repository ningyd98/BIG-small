# R380 T3 诊断钩子作用域恢复计划

规划者为本次实际 gpt-6-astra（/root/astra_r380_r381_plans）。只读调查及计划落盘，尚未实施或运行测试。完整输入 bytes/SHA256、命令 argv、环境和验收以同目录 plan.json 为准。

## 原始问题与限定修复

R376-CR-1 的静态证明成立：内 scoped 把 invalidate 从 O 改 D，外 fault_scope 在 callback 再改 F；内先恢复 O、外后恢复 D，导致诊断闭包残留。原审查不是运行失败，需新增短真实 RED。R376 五个长节点已全部清理：4 PASS，commit_close 1 FAIL；旧 3600 秒预算不得复用。

最小修复使用 _b_t3_exercise 现有 configure(scoped,...) 把其内部 patch owner 交给 terminal callback。D 与 F 在同一个内部栈安装，撤销 F→D→O，在 helper 返回/抛错前恢复。禁止把诊断移到长期存活的外层来掩盖泄漏。可窄提取原诊断 installer/同 owner helper 供短合同直接调用，原 fault 语义不变。

只改 tests/test_operational_runtime_closure.py 的上述范围及新增 tests/test_operational_t3_diagnostic_contract.py。短合同必须运行真实 helper 和 MonkeyPatch，检验正常/异常退出 identity、同进程重复周期、target/non-target 委托一次、参数/返回值/原异常 identity 与 traceback、active exception 记录。替身只可用于诊断委托单元边界，不能冒充真实租约授权。长 confirm_timeout 保留真正 worker/broker 行为。

## 实施与验证顺序

1. 核对全部 pins、HEAD、权限、受保护文件和 R376 清理回执；获得串行源写入/测试独占。
2. 添加短合同，一次 60 秒 RED 必须在 identity 恢复处复现本根因；非预期错误立即停。
3. 最小 shared-owner 修改；保持原业务 fault/public/negative/SQL 断言，暂不修 commit_close。
4. 新短合同一次 GREEN 60 秒，原 fixture 合同一次 60 秒，然后原 confirm_timeout 一次 600 秒。每阶段另留 15 秒清理。精确命令、插件、markers 和 fresh basetemp 见 JSON。
5. 完成原 terminal timeout 全断言、同进程 identity 检查和清理后写步骤报告、独立审查，才允许 R381 更改同源。

新 R380 预算总墙钟 1200 秒，行为+清理名义 840 秒，无普通 retry，无其他长节点重跑。每次检查剩余完整 stage+15 秒预算。不可复跑 R376 runner 或重置其 round-start。可在新目录做旧 runner 的路径/计划/前序适配，但不修重复取消缺口；CR-2 仅静态风险且未发生，明确延期。

## 实际前提和边界

当前 workspace-write、network restricted、.git read-only；不得声称 full-access。现有 .venv、冻结 R235 guard/R373 tracker、真实 accepted_prerequisite、无 trace/profile、独立资源/DB/artifact 目录和 SIMULATION_RUNTIME_DB 缺省均须保留。不装依赖、不用网络/硬件，不并发其他测试或改源。受保护 temporal 文件、两份未跟踪测试和嵌套工作区不变。环境阻断不算产品 RED；仅实际允许升级且行为尚未启动时可一次替代，仍记入预算。

保留原始失败、stdout/stderr/JUnit、诊断、执行权限、argv/env、process identity、清理、源前后 pins 及每阶段步骤报告。验收只证明 CPU 诊断恢复与 confirm_timeout 原断言，commit_close、全流程和正式研究不随之通过。验证交付按明确路径提交推送并核对 SHA；若当前 Git/网络权限阻断，如实记录，不绕过。

补充执行器适配：已只读审核并固定 R377 implementation/bounded_stage.py 及 R376 terminal-handoff。允许用该原样通用 wrapper + 新 R380 spec 等价执行；调用方另行做计划 pins、前序结果、R235 accepted_prerequisite gates。prctl 若被实际环境拒绝即前置阻断。重复取消实现本轮不改、不做信号压力实验，也不声明 CR-2 已实验验证。当前 /proc 仅当前 PID namespace，结合历史逐阶段清理回执，不能宣称全主机扫描。
