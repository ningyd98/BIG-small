# R93 P4 Empty Instance Inventory Implementation Plan

> **For agentic workers:** ROOT交给指定 GPT-6.1-sol，按 superpowers:executing-plans实施；先等P3单写者释放。本轮Astra只规划/有限只读核验，不产品、不测试、不Git、不派代理。

**Goal:** 修复真实cached空实例侧文件被inventory误拒，保持source-only原件完整校验并安排一次受控的新正分支。

**Architecture:** source inventory保持非空；仅artifact reader授权规范实例侧文件可0B，并严格连接实际capture→frozen auxiliary→metadata→binary。producer的空实例表达合法，不改producer或历史数据；CPU新增真实cached方法路径，保留旧fixture默认。

**Tech Stack:** 既有Python/.venv、pytest/Ruff/mypy；规划核验仅标准库。

**Spec:** T12 Task4、AGENTS、原P4冻结和R93委派；不同代理diagnostic仅参考证据，明确仍为`DIAGNOSTIC_ONLY_NOT_ASTRA_PLAN`。

## 原始失败与独立核验

首个`P4/actual`唯一调用exit1，用时21.12933368998347秒；原收据225源无漂移；68文件25,001,424B含DB全部保留。default preflight原一次exit0；发布前reader抛`original integer required without boolean/coercion`，capture-catalog和prefix-receipt均不存在，外部readout0。禁止改写首败、补造catalog或复用原attempt。

本Astra已实际独立复核不同代理44输入pins全部一致，并解析244events/current严格整数项无异常。三次原capture IDs长度0/0/76800、二进制0/0/307200B，与source END、frozen_aux、export SHA完全一致；metadata availability false/false/true，count0/0/76800，passes2/2/3，labels三处一致。详见本轮`independent-diagnosis.json`，未调用产品reader、decoder、SQL、preflight或测试。

根因是`validate_inventory_v1`把所有bytes一律minimum1用于artifact；真实`_capture_cached_observed`明确include_instances=False，camera合法返回空ids。CPU旧cached替身却调用显式with_instances，三次全非空。两者是同一 optional sidecar 合同缺口；并非bool/coercion、时钟D错误或producer漏写。

## 最小范围与约束

只允许三个owned：

- `src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py`：`validate_inventory_v1(value: Any, *, allow_empty_instances: bool=False) -> None`。保留全部原path/shape/SHA/exact-int校验；仅flagTrue且路径完整匹配 `frames/acquisition-[1-9][0-9]*/instances\.i32` 才minimum0，否则minimum1。`_integer`原样；source/startup/prereg调用默认False。不得对所有文件放宽0。
- `src/cloud_edge_robot_arm/research/operational_prefix_v1.py`：仅artifact reader调用传True；在pack前读取真实source-frame metadata，调用新增 `_validate_instance_original_v1(aux: Any, source_result: Any, metadata: Any, *, width: int, height: int) -> None`。保留原metadata observation校验及所有hash、完整分母、source/D/S/current/失败guard。
- `tests/test_operational_capture_v1.py`：新增下表测试和必要局部helpers；`cpu_components(..., *, production_cached=False)`保留旧默认，True时实际绑定`MuJoCoPhysicsBackend._update_sensor_frame`，经过原decorated `_capture_cached_observed`，stub camera `_capture`尊重include_instances，false为空/two passes，explicit为full/three passes。reset调用当前backend._update_sensor_frame。不能把cached再次替成显式capture。旧断言/失败注入/所有旧case不改。

新增reader验证限定在实例侧文件合同：aux/source/metadata为dict；ids为exact list且各exact int（禁止bool，signed32范围），长度0或width×height；与CAPTURE END ids canonical相同；metadata count为exact int并等长，availability为exact bool并等于是否满像素；labels三处相同且为空时必须{}；metadata pass hashes等于source，空2/full3并保留原passes同状态检查。先验证再struct.pack，错误应ValueError进入原INVALID返回。空optional文件不允许空RGB/depth/mask/metadata，非空实例不允许截短/扩长或伪available。这里不授予geometry/native资格。

producer/recorder/backend/camera/worker/config/CLI保持字节不变，不填假ids、不漏文件、不重编码历史JSON。源码inventory即使名字形似optional仍默认拒0；SHA和实际bytes精确相等、negative/bool/string/float、duplicateJSON、path/symlink、required_files与source/current关系不放宽。不修改P3 planner/role/config。

## Review Focus与测试

| 新节点（同一tests文件） | cases | 原源预期 | 改后 |
|---|---:|---|---|
| test_cached_capture_preserves_empty_instance_sidecars_cpu | 1 | FAIL：publication拒合法0B | PASS |
| test_source_inventory_rejects_empty_and_noninteger_bytes_cpu[zero,false,true,negative,string,float] | 6 | PASS拒绝控制 | PASS |
| test_artifact_inventory_preserves_negative_and_geometry_guards_cpu[bytes_bool,bytes_string,bytes_negative,empty_rgb,empty_depth,empty_mask] | 6 | PASS拒绝控制 | PASS |
| test_reader_rejects_instance_source_metadata_mismatch_cpu[availability_false,count_bool,source_ids_changed] | 3 | FAIL：旧reader漏这些joins | PASS |

单次RED **16unique=4fail+12pass，0error/skip**。元数据反例用旧all-instances真实CPU发布作baseline；修改测试临时原件时同步实际pins与frozen/persisted file_hashes，确保旧完整性检查通过后才到缺失的join，不把早期hash拒绝冒充新guard覆盖。不修改历史P4原件。修改source END IDs仅改变该字段并重pinD slab，其他aux/metadata保持不变。精确参数及断言在JSON `tests`。

新正case必须经真实CPU producer/publication产生catalog，不能手拼成功receipt：244events、120steps、3captures（cached0/cached0/explicit76800）、0actions、0/0/307200B真实SHA、metadata/capture/passhash一致。仅raw camera/counter/软件backend seam；不运行engine或模型。

GREEN采用16新+15直接受影响旧case：旧完整all-instances正链1、reader tamper10、returned acquisition拒绝2、direct/derived2，总31。不重跑63、R03或已完成整套。旧失败分母与日志全部保留。

## Task 1：执行步骤与预算

- [ ] ROOT在P3写者释放后复核本计划及有限pins，独占派Sol。原225-source freeze仅历史证据；P3合法变化不得被误当旧attempt漂移或回滚，不pinP3活动源，不要求全仓quiet。
- [ ] 独占新R93/implementation和basetemp，保存source-before；新增fixture/测试后RED一次，必须命中上表4fail12pass。其余异常停并交新Astra。
- [ ] 实施最小schema/reader修改，formatter仅一次。restricted AST(type_comments=True)精确允许schemakeyword/条件、新helper、readerkeyword/helpercall/metadata读取位置与fixture新增范围；其他product AST与旧测试断言不变。formatter前后独立验证完整AST/comments/signatures不变；不得声称业务前后全等。
- [ ] Ruff、formatcheck、mypy各一次，随后31caseGREEN一次。每次保存原argv/env/cwd/start/stdout/stderr/result/JUnit，按start计次数。任何新失败不自修重跑。
- [ ] 冻结after/diff/原件清单和唯一个案分母，交不同作者独审精确source。CPU通过与实际/正式分别记录；Git仍ROOT独立交付。

所有命令cwd仓库根；环境`PYTHONPATH=src:. MYPYPATH=src PYTHONDONTWRITEBYTECODE=1`。以下每项上限一次；无baseline static、collect-only或完整套件重跑：

**RED**

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=/tmp/bigsmall-t12-p4-r93-red tests/test_operational_capture_v1.py::test_cached_capture_preserves_empty_instance_sidecars_cpu tests/test_operational_capture_v1.py::test_source_inventory_rejects_empty_and_noninteger_bytes_cpu tests/test_operational_capture_v1.py::test_artifact_inventory_preserves_negative_and_geometry_guards_cpu tests/test_operational_capture_v1.py::test_reader_rejects_instance_source_metadata_mismatch_cpu --junitxml=artifacts/research/process/20261004-ced-development/astra-rounds/round93-p4-empty-instance-inventory-20261007/implementation/RED.junit.xml
```

**formatter**

```bash
.venv/bin/python -m ruff format src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py src/cloud_edge_robot_arm/research/operational_prefix_v1.py tests/test_operational_capture_v1.py
```

**ruff_check**

```bash
.venv/bin/python -m ruff check src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py src/cloud_edge_robot_arm/research/operational_prefix_v1.py tests/test_operational_capture_v1.py
```

**format_check**

```bash
.venv/bin/python -m ruff format --check src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py src/cloud_edge_robot_arm/research/operational_prefix_v1.py tests/test_operational_capture_v1.py
```

**mypy**

```bash
.venv/bin/python -m mypy --follow-imports=silent src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py src/cloud_edge_robot_arm/research/operational_prefix_v1.py
```

**GREEN**

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=/tmp/bigsmall-t12-p4-r93-green tests/test_operational_capture_v1.py::test_cached_capture_preserves_empty_instance_sidecars_cpu tests/test_operational_capture_v1.py::test_source_inventory_rejects_empty_and_noninteger_bytes_cpu tests/test_operational_capture_v1.py::test_artifact_inventory_preserves_negative_and_geometry_guards_cpu tests/test_operational_capture_v1.py::test_reader_rejects_instance_source_metadata_mismatch_cpu tests/test_operational_capture_v1.py::test_real_interfaces_reset120_capture_current_chain_cpu tests/test_operational_capture_v1.py::test_reader_recomputes_and_never_mints_authority tests/test_operational_capture_v1.py::test_reader_rejects_broken_returned_acquisition_join_cpu tests/test_operational_capture_v1.py::test_current_source_event_join_accepts_direct_and_derived_ids --junitxml=artifacts/research/process/20261004-ced-development/astra-rounds/round93-p4-empty-instance-inventory-20261007/implementation/GREEN.junit.xml
```

## 旧原件读取界

本轮旧actual公共reader预算0：原receipt/catalog从未发布，事后构造entry或删除stage-failures会制造历史成功；不能这样做。已有标准库逐字段诊断足够。未来若单独获准，可生成只读、明确标“事后派生诊断”的结果，但仍非publication/成功attempt；不能把筛选子集冒充完整root。旧68文件/DB及首败分母永久保留，不建SQL连接、checkpoint、恢复或清日志。

## 新真实运行：仅ROOT后续批准

旧attempt无法事后补成正分支，因此修复和独审完成后，可由ROOT单独批准 **一次defaultpreflight + 一次新actual + 条件成立时一次外部publicreadout**。这不是本Astra现在运行授权。以下新目录必须exclusive，旧目录不重用：

- preflight：`P4/preflight-round93`，mode INPUTS_ONLY。
- fresh source freeze：`P4/source-freeze-round93.json`，根据新preflight真实inventory（含P3合法已完成变化）生成；不预造未来SHA/数量。ROOT核对actual前后无漂移。
- actual：`P4/actual-round93`，开始前不存在，CLI负责startup创建；execution收据在外部`P4/execution-round93`。
- public readout：`P4/public-readout-round93`，输出在raw root外，避免改变完整文件分母。

**新preflight，最多一次：**

```bash
.venv/bin/python scripts/run_operational_prefix_v1.py --config configs/research/operational_prefix_v1.json --output artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/preflight-round93
```

**新actual，最多一次：**

```bash
.venv/bin/python scripts/run_operational_prefix_v1.py --config configs/research/operational_prefix_v1.json --output artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual-round93 --execute-once
```

actual仅ROOT串行资源窗口，环境`MUJOCO_GL=egl PYTHONDONTWRITEBYTECODE=1`。preflight必须exit0/actual NOT_RUN；software静态/31case/独审完成并冻结新源后才actual。新actual任何exit1停，保留原件，readout0，无重试。若启动累计真实attempts=2，第一项FAIL与第二项实际终态分别列明，各application max_attempts仍1。

只有新actualexit0且真实capture-catalog/prefix-receipt发布成功，才调用一次外部reader。内部publication两次guarded reader是原生产流程，不冒充外部readout。JSON `actual_running_preconditions.commands.public_readout`给出精确 `.venv/bin/python -c` 参数，先检查catalog scope/固定receipt_path/真实receipt SHA/entry字节解码关系，再调用reader一次，exclusive保存外部result。不触发live clock/DB/backend、不制造catalog。脚本原文：

```python
from pathlib import Path
import hashlib,json
from cloud_edge_robot_arm.research.operational_prefix_schema_v1 import decode_original_json_v1
from cloud_edge_robot_arm.research.operational_prefix_v1 import verify_operational_prefix_originals_v1
attempt=Path("artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual-round93")
cat=decode_original_json_v1((attempt/"capture-catalog.json").read_bytes())
assert cat["scope"]=="SOURCE_ONLY_NO_NATIVE_ADMISSION"
assert cat["receipt_path"]=="prefix-originals/prefix-receipt.json"
raw=(attempt/cat["receipt_path"]).read_bytes()
assert hashlib.sha256(raw).hexdigest()==cat["receipt_sha256"]
receipt=decode_original_json_v1(raw)
assert receipt==cat["entry"]
view=verify_operational_prefix_originals_v1(attempt/"prefix-originals",receipt)
with Path("artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/public-readout-round93/result.json").open("x") as out:
    json.dump(view,out,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps(view,ensure_ascii=False,allow_nan=False))
assert view["original_integrity"]=="VERIFIED" and view["source_prefix_complete"] is True
assert view["formal_accepted"] is False and view["live_authority"]=="UNAVAILABLE"
```

新软件与新actual的验收仍仅`EXCLUDED_SOURCE_ONLY_PREFIX`：formal false、native unavailable、UTC/SI unverified、future H/D和geometry unknown、calibration_groups0、OC3/restart/suspend未验。3capture/1explicit/0action、完整120steps与原D计算age的reader VERIFIED不等于native geometry、物理任务成功或正式研究验收。

规划写入仅本目录plan.md/json和小型independent-diagnosis.json；产品/测试/actual/publicreader/Git/网络/代理均0。原不同作者诊断绝不重标Astra身份；本计划来自本次ROOT指定Astra规划派单，requested_model如实记录，未冒称能独立核验服务端模型。

## 有限输入SHA256

以下pins是实际字节，JSON附bytes。旧225freeze文件保留而不把其中活动P3成员当当前不变前置。

| path | SHA256 |
|---|---|
| `AGENTS.md` | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` |
| `src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py` | `918e029a6a1f0d2a7a455820c721118abdb50b7c5eda6e8ee15f54bed543e67c` |
| `src/cloud_edge_robot_arm/research/operational_prefix_v1.py` | `88710574f1967534cf25f6052544de8b27ceaae99f597a3fb6727343e28f25a8` |
| `src/cloud_edge_robot_arm/research/operational_capture_v1.py` | `06373a9c702420ab38c5afa20f888efb35cd6ea109cf094c662fa04511e60b3c` |
| `src/cloud_edge_robot_arm/research/native_reset_capture_v2.py` | `a22ce81503a1dd7d6aa9b81a57eb61cebcbda64ec58228a5c4dbe21da1e41f5a` |
| `src/cloud_edge_robot_arm/vision/raw_recorder_v3.py` | `4eabd3bf9cdf15b3942c4a740781a95c22ea684f410853c853d0336952d7a303` |
| `src/cloud_edge_robot_arm/simulation/mujoco/backend.py` | `b7b6026b1173448de826e53253ae74f92b6b70ea46a404e10054c5cd451a62a6` |
| `src/cloud_edge_robot_arm/simulation/mujoco/camera.py` | `d85aa6eda7c9f658f2e3bb550c44b3462ebd65e290d5c7d9b79fa30639136e2f` |
| `tests/test_operational_capture_v1.py` | `f86e4b56b29a659081ae4b4aeb721b224308082080988313088b5f5601d7a908` |
| `scripts/run_operational_prefix_v1.py` | `fe8e8c9e021ec437b601895de724f1d10f17eb221fea6b8302c304a65fbcffa9` |
| `configs/research/operational_prefix_v1.json` | `c1d51bb28376f9a2c7e636efe16a0675d426951b8ed8849ead78d342f4b3ada1` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/source-freeze.json` | `27773aa3322a8624718483a3bfe948fcd67fb28a43112ee907d7ff6b5a531db4` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/root-actual-authorization.json` | `8821cd14595d2ce26b4be4e6b1eb0f7969bd1c7b22442d84b1a413e150f28ea2` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/preflight/command.json` | `b65770cab59042a9af672a6df03171a7c27f96bd8ff8fa81ef9c7d926a551fff` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/preflight/execution.json` | `970003da25e78bb400eb29ac4b7d247c6c3846b7761f2417e9b37334fc2fdf24` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/preflight/stdout.txt` | `d5799ab193fd27174c610677ac49563dc40cd79eae3ee8c22626e39f88b88bba` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/preflight/stderr.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/execution/command.json` | `cf89e9e4667d387c3a9d98a8e21204001650a15d2dbbf2df5abbfd01a04b6e64` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/execution/process.json` | `7b0b8480b114a8e61674e09c822766abe2a27a946ac368ec3679d63e4e4eb62b` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/execution/execution.json` | `1a965762c661a70176f66fc44454edc0f4b4eb8cdb9757a8bd0a4b8e2116f009` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/execution/stdout.txt` | `16640bf9566e424c441f44a979cabc22a88a4b2f39929c48ea8e7e89204c25e9` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/execution/stderr.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/runner-failure.json` | `80680a29cadad65042837ca60389be29cd32fb35909827c5580696f8869044c0` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/stage-failures-4.json` | `d108467f72f98bbe3b310138d37eed8d6c6ceec202255c8c826c95d763a421f7` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/runtime.db` | `e29e3e826457e959e910a24b08e75497fa790a896f4d76927ebe7cf508c362dd` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/prefix-originals/operational-originals.json` | `14b54edfe5e65f964708f5a647b1a725af13d05f6a9a4d30bfbd810a41620db4` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/prefix-originals/frozen-originals.json` | `808580199fa6ad3dfed492b638e8f0c78200bb95b4aa81952181b977cb733c45` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/prefix-originals/preregistration.json` | `085eec086849983ab8306fb32509409d342b54d0d7afd12971bf6f690b2e9b0b` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/prefix-originals/startup-inputs.json` | `1004a3b1946c5c94d811ded732245e51fd48de9f1f9722cc0d24213a5a81fbfc` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/prefix-originals/startup-policy.json` | `c1d51bb28376f9a2c7e636efe16a0675d426951b8ed8849ead78d342f4b3ada1` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/prefix-originals/unbound-export.json` | `daa15a8207d47e47ffdc4928ef34366356e40c4373a8cd280129a761697b8f9a` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/prefix-originals/persisted-frames.json` | `21caa4dc7601e72d9e78cddc5ab060132efb81a869d3edd699213583b102e55d` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/prefix-originals/publication-failure.json` | `08f26fbf6fd1b375c1251d731cc1234b06532afa3c86395d12c56610ba66ca44` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/prefix-originals/stage-failures-1.json` | `a63a2b6703963ced201789958a2955f25b69b96e4945d69c8b5f7fb0f9900bc0` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/prefix-originals/stage-failures-2.json` | `a63a2b6703963ced201789958a2955f25b69b96e4945d69c8b5f7fb0f9900bc0` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/prefix-originals/stage-failures-3.json` | `a63a2b6703963ced201789958a2955f25b69b96e4945d69c8b5f7fb0f9900bc0` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/prefix-originals/prefix-failures.json` | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/prefix-originals/source-publication-state.json` | `ad1f97099cf381e8d569b4d66b817eec3495f55b1a57c821746428829c056ac3` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/prefix-originals/frames/acquisition-1/instances.i32` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/prefix-originals/frames/acquisition-1/source-frame.json` | `6122ce8d64f1315011efe737fd88ca2d6677043299b9483b0ae2b7cd5a574849` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/prefix-originals/frames/acquisition-2/instances.i32` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/prefix-originals/frames/acquisition-2/source-frame.json` | `a842e91109dcd0b26e6d31fd6cc7fec4fb0643eb4e2dde3aaac78e4ca2e02d6d` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/prefix-originals/frames/acquisition-3/instances.i32` | `5024f5e1846f12be80f552c8b1419b0cdeac0e319c09d49916b9a727e23a5e4d` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual/prefix-originals/frames/acquisition-3/source-frame.json` | `b8e5f39a04a34df4e4e48ad6851433838209d45900a44ae46457f341e37565bd` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/diagnosis-original-integer/diagnostic.md` | `10a530eb7b3440d498e032b25764e83699256b375d3e680170ed732138846214` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/diagnosis-original-integer/diagnostic.json` | `6fbfcb02895a4c90f4c414d30de655aa30a75e3847872edc37538bbf817156a5` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual-originals-manifest.json` | `62b7ae03851c913090a056791288991316f0b78dc44a2c39d0878751f80d65e5` |
| `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/step-report.md` | `eb8a2ed45aa6c2f68bdea1c67871f107bbc2f672a401382d2add723eb1c951bc` |
| `pyproject.toml` | `b2bf5c4042d568eaf9def415ae7b2f08f0fa541a01f970b7e68e6d950035bb6c` |
| `tests/test_operational_prefix_v1.py` | `1ccb56de190f5cea0280882690bead41ed15aaff0fdfa2b74b32ca9c5cd1b426` |
| `tests/test_visual_raw_recorder_v3.py` | `256d314e43fd71dff2d4173fc9692d1debb2dae180391815e3cf2cfa32220a19` |
| `docs/superpowers/plans/2026-10-07-t12-sol-execution.md` | `5a1358f0397edbc54c301edb63e934b1d2ba15ee79d64c9ae36248749b6af0f8` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round93-p4-empty-instance-inventory-20261007/independent-diagnosis.json` | `2796b75ae6d2211f85b2145e47a8aef7c970b760dadfa6496649ce037345a4cd` |
