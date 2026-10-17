# R125：P6 stage A Ruff 八诊断限定修复

实际 Astra，2026-10-11。仅两路径泛型表达和SQL字面量排版，不扩大技术范围。

## 原始失败与核查

从真实冻结Ruff stdout/stderr/result独立确认exit1：sqlite_repository.py:61 UP047；该文件1164/1536/1543/1692四E501；测试270/483/577三E501。原命令/cwd/env匹配R113，raw SHA/字节核验通过。六当前源码及六snapshot全匹配。

原RED20已消费；import_sort/formatter/scope_proof均exit0且raw一致。scope_proof仅PASS_SOURCE_SCOPE_ONLY，15writers/31SQLsites/20nodes，不是运行通过。原Ruff已消费并失败；format_check/mypy/GREEN均0/1。原件全部保留，不重写scope证明为新版本通过。

## 允许修复

仅 `simulation_runtime/sqlite_repository.py` 和原A20测试文件。_job_writer改为py312的 `[**_P, _R]` 函数类型参数，移除原两TypeVar/ParamSpec赋值及其无用import；Callable、nested guarded签名、wraps、cast、_writer_call逻辑保持。不得Any化或禁用UP规则。

七处SQL长行仅改Python字面量表示，最终SQL常量UTF8字节必须完全相同，包括空格、换行、缩进。优先括号内相邻literal；禁止改SQL换行、strip/dedent、添加noqa。1692属于整段executescript三引号常量，可拆成相邻字面量表示，但整段decoded常量仍必须相同；其余动态join/拼接/参数AST结构不变。

## 新验证额度与原预算

新增仅三项，每项一次，准确argv/env/证据目录见plan.json：

1. R125 formatter：仅两修复文件。
2. R125 delta proof：只用stdlib AST/tokenize核限定差异、SQL字节和其他四源不变；不import/compile/执行产品。
3. R125 Ruff：沿原六路径check一次，无fix。

随后继承原format_check→mypy→GREEN三项各一次；原RED/import-sort/formatter/whole-scope-proof/Ruff消费不重置、不重跑、不替换旧输出。任一新失败停点交下一Astra，不擅自重复。

## 精确delta规则

测试AST/type_comments须完全一致（仅忽略位置），所有SQL常量不变。sqlite AST仅允许规范化上述两赋值删除、两个typing alias删除、_job_writer新增正确ParamSpec/TypeVar type_params；规范化后全AST/type_comments一致。不能笼统删注解掩盖差异。字符串/bytes常量序列仅排除已移除两TypeVar构造名字，其余完全一致；逐SQL保存repr/UTF8 SHA，executescript整个常量亦如此。保留注释/type-ignore锚点、20nodes/参数、writer/issuer/guard/CAS及真实负例。旧scope证明保持原hash，以新窄delta证据衔接适用性，不能改其15/31/20结论冒充运行验收。

## 实施和验收边界

ROOT先核原件/source pins并激活，同replacement手改两源，保存格式前字节与change report后按三新增→三继承执行。R125新目录存完整原始stdout/stderr、UTC时点、argv/cwd/env/exit和ledger；原失败/snapshot不改。作者最终冻结及不同作者审查仍必需。规划者未做AST/static/产品运行或Git。

本轮只修静态失败，不证明软件/actual/formal通过。Stage A仍带legacy UTC veto；B/C/D、native及正式研究不晋升。任何新的类型或运行根因另立实际Astra计划。输入SHA/bytes和完整八诊断见plan.json。
