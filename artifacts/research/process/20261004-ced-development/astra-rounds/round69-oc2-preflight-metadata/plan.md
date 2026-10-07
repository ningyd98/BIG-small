# Astra Round69 — OC2 前置metadata字典路径恢复

状态：PLAN_ONLY_METADATA_PREFLIGHT_RECOVERY_PENDING_ROOT；2 tasks。仅metadata编排，Round67四个产品失败仍待修复。

## 原始失败与已完成证据

原预检stdout已记录 `inputs 151 bad []`，随后 `Path(name)` 接收observed_missing_files的dict row而非path字符串，exit1 TypeError。原script/stdout/stderr/index/收据均保存；缺失观察未完成，preflight.json未创建，产品修改和运行0。

plan67.observed_missing_files is list[dict] with exact path:str and observed:ABSENT_DO_NOT_FILL fields (11 rows). The preserved script loops dictionaries into Path(name), causing immediate TypeError on first row. Source/pin validation already completed according to raw stdout and preserved script order. No product counterexample is established.

Existing round67 is legitimate failed-tool archive. Do not delete/recreate it or rerun dest.mkdir(exist_ok=False) from old script. New recovery metadata goes in round67/round69-metadata-recovery; subsequent Round67 code/evidence goes in fresh round67/implementation.

## 限定范围

新增恢复证据：`artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/round69-metadata-recovery/**`；恢复后Round67开发证据转到新独占 `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/**`。不改原67计划、旧失败、原缺失路径或3源码；代码修复恢复后仍严格依原67三路径/合同/一次GREEN及原验证次数。


## Task 1 — 复用已完成pins并一次补全缺失路径元数据观察

1. ROOT reads this plan then follows up the existing OC2 implementer, no child agent. Verify this bounded input_pins set and both new plan files before recovery; do not recompute all151 or repeat any product verification. Record original successful hash observation as reused provenance from exact stdout plus original script; do not invent an original per-row checks JSON that was never persisted.
2. Create the new recovery directory exclusively. Write new metadata-recovery.py containing only stdlib schema/path validation and result generation. Parse the pinned original plan67; require observed_missing_files is a list of11 rows, each a dict with exact keys path/observed, nonempty str path and literal ABSENT_DO_NOT_FILL, no duplicate paths and exact equality to plan69 registered rows. No generic coercion/fallback or row skipping.
3. Perform exactly one corrected missing-path pass using row["path"] (not Path(row)). Check target absence including dangling symlink path entries by lstat/FileNotFoundError or exists plus is_symlink; any present entry means stop, never remove it. Record each original path, expected absence and actual observation. Do not read original raw/DB, add a placeholder file, or rerun full source inventory.
4. Save exact corrected script SHA, command/cwd/env/start/end/exit/stdout/stderr and missing-path-check.json under the recovery root, exclusively. Save bounded input-pins-before-after including original failure/log/plan/auth/three sources. On any schema error, present path, new input drift or nonzero exit preserve original new raw output and stop for next Astra; no retry.

## Task 2 — 新增恢复收据并以新子目录续行原Round67

1. Only after missing-path pass succeeds and bounded pins remain unchanged, create recovery-receipt.json plus step-report.md/json under recovery root. Distinguish inherited151 exact pin observation (not rerun), newly observed11 absent paths, bounded fresh pin checks, and original exit1 TypeError. Highest result METADATA_PREFLIGHT_RECOVERED_ONLY; old failure artifacts remain paused historical evidence and round67/preflight.json remains absent.
2. Authorize the existing agent to create fresh round67/implementation exclusively for Round67 development source-before/after, logs, CPU manifests and step reports. Any new preflight receipt there must cite this recovery and original raw151 result; do not present it as the previously absent original preflight. This changes only output placement/existing-directory precondition, not the three-path code scope or repair contract.
3. Resume precisely Round67 primary/secondary exception preservation, complete partial denominators, per-case statuses and one owned fullGREEN61+at most2 registered cases, required once-only static/R03 regression, quiet source freeze and independent review. This metadata round consumes zero product runs and adds no additional GREEN budget or permission to rerun oldRED/API/actual. ROOT actual remains unauthorized.
4. If unexpected product/tool failures occur after recovery, preserve evidence and seek the next Astra before fixes. Never rerun original broken preflight script, overwrite failure reports, repeat all151 for a nicer log, change terminal mapper or expand source scope under metadata recovery.

## 实施前置和验收

原151hash不重做；本轮仅核对少量源码/计划/metadata，再单次正确验证11个dict.path仍缺失。脚本不得把dict转字符串后继续、跳过坏row、补文件或删除新出现文件。包含symlink目录项存在性，失败即保留并再Astra。

最高 METADATA_PREFLIGHT_RECOVERED_ONLY；原TypeError不改PASS，不能声称产品4fail已修复。Gate/独审/actual/formal门保持，真实实验0。所有exec require_escalated，Python只用.venv/bin/python，PYTHONDONTWRITEBYTECODE=1。

Any unexpected metadata/product failure, drift/collision or scope expansion: preserve raw evidence, stop affected work and request next actual gpt-6-astra plan; no ad-hoc recovery or repeated run.

## 实际输入指纹（13项）

未重复151，未执行修正missing循环；仅核对以下固定输入。执行者另pin本69计划两文件。

| Path | SHA256 | Bytes |
|---|---|---:|
| `AGENTS.md` | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` | 1774 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/root-round67-authorization.json` | `67050b537de55e5e95a2357a63e040ae7c123faa965369ed0d2230659d31dc6a` | 810 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/preflight-tool-failure-index.json` | `83056c5f307ccd508666397391675a093b54d7e5edfbe17edffc616537c9c5c4` | 1265 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/preflight-tool-failure.json` | `23ef0f8f1b9efb124cc94b90aa449d7b615ab81b00ce66f1e62f296b2ded19d9` | 882 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/preflight-tool-failure.md` | `f2c82d88e72ac74d237802ba4d4d8d10127e15e76a881632728b9d086f884b1c` | 621 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/preflight-tool-failure.script.py` | `7b2a8d5e07300d7c52d0b81b9447314f3ccdddefb837571c36e6bdb1c2b94307` | 1821 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/preflight-tool-failure.stderr.txt` | `4d4d28bfb6dac80168c8eda1e4942296e482006c113837c7d3d905510d7cea01` | 354 |
| `artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/preflight-tool-failure.stdout.txt` | `421937e336d8c25a8fd3fb5317c8cb1a8288139d59ddb3001698abdfa6c2f63d` | 1729 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round67-oc2-green-partials/plan.json` | `3b9af379e4d64dded875f976b47b6e7e6476976d67977ccfdcbce5e34389aea2` | 54412 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round67-oc2-green-partials/plan.md` | `62bc42d4e638fb3e0f7d423f3d6752c0e8818c2ed1adfd926e8cf71f549f2f47` | 39566 |
| `src/cloud_edge_robot_arm/research/operational_capture_v1.py` | `09f4e1ba9dbf831b2f9bbcb9cdbfeaf0e5c88ef1100840e139e746dd5303cabd` | 11100 |
| `src/cloud_edge_robot_arm/research/operational_prefix_v1.py` | `f9612b25d84e435a3d798a4fdec3f8f362ff59deec1b11b1d38a81b7a362d10a` | 53802 |
| `tests/test_operational_capture_v1.py` | `1c427a454f9bff87cc2ad23b0f141a60fd4cf7602786abac821857144a34f0dd` | 11355 |

11原missing row完整保留在plan.json.missing_row_contract.rows。规划仅新写本plan.md/json，无产品实现/验证/CLI actual/网络/Git。
