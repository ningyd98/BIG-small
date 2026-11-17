# Phase12 clean provenance 与运行证据缺口窄修计划

> **For agentic workers:** 按已授权执行方式使用 executing-plans 逐项执行；本 Astra 子任务仅交付计划，不实施、不跑长测。

**Goal:** 修正旧测试把 clean provenance 当作整体验收充分条件的错误，保留默认 Mock/RGBD 的真实阻塞与 GAP。

**Architecture:** 生产验证器、adapter 与运行契约不变。目标测试直接断言该默认环境的 GAP；用三个快速负控制证明 clean provenance 无法覆盖运行证据缺口，现有正控制仍证明证据齐全时可以接受。

**Tech Stack:** Python 3.12、pytest、现有 Phase12 verifier。

**Spec:** 当前父任务的窄修授权、项目 AGENTS.md；本轮原始失败及下面 SHA 清单。实际规划模型 gpt-6-astra，无替代模型。

## 问题与已核实证据

- HEAD 为 `41bb33344c0463a979327d0c78e2acd1088b458f`。原始单项失败耗时 652.20 秒，pytest 返回 1；失败发生于测试第 1954 行要求 ACCEPTED，实际为 GAP。
- 新旧 summary 都是 `PHASE12_VALIDATION_PIPELINE_ACCEPTED_WITH_RUNTIME_EVIDENCE_GAPS`、`PHASE12_FULL_PROFILE_NOT_READY`、`NOT_RUN`。二者 F20 都为 18 条 `BLOCKED_BY_ENV`，failure type 含 `RGBD_CAMERA_REQUIRED`；恢复、重复竞争、恰好执行一次三项 evidence check 均 false。
- 旧原件来自 `f258df862d96f25c2a0507f4b3b9f4f83049aa75`，provenance false；新原件来自当前 HEAD，provenance true。旧 helper 仅由 provenance 分支而偶然通过旧原件；clean provenance 暴露了错误期待。
- 生产 `validation_ready` 还要求所有 checks 为真与多项运行计数条件；它正确拒绝缺口。`git diff f258df86..HEAD` 对该测试、verifier、simulation_runtime adapter 没有变化。
- 原始失败足以作为本轮 RED；规划者没有重跑测试或实验。磁盘 AGENTS.md 为 2026-11-13 按需 Astra 版本，本次有明确 Astra 委派授权。

## 限定范围与禁区

仅修改 `tests/test_phase12_2_runtime_authenticity.py` 的目标测试、删除仅此一处调用的 `_assert_validation_status_matches_provenance`，并加入小型 verifier 负控制。实施者另写本轮步骤报告与阶段总结；原件只读。

不得设置 LEGACY_PIPELINE、改变 RGBD 默认值、伪造脏/净 provenance、修改生产 verifier/adapter/验收阈值、修改原始实验或清理失败。不得新增模型/真机运行或推送；本轮不重跑无关长测组。

## Review Focus

- clean provenance + 三种缺口逐一出现：均应 GAP，而非 ACCEPTED。
- 三项证据完整：既有正控制仍 ACCEPTED，但 full execution 必须 NOT_RUN。
- dirty provenance：既有负控制仍 GAP，不能借本轮放宽 provenance。
- 旧脏原件与新净原件：修复后的相同目标断言都通过；原始字节不变。
- 新运行与原件重放：单独记录执行代码 SHA 和原件 source SHA，不把软件通过升级为真实 F20/full 验收。

## Task 1：测试期待与最小验证

**Files:** Modify `tests/test_phase12_2_runtime_authenticity.py`。生产文件只读。

**Interfaces:** 沿用 `_write_minimal_validation_artifact`、`_patch_minimal_validation_verifier` 和 `verify_phase12`；不增加产品接口。

- [ ] 实施前复核 plan.json 中相关 source/input SHA、HEAD 与范围；若仅独立无关工作改变 HEAD，记明新 HEAD 并核验相关源仍相同。相关源变化需先复核计划。
- [ ] 保留原 RED 日志。目标测试保留全部 paired/count 断言，将 helper 调用换成直接断言 GAP、NOT_READY、NOT_RUN，以及 `recovery_evidence_valid`、`duplicate_competition_evidence_exists`、`runner_invocation_count_exactly_one` 均 `False`；删除闲置 helper。不复制整个生产接受谓词。
- [ ] 添加 `test_clean_provenance_does_not_accept_runtime_evidence_gaps`，参数化上述三项及对应 `_recovery_evidence_valid_for_rows`、`_duplicate_competition_evidence_exists`、`_runner_invocation_count_exactly_one`。先用现有 minimal fixture/patch helper，再只覆盖该 evidence 函数为 false；断言 provenance true、指定 check false、GAP、NOT_READY、NOT_RUN 与 gated authoritative count 为 0。属于合成单元负控制，预期现有生产代码即可通过，不伪造 RED。
- [ ] 快速 pytest 仅运行新三例、`test_validation_acceptance_uses_readiness_only_full_profile_status` 和 `test_verifier_rejects_validation_evidence_from_dirty_worktree`，预期五例通过。使用新的 output/log/JUnit/basetemp。
- [ ] 运行下节只读原件断言重放；新旧各一例通过，输入 SHA 前后一致。
- [ ] 在稳定记录的测试源码修订及真实 clean provenance 条件下，仅重新执行原失败节点一次。新 basetemp 与所有结果目录不得覆盖原件；沿用原记录 `.venv`、PYTHONPATH、线程数 1 与 EGL，分配可用 CPU。预期 pytest 一例通过，生成的新 summary 仍是 GAP/NOT_READY/NOT_RUN，F20 18 条仍阻塞，三项仍 false，provenance true。
- [ ] 记录步骤报告与阶段总结：开发自检、原件重放、新单项运行、正式研究验收边界分开。提交/推送不由本规划子任务执行。

## 快速复用不可变原件的具体方式

用项目 Python 通过 `runpy.run_path` 载入修订后测试文件，取出目标 test 函数，在该函数的 `__globals__` 中仅将 `_run_validation_pipeline` 替换为明确的 no-op，然后依次以两个原件的 `phase12_2` 父目录作为 `tmp_path` 调用目标函数。该测试余下部分仅读取 paired 与 verification JSON，不创建实验、也不改原件。前后校验这两类被读取 JSON 的 SHA，并附带本计划原始 manifest/summary/receipt 输入哈希；标记 `ORIGINAL_ARTIFACT_ASSERTION_REPLAY`、`runtime_invoked_by_replay=false`，禁止记作新 pytest/pipeline 运行。

如另外重跑生产 verifier 检查原件，必须把 `--output` 指向原 artifact root 外的新目录，结果标记“旧原件的新代码验证”。这不是必需快测，也不能替代新的单项 pipeline。不得把原 `verification` 目录当输出。

## 实际运行前置条件与 SHA 记账

新单项约 11 分钟；无需重跑整组。保持默认 Mock/RGBD、无模型/真机启用、原件冻结、独立新 basetemp。确保相关源码在运行期间稳定；clean provenance 必须来自真实稳定源码状态，可按父任务已授权流程处理待提交测试，不能改 provenance 或用未提交结果冒充 clean。

每份记录至少注明 evidence kind、原件 source commit/tree hash、执行验证代码 commit、实际 clean/dirty 状态、测试文件 SHA、dirty 时 diff SHA、输入前后 SHA、输出日志/JUnit/result SHA 和命令/环境。旧原件 SHA 永远是旧原件生成时的修订；补充自检和最终集成提交不能回填成原件生成 SHA。若最终集成提交与被测提交不同，两者都记录。若新 clean 分支运行暂时不具备条件，只报告快测/重放，不关闭新单项运行待办。

## 验收边界

软件完成要求五项快控制、两份原件重放、一次真实 clean provenance 的新目标节点均通过；保留三项 false 与 GAP。默认 F20 阻塞仍表明未调用执行器；本轮不证明 full profile 运行、论文最终验收、真机或模型能力。不将清单/派生报告称为完整远端复现包。出现计划外失败、新根因、相关输入变化或范围扩大，暂停相关修复并按父任务 Astra 约束制定新计划，独立任务继续。

## 关键输入 SHA256

完整清单含两组各 18 份 F20 receipt，见同目录 plan.json。下列为核心 source、失败与 summary/provenance：

| 路径 | SHA256 |
| --- | --- |
| `AGENTS.md` | `7f4f8b080b2f1e99b53d24aeebf62f51815315c69a40dc9223d2e974c3c40cdb` |
| `pyproject.toml` | `42fdefae6dff25d26e3ded9ab39c7910ee8116f4aed2e9d8f60eee23809e0933` |
| `tests/test_phase12_2_runtime_authenticity.py` | `8278bff37a907727fd0da2a8d44588bc4fa4496e4ab6580dc7b4dcedc51e58bf` |
| `src/cloud_edge_robot_arm/final_evaluation/validation.py` | `86dc6a65f8d101caa3ea7def9e27691ae940aa85a68231dc1a9953333c7de786` |
| `src/cloud_edge_robot_arm/final_evaluation/adapters/simulation_runtime.py` | `bb8bcc9f1cce4f5b04f724480f0910e6d0b2282ecaf89606f662d37cbefbfa55` |
| `scripts/verify_phase12.py` | `ebc542770aaadfb09a6e65eb0a113f621b5ef7e6f457869bd2570e7d662c65a9` |
| `experiments/results/phase9/grasp-lift-stop-20261117/regression/phase-long-03/pytest.log` | `f9019d2c51bbfbbcff4089470edbf7718fb8b34ee1c3625c6c8d70ac2679db16` |
| `experiments/results/phase9/grasp-lift-stop-20261117/regression/phase-long-03/pytest.xml` | `be6e1c81d606ee179cfaa2b34b075993a5784b01c61de40ecdaddca772f4d6a1` |
| `experiments/results/phase9/grasp-lift-stop-20261117/regression/phase-long-03/result.json` | `519d6fe075698f6c9f518324fba6aae97840a87d2d9eec4fab5a005f115aee75` |
| `experiments/results/phase9/grasp-lift-stop-20261117/regression/phase-long-03/nodes.txt` | `21bf92a404fcc13c472c7fd9d41e9551de22460f60b85ad41764c6a3566d0fdd` |
| `experiments/results/phase9/grasp-lift-stop-20261117/regression/phase-long-03/tmp/test_paired_summary_marks_isaa0/phase12_2/verification/phase12_summary.json` | `1881663293bd7c1962a13eae2b65cd9b73bb8bd0e1113c8d7d2f62456b61a16f` |
| `experiments/results/phase9/grasp-lift-stop-20261117/regression/phase-long-03/tmp/test_paired_summary_marks_isaa0/phase12_2/verification/run_integrity_verification.json` | `8ce1a2baa4c6d64dfb69d1358f4e65ee793ac27ea744659adff2c6d67b9d5ce9` |
| `experiments/results/phase9/grasp-lift-stop-20261117/regression/phase-long-03/tmp/test_paired_summary_marks_isaa0/phase12_2/manifests/provenance.json` | `4477c38cb8fdb4d308356825d2f3292267c1e1a40b1ff822fd19b004c36637a7` |
| `/tmp/bigsmall-phase12-independent-2/test_paired_summary_marks_isaa0/phase12_2/verification/phase12_summary.json` | `fb7101af608b6e1e4a7cb64fda2435e5bd99626e2a27abd872377b359d51c130` |
| `/tmp/bigsmall-phase12-independent-2/test_paired_summary_marks_isaa0/phase12_2/verification/run_integrity_verification.json` | `bd52125a2893457496e1d6b580c29774351ea2750ef63a5eb14099f682075030` |
| `/tmp/bigsmall-phase12-independent-2/test_paired_summary_marks_isaa0/phase12_2/manifests/provenance.json` | `dab0473b155ce37a171ac9ca1671966a02d217c2b2ad0d2cdee6c5cccb94a255` |

计划自检：范围只含旧测试错误；生产契约保持；正负控制齐全；原件复用与新运行分离；本次实际只写计划二件，未执行验证。

## 独立运行前置调整备注（父任务回传）

父任务报告另有 55 项与本 Phase12 helper 不同根因的运行前置失败：suite-06 的 52 项 encrypted_model_secret_store 因原 basetemp 位于祖先 group-writable 的 worktree 下，被既有生产规则拒绝；render-suite 的 3 项因离线输出 guard 仅允许 `/tmp` 或原批准根，而本轮 basetemp 落在仓库 raw 路径而被拒绝。父任务已保留原命令与日志，正在独立原生 `/tmp` 下以相同用例重跑。此处是父任务已报告的诊断，规划者未独立复查这两组原日志，亦未执行它们。

这些工作仅调整运行前置，不扩大本计划源码范围，不改产品规则或测试断言。分别保留原失败与新结果，核对同一源码修订、文件 SHA/必要 diff SHA，并记录新 basetemp/命令与结果哈希。不得将重跑通过写成原失败不存在，亦不得与 Phase12 clean provenance 根因合并。
