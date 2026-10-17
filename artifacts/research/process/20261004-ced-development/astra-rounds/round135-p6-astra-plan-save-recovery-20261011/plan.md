# R135 — Astra 规划产物保存恢复

实际规划模型：gpt-6-astra；规划者 `/root/astra_status_plan`；2026-10-11。仅元数据，先保存本计划再恢复 R134 计划保存。ROOT 已明确调度，不新增产品授权。

## 原始问题与独立原因

1. 工具 `18dc99` 的只读分类展示器在 PASS case 的 `failure_attributes: null` 上调用 `.get`，exit 1。只发生 JSON 读取与部分展示。原命令余下 models/JUnit/index 读取未执行，无写入。此展示器废弃，不修复、不重跑；今后如需恢复另立 Astra 计划。
2. 工具 `90c536` 在尝试保存该命令文本时，外层 shell heredoc `PY` 与字符串内独立 `PY` 行冲突，Python 源被截断，报未终止 triple-quoted string；bash 随后报 unexpected EOF，exit 1。Python 在解析阶段失败，`mkdir` 与所有 write 均未执行。后续独立只读存在性检查实际确认 R134 与 R135 目录当时都不存在。R134 尚未落盘，不能称已冻结。

`90c536` 完整可得 combined 返回为：

```text
  File "<stdin>", line 4
    cmd=""".venv/bin/python - <<'PY'
        ^
SyntaxError: unterminated triple-quoted string literal (detected at line 15)
/bin/bash: -c: line 20: unexpected EOF while looking for matching `"'
```

工具返回不是预先分离捕获的 stdout/stderr。`18dc99` 完整返回在原会话工具引用中，本轮只保存可可靠获得的错误片段并明确缺口，不重构或冒充完整 raw。两问题均不是产品、pytest 或 acquisition 根因。

## 输入及既有保护

- 用户 AGENTS.md SHA256 `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649`。
- R127 plan.json SHA256 `4e355d66745f07e0db497177e91f25d52a2b065f564e2125a98ef8fcfe983377`，完整路径见 plan.json。
- 当前测试 SHA256 `4a29c6792d0f4226d76f77572dbe63ee4b8d8be96936571739d3dd2b5e321908`；R134 独立只读已核六源与 stopped-red 原件全同、52 protected pins 全匹配。此元数据恢复不写它们。
- 新失败原件是原会话工具输入/返回，原先没有落盘文件，不能虚构事前文件 SHA；结构化保存后另报文件 SHA。

## 精确恢复范围与次序

1. 通过结构化 `tools.apply_patch` 创建本 MD/JSON；不以 shell 执行包含原命令的字符串。
2. 本计划保存后，继续以结构化 apply_patch 新建 R135 `original-evidence/` 中两次失败的 exact-command、observed-output/error-excerpt、capture-note。`90c536` 保存完整实际 combined；`18dc99` 如无法取得完整返回，保存明确标注 excerpt 的文件及 tool 引用，不能称完整。
3. 同方法创建既定 R134 目录下 plan.md、plan.json，保存已完成的独立事实核查、pins、限定产品修复和待 ROOT 激活的预算。R134 方案保存不等于产品激活。
4. 仅允许 `.venv/bin/python` 标准库读字节/JSON/hash 核对上述元数据和 R134 原输入，不解析 AST、导入产品或执行验证；生成 R135 receipt/step-report（如需要）和 SHA 输出。ROOT 核对 R135 恢复及 R134 inputs 后另行激活原单作者。

## 前置、验证与验收边界

输出只能新建，不覆盖已存在文件；若目标意外存在或源漂移，停止并报告。原 R127 RED、ledger、52 protected 源及六产品/测试路径保持原样。禁止重跑两个失败命令、修改展示循环、产品/测试/Git/actual 执行；产品与验证新增额度均为 0，原预算不刷新。验收只是 R135/R134 真实规划文件和忠实失败记录可读取且 SHA 可核对。软件行为、Stage A、native 与正式研究验收均不晋升。
