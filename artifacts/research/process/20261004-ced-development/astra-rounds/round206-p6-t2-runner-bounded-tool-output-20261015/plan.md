# R206 T2 工具输出上界修正计划

实际作者：gpt-6-astra（/root/astra_status_plan）。本轮为执行前静态问题；未发生 T2 测试或实际输出截断。

当前 runner 20824B/940d9df… 在完整结果中保留真实资源记录与文件索引，末尾却无界打印整个 outcome。仅由同一 Sol 修改 T2 输出分支：完整 result.json 先照旧写入，再显示有限标量与完整结果 path/bytes/SHA；可附原流/JUnit/summary 的 pin，不附数据正文。序列化后包含换行总计≤6000 UTF-8 字节；必要时降为最小完整 JSON pin 摘要，不截断 JSON。非 T2 原 print 表达式和返回逻辑保持。

- [ ] ROOT 全读本计划/当前输入，确认未运行和角色额度不变。
- [ ] Sol 独占保存完整 before，再仅改可选纯格式 helper 与末尾 T2/else print；新 diff/report 只写 R206。
- [ ] ROOT 全文/精确字节 diff 门检查；保留 R204 报告、旧 runner 与所有历史，不运行自测。
- [ ] 新 runner pin 作为有物理 before 的源码准备后继，返回原 R204 门禁。此计划不释放 RED/GREEN。

零新增执行、测试、静态、Git 或验证管线。两个 T2 原槽各0/1，argv/env/600秒/cleanup/资源校验和持久证据不变。真实输入 SHA、限定输出字段与具体文件路径见 plan.json；观察见 input-observation.json。遇新问题 STOP，T2/T12/native/formal 不晋升。

