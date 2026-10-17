# R109 作者工具元数据恢复计划

实际 gpt-6-astra；PLANNED_PENDING_ROOT_ACTIVATION。合并记录两项独立作者工具失败，不称同一产品根因。只恢复 ROOT 只读核对和 Sol 已批准 R107 的脚本传输；不改变 R107 产品语义、三个 Python/三个 fixture 范围或剩余预算。

## 原件与根因

A. ROOT 工具 e382a4 exit 1：对 R108/recovery.glob('*') 每项无条件 read_bytes。首项 recovery/preflight 是目录，pathlib 报 `IsADirectoryError`（原 `<stdin>` line 5），在任何输出或写入前停止。完整原命令/合并输出/provenance 已存本轮 root-stop，原 UTC 未记录，不补造。

B. Sol 工具 e6dbe6 exit 1：原脚本 line 3 `script=r'''...` 内的 line 25 `helper='''def marker_cpu_inputs():` 提前闭合外层字符串，报 `SyntaxError: invalid syntax`。Python 解析阶段未执行任何语句，apply-semantic.py、产品/fixture 都未写。完整 8509 B 原工具输入和原输出在 R107/author-script-stop 保持原样。此计划只审传输根因，不将未运行脚本等同正确实现或新的产品验收。

R108 recovery/preflight/command-result.json 已证明 2026-10-07T20:01:04.407978+00:00→20:01:04.438609+00:00 exit 0。R107/implementation/input-check.json/source-before 已存在，不能再断言 implementation 不存在，也不重跑成功 preflight 或覆盖这些原件。停止收据表明十源仍 R106、三 fixture 未建、六验证 used=0、active=[]。

## 恢复步骤

1. ROOT 复读本计划与 13 个有限 pins，另存 R109 activation；原 R107/R108 计划和 activation 均不改。实施者在继续前核对最终十源停止 freeze/预算与限定目标当前状态，不能因本轮元数据恢复重置任何额度。
2. ROOT 只读收据检查优先显式读取 R108/recovery/preflight/command-result.json、同目录 stdout.txt/stderr.txt 和 R107/implementation/input-check.json。若只列 recovery 顶层，先 lstat/type 判断，仅普通文件可 read_bytes；目录只登记 DIRECTORY，不递归读取，不跟随符号链接或扩扫。缺席/类型异常明确报告，不能以空数据当成功。此步骤不再次执行 preflight；新核对记录追加到 R109/root-recovery/，不改原成功收据。
3. Sol 以 apply_patch 直接创建 R107/implementation/apply-semantic.py 的单层 Python 文本，不再用外层 Python raw 三引号包住整段源。保留内层 helper 字符串及原 R107 所需内容。可通过纯文本界标确认候选是原外层 raw 字符串计划承载的 body（外层 script=r 三引号起始到文件尾关闭界标），仅去掉传输包装；不 eval/exec 原失败脚本。不能扩大语义、路径或修改原失败原件。若选择直接产品 patch，同样仅按 R107 已批准变更和 source-before 精确上下文执行，并逐项记录，不能再执行重复应用脚本。
4. 为防同类解析错误，可对新作者脚本做至多一次 stdlib ast.parse 的纯语法检查，记录 argv/output/exit；不 import 产品、不执行脚本、不 py_compile 产品，不把它算产品 GREEN。随后只执行一次已核对的作者应用脚本（或执行单次直接 patch 路线，两者互斥）。若部分执行发生非零，保存真实部分状态并停，不整脚本重跑；不能重复 append/fixture 生成。
5. 按原 R107 保存精确语义差异/fixture SHA，继续原六验证各一次：import_sort、formatter、delta_fixture_proof、ruff、format_check、GREEN32。新预算没有增加；OC1/旧 RED/旧 CPU/proof/preflight 均不重跑。失败按 AGENTS 保存并新 Astra；不因本计划容许任意作者工具错误自动重试。

## 验收与边界

A 只证明 ROOT 正确读取已成功收据；B 只证明脚本传输不再提前闭合且按原授权恢复。两者都不是 P5 软件 PASS。R107 剩余六项各 1、actual/formal/Git/网络/子代理 0；本轮不新增产品测试。R109 原失败和恢复收据 local-only，不新增 Git 发布范围。步骤报告同时引用两个工具失败与 R108 成功，不改旧报告、不伪造原 stdout 或独立时间。本计划冻结后不再编辑；P6 v2 保持独立非激活材料。
