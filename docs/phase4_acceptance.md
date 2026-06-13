# Phase 4 验收说明

## 验收覆盖

- 35 项新增测试（合法规划、幂等性、场景充分性、语义校验、修复、dispatch、repository、prompt registry）
- 7 个验收脚本（API smoke、Mock plan、RuleBased plan、request more observation、malformed output repair、idempotency、edge dispatch）
- Phase 3/3.1/3.2 回归验证

## 验收命令

```bash
ruff format --check .
ruff check .
mypy .
pytest -q
python scripts/verify_phase3.py
python scripts/verify_phase3_1.py
python scripts/verify_phase3_2.py
python scripts/verify_phase4.py
```

## 验收标准

- 168 项测试全部通过（119 + 14 Step 0 + 35 Phase 4）
- 8 项验收脚本全部通过
- Phase 3/3.1/3.2 无回归
- mypy 通过（src/ 无错误）
- ruff format + check 通过
- 模型不可信边界强制（禁止字段拒绝）
- 幂等性和 request_id 冲突检测
- 安全绕过字段硬拒绝
- 场景不充分时返回 REQUEST_MORE_OBSERVATION
- 修复最多 2 次
- Prompt 版本追踪
- 密钥不在代码中
