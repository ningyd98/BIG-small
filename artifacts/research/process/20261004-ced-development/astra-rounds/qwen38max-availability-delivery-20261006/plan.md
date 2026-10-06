# Qwen3.8-max 交付检查 Implementation Plan

> gpt-6-astra；planned_not_executed。执行者沿用 superpowers:executing-plans。

**Goal:** 保留原始证据字节并完成精确路径提交验证。

**Architecture / Tech Stack:** Git 默认文本检查加原始字节 SHA256/CRLF 独立校验；python3 或 .venv/bin/python。

**Spec:** AGENTS.md 与本任务前两轮计划。

## 问题与原始失败

git diff --cached --check exit 2 将必须冻结的原始 TTY traceback 的 14 个 CRLF 行标为 trailing whitespace。

通用源文本空白规则与原始实验字节保全要求冲突；证据内容未损坏，不得转换 CRLF 或修改规则配置来掩盖失败。

原始命令与输出见 `artifacts/research/process/20261006-qwen38max-availability/delivery-whitespace/failure.json`、同目录 `git-diff-check.stdout`/`.stderr`；默认检查 exit 2 永久保留。

## 输入 SHA256（七项已复核，另附清单自身）

| 文件 | SHA256 |
| --- | --- |
| `artifacts/research/process/20261006-qwen38max-availability/attempt-1-tty-failure/failure.txt` | `7e4fc706cb06f413b73aff92a4595a6e0ff9674a83d220c1865d2542b9ff1e2c` |
| `artifacts/research/process/20261006-qwen38max-availability/output-sha256.json` | `2fca77d42f9d08021ceeac24937f6f547f4f0a332a5d106fb4a7e5d9d7805c16` |
| `artifacts/research/process/20261006-qwen38max-availability/final-review.json` | `ad8680940c7928dd2e3143dcca01e5941c2e78ccc1b654ad5eee334809596f77` |
| `artifacts/research/process/20261006-qwen38max-availability/delivery-whitespace/failure.json` | `1c0f554d7c4bb61c1981f78570038934779018ccb0c614ac775f86d4e8677b32` |
| `artifacts/research/process/20261006-qwen38max-availability/delivery-whitespace/git-diff-check.stdout` | `642dbf85b28869d0b2021f1a6818241cca02e3d0c8368166d5120959c16a8115` |
| `artifacts/research/process/20261006-qwen38max-availability/delivery-whitespace/git-diff-check.stderr` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `AGENTS.md` | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` |
| `artifacts/research/process/20261006-qwen38max-availability/delivery-whitespace/input-sha256.json` | `e97023433d4a6ec271bb32879e6cb6f8df90fe475c4cc127e2fb7685354b8cb3` |

## 范围与前置

只调整本任务提交验证方法并新增步骤/交付报告和派生清单；零源代码、配置或原始字节修改，零 API 调用。规划者仅新增本轮 plan.md 与 plan.json。

- 执行前复核以上七项输入及 manifest 哈希；固定 .venv/bin/python 或 python3，使用已有 require_escalated 自动审批通道。
- 当前研发分支 research/20261004-continuation；只操作 availability 目录及本任务三个 Astra 计划目录，不混入其他暂存/脏改动。
- 原有清单和失败证据冻结。本轮派生完整清单另存 delivery-whitespace/output-sha256-delivery.json，避免使旧清单输入哈希失效。

## 精确原件例外

```json
{
  "artifacts/research/process/20261006-qwen38max-availability/attempt-1-tty-failure/failure.txt": {
    "sha256": "7e4fc706cb06f413b73aff92a4595a6e0ff9674a83d220c1865d2542b9ff1e2c",
    "bytes": 853,
    "crlf_count": 14
  },
  "artifacts/research/process/20261006-qwen38max-availability/delivery-whitespace/git-diff-check.stdout": {
    "sha256": "642dbf85b28869d0b2021f1a6818241cca02e3d0c8368166d5120959c16a8115",
    "bytes": 2510,
    "crlf_count": 14
  }
}
```

## 执行与验证

- [ ] 保留原默认检查失败的 exit 2、stdout、stderr、failure.json，不清理或改写，不将默认检查标为通过。
- [ ] 逐文件暂存本任务允许路径；读取完整索引路径清单，拒绝范围外文件及凭据模式命中，不打印秘密值。
- [ ] 对精确两份原始证据分别核对工作区和索引 blob 的 SHA256、字节长度与 CRLF 计数，必须等于 raw_evidence_exact_exclusions；stderr 为空仍参与常规检查。不得过滤、转换或规范化原件。
- [ ] 枚举本任务所有暂存文件，精确排除上述两个路径后以 git diff --cached --check -- <逐个精确路径> 使用默认规则验证全部剩余文件，要求 exit 0。不可使用目录级排除，不修改 .gitconfig/.gitattributes。
- [ ] 独占创建 delivery-whitespace/verification.json、steps.md 与 output-sha256-delivery.json，列出默认检查失败、两原件独立通过及剩余文件检查通过；将阶段结论写入新步骤报告。清单不包含自身，说明生成时点；旧报告与输入清单保留。新增报告/计划逐文件暂存后对最终索引重复精确路径检查及两原件哈希验证。
- [ ] 提交仅本任务三个计划目录与 availability 目录无密钥文件，普通 push 当前研发分支，不 force；读取 local HEAD、上游和 git ls-remote 同分支 SHA，三者一致方可声明交付完成。新 push 失败保留证据，停止修复交下一轮 Astra。

## 验收边界

- **development**：调整后的分组检查全部通过且默认检查失败被如实保留；原始证据工作区/索引哈希及 CRLF 一致。
- **real_run**：沿用已完成的单次文本推理证据，本轮不重跑 API；本轮交付检查不能替代推理证据。
- **formal**：未新增视觉、云边端闭环、硬件、可靠性或正式研究验收。
- **delivery**：提交范围正确、无密钥，普通推送后 local/upstream/remote 三方 SHA 一致。

任何新根因、扩大范围或计划外失败需下一轮 Astra；不得通过清理证据取得通过。
