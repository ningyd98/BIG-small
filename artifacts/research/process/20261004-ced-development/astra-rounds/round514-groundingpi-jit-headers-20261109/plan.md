# R514 GroundingPI JIT Python headers Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans；本轮实际Astra仅规划。用户已授权限定环境修复及门禁通过后的第二次、最后一次BF16加载，无需另一次形式性批准。

**Goal:** 让官方MoonViT原生torch.compile/Triton使用既有冻结Python头文件，先通过CPU编译链门禁，再完成原协议100请求。

**Architecture:** 仅在新子进程设置已验证CPATH与候选自有JIT/TMP目录；原始SDK/模型/编译与attention路径不改。新runner/protocol/run-02追加记录，以原失败1次生成为累计预算起点。

**Tech Stack:** 原GroundingPI runtime、Torch2.10.0+cu128、官方Transformers5.7.0 fork、原Triton和gcc；冻结headers-round489。

**Spec:** 本轮inputs.json、R505候选protocol.json/run-01.json/CPU contract、Lens invocation-01、R489头文件清单；planner_model=gpt-6-astra；日期2026-11-09。

## 原始RED、证据与根因

首轮run-01状态FAILED_NEW_ISSUE：model_loads_started=1，load_s=1.75483710799017，generation_calls_started=1，completed=[]。因此权重加载已成功、第一次生成确已尝试；不能改写成零调用，也不能把未完成预测计准确率0。

launch-01.stderr原始 `fatal error: Python.h: No such file or directory` 出现在Triton cuda_utils.c:7；官方MoonViT get_rope_shape的torch.compile触发Triton CudaUtils，其源码从Triton backends/nvidia/driver.c读取，再由runtime/build.py用gcc -shared编译。命令仅含系统/usr/include/python3.12，当前调用没有Lens已验证的冻结CPATH。根因是子进程缺少Python开发头文件搜索路径，不是BF16加载、注意力算法或提示问题。

原7项登记输入bytes/SHA全部匹配；CPU contract状态PASS且恰好100 requests。原协议CPU hash `6933b444f6888ccc817edef071bc419c8ca461f4ba30498f4126216969535fe7` 和公共输入hash `f413ce5693f7c68b8830e558fa50fb54282f2fd1b44bda13cc55d7c3cdc614de`必须保持。规划者重新核验R489清单中全部usr/include文件；详见JSON输入，未编译或加载模型。

## 修改范围与固定环境

新增R505 implementation `preflight_groundingpi_jit_r514.py`、`run_groundingpi_r514.py`、tests/test_groundingpi_r514.py；新增候选 protocol-r514.json、invocation-02.json、run-02.json、run-progress-r514.local.json、jit-preflight-r514.json和步骤报告。原run_groundingpi.py、protocol.json、run-01.json、invocation-01和actual/run-01全部保留原字节。

原始输出新增到 `datasets/model-cache/ordered-small-vlm-20261109/actual/06-groundingpi/run-02`，launch-02.stdout/stderr与旧launch-01分离。新增候选自有 `datasets/model-cache/ordered-small-vlm-20261109/jit/06-groundingpi-r514/{preflight,triton,inductor,tmp}`。目录存在非空则核来源，不清理重用或覆盖未知产物。冻结headers-round489只读使用，不下载或安装新头文件，不改系统include/sysconfig，不建系统symlink。

子进程CPATH必须与Lens成功invocation中的三个路径顺序一致：

`/home/ningyd/文档/ChatGPT/BIGsmall/datasets/model-cache/zdtaichu5-9b-fp8-round473/headers-round489/usr/include/python3.12:/home/ningyd/文档/ChatGPT/BIGsmall/datasets/model-cache/zdtaichu5-9b-fp8-round473/headers-round489/usr/include/x86_64-linux-gnu/python3.12:/home/ningyd/文档/ChatGPT/BIGsmall/datasets/model-cache/zdtaichu5-9b-fp8-round473/headers-round489/usr/include`

TRITON_CACHE_DIR指向上述triton，TORCHINDUCTOR_CACHE_DIR指向inductor，TMPDIR指向tmp；预检工作产物保存在preflight。不复用Lens/R489 JIT缓存，PYTHONNOUSERSITE=1、PYTHONDONTWRITEBYTECODE=1；保留原runtime/HF offline及IMAGE_MAX_TOKEN_NUM=512。除批准变量外，不注入TORCH_COMPILE_DISABLE、Dynamo suppress_errors、attention fallback或改变编译配置。

禁止改torch.compile装饰器/函数、Triton/torch源码、SDK/fork/模型/attention/精度、prompt、顺序、阈值、坐标解析器或原VisualDecision schema；不禁用编译，不走eager替代或其他后备路径。无新依赖安装。

## Task 1：CPU原始driver C编译门禁

- [ ] 实施前重新核7原输入、CPU contract和全部research_sources、R489头文件manifest及实际header SHA；记录运行Python版本/ABI、sysconfig EXT_SUFFIX、GCC真实路径/version/hash及header Python版本。头文件须适用于当前CPython3.12 amd64，版本/ABI不符则停止，不编辑header。
- [ ] 保存原RED，不重新调用模型复现。预检子进程CUDA_VISIBLE_DEVICES=''，不import模型、调用triton.runtime.driver.active、创建CUDA上下文或发射kernel；仅读取已冻结driver.c原字节。
- [ ] 在候选preflight目录复制原Triton driver.c字节为cuda_utils.c并核SHA相同，使用原失败gcc命令参数（-O3 -shared -fPIC -Wno-psabi、原Triton include/lib、libcuda.so.1、系统python include）只替换源/输出临时路径，叠加批准CPATH。链接系统已有libcuda不构成GPU调用。编译≤300s，保存argv/env、stdout/stderr、returncode、耗时、源与.so SHA。不要调用compile_module_from_src自动导入.so；本门禁只编译/链接，不运行扩展。
- [ ] 用同源码/同include及CPATH做gcc依赖清单或include trace，保留Python.h→pyconfig.h等实际解析路径，确认来自冻结header链且无伪造header。成功标准：原source字节一致、编译退出0、生成非空正确架构的.so、header解析可追溯。可用readelf只读确认架构，不能以存在旧.so代替本次编译成功。
- [ ] 本轮允许CPU编译验证失败的唯一预期RED是已有Python.h错误和新测试的预期断言；新编译/链接错误、缺其他header、ABI差异或工具链改变即保留原证据并下一Astra，不临时追加包/路径。预检PASS只证明C扩展构建链，不证明后续所有Inductor kernel都可运行。

## Task 2：新runner、协议与累计账本

- [ ] 从原run_groundingpi.py复制为run_groundingpi_r514.py，仅改protocol/output/progress目标和累计预算守卫；保留原加载、processor、生成、解析、资源门禁与输入hash断言。提交前保存差异，要求无模型推理语义变化。原research_sources仍全部核验，并将新runner哈希追加到新协议，不能删除旧source核验。
- [ ] 新protocol-r514.json完整继承原数据/CPU contract/hash、native box+point顺序、JSON_RGB/JSON_DUAL、BF16、sdpa、thinking=false、generation kwargs；只追加R514计划hash、env/JIT路径、前次run hash和累计账本字段。100 request列表及每项rendered/features hash完全保持，不重新生成提示。
- [ ] 明确账本：prior_model_loads_started=1、prior_generation_calls_started=1、prior_completed=0；current_run_model_load_cap=1、current_run_generation_cap=100；cumulative_model_load_cap=2、cumulative_generation_cap=101（仍小于R505硬上限134）。旧attempt保留FAILED_NEW_ISSUE，本轮重做首请求是第2次累计生成，不覆盖第1次。新run本地请求编号1..100，另保存cumulative index2..101。
- [ ] 每次load和generate之前先持久化累计STARTED计数；达到2次累计load后禁止任何第三次加载，达到101次累计generation后禁止继续。当前run最多100次，不因旧失败再补第101个新请求；没有smoke/warmup/debug额度。assert前次真实账本仍是1/1/0；与预期不同立即停止重新审计。
- [ ] 测试先RED后GREEN：旧1+新100允许且第101个新调用拒绝；旧1+新1 load允许且第三次累计load拒绝；原100输入/hash完全相同；原文件不可覆写；输出只落run-02且创建使用exclusive规则；env只允许本轮白名单变化；本地和累计索引不混淆。测试不加载模型/调用GPU。

## Task 3：第二次且最后一次真实运行

- [ ] CPU编译PASS、新runner差异审查/相关测试PASS，全部权重/官方源码/依赖/输入/协议哈希重新核验后才能运行。确认旧进程退出且无CUDA占用，取得既有共享GPU锁；不终止其他任务。沿用原准入：GPU空闲且free≥12000MiB，RAM available≥8GiB、磁盘free≥60GiB；记录实际读数。
- [ ] 在任何torch/Triton导入前设置冻结env，保存invocation-02.json（完整argv/cwd/env、各hash与stdout/stderr路径）。一次BF16模型加载≤1800s，加载方法/attention与原协议一致；这是累计第二次且最后一次load。
- [ ] 按CPU contract原100 requests顺序执行（原生box32+2重复，point32+2重复，JSON_RGB16，JSON_DUAL16），seed0、greedy、num_beams1、max_new_tokens512、use_cache=True。各请求先核实际processor features与rendered hash再generate，单调用≤900s。无额外JIT模型预热；首生成包含本轮真实JIT代价，CPU编译预检耗时另列，不声称端到端无预热冷启动。
- [ ] 保留所有started/generated/completed/failed、原文本/token IDs、GPU/RAM资源与冷暖态耗时；若新torch.compile/Triton/模型/解析器异常立即停止，保留账本与raw，下一Astra，不再load或fallback。原低分/截断按R505负结果记录；不改提示/阈值挽救结果。
- [ ] 完成时报告累计load2、generation≤101和实际completed数量；原失败1不纳入准确率分母，不当预测0，不从运行可靠性账本删除。软件测试、原生/JSON真实输出、空间命中与正式验收分开。JSON双图接收不等于depth因果使用，3D/控制/实机未评估。

## 验收与停止边界

计划完成=输入SHA核验和两份计划写入；开发通过=原始driver C在冻结header链CPU编译通过+新runner预算/路径测试通过；真实筛选=run-02原始GPU输出与100请求状态可核验；正式研究/硬件=NOT_PERFORMED。任何新根因、hash变化、范围扩大、GPU异常先下一实际Astra，不能复用本轮授权无限重试。

实施结果写R514步骤报告并汇入R505阶段总结。已验证交付显式artifact路径提交/推送研发分支后核本地/上游/远端SHA；原失败、raw、SDK、权重与JIT产物按既有交付边界保留。manifest不是完整远端复现包。

## Review Focus

1. CPU预检偷偷初始化CUDA：仅gcc构建原C源码，禁止driver.active及.so加载。
2. 旧缓存掩盖编译问题：候选独立目录，实际命令/退出码/产物SHA。
3. 改runner重置预算：前次1load/1generation+新run累计守卫及测试。
4. 调整环境顺带改变推理：严格env白名单、原请求/features/hash相等。
5. 失败调用消失或当0准确率：原run保留，可靠性与评分分母分列。

## 输入SHA清单

plan.json列出所有逐文件输入SHA，包括完整冻结头文件链；下表为原始登记输入及新增直接证据，头文件明细在JSON中避免重复。

| Path | Bytes | SHA256 |
|---|---:|---|
| `AGENTS.md` | 1774 | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/06-groundingpi/run-01.json` | 17042 | `ffa025ffd76ec71e24b9b5f9d5f29456cef9465fed3751cc1f0bfe3c2d2f1c9a` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/06-groundingpi/protocol.json` | 3616 | `0107831262943dbcdd946b9690d88fccbb80d2d26fd919ed70d2e63fe763f134` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/06-groundingpi/invocation-01.json` | 561 | `3da1b3ded360a092db34f8b8c45e53e4eb9b6ee54a39ea4651168e895eaf2f95` |
| `datasets/model-cache/ordered-small-vlm-20261109/actual/06-groundingpi/launch-01.stderr` | 16326 | `870084794637fc0760a5a674b52b7fc1626b389c3ef15ffc4730494c8fe90bc2` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/implementation/run_groundingpi.py` | 8474 | `78fb494d27395b7e72ec8c4b6a4b8acea76ebf1c701f07a4a75f860a4cff55f6` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/03-lens/invocation-01.json` | 1669 | `2d71a58425fdc35eeaa10fed655e23062527b95bd9aeb62fff3443b628928873` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round514-groundingpi-jit-headers-20261109/inputs.json` | 1704 | `6ba31842708ed4763750119996fcd3ce13c6e82ddba4430538be07d81c3e680a` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/06-groundingpi/cpu-contract-r511.json` | 204606 | `6933b444f6888ccc817edef071bc419c8ca461f4ba30498f4126216969535fe7` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round489-taichu-isolated-jit-headers-20261108/header-manifest.json` | 42714 | `cbfb13bd389817121b44d4ea0ef03e0de34b9895bb35eb374b6b8c31852128e8` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round489-taichu-isolated-jit-headers-20261108/header-preparation.json` | 1002 | `4b2c79e45b0ea75163881d0e259c559117edc83c32714043ae8747197cb94fb1` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round489-taichu-isolated-jit-headers-20261108/step-report.json` | 9371 | `a399f74e8b20831f3aede8bc07fcb3f9ebb5bb44c1ed617f0017e09aa3d2cb03` |
| `.venv-taichu-round473/runtime-b/lib/python3.12/site-packages/triton/runtime/build.py` | 3928 | `26c6ddd4dba3534ce54790f12d2b75729f51e467c48b2f740dd62b7c75a85b39` |
| `.venv-taichu-round473/runtime-b/lib/python3.12/site-packages/triton/backends/nvidia/driver.py` | 25625 | `4ad4b4440aa4a5ee15ac2382ae78a7aa8029986c22ec2acbd072a91810e85e94` |
| `.venv-taichu-round473/runtime-b/lib/python3.12/site-packages/triton/backends/nvidia/driver.c` | 19555 | `439c1e886fa9eac7346d7523d03ba0a4c52aa4c9b518ea86d8659b5c07eb7dc9` |
