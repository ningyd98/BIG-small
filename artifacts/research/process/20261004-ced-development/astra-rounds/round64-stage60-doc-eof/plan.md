# Astra Round64 — Stage60 文档末尾单字节修复计划

状态：PLAN_ONLY_SINGLE_EOF_BYTE_REPAIR_PENDING_ROOT_EXECUTION。仅2 tasks；规划者尚未修改文档或运行 Git。

## 问题与原始证据

Stage60六份当前文档的git diff --check因continuation尾部恰一个多余LF而exit2；367个链接已检查存在。仅文档格式校验停止，不更改采集、软件或正式研究门。

原始 `doc-check-step60.json` 必须保留 `STOP_DOCUMENT_CHECK`。原命令 exit2，stdout 精确为：

```text
docs/research/process/continuation_20261004.md:434: new blank line at EOF.
```

stderr为空。Stage59相同六文档检查exit0，其证据是原root工具观察，不能冒充新进程日志。

## 根因与范围

/tmp/bigsmall-stage60-publish.py assigns block=para+report-link+two LF bytes, then appends block to continuation. The resulting continuation ends with exactly two LF bytes; its final extra LF produces the saved sole EOF finding. Other five documents received an inserted paragraph, not this appended EOF block.

唯一允许已有文件变化为 `docs/research/process/continuation_20261004.md`：原112598 B，删除最后一个0x0A，成为112597 B；预期SHA256 `4b457af2b83ae4e2713c79bce8af07b44a8c6cff9969ecb667a56cc2afa2fc1f`。正文及其余每个字节不变。使用原字节切片，不使用rstrip或文本格式化。

新增执行证据只在 `artifacts/research/process/20261004-ced-development/astra-repair-execution/stage60-doc-eof/round64/**`；另允许新建 `artifacts/research/process/20261004-ced-development/doc-check-step60-round64.json`。原report/status/check及其余5docs不可写，helper只读不修。

OC2 Task2/3 modules and worker, possible parallel RW1 producer/test are actively changing. Do not pin them, inspect their diff, require global quietness or claim whole repository preservation.

## 实施前置条件

- Root reads plan before modification and remains sole document writer for this bounded operation. Independent active software work can continue.
- Compare all 12 input SHA256/bytes including six current docs, three original Stage60 artifacts, Stage59 check, helper and AGENTS.md against this plan. Record plan.md/json pins as additional execution inputs before and after.
- Target must still end in exactly two LF bytes and match pinned112598-byte original. Expected result is112597 bytes with SHA256 4b457af2b83ae4e2713c79bce8af07b44a8c6cff9969ecb667a56cc2afa2fc1f. No rstrip(), newline conversion, text rewriting or helper execution.
- Execution evidence directory and corrected check destination must be absent. Create all evidence exclusively; collisions are stops, never reuse or overwrite.
- Every exec uses require_escalated. Python uses existing .venv/bin/python and PYTHONDONTWRITEBYTECODE=1; only stdlib read/hash/write/report orchestration plus the one allowed six-document diff check.

## Task 1 — 冻结限定原件并只删除一个末尾LF

1. Recheck preconditions and all input pins; create new exclusive evidence root. Save input-pins-before.json including plan pins, source_failure_reference.json preserving original failure path/hash/status/exact argv/exit/stdout/stderr, and continuation-before.bin containing the exact original112598 bytes.
2. Compute candidate=original_bytes[:-1] in memory, require original_bytes ends with exactly two LF, candidate ends with exactly one LF, candidate equals the complete original prefix, and candidate SHA/size equals expected_target_after. Replace only continuation file contents with these candidate bytes, preserving its file mode. No other document/body/history/helper/source/report/status/check edit.
3. Save edit-result.json with original and resulting SHA/bytes, removed byte0x0A at original offset112597 (zero-based), length delta-1, exact prefix equality and trailing LF counts2→1. Keep original Stage60 STOP_DOCUMENT_CHECK immutable.

## Task 2 — 一次六文档检查与新增局部校正报告

1. Run exactly once the saved command: ["git", "diff", "--check", "--", "docs/current_authoritative_status.md", "docs/research/process/phase_progress.md", "docs/research/process/handover.md", "docs/research/process/validation_matrix.md", "docs/research/process/continuation_20261004.md", "docs/superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md"]. Capture complete argv/cwd/env/start/end/exit and exact stdout/stderr bytes into new exclusive command.json, stdout.txt and stderr.txt under evidence root; record SHA256/bytes and runs1. Do not rerun on failure.
2. Rehash only the same12 inputs and two plan files into input-pins-after.json. Require continuation matches expected_target_after and every other pinned input/plan unchanged. This is bounded document/evidence preservation, not global source quietness. Do not rescan local links: the removed EOF byte cannot change link syntax, and367/all_targets_exist=true is explicitly carried from immutable old check.
3. If exit0, no new stdout/stderr finding and allowed single-byte delta alone are verified, create exclusive doc-check-step60-round64.json at the planned Stage60 artifact path. Record PASS_SCOPED_DOCUMENT_EOF_CORRECTION, plan/original failure/new command pins, before/after target pins, six checked paths, link evidence reused_from old check with links_rechecked=false, and original check remains STOP_DOCUMENT_CHECK. Do not alter original report/status/check or imply renewed software/actual/formal acceptance.
4. Write exclusive step-report.md/json beneath evidence root, citing original failure→Astra plan→single-byte edit→one verification, command/result/artifact pins, allowed versus actual file changes and all limitations. Include correction JSON pin in step report. Return evidence to root for its later stage integration; do not write any other historical/current summary or perform Git delivery.
5. Any pin/EOF mismatch, new finding, nonzero diff exit, evidence collision or unexpected condition: preserve available raw failure and stop affected work for next Astra plan. No second check, broader whitespace cleanup, script fix, PASS rewrite or local workaround.

## 验收与停止边界

最高仅 PASS_SCOPED_DOCUMENT_EOF_CORRECTION。一次六文档diff检查exit0、输出无新增问题、仅目标末尾1字节变更、其余限定pins及计划不变。367链接引用原检查，不重跑或宣称新验；产品采集/软件/正式研究门不受此校正影响。

On any new cause, expanded scope, mismatched input or unexpected validation failure preserve evidence, stop affected correction and obtain next gpt-6-astra plan before further repair.

## 实际输入指纹（12项）

| Path | SHA256 | Bytes |
|---|---|---:|
| `artifacts/research/process/20261004-ced-development/report-step60.md` | `a7aa8d06c618d5332bd004e7a50b079eb3f547053818c222ee8baeeee211e644` | 6532 |
| `docs/current_authoritative_status.md` | `0074f15713cfd9010a7fd21651fd960dc0a31f42a19acdb919457aeefbac625f` | 32280 |
| `docs/research/process/phase_progress.md` | `edf5a5e3209aa23bb54a11c716213c99a02db660fe28cccd19e2dbe70d19193f` | 12253 |
| `docs/research/process/handover.md` | `76512d7539f16d5c326d80e872390c1fb2d66eb3ca7e83df0b201de173359508` | 18513 |
| `docs/research/process/validation_matrix.md` | `8dfe24969fdb9370a5873800b7fadb1f79ee48a7fbf0092deacd861a7f1c504a` | 16613 |
| `docs/research/process/continuation_20261004.md` | `e9a67459b95c5f6e546fd822eeae91d0b1bb9bc3dd38baf6894c0c3a5ed59c82` | 112598 |
| `docs/superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md` | `b3e27ce7b4e854ade5bcca4058e6bd7606429f39e8e094db4d85b5c9ff41787f` | 29167 |
| `artifacts/research/process/20261004-ced-development/doc-check-step60.json` | `843297b8ae824dd96a729e56f03096e8c574bdd5a0a3107ff47e6e8956e334db` | 4636 |
| `artifacts/research/process/20261004-ced-development/implementation-status-step60.json` | `4333194ad9b0ed93fdd7213921d372c7c71da4972a257fa6dd0d268b5e17a2ef` | 12923 |
| `artifacts/research/process/20261004-ced-development/doc-check-step59.json` | `8d6ad3269f8c3f1adb662bc33786c5a9c6cf001899b891e86236270b31829d8a` | 4631 |
| `/tmp/bigsmall-stage60-publish.py` | `a0cdfaec9dc0b087d1a064b715268a9bc077f69fa4822d436ace5dbe7dc651bd` | 12209 |
| `AGENTS.md` | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` | 1774 |

执行者还须在before/after证据中记录本plan.md和plan.json的实际SHA256/bytes。规划仅写本计划两文件；本轮未运行diff检查，未实施修复。
