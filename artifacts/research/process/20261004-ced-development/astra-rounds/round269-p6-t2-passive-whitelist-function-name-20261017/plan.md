# R269 — 被动观察白名单函数名单字段补充

实际作者 `/root/astra_status_plan`，实际模型 `gpt-6-astra`。仅计划，未实施或运行。

原 R268 `/passive_plugin/whitelist_frames/3` 写为 `_b_t2_wait_behind_event_lock`；冻结测试254018字节、SHA256 ed602dc9ba5c0b15af20fbe8ca4d9b58d2e4e45fac621dc6f5e5e2cd4a94e7d3 第4100行真实唯一声明为 `_b_t2_wait_for_event_lock`。原两次源读取 exit0，这是静态计划名称错误，不是测试失败。

本补充仅将该完整字符串中的 `_behind` 更正为 `_for`，作为后续plugin绑定的有效合同；R268 MD/JSON/observation和原始证据保持原字节，其他四个白名单条目、所有被动约束/argv/环境/两槽身份不变。既有Sol在ROOT接受后准备源码，独立runner准备可继续；无额外白名单或权限。

13项完整输入pin及真实检查见 input-observation.json。当前STATE/PHASE须由 R268 root-context-update.json 的 changes 精确解析：before.original对应完整archive/base64，当前逻辑文件对应after；不得旧代硬比当前或全path豁免。本轮不改角色或context。

读取695ad1实际exit0但因嵌套原件/base64展示过大而内部截断，未将该输出parse或声称全展示；完整原工具返回保留。5d770c仅输出实际状态/schema/三字段pin和两代映射，完整可见。

ROOT完整plan/input/native/source/argv/role门仍是诊断前置。新增运行、测试、静态、审查、Git和验证流水线均0；旧GREEN不退款，不重放。验收仅单字段绑定准确，不代表产品行为通过。冻结后STOP。
