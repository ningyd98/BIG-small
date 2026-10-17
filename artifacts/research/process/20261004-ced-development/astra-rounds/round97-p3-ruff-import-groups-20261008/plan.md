# R97 P3 Ruff import grouping — one-task recovery plan

**Status:** 实际 Astra 计划；仅规划，不是P3独审PASS。ROOT审核后由既有GPT-6.1-sol单写者实施。

**问题与原件：** R94已按该轮计划逐字排列新测试imports，唯一四阶段proof exit0、四负控正确拒绝；随后唯一Ruff exit1，仍报`tests/test_rgbd_role_models.py:1154` I001。作者立即停止；formatcheck/mypy/GREEN均未执行。原停止报告、proof、Ruff start/result/stdout/stderr与source freeze已读取并固定在本轮`input-pins.json`，旧失败不覆盖。

**真实诊断：** 本轮获授权且只执行一次`.venv/bin/python -m ruff check --select I --diff tests/test_rgbd_role_models.py`。原argv/cwd/时间/exit/stdout/stderr保存在`diagnostic.*`；exit1表示有建议diff，**不是GREEN或新增测试失败**。源前后SHA均`d8eee8f5d6b2991f5d0914556376e0d382b41da14c7d4545849970dd0766ff63`、52099B。实际diff仅将`from scripts.probe_rgbd_roles import read_role_config`移到PIL下一行，同一组；与后面的cloud_edge imports之间保留空行。

**根因：** `pyproject.toml`配置`[tool.ruff] src = ["src", "tests"]`，I规则已启用；本环境真实Ruff将scripts与PIL排在同一非first-party组，将cloud_edge置于first-party组。R94计划误把scripts放在cloud_edge组末；原R92又把它单独分组。不是产品语义问题，不靠再次猜测分组或修改Ruff配置解决。

## 唯一允许的源修改

仅`tests/test_rgbd_role_models.py::test_ced_max_reuses_successful_normalized_transport`的imports：

```python
    import io
    import struct
    from pathlib import Path

    from PIL import Image
    from scripts.probe_rgbd_roles import read_role_config

    from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
    from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
    from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository
    from cloud_edge_robot_arm.vision.messages import model_to_observation_pixel
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
```

所有import名称/alias/level及其余函数逐字不变。按本次真实diff做精确字节替换后，预期整个文件SHA256为`07a3ca1d8f0d9340cf7828817d474e08e07fd1196ba5cf7a90be91fc83619a9c`，bytes=52099；这是内存推导的候选hash，**不是已修改/已验证源**。其余四路径（ced_roles.yaml、role_models.py、planner.py、test_ced_runtime_binding.py）必须与R94冻结完全同字节。保留normalized_1000、Max think=False、compatible enable_thinking三项原产品变化；旧generic/Ollama、费用、绑定和旧断言不变。禁止全formatter、Ruff --fix、配置豁免或更多import整理。

## 单任务：精确修复与顺序验证

- [ ] ROOT确认单写者及本轮有限pins仍适用；独占创建`R97/implementation`与新basetemp，保存当前5源before。R94源、四阶段成功proof及四负控/失败Ruff原件保留复用，**不重新执行**。
- [ ] 仅应用上述两hunk diff；写新`implementation/prove-local-import.py`。证明读取R94冻结test与当前test，要求目标函数/精确旧block唯一，构造唯一允许的replacement后与当前**整个文件bytes**相等；其余4路径精确SHA/bytes相等。输出旧/新block位置、before/after hashes及借用的R94 proof SHA。无需再做整个旧AST回退或四负控；精确整文件替换证明保护所有旧断言/注释/签名。
- [ ] 复用R94已fail-closed的runner设计，新文件只改本轮命令allowlist/目录，保持逐条start/result/stdout/stderr与child exit传播。每项单独工具调用，前项必须真实exit0且原件齐全才下一项；启动即消费次数。
- [ ] 执行新局部proof **1次**；非零立即留证停止。
- [ ] 执行新Ruff check **1次**；若0再依次消费继承的formatcheck、mypy、GREEN **各1次**。不再执行diagnostic、不RED、不formatter、不collect-only、不额外GREEN。
- [ ] 冻结新5源/唯一local diff/P3完整差异、原命令/CPU原件/JUnit/分母/预算/步骤报告；交不同作者最终复核。初审PRELIMINARY与本Astra计划不冒充最终PASS。新非预期失败保留并交下一Astra，不连带停独立R93/P5工作。

## 命令与剩余额度

cwd仓库根，沿R94环境`PYTHONPATH=src:. MYPYPATH=src PYTHONDONTWRITEBYTECODE=1`。runner每次只接受一个名字。

1. `scope_proof`: `.venv/bin/python artifacts/research/process/20261004-ced-development/astra-rounds/round97-p3-ruff-import-groups-20261008/implementation/prove-local-import.py`
2. `ruff_check`: `.venv/bin/python -m ruff check src/cloud_edge_robot_arm/vision/role_models.py src/cloud_edge_robot_arm/vision/planner.py tests/test_rgbd_role_models.py tests/test_ced_runtime_binding.py`
3. `format_check`: `.venv/bin/python -m ruff format --check src/cloud_edge_robot_arm/vision/role_models.py src/cloud_edge_robot_arm/vision/planner.py tests/test_rgbd_role_models.py tests/test_ced_runtime_binding.py`
4. `mypy`: `.venv/bin/python -m mypy --follow-imports=silent src/cloud_edge_robot_arm/vision/role_models.py src/cloud_edge_robot_arm/vision/planner.py`
5. `GREEN`: `.venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=/tmp/bigsmall-t12-p3-r97-green tests/test_rgbd_role_models.py tests/test_ced_runtime_binding.py -k 'normalized or source_freeze or role_cost_delta or role' --junitxml=artifacts/research/process/20261004-ced-development/astra-rounds/round97-p3-ruff-import-groups-20261008/implementation/GREEN.junit.xml`

历史不清零：R92 RED1/formatter1/proof1/Ruff1；R94 proof1 PASS/Ruff1 FAIL。本计划新增local proof1+Ruff1；原formatcheck/mypy/GREEN各used0/remaining1继承，禁止额外重复。诊断diff1已用尽，独立标记非GREEN。成功要求5条实际exit0，GREEN独立JUnit覆盖原11新增case且记真实总unique，不预造通过数。

## 实际前置与验收边界

本轮无测试/formatter/Git/network/产品修改；只有上述授权只读诊断1次。实施者软件完成需原件完整+最终5源冻结+不同作者复核；不得用旧35真实call为当前source资格，最终4次角色probe仍等P8适用冻结与ROOT单独激活。all-sent/timeout/unknown bill null、source/setting变更拒绝和真正normalized正向wire仍须在继承GREEN中实际覆盖。本轮不改任何真实运行/正式验收边界。
