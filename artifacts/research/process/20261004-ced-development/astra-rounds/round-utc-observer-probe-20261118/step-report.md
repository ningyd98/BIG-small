# UTC 资源观察器对照

六项计划输入 SHA256 已核验。首轮探针在原 profile 下把未轮询的控制 worker 和真实轮询 worker 都计入构造记录，随后错误断言只构造一个 worker。退出 1 的脚本、日志和原资源文件完整保留。修正副本先从真实 poll 的 `worker_resource_id` 识别执行者，再对另一个已初始化 worker 单独核对无轮询、无 session、无 broker、无 heartbeat。此次探针计划只改该诊断副本。

| 后端 | 原观察器解码 CPU | 聚焦观察器解码 CPU | 运行时采样数（原 / 聚焦） |
| --- | ---: | ---: | ---: |
| Memory | 1.724 s | 0.649 s | 16 / 16 |
| SQLite | 1.714 s | 0.644 s | 16 / 16 |

四组均观察到两个不同的 worker、一个实际 poll、两台 OC1 clock、一个 session、一个 broker 和一个 heartbeat。线程、worker、session 与 issuer 对应，broker 和 heartbeat 均回收。所有资源关闭，清理错误均为空。聚焦组运行期间保留原 profiler，四组退出后均恢复既有观察状态。解码 SHA256 相同，均为 `e77d73d5746b6fea159ec310ff354968ade8bf72cff1614169a01855ce1653ef`。

工作树原始记录在 `experiments/results/phase9/real-harness-20261118/utc-codec-performance/`。首轮结果在 `observer-compare.log`。四组对照、原始资源与六项输入核验见 `observer-compare-v2.log`、`observer-compare-v2-resources/` 和 `observer-v2-input-verification.json`。四组对照在一轮执行中退出 0，使用 CPU 软件工厂。
