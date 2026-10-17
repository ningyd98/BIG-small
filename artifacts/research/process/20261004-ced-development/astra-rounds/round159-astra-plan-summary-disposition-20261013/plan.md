# R159：可选计划摘要展示器处置计划

> 实际规划者：gpt-6-astra（`/root/astra_status_plan`）。冻结后等待 ROOT 激活。

问题仅发生在尚未落盘的 R158 计划摘要展示：对非数组 `commands` 调用 `.map`，得到真实 wrapper `TypeError`。没有调用 shell、文件写入、产品、测试或 Git；没有可声称的 subprocess exit 或独立 stdout/stderr。准确提交代码和实际可得返回保存在 `original-failure.json`。

放弃该可选展示器，零重试。ROOT 核对本计划和三项真实输入 pin 后，允许 Astra 用类型检查及有界 JSON 文本检查自己的计划对象，将原 R158 计划通过结构化 apply_patch 保存到既定 `plan.md` 和 `plan.json`，再进行一次标准库 metadata 字节/hash/JSON 核对。不得执行产品 AST/import/compile/测试/静态/Git，不增加或重置产品预算。

恢复前 R158 两计划文件必须仍不存在，三项输入必须仍匹配。原始失败和已有 R158 输入清单/调用点清单保持。R159 只允许自身 input-check/root-activation/step-report 元数据；具体绝对路径、SHA 和限定恢复步骤见 plan.json。R158 的15条拟议命令仍待 ROOT 后续独立激活，本计划不授予 B9 实施或验收。

新失败或输入漂移立即暂停相关恢复。本轮完成只表示计划元数据已安全保存，不表示 B9 软件、真实、native、formal 或 Git 交付完成。
