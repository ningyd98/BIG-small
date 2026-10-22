# R314：R313 生成器计数接续

实际规划模型：`gpt-6-astra`；本轮只规划，未实施、未运行测试。

## 原始问题与根因

原始 JS 工具报 `Error: selector count R311`，在 `apply_patch` 前停止，native exit code 为 null；runner 和诊断输出均未创建。冻结模板的 `R311` 实际为 **6** 次，`r311` 为 **2** 次，模板与失败输入中保存的全文一致。错误来自元数据生成器要求 7 次的假设，不是产品或运行失败。只读核对回执：`f3c544`，exit 0。

## 唯一修正

在冻结 `failed_functions_exec_source` 中恰好替换一次：

```diff
-all("R311","R313",7);
+all("R311","R313",6);
```

其他生成器文本、所有选择器断言及输出路径保持原样。若临时 store 已失效，只允许把冻结输入的 `capture_source_input` 原字符串恢复为 `R313_capture_source`，逐字相同，不改 capture 逻辑。

## 实施前置与接续

1. ROOT 核对下列输入仍适用、runner 和诊断目录仍不存在；沿用实际 Sol 单写者及 ROOT 独立复核。
2. Sol 按上述唯一改动执行一次生成命令，保留完整修正 invocation、实际返回、映射和 runner diff。只继续 R313 原定 runner／diff／新轮 ledger 准备；不改旧 roles。
3. ROOT 按 R313 既定 source／argv／role 门复核后，继续原唯一诊断。R314 不直接放行运行，不重复已接受的现场保全或 sampler 审阅。

任何新 selector 失败、输入变化或意外已有输出立即停止相关准备，交回 Astra；不得试错重跑旧命令。

## 额度与验收边界

新增测试、运行槽均为 **0**。R313 `writer_memory_diagnostic` 仍是原一次额度，child 180s、outer 300s、retry 0；不得重置旧 SPENT。原六项通过和两项 budget 通过不重跑，writer_sqlite 保持原状态。本轮只确认生成器来源与元数据准备，不能宣称诊断完成、writer 通过或 T2 完成。

禁止更改 R313 冻结计划、已接受 sampler／archive、产品、测试、TTL、权限及原断言。本规划席位不执行 SQL、产品、测试或 Git 写操作。

## 输入 SHA256

| 文件 | 字节 | SHA256 |
|---|---:|---|
| `artifacts/research/process/20261004-ced-development/astra-rounds/round313-p6-t2-writer-crash-diagnosis-20261023/plan.json` | 15294 | `b651e87fce6370fed2e501a188be34e76e4f2bf002da84d1f0d5062308c5bbc0` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round313-p6-t2-writer-crash-diagnosis-20261023/implementation/r313_writer_stack.py` | 8340 | `bdebba39fc38face711dcd910771ab9c61c5cb0b8e35b5a38f7e7d55f7974608` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round313-p6-t2-writer-crash-diagnosis-20261023/reviews/original-scene-root-acceptance.json` | 78842 | `b3f4b4b7bec86adee8ce677fe8aee5e208951e86c0d05eed86fb71697a39397a` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round313-p6-t2-writer-crash-diagnosis-20261023/original-scene/manifest.json` | 188910 | `ed7d17c08baf78d42e6a55b12b98a36227dc9d020efed231e63db8e33a9a3785` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round313-p6-t2-writer-crash-diagnosis-20261023/reviews/sampler-source-native-actual.json` | 9399 | `40459158d580cfbbcf64bbe44dd3d5a6723e4c78284b19a08a04a74b147c8fdb` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round313-p6-t2-writer-crash-diagnosis-20261023/reviews/runner-generation-prewrite-failure.json` | 470 | `b114bb7819483e7349a1146ecdb24a1e0c135912010fa371eea6abe4f03f1b2d` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round313-p6-t2-writer-crash-diagnosis-20261023/reviews/runner-generation-prewrite-failure-input.json` | 30371 | `4ab3626c1d03fd15a26aef567f5e68b61aa4380f7c461971b81311f66e3fa398` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round313-p6-t2-writer-crash-diagnosis-20261023/reviews/prewrite-pause-pins-actual.json` | 2974 | `3f6817cc531e2011f2854aa95bac0edf9603711e07062ded646a33699ffedc48` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round311-p6-stage-b-continuation-20261023/implementation/run-evidence.py` | 15104 | `b3a940c0ef9e22afc2c99005fb6e6b628e2d06d99064952b5e6c2b21ed43abe3` |
