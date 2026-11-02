# R381 commit_close 测试连接归属修复

R389实际Astra重新确认已交付checkpoint适用，旧80pins仅接收R380授权closure变化；原暂停回执已按字节保存。新线程合同RED2项明确复现跨线程ProgrammingError。唯一修复在真实COMMIT后，以当前线程新建并关闭独立观察连接；原writer、COMMIT、terminal谓词、故障及公共断言保持。

短GREEN2通过：非终态/foreign连接不触发；实际终态COMMIT关闭同writer；观察正常/查询错误两路径均在创建线程验证closed。原diagnostic+manifest6通过。原commit_close长节点一次通过（pytest240.74秒/外层241.577秒）：真实COMMIT后同writer已关闭，原生异常为Cannot operate on a closed database，job/attempt SUCCEEDED、lease released、public accepted=false、23份unconfirmed保留、无最终result.json，原完整断言完成。678资源、无cleanup异常、source/prerequisite/进程回收均满足。

全部测试已在原新轮预算内结束，之后环境续接仅读取冻结回执，未复跑或重置预算。完整证明与原件SHA见acceptance.json，独审见review。R376原始失败不改；累计目标恢复不等于全仓、真实模型/硬件或正式研究验收。完整raw/DB仍本地。
