# Phase 8.2 验收

Phase 8.2 通过命令和守卫条件验收。

## 必需命令

- `ruff format --check .`
- `ruff check .`
- `mypy .`
- `pytest -q`
- `python scripts/verify_phase8.py`
- `python scripts/verify_phase8_1.py`
- `python scripts/verify_phase8_2.py`
- `pip check`
- Phase 3-7 验证脚本。

## 新增守卫条件

`scripts/verify_phase8_2.py` 在以下情况失败：

- PCSC 任务没有产生多个周期 tick。
- 故障检测延迟退化成 0。
- 多崩溃恢复没有覆盖 9 个 Phase 8.2 crash point。
- mode、network 或 seed 分组指标全部相同。
- PCSC 没有任何至少两次监督决策的运行。

## 新增测试

- `tests/test_phase8_2_pcsc_multiple_ticks.py`
- `tests/test_phase8_2_tick_step_interleaving.py`
- `tests/test_phase8_2_tick_observes_dynamic_fault.py`
- `tests/test_phase8_2_eteac_has_no_ticks.py`
- `tests/test_phase8_2_fault_detection_realism.py`
- `tests/test_phase8_2_transition_safe_boundary.py`
- `tests/test_phase8_2_crash_points.py`
- `tests/test_phase8_2_experiment_sensitivity.py`

## 运行规模

- Smoke：45 次运行。
- Validation：675 次运行。
- Full benchmark：2250 次运行。
