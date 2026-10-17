# R215 — R214 writer-reference 行数统计补充

实际计划作者：gpt-6-astra（/root/astra_status_plan）。状态：等待 ROOT 与 R214 联合审阅；尚未实施恢复。

R214 交付前自查发现纯计划算术错误：七个 inclusive ranges 共 41+81+93+91+9+33+17=365 行，JSON planned_selected_lines 与 Markdown 同一表述误写 465。这不是命令、测试或产品运行失败，没有可填写的失败退出码。

本补充仅将 R214 plan.json 的 execution.new_metadata_read.planned_selected_lines 及 MD 对应统计解释从 465 更正为 365。三份 R214 原件保持原字节；本计划本身作为纠正依据。四文件路径、七个 ranges、所有 SHA、600 行/36000 UTF-8 bytes 上限、reader source/argv/cwd/env、前置和停止条件完全沿用 R214。

ROOT 必须先全文审阅 R214/R215，核对 plan.json 内列出的三份 R214 真实 pins，逐项按 end-start+1 核算并接受该补充。之后只可释放 R214 原有唯一 metadata read（当前 0/1 HELD）；R215 新执行/核验/产品/测试/静态/审查/Git 槽全部为 0，无预算重置。

该轮仅修正计划统计解释，不表示参考读取完成，不授予产品修改或 T2/T12、native、formal 验收。保存后 STOP，等待 ROOT 联合门控。

输入完整绝对路径、bytes、SHA256、七 ranges 和明确约束见同目录 plan.json；输入观察见 input-observation.json。

