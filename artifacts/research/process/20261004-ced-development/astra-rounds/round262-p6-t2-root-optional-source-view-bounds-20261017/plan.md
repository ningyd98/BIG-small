# R262：弃用越界的可选源码展示器

实际计划作者：`/root/astra_status_plan`，模型 `gpt-6-astra`。仅计划，等待 ROOT 接受。

ROOT 可选展示器 `cd273f` 实际退出 1。最后请求一基闭区间 4937–4960；冻结文件实际 4956 行，输出已到 4956。首次越界为 n=4957、零基索引 4956；后续三次循环未执行。原因是逐行索引前未验证 EOF，属于元数据展示失败，不是产品或测试失败。独立 stdout/stderr 未提供，保持 null；完整原调用和实际输出保留在原件。

本轮直接弃用该可选 viewer：不修、不重放、不替代聚合、不增验证器或执行槽。原失败不能重标成功，也不能单独用于完整源码审阅或门通过结论。ROOT 已报告的独立成功源读 2b8632、195810 与冻结源码身份可继续作为原门的依据；本轮不冒称重新读取其物理回执。

唯一已有规划观察确认两输入的 bytes/SHA 与 4956 行 EOF。完整输入 pin 在 plan.json 和 input-observation.json。原失败：11259 B / 832bcc25b08addb7df3fa3a07f3e27ed47f73397c311b173fe769ba7821cb793；冻结测试：254018 B / ed602dc9ba5c0b15af20fbe8ca4d9b58d2e4e45fac621dc6f5e5e2cd4a94e7d3。

ROOT 全读本计划和原件、按 path/bytes/sha256 核输入后，可记录处置并继续既有必要 source/input/argv/evidence gates；独立 sole Sol 源码准备不受影响。原 R258 门和运行前置均不削弱。未来必要文本展示应先验证零基半开区间 `0 <= lo <= hi <= len(lines)`；一基闭区间应先验证 `1 <= first <= last <= len(lines)` 再转换。不静默截断、不猜缺失行；此规则不授予额外读取。

不改产品、夹具、原 runner、roles、STATE/PHASE、旧原件或任何预算；不运行产品、测试、导入、AST、编译、SQL、Git、探针或网络。新增执行/reader/validator/审查槽均为 0，父 R158.t2_green 仍 0/1 HELD。本轮仅恢复既有元数据工作资格，不释放运行、不宣称 GREEN7/T2/native/formal 完成。冻结后 STOP。
