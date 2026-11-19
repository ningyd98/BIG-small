# 开发批次规划期的两项 B0 输入更新

原计划 15 项中，13 项逐件 SHA 相符。ced_selection.yaml 仅从规划时已存在的池配置上增加真实 role_probe 路径；把这一行还原为 null 即得到原计划配置 SHA。prerequisite-readback.json 的规划时字节可按原 SHA 恢复。顶层新增 role probe 后的配置 SHA，fields.role_probe 新增 path、real_probe_available、real_probe_receipt_sha256、bound_role_bundle_hash，状态由 MISSING_QUALIFYING_PROBE 变为 READY_PRIVATE_ORIGINALS_PRESENT。移除这些变化后 JSON 与原件相同。a6603e83 的 Git 对象与两个新工作树文件逐字节相同。该提交的父提交包含更早的池状态，因此相对父提交的差异多于相对于本轮规划输入的差异。

仅在当前开发轮规划前置核验中用本清单明确接受上述两件的新摘要，继承原 13 项逐字节校验与原核验流程。若这两件再次变动或其余来源不匹配仍须拒绝。不修改被测核心、角色配置、实际历史/池、时间/安全阈值、批次 20+2、既有试次所有权及付费授权。恢复 stage 前核对本方案、生产 freeze/独立 wheel 与实际来源；按各自原入口继续，不为这两项规划材料增加运行授权。

按注册顺序独立执行。每个 slot 一次 BEGIN，不因超时、组件错误、环境中断或保护停止重复启动。已识别且证据完整的正常完成、已登记的保护停止在独立读回后登记其物理/组件结局并继续；未知保护签名、准入或资源状态、意外异常、缺失原件或不明退出保留并暂停受影响波次，依既有流程诊断，确认其余未启动槽可独立派发后继续。用户支付授权仍适用。原计划与旧/新 B0 进度和 commit 证据共同保留。
