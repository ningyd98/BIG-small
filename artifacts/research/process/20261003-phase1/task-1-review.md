# T1 独立审查：历史证据冻结与研究来源审计

审查范围：`task-1-brief.md`、`task-1-report.md`、`research/models.py`、`research/provenance.py`、`test_research_provenance.py`、Phase 11.1 verifier 当前文件及其 `before/` 镜像、`docs/research/evidence_inventory.md`。只审查 T1，未修改实现，未重跑实施者已报告通过的 32 项测试、Ruff 和 mypy。

## 规格符合性结论

**尚未完全符合。** 旧 5,580 行与新论文运行分母隔离、`PHASE12_REJECTED` 和权威运行数 0 的文档边界与当前权威状态一致。`EvidenceKind`、阶段状态、必需来源字段和历史 verifier 的 `LEGACY_PIPELINE` 显式选择均满足 T1 接口要求；verifier 相对前镜像仅增加这一行，产品 `ExperimentDraft.input_mode` 仍默认 `RGBD`。但以下审计缺陷会错误报告阶段覆盖或泄露，妨碍用该结果判断 G0。

## 代码质量结论

**存在需要修复的来源审计逻辑错误。** 当前测试覆盖了常规阻塞、历史隔离、真实阶段、合法同组配对和简单跨 split，但未覆盖缺阶段时的覆盖率、同 ID 冲突记录及空字符串来源。以下均为当前代码可直接推导的反例；未扩大到后续 RGB-D、VLM 或物理运行实现。

1. **P1：重复 run ID 可隐藏跨 split 泄露。** `src/cloud_edge_robot_arm/research/provenance.py:41-45` 在第二条同 ID 记录进入 `splits_by_group` 和 `ground_truth_exposed_online` 检查之前就 `continue`。同一 `run_id` 的第一条为 `scene-1/TRAIN`、第二条为 `scene-1/TEST` 时，`duplicate_run_ids` 虽列出 ID，`cross_split_scene_groups` 和 `leakage_count` 却仍为零；若第二条标记在线真值泄露，也被漏报。这使“泄露为零”的输出受输入顺序影响。保留单一成功率分母是正确的，但重复行的冲突信息仍需参与泄露审计，或作为明确的不可通过问题报告。

2. **P2：缺失核心阶段可获得 100% 阶段覆盖率。** `src/cloud_edge_robot_arm/research/provenance.py:49-51,116-119` 以实际提供的 `len(record.stages)` 作应有阶段数。若只有 `PERCEPTION` 和 `ACTION` 且均为 `REAL`，输出 `stage_coverage == 1.0`，尽管 `audit_issues` 已写明缺少 `INFERENCE`。T1 要求感知、推理、动作各显式一次，并另报阶段覆盖率；覆盖率分母至少应包含每个新研究 run 的三个核心阶段，不能由缺失的记录自行缩小。

3. **P2：空字符串来源可被算作真实阶段及物理成功。** `src/cloud_edge_robot_arm/research/provenance.py:52-60,69-71,92-105` 使用 `bool(stage.source_hashes)` 和 `bool(record.observation_hashes)` 检查列表；`source_hashes=[""]` 和 `observation_hashes=[""]` 都被接受为非空来源。若其它字段沿用测试中有效记录，三个阶段都填 `[""]` 仍可得到 `stage_authenticity == 1.0` 和 `physical_success_count == 1`。至少应拒绝空白来源条目，避免无实际来源的 `REAL` 被计入真实性。

修复后建议用上述三个最小反例补充针对性测试，再运行 T1 简报指定的两组回归。当前报告中的 `32 passed`、Ruff 和 mypy 结果仅证明现有测试及静态检查通过，未覆盖这些反例。

## 首轮修复局部复审（2026-10-03）

**先前 3 项发现均已修复；就这 3 项放行。** 本节结论取代上文对这些问题仍然存在的判断；上文保留为首轮审查记录。

1. 重复 run ID：当前实现先将每条新研究记录的 scene/split 和在线真值标记纳入泄露统计，再按 ID 去重。冲突的重复记录产生 `conflicting duplicate run ID`，使该 ID 不进入物理成功分子；`test_conflicting_duplicate_run_reports_leakage_and_invalidates_success` 同时核对分母、两类泄露和成功数。
2. 缺失核心阶段：应有阶段数至少为三，只有感知与动作时覆盖率为 `2/3`；`test_missing_core_stage_reduces_coverage` 覆盖该反例。
3. 空白来源：`_has_hashes` 要求列表非空且每项去空白后非空，用于阶段真实性、观测来源与物理成功判断；源码树和模型快照也检查去空白值。`test_blank_hash_entries_are_not_authentic_sources` 覆盖空字符串和空白字符串。

本次仅静态核对 `provenance.py` 与 `test_research_provenance.py` 的上述改动，未重新扩大审查范围，也未重跑测试。实施者报告新增审计测试 15 passed、指定合并回归 35 passed，Ruff 和 mypy 通过。
