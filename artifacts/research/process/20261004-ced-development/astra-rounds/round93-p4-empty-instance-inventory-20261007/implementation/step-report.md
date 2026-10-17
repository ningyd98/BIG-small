# R93 P4 软件步骤报告

状态：AUTHOR_VERIFIED_PENDING_INDEPENDENT_REVIEW。仅schema/prefix reader/capture tests三个owned源；P3 R92与历史P4首败保持冻结。新actual/旧external reader/模型/网络/Git/子代理均0。

仅artifact inventory中完整匹配规范路径的instances.i32允许0B，默认source inventory仍必须正整数bytes。reader在pack前精确验证CAPTURE END、frozen auxiliary和source-frame元数据的IDs、signed32、长度、count、availability、labels和passes。所有其他原product AST和旧断言保留；fixture默认行为不变，opt-in经真实decorated cached capture。

唯一RED16：4预期FAIL/12PASS/0ERROR/SKIP，失败原件永久保留。formatter/proof/Ruff/formatcheck/mypy各一次exit0；单独命令逐项核退出，时序证据验证上一门结束后才开始下一门。独立formatter证明完整AST/comments/signatures等价，TypeIgnore先核tag及绑定再规范坐标（本三文件实际0条）。唯一GREEN31：31PASS/0FAIL/ERROR/SKIP，包括16新+15直接受影响旧case；没有63/R03/旧完整套件重跑。

CPU真实cached正链生成catalog/receipt，244events、120steps、3captures、0actions，IDs0/0/76800、instances0/0/307200B、availability false/false/true、passes2/2/3及SHA/source joins一致。它是CPU软件证据，不能替代真实运行/正式研究验收。

CPU分母：RED 645普通文件/158543794B；GREEN 1472普通文件/362140999B；总2117文件/520684793B，全部逐字复制保存并有完整manifest，原tmp未删。pytest链接原target记录，不冒称可移植远端包。JUnit是唯一case分母，不合并旧轮重跑。53输入复核，50保护输入字节不变，3为已批准owned delta；三source-after与当前源精确一致。

审查入口：source.diff、source-before/、semantic-after/、source-after/、source-freeze.json、scope-proof.py/json、registered-scope-recipe.json、各command-start/result/stdout/stderr、RED/GREEN.junit.xml、cached-cpu-evidence.json、RED/GREEN.cpu-manifest.json、finite-evidence-pins.json。产品源全部静止。不同作者独审、ROOT交付及后续单独真实资源授权尚未完成；最高author验证，不自行宣告review通过。formal false/native unavailable/UTC-SI unverified/future H-D与geometry unknown/calibration_groups0/OC3未验。
