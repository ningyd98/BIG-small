# R293：元数据 helper 长度证明恢复计划

实际 gpt-6-astra；仅计划，STOP 等 ROOT。R294 已接受弃用 `0b4263`，本轮不继续、修复或重放该规划构造器。

原作者 `702f9d exit1` 停在第 52 行合取断言。独立物理观察 `41f875 exit0` 确认 C486 的 `[5352:23031]` 与最终 runner 的 `[5348:23027]`，即唯一 `def _t2_pin` 至 `def author_bytes` 完整区段，均为 **17679 B**、SHA256 `8ef88c6906820c7a82a7c3bddfc2e60dc8335b4c8c3919228aa7938bf37b5af6`，逐字相同。第一项硬编码 17622 为假；原第二项被短路，独立观察十段拼接确实等于整源。十项 expected 等式位于原失败之前，ROOT 原 1341 源门也保留。没有产品或候选执行失败。

ROOT 接受后，唯一 Sol 在 R293 新路径持久准备 metadata finalizer。修正范围只有：三处错误长度声明采用真实锚点的 len/SHA/whole equality；把整源拼接改为独立保留断言；现有两个 after 原件改为读取核对，绝不覆盖；新报告明确 R293 恢复来源。不得删除十项 expected 等式或任何原 native、输入、模式、base64、C486/main/selector 约束。报告保留原实际 schema：`native` 为完整 N 对象、`native_pin` 为三字段身份，`runner_portions` 为十项完整 before/after 字节区间。不得留下未证实的 `whole17622bytesunchanged`。

完整原命令保存在 failure JSON，本轮没有提取 heredoc。未来作者若提取，必须证明 exact prefix/body/suffix 可重构原命令；实际终末无 LF，不 strip 或 normalize。新 source/candidate/native/diff/scope 先持久，ROOT 全文和输入/argv 门通过后，才一次 stdlib metadata 运行：程序 120s、外层 125s/TERM/5s kill，env-i、固定绝对 Python、stdout ≤6000 UTF8。完整 literal 见 plan.json。没有产品 import、AST、compile、测试、SQL、Git。

运行前四份报告必须全不存在，之后仅独占新建 `limited.diff`、`final-source-scope-proof.json`、`source-index.json`、`change-report.json`。已落盘的 target/after/candidate/native 保持。任何失败保全完整实际对象与部分输出后 STOP，不重试、不清理；不能把新成功记在旧失败上。

25 个必要输入的完整 path/bytes/SHA 位于 input-observation.json；before/manifest.json 保留原失败 JSON、两 target、两 after 的完整物理原件/base64/mode。不会重新审计已接受的 27/211/54DB/68 历史。新增唯一 metadata proof，不新增或重置 runtime/tests/static/review/Git 额度，不创建角色、不改 STATE/PHASE。

本轮只冻结文档与原始规划证据。即使日后 metadata proof 成功，也只是恢复源码报告，不能表示行为或 T2 完成，更不能自动放行 R289 runtime。
