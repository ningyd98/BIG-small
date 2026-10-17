# R267：规划器 control_before 结构处置

实际作者 `/root/astra_status_plan`，模型 `gpt-6-astra`。仅计划，等待 ROOT 接受。

R266 普通元数据 assembler 的 `7c28c8` 实际 exit1、`KeyError: 'path'`。有限源码输出已完成，但随后构造读取列表时用 `control_before[0]['path']` 错取字段；后续 pin/role 循环未执行，也未写 observation、计划、源码或角色。完整调用/实际返回保留；独立 stdout/stderr null。该问题与父 GREEN7 两个真实失败和600秒超时无因果替代关系。

本轮仅两个明确输入的 bytes/hash/schema 读取 `0daf30 exit0` 确认：`control_before` 是 list2，每项恰为 `{original, archive, base64}`。逻辑历史身份取 `row['original']`，物理完整 before 取 `row['archive']`；二者各有 path/bytes/sha256。完整 base64 留在原 invocation，不打印。历史 original pin 不能硬比已合法更新的当前 logical role 文件；应通过其精确 archive/fullbefore 解析。身份只比较三个 pin 字段，不对异构整字典作相等断言。

处置为弃用失败 assembler，不修旧 reader、不重放、不替代聚合、不新增 validator。ROOT 全读计划/原件并核两个输入后可原生接受，随后仅恢复 R266 规划，复用前三次成功原读、已成功源码前缀及 ROOT 已有实际观察。以后必要路径选择明确区分原逻辑与物理归档，不再用错误表达式。R266 尚未冻结，不在本轮实施修复。

输入：失败原件89447 B / `9e99b7a4cb2b577059c7185cbf3a8655e4c7aba09e267a648aee4fcfd85a9825`；invocation690772 B / `b463b3c4699bc2bf3b65e808d3dbf81dd87c1032d92b9219420d6c09f5057a76`。完整绝对路径与实际回执见 JSON。

新增执行、reader、validator、产品/测试/静态/审查/Git 槽均0；不改源码、roles、STATE/PHASE或任何原件。父 GREEN7 原槽已消耗，不能恢复0/1或另名重跑；其实际 failure 结算另由 R266 规划。本轮不接受 GREEN7、不判断两次 DID NOT RAISE 与超时的根因、不宣称 T2 完成。冻结后 STOP。
