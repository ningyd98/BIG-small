# Phase 9 资产

`assets/manifest.yaml` 记录已提交的 Phase 9 参考 MJCF。

该资产使用 SI unit，面向确定性 MuJoCo CI 测试和 Phase 9 readiness 实验。大型第三方资产应下载到已忽略的 cache 目录，并在使用前写入 manifest。

2026-11-02 登记更新为 `phase9.reference.v3`，绑定当前已提交场景 `66a0e27047e5…`，模型字节未改。
旧 v2 的 `6a7938709366…` 来自 `a33b32af`；中间 `d2afb0d9` 为 `182fb2bc068b…`，当前 `d3472a56` 调整后的源为上述 `66a0…`。
这是项目 CI 参考模型的版本登记，不能作为官方 Franka 几何或物理验收证明；历史数据继续保留各自原始模型哈希和结果。
完整来源、历史差异与冻结原件见 [R379 来源收据](../artifacts/research/process/20261004-ced-development/astra-rounds/round379-scene-asset-manifest-consistency-20261101/inputs/provenance.json)。
