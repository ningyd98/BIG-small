# R328：observer 独立审阅 manifest 定位接续

> 实际模型 gpt-6-astra；仅规划，沿用实际独立 fresh seat。

## 原始问题与输入

R319/reviews/fresh-observer-review/batch-01-receipt.json 完整保留 5fabee exit1 StopIteration；第1/4次 SPENT，无展示、无新增覆盖。根因是两个 locator 都对整个 source 字典转字符串后 endswith；真实结构是 files[].source.path。before 有四项（两 tests、R315/R296 runner），after 只有两 tests。map 的 fixture 是 old/new_observe_base64，micro 是 literal_changes[before_base64/after_base64/occurrences]。本轮输入 SHA 全列于 input-observation.json。

## 不新增额度：原剩余三读

原 R319.fresh_observer_review 总4，已用1保持；剩余3按 batch02 source、batch03 runtime、batch04 all15 overlay。每次≤600源码行、≤39,000总UTF8硬上限，目标≤28,000；每批先计完整展示（包括pins/header/metadata），失败/拒绝也消耗，不自动重试。不得借用其他旧桶或把本 Astra 规划核对当 fresh 已读。

### batch02：修正原 source reader

以失败 receipt 的 invocation.args.cmd 为模板：

1. 将两处（count2）`str(x['source']).endswith(suffix)` 精确替换为 `Path(x['source']['path']) == ROOT/suffix`，匹配两个真实绝对 tests 路径。保留 before/after base64、完整 literal reconstruction、source/live SHA 与所有发生次数/相等结果，不跳过未找到条目。
2. 原四次 lease/worker source 调用移到 batch04，见 plan.json 的精确列表；不是删除覆盖。其余完整116行diff、113行新真实测试、96行changed-hunk context全部保留，标题仅标实际batch02。
3. 保留原 release/plan pins 断言及28k展示护栏，可增加本R328 plan pin的小型来源记录，不输出完整计划或release。

已只读测量：仅修locator为446行33,303B，仍会超过原28k目标；移走上述121行后325行25,289B，完整重建均相等。测量仅构造字符串，不展示独立review payload，不计fresh覆盖。独立seat仍必须实际执行与审读。

### batch03：三次原运行证据

仅三固定目录 session_init_red / session_init_green / observer_selective_green；实际实际回执结构为 invocation、initial、polls、completion、actual_tool_return、attempts、retries。initial/completion的kind可缺省；中间polls与独立completion分别核对。展示真实argv关联、child/wrapper、JUnit、source-before/after与gate匹配、raw/index/DB/archive/sidecars hash的有限逐文件结果及所有不匹配。

RED/GREEN使用 result.cases、resource_summary、resource_counts、prerequisite；逐个读取 cases.files[0].pin/data 与 resource_summary.records[0].pin/data，核对1个真实poll、284资源计数、session/worker/threads链接、constructor/error变化、代理与异常对象、原hooks/method恢复、2DB清理。selective使用 micro_cases（files为空），无resource_summary、0DB/0poll，不能套真实运行分支。展示原case checks、关键callback/session实际字段和counter，不能以ROOT accepted布尔代替独立语义检查。文件hash表可按唯一文件去重、路径相对化，不能隐去错误行；不展开全284资源数组或完整source pins大表。

### batch04：全部15条历史overlay及原控制流

读取 historical-session-initialization-overlay.json 的原 original_facts、historical_raw_totals、rows[15] 与所有声明边界；逐行核验 resource_pin、source_before/source_after、source_generation 的原始bytes/SHA。每个唯一raw只读一次，按resource_id/worker_resource_id/poll_id查回实际session、worker、normal_poll、owned_threads，与overlay值比较。

展示全部15行：command/原pin引用/pid/nodeid、session原initialized=false及原error/cleanup/broker_alive、worker关联和session/heartbeat观察、normal_poll returned_normally/return_value/exception/sequence、两owned_threads的session/worker链接与alive_after_join。明确均是原保存数据；原显式constructor-return trace不存在。去重pins但不省略任何行或矛盾。

补读移来的 operational_lease.py416–460、913–948（实际文件到947）；worker.py146–180、235–240，共121行，以真实工厂返回后才安装session的控制流评估15个推断。5708 attempts/5693 recorded initialized/5708 cleanup原事实不改；15推断及5708解释总数只能作为新overlay结论，不能冒充历史return trace或修复旧35DB/90sidecar缺口。允许基于实际读证据拒绝/部分接受推断。

## 实际前置与记录

ROOT核对本轮输入仍适用，三runtime确已结算；source/HEAD冻结。独立seat读取R328限定计划，沿原release（不重写）记录剩余3。保存原R319 review目录batch02/03/04完整args/actual、精确范围、真实字节/行数、spent/remaining，及最终双Spec/Quality verdict。未覆盖或三读不足即列明缺口、保持Incomplete，无自动增额或通过。

本轮无产品/测试/SQL/运行/源修改权限；规划器未执行任何产品或测试。原失败永久保留。只修locator和同范围展示分配，独立review判断不由计划预设。
