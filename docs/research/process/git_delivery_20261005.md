# Git delivery audit — 2026-10-05

The first delivery should be a coherent Stage 49 backlog snapshot: validated application code, tests, configuration, robot assets, dashboard changes, project documentation, and the precise default/test evidence dependencies below. The new `step_rgbd` module and its tests, and `artifacts/research/process/20261004-ced-development/t7b-continuous-visibility/`, stay outside this delivery while implementation and review continue. Independent core changes depend on one another; selecting only a few new modules would leave consumers, schemas, repositories, and tests inconsistent.

This audit is read-only with respect to Git and live source. It neither stages nor commits nor pushes. The root agent owns those authorized actions on `research/20261004-continuation` and should establish its upstream when pushing to the supplied origin. Audit HEAD was `ddbeb92a1aa1dfa8039f6260d6b5887c58072383`. Existing tracked research artifacts remain tracked. All excluded local files remain on disk; there are no deletion recommendations.

After the environment/weight ignore changes, the untracked artifact inventory contained 75,335 paths totaling 7,517,925,304 bytes. The explicit candidate manifest `/tmp/ced_git_artifact_candidates.json` selects 43,770 paths / 657,775,205 bytes and leaves 31,565 paths / 6,860,150,099 bytes local. Its SHA-256 is `16b8a575550942d6b6b13d9dbeb5663aa88a5b6b4251b81a8c1820f4c4938dbf`. Selected files have individual SHA-256/size records; excluded files have exact paths, sizes and reasons. This is a preparation-time review manifest, not a declaration that every candidate has been staged or validated. It is temporary local input for root's exact path selection; the resulting commit tree is the durable delivered inventory.

Candidate policy retains authored reports, bounded manifests, scripts, validation logs, nonraw review images, and frozen text source/baseline archives. The source archive classification contains 20,932 paths / 186,923,697 bytes. It rejects ordinary bulk trial observations, commands, trajectories, raw arrays and raw capture images outside the explicit roots below. Nonrequired report/metadata files above 2,000,000 bytes are left local, except frozen source/baseline archives. Nine generated assignments/pools/dependency-index JSONs totaling 37,437,621 bytes were removed by that rule. Authored download scripts and revision/checksum provenance may be retained; downloaded model/tokenizer contents, wheel and toolchain contents are excluded regardless of file size.

The following nine raw roots total 259 files / 223,058,602 bytes. All paths in the table are relative to `artifacts/research/process/`. Keep complete frame/stream joins and existing hashes within each root. Do not trim an observation file while retaining a manifest which authenticates the original bytes.

| Required root | Files | Bytes | Current dependency |
| --- | ---: | ---: | --- |
| `20261004-gripper-project-migration/model-probe/` | 28 | 2,997,277 | `vision/defaults.py`, `test_rgbd_project_defaults.py`; `visual_smoke.yaml`, both pilot foundation configs; frozen-model evidence and captures |
| `20261004-ced-development/t7b-pose-markers/actual-capture-1/` | 10 | 1,266,738 | `test_pose_marker_evidence.py` static 320-pixel decoder case |
| `20261004-ced-development/t7b-pose-markers/actual-capture-640/` | 10 | 4,984,506 | Same test's 640-pixel decoder case |
| `20261004-ced-development/t7b-pose-marker-color/actual-capture-640/` | 10 | 4,984,877 | `test_pose_marker_assets.py`, `test_marker_association.py`, `test_marker_extent_integration.py` |
| `20261004-ced-development/t7b-real-capture-v2/initial/` | 5 | 877,364 | `test_opencv_target_evidence.py` |
| `20261004-ced-development/t7b-real-clean-capture-2/initial/` | 7 | 1,253,965 | `test_opencv_target_evidence.py` |
| `20261004-ced-development/t7b-pose-marker-motion-development/attempt-1/` | 80 | 73,751,253 | `test_research_risk_sources.py` stream/audit fixtures and copied complete fixture; association/extent tests; completed centered trial and outboard comparison |
| `20261004-ced-development/t7b-visible-marker-next/attempt-1/` | 80 | 73,761,253 | Completed outboard trial, `verify_offline.py`, independent review and exact 4,807-row trajectory comparison |
| `20261004-ced-development/t8-real-raw-development/` | 29 | 59,181,369 | Actual raw/source provenance and `ced_exclusions.yaml` pinned `assignment.json` |

The centered trial's parent `header.json`, source hashes, scripts and reports belong in the durable metadata selection even though they are outside `attempt-1/`. Existing raw hash manifests bind the marker roots: 320 capture `08494e588a082c4d771a295a24c6f8e72910d605e35ee2557f4465353a16c6a6`; 640 capture `9e81fc1378f3faf288a12b29f67bef792d23414b60a657814f0614c691fa7436`; color capture `52486616e2a43b4dc8d14c1530216b142bbd6a3a857ec2be921cc2be7a80fc7a`; centered attempt `f2bbd9435438e94e835c400d6c5373fd5379bd10c5a0ff32312609b81d074b31`; outboard attempt `7e4f8931829f0d0271b6ee506653d4be93ccdf8d5efe25f606a3cc5a2c890bb9`. The T8 `source-and-payload-hashes.json` SHA is `b0d6d09e8752d0dbc77412deb238386306eb0d21268d61434845991df933b123`. The two OpenCV initial fixtures lack their own raw hash manifest; the candidate inventory records exact per-file hashes.

One additional ignored provenance input is referenced by `configs/research/ced_exclusions.yaml`, `ced_foundation.yaml` and `ced_selection.yaml`: `datasets/rgbd-ced-dev-smoke-20261004/samples.jsonl`, 2,315,487 bytes, SHA-256 `595c3ee953e5169e16739ae0960c1abd821f548577dd15b82d99d83d7c2bf655`. It is outside the artifact-only candidate list and should be selected as that exact single file if these configuration paths are delivered as runnable inputs. This does not justify staging the whole ignored datasets tree. Delivering only the configurations and a hash leaves that provenance input unavailable in a clean checkout.

Exclude these exact download/active prefixes:

- `artifacts/research/process/20261004-t7-parallel-local-models-physics/gemma-minicpm/gemma-model/`
- `artifacts/research/process/20261004-t7-parallel-local-models-physics/gemma-minicpm/minicpm-model/`
- `artifacts/research/process/20261004-t7-parallel-local-models-physics/molmo/models/`
- `artifacts/research/process/20261004-t7-parallel-local-models-physics/molmo/toolchain/`
- `artifacts/research/process/20261004-t7-parallel-local-models-physics/molmo/wheelhouse/`
- `artifacts/research/process/20261004-ced-development/t7b-continuous-visibility/`

The Molmo toolchain includes approximately 28 MB of downloaded static Python libraries; its wheelhouse contains `tokenizers` and `transformers` wheels totaling 15,241,146 bytes. The earlier model/environment inventory included approximately 64 GB of downloaded weights and two extra environments totaling 11,659,945,041 bytes. The root's `.venv-*/` and weight suffix ignore rules prevent those from entering ordinary candidate enumeration. No remaining inventoried untracked nonmodel/nonenvironment artifact file exceeded 100,000,000 bytes; the largest was an older `physical-evidence.json` at 31,495,158 bytes, which is outside the required raw selection.

All runtime database contents stay local. Exact database paths, relative to `artifacts/research/process/`, are:

- `20261004-gripper-project-migration/{workbench,workbench-v2}/{model.db,runtime.db}`
- `20261004-t17a-workbench/{e2e,e2e-final}/model_control.db`
- `20261004-t7-parallel-local-models-physics/physics/{pre-corrected-fullsuite-db-state,pre-restoration-generated-db-archive}/{baseline-model_control.db,h3-model_control.db}`
- `20261004-t7-parallel-local-models-physics/physics/regression-runtime/{baseline-model-control.db,baseline-relevant-v1-model-control.db,h3-model-control.db,h3-relevant-v1-model-control.db}`
- `20261004-t7-parallel-local-models-physics/physics/workspace/data/model_control.db`

These are 15 database files. Their names were inventoried; contents were not read. Artifact-wide ignore patterns for `.db`, `.db-shm`, `.db-wal`, SQLite variants and downloaded wheel/toolchain trees avoid accidental inclusion beyond the currently enumerated paths. Keep repository schemas and public initialization scripts. Real `.env` files, credentials and local profiles are excluded; no secret values were read during this audit.

Older T7 retest/larger-model runs, T8 foundation's 120-trial bulk raw JSON/RGBD, repeated raw copies inside source archives, generated workbench databases, and the other excluded artifacts remain local. Their retained reports/hashes document their existence but do not make missing payloads reproducible from this Git delivery. Historical complete-package restoration and a portable bulk raw archive with retrieval information remain pending; this does not block pushing the validated implementation and required fixtures now. Do not claim that a source hash or a successful offline fixture test establishes new physical/calibration evidence.

For this backlog, one coherent implementation/test/config/assets/default-fixture commit followed by a documentation/evidence-archive commit is reasonable if both are delivered together; one scoped backlog snapshot commit is also coherent. Future bounded changes should commit their code, relevant tests, docs, immutable input/source hashes and validation result together after checks, then push the branch. Preserve failures and exclusions in the evidence inventory. Use Git history for source versioning instead of continually copying the entire project and its old raw payloads into new module directories. A new actual trial needs its own exact source, group identity, protocol and raw inventory; a software-only change needs no repeated physical run unless its claims require one.

This audit inspected filenames, sizes, content hashes, current literal source/test/config references and Git status. It ran no broad suites, simulation, rendering, model/provider calls or historical trial replay. The delivery commit and push result must be recorded by the root agent after its staged-tree review and required validation.


## 实际交付结果

2026-10-05已完成提交并推送到[研发分支](https://github.com/ningyd98/BIG-small/tree/research/20261004-continuation)，上游为 `origin/research/20261004-continuation`。推送退出0；2026-10-05 08:52:07 UTC以 `git ls-remote` 核对远端，远端SHA与本地HEAD及上游均为 `f7860ffd551cf663ffd78f683f7df616da70d98f`。本段与机器记录作为后续文档提交交付，其提交号见Git历史。

- `d3472a562356e6edc3dc1da2aa07a45096b54e5c`：阶段49研发快照，44037个所选路径、664996295字节；代码、测试、配置、资产、报告、冻结文本源和九个必要原始根及单个provenance输入一并交付。
- `f7860ffd551cf663ffd78f683f7df616da70d98f`：阶段50逐步RGB-D研究记录器，34个路径；含实现、测试、原失败/初版及最终源、限定独审、阶段总结和Git清单。

定向七文件81项通过；本模块17项和独立17项通过，集合重叠不相加。所提交范围的差异、12份当前文本与26个本地链接检查通过；未宣称全仓测试通过。新完整动作内采集脚本仍未实际运行，尚未通过的脚本和后续native参照工作未进入上述实现提交。保持真实Max、native与正式验收的原缺项口径。

[tmp审计输入的完整交付副本](../../../artifacts/research/process/20261004-ced-development/git-delivery-20261005/packaging-manifest.json)、[快照范围](../../../artifacts/research/process/20261004-ced-development/git-delivery-20261005/backlog-scope.json)及[远端交付记录](../../../artifacts/research/process/20261004-ced-development/git-delivery-20261005/delivery-record.json)已进入仓库。manifest逐项记录本次选择的哈希与留在本地的路径/原因；真实`.env`/凭据、环境、模型权重、数据库及非必要批量原始数据留在本地。该Git交付包含必要运行fixture，不等于所有历史大体积实验载荷的远端备份。

后续每项可交付变更在验证后，把实现、相关测试、步骤报告与阶段总结一并按明确路径提交并推送；推送后核验远端SHA与上游。使用Git版本管理源代码，实际实验只归档该次必要来源及完整原始清单。保持独立研发分支，待整体验收后再按用户指令合并；本次没有合并主分支或改写远端历史。

交付记录提交 `93e3222131d9400684ce99046c81fa4ea5a10ec9` 已再次推送，并经 `git ls-remote` 核对。其所附 `push-initial.log` 保留GitHub原始输出的4行尾部空格，该提交的含原始日志差异检查退出2；源码/报告推送前限定检查退出0的记录保持不变，不宣称包含该原始日志的差异检查通过。本补记保留原日志与原提交，后续文档差异单独核对。


## 第51步实际交付

阶段51实现提交 `f3f59c412b3dc5d75222525a06495cd0fcecd02f` 已推送研发分支。2026-10-05T09:53:05.757757+00:00核对本地HEAD、上游及 `git ls-remote` 远端SHA一致，推送退出0。140个变更路径包含动作参照实现、相关测试/独审、失败逐步实测的原始证据与阶段总结；新诊断和Task2活动源码未混入。实现提交后已跟踪工作区无未提交变更，历史批量原始资料及活动源码仍在本地。见[本步交付记录](../../../artifacts/research/process/20261004-ced-development/git-delivery-step51.json)。

源码、报告和其他非日志差异检查退出0；原终端日志有242处尾部空格，保留原始字节并在[限定检查记录](../../../artifacts/research/process/20261004-ced-development/git-check-step51.json)单列。完整含日志检查退出2，不宣称全范围零空白问题。29新模块测试、93项受影响回归及独立29项的范围重叠，不相加；真实逐步采集仍11次/10保存/1失败、INCOMPLETE。没有把Git交付提升为native或正式研究验收。本段及交付记录随后续文档提交推送。


## 本地对象维护

只读检查发现22个旧临时对象/打包文件，约128.5 GB，当前HEAD树约1.59 GB、64644文件，最大单文件低于100 MB；两者不能混作本次提交大小。磁盘仍约716 GB可用，gc.log仅报告不可达松散对象过多。未发现匹配Git/repack进程或可读FD占用，但进程检查受权限限制，不据此删除对象。

已仅在本仓库将 `gc.auto` 从未设置改为0，暂停失败的自动整理；可用 `git config --local --unset gc.auto` 恢复。全部临时文件、packs、reflog及可恢复对象原地保留，没有运行prune/gc、改写历史或回收空间。受控存储清理另行处理，当前提交与推送不受影响。见[只读清单](../../../artifacts/research/process/20261004-ced-development/git-delivery-20261005/local-storage-audit.json)和[本地维护结果](../../../artifacts/research/process/20261004-ced-development/git-delivery-20261005/local-maintenance-result.json)。

## 第52步实际交付

实现提交 `05d971f82b6542fdd78c2ba12ea8d211f86f94b9` 已推送研发分支；2026-10-05T10:56:55.124091+00:00 核对本地、上游及 `git ls-remote` 远端一致，push退出0，提交后已跟踪工作区干净。237个变更路径/8,746,641字节含冻结诊断、142份完整原始件、v2核验器、定向测试/独审和阶段报告；活动guard/native源码与历史批量原始载荷未混入。

48项定向CPU通过（诊断31＋新核验器17），Ruff和非日志差异检查通过。原始终端日志17处尾空格保留，完整差异检查退出2，不宣称全范围无空白问题；首次同名测试收集失败及修正命令后的日志均保留。真实诊断仍末尾copy guard退出1、旧试验11/10/1不改写、无完整horizon/native/正式验收。见[限定检查](../../../artifacts/research/process/20261004-ced-development/git-check-step52.json)和[交付记录](../../../artifacts/research/process/20261004-ced-development/git-delivery-step52.json)。本段及交付记录随后续文档提交推送。


## 第53步软件交付

已审状态保护和校准读取器及其五个源码/测试、报告、独审与原始失败证据由 `486ec6eef6acaf3158e33add238b4067ae3e0aeb` 提交并推送。远端、本地、上游一致，push退出0；207个变更路径/1,428,344字节。root新复跑状态保护62项、校准61项及五文件Ruff通过，范围不相加为全仓或研究验收。

新V3开放操作身份/失败分母问题及RESET/UTC设计未纳入此提交，实际完整采集、独立校准与正式阶段未完成。完整差异检查退出2，301条日志尾空白按原字节保留；非日志检查退出0。首次检查解析误把日志中的added traceback行当diff诊断，派生记录已更正，初始记录仍保存。详见[机器交付记录](../../../artifacts/research/process/20261004-ced-development/git-delivery-step53.json)、[本步报告](../../../artifacts/research/process/20261004-ced-development/report-step53.md)及[差异检查](../../../artifacts/research/process/20261004-ced-development/git-check-step53.json)。本段和机器记录随后续文档提交推送。

## 第54步：Astra计划与V3软件修复交付

第54步Git交付：Astra计划与10任务/48步骤报告、V3已审三份源/测试及本轮协议/反例/独审、RESET/UTC设计独审和配置/工具链报告已提交 `eed552283c1804e707f661c82ab547b7e1ac2916` 并推送；本地、上游及远端SHA一致，push退出0。112个变更路径/1,264,879字节。完整差异检查退出2，101处日志尾空白及1处已冻结legacy fixture末尾空行按原字节保留；新增代码与文档检查退出0。完整实际采集原件与活动离线结果、未验收R2源码和历史批量raw未混入。见[机器交付记录](../../../artifacts/research/process/20261004-ced-development/git-delivery-step54.json)。本段与机器记录随后续文档提交推送，采集退出0不表示完整性、decoder或正式验收通过。
