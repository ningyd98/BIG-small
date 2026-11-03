# R400 静态检查补正结果

按实际Astra计划，明示7个self调用映射仅作用于修后NEW AST；六getter/helper签名、docstring后原body、公共委托逐项比较，内部list单独比较，其余类/模块结构完整比较。一次纯静态运行0.216秒通过，写入R399/preflight/product-comparison.json。

产品SHA `7d73669b175da19e278593b7db063740255a368a391915c59ea13001f5d93173`、测试SHA `9b81a9952ccac98502d32ecabd47093e5eedc4166d44000df824792221f9dfe1` 均未改。普通Lock、guard、SQL、事务保留；持锁调用图无残留公共wrapped reader边。只证明结构保留，不代替行为验收。原方向错误来自临时检查器，原完整inline文件未保留，记录如实说明。未增加R399行为或Git配额，1800秒时钟继续。
