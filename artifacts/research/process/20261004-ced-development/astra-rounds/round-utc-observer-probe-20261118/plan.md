# Astra：UTC观察器对照探针极小修复

实际模型`gpt-6-astra`，PLANNED_NOT_FIXED。新`observer-compare.py`错误要求只构造1个worker；既有software_factory实际构造未poll控制worker和真poll worker。1次真实poll、2个时钟、各1个session/broker/heartbeat、0个cleanup错误与两个构造记录并不矛盾。错误在诊断计数及单元素解包，不授权改产品或原测试。6项因果输入SHA见JSON；已报告48项codec/safety/boundary通过，原600秒门仍未运行。

保留原失败脚本和日志，新建v2诊断副本：严格核实2个不同worker，按真实poll记录的resource_id识别执行者，控制worker不得有poll/会话资源；对真执行者保留issuer、session/broker/heartbeat关联、关闭、返回及profile恢复断言。运行memory/sqlite×原全帧/新边界4组A/B，核对资源语义、角色与canonical输出等价。通过后仅继续上一轮既定边界优化和原两节点合计600秒门；不扩大cache/生产worker范围。0GPU/API；新意外失败再交实际Astra，不把探针通过写成UTC门通过。
