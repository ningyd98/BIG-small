# BIG-small 当前完成情况与接手说明

本文档记录截至当前分支 `codex/phase13-real-llm-baseline` 的实际进展、已验证证据、远端状态和后续接手步骤。本文档不是新的验收结论；未完成、未核验或被环境阻塞的内容均按阻塞状态记录。

## 1. 当前 Git 状态

- 工作目录：当前本地 worktree，文档中不记录本机绝对路径
- 当前分支：`codex/phase13-real-llm-baseline`
- 当前 HEAD：`695b688392fc42f7c964554d13d46f98db21c6cd`
- 当前分支远端：`origin/codex/phase13-real-llm-baseline`
- 远端分支 SHA：`695b688392fc42f7c964554d13d46f98db21c6cd`
- 本地与远端 Phase 13.1 分支 ahead/behind：`0/0`
- `origin/main` 当前基线：`5c43450eab1dd29b5a32786fb506f503b2729d4e`
- 当前分支相对 `origin/main`：ahead 12 / behind 0
- 工作区：最后一次检查为 clean

当前分支包含 `codex/thesis-report` 的论文工作和 Phase 13.1 工作。由于 PR #1 尚未确认合并，Phase 13.1 分支目前属于依赖分支，而不是从已合并 main 派生的最终干净分支。

## 2. PR #1 状态

- PR 地址：<https://github.com/ningyd98/BIG-small/pull/1>
- PR 标题：`Phase 12.3: harden evidence-traceable thesis build and merge gates`
- base：`main`
- head：`codex/thesis-report`
- head SHA：`13ac69834de901443c6b0782842216d562ff88a6`
- 当前状态：open，非 draft
- 本地新增修复已推送到远端 `codex/thesis-report`

PR #1 的最新 CI run：

- Run：<https://github.com/ningyd98/BIG-small/actions/runs/27870850376>
- 已观察到通过的步骤包括：
  - compile
  - ruff format
  - ruff check
  - mypy
  - core unit tests
  - phase8/phase9 unit tests
  - phase10 through thesis unit tests
  - documentation consistency
  - thesis and LLM-only merge gates
  - Phase 3、4、5、6、6.2、7、8、8.1、8.2、9 MuJoCo、9.1 blocked-environment guard
- 最后可观察状态：CI 进入 `Project CI profile` 长步骤，后续状态未能最终确认。

未合并原因：

- GitHub API 已触发未认证 rate limit。
- 本机 `gh auth status` 显示未登录。
- 因此无法继续可靠查询最终 CI 结论，也无法使用 GitHub API/CLI 执行 merge。
- 未执行 PR merge，未修改 `main`。

接手建议：

1. 登录 GitHub CLI：`gh auth login`
2. 查看 PR 状态：`gh pr view 1 --json state,isDraft,mergeStateStatus,headRefOid,statusCheckRollup`
3. 若所有 required checks 成功，再按 squash merge 合并。
4. 合并后同步本地 main：

```bash
# 同步 main 前先确认 PR 已经合并，避免把未验收分支混入主线。
git fetch origin
git checkout main
git pull --ff-only origin main
```

## 3. 论文工程完成情况

论文分支已实现 Phase 12.3 的主要工程目标：

- 论文正文源拆分到 `docs/thesis/manuscript/`
- `scripts/build_thesis.py` 负责装配、模板渲染和格式转换，不再作为唯一正文事实源
- 建立 35 条已核验参考文献，并全部被正文引用
- fake-provider 证据已从真实模型性能结论中隔离
- placeholder PNG 不进入正式正文
- DOCX 和 PDF 均已实际生成并通过本地检查

当前主要论文产物：

- Markdown：`artifacts/thesis_report/论文报告.md`
- LaTeX：`artifacts/thesis_report/论文报告.tex`
- DOCX：`artifacts/thesis_report/论文报告.docx`
- PDF：`artifacts/thesis_report/论文报告.pdf`

最后一次本地构建记录：

- DOCX：`BUILT_AND_VALIDATED`
- DOCX SHA-256：`16eb1d9e0dffb69992c4c5950376c12e1401b2d2735185d8c560eef08ee95dfe`
- PDF：`BUILT_AND_VALIDATED`
- PDF 页数：39
- PDF SHA-256：`ee98b10bca4b51872f219688f80b118a1dfe6b69fa49d575c9e749e1fcf16630`
- 正式图：28
- placeholder 正式正文引用数：0

相关状态文件：

- `artifacts/thesis_report/build_status.json`
- `thesis/generated/claim_evidence.json`
- `thesis/generated/thesis_metrics.json`
- `thesis/generated/reference_verification.json`
- `thesis/figures/figure_index.json`

## 4. Phase 13.1 实现情况

Phase 13.1 名称：

`真实 OpenAI-compatible / Ollama LLM-only 对照实验与论文证据回填`

当前已完成：

- 新增 LLM-only provider 抽象：
  - `fake`
  - `openai-compatible`
  - `ollama`
- OpenAI-compatible provider：
  - 只从环境变量读取 endpoint、API key 和 model
  - 默认不发起付费推理
  - 必须显式传入 `--allow-paid-model-call`
  - 不保存 API key、Authorization header 或 secret
- Ollama provider：
  - 只访问 loopback 本机 HTTP API
  - 检测 daemon、版本和已安装模型
  - 不自动下载模型
- fake provider：
  - 仅用于 pipeline smoke
  - 永远不能成为 `model_runtime_accepted=true`
  - 永远不能进入 authoritative model performance dataset
- 新增 Phase 13.1 CLI：
  - `scripts/check_llm_provider_environment.py`
  - `scripts/run_phase13_1_experiments.py`
  - `scripts/analyze_phase13_1.py`
  - `scripts/build_phase13_1_figures.py`
  - `scripts/verify_phase13_1.py`
  - `scripts/update_thesis_from_phase13_1.py`

当前 Phase 13.1 artifact：

- `artifacts/phase13_1/environment/ollama_environment.json`
- `artifacts/phase13_1/environment/openai_compatible_environment.json`
- `artifacts/phase13_1/runs/llm_only_runs.jsonl`
- `artifacts/phase13_1/responses/`
- `artifacts/phase13_1/aggregates/llm_only_summary.json`
- `artifacts/phase13_1/statistics/phase13_1_statistics.json`
- `artifacts/phase13_1/figures/figure_index.json`
- `artifacts/phase13_1/verification/phase13_1_summary.json`

当前 Phase 13.1 状态：

```text
PHASE13_1_IMPLEMENTATION_READY_WITH_MODEL_ENV_BLOCK
```

原因：

- Ollama daemon 不可达
- 未配置 Ollama model
- 未配置 OpenAI-compatible base URL
- 未配置 OpenAI-compatible API key
- 未配置 OpenAI-compatible model
- 未显式授权 paid model call

当前 fake pipeline 结果：

- run count：9
- fake row count：9
- accepted real model rows：0
- authoritative model performance rows：0
- model request count：6
- task success count：0
- latency：`NOT_AVAILABLE`
- valid contract rate：`NOT_AVAILABLE`
- unsafe proposed action count：0
- unsafe command execution count：0
- source artifact hash verified：true
- contains secret：false

## 5. 本地验证结果

以下命令已在当前分支实际运行并通过：

```bash
# 本地回归命令清单，作为接手人复核当前分支质量的入口。
python -m compileall src scripts tests
python -m ruff format --check .
python -m ruff check .
python -m mypy .
python -m pytest -q tests/test_llm_only_baseline.py tests/test_thesis_claims.py
python -m pytest -q
python scripts/check_docs.py
python scripts/check_model_control_secrets.py
python scripts/check_chinese_comments.py
python scripts/check_thesis_claims.py
python scripts/verify_phase13_1.py --root artifacts/phase13_1
python scripts/build_thesis_evidence.py
python scripts/build_thesis_tables.py
python scripts/build_thesis_figures.py
python scripts/verify_thesis_references.py
python scripts/build_thesis.py
python scripts/check_thesis_build.py
python scripts/check_thesis_figures.py
python scripts/verify_llm_only_baseline.py
```

关键输出：

- `python -m pytest -q`：`748 passed in 1154.28s`
- `python scripts/check_chinese_comments.py`：`files=779 english_only=0 missing=0`
- `python scripts/check_thesis_build.py`：DOCX/PDF validated，PDF 39 页
- `python scripts/check_thesis_figures.py`：formal=28，placeholder_excluded=17
- `python scripts/verify_phase13_1.py --root artifacts/phase13_1`：`PHASE13_1_IMPLEMENTATION_READY_WITH_MODEL_ENV_BLOCK`

未完成的远端验证：

- PR #1 GitHub CI 最终结论未确认。
- Phase 13.1 分支尚未创建 PR，因为本机 GitHub CLI 未登录。

## 6. 安全边界

当前必须继续保持：

```text
real_controller_contacted=false
hardware_motion_observed=false
hardware_write_operations=[]
highest_real_hardware_acceptance_level=NONE
full_profile_accepted=false
project_status=NOT_CLOSED
```

本轮没有执行：

- 真实机械臂连接
- 真实硬件写操作
- MoveIt execute
- ROS trajectory command
- Level 0--6 真实硬件验收
- 付费模型调用
- Ollama 模型下载
- Phase 12 full profile

## 7. 接手操作顺序建议

### 7.1 先完成 PR #1 合并

```bash
cd <local-worktree>
git fetch origin
git checkout codex/thesis-report
git status --short
gh auth login
gh pr view 1 --json state,isDraft,mergeStateStatus,headRefOid,statusCheckRollup
```

如果 PR #1 CI 全部通过且无冲突：

```bash
gh pr merge 1 --squash \
  --subject "feat: add evidence-traceable thesis pipeline and manuscript" \
  --body "Adds thesis manuscript source separation, verified bibliography, reproducible DOCX/PDF artifacts, fake-provider isolation, and thesis merge gates."
```

合并后：

```bash
git fetch origin
git checkout main
git pull --ff-only origin main
git status --short
```

### 7.2 再整理 Phase 13.1 分支

PR #1 合并后，建议将 Phase 13.1 重新基于最新 main 整理，避免 PR 中重复包含论文分支历史：

```bash
git checkout codex/phase13-real-llm-baseline
git rebase origin/main
```

如果 rebase 风险较高，也可以保留当前历史，但 PR 会包含 thesis-report 的提交，审阅成本更高。

### 7.3 创建 Phase 13.1 PR

```bash
git push -u origin codex/phase13-real-llm-baseline
gh pr create \
  --base main \
  --head codex/phase13-real-llm-baseline \
  --title "Phase 13.1: add real LLM-only baseline framework" \
  --body "Implements OpenAI-compatible and Ollama provider abstraction, paid-call gate, environment diagnostics, fake evidence isolation, Phase 13.1 artifacts, verifier, and documentation. Current real model runtime is blocked by environment."
```

当前远端分支已存在，可直接打开：

<https://github.com/ningyd98/BIG-small/pull/new/codex/phase13-real-llm-baseline>

## 8. 真实模型运行条件

只有满足以下条件，才能把真实模型结果写入论文性能结论：

- provider 不是 fake
- provider health check 成功
- 实际推理请求成功
- `model_runtime_accepted=true`
- `authoritative_for_model_performance=true`
- prompt hash 和 response hash 存在
- source artifact hash 可复算
- 没有 secret 泄漏
- `unsafe_command_execution_count=0`

OpenAI-compatible smoke 示例：

```bash
export BIGSMALL_LLM_PROVIDER=openai_compatible
export BIGSMALL_LLM_BASE_URL=<openai-compatible-base-url>
# 从安全的 shell 环境注入 API key；不要写入文件或提交到仓库。
export BIGSMALL_LLM_API_KEY
export BIGSMALL_LLM_MODEL=<model>

python scripts/run_phase13_1_experiments.py \
  --provider openai-compatible \
  --profile smoke \
  --allow-paid-model-call
python scripts/analyze_phase13_1.py
python scripts/build_phase13_1_figures.py
python scripts/verify_phase13_1.py
```

Ollama smoke 示例：

```bash
export BIGSMALL_OLLAMA_BASE_URL=http://127.0.0.1:11434
export BIGSMALL_OLLAMA_MODEL=<installed-model-tag>

python scripts/check_llm_provider_environment.py --provider ollama
python scripts/run_phase13_1_experiments.py \
  --provider ollama \
  --profile smoke \
  --model <installed-model-tag>
python scripts/analyze_phase13_1.py
python scripts/build_phase13_1_figures.py
python scripts/verify_phase13_1.py
```

不得自动下载模型；不得在没有 `--allow-paid-model-call` 时调用收费 OpenAI-compatible 推理。

## 9. 当前不能声明的内容

当前不能声明：

- PR #1 已合并
- main 已包含论文分支
- Phase 13.1 PR 已创建
- GitHub CI 最终全部通过
- 真实模型 smoke accepted
- 真实模型 validation accepted
- Ollama runtime accepted
- OpenAI-compatible runtime accepted
- Phase 12 full accepted
- 真实机械臂接入或运动完成
- 项目已封板

当前可以声明：

- 本地 Phase 13.1 框架已实现并推送到远端分支
- fake pipeline 仅作为 pipeline evidence，未进入真实模型性能结论
- 本地全量 pytest 通过
- 本地论文构建、claim、figure、reference 和 secret 检查通过
- 当前真实模型环境阻塞，状态为 `PHASE13_1_IMPLEMENTATION_READY_WITH_MODEL_ENV_BLOCK`
