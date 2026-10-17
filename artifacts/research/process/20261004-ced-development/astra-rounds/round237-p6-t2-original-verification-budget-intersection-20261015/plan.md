# R237 — 原始验证预算交集的生产修正

实际规划者：gpt-6-astra（/root/astra_status_plan）。仅冻结计划；ROOT审核后由原唯一gpt-6.1-sol作者实施。

R236三条完整异常链均为 budget duration cannot extend the original obligation：初始化→真实private dispatch→initial_history_state→_state。诊断child1/wrapper0、3FAIL，不是合法RED。原始失败及完整trace保持。

根因已由源确认：task与role verification两个hard预算来自同一原始D_app事件；task_window保留二者交集。但本地definition直接使用原role配置较长deadline，state又逐项继承definition并受严格原义务约束。不能只修改state，也不能放宽_state、改references或延长原始时间。

唯一产品文件是vision/worker_runtime.py。新增私有纯派生helper；首次_initialize_local在definition和source commitment之前派生有效VerificationBudget。设B为原task/verification hard预算与原配置floor-to-ns的最小值，全部计数不变、原references不变。保留原值若其Decimal与现有int转换都不越B；否则B/1e9转换为float，必要时仅一次nextafter朝零，再严格验证两种ns转换均不越界且为正。没有当前时间、remaining-time推算、任意epsilon或新origin。

初始化原_validate_role_sources(limits)与owner绑定继续校验完整原role配置。该验证函数新增明确local_definition关键字，后续check_active、_check_optional_sources、route三处按local模式比较同一确定性派生值；其余bundle/config/capabilities/inventory检查全部保留。legacy模式仍精确原policy相等。已有definition/history绝不回填、迁移或放宽；首次承诺后漂移必须拒绝。

范围：一个产品文件内五个既有函数的指定区域、一个新helper及必要imports；其余26源、211保护、strictcodec/P5/windows/broker、冻结全部测试/observer、event3及R235两处detach修正不变。新建两份R237作者脚本，旧脚本不改。

新增三个独立once槽：baseline120s（完整27物理快照+211+精确scope与历史适用性）、定向Ruff120s（E9/F63/F7/F82，仅runtime）、恢复RED3 600s+15s清理。ROOT每槽先reserve再发送literal，无prelaunch helper/探针/重试。精确argv/env/输出见plan.json。继续原样使用R235 import-only插件；合法RED不加载R236 trace插件。

RED必须三个原节点都真正达到episode、bootstrap、binding、双库COMPLETE，再在原 'R223 late local binding was not rejected' 断言失败。预算/启动/JSON/setup错误、预导入成功或wrapper1都不能替代。完整raw/JUnit/resources先保存后判定；实际资源分母不预设，未观察项保留null。历史18数据库/54sidecar以字节核验，不执行SQL。

输入观察230364B，SHA256 c8f5cbdc7961de4c0351265fe64b7aebb69c60e9e7ea5096707d05fcdd7a059d：24直接输入、27current、211protected、18DB/54sidecar与三trace全部identity检查match。旧世代以完整原物理/原invocation字节映射，不拿旧角色pin硬比授权后的活文件，不blanket skip。ROOT路径误读/capped显示独立保留，非产品根因。

ROOT负责计划/源码全文与pin门、三槽证据核对和自己的元数据。Sol独占产品与作者脚本。所有旧spent永久保留；R223余4、GREEN9、父GREEN7、原budget-not-refilled两节点、freshreview12与Git0不释放。即使获得合法RED，event3修复和后续continuation也须下一实际计划。T2/T12/native/formal均未通过。完成本轮证据结算即STOP。
