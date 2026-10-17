# R239：writer release 屏障进度旁观诊断计划

实际作者：gpt-6-astra（/root/astra_status_plan）。仅计划；ROOT 门控前不实施、不运行。

R237/R238 的预算修复已通过基线与窄 Ruff，但唯一恢复 RED 为3FAIL。三个场景均已获得真实 bootstrap binding 和两库 COMPLETE；writer 先因原 `release.wait(10)` 超时而抛 AssertionError，随后才记录 during_episode 的完整读取/快照阶段。最终确实到达原测试255/265行失败断言，但没有证明正向 legacy 竞争写入，因此不是合法 RED。三槽均已花费，不重置。

已审冻结 fixture 89–225、249–268行及 observer sampling/profile、snapshot 函数：writer 等待在 private bootstrap 入口之后开始，release 在 during_episode 完整读回和快照之后。现有顺序没有时间戳，不能区分 bootstrap、解码/快照、profile 开销或锁等待。没有依据延长10秒、改TTL、改observer或回退预算生产修复。

本轮唯一新增权限是一条600秒、清理总额15秒的诊断槽。唯一Sol作者仅准备两个新源：`implementation/r239_barrier_observer.py` 和 `implementation/run-command.py`。保留原3个精确节点与R235原字节导入插件，不修改任何产品、原测试、旧runner、屏障或原有hook。没有额外baseline、Ruff、SQL、探针、Git或审查命令。

每例 setup 前启动一个真实旁观 sampler，读取实际主线程/原writer有限栈与明确列出的case primitive、既存Event原生布尔标志，不调用产品或屏障方法。它不设置/清空trace/profile，不包装产品函数；记录实际继承hook，finally停止并真实join。新增线程与自身Event单独记录构造、启动、native身份、终止和失败，不能藏在旧738分母之外或伪称被旧observer完整计数。

采样间隔0.25秒，整次最多2401 tick，每例最多1024记录/8MiB，两线程各最多12栈帧；及时释放frame引用。host perf仅作诊断、不进入OC1。非原子采样可能遗漏中间状态，观察本身也会影响调度；超限、未知或缺失必须原样报告，不重试。目标是给出writer等待窗口内主线程实际位置及barrier状态，证据不足仍记unknown。

同一runner在启动前后保全完整current27、211保护、321历史的精确原代映射、旧18DB/54sidecar及新R237六DB/18sidecar；只读字节/哈希，不执行SQL。R240已经实际329项核验并获ROOT接受，输入记录与历史physical_original对象分代处理。原始失败、R237结算和冻结数据全部保持。

ROOT先全文审两个新源、输入、literal argv/finite env、资源清理和输出边界，再预留唯一槽后发送。实际返回先store再显示，独立raw完整保存，stdout只输出≤6000字节摘要。child退出0或1均只作诊断，wrapper0仅代表诊断证据完整，永远不能替代合法RED/GREEN。

ROOT随后仅做元数据完整性结算。可完整before归档/CAS后追加planning.R239和PHASE事实，不改其他阶段或验收。原R223四槽、GREEN9、父GREEN7、fresh12及Git0继续保持；event3不得提前修。获取证据后STOP，下一真实Astra计划才决定是否修复或调整夹具。

完整23直接输入SHA、当前/历史来源、精确三个node和argv/env、唯一槽、输出路径与验收边界见同目录plan.json。input-observation.json保留实际源读取和原始失败分析，未生成任何新运行结论。
