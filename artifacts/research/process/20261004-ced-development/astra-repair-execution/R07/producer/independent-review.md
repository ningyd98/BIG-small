# R07 producer independent scoped software review

**PASS_SCOPED_SOFTWARE。** 当前 quiet 三个 owned 源码可供 root 按下述唯一 frozen protocol hash 执行首个 recovery-0001/attempt1；未发现新的 qualified 缺陷。本评审没有执行 actual，当前仍是 0/200，不是 native、G4 或全池验收 PASS。

Reviewed protocol hash: `66570b912ba08e0924e4cbe31098be9df7f1f02ed43548b131f65b2695ded724`，仅 `producer/protocol-final`。首组 `g-77a8915dc8c2eb94596a37633248a6d8`、scene `0cb7d448e904fa514ab555ad37a2f99cf90cde5a888a05f1afe3db6cbffc4e74`；first assignment recovery-0001、ordinal1、direction_y=+1。root 已授权整体研发及唯一首 actual，评审没有新增用户许可流程。

## 范围与执行

读取作者 report/source-hashes/diff、三份 live owned files 及 unchanged reset/capture/teacher/backend/source adapter/verifier 接口。只独立复跑 owned 20 CPU 一次和定向 Ruff/format/mypy；额外 source/catalog/pool/default-preflight 是纯 CPU 检查。不构建或初始化模型/backend，不运行 renderer、physics、decoder、provider 或硬件，不重跑旧 broad tests。owned integration test 禁止真实 initialize，使用明确 CPU hook/raw fixtures 和原 verifier，不 mock accepted verdict，也不把软件重算成功计入正式200。

## 主要结论

- 最终 header canonical hash 独立匹配；23 execution source/model pins、6 payload hashes、Python3.12.3 和 MuJoCo3.3.7/NumPy2.5.3/Pillow12.3.0/Pydantic2.13.5 metadata 版本匹配。三份 source-package 副本逐字节匹配 owned live SHA；review-package.diff 精确重建相等。四个旧合同/collector 文件 SHA 未变，不改旧验收合同。
- 独立重算全部31份声明的本地 metadata catalog，与 frozen history.json 完全相等：7563 group IDs、6361 scene hashes、7440 physical keys、7440 components、unresolved0。新 formal2400/foundation120/ood300/power120/recovery200/selection120 共3260，group/scene/physical key 各3260唯一，与历史三类交集均0。所有200 eligibility/fault日程及2400候选逐项复现，±方向各100、200 eligible。此闭包仅 EXPLICIT_LOCAL_ORIGINALS_ONLY；没有声称未知外部或未登记历史全知。
- 实际入口在 preflight/hash/独占分配之后才 lazy 调用原 MuJoCoCaptureSession；原 initialize/reset/apply_scene 使用 fresh episode。reset0 当前 snapshot、120 settle、实际 TARGET_MOTION(.02m/s,1s,direction_y)、原 FINISHED 等待最多241个完成步。只有 FINISHED 后才原 NORMAL T5 settle0，原9动作及两个 dwell 不变；没有加载或复制旧实际 episode，没有新控制器或隐式重试。
- reset 到 terminal 的原 PhysicsStepObservation 全数 detach/enqueue；仅相同 teacher entry snapshot去重且同step内容不同拒绝。全程 actuator observer 包含原 next-completed-step ID、PRE simtime/q/qfrc_bias/ctrl/gain/range；原 backend command_seq 从1开始，T5 action half-open command ranges 原样。完整 RGBD trajectory frames、unframed failed results、raw command/fault/action/state/control prefix 分开保全，不借旧640帧充新320组。
- `write_recovery_source` 只是原 passive adapter。PROVEN 必须由 unchanged `_recovery` 对 assigned geometry、完整 reset/terminal steps/clock、真实STARTED/FINISHED/位移、原9action结果、command_seq1连续prefix、全actuator执行、安全geometry和独立 `evaluate_evidence` 成功重算；另加 faultstart+60s 全段上界。caller success/fault_finished flags 不成立，owned反例保持 FAILED/INCOMPLETE。实际未成功、missing-source 或部分轨迹只是 pipeline 未完成，不能因此伪造 proof。
- 独占 ALLOCATED x-file 在物理前写入并 fsync；fresh nonsymlink output、固定 namespace、copy/reentry/ordinal skipping 拒绝；首 ordinal1，后续显式最多5，不能自动retry或跳过前一完整失败结果。所有 allocated assignment IDs 保留固定200 attempted分母，EXCLUDED/FAILED/partial亦不删，未启动组保留unattempted，单组即使PROVEN整体G4仍false。
- 日志队列32768有界，callback只detach/enqueue，writer线程每64行及close fsync。队列饱和、writer或实际异常显式失败，allocation及已有prefix不删；崩溃缺尾迹或source adapter无法完成保持 INCOMPLETE/FAILED。现预算 wall1800s、retained2GiB、free reserve10GiB、faultstart+60s；原 raw/actuator每行16384B保守reservation、最后实际file-size检查。生产器fcntl lease拒绝同生产器并发；root仍须串行其它renderer。原报告如实说明native阻塞下SIGALRM响应可延后，强制watchdog只承诺已fsync prefix，不能把它误记完整恢复。
- registered clean-raw 场景 depth noise0 与现 pool/apply_scene 合同一致；本 slice不改 native默认noise.001，未运行cloudtransport。原controller/camera和320×240域未改。固定 opportunity collector 明确 NOT_IMPLEMENTED；2400 frozen候选不是已采集label。后续 derivative evidence-inputs 要包含每个已分配attempt/失败/缺原件诊断，locked pools保持不改；这段汇编未由本次完成。

## 独立命令

| 检查 | 结果 |
| --- | --- |
| owned test_protocol_generation_sources.py，仅20CPU，禁用pytest cache，fixtures在/tmp | exit0，20 passed in28.86s |
| Ruff check，3owned源 | exit0 |
| Ruff format --check，3owned源 | exit0，3files already formatted |
| mypy，2owned生产源码，cache在/tmp | exit0，no issues |
| final default CLI | exit0，PREFLIGHT_ONLY，actual_calls0、未分配 |
| 全31原metadata库存/3260池/200日程/2400候选/源diff独立重算 | PASS |
| old protocol/protocol-reviewed、source或env内存drift、错误caller hash | pre-actual拒绝；错误hash在allocation前拒绝 |

copy-namespace、reentry、wrong-review-pin、原source-prefix/无故障success旗标、故障方向、faultstart deadline、byte/free/wall、spool及renderer lease 拒绝控制由同20owned tests覆盖，独立复跑通过。作者20与独立复跑是同一集合，不相加为40；新增qualified RED=0，不制造 speculative design veto。命令和stdout/stderr保存在 log。

## 保全与 pins

固定本 slice120 inputs的before/after SHA完全一致，changed_inputs=0。未全仓hash；只创建 independent-review.md/json/log 三个新文件。protocol-final/allocations 与 producer/raw 在前后及最后readback均不存在；未写Git、rootdocs、Stage、旧report或源码。

| owned live=source-package | before=after SHA256 |
| --- | --- |
| `scripts/generate_rgbd_protocol_evidence.py` | `91a002d3a1ef67d436b88f7f509729c398d4669f8a8b07161644c4af46a7c672` |
| `src/cloud_edge_robot_arm/research/protocol_generation.py` | `92f455e554bc87ab7b263ded5bdc378b65fb16d2e25bdb7716fa154448f019b6` |
| `tests/test_protocol_generation_sources.py` | `a2a90fdca835cbfb6dca8c302e18c58e5a268cd6b2a36fde6c995501041c0450` |

| 输入报告/包 | before=after SHA256 |
| --- | --- |
| `report.md` | `503fe6958d68ee148763c83afdbb8ffab2f72d652166aeb9b9fdc4c894c30ccd` |
| `report.json` | `576c8894cc1a9eb7b8f549607a530a7c27d603e39ffa7b9ec4f80e17c50e6d1c` |
| `source-hashes.json` | `5ffd5f030b6b1f9c937c16dc0ee59d57ad423fe64ca6995a14b2586087e39f9b` |
| `review-package.diff` | `22fb94a17fd4276b563f9ae6bf10f41462d3d97d6f38d3ecf6d711ad1ef45fa3` |
| `protocol-final/generation.json` | `ea21219b1cb98b7520526457211d4ff2dbfaf5a9311451897351a56b911276ba` |

四旧文件及全部120 SHA map见 JSON/log。review log SHA256: `1df90c42921796faae700b4cfd59f070527fcc8127e99126e1075f12b8134642`。

通过仅治理 root 的上述唯一首真实恢复入口的软件准备；实际 wall/RSS/retained、fault位移及恢复原件要由首 actual 测量。native/calibration/UTC、formal opportunity、200组G4、future stability、未知外部历史和吞吐均没有升级。
