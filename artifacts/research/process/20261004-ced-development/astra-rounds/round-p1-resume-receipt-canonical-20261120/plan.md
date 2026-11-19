# JSON 审计回执的逐字节比较与续行

首次恢复在 development-01 的 Python 对象比较时退出，未发起第 12 槽，也未写新的 owner 补充回执。十份原 strict 回执逐字节 SHA 均与新鲜重算后使用原 canonical() 的 SHA 相同。两处物理安全字段在内存为 tuple、从 JSON 读回为 list。11 的完整补充回执 d1758e71… 是原 v1 的读回结果，含 v1 工具自身摘要，原包装与 unresolved 保留不变。

只新增 v2 外层研究入口。以哈希绑定并调用未经修改的原 owner runner、原 v1 supplemental_audit 和原 canonical（排序键、两空格缩进、允许 JSON 原生值、拒绝 NaN、末尾换行）。严格前驱与已存在的补充回执均用 **原已保存文件的实际字节 == canonical(新重新核验的结果)**；保留严格解析和原 accepted/recognized 判据。不得删除字段、重新序列化两边以覆盖旧文件格式/重复键差异，也不得用 v2 文件的 SHA 取代 v1 自指来源。原本缺席的 owner 补充件只按原 append-only 接口在同一锁下建立；第11组的内容须与 d1758e71… 完全一致。存在即逐字节复核；冲突、截断或非完整 BEGIN/END 继续拒绝。

先在离线入口完整核验 1–10 的旧 strict 及 11 的 supplemental（各自重新读实际原件），证实前缀计数/顺序和各归属；正例覆盖 list/tuple JSON 等价，负例至少覆盖不同 bool/int、不同数值/成员顺序或缺字段、旧文件字节或自指 SHA 被改、已存在补充件与新补充不一致、claim 缺 END 与重入。确认 v2 的 resume、audit/report 使用同一套 canonical 比对；严禁修改 v1 函数、冻结文件或为通过直接替换 runtime 模块。原记录逐项复核后即在原 exclusive_owner 锁内再次核有效前缀，沿用旧 FREEZE_SHA、normal launch_slot、22 项固定顺序、逐槽一次 BEGIN、终态/统计及资源规则。第 12 槽始可真实启动；既有 11 槽不得重跑。未来同根因由两处同一比较规则处理，未知差异仍停。保留 v1 首次退出及本轮新输出与原件哈希。
