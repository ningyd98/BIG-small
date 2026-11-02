# R392 / R390 离线脚本静态审查

`APPROVED_R392_STATIC_FIX_AND_R390_SINGLE_OFFLINE_ATTEMPT`。Critical/Important/Minor均无；原URI Important已解决。允许按R390原未用额度执行一次离线诊断，仍待实际输出审查。

原script完整字节保存在R392 inputs，SHA269c8af…；当前SHA4f1037f…。整文件精确唯一替换为133行connect添加`uri=True`；去除此keyword后AST与原件相同。唯一SQLite连接对象是新forensic-copy下的file URI，保留`?mode=ro`、timeout1、query_only和finally close，没有使用immutable忽略WAL，也没有打开原DB。未以连接探针或测试验证此静态修正。

完整脚本已静态检查：stdlib-only；无产品、网络、Git、信号或subprocess调用；原件输入哈希门、DB/WAL/SHM闭合tuple复制/前后/最终哈希、10000行上限、progress handler和120秒monotonic deadline保留。zip仅读member不extractall，响应member有25MB上限；输出新建open-x。来源时间域与UNKNOWN/deadlock未证实边界保持，不能据分析代码预先认定19个case同根因。

R390原63pins全部当前相符；R392四pins仅script的批准变化，原件其他pins不变。审查时execution-start/input-freeze/diagnostic-result/forensic-copy均尚不存在。下一步须在ROOT以`/usr/bin/python3 -I`按原一次120秒分析、15秒清理、300秒墙钟执行，零重试；R392未新增分析/连接/测试额度，旧browser升级权限不扩散。

本席仅静态AST/哈希/文件阅读和写新review，诊断script/DB连接/产品导入/测试/网络/信号/Git写均0。实际副本一致性、查询结果及因果结论须等唯一运行后另审；任何新探针、性能/并发/等待或产品修改仍需下一实际Astra计划。软件/硬件/正式研究状态无升级。
