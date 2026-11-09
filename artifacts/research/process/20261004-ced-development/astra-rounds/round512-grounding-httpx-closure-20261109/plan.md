# R512 GroundingPI HTTP dependency closure Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans；用户已授权最小依赖补全及继续R511 CPU gate。本轮实际Astra仅规划，不下载、安装或执行模型。

**Goal:** 在GroundingPI独立runtime补齐httpx0.28.1/httpcore1.0.9，完整静态依赖闭包PASS后才安装，并恢复R511官方SDK CPU门禁。

**Architecture:** 保留R511原锁与布局证据，新增R512锁；只读复用满足要求的基线包。官方PyPI metadata/wheel逐字节冻结，--no-deps仅安装已批准固定wheel到新runtime。

**Tech Stack:** Python3.12/Linux x86_64；官方GroundingPI Transformers5.7.0 fork；R511 HF1.32.0、regex2026.9.10、tokenizers0.22.1；新增httpx0.28.1、httpcore1.0.9。

**Spec:** 本轮request.md/inputs.json、R511 plan.json、R505候选dependency-lock-r511.json；planner_model=gpt-6-astra；2026-11-09。

## 问题、原始证据与核验

R511锁状态DEPENDENCY_NOT_READY，记录huggingface-hub1.32.0的 `httpx<1,>=0.23.0` 缺失，installation_started=false。这是本轮原始RED，不重复安装来重现。SDK布局修复和2328源码核验已有source-verification-r511.json，保留既有7测试PASS证据；本轮不重复解包。

规划者核验原2项登记输入bytes/SHA一致；重新哈希R511三wheel并读取其METADATA，Requires-Dist均与锁完全相同。基线静态metadata确认httpx/httpcore均无分发记录；anyio4.16.0、h11 0.16.0、idna3.20、certifi2026.10.23、typing_extensions4.16.0存在。anyio实际Requires-Dist只在当前Python3.12启用idna>=2.8、typing_extensions>=4.16.0；exceptiongroup分支为Python<3.11，不启用；trio为未请求extra。anyio当前metadata没有sniffio依赖，不能凭旧版本记忆盲装sniffio。

httpx0.28.1/httpcore1.0.9本轮尚未下载，因此其准确Requires-Dist、wheel SHA和Python约束须以Task1实际冻结metadata为准，不预编SHA或宣称闭包已通过。当前安装、模型导入、权重加载、生成均未由本规划者执行。

## 范围与禁止项

只新增 `datasets/model-cache/ordered-small-vlm-20261109/wheelhouse/groundingpi-r512`；R505 candidates/06-groundingpi下 `httpx-r512-pypi.raw.json`、`httpcore-r512-pypi.raw.json`、`dependency-lock-r512.json`、安装/环境/CPU输出；R512 evidence、steps-report；可新增R505 implementation/prepare_groundingpi_http_r512.py和对应tests/test_groundingpi_http_r512.py。只向R511已授权独立runtime `runtimes/groundingpi-r505`安装。

保留R511 dependency-lock、下载metadata、stdout/stderr和测试结果原字节。禁止修改任何基线、SDK、fork、checkpoint、版本检查或注册；不允许追新版、pip自动依赖升级、切换Transformers实现或执行SDK源码transform。R511所有其余范围和停止边界继续适用；GroundAnything DLM不在范围。

## Task 1：冻结新增wheel及完整传递闭包

- [ ] 执行前重核本计划输入、R511三wheel、官方fork2328文件验证状态、runtime尚未安装状态；如已有并行写入先复核适用性，不覆盖证据。
- [ ] 通过既有physical-interface helper获取 `https://pypi.org/pypi/httpx/0.28.1/json` 和 `https://pypi.org/pypi/httpcore/1.0.9/json`，保留响应原字节、URL、状态码、bytes/SHA及可追溯wheel URL；enp7s0、DNS223.5.5.5/223.6.6.6、trust_env=False、exact allowlist pypi.org/files.pythonhosted.org、正常TLS。沿用R505连接/下载时限；不开放任意域名。
- [ ] 每包选择官方兼容Python3.12/Linux x86_64 wheel，要求固定版本、metadata官方digest与下载SHA匹配、大小一致。仅wheel，无sdist构建。保存wheel内部METADATA原字节/hash、Requires-Python、Requires-Dist和wheel tags。官方版本不可用、hash不符或平台不符立即保留证据并下一Astra。
- [ ] 静态按当前Python/平台、extra为空解析完整必要依赖图：以R511三wheel、新两wheel以及fork runtime必要依赖为根；每个依赖记录parent、原始Requires-Dist、marker判定、选中版本、来源路径/metadata SHA、specifier PASS/FAIL。必须递归检查基线anyio等的Requires-Dist，不能只检查新增包第一层。
- [ ] 固定选择httpx0.28.1、httpcore1.0.9；预计基础传递包来自已有anyio、certifi、h11、idna及typing_extensions，以实际新wheel metadata最终判定。已有版本满足则只读复用，不下载安装副本。sniffio未被有效marker要求时不安装；若实际wheel metadata出现本计划未覆盖的缺失/不满足传递依赖，输出准确约束后下一Astra，不猜版本。HTTP2/socks/brotli/zstd/cli/testing等未请求extras不得启用。
- [ ] 纯静态测试覆盖：原R511缺httpx判FAIL；只有httpx仍缺httpcore判FAIL；模拟两包及满足的基线递归图判PASS；已满足包只读；Python<3.11/extra依赖正确跳过；缺失依赖不能被忽略；同名包选择实际overlay优先级。预期RED→最小实现→GREEN属于本轮允许。
- [ ] 新建dependency-lock-r512.json引用R511锁SHA；在全部根及传递节点PASS且no unresolved记录时才标STATIC_CLOSURE_PASS。没有安装前闭包PASS就不能运行pip。

## Task 2：隔离安装及真实来源验证

- [ ] 在R511新runtime执行 `python -m pip install --no-index --no-deps <R511已核三wheel绝对路径> <R512已核两wheel绝对路径>`；安装前记录精确命令和wheel SHA。单次安装≤1800s，不指向现有venv，不允许pip联网或resolver升级基线。
- [ ] 保持R511路径顺序：独立runtime site-packages优先，再官方vendor/transformers/src、SDK根，最后只读Torch2.10基线；不引入错误解包vendor/src。关闭用户site与继承PYTHONPATH污染，PYTHONDONTWRITEBYTECODE=1，HF缓存仅写R511独立路径。
- [ ] 在CUDA_VISIBLE_DEVICES=''新进程依次验证实际httpx/httpcore/HF/regex/tokenizers导入版本及__file__来自新runtime，anyio/h11/idna/certifi/typing_extensions来自只读基线；实际fork版本5.7.0及__file__来自正确官方目录，Torch来自2.10基线。记录distribution metadata与module版本，不能把底层transformers5.22 dist-info当运行中的fork。
- [ ] 静态闭包通过而导入出现新API/ABI、缺包或路径问题，保留stdout/stderr/退出码停止，不修改版本检查或临时追加包。新根因交下一实际Astra。

## Task 3：继续R511 CPU gate

- [ ] 重新冻结R511 CPU脚本、SDK、checkpoint config/processor/tokenizer和输入hash；运行R511指定官方config、模型class导入及真实单RGB原生processor/SDK path合约。不得实例化模型、load权重或generate，CUDA不可见且未初始化；每项CPU≤300s。
- [ ] 保存实际类/模块路径、原消息与模板hash、图像hash、张量键/shape/dtype/hash及native path证据；输入只用R505白名单，不含oracle、mask、raw depth或旧答案。任何配置/模型类/processor注册或API新失败都停在CPU并交下一Astra。
- [ ] 新增依赖闭包测试和受影响R511测试PASS后形成步骤报告；软件验证、CPU接口、真实GPU和正式研究分别写状态。R511源码布局通过不能代替CPU通过，CPU通过不能代替模型实测。

## 真实运行前置与验收边界

本轮没有GPU调用授权增量；继续R505真实screen仍须完整权重SHA、冻结native协议/坐标与模式支持、相关测试、前序候选状态和实时资源门禁全PASS，才能依R505 runner执行。所有调用继续计同一候选累计≤134，seed0、greedy、beam1、max_new_tokens512；没有额外smoke或调参额度。R511禁止源码修改、R505原schema和DEV16边界不变。

本计划验收=两份计划、输入核验和明确范围；开发验收=完整静态闭包PASS、隔离安装与来源断言、真实CPU合约PASS；实际GPU=仅真实原始输出可证明；正式研究/控制/实机=NOT_PERFORMED。原始R511锁保留DEPENDENCY_NOT_READY，新R512证据不得覆写历史。

hash差异、未覆盖依赖、安装/导入/API失败、范围扩大立即保留证据并下一Astra。独立不受影响工作可继续。已验证交付按明确artifact路径提交推送研发分支并核本地/上游/远端SHA；wheel、环境和完整raw依既有交付边界，派生锁不是完整远端复现包。

## Review Focus

1. 只补httpx却漏httpcore：递归闭包及缺httpcore负测试。
2. 凭旧anyio记忆安装sniffio：真实metadata与marker证据决定，不盲装。
3. --no-deps掩盖缺失：安装前强制全图PASS。
4. 导入基线错误版本：新进程真实__file__/版本断言。
5. CPU通过冒充GPU成功：分层验收，调用账本仍为实际计数。

## 输入SHA清单

| Path | Bytes | SHA256 |
|---|---:|---|
| `artifacts/research/process/20261004-ced-development/astra-rounds/round511-grounding-sdk-archive-layout-20261109/plan.json` | 10218 | `c5ec2c5a56c4021d010e197eb82d0d08334209f9bbdc0fe292df5b14e9cd29d5` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/06-groundingpi/dependency-lock-r511.json` | 7992 | `8fa8961e9eb57ea40608d6da34e2bcdccbe969516259d1b31aa3efac59802e80` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round512-grounding-httpx-closure-20261109/inputs.json` | 534 | `9deeeb9b3f58c063bb4355300231cf22a1cc37641ec95dc01f95189327500dba` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round512-grounding-httpx-closure-20261109/request.md` | 502 | `8853c873aa2247d9ea29d2b2dd0884ad60b600a7f63b28b8b947652fb7cb6d57` |
| `AGENTS.md` | 1774 | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/06-groundingpi/source-verification-r511.json` | 389677 | `18cbb0b05e6489a4875d2929f81672d92d60030be9f4c501ae884742b53abf3a` |
| `.venv-taichu-round473/runtime-b/lib/python3.12/site-packages/typing_extensions-4.16.0.dist-info/METADATA` | 3310 | `b05084ca1d50879865178d9fff9fabeab61bdfb1f361bfbde95421ffc8f9be46` |
| `.venv-taichu-round473/runtime-b/lib/python3.12/site-packages/idna-3.20.dist-info/METADATA` | 7207 | `dbd8c14c1e4ca1e0c9824a6dbc7cbbf78884f38eb52d91148cd3025f671e4b85` |
| `.venv-taichu-round473/runtime-b/lib/python3.12/site-packages/h11-0.16.0.dist-info/METADATA` | 8348 | `28f326098ac09fcba79b8f180f96087c841fe2456215cb7b872a9c7d5cd19d64` |
| `.venv-taichu-round473/runtime-b/lib/python3.12/site-packages/anyio-4.16.0.dist-info/METADATA` | 4733 | `b184ac9cd097e2bb7f90d42799346cc91c276095d000d95d7f7ddd407d0c887e` |
| `.venv-taichu-round473/runtime-b/lib/python3.12/site-packages/certifi-2026.10.23.dist-info/METADATA` | 2526 | `e463e38f7fe7da36a11e6d3fecc5dfa5b97be8c8022620400750d79ae7d842bc` |
| `datasets/model-cache/ordered-small-vlm-20261109/wheelhouse/groundingpi-r511/huggingface_hub-1.32.0-py3-none-any.whl` | 842906 | `b0c7c80561969d9cdacdd55fce67ba9584cca0b9d4ea80957a3a5c1445fac5c8` |
| `datasets/model-cache/ordered-small-vlm-20261109/wheelhouse/groundingpi-r511/regex-2026.9.10-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl` | 804587 | `2e67f8843f0e4b931f1fa860bf3bbe4134b714c0155cc5c7c0d7ea450230aae0` |
| `datasets/model-cache/ordered-small-vlm-20261109/wheelhouse/groundingpi-r511/tokenizers-0.22.1-cp39-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` | 3250221 | `e2ef6063d7a84994129732b47e7915e8710f27f99f3a3260b8a38fc7ccd083f4` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/06-groundingpi/huggingface-hub-r511-pypi.raw.json` | 17498 | `3e77db4a0f2784f42eca1aa1a2a3391a06bdb4d23c88109ab960a3ddff1f9879` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/06-groundingpi/regex-r511-pypi.raw.json` | 156896 | `faaecf25cf7f42d5669c3ee18eb7bdaa02247d247ac6d26f1ef7019da5853381` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/06-groundingpi/tokenizers-r511-pypi.raw.json` | 20400 | `5fd51a6c16e2c277a4ac5e25e242514cc09ba0449b99be518fb25c31465f866b` |
