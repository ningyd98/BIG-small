# P4 R93 真实来源独立审查

结论：**PASS_SOURCE_ONLY**。审查者 gpt-6-astra `/root/astra_oc2_residual` 是 R93 规划者，非 Sol 产品实现作者、非 ROOT 实际执行者。未重新调用公共 reader、产品测试或 actual。

新 actual 一次 exit 0，20.193515827 秒；随后另一 PID 的公共 reader 一次 exit 0，`VERIFIED/source_prefix_complete=true`。原失败保留：累计两次实际尝试，一败一成。

独立核对原件得到 RESET1 / CONTROL120 / PHYSICS120 / CAPTURE3，共244事件、488 BEGIN/END记录；physics完整1至120。缓存实例0/0，显式76800（0/0/307200字节），对应2/2/3 render passes，actions0。

原 D capture bracket=[515217248372848,515217981244107]，current=[515219225898709,515219226102047]，年龄重新做整数差为[1244654602,1977729199]ns，within5s=true；同域、session及 acquisition3/current因果关联成立。此处没有用本次审查时钟重贴年龄。

预注册先于RESET由本次冻结且哈希匹配的生产路径顺序（exclusive prereg写入563–569，prepare1434，RESET1451）和原startup/RESET记录共同支持，不声称另有文件写入时刻测量。SQLite只读查见唯一真实job/lease/attempt；预注册和发布的job/run/worker/lease/acquired fencing一致，发布观察在租约到期前，最终SUCCEEDED/released。该UTC租约事实不升级为D域lease迁移或live authority。

225来源库存原件连接匹配；执行器三阶段均记录无漂移。完整新63文件16,700,451B、旧68文件25,001,424B逐项哈希和文件集合均复核。catalog→receipt→original_files连接成立。全量raw/DB仍本地保存。

来源正分支通过不等于native/live/formal验收：native/live UNAVAILABLE，formal=false，UTC/SI UNVERIFIED，future H/D与geometry UNKNOWN，calibration groups0；不能计作九组、G1或T12实际决策完成。

## 有限 Git 建议

以下26个现存小文件合计69,305B，另加本审查和随后冻结的小步骤报告；仅建议，未导出、提交或推送。ROOT交付前复核精确hash。完整raw、DB、source freeze/完整库存和旧actual树保持local-only；摘要/manifest/catalog不能冒充完整远端复现包。原日志字节不strip，不以修改失败原件通过检查。

- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/root-activation-round93.json` (2722B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/root-acceptance-round93.json` (3090B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual-round93/capture-catalog.json` (5403B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual-round93/prefix-originals/prefix-receipt.json` (5213B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual-round93/prefix-originals/source-publication-state.json` (998B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/public-readout-round93/result.json` (776B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/preflight-round93/command.json` (513B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/preflight-round93/execution.json` (357B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/preflight-round93/process.json` (100B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/preflight-round93/stdout.txt` (34529B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/preflight-round93/stderr.txt` (0B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/execution-round93/command.json` (553B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/execution-round93/execution.json` (357B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/execution-round93/process.json` (100B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/execution-round93/stdout.txt` (5500B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/execution-round93/stderr.txt` (0B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/public-readout-round93/command.json` (1609B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/public-readout-round93/execution.json` (358B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/public-readout-round93/process.json` (100B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/public-readout-round93/stdout.txt` (717B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/public-readout-round93/stderr.txt` (0B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual-round93/worker-attempt/attempts.jsonl` (217B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual-round93/worker-attempt/lease_history.jsonl` (345B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual-round93/worker-attempt/state_transitions.jsonl` (2230B)
- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/actual-round93/worker-attempt/evidence_consistency.json` (2440B)

- `artifacts/research/process/20261004-ced-development/t12-convergence-execution/P4/step-report-round93.md` (1078B)

时点边界：本审查依据 P4 实际时冻结及运行前后收据。其后 ROOT 授权 P5/R100 的合法源码修改不属于 P4 漂移，本审查不要求新工作继续匹配旧冻结。

## 核对项目

- PASS — preflight-round93 receipts
- PASS — execution-round93 receipts
- PASS — public-readout-round93 receipts
- PASS — preflight NOT_RUN
- PASS — catalog original receipt binding
- PASS — actual-round93-originals-manifest.json full local bytes
- PASS — actual-originals-manifest.json full local bytes
- PASS — receipt originals hashes
- PASS — 244 complete events
- PASS — ledger BEGIN END pairs
- PASS — physics steps1to120
- PASS — real cached and explicit instances
- PASS — no actions and one explicit
- PASS — original D age recomputation
- PASS — 225 inventory joins
- PASS — reviewed producer source equals actual freeze
- PASS — worker fence stable
- PASS — real SQLite sole worker lease attempt
- PASS — preregistration before RESET evidence
- PASS — external independent process original reader
- PASS — source-only boundary
- PASS — root acceptance preserves failure denominator

## ROOT 已准备交付集合复核

`delivery-p4-actual-round93/prepared-evidence.json` 的22文件64,380B逐项字节/hash匹配；该精简集合可接受，另加本审查与非自引用最终ROOT接受即可。上文额外的 publication-state 和四份 worker生命周期收据仅为可选解释材料，不要求扩大ROOT清单。pending原报告保持原样，最终接受另写；不新增产品、测试、reader或actual验证。完整原件/DB/大freeze仍本地。
