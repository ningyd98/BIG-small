# Astra 限定恢复计划

- 轮次：round-docx-application-render-entrypoint-20261011
- 规划模型：gpt-6-astra
- 日期：2026-10-11
- 状态：仅生成计划，未实施、未渲染

## 问题与原始失败

Word 开题申请制作过程中把 renderer 错定位到 scripts 子目录；仅恢复工具调用入口。

- 原始 chunk：c7a4af；exit_code=2。
- 原始命令：`sed -n '1,140p' /home/ningyd/.codex/plugins/cache/openai-primary-runtime/documents/26.1009.11318/skills/documents/scripts/render_docx.py`
- 原始 stderr：`sed: can't read /home/ningyd/.codex/plugins/cache/openai-primary-runtime/documents/26.1009.11318/skills/documents/scripts/render_docx.py: No such file or directory`
- 上述原始证据由父代理提供，未重跑失败命令。
- 恢复检查 chunk 585441 exit_code=2：中断后计划目录尚未创建，属于同一恢复上下文。

## 输入及 SHA256

- `/home/ningyd/文档/ChatGPT/BIGsmall/AGENTS.md`
  SHA256 `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649`
- `/home/ningyd/.codex/plugins/cache/openai-primary-runtime/documents/26.1009.11318/skills/documents/SKILL.md`
  SHA256 `c9b9ba61ac15f20a600220bc10a380c7753992bbd3c323bfe33fae864adefc21`
- `/home/ningyd/.codex/plugins/cache/openai-primary-runtime/documents/26.1009.11318/skills/documents/render_docx.py`
  SHA256 `876d5993324e2faaaa96a68a4f7504642e9a07e6df265b385b2baa03b231369e`
- `/home/ningyd/.codex/plugins/cache/openai-primary-runtime/documents/26.1009.11318/skills/documents/scripts/render_and_diff.py`
  SHA256 `ea05e15461d14cf7361492f011364fbc18b257b99e3b96b61ca783bf65058f07`
- `/home/ningyd/.codex/plugins/cache/openai-primary-runtime/documents/26.1009.11318/skills/documents/scripts/section_audit.py`
  SHA256 `ad3d11349bd30bbf430734a2db06fd9c8fd373b63640cfa5335176e467e7c2bd`
- `/home/ningyd/.codex/plugins/cache/openai-primary-runtime/documents/26.1009.11318/skills/documents/scripts/style_lint.py`
  SHA256 `52d762eb3535e641c547fbca458a5b6f2a252c4216d55d840a109d9215ffe4f8`

## 根因

调用方误将根目录 renderer 按同包辅助脚本的位置推定为 scripts/render_docx.py。实际根目录文件存在；render_and_diff.py 默认入口也指向父级根目录 render_docx.py。未发现需要修改工具源码或产品代码的证据。

## 已只读核实的入口和 CLI

- renderer：`/home/ningyd/.codex/plugins/cache/openai-primary-runtime/documents/26.1009.11318/skills/documents/render_docx.py`；参数 `input_path [--output_dir DIR] [--width 1600] [--height 2000] [--dpi DPI] [--emit_pdf] [--verbose]`。
- render_and_diff：`/home/ningyd/.codex/plugins/cache/openai-primary-runtime/documents/26.1009.11318/skills/documents/scripts/render_and_diff.py`；参数 `a_docx b_docx --outdir DIR [--render_py PATH]`。
- section_audit：`/home/ningyd/.codex/plugins/cache/openai-primary-runtime/documents/26.1009.11318/skills/documents/scripts/section_audit.py`；参数 `docx`。
- style_lint：`/home/ningyd/.codex/plugins/cache/openai-primary-runtime/documents/26.1009.11318/skills/documents/scripts/style_lint.py`；参数 `input_docx [--json REPORT]`。

render_and_diff 默认使用技能根目录 renderer，且以当前 Python sys.executable 启动。参数定义由源码读取核实，未执行 --help 或渲染。

## 当前允许写入

- 仅写本计划目录的 plan.md 和 plan.json

## 建议采用的限定恢复

- 后续调用改为技能根目录 render_docx.py 的绝对路径。
- 允许使用同包 scripts/render_and_diff.py、section_audit.py、style_lint.py 审查用户已授权的文档及模板副本。
- 后续 Word 内容制作仍是已授权文档创作；本计划不构成产品研发修改。

## 排除范围

- 不改产品、模板原件、技能包或工具源码。
- 不新增替代渲染器，不安装依赖，不清理历史失败。
- 本轮不运行渲染、不生成或修改 DOCX、不提交或推送其他代理文件。

## 实际运行前置条件

- 实施前复核输入文件 SHA256、入口和 CLI 与本计划一致；如变化先判断计划适用性。
- 通过 load_workspace_dependencies 获取权威 bundled Python/Node/runtime；本计划未验证运行时可用性。
- 实际渲染前核实 bundled LibreOffice、Poppler、pdf2image；diff 需 lxml/Pillow，audit/lint 需 python-docx。
- 从可写工作目录运行，DOCX 输入及输出目录明确，模板原件保留并记录其 SHA256。
- 作者首次 create/edit 前按技能运行标记入口；本只读计划不触发该要求。

## 验证方法与证据保留

- 本轮已只读检查技能说明、renderer argparse 定义以及三个辅助脚本 CLI/default renderer；不等同运行通过。
- 后续使用权威运行时调用入口 --help 保存命令、退出码及日志，再对任务 DOCX 渲染；若发生新根因或计划外失败，暂停相关修复并提交下一轮 Astra 计划。
- 保存 section_audit/style_lint 输出；样式 lint 为提示而非自动否决模板固有格式。
- 实际渲染成功后打开全部 page-N.png 做视觉检查；需要比较时保留 render_and_diff 的 summary/text/visual diff。
- 将实施结果、原始失败和验证记录写入后续步骤报告及阶段总结，不覆盖本计划的原始失败。

## 验收边界

- 本计划验收仅为入口位置和静态 CLI 核实、受限恢复方案完整记录。
- 运行时可用、文档渲染成功、模板保真、内容正确和视觉质量需后续实际证据；本轮均未验收。
- 任何文档或软件验证都不能替代真实实验、正式研究验收或完整远端复现包。
