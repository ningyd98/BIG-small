# R265：规划器 helper 切片边界处置

实际作者 `/root/astra_status_plan`，模型 `gpt-6-astra`。仅处置计划，待 ROOT 接受。

R264 元数据读取 `a6be9c` 实际 exit 1，失败于两个文本切片的相等断言，尚未写 observation 或计划。完整原调用和实际返回保持不变；独立 stdout/stderr 为 null。不是产品或测试失败。

本轮唯一必要字节观察 `f4b12f exit0` 已确认：

- 旧 runner `[1340:18962]` 是完整四 helper 块，17622 B，SHA `0a2601487ad75ccb1ae32872d40f340ab74ba799aa394f76855fea898687ffe4`。
- 新候选从 helper 起点到 `def map_bytes(` 的 `[4937:22560]` 为 17623 B，SHA `50394da29d6e99132ee752d3c0d943a7ee12a18ffa7b997852bf539e70e0ede4`。
- 前 17622 字节完全相同，仅多一个 LF（hex `0a`）；旧完整块在候选中恰好出现一次，位置4937。新块精确终点22559，分隔字节区间 `[22559:22560]`。候选与 live runner 完全相同。

因此，“完整旧块被精确复制”成立；“以不同下一函数为终点的两切片全等”不成立。弃用该失败断言，不重放、不修源码、不删空白、不归一化，不把原失败改成成功。

ROOT 接受后仅恢复 R264 规划。后续复制证明以原 runner 的真实17622字节块及其 SHA 为权威，在新候选唯一 helper 起点按该块长度逐字比较，并单独保留/报告周边分隔字节。上述位置只适用于当前 v1，不硬套未来候选；不用字符偏移切 UTF-8 bytes，也不以任意下一个函数推定块长度。R264 的 lifecycle 与 case-binding 两项合同缺口仍须其独立计划及 ROOT 门，不在此修正。

五个完整输入 pin 见 plan.json / input-observation.json，原始字节观察 actual 全量保留。ROOT 可正常全文/输入核验并原生接受本处置，无新 reader、validator、执行、审查或 Git 槽。产品、测试、冻结 helper、observer、角色、STATE/PHASE 均不改；父 GREEN7 双角色仍 0/1 HELD。冻结后 STOP，等待 ROOT 明确接受后再恢复 R264。
