# R563 函数限定实施步骤

按AST FunctionDef范围构造候选，写入前验证除_registry_check/_reservations外所有模块节点AST相同，_check_sources原字节不变；没有使用歧义全局替换。补全登记身份、claims/events/G*命名空间、预留全集和组/案只读额度核验。

原4项namespace RED转为4 passed（6.22s）；85项harness及既有接口/采集组合共317 passed（61.84s），scopedRuff与git diff --check通过。限定diff、范围JSON及原辅助失败保留。实际模型/生成/付费0，R558剩余3/20/3不变；原7案参数未改。
