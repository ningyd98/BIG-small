# P1 按已冻结六池准备协议

GPT-6.2 Astra 制定，GPT-6.2 Sol 实施。

R07 三份历史生成器在六池中按 assignment/scene SHA/group 匹配当前 0/3260，recovery 0/200。原独立协议证据 1/200 恢复、0 机会；正式教师 0/9。prepare_generation 只按 seed 再造池，独立证据 CLI 虽可读 pools，却不会生成受源约束的 recovery 调度。

## 原件核对

1. 现池是 3376352 字节的 JSON 映射，原始 SHA e86ac4858fffb0040301c38a0481da7261bece6070e3531cfe9fc2e863c10618。selection/foundation/power/formal/recovery/ood 为 120/120/120/2400/200/300。已对现池执行原 _pool_check、_topology_complete 和 _lock；全行有序 clean content_digest=180653d504596bde8062345452e946e3b655534cc6c0a81aca5f49165da88b8a，现行 rgbd.pool-lock.v2 content_digest=e2fe0f4e442938d37da0b70a30481f11b1fedf7d67b82e52d669fbf762228749。

2. 31/31 R07 原始历史路径的现有字节匹配 reviewed/history.json.entries；其声明范围仅为这些本地来源。对 reviewed history 中 7563 group、6361 scene_hash、7440 physical_key 查交，3260 个输入行三种交集各为零，池内 physical_key 重复为零。协议 evidence reader 从同31件读出7564个组，另一个 canonical_physical_group 为 g-0411d40a765c14987e48c552eb61af80，现池中无该组。开发 lineage 的 parent_sha256、父场景哈希和 SceneSpec.from_parameters 返回的这个组均已实核，原物理键在同一已记录连通分量。用旧 inventory 的 group_ids 原样填 excluded 会触发现行 prepare_protocol_evidence 的 previous <= excluded 拒绝。

## 限定改动

1. 仅在 scripts/generate_rgbd_protocol_evidence.py 的普通 --prepare 上新增可选 --pools PATH，映射到 prepare_generation 的可选关键字参数；显式映射优先作为唯一本次分配来源，禁止把 seed 描述为这些行的生成依据。普通无 --pools 的原 seed、排除后生成/重采样、六个固定 payload、返回语义、继承模式和原 admission 保留。禁止在单纯 preflight、execute 或 successor 中接受外部替换 pools。保持源码/环境指纹真实，旧冻结用其原代码/环境，旧审计与漂移拒绝照常。

2. 显式导入先普通非符号链接文件单次取字节、记录源身份/真实 SHA，与同次解析内容绑定。只接受六个干净池（拒绝 _evidence 或额外键），核拓扑/顺序/完整 row、SceneSpec 重算、id/stratum、扰动和历史排除。按显式历史闭合清单重建 group/scene/物理键，拒绝跨池物理别名、历史别名与物理碰撞；这一路禁止补抽、改名、重排或截断。使用原 canonical _candidate、_fault、_eligible 生成 2400 个候选与 200 调度。导入头登记原字节 SHA 和 clean digest；派生 pools.json 可带原协议所需 _evidence，空两类 source map。输入按原规则不完整时记 BLOCKED_HISTORY 或拒绝，不能 preflight/allocate。

3. 收窄到显式导入历史解析。对真实 lineage 的 canonical_physical_group 以登记的父件字节 SHA、相同 scene SHA、重算的 canonical group 和父 physical key 绑定；沿用已登记显式 sources，不追开任意自由路径。将别名加入 history/excluded 及原连通分量。核对独立 evidence reader 从同组原件读出的全部 group 确已排除；无法验证的引用、缺失父件、矛盾/未闭合别名保持拒绝或 BLOCKED，禁止静默略过或把未解析字符串当物理证明。历史来源覆盖范围照实保留，可另列较新实际运行中有物理共同标识的交集/未知，不能把31件声明成全项目历史。

4. 在原 preflight/_generation_inputs 和合法 successor 继承处按显式来源再验证头绑定、原始 SHA/clean 完整映射/源漂移；不为旧头虚构新键。复用现行 payload/source pin、canonical allocations、旧闭合/预算/排他规则。保持 prepare_protocol_evidence / verify_protocol_evidence 与 freeze_evidence 的全部原接受条件，消费者无需放宽。软件最小修改面为 producer、其 CLI、针对性测试；现实闭合读回和报告落在本轮新目录。

## 验收

1. 先保留现行 CLI 不能按 --pools prepare 的 RED，以及由旧 excluded（7563）使用原 reader 得到的真实未覆盖组；记录输入和新原 stdout、退出码。用 normal CLI --prepare --protocol NEW --pools FROZEN --history-catalog CATALOG，随后对同 NEW 运行原不含 execute 的 preflight，读到对应真实行、首次 ordinal、attempted=0、unattempted=200，无 allocation。验证两个生成分支，历史原件和既有注册源码不回写。

2. 用原 scripts/prepare_rgbd_protocol_evidence.py --pools NEW/pools.json --output NEW_EVIDENCE 再 --verify；两个 CLI 在实际缺样本时均应 INCOMPLETE/退出3、integrity_valid=true、topology_complete=true、recovery_proven=0、opportunity_count=0、2400 missing、valid=false，不能误作失败修绿。由独立读者重新从绑定原件和落盘 protocol 逐池逐序比对完整3260条，重算每条 content_digest、2400候选和200 fault/eligibility，对比 pool-lock、clean digest、SHA 和 foundation 的 evidence-pools 精确比较。区分旧1/200与本池0/200，零机会属于不同批次，各自保留。

3. 反控覆盖同数但替换/乱序或重封单字段、历史重新命名与同物理不同 camera/noise、池内物理别名、外来 _evidence、半池、版本/源内容漂移和 lineage 父件缺失/伪造。无 --pools 回归原 seed 生成和 successor 的同一 allocation ledger/旧 reader，负控不得创造 allocation。运行 protocol generation/evidence 原专项和相关 pilot/freeze 消费回归与代码规范检查，新增实际回执写入步骤报告。

## 后续真实采集

1. 恢复已有入口 generate_rgbd_protocol_evidence.py --execute-once，须绑定经过 review 的同一协议 hash、唯一 recovery assignment、显式 ordinal、全新输出、canonical 已占用记录、renderer/预算及合格正式教师/实际窗口；保留每次失败及缺尾。依冻结规则 TARGET_MOTION 0.02m/s×1s、实测位移≥0.005m、60s恢复窗，reset到terminal逐步物理、作用/命令/执行器、故障与安全全记录，保留原序号最多5/组、已证明后禁重试；正式审计取200个不同组各自首个独立 PROVEN。

2. 机会当前无生产采集器。后续须另建原 assignment 固定 MOVE_TCP 的离线物理 producer，采校准 320×240 RGB/optical-z float32/instance 三通道及同一步三pass原状态、上下文、真实全路径动作/命令与执行器和完整碰撞范围；用原独立 reader 逐案标注 VALID/INVALID/UNKNOWN、查0.25s有效性、半径/8s terminal条件、2400组完整对应及 geometry_applicable，保留 UNKNOWN 及其来源。不能由候选清单、合成 fixture 或既有开发动作替代。机会标签只供 offline_evaluation。

3. 待真实证据审计 COMPLETE/valid、同池 foundation、资源证据和实际 selection/foundation 来源满足原入口后，才绑定 protocol_evidence；selection_evidence 须经真实 selection 独立审计。B0/后续 freeze 实际消费仍按各自真实条件。

## 运行前置

实施前核全输入和31份原字节，真实 selection 配置/冻结外部 pool 路径与三组源数据可读，使用现有 Python 环境和全新本地输出位置。此轮 prepare、preflight、证据归档与 verify 均为 CPU 离线，可与教师独立工作并行。零 BEGIN、物理、渲染、模型与付费调用，保持两个 evidence 字段 null。

源文件、原始失败、历史别名原件及消费者的 SHA256 见同轮 [plan.json](plan.json)。
