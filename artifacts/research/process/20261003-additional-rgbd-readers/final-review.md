# 新增 RGBD 读取器独立最终审查

审查日期：2026-10-03。分支：`codex/ubuntu-integrated-deploy`；HEAD：`a778fd1f31dd5ad0005812cd00fccb25896c5a1f`。

本次以工作区实际文件为准审查，未将未跟踪文件遗漏为“无 diff”。范围为计划 `docs/superpowers/plans/2026-10-03-additional-rgbd-readers.md` 指定的五个新模块、相关统一契约/loader/provider/部署改动、三份固定源 manifest、配置、新增三组测试及使用文档。没有修改生产代码，没有请求网络，没有重跑真实转换。

## 已确认的优点

- 三套读取器保留原始 uint16 深度、时间基准与源摘要。IndustryShapes 的 classic/test 未变成 train；MicroAGI 和 VINS 的未知 split 仍是 unknown。
- 单位和几何能力独立门禁：IndustryShapes 使用固定 README 的 mm 说明；MicroAGI 读取包内单位消息但不把日志时间当采集同步；VINS 不凭话题名称补造单位、内参或像素注册。65535 的排除明确是项目保守策略，原值保留。
- `model_input()` 与普通回放不包含 annotations 或 action，实例位姿留在显式 oracle 通道；回放保留源时间且仍标记 execution_verified=false。
- 源文件大小/摘要、逐帧记录身份、图像摘要与路径均有检查。转换使用 staging、逐次空间检查、完成清单及原子发布；完成标记的派生清单遭篡改时拒绝复用。
- 原生解析有文件/块/帧数/嵌套等上限；ROS 数值深度限制为 uint16，拒绝把 RGB8 可视化当深度。

## Critical

无。

## Important

当前未解决项：无。以下保留本次审查发现及修复前证据。

### I1（已修复并复核）：已完成转换的重复 deploy 仍被首次转换峰值误阻断

位置：`src/cloud_edge_robot_arm/datasets/external/prepared_deployment.py:50`（`local_budget`，特别是 56–59 行）；触发入口：`src/cloud_edge_robot_arm/datasets/external/deployment.py:746`。

`local_budget()` 始终把完整 `extraction_estimated_bytes` 加到保留空间门槛中，未检查同一计划是否已有经过清单校验的 COMPLETE。于是同一计划的 `extract` 可以返回 REUSED，但 `deploy` 在 plan 阶段就返回 BLOCKED_STORAGE，并将原先的 SELECTED_RGBD_VERIFIED 覆盖为 NOT_VERIFIED。这违反了重复部署复用已完成转换的预期；实际使用中完成转换本身就可能把剩余空间降到首次峰值门槛以下。

复现使用小型离线 fixture，不改真实数据或源代码：

```bash
.venv-data/bin/python - <<'PY'
import importlib.util
import tempfile
from pathlib import Path
from unittest.mock import patch
from collections import namedtuple

spec = importlib.util.spec_from_file_location(
    'additional_tests', 'tests/test_external_rgbd_additional_deployment.py'
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from cloud_edge_robot_arm.datasets.external.deployment import run_operation
from cloud_edge_robot_arm.datasets.external.prepared_deployment import local_budget

with tempfile.TemporaryDirectory() as folder:
    plan = module.local_plan(Path(folder))
    first = run_operation('deploy', plan, num_workers=0)
    reserve = plan['minimum_free_bytes']
    free = reserve + plan['extraction_estimated_bytes'] // 2
    Usage = namedtuple('Usage', 'total used free')
    with patch(
        'cloud_edge_robot_arm.datasets.external.prepared_deployment.shutil.disk_usage',
        return_value=Usage(10**9, 0, free),
    ):
        print({
            'first_deploy': first['verified_scope'],
            'free': free,
            'reserve': reserve,
            'full_conversion_estimate': plan['extraction_estimated_bytes'],
            'existing_extract': run_operation('extract', plan)['status'],
            'repeated_plan': local_budget(plan)['status'],
            'repeated_deploy': run_operation('deploy', plan, num_workers=0)['verified_scope'],
        })
PY
```

实际输出：

```text
{'first_deploy': 'SELECTED_RGBD_VERIFIED', 'free': 5000000, 'reserve': 0, 'full_conversion_estimate': 10000000, 'existing_extract': 'REUSED', 'repeated_plan': 'BLOCKED_STORAGE', 'repeated_deploy': 'NOT_VERIFIED'}
```

建议：预算规划先核实同一身份的完整派生成品；确认可复用时不再计入全量转换峰值，保留实际增量写入和磁盘余量门禁。新增完成后低于首次峰值门槛仍能重复部署的回归测试；同时保证损坏或身份不匹配的 COMPLETE 不能借复用分支绕过验证。

修复复核：`local_budget()` 仍先执行 `verify_existing()`，发现完成标记后调用 `_verify_raw_marker()` 核对计划身份及派生清单；只有成功后才将本轮转换峰值改为 0，并报告 `raw_reusable=true`。`minimum_free_bytes` 门槛保留。复核未修改生产代码或重跑真实转换。

审查者在修复后实际执行：

```text
.venv-data/bin/python -m pytest -q tests/test_external_rgbd_additional_deployment.py -k 'test_reused_raw_does_not_reserve_conversion_space_again or test_reuse_plan_does_not_trust_corrupted_raw_to_skip_space_gate'
2 passed, 10 deselected in 0.58s
```

两项测试分别验证：完整成品在低于首次峰值但高于余量时可 plan/deploy、低于余量时仍阻断；成品清单损坏时拒绝在 plan 中复用。I1 关闭。

## Minor

无额外阻断或建议项。

## 验证证据

审查者实际执行：

```text
.venv-data/bin/python -m pytest -q tests/test_external_rgbd_prepared.py tests/test_external_rgbd_native.py tests/test_external_rgbd_additional_deployment.py
30 passed in 1.51s
```

此外只读检查三套真实索引、转换报告，并各读取一个中间样本及普通回放观察，结果：

| 来源 | 索引对数 | split | 配对证据 | 抽读结果 |
|---|---:|---|---|---|
| IndustryShapes | 370 | test | 静态场景，不伪造时刻 | uint16；mm→m；GT/action 不进入普通观察 |
| MicroAGI01 | 108 | unknown | 108 RGB / 108 depth；最大日志时间差 4,918,000 ns；无未配对帧 | uint16；单位消息；采集同步未知 |
| VINS | 973 | unknown | 974 RGB / 973 depth；精确 header.stamp；未配对 RGB 原帧号 973 | uint16；depth_m=None；内参与像素注册未知 |

三个抽读样本的回放 timestamp 均与原 DatasetSample 一致，均无 action/GT 泄漏。此抽读不冒充审查者重新执行全帧验收。

主执行流程保存的日志另显示：`tests-external.log` 为 267 passed、2 skipped；`tests-regression.log` 为 172 passed、1 warning。上述全套结果是审查者读取现有日志，未重复运行；skip 不算 pass。

## 明确未评判的范围

- 通用 ROS/MCAP SDK 的全部格式、压缩算法或任意上游未来版本：本计划明确限定已固定的小包格式。
- 既有 external RGBD 模块的整体架构重构、此前完整 RoboMIND/GraspClutter 下载目标：不属于本次新增读取器范围。
- 网络直连下载链路、真实机械臂执行、VLM 效果、正式训练与完整上游基准：本轮只做本地离线转换和接口接入，未据此提升这些能力状态。
- 三套真实数据的全帧重新转换：主执行代理已执行并保存报告；本审查按授权只读检查并做样本抽读。

## 结论

**通过：当前 0 Critical、0 未解决 Important。** 本次发现的 I1 已修复并由同一审查者完成定向复核；数据语义、GT 隔离和所选真实范围的读取链路未发现其他重要问题。修复后的全量回归与真实验收仍由主执行流程保存最终结果，本结论不将未运行的检查计为通过。
