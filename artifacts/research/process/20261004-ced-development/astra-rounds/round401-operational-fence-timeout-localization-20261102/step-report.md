# R401 分段权限验证

原combined180秒TIMEOUT保留。最终原memory节点138.021秒call+teardown PASS；SQL successor自然1 passed139.94秒，进程140.4896秒，R235accepted/0signals/reaped/source drift0；15秒原栈位于local_temporal JSON decode/semantic/adopt_plan，而非原SQLite215同锁等待，不能单凭单栈推断性能根因。

其余原3节点共5实例：4 passed、1 failed。test_foreign_thread_has_no_owner_context 在captured→reserve_capture初始transition义务校验前置失败，尚未创建foreign thread；原栈/JUnit保留，交实际Astra R403。不能把guard聚合标为通过，不能把原combined TIMEOUT重写。

原产品和guard测试字节均保持。R402后来只改新native验收身份字段，不能声称整个新test文件与原guard快照相同。预算/配额未重置。
