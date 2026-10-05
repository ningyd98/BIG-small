# R01 V4 range fix-round-1 independent targeted re-review

**PASS_SCOPED_SOFTWARE。R01-V4-RANGE-01 已关闭。** 当前新冻结 `fix-round-1/pilot-protocol` 可供 root 串行执行唯一 fresh sparse pilot；actual 仍0，旧 initial protocol 不可执行。此结论不提升 continuous visibility/native/UTC/calibration/group/future/formal authority。

仅对本缺陷修复、新 source/header gate/path 和保全进行定向复审：读取 fix report、source-before、精确源码 diff、新冻结元数据；独立复跑 owned40CPU一次、原 exact probe、3 owned源码定向Ruff/format/in-memory compile。没有调用 model/backend/renderer/physics/decoder/provider/hardware/UDP，没有重跑 old90、full342 audit、旧201raw/9input audit或全raw解码。

## 原 exact probe 与范围终态

保存的 `exact-original-range-probe.py` 与旧独立 log 最后一个 corrected probe byte-for-byte 相同，SHA `d2517eca71c59f86e98fcd5545b14a119eaa018d750eece9695c5b054d6f5de0`。独立运行 exit0，原健康对照不变，额外终点不再 COMPLETE。该不改字节 probe 的旧 initial header disabled gate 仅作为 CPU fixture；真实 execute/source 入口均拒绝该旧 gate。

| 实际终点 | 终态 | callbacks | 保存固定 selected | 缺失selected |
| --- | --- | ---: | ---: | --- |
| 4806 | COMPLETE / MATCH | 4807 | 201 | 无 |
| 4807 | INCOMPLETE / RECIPE_DEVIATION | 4808 | 201 | 无 |
| 4805 | INCOMPLETE / RECIPE_DEVIATION | 4806 | 200 | 4806 |

额外4807 callback以selected=false完整保留；short/extra均有明确非空 reason、expected4806与actual终点/time。没有裁剪、迁移201 IDs、删掉已保存帧、丢弃未完成分母或 retry。short原件直接读取本次40CPU运行的真实 recorder fixture输出，不另跑一套test或伪造接受 verdict。

实际 factory 把 frozen expected4806 注入 SparseRGBDRecorder；finish 除原连续性/identity/failure/selected条件外必须范围完全匹配。新header gate=true；require_range_policy严格拒绝range4807、range boolTrue、gateFalse或整数1。独立CPU entry控制证明这些拒绝在 configured_runner/frozen base/runtime/model加载之前；source_preflight的第一操作再次拒绝。旧actual路径也在header/runner加载前拒绝。唯一允许的新路径是 `marker-v4-preparation/fix-round-1/pilot-protocol`，relative输入规范化后指向同一冻结目录。

## 来源与最小变更

- 三个authorized live文件之外，18 baseline中的其余15文件字节不变；三个旧live字节已在source-before原样保存并与baseline旧SHA匹配。旧REQUEST_FIX三文件、旧report/owned pins/plan、selection201、v4XML、initial header/manifest/index及其三档案均保全。
- prepare.py只合并等值字符串，AST与source-before完全相等。run diff仅范围、gate、新path/freeze及重用不变archive的必要变化；teacher/controller/camera/guard/decoder/XML/marker注册未改。新tests只适配expected参数/path并补6范围/policy cases；原34语义仍通过。
- 新header/manifest/index匹配指定 pins；34个live/archive必要sources匹配、总434153B，32旧archive引用+2新prepare/runner副本；21环境pin匹配。selection header/manifest201 IDs与旧header完全一致。源码/元数据/环境CPU preflight和contract构造通过，contract digest仍 `16bfd83aa42ba257b2b3932335fdf8d1fdab423c513102a5fa9cbdee53450c99`。
- unchanged original_pins仍在 actual source preflight、继承runtime/model之前调用。为遵守本轮不重跑旧raw audit，独立CPU元数据preflight仅将该未变委托换为计数spy，确认201选中/9inputs/201frames；没有声称重新哈希这210旧原件。它们的原独审/作者保全结果被复用，其manifest/旧review pins本轮匹配。source→runtime→first session/model 的继承顺序保持。

## 定向验证与保全

| 检查 | 结果 |
| --- | --- |
| owned40CPU，禁pytest cache，/tmp fixtures | exit0，40 passed in0.63s |
| 原 exact probe，字节未改 | exit0；原RED关闭，健康控制保留 |
| Ruff check，3owned | exit0 |
| Ruff format --check，3owned | exit0，3files already formatted |
| 3owned in-memory compile | exit0 |
| entry/source第一操作拒绝与short/extra真实fixture原件检查 | PASS，actual0 |

原34+作者新增6构成同40；作者40与独立复跑40不相加为80或74，exact probe单列而不是另一个suite。新qualifiedRED=0。

127个限定slice inputs before/after SHA完全相等，changed_inputs=0；没有扩成old342或全仓hash。仅本fix-round-1新建 independent-review.md/json/log，旧报告、源码、rootdocs、Git均未由评审修改。旧和新attempt-1前后均不存在。全SHA maps、diff、命令及输出见JSON/log。

| 新冻结关键文件 | before=after SHA256 |
| --- | --- |
| `../prepare.py` | `57ec9a6e1cb5dee420387f242b0e05fdd668766c264cbbc4b22040e6a3144a47` |
| `../run_sparse_once.py` | `8c9328d29e57d5195039f4465e76c2563ed16361f8013cf63ba79dbf363a136c` |
| `../test_cpu.py` | `e3e093e56f33d338cf14fd4762e8e73c47f29bfebc2c152974f9f618d45271f4` |
| `pilot-protocol/header.json` | `d856dd0e1093278709239cb6e5cd312872b1f41dfd79d5d87a3b36b8de8e4213` |
| `pilot-protocol/execution-source-hashes.json` | `f51eb9ae3e27e8b290e2bc02a5db58b82766600b7fcdd436f435a8779d3c580e` |
| `pilot-protocol/execution-archive-index.json` | `bb56ad5d3cfebcc1a54aabad18eb0fcd8d5ee29d7a82d8d44576dfe8b661243c` |

review log SHA256: `92c0809be9fef2e2168ab78e2e2434b560db9d846dfb3e8779fa56a85a8fdce0`。

root仍独占串行renderer，按已冻结新path执行一次；不要再次prepare或调用旧path。该实验只采固定201 RGBD，原120settle/9actions/2dwell与4806诊断合同不变，全部实际物理/truth/operations仍保存。Sparse采样不满足原0.005s observability gap，改善效果与compiled-model dynamics尚未actual测量；本评审没有构造反事实旧pose。
