# R410：改动源码的静态质量与交付准备

实际 gpt-6-astra；UTC 2026-11-03T08:56:05.881058+00:00。已按授权只读运行缓存 Ruff：四文件55条；HEAD原件同配置对照确认40条既有（sqlite27、operational_windows13），新增15条（sqlite新helper一条E501、native新测试13条、legacy新测试I001一条）。原JSON/命令/退出码/HEAD字节与分类冻结，无source修改。

源修改必须等待 R409以及R408两套浏览器终态并释放源冻结，保存终态适用回执。当前不格式化。允许只拆分sqlite新helper的列表推导长行，以及两新测试中已列E501/I001；不改ops，不清理历史40，不改ruff配置或noqa。

sqlite与native测试全模块AST须精确相等；legacy仅允许起始三个stdlib import排序的严格归一化，其余AST/所有函数/断言/常量相等。保存新SHA与显式before/after桥接，旧c962/1e74/7d及所有运行时点原件保持，不称旧全pinset等于新文件。

修后一次同四文件Ruff≤30s，预期仍exit1且只有完全对应的40历史项、零新增，两新测试无finding；另一次只读diff --check。不能宣称全Ruff通过。无新行为测试/浏览器复跑/产品import/SQL/Git写额度。AST差异或新非预期lint须下一Astra，不现场扩修。

浏览器新失败依旧独立暂停，格式化不能豁免。后续具体delivery计划刷新当前候选与provenance、一次fresh whole-change独审，再精选提交推送；本轮不提前Git，不回写旧证据/readyfalse，不碰dirtygitlinks。
