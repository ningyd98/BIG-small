# 步骤48：实际 recorder 的传感器扰动来源

日期：2026-10-05。范围：SOFTWARE_ONLY / SOURCE_CONSISTENCY_ONLY；未运行新的动作实验或模型。

`VisualRawRecorderV3.capture` 原来直接调用 `capture_with_instances`，会绕过 pilot 的 `PerturbedCapture.capture`，使 SENSOR 分配实际收到干净帧。本次新增单帧 `transform_observation` 接口：相机只采一次，原始帧保留为 SOURCE，固定扰动后的帧单独登记为 ONLINE，策略仅收到派生输入。两帧共享实际相机采集区间、episode、物理步和相机来源，ONLINE 明确关联 source_acquisition_id。

固定 `rgbd.fixed-corruption.v1` recipe 保留六个原字段；recorder 使用既有 reader 的变换重放逐字节核验，并检查变换代码的固定来源。派生分母在调用变换前登记。变换异常、来源漂移或像素与 recipe 不一致时，保留缺失 ONLINE 记录并抛错，不以干净帧补位。变换不能推进物理或新增控制命令。历史 v2/v3 reader 和冻结原始资料没有改写。

四个新增回归先观察到合格 RED，涵盖正常固定变换、变换异常、错误来源和错误像素。独立源审查的相关套件为40 passed / 1 deselected，并确认实际调用顺序及失败分母；独审未运行实际 renderer/物理。root 合并套件中四项均通过，最后精确检查为4 passed / 0.70秒，日志见 [raw-transform-cpu.log](../t12-next-runtime-integration/raw-transform-cpu.log)。

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -m pytest -q tests/test_visual_raw_recorder_transform.py
```

源摘要见 [source-hashes.json](../t12-next-runtime-integration/source-hashes.json)，独立检查见 [independent-source-review.md](../t12-next-runtime-integration/independent-source-review.md)。本检查证明来源与固定扰动一致，不证明端侧几何、连续运动或物理质量；这些研究条件仍待真实证据。
