# Astra round62：登记摘要独审元数据修复计划

状态：PLAN_ONLY_NOT_EXECUTED；角色：gpt-6-astra；仅两个任务。

## 问题和原始证据

Review script hashes the three-key header object directly. Frozen reader constructs PoseMarkerRegistration(**header[marker_registration]); frozen dataclass adds dictionary=DICT_4X4_50 and digest serializes asdict(self). The missing default changes the expected digest. No reader/source/raw defect is established.

旧独审进程 exit 0，但语义结果 REQUEST_NEXT_ASTRA_PLAN；步骤 0–4806 共 4807 条绑定失败。保存全部旧失败，首行诊断不代表全量。

## 规范化与限定范围

冻结 dataclass 四字段和默认 dictionary=DICT_4X4_50；冻结 reader 调用 PoseMarkerRegistration(**header['marker_registration'])。

规范 JSON：`{"dictionary":"DICT_4X4_50","marked_asset_sha256":"045ce032032426ec6130348ee75e5f53b7db02699fc1f39558727edd63f67e0d","marker_id":7,"marker_size_m":0.075}`

诊断计算值：`ab49376cc3e25da593531c651804308aa93777685c3026049de51622099fc56c`。实施必须从冻结 header + schema/default 重新正确构造，不可将该值或首行值硬编码为期望。

最多一次标准库 binding-only 补验：优先真实存在的完整保存字段，否则允许一次读取 4807 已解码 derived 行，仅提取 identity/registration 字段；同一遍核对流 SHA256。禁止 raw/旧 derived、pose 重算、第二 decoder/reader、重跑其他已过检查。

## 实际前置条件

- Root actual session 88431 and only strict reader session 1633 have terminated exit 0; verify terminal metadata, not rerun either process.
- Recheck plan and every actually-read metadata/source pin before implementation, quietly. For derived stream pin, verify bytes SHA256 only during the one allowed read, or use already-preserved complete per-row fields with an auditable original stream pin. No extra derived hashing pass.
- Root holds shared source unchanged through completion of post-terminal final independent review. Parallel OC2 Task 1 review is read-only with respect to shared source.
- New output directory must not exist; create it exclusively. Every output uses exclusive create and no overwritten file, no retry.
- Use .venv/bin/python with standard library only and PYTHONDONTWRITEBYTECODE=1; no project imports, optional dependencies or test execution.
- Inspect existing saved review artifacts for COMPLETE raw per-row identity/registration fields first. Existing recomputed report stores findings and aggregates and saved first line stores only one row; neither alone suffices. Do not claim an unsaved in-memory list exists.
- Protect current metadata/source/header/archive and all original review files with SHA256 before and after; protect derived stream with stat before/after and single-pass bytes digest when read. Reuse immutable inventories for raw/old inputs; never reopen raw or old derived for protection.

## T1 Create and execute one exclusive binding-only metadata validator

唯一新增写入范围：`artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/implementation/post-terminal-independent-review/round62/** (new files only)`

1. Save new validator source, exact argv/cwd/environment, scope and source-selection decision, input origins/pins, protected-metadata-before, execution/exit, stdout/stderr. Preserve old script, failed findings list and old evidence untouched.
2. Using static reading/AST only, validate frozen dataclass four-field schema, __post_init__ validity constraints and digest expression, plus frozen reader constructor semantics. Derive canonical object from frozen header values plus ONLY absent schema defaults; preserve explicit dictionary value and reject unsupported value or unexpected fields. Do not coerce numeric types or invent defaults.
3. Validate marker_id is exact int in [0,50), marker_size_m exact int/float finite >0, marked_asset_sha256 lowercase 64 hex string and dictionary exactly DICT_4X4_50. Serialize full four-field mapping using json.dumps(sort_keys=True,separators=(comma,colon),allow_nan=False).encode() and SHA256. Record header pin, schema/archive pins, schema/default origin, canonical object, canonical UTF-8 representation and computed digest. The diagnostic hash may cross-check the result, never supply it.
4. If a complete saved per-row field artifact truly exists, pin and read it once and document original derived provenance. Otherwise read ONLY offline/offline-markers.jsonl once as binary JSONL, computing its SHA256 and byte count in the same pass. Parse JSON, extract only physics_step, decode_status, observation_id, checksum and marker.status/observation_id/observation_checksum_sha256/registration_hash; do not use pose, corners, raw fields, gaps or other passed checks.
5. For every step 0..4806 exactly once, independently compare marker.status with decode_status, marker.observation_id with row.observation_id, marker.observation_checksum_sha256 with row.checksum, and marker.registration_hash with dynamically computed canonical digest. Keep full extracted originals and each component result in new binding-rows.jsonl; findings retain actual/expected values and step. Exact denominator, no missing/duplicate step, all 4807 identity and registration checks and stream provenance must pass; do not generalize from the first row.
6. Write binding-result.json including expected_registration_origin, input pins, rows checked, all four component totals, full findings, exact denominator, stream read count (0 if auditable saved fields reused, otherwise 1), zero decoder/raw/old-derived/project-import/model/camera/test/network/Git counts and no source/header changes. Finish protected-metadata-after and compare. Save process exit and semantic result separately; process exit 0 alone is not PASS.
7. One execution attempt only. Unexpected exception, mismatch, missing field, input drift or guard failure must be retained and trigger STOP/next Astra, with no local fix or retry.

验证：Metadata-only 4807/4807 exact identity + dynamically canonicalized registration bindings, auditable stream provenance and no protected input changes. Do not re-evaluate independent earlier count/gap/stream/raw checks.

## T2 Compose final independent review and step report from preserved evidence

唯一新增写入范围：`artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/implementation/post-terminal-independent-review/round62/** (exclusive final report files)`

1. Produce final-review.md, final-review.json and step-report.md/json in the new directory; link/hash original failed report, diagnostic, new binding result, original strict-reader report and original actual evidence. Embed or preserve full mappings of earlier passed other checks with original provenance and label them reused rather than rerun.
2. State old independent process exit 0 yet semantic REQUEST_NEXT_ASTRA_PLAN, exact canonicalization defect, first-line diagnostic limitation, new complete binding result and combined final judgment. Historical 4807 findings and FAIL_OR_UNAVAILABLE remain untouched.
3. Explicitly distinguish developer/software verification, one actual development run and formal research admission. Reconcile pending-reader label in old actual metadata by citing terminal strict-reader evidence, not editing the old artifact.
4. Highest result: one development full-frame observability PASS_THIS_FULL_HORIZON for the saved horizon, with strict-reader raw verification reused and 4618 OBSERVED preserved plus 189 UNKNOWN recovered, exact four recorded streams equal excluding episode_id only. This is not an independent physics replay or proof of unrecorded internal-state equality.
5. Keep native_admission NOT_PROMOTED, formal_accepted false, source_authenticity UNKNOWN, stability UNKNOWN, future stability UNAVAILABLE, continuous visibility NOT_ESTABLISHED, continuous motion NOT_CERTIFIED, SI/certified UTC NOT_ESTABLISHED, nine independent calibration groups false, independent_calibration_group false, zero support and geometric/angular bounds null. Include all these in final JSON and prose.
6. Record this round in its step report for later stage-summary integration. Shared-source hold releases only after root accepts the completed post-terminal final independent review. No Git or broader stage artifact mutation in this plan.

验证：Check final report references all immutable original failure/other-check evidence and new full binding PASS; acceptance claims obey every nonpromotion boundary.

## 失败停止和验收边界

Any new finding, unexpected failure, input/schema drift, need for wider scope, missing actual terminal proof, ambiguity in complete saved-field provenance or output collision: retain evidence and stop affected work; request next gpt-6-astra round before edits or retry. Unaffected independent read-only work may continue.

This is a repair plan, not a completed binding validation. All 4807 must be checked in T1 before combining results. No new actual run, formal acceptance or native promotion is authorized.

真实 actual 一次：session 88431，exit 0，674.8442775509902 秒，4807 saved / 4806 physics / 9 actions；raw 4829 files / 534140506 B。唯一 full strict reader session 1633 exit 0，父级记录 684.093 秒。原 9822 输入未变；本轮不重新读取原 raw。

开发验证、真实运行、正式研究验收分别记录；最高仅一次开发运行保存全时域的 full-frame PASS。formal false / native NOT_PROMOTED / zero support / geometric 与 angular bounds null，其余非晋升限制完整保留。

## 输入文件与 SHA256

- `AGENTS.md` — `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` (1774 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/implementation/post-terminal-independent-review/recomputed.json` — `c8f28f2155c267dc679ba5458988217f4da1548570ed7a492c9be0d50479ddc8` (521324 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/implementation/post-terminal-independent-review/registration-binding-diagnostic.json` — `4cf3cf837693fd1521882027754ae0007f5b5c9c15efbffb0e933ab37a42d116` (1205 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/implementation/post-terminal-independent-review/first-derived-line-original.jsonl` — `b0a694aa794d638ac61599c6af31555b9d9c89bfb52b1739853423b3ce758280` (2099 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/implementation/post-terminal-independent-review/recompute-command.py.txt` — `0bccd3f7207ea4aefe213e71f66f71da6b9a078d982f8828dced28b77f4122dc` (16655 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/implementation/post-terminal-independent-review/command.json` — `d88b4cfc8e99f82bd4be55ac569bd619a2035569c9321449fc6747855bc79d68` (591 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/implementation/post-terminal-independent-review/execution.json` — `a148a8e2e822131cdc224e3b608285a06cd6b6a562a7019d164f2810dd51c659` (290 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/implementation/post-terminal-independent-review/stdout.txt` — `e6a5efa99942f157f037a88de43cbb29b358e476096418f81e10ae01b7ef1638` (513947 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/implementation/post-terminal-independent-review/stderr.txt` — `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (0 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/implementation/post-terminal-independent-review/actual-metadata-review.json` — `5c71636a7b18baf50ca99b3ea395d79fd9bd0a8644579d425cc0a63df9fb5d9c` (5572 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/offline/offline-verification.json` — `9b9a1808775829d70e7bd77eb2b2326edaaf625734410876c3754948cfb6ab5a` (138077 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/full-protocol/header.json` — `2dec1ca5ac4352a90056f8734d26e8fdef1795da212537f1897c8e1a77542100` (76541 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/full-protocol/execution-archive-index.json` — `04bc813a2b89d30a65a7b7fb541eef5c77fb91cfb3c6205f2b908b19d9ed0d30` (16612 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/full-protocol/execution-source-hashes.json` — `88a58cb2e18f9f039d150f64ae6e6c6beb97d75be19e2ad6863122929fc7d483` (6504 B); Astra read-only metadata/source inspection; no project imports
- `src/cloud_edge_robot_arm/vision/pose_markers.py` — `68f9e6e0675a4b6ccdead896bd767c685fd53357591ab1fdf4d71d124c72264f` (9260 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/t7b-continuous-visibility/source-before/src/cloud_edge_robot_arm/vision/pose_markers.py` — `68f9e6e0675a4b6ccdead896bd767c685fd53357591ab1fdf4d71d124c72264f` (9260 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/verify_full.py` — `011f7ef1d8a5adf615ec3108debb1072465a1a798cd11b7a14bf99e910f8bc09` (58135 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/full-protocol/source-final/verify_full.py` — `011f7ef1d8a5adf615ec3108debb1072465a1a798cd11b7a14bf99e910f8bc09` (58135 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/actual/execution.json` — `07d318503b7138efad5068566cb49e3b054366fe8be63fe97f26e6dfc6dc0225` (1139 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/actual/root-terminal-summary.json` — `ece87459505b2771e3fe593c4a1bfb8cf5e6dfdeaaffe45168032c091d886f5d` (114344 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/actual/reader-command.json` — `6192c94acbdb3457d56dbd92a14c5f88f9f4f846617beac4aaad762355f316d1` (1423 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/offline/input-inventory-before.json` — `b8f35f53c5233cfcaecff039d6d484d1d89dd34b7b264e697f9d134dd850f596` (2945089 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/offline/input-inventory-after.json` — `b8f35f53c5233cfcaecff039d6d484d1d89dd34b7b264e697f9d134dd850f596` (2945089 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/offline/immutable-differences.json` — `a828190e7372334fd9b9385ad6ce48ded50f8e9b55cdd57e2efde8bb9030d184` (52 B); Astra read-only metadata/source inspection; no project imports
- `artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-full/offline/offline-markers.jsonl` — `86aab147b78efdfb9da5fe374ce666a490d008b3f05238108b18aec439c04483` (9853287 B); Existing original independent-review input_pins; Astra did not open or hash the derived stream

## 计划生成说明

Initial read-only default-shell calls failed bwrap loopback Operation not permitted; continued only with parent-requested require_escalated .venv/bin/python metadata inspection. No code repair or validator execution occurred.

本次仅创建 plan.md/json；未运行实施、测试、解码、模型、相机、Git 或网络。完整机器可读原始证据、禁止项、两任务和验收细节见同目录 plan.json。
