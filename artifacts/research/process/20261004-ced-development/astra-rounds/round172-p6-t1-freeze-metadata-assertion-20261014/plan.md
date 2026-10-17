# R172：T1 候选冻结路径坐标修复计划

实际规划者：gpt-6-astra（/root/astra_status_plan），2026-10-14。仅恢复候选元数据准备，等待 ROOT 输入及完整脚本文本门。

## 已确认问题与原始证据

原工具 2463bc 实际 exit 1，第 49 行 assert current == old 失败。完整 literal source、准确命令和实际 combined 返回保存在 original-failure.json（52744B，SHA256 fe7d1b68737b7af7354ba3816ea09e8e4d08ae399c24d4fe2bc6502b79d55dce）。独立 stdout/stderr 和 Python 局部变量不可得，不补造。

独立核查确认 R158 task 的九项 owned_paths 全为相对路径，而 scope 的二十四项及 before 记录使用绝对路径。原直接 membership 将合法 T1 修改当成后续阶段文件。按固定仓库根统一坐标后，九项实际变化全部属于 T1，十五项后续文件逐字节不变。二十三 before 校验、211 protected、A80556、七个 T1 节点对应 body/decorator tail、R170 当前测试 after pin 均匹配。完整观察和全部 SHA 收于 input-observation.json 与 plan.json。

原源文本首次写入在第 210 行，此前第 49 行已退出，因而该调用没有执行报告写入。当前独立清点：三个已有 JSON 报告仍存在，其他十个目标不存在。不能将旧报告当本次部分输出；新操作更新前必须保存其完整原字节。

## 最小修复及执行顺序

唯一作者 /root/p6_stage_b_sol 只准备新的 freeze-candidate.py 元数据源，基于已保存原 literal source。ROOT 完整读脚本、核全部 43 inputs 后，新增一次 .venv/bin/python 标准库动作（120 秒上限）；原失败冻结动作 1/0 保留，不重跑原脚本。

所有 scope/task/new/before 路径统一为固定 ROOT 下的准确绝对路径；相对路径仅拼接固定 ROOT。拒绝越界、..、重复 canonical 项和符号链接，不改原计划、不猜 basename。保留原 raw 路径用于审计。所有 ownership 判断、原件索引和 absent-new 判断使用同一坐标。原 current==old 断言必须保留且对十五 later-owned 真正成立。

所有输入、23 before、24 当前源、211 protected、七节点/A 前缀、真实 golden、runner 和两角色账本检查完成后才写输出。账本实际 role 状态不同：作者 HELD，ROOT HELD_PENDING_ROOT_GATE；各自按真实字段检查，不强求字符串相同。baseline/t1_red 已用各 1，其余十三项 0/1。

沿原六份文档的 JSON/MD 对与 limited.diff 合同生成候选报告。先独占保存 before-reports.json，保留三个旧 JSON 的完整字节/base64/SHA，再允许替换这三份准确目标；另外十个目标独占创建。报告内也保留 previous_current_metadata_preserved。写前复核源和旧报告未变，写后在同一次动作读回全部输出，并确认源、保护项、runner、golden、账本没有变化。完整实际返回及步骤报告留本轮，只输出短摘要。

## 不变边界与停止条件

不改源码、测试、runner、golden、旧 raw/计划或 STATE/PHASE；不执行 AST、产品导入、compile、collect、pytest、静态、SQL、probe、Git。原 R158 为 2 spent / 13 HELD，T1 GREEN 0/1；R170 metadata 1/0，R169 始终 HELD_SUPERSEDED 0。原 RED 七 FAIL 与 R166 独立控制一 PASS 只构成两次运行的组合前置，不能改写为单次七节点合格 RED。

所有强断言保留，任何新失败、漂移、竞争写入或范围扩大均保留并停止。成功只表示候选准备恢复，仍需 ROOT 新源码/fixture/runner 门、原未用 GREEN 以及独立审查；不表示 T1、B9、T12、native、actual 或 formal 验收。
