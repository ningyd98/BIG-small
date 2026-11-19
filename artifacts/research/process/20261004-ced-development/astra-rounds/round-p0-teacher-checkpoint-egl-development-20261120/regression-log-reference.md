# 教师 EGL 短窗的回归日志输入定位

原计划中 checkpoint-regression.txt 所记 SHA256 5f1375fc… 是同一次 pytest 的私有原 stdout，现存于 cache/local-verification/20261119-worker-docs/teacher-timing-readonly/checkpoint-regression.raw.txt。提交 290ba377 所收公开版本 db19f818… 仅将第 7 行弃用提示中的应用虚拟环境绝对路径替换为 <application-venv>。恢复前缀即可重现原字节；两者都是 285 passed、1 个警告、100.63 秒，并无耗时或复验结局改变。

短窗可沿原计划继续。执行前将原第18项散列规则中的该日志与上述确切 raw 路径及原 SHA 配对，再核公开版本的 Git 对象和新 SHA。其余17个原输入逐件复核不变，全部产品源码、正式 claim 与软件运行条件原样保留。不得为其他文件建立泛化豁免，不需重新执行285项或再次授权。
