# R505 Ordered small VLM screening Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans 按任务执行；本轮仅授权研究 artifact，不授权产品修改。用户已授权按顺序测试，无需另一次形式性批准。

**Goal:** 在现有 16GB GPU 上依指定顺序实测八个候选，分清原生定位、完整 JSON 与双图兼容，交付可复核的 DEV 筛选结果。

**Architecture:** 一个冻结的 v1 DEV16 主集；模型执行进程仅拿到 RGB/指令白名单，离线评分独立读 oracle。每个模型先冻结官方 metadata/SDK 和 CPU 合约，再运行已登记配置；不同输出模态、精度和接口阶段分别报告。

**Tech Stack:** Python 3；隔离 overlay；现有 Torch 2.10.0+cu128 / Transformers 5.22.2 仅为可复用基线，实际兼容需验证；官方 SDK 原字节只读。

**Spec:** `request-and-design.md`。**planner_model:** `gpt-6-astra`（本轮实际 Astra 子代理）；**planning date:** 2026-11-09；**base HEAD:** `025c538935199ea7d3aa8cf15b6e93ac9826cf3a`。`plan.json` 含全部本地输入 bytes/SHA256；未下载官方文件绝不预编 SHA。

## 问题、证据与假设

R497 的同一 S01 帧 JSON 4/4 合法但目标与区域均 0/4 mask 命中，说明格式通过不足以判定定位可用。R501 的 16 场景原始门槛失败为 `AssertionError: (198.329274892807, 240.12212063977495)`，`B_NOT_RUN_TIME`，实际生成 0；这是自设总截止造成的未运行，不能当准确率 0。原报告、失败 JSON 和历史捕获均冻结保留。

假设：专门定位 SDK 可能改善小物体/区域定位；完整任务 JSON 可能引入额外格式失败；单 RGB SDK 不证明双图能力；公开模型名、镜像归属、架构、专用 head 与资源要求须在 metadata 阶段逐个核实。不能未经查证把所有模型塞入同一个 AutoModel 推理类。

补充本轮原始准备失败：`diagnostic/metadata-preparation-failure.json` 记录 runtime-b 缺少 httpx，tool `29b117`，网络请求/模型调用均0。根因是将模型环境误用为网络客户端；本计划直接选择已验证的 `.venv/bin/python`（httpx0.28.1/httpcore1.0.9）执行原 physical-interface helper，不修改模型base。网络纯policy验证已经由实施者完成，实际下载前仍核allowlist。

WeVis SDK已由GitHub connector冻结commit `9a6bcd85404505df0d05cfb5d97512ccacf35dee` / tree `d6995bdc4753875e81d806635aa55c80c90dd4ee`；15文件bytes/SHA在 `diagnostic/wevis-sdk-static-review.json`，本计划再次逐文件核验。其声明Torch2.11/Transformers5.12.1与现有2.10/5.22.2不同，允许在protocol明确登记“版本偏离、未经官方完整栈验证”，以只读SDK sys.path+隔离overlay验证实际HF推理依赖闭包。按源码分支核HF实际需要的Torch/Numpy/PIL、transformers/huggingface_hub/qwen_vl_utils及内部decoder；不因静态可选import就盲装vLLM/demo/scipy/supervision。缺少必要包的首次依赖发现属于本计划预期CPU准备，冻结官方metadata/必要版本并只装overlay；已声明依赖装好后出现ABI/API/合约失败则新Astra轮。绝不修改SDK字节以兼容旧base。最近GPU free14886MiB/no compute app仅为读数，加载前重新核验。

## 全局限制与范围

顺序固定：WeVisOne-VL-4B → WeVisOne-VL-2B → Xiaomi-Lens-0 → Molmo2-ER → RynnBrain1.1-2B → GroundingPI → GroundAnything → MiniCPM-V-4.7-1B。前一模型完成或留下有证据的终止/暂缓状态后再调用下一模型，不因首个好结果停止。GPU 串行；下载/只读 metadata 可提前准备。

仅新增本目录内 `implementation/`、`tests/`、`diagnostic/`、`candidates/01-wevis4b` 至 `08-minicpm`、`report.md`、`phase-summary.md` 与交付清单。产品、既有脚本、共享 index、他人修改、旧证据、默认模型均不改；本地大权重/SDK/raw 在既有研究 CACHE 的 R505 独立子目录，Git 仅显式 artifact 路径。无控制器命令、物理仿真重跑、实机动作或正式验收。

## 主数据与输入隔离

唯一主集为 R501 source-inventory 的原顺序 16 个 v1 捕获：positive-01..12、negative_absent-01..04，320×240，12 正例+4 缺目标。规划时 151 个递归来源文件 bytes/SHA 全部核对通过。旧 DEV20/其他 scene-bank 的 v2 捕获仅作来源对照，既不替换同名 case，也不混入分母；重复 S01 不计独立场景。全为见过的 DEV，不称 heldout。

生成新的 `diagnostic/model-inputs.json` 仅允许 opaque case index、原 RGB 路径/bytes/SHA、原 user instruction、从该指令机械提取的 target phrase 和 destination phrase；推理请求/文件名不带 positive/absent 标签。R501 旧 system 是双图完整 JSON 专用，不用于原生 RGB 阶段。目标 query 统一语义为“Locate {target phrase}; return no detection if absent”；区域 query 为“Locate {destination phrase}; return no detection if absent”，只允许官方原生格式所需包装。每模型原样 prompt、模板、图像预处理、tensor/IDs摘要在第一条真实调用前冻结。mask/instance/raw depth/calibration/旧回答/旧预测/scene palette 禁止进入模型提示、预处理、候选筛选或阈值调参；runner 不加载 oracle 清单。离线 scorer 单独读取。

双图阶段才允许原 RGB + 原 depth PNG，固定顺序；raw depth 不送模型。不重渲染、不更换校准、不用 oracle crop。官方 resize/tile 必须记录并能逆映射至原 RGB；不能把两张图拼成一张冒充原生双图。

## 原生输出、映射与评分

每个官方明确支持的 point / box / mask 模式各自跑完整 16×2 queries；不支持记 UNSUPPORTED，不合成假原生模态。多模式主指标预设优先级 mask→box→point，取第一个官方支持且 CPU 合约可定义的模式；不得看 GPU 分数后换主模式。其他模态分列。SDK 同次返回多个模态可复用同一次原生结果，但不能重复计调用。

`normalize_native(raw, contract, width, height)` 只按冻结的官方坐标语义转换。官方 unit/1000 归一化点按其声明逆变换；连续原图坐标取 floor，精确右/下归一化端点映射 W−1/H−1；非有限、越界、轴反转、未知坐标系均 INVALID，不 clamp 修正。完整 VisualDecision 的 normalized_1000 使用现有 messages.py：合法整数 x,y∈[0,1000] 后 min(W−1,xW//1000)、min(H−1,yH//1000)。box 按官方边界定义还原，派生点为几何中心 floor。mask 采用官方阈值，官方未给时二值概率阈值固定 0.5、logit 固定 0；nearest 恢复原分辨率；派生点为预测前景内距其自身质心最近的像素，平局按 y,x 排序。空输出为拒答，解析异常不是拒答。

多候选按官方单结果规则；若官方无规则，优先原始 score 最高、同分原顺序；无 score 取原顺序第一。不以 GT 选择候选，不跨模态投票。若上述规则无法覆盖 SDK 特殊语义，不临时猜测，停在 CPU 合约并请求下一 Astra 轮。

正例主指标：目标派生点在 object_geom mask、区域派生点在 target_region_geom mask、二者联合命中，分母各 12；额外报告 box 对 oracle 紧框 IoU、mask IoU/Dice，原生模态有效率与每种失败数，不将不同模态 IoU混平均。4 个缺目标分别报告 target 明确无检出率、虚假目标率、无输出/超时率；区域存在，原生 destination query 不是动作建议，不能要求其也无检出。JSON 阶段拒答必须 target=null、destination=null、skills=[]；任意非空 skills 单列“无依据动作建议”，没有执行。

时间从输入预处理前到 CPU 可用最终原生输出，单独记录 load、首条冷态、其余暖态 p50/p90（注明样本数）；记录 peak allocated/reserved 和 nvidia-smi 峰值、RAM、tokens、全部 attempted/completed 调用。3D/抓取率/深度因果使用均 NOT_ASSESSED。研究推进信号仅为某冻结主模式 12 正例联合≥10/12 且4缺目标拒答4/4且完整覆盖；未达标仍完成其他候选，达到也不代表产品通过或统计胜出。

## 预算、资源与停止边界

没有整轮/单模型短总 deadline；允许跨会话长任务，每模型形成独立结果后推进。实测前重查 16GB RTX4070TiSUPER、可用 RAM（总约62GiB）、磁盘（当前约424GB）及 GPU 占用，不终止其他任务。保留≥8GiB主机可用内存、≥60GiB磁盘；预计文件+临时文件+overlay 超余量则 RESOURCE_DEFERRED，不伪称模型失败。GPU 不空闲则挂起等待，不占用它。

单次 metadata 请求 connect≤20s/read≤120s；权重分块可恢复，单个连接无进展120s停止、单下载会话≤6h，每文件最多3个恢复会话；官方镜像失败后最多一个 HF 官方源回退。到限标 DOWNLOAD_DEFERRED、保留 partial/原错误、继续下一个候选，不循环换源。没有整个清单的统一倒计时。

单 CPU contract 300s、依赖安装1800s、模型加载1800s、单次真实 query/JSON 900s。每候选最多一次基线依赖 overlay 建立、最多两次模型加载（一个预登记精度配置的初次加载+进程意外退出后的记录性复核仅在新 Astra 批准时；不自动重试）。BF16 若静态权重/预估内存可容纳则优先；否则在 GPU 前登记一个官方可支持的量化配置。WeVis 的 Qwen3VL 与约9.6M参数 mask decoder 是待 metadata 核实输入要求，vision、mask decoder必须保持专用原精度，明确排除列表；不能用量化整个模型掩盖依赖/加载问题。不强制同候选跑第二精度基准，不混称精度优劣。

每候选最多134次真实推理：原生三模态×32=96；每实际支持模式完整screen后 positive-01 target 原配置重复2次，最多6；完整JSON RGB-only16+真实双图16=32。所有 smoke/warmup/debug 真实调用均必须占对应额度；不得偷偷额外调用。总上限1072，少于上限正常；没有已登记额度以外的生成重试、prompt搜索或采样择优。seed=0、greedy、beam=1；文本 max_new_tokens=512，官方原生固定head使用官方配置。若官方不可表达greedy或需>512，先停CPU阶段交下一Astra。

OOM、NaN、hash差异、未知依赖/ABI、SDK合约失败、解析器/scorer bug及计划外异常：保留原始stdout/stderr/退出码，停止受影响候选，不修到“能跑”；交下一实际 Astra 轮制定修复计划。timeout/truncation/空mask/低分等预登记观测只记录负结果，不调参；两次连续900s timeout终止该候选余项为 NOT_RUN_AFTER_TIMEOUT（不当错误预测计零），继续下一候选。单候选R505内不进行修复循环。需要额外根因轮时保留本轮调用累计账本；新轮不得重置上限。独立候选可继续但不能把暂缓写成已完成测试。

## 任务与运行门槛

### Task 1 — 冻结公共输入与离线合约

- [ ] 新建 `implementation/freeze_inputs.py`：`freeze_inputs(source_inventory: Path, out: Path) -> manifest`；逐文件重验 plan.json输入和图像hash，确认151来源及case顺序，仅生成模型白名单与单独oracle清单。执行前如HEAD已变只复核范围/输入适用性，不覆盖共享修改。
- [ ] 新建 `implementation/score_native.py` 和 `tests/test_contract.py`。先写预期RED：坐标轴互换/端点/out-of-range/NaN、box中心、mask阈值/逆resize/空mask、多候选tie、absence与异常区别、GT泄漏哨兵、同名v1/v2混用、严格JSON无修复；实现转换与评分后CPU测试通过。oracle合成测试可用，但不能把oracle传模型。
- [ ] `python3 -m pytest <本目录>/tests -q` 全通过，输出case清单、每项失败与hash报告；公共合约完成后才准入候选GPU。

### Task 2 — 按序官方发现、下载、CPU contract（每候选一次）

- [ ] `candidates/<id>/protocol.json` 在权重运行前追加登记：确切官方repo/作者、revision、license、配置架构、SDK commit与原文件bytes/SHA、官方任务入口及函数签名、点框掩膜原生支持、双图支持依据、依赖lock、精度/module排除列表、下载完整文件清单/大小/hash、提示及预处理/坐标/threshold/output解析规则、调用账本和阶段顺序。它是本计划预授权的参数绑定，不得改公共数据/门槛/预算。未知项不能填猜测值；metadata发现未完成则 NOT_READY，不生成。
- [ ] 先 ModelScope 官方同名镜像，核发布主体与原repo版本关系；无法证明同版则明确镜像revision与差异，不声称等价。必要HF官方回退写原因。复用 `src/cloud_edge_robot_arm/datasets/external/network.py` physical-interface helper：enp7s0、DNS223.5.5.5/223.6.6.6、trust_env=False、exact域名allowlist（包含经审核的确切redirect域名）；不开放任意host、不改全局网络策略。每个下载文件实际核bytes/SHA；SDK归档/source、专用decoder文件和原始依赖原文一同冻结，不改官方字节。
- [ ] 新建该候选研究adapter，使用已核实官方API，不臆造通用类；overlay隔离安装，冻结pip/package/source manifests。CPU contract验证原生processor可处理白名单图像、输出转换合成边界、decoder存在、量化排除模块、oracle不入参。仅在官方API确有双图路径时验证两张独立图像与processor各自张量/token占位并冻结hash。公开单RGB的WeVis/Lens/GroundingPI默认dual=UNSUPPORTED；只有新冻结源码明确独立双图路径且CPU合同通过才可升级，不靠底层基座宣称。
- [ ] `cpu-contract.json`记录命令/实际环境/每项PASS。官方SDK要求超出已登记能力、需修改源码或专用新推理算法时，停止该候选并交新Astra计划，不将protocol当作无限扩权。

### Task 3 — 原生GPU定位、JSON与双图阶段

- [ ] CPU合约PASS、完整权重hash PASS、资源PASS、协议hash冻结后运行 `implementation/run_candidate.py --protocol <path>`，一次仅一个模型。每模态按16case顺序逐case先target后destination，先完整主模式再其他支持模式。每次追加不可覆盖的attempt记录，保存原始输出/IDs/mask/log和资源采样；完成完整screen后才做两次暖态重复，不参与准确率分母。
- [ ] 原生阶段正常完成后，如官方接口确实支持自由文本chat，独立跑 `JSON_RGB` 16次；系统文本取冻结原schema说明，将图像说明明确改为仅RGB，其余任务不改；禁止强制补skills、围栏清理、JSON修复或R497约束解码移植。非chat SDK记 JSON_UNSUPPORTED，不构造伪原生完整JSON。
- [ ] 若独立双图CPU合约PASS，使用R501原system/user与RGB+depth原图跑 `JSON_DUAL` 16次；否则记 DUAL_UNSUPPORTED/NOT_VERIFIED。两阶段不依定位分数择优，按兼容性执行。JSON schema/完整拒答/空间命中分别评分，单图与双图并列不混分；双图接收成功不等于实际使用深度。
- [ ] 每候选输出 `result.json`、`report.md`、raw manifest与步骤证据；调用总数≤134，无原始输出丢失，分母与missing一致。终止时明确metadata/download/CPU/load/generation/scored各阶段状态，未运行不写0准确率。

### Task 4 — 阶段交付与比较

- [ ] 每候选完成或有证据终止后更新本目录 `phase-summary.md`，所有八候选均有状态后形成 `report.md` 比较表：同一v1 DEV16/同一模态和配置的可比指标；不同精度/模态/缺测显式标注。不以CPU通过替代GPU，不以DEV通过替代实机或正式研究验收。
- [ ] 使用独立研发分支与临时 `GIT_INDEX_FILE`，以批准base树和显式R505 artifact路径构造提交；不 checkout/reset 共享工作树、不git add -A。先核提交仅包含本轮允许文件，再推送并核本地提交、上游ref、远端SHA一致。SDK/模型/完整raw和环境本地留存，派生manifest不是完整远端复现包。

## Review Focus与验收边界

重点核验：同名case跨v1/v2串用；oracle进入提示/裁剪/候选选择；坐标轴/resize/边界转换错误；mask专用decoder被遗漏或量化；单RGB接口被说成双图。各自在Task1测试、Task2源码/CPU合约和Task3真实记录中验证。

计划交付=两份计划与本地输入清单可核验；软件验证=CPU测试结果；真实screen=有完整原始输出的实际GPU调用；正式研究/控制/硬件验收=未进行。候选全部有状态不等于全部已实测。当前计划制定不执行下载、安装或GPU，不宣布任何新模型通过。
