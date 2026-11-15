# 阶段3新根因补充：恢复可选component_scene绑定

实际规划模型 **gpt-6-astra**；状态 **PLAN_ONLY_NOT_IMPLEMENTED**。仅计划，不修源码。原plan字节不变。

## 原始失败和根因

新隔离树 `offline-regression/first-case-01/result.json` 为 `KeyError: 'component_scene'`，栈指向新增离线模块build_frozen_worker里的 `assignment["component_scene"]`。构造尚未返回，未进入worker/backend或point回放。原日志仅保存结果摘要，未捕获完整argv，因此不伪造历史命令。原result、log和当下三个新增文件SHA/快照已追加保全；`first-case-01`禁止覆盖。

独立核查40份assignment、role-binding及worker/job原字节全部与先前计划绑定SHA一致：10个fixed均为 `FIXED_REGISTERED_SCENE`且assignment和role policy都**缺少**component_scene；15 development＋15 held-out均有完全相同的seeded mapping，seed/split与批次和job一致。原 `physical_component_scenario(seed, scene)`对40例纯配置验证通过，未启动backend。原make_worker_binding参数允许None，原run_worker_episode只在key存在时增加scene override。

根因是新离线组装器错误地把可选字段变成必填，不是V3缺失数据，也不是物理/相机问题。

## 限定修改与接口

只改计划内新增 `sol_molmo_offline_regression.py`及 `tests/test_sol_molmo_offline_regression.py`；第三个新CLI仅绑定SHA，本修复无需改。已有生产、guard AST、控制器、物理、评价器和阈值不变。

新增纯验证函数：

```python
def _validated_component_scene(case: FrozenCase) -> dict[str, Any] | None: ...
```

在build_frozen_worker传递make_worker_binding前调用它。读取均经FrozenCase.json校验，规则如下：

- seed必须为整数并与case.row和worker/job相等，scenario与job均为S01_NORMAL_STATIC。
- fixed split必须是FIXED_REGISTERED_SCENE、independent_random_scene严格False，assignment/历史role两边均没有component_scene key；返回None。不能把显式null、空字典或人为fixed mapping当原始缺key。
- development/held-out必须是SEEDED_COMPONENT_POSE_V1、independent_random_scene严格True，component_scene是dict且与role policy精确相同，seed/split吻合；调用原physical_component_scenario进行确定性配置校验。缺key/null/未知模式均拒绝。
- 把验证后的None/dict传给原make_worker_binding；**不要向fixed assignment补key或生成假scene**。传给run_worker_episode的assignment仍是原冻结内容。
- 版本2完整配置hash、source pinning、RGB/query/完整cloud请求匹配继续严格保持，不变更采集顺序、渲染、噪声、seed或计划。

## RED / GREEN步骤

1. 先加fixed缺key回归：实际planner/binding组装应成功且生成role policy无component_scene；当前代码应以原KeyError失败。只做构造，不调用plan/point/worker/backend。
2. 补development、held-out正对照及负例：fixed显式null/空/假dict，seeded缺key/null，assignment-role差异，seed/split/job不符，未知sampling及独立采样flag不符。所有不一致在组装执行前拒绝。
3. 实现上述纯验证与单一参数替换，不扩大其它代码范围。运行聚焦测试，记录完整RED/GREEN和修改前后SHA；对全部40例再做纯配置绑定核验，不启动仿真。
4. 原fixed构造GREEN后，才能用原CLI `case --case fixed-042001`恢复实际worker验证；输出选全新 `first-case-02`等目录，不覆盖首次失败。该次新闭环尚待运行，组装成功不能替代它。
5. 新失败仍原样保留并先交Astra；不削减原27名单。独立帧审计可以继续。

聚焦命令模板（cwd新隔离树，测试按上述名字前缀组织）：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -m pytest -p no:cacheprovider --basetemp=/tmp/v4-optional-scene-20261115 tests/test_sol_molmo_offline_regression.py -k 'component_scene or fixed_worker_binding' -q
```

## 验收边界

本补充仅纠正离线组装语义，禁止伪造fixed场景或放松历史绑定。不覆盖V3、first-case-01或任何原失败；不新增模型/网络调用。全仓600秒exit124及5个未定位F仍为未完成，不能因本小修复宣布全仓通过。输入SHA、40例核查和独立SHA256SUMS附后；原计划及其它补充字节不变。
