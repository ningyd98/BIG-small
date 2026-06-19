# 贡献说明

## 开发环境

```bash
# 开发环境：安装仿真开发依赖，不下载模型或连接真实硬件。
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev,sim-mujoco,sim-analysis]"
```

## 分支和提交规则

- 除非维护者明确要求直接改 `main`，否则使用 topic branch。
- 提交信息使用 Conventional Commit 前缀：`feat:`、`fix:`、`refactor:`、`test:`、`docs:`、`ci:`、`chore:`。
- 不要 rewrite 已推送的 `main` 历史，不要 squash 已推送 commit，也不要 force push。

## 必跑检查

```bash
# 必跑检查：覆盖格式、类型、单测和文档一致性。
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q
python scripts/check_docs.py
```

环境相关 verifier 只在满足对应文档要求的主机上运行。

## 文档规则

- 行为、公开入口、安全边界或 verifier 状态变化时，同步更新文档。
- README 保持简洁；详细命令列表放在 `docs/verification.md`。
- 没有权威硬件证据时，不得宣称真实机械臂验证完成。

## Artifact 规则

- accepted artifact 只有在明确验证任务要求时才可以提交。
- 不要提交大缓存、私有现场数据、真实 controller IP、serial number、credential 或原始 operator token。
- generated log 和 authoritative evidence 必须清楚区分。

## 安全相关变更

任何涉及 `SafetyShield`、`HardwareExecutionGate`、真实机械臂验收级别、operator confirmation 或真实硬件脚本的变更，都必须同步更新：

- tests
- safety docs
- acceptance docs
- verifier behavior
- changelog

## 真实机械臂审查规则

真实机械臂代码默认必须 fail closed。在 production/hardware mode 下，不能静默回退到 Mock、MuJoCo、Isaac 或 simulation adapter。

不要新增自动连续运行多个硬件运动级别的脚本。硬件运动必须有显式现场配置和操作员批准。
