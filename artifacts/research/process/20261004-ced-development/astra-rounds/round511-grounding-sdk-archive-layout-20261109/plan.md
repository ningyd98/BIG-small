# R511 GroundingPI SDK archive layout Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans，按本轮限定路径执行。用户已授权研究准备；本轮实际 Astra 只规划，不解包、不安装、不导入模型、不加载或生成。

**Goal:** 保留错误解包证据，将同一官方归档放到正确目录，建立只使用官方 Transformers 5.7.0 fork 的独立 GroundingPI CPU 验证环境。

**Architecture:** 归档完整性已通过，修改仅为新建正确解包目的地。新 runtime 通过受控sys.path引用冻结fork、隔离依赖overlay和只读Torch基线；静态依赖约束先于任何模型导入验证。

**Tech Stack:** Python3.12；GroundingPI SDK commit `98641f0b8ed94a091f1457e0e624c49c0ebf3876`；随SDK发行的 Transformers5.7.0 fork/source revision `90dd8674248257e1115e531f2250fd85a32c3863`；只读Torch2.10.0基线。

**Spec:** 本轮 inputs.json/failure.json、R505 plan.json、官方third_party/manifest.json和requirements/serve.txt；planner_model=`gpt-6-astra`；日期2026-11-09。

## 问题、原始RED与核验证据

R505 `diagnostic/grounding-sdk-source-download.stdout` 记录 `TAR_PREFIX LICENSE`；stderr记录 `FileNotFoundError: .../sdk/GroundingPI-98641f0b8e/vendor/transformers/LICENSE`。tar根是LICENSE、src/...，预备脚本却将它解包到vendor父目录，官方manifest期望vendor/transformers。属于归档布局错误，非下载损坏或模型失败；原错误树、原日志及原字节全部保留，不移动、不清理。

规划者已重新核验原6项输入bytes/SHA全部一致；tar 7,944,881 bytes，SHA256 `3b9d4b20efc92041d3d270be1b875a760f7ed2651ba01be59286d1e0ad6d4f25`；tar含2328普通文件、无链接，逐成员内容SHA与manifest `dependencies.transformers.files`完全一致。此结果是只读内存核验，尚未正确解包。当前0 model imports、0 model loads、0 generation。

静态发现的同轮环境前置：官方fork依赖HF>=1.5.0,<2.0，基线HF2.4.0不满足；官方requirements/serve.txt明确固定huggingface-hub1.32.0和regex2026.9.10，基线regex2026.11.7虽满足fork宽约束仍应按官方固定。基线tokenizers0.23.3不满足fork>=0.22.0,<=0.23.0；本轮新增明确固定tokenizers0.22.1（满足官方范围，非声称官方serve文件固定此版本）。先验证对应wheel METADATA对HF1.32.0兼容再安装。依赖闭包尚未实际下载/安装/导入，不声称完整环境已通过。

## 限定范围

唯一SDK新增目录为 `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/vendor/transformers/`。其文件必须与同一manifest精确一致；已存在正确目录则先核验，匹配可复用，不匹配不得覆盖或删除。保留错误 `vendor/LICENSE`、`vendor/src/` 等。禁止修改SDK、tar、manifest、checkpoint、模型源码、官方requirements、历史实验、任何现有venv或基线。

允许全新 `datasets/model-cache/ordered-small-vlm-20261109/runtimes/groundingpi-r505`，及同cache下 `wheelhouse/groundingpi-r511`、`hf-modules-groundingpi-r511`、`hf-cache-groundingpi-r511`。已存在runtime先查来源和完整性，不能静默重建覆盖；未知或已使用状态暂停复核。

允许R505 implementation新增 `prepare_groundingpi_r511.py`、`cpu_groundingpi_r511.py`，tests新增 `test_groundingpi_r511_contract.py`；R511新增evidence、步骤报告，R505 `candidates/06-groundingpi`新增environment-r511、cpu-contract-r511、source-verification-r511、dependency-lock-r511及原始stdout/stderr，最后更新阶段总结。不得修改公共scorer或其他候选。GroundAnything DLM完全不在本轮。

严格使用官方发行fork5.7.0，不替换PyPI5.7.0或5.22.2内建实现；不做注册/类名monkeypatch或禁用版本检查。官方 `models/vlm_compat.py`含源码transform函数，本轮不运行这些transform或准备脚本来改写checkpoint；若实际原生路径必须依赖源改写，应停止并另交Astra，而非以“官方脚本”无限扩权。

## Task 1：从既有RED到正确布局GREEN

- [ ] 重核所有本计划输入与原始失败仍适用。将错误vendor现有文件相对路径、bytes/SHA冻结至evidence（不复制大树）；记录正确目的地当前是否存在。既有FileNotFoundError即RED证据，无需重跑会产生写入的原失败脚本。
- [ ] 写纯合成tar测试验证目的地：rootless LICENSE/src结构正确落入vendor/transformers；绝对路径、..、重复规范化路径、symlink/hardlink、设备/FIFO成员及跨目录逃逸均被拒绝，提取前发现任一非法成员则不写。此处预期RED→最小实现→GREEN是计划内测试。
- [ ] 重新核tar总SHA与manifest；预扫所有成员，要求精确2328普通文件且规范化相对路径集合等于manifest.files。目标及其父路径不能有symlink。使用受控regular-file提取到新建vendor/transformers；不以首层目录名猜strip-components，不解包到vendor父目录。Python tar安全filter可作附加防线，不替代路径/成员检查。
- [ ] 对正确目录逐文件重算SHA并核2328文件、无额外.py（更严格可要求普通文件集合完全相等）；调用冻结的 `models.dependency_contract.verify_dependency('transformers', root=<sdk>)`，预期返回 `90dd8674248257e1115e531f2250fd85a32c3863`。不导入整个模型以验证布局。对原错误树重核其既有文件全部未变化，新正确子目录不纳入旧树比较。
- [ ] 写source-verification-r511.json，分别记录tar匹配、成员预扫、落盘hash、无额外Python、官方contract返回revision以及原错误树保留证据。提取中断保留部分目录和异常，禁止自动删除重试；新根因另Astra。

## Task 2：独立依赖overlay与静态闭包门禁

- [ ] 在新runtime建venv，不写基线。环境路径优先级必须为新runtime自身site-packages、正确官方fork的 `vendor/transformers/src`、SDK根、最后 `.venv-taichu-round473/runtime-b/lib/python3.12/site-packages`；不得加入错误vendor/src。明确受控路径注入方式，关闭用户site和继承PYTHONPATH污染。新的site-packages不得安装别的transformers实现。读取源的fork与底层dist-info5.22元数据不一致须显式报告，不能仅依pip freeze宣称fork版本；以__file__/__version__/源码manifest证明真实来源。
- [ ] 在首次导入transformers前，静态解析官方fork setup.py install_requires、dependency_versions_table.py和dependency_versions_check.py（不执行setup）。列出必要运行依赖、SDK import所需依赖与实际解析版本/来源；只读复用满足约束的Torch2.10、torchvision0.25等，不因部署注释盲装vLLM或训练swift。
- [ ] 通过现有physical-interface helper下载官方PyPI原始JSON元数据和wheel：enp7s0，DNS223.5.5.5/223.6.6.6，trust_env=False，exact allowlist pypi.org/files.pythonhosted.org，TLS校验保持。固定huggingface-hub==1.32.0、regex==2026.9.10、tokenizers==0.22.1；保存URL、原始metadata bytes/SHA、wheel bytes/SHA、官方digest匹配、Python3.12/x86_64 wheel tag证据。可复用已核官方历史tokenizers0.22.1 wheel，但保留来源元数据链；禁止sdist构建和未经审核镜像。
- [ ] 读取每个wheel METADATA/Requires-Dist，按Python3.12/Linux和未启用extras解析完整必要闭包，再用静态specifier检查基线或overlay满足情况。固定三包之外如出现缺失/不满足的直接或传递依赖，本轮不任意挑新版：输出差异与已冻结元数据，交下一Astra限定版本；不先安装再碰运气。若发现固定版本不存在/不支持平台/互不兼容亦如此。
- [ ] 所有静态闭包满足才执行新runtime python -m pip install --no-deps --no-index <已核绝对wheel路径...>；记录完整命令、退出码、安装报告。禁止--target指向原环境、禁止pip自动依赖解析升级基线。安装≤1800s；下载沿用R505恢复/时限边界。
- [ ] 在CUDA_VISIBLE_DEVICES=''、PYTHONDONTWRITEBYTECODE=1新进程核模块__file__/版本：fork5.7.0、HF1.32.0、regex2026.9.10、tokenizers0.22.1、Torch2.10，SDK与fork均在批准路径；记录环境sys.path、必要包dist-info与真实module版本。HF/动态模块cache仅写新目录，offline/local_files_only，无网络兜底。版本/路径门禁不通过则停止，不改sys.modules伪装修复。

## Task 3：真实CPU接口验证与GPU资格边界

- [ ] 在R505冻结checkpoint config/processor/tokenizer/源码与完整asset-manifest基础上，先记录SDK原生入口的确切函数/类及调用路径、实际签名、checkpoint标识/auto_map。使用已冻结官方SDK配置和类，不以通用Auto类能import代替SDK native path。证据不足则NOT_READY。
- [ ] 命令形式为 `CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 <new-runtime>/bin/python <R505>/implementation/cpu_groundingpi_r511.py --sdk <sdk> --model <checkpoint> --out <candidate>/cpu-contract-r511.json`；实现后在执行前冻结确切路径、脚本SHA、参数和输入SHA。每项CPU≤300s，严禁模型实例化/权重加载/generate；CUDA不可见且未初始化。
- [ ] 实际导入官方config和model class，实例化无权重config及官方processor，在R505白名单真实单RGB+原user query上执行原生预处理路径；记录消息/template/hash、图像原字节hash、张量键/shape/dtype/hash、必要坐标/输出合约来源。系统角色/双图仅在官方支持证据存在时做CPU合约，不能由基座能力推断。无oracle、mask、raw depth或历史答案进入模型输入。
- [ ] 运行新增布局/路径/依赖约束测试与R505相关tests，保存退出码、stdout/stderr、期望/实际。官方fork或SDK在配置、类导入、processor、native path发生新的API/ABI/注册/合约失败，保留异常并暂停候选，另交Astra；不能把本轮布局计划扩大为模型兼容性修复循环。
- [ ] CPU PASS仅授予进入R505剩余运行前置检查的资格，不自动开始GPU。真实运行前还须完整权重逐文件SHA、所有软件测试、原生坐标解析/模式/JSON/双图支持、冻结protocol、前序候选状态和资源门禁全部PASS。不得把source extraction、import或processor通过写作模型实测成功。

## 实际运行前置与验收边界

本轮不改变R505研究协议：DEV16原顺序、12正例+4缺目标；原生point/box/mask仅官方支持者；原VisualDecision schema不改；seed0、greedy、beam1、max_new_tokens512；每候选真实调用累计≤134，smoke/debug/warmup也计数。预算不能随R511重置，本次规划0调用。

GPU在官方原生路径和CPU门禁后仍须串行、空闲、实际资源检查：主机可用≥8GiB、磁盘≥60GiB、16GBGPU预估内存可满足冻结精度配置。模型加载≤1800s、单调用≤900s；本轮没有授权额外模型加载、重试、量化搜索或新提示。R505既有原始输出/attempt账本、评分、缺测分母、timeout和新Astra停止规则继续生效。新运行必须由R505冻结runner/protocol实施；本轮不创建通用GPU入口绕门禁。

交付分层：布局GREEN=2328文件与官方manifest一致且原错误树未变；环境GREEN=隔离依赖/真实路径版本与静态闭包满足；开发GREEN=真实checkpoint SDK CPU config/class/processor/native path和相关测试通过；真实screen=另有GPU原始输出才能声明；正式研究/控制/实机验收=NOT_PERFORMED。GroundAnything DLM不在范围。

新增根因、hash差异、意外依赖、源码修改需求、OOM/NaN、范围扩大都先下一实际Astra；历史失败不改字节。实施后写步骤报告并汇入R505阶段总结，验证交付以明确artifact路径提交/推送研发分支，核本地/上游/远端SHA。权重、运行时、SDK、完整raw按既有本地边界保留，manifest不能充当完整远端复现包。

## Review Focus

1. 再次解包父目录：rootless合成测试与目的地完整hash核验。
2. 路径/链接逃逸或覆盖旧证据：提取前全量成员检查，旧树前后hash。
3. sys.path意外选中TF5.22或错误vendor/src：真实__file__断言，不能仅看metadata。
4. HF/tokenizers传递约束冲突：先wheel METADATA闭包核验，再--no-deps安装。
5. import通过被当成真实SDK或GPU通过：分阶段CPU config/class/processor/native path，GPU前置单列。

## 输入清单

原登记6项及本轮扩展输入均逐文件重新核验；manifest再绑定2328归档成员的逐文件SHA，规划者已验证全部匹配。

| Path | Bytes | SHA256 |
|---|---:|---|
| `AGENTS.md` | 1774 | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/plan.json` | 51331 | `16d6d5e722cd30dcb4190f08b5af3685a5a6831a863b3e0a37a8bac528771b93` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/diagnostic/grounding-sdk-source-download.stderr` | 602 | `7000b315101f5ed101115a800a2e2bc9c8dcdfcb620d00abfc8c077f5ad081d7` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/diagnostic/grounding-sdk-source-download.stdout` | 734 | `c69428e4ea1072d1355f02d919a8b20647fb478b10014b5d68eb54be69aea268` |
| `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/third_party/manifest.json` | 743562 | `6ccee676a2de20f7f5dca98719666b50fd9a729316e1eccb81712e3484310156` |
| `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/third_party/transformers.tar.gz` | 7944881 | `3b9d4b20efc92041d3d270be1b875a760f7ed2651ba01be59286d1e0ad6d4f25` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round511-grounding-sdk-archive-layout-20261109/inputs.json` | 1399 | `0204976e21650e07f6a80775aae390223c39b094b5fe0ed2923baf00728955d8` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round511-grounding-sdk-archive-layout-20261109/failure.json` | 420 | `252e455b0fb2e73d3139029a0cd7f1906029a658587ff274e3220a1d3a676c1a` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/diagnostic/grounding-sdk-physical-download.json` | 1362 | `aad6e5c64300f459d6c45a651012c77aa56c3d6bbb11a62f25c9385015bfd344` |
| `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/requirements/serve.txt` | 261 | `f40d0b59e9376cd8539f1c0b2bf09592c9ec8b79a40dbdd3609dd1e53132e084` |
| `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/models/dependency_contract.py` | 1292 | `d5ed906cf2e21b340770e0ced891c042a458c9397ffca568aa508b2c074fd5f4` |
| `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/models/vlm_compat.py` | 13963 | `596b79465af11a416f630eab66c37d294f76ec1c7b3a7d08341d54e9114ac9db` |
| `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/models/README.md` | 445 | `9dc86483bcf1915732a2aef8980ce4c7c683870907536419a16d34f364a9f8d2` |
| `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/models/__init__.py` | 38 | `34a2772225bb2b6fd3b6de3d32b43ea643c36437e2add8c524372f38d9acb9f8` |
| `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/vendor/src/transformers/dependency_versions_table.py` | 3335 | `9bc6dc124e274a74d60d2547b52bd9d5c1af952e2bc0ef8f0be4d77cced06115` |
| `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/vendor/src/transformers/dependency_versions_check.py` | 2099 | `523dcce519f7f0c0e32e0e6af43033d931a739dbe4743a70ad2af11a356e9103` |
| `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/vendor/setup.py` | 13298 | `e22f0582e71edbfc9feb5354851da9a5dd76669bbe07c03bfd8bcd594b95e621` |
| `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/vendor/src/transformers/__init__.py` | 40505 | `f9540fe5a11e5c8d8c23d932de6fbb78273b993f356c0223b6f544588b8f9788` |
| `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/models/vlm/image_processing_groundingpi.py` | 8325 | `0b81c45dbe91473c4370ad8a4f95e56defb92bbcff35f22f85518937da061db7` |
| `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/models/vlm/configuration_groundingpi.py` | 6050 | `feb2c7822fbc4e26ef0793c31bf38407e5cc019f922b867fdeef7c4e17da84f1` |
| `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/models/vlm/streammind_gate.py` | 5564 | `6e4b0d13a6c4108eb8f3b5ad4cd6c7a026cac193d1616cbb74e3c1615200c2cf` |
| `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/models/vlm/configuration_groundingpi_vision.py` | 11734 | `5271ee5625322634fd181d9b4cd47249abf7b97c844baf57544a557f49bffd5d` |
| `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/models/vlm/modeling_groundingpi_vision.py` | 53969 | `fb1243c45e2be50517c867e68bc2eeee7d7cb4341f9846db2f50105ee9d95dd2` |
| `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/models/vlm/media_utils.py` | 14078 | `cd35b564297094520a970dd30555b8af20291746ce30e9b4c33d04eda16f2b09` |
| `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/models/vlm/modeling_groundingpi.py` | 76748 | `c89476c7969ce2115ddb5fa3cace84090ebd2f24216f43c73d4eca51a42bb28b` |
| `datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e/models/vlm/processing_groundingpi.py` | 3207 | `fada769df58fa0d4efd9d4ec45688f6cf01e0c5433539fa9cc888f5615db5fe4` |
| `.venv-taichu-round473/runtime-b/lib/python3.12/site-packages/regex-2026.11.7.dist-info/METADATA` | 40513 | `56d072c8589df8dda537d9bd8e4a25468bce1f201623bb07a6d76dd9621b4f12` |
| `.venv-taichu-round473/runtime-b/lib/python3.12/site-packages/tokenizers-0.23.3.dist-info/METADATA` | 9830 | `87032ea29ec14be956ce0f15d164a8f436d6f1adbe19b261d6c179d9184f5cba` |
| `.venv-taichu-round473/runtime-b/lib/python3.12/site-packages/torch-2.10.0.dist-info/METADATA` | 31092 | `4b0f1217de69037355b4e582905cdb303a56a488ac6fd172f148d88fed634f54` |
| `.venv-taichu-round473/runtime-b/lib/python3.12/site-packages/huggingface_hub-2.4.0.dist-info/METADATA` | 16212 | `b575d5eabe0b381489db2c163bb382f4ef44588ffbf468a4052719bf161b4211` |
| `.venv-taichu-round473/runtime-b/lib/python3.12/site-packages/torchvision-0.25.0.dist-info/METADATA` | 5401 | `b13b6c09eb07623dd666e6eebd6e4af1c9f5c922cbe8be54802aba7931df4ba4` |
