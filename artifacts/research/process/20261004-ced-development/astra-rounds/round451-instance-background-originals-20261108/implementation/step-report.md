# R451 实施结果

F1 已由 CPU 原件图验证修复。唯一 RED 为预期 1 FAIL / 1 PASS；唯一 GREEN 为 2 PASS。

新夹具使用真实 NativeFullHorizonRecorder callback、原件写入和 reader.frame，局部软件 camera 保持生产者的 -1 背景及非负几何标签形状。背景字节未改造、未补造标签；缺失前景标签和未知负编号均拒绝。两 pass 隐式采集仍为空 instances。

全部监督子进程已回收，无源漂移、无残留进程。静态检查按计划留到 R453 统一执行。以上仅 SOFTWARE_ONLY，实际初始化、physics、render、模型和硬件调用均为 0；native UNKNOWN，正式研究未验收。精确前后 SHA 和差异见本目录 JSON/diff。
