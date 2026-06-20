# Phase 13.1 真实 LLM-only 对照实验

本阶段在 `codex/phase13-real-llm-baseline` 分支实现真实 OpenAI-compatible 与
Ollama provider 的实验入口。当前分支依赖尚未合并的 `codex/thesis-report`：

- `base_dependency=codex/thesis-report`
- `main_not_merged=true`

## Provider 规则

- `fake` 只用于 pipeline smoke，不进入真实模型性能数据集。
- `openai-compatible` 只从 `BIGSMALL_LLM_*` 环境变量读取配置。
- OpenAI-compatible 推理请求必须显式传入 `--allow-paid-model-call`。
- `ollama` 只访问本机 loopback Ollama HTTP API，不自动下载模型。
- 任何 provider 未通过 health check 时输出 `BLOCKED_BY_ENV`，不回退到 fake。

## 命令

```bash
python scripts/check_llm_provider_environment.py --provider ollama
python scripts/check_llm_provider_environment.py --provider openai-compatible

python scripts/run_phase13_1_experiments.py --provider fake --profile smoke
python scripts/analyze_phase13_1.py
python scripts/build_phase13_1_figures.py
python scripts/verify_phase13_1.py
```

真实 OpenAI-compatible 调用必须显式授权：

```bash
python scripts/run_phase13_1_experiments.py \
  --provider openai-compatible \
  --profile smoke \
  --allow-paid-model-call
```

Ollama 必须已有本地模型：

```bash
python scripts/run_phase13_1_experiments.py \
  --provider ollama \
  --profile smoke \
  --model <installed-model-tag>
```

## 当前边界

当前环境未检测到可用 Ollama daemon/model，也未检测到 OpenAI-compatible endpoint、
API key 和 model 配置。因此当前状态应保持：

```text
PHASE13_1_IMPLEMENTATION_READY_WITH_MODEL_ENV_BLOCK
```

不得将 fake provider 结果写成真实大模型性能结论。

## 硬件安全

本阶段所有运行均为 simulation-only / planning-only：

- `real_controller_contacted=false`
- `hardware_motion_observed=false`
- `hardware_write_operations=[]`
- `highest_real_hardware_acceptance_level=NONE`
