# R387 Git 对象恢复步骤报告

实际 gpt-6-astra 计划先于任何恢复；plan.md、plan.json、input-audit.json 固定原始错误和输入 SHA256。空 loose 文件解释读取失败，产生原因 UNKNOWN，未诊断为磁盘或进程故障。

发现110个空节点，其中109个合法OID、1个旧tmp。原件、完整index、HEAD/refs/reflogs与59份可恢复payload先备份至本地 .git/r387-empty-object-recovery-20261102，再按精确路径可逆隔离。59个index引用blob以65条工作区路径的原字节恢复，OID/type/size/SHA256及loose解压内容全部吻合；50个非可达OID与1个临时节点仅保全隔离，没有伪造丢失载荷。私有备份及index不发布。

原生 reachability、connectivity 与完整 git fsck --full --no-progress 均退出0；full耗时553.284秒。dangling通知原样保留，不删除历史对象。全132657个index blob条目可读，1091个已暂存文件逐字节匹配。index SHA256保持1b2007611933a6e2d16d03316bf3eb50fc7965a2bf6c0bf8ed4ea23ad29c57a8，HEAD/refs/reflogs与有效旧loose对象元数据不变，源码和67项PASS证据不变，objects命名空间零空节点。recovery-summary.json accepted=true。

没有新产品修改、软件重测或真实运行。恢复仅完成此次可达数据与对象库完整性验收；空对象来源仍未知，不能称已根治。完整reachability stdout约18MB按精确路径留本地，哈希及理由见local-retention.json，其余小型原生输出随交付保留。完整raw/DB/权重/SDK边界沿用R383。
