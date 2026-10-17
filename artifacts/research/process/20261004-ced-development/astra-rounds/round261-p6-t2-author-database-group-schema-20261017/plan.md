# R261：作者数据库分组 schema 处置计划

实际规划者：gpt-6-astra（/root/astra_status_plan）。只计划，STOP 等 ROOT 接受。

原6189f4实际exit1、KeyError:0。源码先打印字段为dict，随后把前三个list和该dict放入同一 `o[k][0]` 循环；没有按已知字段类型分派。冻结schema没有漂移。此前前三条首record已完整返回，DB组正文未打印；原完整invocation/actual/native保存事实保持不变，不冒称调用成功。

## 明确字段

`observation.retained_workspace_databases` 仅含两个命名组：

- `R242_R248`：list12，内部各record保留原R242/R248 provenance，共36 sidecars。
- `R251`：list18，保留R251 provenance，共54 sidecars。

每个record为 `{pin, sidecars, provenance}`；pin为path/bytes/sha256，sidecars为3条path/exists/is_symlink/pin记录，当前false/false/null。它们不能与旧35 missing/null、旧90 absent混为一类。

本轮读取全部30条结构一致，未重新读DB/SQL。完整字段形状表及30条来源记录在input-observation.json。特别区分：observation的parent_role_timepoint值为pin+selected；plan的相应摘要为pin+t2_red+t2_green。其余三个被错误合并循环的字段确为list；不再用统一first-record循环。

## 最小恢复与门

放弃整个失败optional viewer，不重放、不写替代聚合、不新增独立validator或执行槽。ROOT接受本计划后，同一Sol可继续既有R258 SOURCE_PREPARATION_ONLY，使用物理固定输入、精确组名及JSON内规范投影构造原已授权bridge；必要普通metadata读取仍属原范围。完整候选先持久，再native，之后仍由ROOT完整源/参数/差分/输入门审核。

未知shape必须停止，不能猜fallback。只输出有限scalar/key/type/count/pin摘要，不重复大账本/base64。身份仅比较path/bytes/SHA，原其他字段不删改。R260两selector的精确合同保持。

已成功G0和activation不改；不改产品/测试/原runner/角色/STATE/PHASE。父GREEN7仍0/1HELD，R251原四槽spent，fresh12/Git0不变。本轮零新运行/验证槽、无产品import/AST/compile/SQL/Git，不放行GREEN7。实际输入SHA、原失败、准确边界与前置见JSON。
