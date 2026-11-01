# R387 Git空对象保全与精确恢复计划

实际 **gpt-6-astra /root/astra_delivery_plan**，仅只读调查及本计划落盘。输入audit SHA256 `a9754228f28317a4bd8ed45e2a370ef9ad8bf792d97808cf81a0589596c9e775`。原Git错误、复现stdout/stderr及精确输入pins见plan.json；原toolchunk e1d443不重造为落盘原件。

## 已确认

110空节点中**109个合法OID、1个旧`c5/tmp_obj_DliCr9`临时文件**，不能全称Git对象。59个OID被index65路径引用，65份当前worktree字节全部重算`SHA1(b"blob "+length+b"\0"+payload)`精确等于所需OID，SHA256逐项冻结。全部110节点size/inode/mtime与intake一致，index SHA仍`1b2007611933a6e2d16d03316bf3eb50fc7965a2bf6c0bf8ed4ea23ad29c57a8`。

8个pack idx均没有这些109 OID，无alternates/shallow/commondir。`git rev-list --objects --all --reflog --missing=print`退出0、105029行、无missing、无空OID命中；因此其余**50合法OID＋1临时节点**不在现有refs/reflogs/index根中。此遍历不等于完整对象内容或不可达对象图健康；完整fsck仍待实施。

空loose文件足以解释读取失败；其产生原因仍UNKNOWN，不能凭空归因磁盘满或进程中断。后续IndexError是行政读取器未先处理Git失败；新验证器须检查native退出/响应后才解析，不能吞掉原错误。R386原67项已通过；无需重复产品测试。

## 精确实施顺序

- [ ] **冻结与备份。** 暂停所有Git写入，重核本轮pins、65 payload、HEAD/branch/index/refs/reflogs、110节点身份及无新空节点。私有新建`.git/r387-empty-object-recovery-20261102/`；完整index原bytes及HEAD/refs/reflogs快照仅存此处，index必须复制后SHA一致，绝不发布。110原空文件逐项copy保存bytes/path/stat/hash，先验证全部backup再移动任何节点。
- [ ] **可逆隔离。** 仅按intake精确110路径，逐项重查regular/non-symlink/size0/inode/mtime、备份存在、目标不存在，移到私有quarantine相同fanout/name。保留每步receipt，未知非空/漂移立即stop。绝不通配清理、触碰有效对象/pack/refs。50非index合法OID和1tmp仅保全隔离，不伪造其内容。
- [ ] **重建59个blob。** 当前无packed副本；若实施前发现新有效副本，须先验证其type/size/OID/content，不能仅凭idx名字信任。对每个已冻结payload用`git hash-object -w --stdin`写入真实原字节（subprocess stdin，避免shell及filter），必须返回精确原OID；随后cat-file校验blob类型、SHA256和完整OID，生成loose的解压header/payload也须相符。已有非空未知对象不能覆盖。期间不stage、不update-index、不write-tree。
- [ ] **全面验收。** 保存完整native输出，依次执行`git rev-list --objects --all --reflog --missing=print`、`git fsck --connectivity-only --no-progress`、**`git fsck --full --no-progress`**。保留默认index/refs/reflogs根，不用--no-reflogs、--lost-found。任何missing/corrupt/bad-link均停止并交新Astra；仅dangling/unreachable通知可如实记录，不清理。最大pack约56.4GB，full可能耗时，等待时正常更新，不以connectivity结果代替full。
- [ ] **不变量。** 实际objects命名空间零空文件（私有quarantine不在其中）；110逐项处置齐全；全index对象可读，160000 gitlink按原OID及原嵌套关系核对，不误当superproject丢失blob。65恢复路径和全部1091已stage交付文件与冻结worktree匹配。index原bytes/SHA、HEAD/符号HEAD、refs/reflogs及有效旧对象不变；源与67项证据pins不变；全部原件和backup完好。
- [ ] **恢复交付。** 写R387步骤报告，区分原损坏、59恢复、50非可达OID＋1临时节点隔离、完整fsck结果和产生原因未知。全部通过后才继续原R383精确stage审计/正常checkpoint commit/push及三SHA核验。私有index/quarantine不入提交；小型安全报告/原失败日志仍经原secret/path/size门槛。

## 停止边界

非空或身份漂移、新空节点、哈希不匹配、不可恢复的可达对象、fsck新损坏、HEAD/index/refs漂移均保留现场并转下一实际Astra，不扩修。中断后按已记录每对象状态复核，不盲目重放；不自动用旧空文件覆盖已恢复的有效对象。禁reset/clean/gc/prune/rebase/amend/force、删除对象/历史、改产品或重跑67项。计划不扩大研究或Git交付范围。
