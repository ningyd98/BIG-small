# R126：PEP695 类型参数名称限定恢复

实际 Astra，2026-10-11。canonical冻结为R125 `implementation/stopped-up049`；额外stopped-ruff镜像只按ROOT报告登记，不再复制/删除。

## 原始失败

实际Ruff exit1仅两条UP049：sqlite_repository.py第57行19/23列的_P、_R；原help明确去除前导下划线。R125按原计划指定名称执行，暴露的是计划遗漏命名规则，不能改旧计划掩盖。冻结6source与当前12项hash一致，config未变；R125 formatter/delta exit0原raw一致，delta记录两源SQL常量相同及四源/旧scope不变均核实。R125三预算全耗尽；R113 last3(format_check/mypy/GREEN)仍各0/1。未运行产品或AST验证。

## 唯一修复

只在sqlite_repository.py的_job_writer及其nested guarded词法范围，把PEP695声明及绑定引用_P→P、_R→R；包括Callable、args/kwargs/return和cast(R,...)。保留ParamSpec/TypeVar种类、所有其他标识符、调用/控制/事务语义、SQL/字面量/注释/空白。不是全文件字符串替换，不触碰_PUBLICATION等名字。不Any化、不noqa、不改规则。类型参数可反射名称有意改变，不冒称其字符串名称未变。

## 最小验证额度

新增仅delta_proof一次→Ruff一次。**新formatter额度0**：只删标识符下划线、保留已格式化空白，原未用format_check负责格式验收，无须重复formatter。准确命令和新输出目录见plan.json。

窄delta用stdlib tokenize和AST：token仅允许指定词法绑定的NAME替换；新类型参数及其绑定引用alpha归一回旧名后，全AST/type_comments一致。不能删全部注解或任意rename来放行。检查无新P/R绑定冲突，全部SQL UTF8/字符串常量/注释/空白不变，其余五源含A20原hash不变，原R125和R113证明原字节不改。该检查不import/compile/执行产品。

新两项通过后必须停在原format_check/mypy/GREEN之前：ROOT已因独立早审缺口明确冻结这三项消费，额度仍各0/1。待完整审查及另一实际Astra计划再恢复，type-only通过不能解除此停点。不重跑RED/import/whole-proof/旧回归或R125检查。

## 执行/边界

ROOT核源/账本/计划并激活同replacement。作者保存单一改名diff和SHA，逐命令先记消费、保存原始stdout/stderr/UTC/cwd/env/exit。新失败先停并交实际Astra，不改旧失败/计划/证明。

独立早审只读原R113语义快照，其未知结论不属于本轮；不能声称已修复或据此扩范围。若后续有经ROOT确认的语义缺陷，另立实际Astra计划并协调暂停依赖验证。StageA仍为legacy UTC veto限定软件，最终GREEN/静态/独审未全通过前无验收；P6/native/actual/formal不晋升。

ROOT补充的早审初步问题为：confirmation_lost尚未证明真实RPC超时/迟到broker reply；restart尚未证明未结束旧attempt的实际终止。本轮未独立审定或修复这些语义/覆盖问题，不能当作后续B/C可延后义务，也不能称已通过。R126仍仅改名及两项窄验证。
