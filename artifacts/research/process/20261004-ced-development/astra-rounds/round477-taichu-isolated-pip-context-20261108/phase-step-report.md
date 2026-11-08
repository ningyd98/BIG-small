# R477 步骤报告

原 PYTHONPATH=src 与仓库 cwd 令 pip 读取项目 src/big_small.egg-info，触发缺失服务依赖及项目 Pillow 约束。原失败保留。同一 B 解释器清除 PYTHONPATH/PYTHONHOME、关闭用户 site、以模型缓存为 cwd 后，64 个锁定 distribution 全部来自 runtime-b site-packages，版本匹配，pip check/freeze 均 rc0；未增删或降级包。后续模型子进程使用相同清洁上下文；finalizer 的检查子进程也已限定此环境。该修复只验证纯模型闭包，项目产品继续原环境。
