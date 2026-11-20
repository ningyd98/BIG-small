# Astra V10 Phase2 独立公开交付计划

本轮由 `gpt-6-astra` 规划；仅规划，未实施 Git 修改或推送。保留当前完成工作和原提交 `8ff56b1cc5c455be9109b7a9f0c7d629ad746c83`，新分支 `research/harness-candidate-v10-phase2-20261121` 严格从实际远端基线 `7e44e8657a2ec7f547ba87b6748173c7e4925b48` 重建。

## 问题与原始证据

直接推送原分支将发布可达父提交中的私有原始日志及无关本地历史证据；只限制当前 stage 路径不能隔离父提交。已只读核实 merge-base 等于指定远端基线，六个 src/configs 依赖与父任务一致。实际 ls-remote 由父任务执行并报告，实施前须重核。现有公开 software-log-provenance.json 标注 retained_privately；本计划只嵌入安全标题、字节数和哈希，不复制原始私有内容。证据清单和全部输入 SHA256 见 plan.json。

## 实施顺序、验证与边界

1. 只读保存当前 HEAD、工作树状态、生产/测试文件 SHA256 和本地原始验证证据；禁止 reset、stash、clean、rebase、amend、删除原日志、覆盖冻结原件。复核本计划输入与当前完成改动一致；若独立实现尚在更新，待其验证完成再固定最终源清单和哈希。

2. 实施前重新 git ls-remote origin refs/heads/research/harness-candidate-20261118，要求仍为指定远端基线；确认新分支本地及远端不存在。远端前进或目标已存在则停止交付并重新评估，不强推、不覆盖。确保基线对象存在；如缺失仅精确 fetch 所需来源。

3. 新建独立研发分支 research/harness-candidate-v10-phase2-20261121，起点严格为 7e44e8657a2ec7f547ba87b6748173c7e4925b48。允许 git worktree add --no-checkout -b <new-branch> <new-worktree> <base>，仅在新 worktree 设置 sparse-checkout（优先 cone：src、configs、tests、scripts；根级配置文件随 cone 保留）。不要检出整个 artifacts/experiments/cache，完整树约 13.03 GB（父任务测量）。按实际测试依赖仅增加精确必要目录，记录它们；不得改写原工作树或迁移原分支。

4. 从原父提交精确导出六个依赖文件，从已完成并验证的原工作树精确复制三个 Phase2 生产文件与三个测试，记录各来源与 SHA256；不用 merge/cherry-pick 原提交或整目录复制。六个依赖的工作树字节必须与 8ff56b1c 对应 blob 一致，如不一致先复核范围。比较新旧 src/configs 全部路径的 Git blob/文件哈希映射（含新增删除和 mode），验证新交付源码与已验证目标完全一致，而非仅比九个文件。

5. 在新 worktree 生成四个指定 public 派生文件并复制本轮这两份安全计划。其他阶段原计划、输入清单、原始日志不得整包复制。public 派生报告只含 repo-relative 路径、非敏感测试名称/计数/退出码、版本、来源 commit 和 SHA256、RED/GREEN 判定及局限。原始日志仍保存本地，以安全标题和哈希关联；不抄本机绝对路径、环境变量、凭据、历史原始数据/负载。注明这些是派生摘要而非完整远端复现包。

6. 在新 worktree 使用相同受控 Python 环境运行根任务规定的完整聚焦/Phase2 软件回归及六个 Phase1 依赖对应必要回归；至少包含本轮三个测试文件。可复用原 .venv 的解释器但 PYTHONPATH 必须显式指向新 worktree/src 与新 worktree，并检查 cloud_edge_robot_arm 及修改模块 __file__ 全部来自新 worktree，避免 editable-install 误测原源码。保存实际命令、版本、退出码、测试收集数与哈希，公开副本去本机路径。Ruff 和 mypy 使用相同参数比较前后诊断，不能因 sparse 缺依赖而缩减原已承诺验证。

7. 历史原件兼容验证仍在受控本地只读执行；不得把原件复制到可发目录。公开只保留安全样本标识、原字节哈希、验证状态和 payload/digest 不变结论。新交付源码哈希与该验证源码必须匹配。没有真实模型/硬件/v10 运行，不宣称正式研究验收。

8. 提交前按下方精确 stage_allowlist 逐项 git add -- <paths>；public 文件在 sparse 范围之外时用精确 git add --sparse -- <path>，不得添加整个 artifacts 目录。逐项审查 git diff --cached --name-status、--stat 及内容，暂存路径集合必须等于最终实际批准清单（不含未生成文件）；禁止 git add -A、git add .、git commit -a。

9. 创建单一或少量可审查的新提交。验证指定 base 是 ancestor，8ff56b1c 不是新 HEAD ancestor；git rev-list <new-head> --not <base> 枚举每个新可达提交，其 parent 链必须仅接入指定 base，逐个检查所有新增/修改路径与 blob。拒绝私有日志、*.local.json、原始运行数据/数据库、凭据、权重、SDK 或未经批准路径。删除末端私有文件不能消除中间提交泄漏，因此不能只看末端 diff。

10. 检查完整提交树：所有非 allowlist 路径和 blob 必须与 base 完全相同，allowlist 内容通过人工和自动敏感信息扫描；旧公开 provenance 中 retained_privately 原始路径/原始 blob 及本轮本地证据不得出现在新增历史或新树。确认既有公开副本字节保持不变。若 base 本身已含应私有内容，停止并报告，不擅自删除、改写远端或声称整个历史已净化。将检查范围精确表述为基线审查和新发布增量边界。

11. 仅在全部验收通过后显式 git push -u origin research/harness-candidate-v10-phase2-20261121:refs/heads/research/harness-candidate-v10-phase2-20261121，不使用 --all、--tags、--mirror 或 force。核对本地 HEAD、该分支 upstream 和 git ls-remote 新分支 SHA 完全相同，并复核旧远端分支仍为原基线。最终报告新分支与 SHA；原工作树、原 commit 和本地 raw 均保留。

## 精确暂存允许清单

- `configs/research/native_registered_single_teacher_p0_v10_20261121.yaml`
- `src/cloud_edge_robot_arm/edge/safety/context_builder.py`
- `src/cloud_edge_robot_arm/edge/safety/models.py`
- `src/cloud_edge_robot_arm/edge/safety/rules.py`
- `src/cloud_edge_robot_arm/research/native_calibration_collection.py`
- `src/cloud_edge_robot_arm/vision/native_completion_horizon.py`
- `src/cloud_edge_robot_arm/contracts/models.py`
- `src/cloud_edge_robot_arm/research/native_collection_application.py`
- `src/cloud_edge_robot_arm/research/native_collection_grounding.py`
- `tests/test_contract_timeout_metadata.py`
- `tests/test_native_collection_context_steps.py`
- `tests/test_native_collection_grounding.py`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round-v10-phase2-public-delivery-20261121/plan.md`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round-v10-phase2-public-delivery-20261121/plan.json`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round-v10-phase2-public-delivery-20261121/source-manifest.public.json`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round-v10-phase2-public-delivery-20261121/validation.public.json`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round-v10-phase2-public-delivery-20261121/stage-summary.public.md`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round-v10-phase2-public-delivery-20261121/delivery-provenance.public.json`

## 前置条件与验收

- Current fixes complete and independently verified; exact intended source bytes frozen.
- Separate writable worktree, sufficient disk, Git object availability and origin access.
- All required software test dependencies available; no new real-run authorization.
- Original worktree modifications, old HEAD and original evidence preserved.
- New branch descends from exact remote base, not the private source commit.
- New reachable history and tree add only exact reviewed allowlist; no private blob or unrelated path added.
- New worktree source identity matches completed source and required software checks run against new modules.
- Published derived reports distinguish software verification from real-run and formal research qualification.
- Local/upstream/remote new-branch SHA equal; original remote branch unchanged.
- Unexpected test failure/new root cause or expanded source scope requires new Astra round.
- Remote drift, sensitive content in base, unexpected staged path/blob or source hash mismatch blocks push pending diagnosis.

本轮原始 RED、GREEN 与历史原件继续保留本地；派生报告和清单不是完整远端复现包。不执行真实实验，不把软件通过替代研究验收。

## 输入 SHA256

- `configs/research/native_registered_single_teacher_p0_v10_20261121.yaml` — `2b893cbcd1b959703ceada3663433eebb975adbcf8278a522967f2ad12131cf8`
- `src/cloud_edge_robot_arm/edge/safety/context_builder.py` — `4615404f4259210fca1b7218cc9e5a1dc683721f0218367083a957bf41396bed`
- `src/cloud_edge_robot_arm/edge/safety/models.py` — `9597cecf9ff02c1909f705353820901aaa4219b5f71083e89b082f11f1c2d135`
- `src/cloud_edge_robot_arm/edge/safety/rules.py` — `be5911abef6b85b9f11b07c2ddf80adfc9f91b7f1837dd80692c78f9f8c99b01`
- `src/cloud_edge_robot_arm/research/native_calibration_collection.py` — `2ee3f55bfd4e0ed0d4c186197e26dc5b489f23994d2d9df8f0225de8d81cf5cc`
- `src/cloud_edge_robot_arm/vision/native_completion_horizon.py` — `163c603016096529a78117167b62cb0f68d589498ba6ff88f29379271ecfa157`
- `src/cloud_edge_robot_arm/contracts/models.py` — `d9b3888fca6bb46c62326c9bf5fd49cf4c646ce21cf29994315107bf41d79464`
- `src/cloud_edge_robot_arm/research/native_collection_application.py` — `bac18e903699ffbd70f76ccc048481c806b5d6a2f554f20c3b124f5b395f8168`
- `src/cloud_edge_robot_arm/research/native_collection_grounding.py` — `720a999f2e7b349eca2adad055fd69eb31e634c013aa8dee3cf4c208ac188204`
- `tests/test_contract_timeout_metadata.py` — `b34ecfd7c2a257c43c464bc5b0cd7e6934b5c5fcee1f87ea12af8ecb8bf17fc5`
- `tests/test_native_collection_context_steps.py` — `1e010dabe0e5f57d8ee90daf9a301c3c799c38ae49e96328f29376a4c558cb3f`
- `tests/test_native_collection_grounding.py` — `bc02f9f4c7f5e439c3932e84baa13bfaa41ffae9df0ab20de6092c8d20f0209b`
- `pyproject.toml` — `034a85388f25f1aedfb856f1783e6d3c6a3413f00d4a1825b907fe3749399565`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round-p0-teacher-active-checks-20261121/software-log-provenance.json` — `f9c86304e47e1d6db4fe25e9323e359c320ad3e2938596945bfb0f460a5134d0`
- `round-v10-phase2-metadata-compat-20261121/plan.md` — `6803b2a350a1b3dc9d9dd2850771e39a4b05a95e1821e32cb5f1ce1bdd996fc5`
- `round-v10-phase2-metadata-compat-20261121/plan.json` — `7d28f033f99f0890d09925dafb8a03e09cf0f6105a86ab1b85416a99640ae6bf`
- `round-v10-phase2-metadata-schema-20261121/plan.md` — `75c877d3338f2d390748c535688effb6de8c86d64d2f836b721fae13eeb11b1d`
- `round-v10-phase2-metadata-schema-20261121/plan.json` — `c1e8353c459a282ff4ca5d3e02da74094e382b5c75e20c8d4994072e72a50d06`
