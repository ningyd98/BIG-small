# 原100ms期限下的独立运行复核

低量同文件系统探查一次通过：8帧、32文件、4,928,135字节与原件相同，最大归档2.936ms。唯一新完整零API运行通过，worker和独立物理成功，稳定放置9.4417秒；778帧及全部恢复绑定复核，最大采样加IK91.403ms，未扣除被动诊断开销。源50项与4测试前后相同。

原LIFT2480超过100ms的失败保留，111.74ms间隙原因未确定。本次最大归档36.982ms与一次generation2 GC34.549ms重叠，只描述本次观测，不归因旧失败，不证明硬实时。实际模型/API均0。详见runtime-step-report.json、runtime-overhead.json及原始本地目录experiments/results/phase9/real-harness-20261118/native-archive-latency-validation。
