# Phase 0 验收

## 状态

以下命令通过时，Phase 0 视为完成。

## 验收项

| 项目 | 状态 | 证据 |
| --- | --- | --- |
| Python 包配置 | 完成 | `pyproject.toml` |
| Ruff、MyPy、Pytest 配置 | 完成 | `pyproject.toml` |
| `.env.example` | 完成 | `.env.example` |
| 结构化 JSON 日志 | 完成 | `src/cloud_edge_robot_arm/logging_utils.py` |
| 必需 Pydantic 模型 | 完成 | `src/cloud_edge_robot_arm/contracts/models.py` |
| JSON Schema 导出 | 完成 | `model_json_schema()` 测试 |
| 五个有效契约示例 | 完成 | `contracts/examples/valid` |
| 五个无效契约示例 | 完成 | `contracts/examples/invalid` |
| 自动契约验证脚本 | 完成 | `scripts/validate_contract_examples.py` |
| 云端模型集成 | 阻塞 | 明确推迟到 Phase 1 验收之后 |
| 真实机械臂集成 | 阻塞 | 明确推迟到 Phase 9 |

## 命令

```bash
# 命令说明：按本文上下文运行该验证或环境命令，默认不连接真实机械臂。
ruff check .
mypy .
pytest -q
python scripts/validate_contract_examples.py
```
