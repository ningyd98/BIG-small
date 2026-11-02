# R392 离线 SQLite 副本显式只读 URI 修正

实际模型 gpt-6-astra；代理 /root/astra_r389_revalidate；2026-11-02T11:27:39.704938+00:00。

仅批准R390未执行诊断script唯一sqlite3.connect调用增加`uri=True`，独立静态审查通过后再使用R390原唯一分析配额。不授权任何数据库预探针、测试、浏览器重跑或产品修复。

## 证据与根因

独立静态审查Important由主执行器转交。script为11496字节，SHA256 `269c8af0eb50de149b8676f880428ebb840a0d42f5cc57af412e0b80be60427a`；AST确认唯一connect位于133行，仅显式timeout=1。现有代码将副本as_uri()+`?mode=ro`传入connect，却没有API URI opt-in。

本机/usr/bin/python3隔离读取sqlite3.connect.__text_signature__确认`uri=False`默认值；只导入stdlib，没有调用connect或导入诊断/产品模块。`query_only=ON`不能替代R390要求的打开时只读URI合同。不声称此前已执行错误连接或数据库被修改，也不猜测本机构建在默认参数下的实际URI行为。

规划时execution-start、diagnostic-result、input-freeze和forensic-copy均不存在；原DB未打开/复制由主执行器报告，非全主机open-file审计。

## 限定修改和验证

先在R392新inputs目录保存原script精确字节及原finding回执，再只把133行`timeout=1)`改成`timeout=1, uri=True)`。预期新字节11506，SHA256 `4f1037f47f757130b85d25e722732630d740ee76662add5d0b05fcda02053500`。路径、mode=ro、query_only、timeout、SQL、输入、复制/前后hash和cleanup逻辑均不变。

静态整文件精确替换比较、AST和hash验证后，须独立只读审查批准再执行。严禁为验证只读而创建样本DB、调用connect、执行database_copy/main或运行测试；本轮是修正显式接口选项，不需要数据库行为实验。

## 预算与独立工作

R392新增行为/分析/连接探针配额均0。R390原未使用的一次120秒分析+15秒清理/300秒墙钟保持，0retry；不修改其plan/inputs、不启动新计时或重置已开始计时。真正运行遇新失败仍保留证据交下一实际Astra计划。

当前workspace-write/networkrestricted/.gitreadonly。R378/R391的marker审查与R379独立asset工作可按原门继续，不因本script修正扩范围或等待；仍遵守单writer和source冻结。75项软件通过、browser未满足目标和正式研究边界均不升级。

完整原始代码行、接口默认值、SHA、精确替换及运行前置见plan.json。规划仅静态阅读/AST/stdlib接口检查，未执行数据库或测试。
