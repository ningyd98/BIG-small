# R259 父命令字典读取恢复计划

实际规划者：gpt-6-astra，/root/astra_status_plan。仅计划，等待 ROOT 门控。

## 问题与真实证据

R258 元数据读取 cce39b 实际 exit1，第一项 print 前调用字符串的 get，抛 AttributeError。其后账本及结算文件读取没有执行。完整 exact cmd、实际工具对象与独立流 null 已保留；失败原件不改、不重放。

本轮直接检查物理 R158 plan.json：commands 是 dict，command ID 是键；t2_red、t2_green 两值为 dict。此前 ROOT b61e8f 的正确 items() 读取保留在完整 evidence 文件。成功的 R258 inventory 实际对象也已物理保存。所有输入和完整历史副本的精确 SHA256 见 plan.json 与 input-observation.json。

## 最小恢复

只准备新的 proposed-command-map-reader.py。它严格要求字典，按两个已知键选取记录，拒绝 list 兼容或字段猜测；三个输入只读为 R158 plan 和当前两角色账本。原件身份仅比较 path、bytes、sha256。

- [ ] ROOT 全文审阅本计划、完整新源、输入 SHA、argv、有限环境及 shell transport。
- [ ] ROOT 创建空 implementation 目录并预约唯一元数据读取；作者不得自行执行。
- [ ] 按 JSON 精确 argv 执行一次；120 秒源码边界，外层125秒加5秒终止边界。只输出小型 pin 摘要，完整48KB以内结果独占保存。
- [ ] 立即保存完整 actual，再展示；仅可等待同 session。失败或不确定即 STOP，不重试，不补造独立 stdout/stderr。
- [ ] ROOT 核对实际结果后，才恢复尚未冻结的 R258 规划。

## 范围与验收

本轮没有产品、测试、helper、AST、编译、SQL、Git、网络或审查运行；不修改源、旧 runner、角色、STATE、PHASE。只新增一次纯元数据读取机会，不增加或重置任何验证槽。R251 原四槽仍 spent；父 t2_green 仍 HELD0/1。新元数据成功不构成 GREEN7、T2 或 T12 完成。

规划时 shape 输出附带历史 MD 导致展示 capped；不把该显示当完整 MD 审阅，也未解析截断文本。物理 JSON 类型、原 failure 和输入 pins 已直接核对。全 actual 仍保留。本计划不恢复或覆盖旧失败 stdout。
