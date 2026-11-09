# R507 Molmo2-ER Transformers compatibility Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans 按以下门禁实施；用户已授权研究筛选，不另设形式性批准。本轮实际 Astra 仅规划，未实施环境修改或模型执行。

**Goal:** 通过已有只读 TF4.57.1 依赖闭包消除 Molmo2-ER 的 TF5 注册冲突，先验证本 checkpoint CPU 接口，再按 R505 执行获准原生 point DEV16。

**Architecture:** 仅改变 R505 独立 runtime 的依赖搜索顺序；官方 checkpoint/source、历史 venv 和历史实验保持原字节。原完整 system/user JSON 协议明确 unsupported，双图 processor 能力单独验证，二者不得互相替代。

**Tech Stack:** Python3.12；历史 Molmo overlay Transformers4.57.1/tokenizers0.22.1，底层 Torch2.6.0+cu124；官方 config 记录4.56.2，是训练/导出记录而非精确安装强制声明。

**Spec:** 本目录 request.md、failure-inputs.json，R505 plan.md/plan.json；planner_model=gpt-6-astra，2026-11-09。

## 原始失败与根因

`candidates/04-molmoer/cpu-import-01.stderr` 在官方 `modeling_molmo2.py:1764` 调用 `AutoModelForImageTextToText.register(Molmo2Config, Molmo2ForConditionalGeneration)` 后报 `ValueError: ...Molmo2Config... is already used by a Transformers model.`。实际 TF5 的 modeling_auto.py 已含 molmo2 映射，auto_factory.py 按配置类名检查已有映射并拒绝注册；这是源码可核验的版本注册冲突。发生于类导入，0 model loads、0 generation；不得写成加载失败或模型准确率0。

14 项原登记输入 bytes/SHA 全部核验通过；扩展输入见本计划 JSON 和末尾清单。下载结果记录完整 PASS，本次规划未重新流式哈希全部大权重；执行前必须重核，不把下载记录当本轮复核结果。

重要路径更正：仓库 `.venv-vlm` 实际 TF4.48.3/tokenizers0.21.4；TF4.57.1/tokenizers0.22.1 在 `artifacts/research/process/20261004-t7-parallel-local-models-physics/molmo/.venv/lib/python3.12/site-packages`，其 pth 再引用 `.venv-vlm`。历史 Molmo2-4B CPU preflight 通过仅是兼容选择依据，ER 代码哈希不同，不能继承通过状态。TF4.57.1 是否完整满足 ER 当前 masking/processor/generation API 尚须本 checkpoint CPU 门禁。

规划期间裸 `python` 不存在，读取核验已改用 `python3`；这不是模型错误，也不需要修改系统安装。

## 限定范围与全局约束

允许修改仅 `datasets/model-cache/ordered-small-vlm-20261109/runtimes/molmoer-r505/.../baseline.pth`；改前保存原字节与hash至R507 evidence。只读引用顺序为历史 Molmo overlay 路径、`.venv-vlm` site-packages 路径，两个独立绝对路径行。不能仅引用底层 `.venv-vlm`，也不能指望作为普通路径加入的 overlay 自动执行其内部 pth。新进程不得混入 runtime-b/TF5，禁止对任一历史环境 pip install 或修改 pth。

允许新增 R505 `implementation/molmoer_adapter.py`、`implementation/cpu_molmoer.py`、`implementation/prepare_molmoer_protocol.py`、`implementation/run_candidate_molmoer.py`、`tests/test_molmoer_contract.py`；候选下新增带 R507 名称的 environment、CPU、protocol、结果、stdout/stderr、manifest。允许新增R507 evidence/、步骤报告，并更新R505阶段总结。公共scorer只读复用；若需修其bug，另开Astra。

新 HF_MODULES_CACHE 使用 `datasets/model-cache/ordered-small-vlm-20261109/hf-modules-molmoer-r507`，保留旧缓存；HF offline/local_files_only，PYTHONDONTWRITEBYTECODE=1，所有可写缓存指向新目录。禁止注册monkeypatch、exist_ok=True、删除注册、替换官方模型实现、修改chat_template、静默使用TF5内建Molmo2、修改checkpoint/config/tokenizer/VisualDecision schema。禁止新精度搜索、JSON修复或额外prompt实验。

R505 v1 DEV16、原顺序、白名单、无oracle输入、独立评分和原始证据要求全部继承。seed=0、do_sample=False、num_beams=1、max_new_tokens=512；本轮一次BF16基线加载，不自动重试。累计候选预算≤134（包括全部smoke/warmup/debug和之前轮次），不能因新轮归零。

## JSON与双图决策

官方模板允许交替 user/assistant（另有subtitle特殊分支），直接system必定触发 `Conversation roles must alternate user/assistant/user/assistant/...`。因此 `JSON_RGB` 和 `JSON_DUAL` 原 R501/R505 system/user 协议均记 `UNSUPPORTED_SYSTEM_ROLE`，调用0，准确率null；不是断言该模型不能生成JSON。禁止把system转subtitle，禁止合并到user并声称等效。

本轮选择最小修复，不运行研究性原文嵌入变体。如后续要做，须另轮预登记新实验名、逐字嵌入包装、消息hash及非等效边界，仍不得增加候选134总额度。本轮双图只允许CPU processor输入能力检查，PASS仅表示两张独立图像进入张量，不表示原JSON协议通过或使用深度。原生基准仍单RGB；旧双图bridge不是可直接复用的本轮prompt或协议。

## Task 1：固定独立依赖并验证本checkpoint CPU

- [ ] 复核全部输入sha和允许范围，冻结原baseline.pth、环境说明及现有失败；不同HEAD本身不构成失败，输入或范围变化则暂停复核。
- [ ] 将新runtime baseline.pth按上文两层顺序绑定只读依赖。新进程记录sys.path、sys.executable、Python/Torch/torchvision/Transformers/tokenizers/huggingface_hub版本与各自__file__；断言TF4.57.1、tokenizers0.22.1、无runtime-b路径。记录必要依赖闭包检查；不得把无关历史全环境pip-check通过作为替代。
- [ ] CPU命令形式：`CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 <cache>/runtimes/molmoer-r505/bin/python <R505>/implementation/cpu_molmoer.py --model <cache>/models/Molmo2-ER --out <candidate>/cpu-contract-r507.json`。运行前冻结确切脚本、参数、命令与hash，单次CPU300s。
- [ ] CPU脚本用官方AutoConfig、get_class_from_dynamic_module加载config.auto_map中的模型类，AutoProcessor.from_pretrained(trust_remote_code=True,local_files_only=True,use_fast=False)。不构造模型、不load权重、不generate、无CUDA初始化。分别处理白名单一张RGB和原RGB+depth PNG，记录原图hash、rendered prompt/hash、token IDs/hash、tensor键/形状/dtype/hash及image_num_crops/image_grids对应图像数量；证明不是拼图。
- [ ] 原system/user消息模板负测试必须断言原始异常类别/信息，保存stdout/stderr，并写UNSUPPORTED_SYSTEM_ROLE；此预登记负例属预期，不触发新根因轮。原生user-only输入须正常；不可用降级模板掩盖失败。
- [ ] TF4.57.1仍有导入、ABI/API、processor或张量合约失败时冻结原始异常，停候选并交下一Astra。本轮不自动试4.56.2、升级torch或复制/编辑SDK，避免将所有兼容错误视作同一注册根因。

## Task 2：原生point合约与软件门禁

- [ ] 新adapter只读R505白名单，用单RGB官方模板，target/destination query保持R505固定语义。冻结官方point输出格式及坐标来源，尤其单图与旧多图 `<points coords=...>` 的差异；旧native_adapter.py仅作参考，不是新ER单图格式的官方证明。已有本地官方材料不足时，按R505渠道冻结对应官方SDK/格式说明及sha后再绑定；不能依据生成结果/GT猜归一化尺度，无法证实则 NATIVE_CONTRACT_NOT_READY、0 GPU calls。
- [ ] `tests/test_molmoer_contract.py`先写预期RED再最小实现：官方坐标端点与轴顺序、越界/NaN拒绝、明确ABSENT和解析失败区别、多点按R505冻结规则、单/双图计数、system原样拒绝、oracle/旧答案不进入模型、未运行JSON不能计为0准确率、累计预算拒绝第135次尝试。禁止借旧bridge派生完整VisualDecision。
- [ ] 单次运行新增测试和已有R505 tests，记录命令退出码及输出；所有软件门禁PASS并冻结protocol-r507.json后才有GPU资格。新的解析器/scorer根因先Astra，预期RED例外。

## Task 3：真实运行前置与验收

- [ ] 逐文件重核asset-manifest的bytes/SHA，包括4权重分片、索引、源码及tokenizer；核索引引用全部存在。再次核执行脚本、协议、DEV16输入、只读依赖文件/版本、原始失败未变化。
- [ ] 确认前序候选终止/完成证据，GPU串行且空闲，不停止他人任务；RTX4070TiSUPER16GB，主机可用≥8GiB、磁盘余量≥60GiB；记录真实读数、BF16参数驻留预估和activation/KV余量。若无法支持本已登记BF16配置，记RESOURCE_DEFERRED，本轮不临时量化。
- [ ] 一次AutoModelForImageTextToText.from_pretrained本地官方ER权重（trust_remote_code、local_files_only、BF16、SDPA、device_map GPU0），一次模型加载≤1800s；准确参数绑定必须在load前冻结。load不是CPU类导入。每次query≤900s，greedy512，不设整候选短截止。
- [ ] 原生point16×2=32；完成screen后positive-01 target同配置重复2次；共最多34次本轮生成，无额外warmup。box/mask无支持记UNSUPPORTED，JSON两阶段各0 calls，剩余额度不挪用于prompt搜索。累计账本仍≤134；每次attempt生成前落盘，保留generated/failed/completed、raw文本/token IDs、计时与显存。
- [ ] 低分、空输出、格式不符和512截断如实记录，不改prompt重试；连续两次900s timeout按R505终止余项NOT_RUN_AFTER_TIMEOUT。OOM/NaN、hash差异、实际API异常、新解析器bug或范围扩大停止受影响工作并交下一Astra，不另load重试。
- [ ] 单独离线评分正例12、缺目标4，报告target/destination/联合命中、明确无目标/虚假目标/解析错误，冷态和暖态n/p50/p90，load时间和VRAM。重复调用不入准确率。JSON original-protocol unsupported；双图CPU支持和depth因果使用NOT_ASSESSED分别报告。3D/控制/实机/正式研究验收未进行。
- [ ] 写R507步骤报告与R505候选结果/阶段总结，标明开发验证、真实运行和正式研究边界。显式路径提交研发分支并推送后核本地/上游/远端SHA一致；完整raw/权重/venv按现有本地边界保留，manifest不是完整远端复现包。

## Review Focus

1. 误把基础venv当TF4.57.1：Task1实际模块路径与版本断言。
2. 注册通过但ER新API不兼容：Task1真实checkpoint类与processor门禁，不继承旧模型通过。
3. system角色被静默改写：原模板负测试、JSON调用为0，unsupported独立状态。
4. 单图点格式误用旧双图坐标：Task2官方来源与边界测试，来源不足不得生成。
5. CPU双图被说成深度有效/完整JSON：Task3报告分离能力、真实调用与验收。

本计划完成只证明规划和输入核验；目前新ER CPU、权重load、generation均未由规划者执行。无软件PASS或正式研究PASS声明。

## 输入清单

以下所有输入均由规划者核验bytes/SHA；大权重通过asset-manifest/download-result引用，其现场重核为Task3硬门槛。

| Path | Bytes | SHA256 |
|---|---:|---|
| `AGENTS.md` | 1774 | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/plan.md` | 16610 | `00aa44e6fa5507bda69dcd8383f9963f88316c143d1397fdfb142ec4ab293b63` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/plan.json` | 51331 | `16d6d5e722cd30dcb4190f08b5af3685a5a6831a863b3e0a37a8bac528771b93` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/04-molmoer/cpu-import-01.stdout` | 7 | `96412115a030a15a7c6d4a297146d9c8ac89b44451a02a93c77d2a7b3f463d50` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/04-molmoer/cpu-import-01.stderr` | 2586 | `917b97a614bfdbb847e907c0389bf3186f1219d272391848aa1da447e69f9362` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/04-molmoer/environment.json` | 302 | `3f6bd4ec0318a1376077719434e8feb073501ee6392e37200a4ba7b7551b0908` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/04-molmoer/asset-manifest.json` | 13198 | `ff0563c87a9bd42a90df49db81dc14ee00d88894ad662f2b43c1942475076464` |
| `datasets/model-cache/ordered-small-vlm-20261109/models/Molmo2-ER/configuration_molmo2.py` | 13905 | `1405b6760579de537521829b9641c8362d5d50e7ef2bdbe3434d2de4a2fc6416` |
| `datasets/model-cache/ordered-small-vlm-20261109/models/Molmo2-ER/video_processing_molmo2.py` | 37660 | `aaeffabdee0b11f93fb380093df1738964340ea072ba6352bd3f371cc0df835e` |
| `datasets/model-cache/ordered-small-vlm-20261109/models/Molmo2-ER/processing_molmo2.py` | 18224 | `73fee7d5cc24e64fdecff90b07e2fea1985113394ffaaf9b87f42e40f3fb4aeb` |
| `datasets/model-cache/ordered-small-vlm-20261109/models/Molmo2-ER/image_processing_molmo2.py` | 22169 | `22fcc160210a3a648b6d618171686c40b900f512107f532c266af7792ac00511` |
| `datasets/model-cache/ordered-small-vlm-20261109/models/Molmo2-ER/modeling_molmo2.py` | 71559 | `d3cafcb5300dee41dc9b6d6e8b59e7d3b710bce0408672e8fd78a3bcb28669ce` |
| `datasets/model-cache/ordered-small-vlm-20261109/models/Molmo2-ER/config.json` | 2538 | `0030efa549538d7eb29db139aba773417f330a0d2ecacc8dad2b85d72e963391` |
| `datasets/model-cache/ordered-small-vlm-20261109/models/Molmo2-ER/README.md` | 2844 | `a994157d556bd3450d24248d7aea618e537003b5fbc7c6fe392e2530549eccba` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round507-molmoer-transformers-compat-20261109/request.md` | 830 | `46bf2099deb89857ad746df2987b89cd3380b2006fd291728b17cee69e47b121` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round507-molmoer-transformers-compat-20261109/failure-inputs.json` | 3181 | `929678b978d880c4de629f219ab8f42fa62f19851e99b662ffbe91eaa5a5bf21` |
| `datasets/model-cache/ordered-small-vlm-20261109/models/Molmo2-ER/chat_template.jinja` | 3169 | `ec66862fda57dc1aef90a21b2a0f64c18a280e2483206449bd251a73b8993101` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/04-molmoer/download-result.json` | 11037 | `20f8cd908a5588004a6d003c8938c14f06ff2004c8cd7bfe1c03c08a9560ba76` |
| `datasets/model-cache/ordered-small-vlm-20261109/runtimes/molmoer-r505/lib/python3.12/site-packages/baseline.pth` | 98 | `7c6d722cc64172f763eea7587c77feed02217b2a341cb9103f4e887891b1773a` |
| `artifacts/research/process/20261004-t7-parallel-local-models-physics/molmo/Molmo2-cpu-preflight.json` | 1386 | `e8309694da4a16a0e7a7f96a44a63fb4d89fa388071e8ee2ae1ce725b6acb4da` |
| `artifacts/research/process/20261004-t7-parallel-local-models-physics/molmo/environment-freeze.txt` | 1729 | `d9c96a31ef371bbe5f5ce8dd5c2faf67f840cd871e14acb8b13b0b0881ee3aff` |
| `artifacts/research/process/20261004-t7-parallel-local-models-physics/molmo/native_bridge.py` | 21989 | `e8e7c66b31f452e4f95e1508ed5b97cfbb58bff90000211895287b152adf5a22` |
| `artifacts/research/process/20261004-t7-parallel-local-models-physics/molmo/native_adapter.py` | 7280 | `dfac1fce8bd5ac469e5bce14abf8f36d33f6f13252db3dc022bb6eaacc894ff9` |
| `artifacts/research/process/20261004-t7-parallel-local-models-physics/molmo/prepare_environment.py` | 1901 | `3812b268f83a740cfda3f00e2a8848bab3f79a1354411293fceba579a7200cf6` |
| `artifacts/research/process/20261004-t7-parallel-local-models-physics/molmo/.venv/lib/python3.12/site-packages/frozen_vlm_dependencies.pth` | 76 | `0bb32dab2d39f9515ee11b1e734db0204660e1e9e51695e9ee06d143930743d5` |
| `artifacts/research/process/20261004-t7-parallel-local-models-physics/molmo/.venv/lib/python3.12/site-packages/transformers-4.57.1.dist-info/METADATA` | 43991 | `5a7907140118994d1b284d23ea8cda916e6fa8a4d8698aa1d20ab5f59e610590` |
| `.venv-vlm/lib/python3.12/site-packages/transformers-4.48.3.dist-info/METADATA` | 44388 | `2e2780d2f5328a387fd8676aa6fb4d252acf551cb4d5d4eed490b443c5e5eaa6` |
| `.venv-taichu-round473/runtime-b/lib/python3.12/site-packages/transformers/models/auto/auto_factory.py` | 35865 | `de038689f8d999faef4fa5ab77c547c3c93b13d809d329e1a5a613f54da755aa` |
| `.venv-taichu-round473/runtime-b/lib/python3.12/site-packages/transformers/models/auto/modeling_auto.py` | 117562 | `7e1d7f5da77efc95f11531ea2ed7270ffd4e19615c48ed44d9386229a8182988` |
