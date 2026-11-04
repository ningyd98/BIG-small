# R432 局部类型修正

按实际 Astra 计划复核17个输入后，只重命名指定子树的5个 Name（1 Store、4 Load）。逆向归一化后整个模块 AST 与 R431 冻结原件完全相等，子树外10个 pair 不变，其余3文件 SHA 不变。Ruff、格式及 mypy 各一次60秒上限检查全部返回0。未重复91项运行；既有运行证据属于 R431。独立审查的 R431-F4 另交 R433，未视为本轮闭合。

COMMAND 原始结果包含 physics_state 和 command_records；本轮未运行真实 COMMAND。真实完整 H producer、守卫、独立校准及正式 native 仍未验收。
