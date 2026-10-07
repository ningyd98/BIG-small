# R92 P3 Compatible Thinking Wire Implementation Plan

> **For agentic workers:** ROOT 按既有用户授权交 GPT-6.1-sol，实施者使用 superpowers:executing-plans；本轮规划不实施、不派子代理、不操作 Git。先等 P4 actual/readout 终态及 ROOT 派单。

**Goal:** 使当前 Max 角色在真实 compatible 请求字节中保留成功配置 `enable_thinking=false`，并完成原 Task 3 尚未消费的软件验证。

**Architecture:** 复用现有 `ModelConfigSnapshot.generation_parameters["think"]` 的严格 bool 验证与冻结/hash；Max 角色工厂显式设置 False，compatible 序列化仅在该键存在时映射为 `enable_thinking`。不增加无调用者消费的 YAML 字段、不改 resolver schema。

**Tech Stack:** Python 3.12、既有 urllib/Pydantic/YAML、pytest/Ruff/mypy，全部使用 `.venv/bin/python`。

**Spec:** `docs/superpowers/plans/2026-10-07-t12-sol-execution.md` Task 3；原 Astra 总计划及 P3 dispatch/brief 见下方有限输入 pins。

## 原件与根因

P3 当前停点为 `NEEDS_ASTRA_P3_COMPATIBLE_WIRE_THINKING_FIELD`，是实际公开 request 与源码的静态反例，**没有执行失败命令、RED 或新云端请求**。报告 JSON SHA `f8f7a68d63b8ceffff6d305f078a6840248130e5d95e2d7d6aa221d184afa732`。case07 request SHA `17635c77af0d589ab4c607b4e52b609c05b285e6433771239a950690f4010077`；本次只读取该单份公开 JSON，复核两图 PNG 实为320×240、temperature0/max_tokens512/enable_thinking false，未复制完整请求。旧 receipt 的 HTTP200/请求 SHA、35调用及独立 valid=true仍是历史证据。

当前 planner SHA `0f1f31392c84f8db32535f6908e1d3e2bdae2d2265b7afec7e12a5492af96f66`，`_request_visual` compatible 分支只有 model/messages/temperature/max_tokens/response_format；角色工厂只填 temperature/num_predict。内部合法 `think` bool 已存在，两端缺失同属生成参数到 wire 合同不完整。原四源范围不能实现真实 wire，因此本轮仅扩一条生产路径 planner.py。

## 限定范围与接口

1. `configs/research/ced_roles.yaml`：仅 cloud.coordinate_system `pixel → normalized_1000`，保留320×240、grasp v2及其他配置。
2. `src/cloud_edge_robot_arm/vision/role_models.py::resolve_cloud_role`：已有 generation_parameters literal 加 `"think": False`。该工厂已限制启用的 compatible Max/合法日期版本；因此是 Max 角色明确成功策略，且进入既有 snapshot/evidence/request_config_hash。profile temperature/max_tokens 继续取真实 profile，不能把777等合法值静默改成512；T12后续 actual 的公开选定 profile 必须核对0/512。不写用户 profile，不读取秘密存储。
3. **新增范围** `src/cloud_edge_robot_arm/vision/planner.py::RGBDPlannerAdapter._request_visual`：仅 compatible 已有 body 构造之后、path赋值之前增加：

```python
if "think" in generation:
    body["enable_thinking"] = generation["think"]
```

4. `tests/test_rgbd_role_models.py`、`tests/test_ced_runtime_binding.py`：仅新增下面六个命名函数及必要局部 fixture/import。禁止删除/削弱旧断言、改全局 helper 行为。

任何 compatible 显式给合法 think 即 opt-in 序列化该扩展；无该键或无 snapshot 时不发送此字段，绝不通过默认 False 强加其他 API。Ollama 的 think/options、paid guard、其余 planner 方法和网络/成本/UTC逻辑语义保持。无需改 model_resolver.py、messages.py、runtime_binding.py、cost_ledger.py 或 probe CLI。

## Review Focus 与命名 CPU 验证

用例仅替换 `urllib.request.build_opener` 的外部 open 边界；必须执行真实工厂/消息转换/_request_visual/_post/Request 序列化。捕获 `request.data` 而非伪造 body、报告 flag 或 mock `_post`。不连接网络、不运行 MuJoCo、模型或真实相机。具体各项断言和节点在 plan.json `tests`，节点/分母如下。

| 节点（原 Task3 三项保留） | cases | 原源预期 | 改后 |
|---|---:|---|---|
| test_ced_max_reuses_successful_normalized_transport | 1 | FAIL：配置 pixel | PASS |
| test_existing_max_success_is_not_new_source_freeze | 1 | PASS控制 | PASS |
| test_role_cost_delta_preserves_all_sent_requests | 1 | PASS控制 | PASS |
| test_role_compatible_thinking_reaches_serialized_request[false/true] | 2 | 两项缺真实 enable_thinking 的断言 FAIL | PASS |
| test_role_thinking_provider_controls[compatible_without_setting/compatible_without_snapshot/ollama_default/ollama_true/paid_disabled] | 5 | PASS控制 | PASS |
| test_role_thinking_change_invalidates_request_binding | 1 | PASS控制 | PASS |

一次 RED 预期 **11 unique = 3 FAIL + 8 PASS，0error/skip，exit1**，不是把控制项预登记必失败。具体重点：

- 新 synthetic CPU RGBDObservation 需真实生成320×240 RGB PNG/metric depth；现有 observation_payload只有2×2且实现不放大，不能拿它冒称320×240。读取真实 YAML传入工厂；临时 profile0/512，断言真实 request model/两个不同320×240PNG/normalized prompt与既有坐标解码/temperature0/max_tokens512/enable_thinking is False/response_format及请求hash。grasp维持v2；mock回复明确仅软件。
- false/true 两参数直接合法 snapshot，独立穿透真实序列化，以免 YAML 首个断言遮蔽 wire 根因。严格 bool值无转换，兼容请求无内部 think 键，snapshot不被pop修改。
- generic无设置、无snapshot保持原五键；Ollama default/true保留旧协议，paid_disabled在任何发包前拒绝。其他provider不被强加字段。
- 旧成功不能豁免真实 RoleRuntimeBinding 源变化拒绝；think False→True也必须改变 request hash并被已有runtime绑定拒绝。只变测试临时源，不改全局源。
- 成本控制通过真实 _post/CostLedger做三次模拟sent（两次 TimeoutError后一次成功），检查不同attempt ID、3请求与真实字节和、TIMEOUT/TIMEOUT/SUCCESS、远端未知金额None；不发实际请求、不添加自动retry，不把规则计为模型。

## Task 1：同一根因，一次有界修复

- [ ] ROOT确认 P4真实prefix和公共readout终态，再校验全部有限pins与本MD/hash链接、原P3零消费台账、唯一Sol写者；不要求全仓quiet，不pin活动OC2/RW1/P4总表。不编造尚未生成的P4终态hash。
- [ ] 独占创建 R92/implementation 与新basetemp，保存五源before；原P3停点、source-before/after、failure/报告全部保留，续报及新差异写R92，不覆盖旧P3 role-delta。
- [ ] 写上述11case，单次RED，原输出/命令/JUnit完整保存；只允许预期3fail8pass继续。
- [ ] 做上面三项产品语义变更；执行一次owned Ruff formatter纯格式整理，保存 semantic-after与format-after。
- [ ] AST(type_comments=True)证明去除授权factory键、compatible条件与新增测试后其余语义不变；独立证明formatter前后完整AST/comments/signatures相同；YAML解析差异只有坐标字段。整个业务前后并不等价，必须明确三项意图变化。
- [ ] 按下列次数执行静态和原Task3 owned GREEN，各仅一次；任何新非预期失败保留后停止交Astra，不追加修复/重跑。
- [ ] 冻结source-after、完整diff、逐命令原件/节点与CPU模拟请求分母、原件pins及步骤报告；交不同作者独审。未经审查及ROOT实际前置不晋升真实或正式验收，不自行Git。

## 精确命令和剩余额度

以下 cwd 均为仓库根，环境 `PYTHONPATH=src:. MYPYPATH=src PYTHONDONTWRITEBYTECODE=1`。所有argv原样见plan.json，不通过收集测试另加collect-only。

**RED：最多1次。**

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=/tmp/bigsmall-t12-p3-r92-red tests/test_rgbd_role_models.py::test_ced_max_reuses_successful_normalized_transport tests/test_ced_runtime_binding.py::test_existing_max_success_is_not_new_source_freeze tests/test_rgbd_role_models.py::test_role_cost_delta_preserves_all_sent_requests tests/test_rgbd_role_models.py::test_role_compatible_thinking_reaches_serialized_request tests/test_rgbd_role_models.py::test_role_thinking_provider_controls tests/test_ced_runtime_binding.py::test_role_thinking_change_invalidates_request_binding --junitxml=artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/RED.junit.xml
```

**formatter：最多1次。**

```bash
.venv/bin/python -m ruff format src/cloud_edge_robot_arm/vision/role_models.py src/cloud_edge_robot_arm/vision/planner.py tests/test_rgbd_role_models.py tests/test_ced_runtime_binding.py
```

**ruff_check：最多1次。**

```bash
.venv/bin/python -m ruff check src/cloud_edge_robot_arm/vision/role_models.py src/cloud_edge_robot_arm/vision/planner.py tests/test_rgbd_role_models.py tests/test_ced_runtime_binding.py
```

**format_check：最多1次。**

```bash
.venv/bin/python -m ruff format --check src/cloud_edge_robot_arm/vision/role_models.py src/cloud_edge_robot_arm/vision/planner.py tests/test_rgbd_role_models.py tests/test_ced_runtime_binding.py
```

**mypy：最多1次。**

```bash
.venv/bin/python -m mypy --follow-imports=silent src/cloud_edge_robot_arm/vision/role_models.py src/cloud_edge_robot_arm/vision/planner.py
```

**GREEN：最多1次。**

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=/tmp/bigsmall-t12-p3-r92-green tests/test_rgbd_role_models.py tests/test_ced_runtime_binding.py -k 'normalized or source_freeze or role_cost_delta or role' --junitxml=artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/GREEN.junit.xml
```

P3原RED/GREEN/formatter/Ruff/formatcheck/mypy全部0；现在各剩1，不重置旧任务、不另加完整GREEN。首次GREEN含原两文件原选择式和11新增case（名称带role/normalized/source_freeze/cost）；通过分母以真实JUnit去重，不预造总数。changed production的mypy仅两目标一次，不声称历史已通过。formatter只处理四个owned Python文件，独立AST纯格式证明；Ruff禁止 --fix，发现超出授权语义的问题走新Astra。不能重复35call、旧P1/P2/OC2/RW1 suites。

## 实际前置与验收界

本计划网络/model/render/physics/Git均0，不授权当前4次真实probe。最终真实probe仍等P8所有受影响source冻结、软件与独审通过、ROOT单独核对合法选定profile的公开0/512与secret引用可用，再按现行合同cold+3warm=4；已有现行合格原件先复用。旧35调用不当新source资格，grasp v1→v2不继承旧资格，权重未知保持null。所有sent含timeout/retry计入成本，unknown bill null不变。软件PASS、独审、actual role/source、physical与formal分栏；本轮CPU不等于正式研究通过。

Astra 本轮已实际收到规划派单并生成这两文件；记录requested_model=gpt-6-astra，未冒称能独立核验服务端模型身份。规划仅标准库读/解析/哈希与写计划：产品/测试修改0，测试/静态运行0，网络0，secret读取0，Git0，子代理0。

## 有限输入 SHA256

全部以下值来自本次实际读取字节。plan.json `input_pins`同表并附bytes；执行前每项复核。

| path | SHA256 |
|---|---|
| `AGENTS.md` | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` |
| `pyproject.toml` | `b2bf5c4042d568eaf9def415ae7b2f08f0fa541a01f970b7e68e6d950035bb6c` |
| `docs/superpowers/plans/2026-10-07-t12-sol-execution.md` | `5a1358f0397edbc54c301edb63e934b1d2ba15ee79d64c9ae36248749b6af0f8` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/t12-convergence-repair-20261006/plan.md` | `d5c3d6b1ffa6f51f3a2785af5f5ab9fedf506f81080a3bea311644fff7c70219` |
| `configs/research/ced_roles.yaml` | `54cfa5787f81f284d999703e4fd5da47ae59c5d53784f8636393ab4d2e759f22` |
| `src/cloud_edge_robot_arm/vision/role_models.py` | `13b59bd3679cd4893de60431e1392ec495bc1a964aa8493536defc435d91c0c9` |
| `src/cloud_edge_robot_arm/vision/planner.py` | `0f1f31392c84f8db32535f6908e1d3e2bdae2d2265b7afec7e12a5492af96f66` |
| `tests/test_rgbd_role_models.py` | `98ef1e0d28ca6bc6a6046e715b6654f10754e9bb1a930e8adf2ab582cb284067` |
| `tests/test_ced_runtime_binding.py` | `ebdff387edaae902726042239c87cc4ae5533b9493e61d26a4d2b9e2f44fe48a` |
| `src/cloud_edge_robot_arm/vision/model_resolver.py` | `2185ef00005d2c026ba1dc528e202b7eec05cb90cc2ee5635e6bc9ffb6523cae` |
| `src/cloud_edge_robot_arm/vision/messages.py` | `f60868e4db77ac103d94d2b18b769612ae19b54bed60f79fbfe5a2846c5e30a3` |
| `src/cloud_edge_robot_arm/vision/runtime_binding.py` | `d6e6c7a42cc57a2ef0aa2e205c6499fe84244be53c8ca91241137265d2fc69dc` |
| `src/cloud_edge_robot_arm/research/cost_ledger.py` | `64a92563c79f0ae04c07eec974213d28676518a062c08ccfde349afba840edd9` |
| `scripts/probe_rgbd_roles.py` | `471b03ea46058bb2aff8fe7d839a4d2b7947110d944fc5650afe608a3a004a76` |
| `scripts/probe_rgbd_model.py` | `a6d8f61e6c278a2b06ae9a6abdcbb9d17dcee73666aa6735ee6ad0a6653dab94` |
| `tests/test_rgbd_observations.py` | `333b1837cff77bdfce9344cf40f7617064570e1e3c08c881d6942316e9a250fe` |
| `artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/p3-executor-brief.md` | `5d6bf7e122b124c720df5efb002d68c3abb6709cce3f7e7a3cd4e0e4668eb07e` |
| `artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/p3-dispatch.json` | `78fa5729f2cf5d6b94d87bc8de5f98345fa8a4d866492f6ab55a80f9d6525582` |
| `artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/p3-prepared-inputs.json` | `987d9d984edf8250ef6bd30d3dcfedde571a92dba175fb6140d2ccb5d2b41afa` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P3/step-report.md` | `6f7f192e1866314a0935159594d602b2ec8e3bf4904841097814f0bb139e3a53` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P3/step-report.json` | `f8f7a68d63b8ceffff6d305f078a6840248130e5d95e2d7d6aa221d184afa732` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P3/failure-receipt.json` | `3ec209bef777015c5b89e7f5ea1adde6e06e18a16a2b37194324e75c815beb5c` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P3/role-delta.json` | `d4c66f36ab1cc879e4b4502eebb0b84007a090239e9256fe7f1f4b3730b2c8ca` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P3/original-success-public-evidence.json` | `90b87654e9543dfe3db2e9b64c993339ad5f4c11fc01adab1a82f152b7a0f555` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P3/planner-request-visual-source.txt` | `22f4379b9484a4d33a205b829fb66070ddf022aeb01243c3ca2c0403f2f4ff4c` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P3/source-freeze.json` | `a1dbfc21132d62fd22f7855fd4ed810ef69abb3d847a4352a653d61c26d1b7a8` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P3/delivery-paths.txt` | `02594e48fbc0137ad461090715704c1a997be39394b3d73b3122fcd7f128f025` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P3/report-evidence-pins.json` | `550e5e9683d427c792c619dcd98842a8132f840a8da53a4e21d4b9cc51c84872` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P3/input-check.json` | `d9f8c6c63ae0888975e460e1fa68d6d4b306bf4e8b2d3bf13f08ca779ebe0685` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P3/input-check-after.json` | `942c355827b8e065715b19043399021da737c9f3418131fc496ceccb9d915533` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P3/dispatch-pins.json` | `c9fb8e0fccb10c74cf429115007beb46207e7aa6e3c813a501695d578ab2889d` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P3/run-ledger.json` | `ef6bdbcf34fddec753d2baf70ccf9f1e01ada8ff3b42a369b1d290d029e0a7f9` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P3/source.diff` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `artifacts/research/process/20261004-qwen38max-closed-loop/acceptance.md` | `6fc8f4bcc8ce35267522cc974fd019ea2953338c480956b75606961d69606f19` |
| `artifacts/research/process/20261004-qwen38max-closed-loop/verification.json` | `f1b6702a5f2d9b88a2cab90d6dd7aad0d5499d258b76c7f8cef4adf8ca2087c7` |
| `artifacts/research/process/20261004-qwen38max-closed-loop/run-v2/model.json` | `c756cb199156b7c9de6c88ec5e94f87ad98a72d7993ee02c057ec58a2b01438e` |
| `artifacts/research/process/20261004-qwen38max-closed-loop/run-v2/protocol.json` | `4061c0d91544993c66a4183fa8be9484eeaf8d2b4dbb75ea55caf12e574fe1f5` |
| `artifacts/research/process/20261004-qwen38max-closed-loop/run-v2/cases/case-07/api/01/request.json` | `17635c77af0d589ab4c607b4e52b609c05b285e6433771239a950690f4010077` |
| `artifacts/research/process/20261004-qwen38max-closed-loop/run-v2/cases/case-07/api/01/receipt.json` | `105ff57b09d41e90b6e97272ce77b7033cdf709a32abb75861016f886182efae` |
