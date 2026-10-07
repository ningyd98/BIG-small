# R94 P3 Scope Proof and Import Order Implementation Plan

> **For agentic workers:** ROOT明确单写者窗口后交指定GPT-6.1-sol，使用executing-plans。Astra本轮只规划/有限AST诊断，不实施、不测试、不Git、不派代理。

**Goal:** 恢复准确的R92范围证明，修正唯一新测试局部I001，消费尚余验证预算，不改变三项已落盘产品语义。

**Architecture:** 证明脚本按精确路径及节点定位，保留类型注释绑定，仅为两条已核实同一赋值的TypeIgnore规范化行位置；产品源不动，仅一个新测试local imports排序。证明、Ruff及余下验证逐条失败即停。

**Tech Stack:** 既有Python AST/tokenize、Ruff/mypy/pytest，均`.venv/bin/python`。

**Spec:** R92原计划与被冻结停止报告；报告SHA `2472d5f165260ac17a692127babe5127f8c29b38ab0133143bddb0c1105867fd`。

## 原失败与确认根因

R92唯一RED已正确3fail+8pass/0error/skip，formatter唯一exit0。prove-scope.py在83行整模块回退相等断言exit1。原Traceback未列当前模块，但按实际owned顺序及独立AST差异，首个失败确定为生产`role_models.py`：原`type_ignores[0].lineno`206→207、第二项224→225。两条仍分别附在`planner.role_config_version = profile.config_version`、`planner.role_snapshot = snapshot`，tag均`[attr-defined]`，可执行AST没有变化。`include_attributes=False`仍保留TypeIgnore.lineno，因为它是字段。

第二个确定但**原执行尚未到达**的证明缺陷：`name.endswith("role_models.py")`也匹配`tests/test_rgbd_role_models.py`，错误寻找不存在的resolve_cloud_role会StopIteration。不能冒称它是原83行失败。

独立只读对照四个Python的semantic-after与source-after，完整AST(type_comments)/comments均等价；精准回退三项R92授权增量及8新增测试/helper后，除上述两个line位置外无差异。此诊断不代替待执行新proof收据。

原proof没有独立start/stdout/stderr收据，只保留真实tool原文及observed result，不补造时间。作者在proof失败后仍运行Ruff，这是执行顺序违规；Ruff确已用一次exit1，唯一I001在新`test_ced_max_reuses_successful_normalized_transport`1154行local imports。原runner另有确认缺陷：不向调用者传播子进程returncode；这不是未经证明的原事故唯一成因，但新runner必须修正。

## 限定修改

唯一仓库文件：`tests/test_rgbd_role_models.py`，只将上述新函数头部imports改为以下顺序，模块/name/alias/level完全相同，不改其他函数、旧断言、fixture或三条产品增量：

```python
    import io
    import struct
    from pathlib import Path

    from PIL import Image

    from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
    from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
    from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository
    from cloud_edge_robot_arm.vision.messages import model_to_observation_pixel
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from scripts.probe_rgbd_roles import read_role_config
```

Ruff --fix、全文件import排序和formatter重跑均不允许。所有生产文件及tests/test_ced_runtime_binding.py保持冻结字节。新helper只写`R94/implementation/prove-scope.py`和`command-runner.py`；R92所有script/source-before/semantic-after/source-after/diff/report/CPU原件均不可覆盖。

## 精确证明算法与Review Focus

1. 用完整五条路径做dispatch，unknown path立刻拒绝；不能basename/endswith。YAML只回退cloud.coordinate_system；factory仅精确`resolve_cloud_role`内赋给model_snapshot的ModelConfigSnapshot调用里generation_parameters新增的唯一`think: False`；planner仅精确class/method/compatible else中紧邻`path=self.chat_path`前的完整if AST。其余任何差异失败。
2. 新函数集合按文件固定：rgbd tests仅`_p3_snapshot_for_wire`、`_p3_wire_boundary`、`test_ced_max_reuses_successful_normalized_transport`、`test_role_cost_delta_preserves_all_sent_requests`、`test_role_compatible_thinking_reaches_serialized_request`、`test_role_thinking_provider_controls`；runtime binding tests仅另两原命名函数`test_existing_max_success_is_not_new_source_freeze`、`test_role_thinking_change_invalidates_request_binding`。要求每项存在一次，只移除这些节点，不删未知节点。
3. **TypeIgnore严格绑定，不宽泛消除：**仅生产role_models.py允许两条已列注释位置改变。先从真实token核对注释文本、tag/order/count；每条必须仍位于resolve_cloud_role中相同目标的唯一Assign上，声明与赋值AST精确相同。证据记录206→207和224→225。仅在上述核验后，把复制的回退AST两条lineno映射回原位置作比较；原AST/text不改。不得清空type_ignores、删除tag、忽略type_comments或移除所有行字段。任何新增/删除/换tag/换绑定目标必须拒绝；所有普通参数/返回注解和type_comment仍参加完整AST相等。
4. 分开三个阶段：R92before→semantic-after的授权语义；R92semantic-after→R92formatted完整AST/comments/signatures等价；R92formatted→R94当前仅精确local import排列变化。最后一步把唯一import区块复位旧顺序后整模块AST应相同，其他四owned应字节相同。明确import顺序改变是授权测试变动，不冒称原始AST完全不变。
5. 新proof一次调用内用内存副本做4个拒绝自检（改ignoretag、挪ignore目标、改普通注解、改旧assertion），必须拒绝，再生成真实正证明；不导入产品、不pytest、不写假源。失败报告应带path/stage/首个AST或token差异。只在全部成功后exclusive写restricted-scope-proof及完成信息。

## Task 1：单次恢复与失败即停

- [ ] ROOT校验有限pins和R92当前5源冻结，确认无其他单写者冲突，独占新R94 implementation/basetemp。保存before、所有新after及完整局部diff；不恢复旧产品覆盖主树。
- [ ] 新建精确proof及fail-closed runner，只排序指定import区块。修改范围零产品语义、零旧断言。
- [ ] 运行新proof一次，查看真实exit/result与成功证明；非零立即停止，不运行Ruff。
- [ ] 新Ruffcheck一次；若0才依次消费原剩余formatcheck、mypy、Task3 ownedGREEN各一次。每个命令单独工具调用并检查收据；不无条件链式调用、不parallel、不finally继续下一步。
- [ ] source-after/证明/逐命令/JUnit/预算/差异冻结后交不同作者独审。保留原两个失败与顺序违规；软件、actual、physical/formal分栏。

新runner每次只接受一个allowlisted命令名。exclusive记录command-start后启动，完整原stdout/stderr/result；即使child失败先保留result，然后`sys.exit(result.returncode)`。启动异常也必须非零。start即消费次数，不因异常退还。后续调用还需检查上一receipt；不能只相信外层进程exit0。原证据没有时间就记录缺失，不伪造。

## 预算与精确命令

原已用：RED1、formatter1、proof1、Ruff1；这些仍为已用失败/通过历史，不清零。本轮仅新增**修正版proof1、新Ruff1**。原formatcheck/mypy/GREEN各used0、remaining1，本轮继承消费。新RED0、formatter0、额外GREEN0、collect-only0、actual/network/Git0。

环境`PYTHONPATH=src:. MYPYPATH=src PYTHONDONTWRITEBYTECODE=1`，cwd仓库根。GREEN选择完全继承R92，仅basetemp/JUnit换新R94路径保护旧件；总unique以真实JUnit为准，必须覆盖已登记11新case，不预造总数。

**scope_proof：最多1次。**

```bash
.venv/bin/python artifacts/research/process/20261004-ced-development/astra-rounds/round94-p3-scope-proof-import-order-20261008/implementation/prove-scope.py
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
.venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=/tmp/bigsmall-t12-p3-r94-green tests/test_rgbd_role_models.py tests/test_ced_runtime_binding.py -k 'normalized or source_freeze or role_cost_delta or role' --junitxml=artifacts/research/process/20261004-ced-development/astra-rounds/round94-p3-scope-proof-import-order-20261008/implementation/GREEN.junit.xml
```

任何新failure、scope变化、pins漂移立即留证并交下一实际Astra；不追加修复/重试。原56CPU文件72,850B与失败RED保存；13次fakeHTTPopen/9次模拟inference仅CPU，不冒充真实请求。

## 验收与实际前置

proof精确通过、Ruff及继承format/mypy/GREEN均0，所有类型注释/旧断言保护与最终source经不同作者独审，才可标软件验证。三条R92产品变化不动，all-sent timeout/retry及unknown bill null不变。最终Max cold+3warm四请求仍等P8最终source freeze和ROOT独立调度；本轮不读真实secret store、不网络、不发布Git、不将旧35call当现行qualification。R93其他源不作为此轮活动不变pins。

本次Astra规划通过原字节/AST/token有限诊断，未运行旧proof、产品模块或静态/测试命令；只写本目录plan.md/json及小型independent-diagnosis.json。requested_model如实为gpt-6-astra，未冒称独立核验服务端模型身份。

## 有限输入SHA256

JSON input_pins附bytes。原before/semantic-after/formatted阶段均按实际字节固定，执行前复核。

| path | SHA256 |
|---|---|
| `AGENTS.md` | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` |
| `pyproject.toml` | `b2bf5c4042d568eaf9def415ae7b2f08f0fa541a01f970b7e68e6d950035bb6c` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/plan.md` | `0b6bc6fd6c179683d80d813da14383afeeb5a0aff35dbf5ed0e4b60394df5f35` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/plan.json` | `f4c81c6ca710a733482d7de8edeed9dc913c15d97e09e2ba88b5b2eee2fbdc0f` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/root-authorization.json` | `3d34479e368392312ff1ad9329e9fab21df33455ca89e3298473263db6bb2892` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/step-report.md` | `2af28c86018124f53bf1d6538e3885a2cb9fe2aaf3565131a167a27f3b246f1b` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/step-report.json` | `2472d5f165260ac17a692127babe5127f8c29b38ab0133143bddb0c1105867fd` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/failure-receipt.json` | `2163a6269c34e2980a54e7175df6095747f753e0fd37c9bd687751af572352f0` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/prove-scope.py` | `43a44f24f8348530ab821223cdb0d8ef3383099a3a4f5ed21315038a843153dc` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/scope-proof.tool-output.txt` | `da922792b92c7630d42d4496a0428ef7f91385c220e11b93e020ed119c7282c8` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/scope-proof.exec-observed-result.json` | `20abca1d2e345c2b0e9b4d1f2a395b50399cfb7ceeab80412fb4ebe0d155cdd5` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/command-runner.py` | `0089c52b39c427facea6812afd352b713bdfd07ed49328382ffe192c2e261559` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/run-ledger.json` | `ee6278f7466f1652524cff83f0047d2cb4ae902cc5adbc626a457381a4aa8aee` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/source-freeze.json` | `01803be5d6f659a7e3512ca0ba78ae2e6286c6bdf8d7c79907d980ca26076d75` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/input-check-after.json` | `dcc23088a46a97c0e89f48b4b9e8dd0685d2e8f528c9cc948385416f2ac831bf` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/source.diff` | `549dde1ff87f47996cc7761b45a47c0e15894e362c9d3bcc45ec59e757e1a265` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/report-evidence-pins.json` | `695013d2bd85bb2b8af1adc99d4553537a91cf8724221eb475b7fed5486ce98e` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/cpu-originals-manifest.json` | `5afa79f2f73ce6cf4800c1b739f2ea0cd371ee9a6283315ca366bc142f29cafb` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/RED.command-start.json` | `74bb0b4ff7bbc26cdcca2b8c36b2e2a733d73a63c88f7fabdca6534f95eb7fac` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/RED.command-result.json` | `a86514acc4f786828f401927208ea17ebf2a95cea7e3839b839ed041d7e11740` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/RED.stdout.txt` | `97ba574620fcdda90f1a9a48c8ee30701624beea8a0afeee66378263e99c1e4c` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/RED.stderr.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/RED.junit.xml` | `ceee1caceb1327dff35f495b07db4e660318af47ac634d6ff2affbd54c8241e3` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/test-outcomes.json` | `52c08d6e0c2453ee4ed7c39c626a297bd9d57b9a5ee9ed644ed8f59bcfe006cc` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/formatter.command-start.json` | `05c566be2ebd72e36ecf86eb8222f927aa14bf5bb1f2ec882599eca6d43974dd` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/formatter.command-result.json` | `c6e53284fa0ef198e7f16c46e80e7f36bf6a48af306114616b18aebeba8a2619` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/formatter.stdout.txt` | `1dc6a19feae160e87088a6a505f8844ac8bfdaf9001c9c3cc558beceb0f6c9d9` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/formatter.stderr.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/ruff_check.command-start.json` | `0c47cfad45a7f5d9dc829046e03073bf3250eec05da117288cbb156b3d776b2d` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/ruff_check.command-result.json` | `b83ca07fa60e1694ea682124e87f82455c986056f12dd762a0940ef103112935` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/ruff_check.stdout.txt` | `5f92add47a640beb2d0fd74b50873a9b80e7133eef21c6ba6278dc60bf13b33c` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/ruff_check.stderr.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/authorization-pins.json` | `f50f861d1e19e692b5282b95801f96e3320cc7b5cd243d4257e33e2c884a403d` |
| `configs/research/ced_roles.yaml` | `d3fddcff7a06306d3b56a0b17478c8f398f702a614a313d729199a9b9d1539b3` |
| `src/cloud_edge_robot_arm/vision/role_models.py` | `cdeef8872e38aab742a2018ff1826575cedb3a35aca7969da369a8854890959e` |
| `src/cloud_edge_robot_arm/vision/planner.py` | `33dfe0aa25b6a316a346e7247724fa20a9db6082ef5317c036bbc9f7ddaea317` |
| `tests/test_rgbd_role_models.py` | `afad7fe64f4989477d56922c5e9ea809165b14256ffca78bcb40f9104fabeca7` |
| `tests/test_ced_runtime_binding.py` | `40b665857bec2c07c74e2f789d2ad28319e561ef856870b13aa190ed85be8d4b` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/source-before/configs/research/ced_roles.yaml` | `54cfa5787f81f284d999703e4fd5da47ae59c5d53784f8636393ab4d2e759f22` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/source-before/src/cloud_edge_robot_arm/vision/role_models.py` | `13b59bd3679cd4893de60431e1392ec495bc1a964aa8493536defc435d91c0c9` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/source-before/src/cloud_edge_robot_arm/vision/planner.py` | `0f1f31392c84f8db32535f6908e1d3e2bdae2d2265b7afec7e12a5492af96f66` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/source-before/tests/test_rgbd_role_models.py` | `98ef1e0d28ca6bc6a6046e715b6654f10754e9bb1a930e8adf2ab582cb284067` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/source-before/tests/test_ced_runtime_binding.py` | `ebdff387edaae902726042239c87cc4ae5533b9493e61d26a4d2b9e2f44fe48a` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/semantic-after/configs/research/ced_roles.yaml` | `d3fddcff7a06306d3b56a0b17478c8f398f702a614a313d729199a9b9d1539b3` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/semantic-after/src/cloud_edge_robot_arm/vision/role_models.py` | `cdeef8872e38aab742a2018ff1826575cedb3a35aca7969da369a8854890959e` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/semantic-after/src/cloud_edge_robot_arm/vision/planner.py` | `3ac5af26f7ad47c010646df6d4571590be6bbb1699685663207c2d417b89c702` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/semantic-after/tests/test_rgbd_role_models.py` | `6da9163672b64526565445d196afb66c76009cf504a0a3a4220baf92b2781902` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/semantic-after/tests/test_ced_runtime_binding.py` | `81e8f816164168564a2a711b256ffc40c4bcdcbb5a06d3cce2759984b582d8e7` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/source-after/configs/research/ced_roles.yaml` | `d3fddcff7a06306d3b56a0b17478c8f398f702a614a313d729199a9b9d1539b3` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/source-after/src/cloud_edge_robot_arm/vision/role_models.py` | `cdeef8872e38aab742a2018ff1826575cedb3a35aca7969da369a8854890959e` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/source-after/src/cloud_edge_robot_arm/vision/planner.py` | `33dfe0aa25b6a316a346e7247724fa20a9db6082ef5317c036bbc9f7ddaea317` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/source-after/tests/test_rgbd_role_models.py` | `afad7fe64f4989477d56922c5e9ea809165b14256ffca78bcb40f9104fabeca7` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round92-p3-compatible-thinking-wire-20261007/implementation/source-after/tests/test_ced_runtime_binding.py` | `40b665857bec2c07c74e2f789d2ad28319e561ef856870b13aa190ed85be8d4b` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round94-p3-scope-proof-import-order-20261008/independent-diagnosis.json` | `2caa446f5024b40f99dddabf2cafb16a446f612970fefd883df50d14b668b563` |
