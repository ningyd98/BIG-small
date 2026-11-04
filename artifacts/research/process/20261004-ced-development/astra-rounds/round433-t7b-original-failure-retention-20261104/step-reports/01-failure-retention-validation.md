# R433 失败原件逐行保留

实施前复核实际 Astra 计划25项输入、分支和HEAD。先新增组合反例，原reader上RED在“later original action failure was omitted”断言准确失败，完整正例通过，setup/teardown均通过。原日志保留。

随后只修改retain_failures方法体，每行检查对象及returned_result类型；畸形行按group/index/original及错误类型保留并继续扫描。既有失败判定及最终不完整判定保留。scope-proof证明方法外文本、旧fixture和旧测试不变，新测试从RED至GREEN字节不变。

GREEN为92项（既有91+新反例1），setup/call/teardown全部通过，无skip、source drift或残留进程，supervisor 43.54241257999092秒。Ruff、格式、mypy各一次60秒上限检查全部返回0。RED/GREEN原始样例及完整临时文件已逐文件比对保存本地，清单不冒充完整远端复现包。独立Astra最终审查单独记录。

软件验证不提供真实生产端或运行守卫资格；SOFTWARE_ONLY、UNAVAILABLE、NOT_PROVEN、UNKNOWN保持原值。
