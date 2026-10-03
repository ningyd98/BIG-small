# T1 交付报告：历史证据冻结与研究来源审计

## 文件与行为

- `src/cloud_edge_robot_arm/research/models.py`：新增证据种类、阶段状态与 `RunProvenance`。为区分历史记录与新试验、避免把一次软件成功当作物理成功，审计必需字段增加 `cohort`、`task_success`、`ground_truth_exposed_online`。阶段感知、推理、动作各须出现一次。
- `src/cloud_edge_robot_arm/research/provenance.py`：`audit_provenance` 输出新试验分母、物理成功数、历史数、阶段覆盖及各阶段真实性、阻塞原因、在线真值与跨 split 泄露、重复 run ID 和缺失/重复阶段问题。同组跨方法但同 split 允许配对；重复 run ID 不扩张分母。
- `tests/test_research_provenance.py`：12 项针对性行为测试，覆盖非物理证据、缺模型、历史隔离、预动作阻塞、跨方法合法配对、跨 split 泄露、在线真值、三核心阶段和重复 ID。
- `scripts/verify_phase11_1_simulation_runtime.py`：仅历史软件 verifier 的 `_draft` 显式使用 `LEGACY_PIPELINE`，产品 `ExperimentDraft` 默认 `RGBD` 未变。
- `docs/research/evidence_inventory.md`：冻结 Phase 11.1 与 Phase 12 旧证据适用范围、`PHASE12_REJECTED`、旧 5,580 行与新论文权威运行数 0 的边界。

## RED / GREEN

1. 新测试初次 RED：`ModuleNotFoundError: No module named 'cloud_edge_robot_arm.research'`，新增契约前导入失败。建立模型及审计后 `8 passed`。
2. 审查补强前 RED：缺推理仍计物理成功、重复推理仍计成功、无来源 `REAL` 阶段计入真实性、重复 run ID 扩大分母，`4 failed, 8 passed`。修正后 `12 passed`。
3. 最终合并回归（主机执行）`.venv/bin/python -m pytest -q tests/test_research_provenance.py tests/test_phase11_1_simulation_runtime.py`：`32 passed, 1 warning in 35.46s`。唯一 warning 是 Starlette TestClient 的既有 AnyIO 别名弃用。
4. `.venv/bin/ruff check src/cloud_edge_robot_arm/research tests/test_research_provenance.py scripts/verify_phase11_1_simulation_runtime.py`：通过。`.venv/bin/mypy` 同路径：`Success: no issues found in 5 source files`；配置提示 `rclpy.*` override 未使用。

## 验证范围与局限

主机执行是必要的：同一合并回归在受限沙箱运行到第 17 个进度点后挂在 TestClient portal，已中断；根代理的独立诊断表明这是执行环境限制，见 `artifacts/research/process/20261003-phase1/runtime-{hang,host}-diagnostic.log`。本任务运行的是来源审计和既有软件运行时回归，没有运行正式 RGB-D 物理试验、模型服务或真实硬件；新研究权威论文运行数仍为 0。历史数据仍维持原拒绝结论，不能通过此审计契约自动升级。

## 首轮审查修正（2026-10-03）

按 `task-1-review.md` 的三个确定反例补测试：冲突重复 run ID 的第二条含跨 split 与在线真值、缺推理阶段但其余阶段真实、空白观测与阶段哈希。修复前 `3 failed, 12 passed`；修复后 `15 passed`。审计现在先扫描所有新记录的 split 和在线真值标记，同 ID 仅计一个分母，冲突重复记录标为审计问题并禁止计物理成功；阶段覆盖分母每个新 run 至少为三个核心阶段；哈希列表须非空且每项去空白后非空。

复验：主机执行 T1 指定合并命令 `35 passed, 1 warning in 35.36s`；Ruff 精确路径通过，mypy 精确路径 `Success: no issues found in 5 source files`。warning 仍为 Starlette TestClient 的 AnyIO 别名弃用。本次修正仅涉及来源审计、测试和本报告。
