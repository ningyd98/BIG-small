# R454 RESET 转换来源完整性

原始短 RGB 真实触发旧转换器 ValueError；RED 恰1 FAIL，旧路径进入 guard。现在首步检查要求同源 ACQUISITION 为 COMPLETE/error=None，唯一 live/source-frame 均有相同观察身份，库存字节通过哈希核对。原 ABORTED、错误和 null 帧保持；已返回两个 pass 仍 exact=2。

GREEN 4 PASS，ruff/format/mypy 全通过；所有子进程回收、无漂移、无存活遗留。R453 的50节点不重跑。限定复核尚待最终回复。实际初始化/physics/render/模型/硬件均0；native UNKNOWN，正式验收 NOT_ACCEPTED。前置 shell 解释器选择失败及冻结 before 恢复单独记于 R456，不算测试失败或追加 RED。
