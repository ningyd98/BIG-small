# R263：源码构造的 UTF-8 运行环境处置

实际作者 `/root/astra_status_plan`，模型 `gpt-6-astra`。仅计划，等待 ROOT 接受。

完整失败 JS 为 6120 B，不是完整 bridge 候选。它读取唯一外部 operand `r258_original_runner_construction_read_actual.actual.output` 后，在首个 `new TextEncoder().encode(original)` 抛出 V8 `ReferenceError`；边界提取、首个 store、header 模板求值及任何工具/文件写入均未到达。实际错误只有保全的文本，structured result、numeric exit、独立流保持 null。不能把 native `{}` 当作 exit 0。

根因为编排代码假设 functions.exec 提供未保证的 TextEncoder。现存 operand 已由同一作者原样归档为 `original-source-read-actual.json`，本轮确认其 `{invocation,actual}` 结构及 output 为字符串；UTF-8 31818 B / `13304d13376054c42441eda1060dcd926984498bafaea98243edf1c27f839808`，与物理原 runner 一致，无截断前缀。物理原 runner 的 `def _t2_pin(` 与 `def main()` 各唯一且顺序正确。全部八个输入完整 SHA 见 plan.json / input-observation.json。

ROOT 接受后的最小恢复：

1. 保留失败调用、错误、原生保存回执及 operand 原件，不重放旧调用。仅从固定物理原 runner / 已保全全文继续既有源码准备，不依赖易失 store。
2. 同一 Sol 可用受支持的普通 V8 字符串操作完成 R258 原 bridge；真正 UTF-8 字节数和 SHA 使用既定 Python 标准库物理 bytes 核验，不用 JS length 冒充字节数，不安装编码 API、不引入 standalone generator/validator。
3. 完整候选先在 workspace 独占持久保存，再进行 implementation native application。保留完整物理 before、候选、exact patch/真实返回、有限 diff、报告及各自 pin；任何已有目标不得覆盖。原四 helper 字节、R258 所有运行合同不变。
4. ROOT 仍须全文、输入、SHA、原生差分、argv、角色/CAS 门。这里只恢复 SOURCE_PREPARATION_ONLY，不预留或放行 t2_green。新失败立即保留并 STOP。

本轮不改产品、测试、夹具、旧 runner、R258 冻结计划/G0、roles、STATE/PHASE 或原件；不运行产品/测试/导入/AST/编译/SQL/Git/网络。新增运行、验证、审查槽均为 0，父 GREEN7 双角色仍 0/1 HELD，Git 0。后续源码准备成功不等于 GREEN7 或 T2 完成。冻结后 STOP。
