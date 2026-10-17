# R260：ROOT 缺失原件 selector 结构处置计划

实际规划者：gpt-6-astra（/root/astra_status_plan）。仅冻结计划，等待 ROOT 审核；不执行纠正 gate。

ROOT 原 bbb8de 实际 exit1：把 literal `new_retained_databases.pin` 当 JSON 顶层键，触发 KeyError。此前 input_records 示例已打印；后续可选 context/schema/output 展示未到。完整 invocation/actual 与历史失败字节保留，原命令不重放，独立流未知不伪造。

实际读取两份固定 authority JSON 后，35条全部原始身份匹配：

- 29条 `input_records` → `container["input_records"][ordinal]`。
- 6条 `new_retained_databases.pin` → `container["new_retained_databases"][ordinal]["pin"]`。

两容器 pin、实际列表长度、每条 ordinal/完整原始identity/比较结果均在 input-observation.json。35路径当前仍缺失；其历史实测不被撤销，缺字节/null边界不被补造。只比较 path/bytes/sha256 三字段身份，其余原属性保留。

## 限定恢复

ROOT 在原 R258 必要120秒 stdlib G0/source/input/argv/evidence gate 内使用 plan.json 的精确两分支合同，不新增独立reader、恢复执行槽或验证链。不得generic dotted eval、list猜测兼容、略过任何row或递归扩历史。

实施 gate 前：完整新源物理保存，ROOT 全文/SHA/精确绝对解释器argv/cwd/finite env审核；先核authority文件完整pin，再严格dict/list/int ordinal边界及每条identity。每条原disposition与null字段保持；current出现文件或symlink、未知selector/身份差异即STOP。完整具名结果写新文件，stdout≤6000UTF8，不显示大容器/base64。

## 保持与验收

不改R258已冻结计划/观察/失败，不改产品/测试/旧脚本/角色/STATE/PHASE。R258 source preparation尚未开始；父GREEN7两角色仍0/1 HELD，原四槽spent、fresh12与Git0不变。ROOT接受本处置只恢复实现原必要gate的资格，不构成G0通过或产品授权。原gate另行全文门后才可执行；任何失败保全并停止。

所有输入SHA、失败原件与限定算法见 JSON；没有产品/测试/import/AST/compile/SQL/Git/网络执行。STOP。
