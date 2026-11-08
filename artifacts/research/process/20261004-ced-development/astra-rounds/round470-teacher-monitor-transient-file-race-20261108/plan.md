# R470 teacher 监督器临时文件竞态修复与一次替代运行

实际规划者 `gpt-6-astra`；PLAN_FROZEN_NOT_EXECUTED。用户“开始真实运行”的持续研发授权覆盖本轮限定修复及一次有界替代开发采集，无需额外确认。这不是R468 retry0的自动重试：R468的claim/原件和失败永不重开，R470由本轮Astra明确重新冻结一次新尝试，累计最多2次真实attempt，不能称总attempt1或独立校准重复组。

## 原始失败与根因

R468 full真实launched，约4.088秒后监督器file_bytes在os.walk已列出runtime.db-shm、Path.stat前SQLite将其删除，FileNotFoundError errno2冒泡后监督器SIGTERM停止child。rc=-15、reaped=true、remaining_live=[]、source unchanged；raw9826539字节73文件。尚未建立产品失败根因。原始命令、日志、准入、终态和资源文件SHA均冻结于plan.json。

R468 prepare rc0；独立read已rc0，9组全null/infinity，native UNKNOWN。部分原始source-frame有14帧、最大physics_step=13、已记录pass_count合计41；只支持待逐帧校验的下界，不证明最终精确计数。reader因inventory缺失返回的total_physics_steps=0不是实际零，不改原输出，以报告说明。

HEAD `ae3b88370276ebe0b2782720588c0b52d6c8e1d8`，完整423源码/固定输入source_generation `e5795af5d1a7b90a7dcb442da0f37c0ec9fe4fad04d13e3696c4a5cf609fdd55`未变。新plan.json含全部source_hashes及52项原始输入SHA/字节数。本规划不读DB内容，不运行产品/测试/GPU诊断/采集。

## 限定修复

仅在新R470 implementation/run_stage.py拷贝修改本轮一次性监督artifact；R468 runner、protocol、claim、raw和产品/src/tests/config/assets不动。

- strict：originals/**、protocol、startup/final及stdout/stderr/JSONL证据；可增长但消失必须停止。
- volatile仅新raw下runtime.db、runtime.db-wal、runtime.db-shm、runtime.db-journal及各阶段自有cache/tmp子树。live扫描的ENOENT可跳过但记录路径、errno、操作、UTC/monotonic和scan起止；不吞其它OSError，symlink/未知路径失败停止。os.walk/scandir错误必须显式处理。
- 所有live扫描标记NON_ATOMIC_CONCURRENT_SCAN；有跳过项则为部分观察和下界，禁止宣称精确瞬时总量。JSONL当前记录在扫描后追加，后续/终态计入，不循环追逐自身增长。
- 保留产品每blob严格raw上限/fsync、checkpoint RSS及监督free/RSS/wall上限。采样总量超过上限立即停止；正常暂态缺失不再误杀，但其无法给出连续硬限证明的局限必须保留。
- child/后代全部退出、live流关闭后，严格完整静态树统计所有现存文件；已跳过的volatile如今确实不存在可记absent。静态枚举期间再ENOENT则失败，不吞。最终统计自身receipt明确列为统计边界后写入并单列字节/哈希，仍纳入最终cap，不伪称自包含瞬时精确量。
- read新输出直接统计read-evidence/readout/read-runtime-cache/read-tmp，不用总量减initial让输入文件消失抵扣输出；冻结raw单独≤16GiB，新输出≤2GiB。每阶段新cache/tmp隔离，完整总量仍记录。

ROOT可在任何阶段启动前修正未执行runner的限定语法/接口，静态AST/JSON/hash及计划所列分支核对后冻结SHA；不增加软件测试。所有其它错误仍走原owned进程组清理，保留primary/secondary错误。

## 新运行路径、命令与上限

唯一assignment native-r439-0001、seed439001；其它8组保留未运行分母。新protocol在本轮actual/protocol，新raw `/home/ningyd/文档/ChatGPT/BIGsmall/cache/research/r470-teacher-replacement-full-20261108/native-r439-0001`，新readout在本轮actual/readout。旧raw/claim不复用。provider/model=null、cloud/API0；marker7、顶视camera、controller、mujoco_upright_box_v2、OC1、TTL5秒、guard/lease/worker/UNKNOWN均保持。

### prepare

```sh
'/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python' '/home/ningyd/文档/ChatGPT/BIGsmall/scripts/collect_native_calibration.py' --prepare-only --config '/home/ningyd/文档/ChatGPT/BIGsmall/configs/research/native_operational_calibration.yaml' --output '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round470-teacher-monitor-transient-file-race-20261108/actual/protocol'
```

上下文 `use_default`；child 120秒、outer 240秒、最多一次/retry0。精确env与outer argv见plan.json。

### full

```sh
'/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python' '/home/ningyd/文档/ChatGPT/BIGsmall/scripts/collect_native_calibration.py' --collect-once --protocol '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round470-teacher-monitor-transient-file-race-20261108/actual/protocol' --assignment-id native-r439-0001 --output '/home/ningyd/文档/ChatGPT/BIGsmall/cache/research/r470-teacher-replacement-full-20261108/native-r439-0001'
```

上下文 `require_escalated`；child 1800秒、outer 1920秒、最多一次/retry0。精确env与outer argv见plan.json。

### read

```sh
'/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python' '/home/ningyd/文档/ChatGPT/BIGsmall/scripts/collect_native_calibration.py' --verify --protocol '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round470-teacher-monitor-transient-file-race-20261108/actual/protocol' --output '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round470-teacher-monitor-transient-file-race-20261108/actual/readout'
```

上下文 `use_default`；child 900秒、outer 1020秒、最多一次/retry0。精确env与outer argv见plan.json。

full上限physics12960、explicit12976、implicit12962、render64852，wall1800/outer1920、RSS8GiB、raw及actual总量16GiB、free≥32GiB，均不放宽。历史失败的实际/下界/未知量单独累计报告，不声称两次合计仍在单次上限内。

共享原R468/R469非阻塞GPU锁，full锁内仅一次既定gpu/compute/Qwen资源准入，再一个require_escalated EGL生产采集；不重复诊断或启停服务，无P1/GPU并行。首次CPU prepare成功、fresh协议/源哈希验证后才能full。进程清理后严格终态统计，再一次独立read，partial输入按原边界允许；任何新失败保全并交下一实际Astra，不自动重跑。

## 验证与交付

ROOT保存与原runner差异及静态分支推演：允许SHM/cache ENOENT有记录继续；originals/未知路径ENOENT、其它errno、symlink、静态终态竞态必须停止；JSONL增长有诚实采样口径；read直接分区统计；所有退出同identity自有进程清理。只做stdlib AST/JSON/hash和静态核对，无新增测试或产品预热。

实施前写attempt-ledger保留R468真实失败及R470未运行状态，启动后追加事件；新运行仍是相同group/seed的依赖替代，不能增加独立样本数。完整collection声明须原始生命周期、worker/owner关闭、8个horizon和独立读取支持，否则PARTIAL/FAILED/NOT_RUN。native UNKNOWN，formal NOT_ACCEPTED，硬件NOT_RUN。

步骤报告分别列软件、实际和正式研究状态，保留两轮失败/结果及所有raw本地路径；显式路径提交推送验证后的本轮artifact，核对本地/上游/远端SHA。DB/完整raw本地保留不提交，清单不等于完整远端复现包。

补充冻结：R468 implementation/step-report.md/json 与 actual/read-input-after.json 已列入输入SHA。ROOT已核对14份source-frame及引用blob SHA，physics≥13、render≥41（1次implicit2pass＋13次perstep3pass）为LOWER_BOUND_ONLY，精确总量仍null；独立读前后非DB内容SHA及DBstat不变。本规划未读取DB内容。
