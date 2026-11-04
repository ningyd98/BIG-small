# R427 原件驱动的动作返回终点诊断

基线 439bd9260ae83c6ad1ced8c9dde591be8d68e71b；实际 Astra 计划后 inline 实施。新增 native_completion_originals.py 与配套测试，没有修改已有产品代码。1315 项基线文件（408 个源码文件）哈希保持不变。

读取真实清单及原件字节、校验 RawV3 记录图，对全部已分配图像执行 RGB-D 标记解码和完整刚体几何重建，再复算 owner 绑定与实际执行参数。MOVE_ABOVE/APPROACH 输出实际返回时的 G/U/L/M/C，保留原始步长 1/240 秒、capture/dispatch/return 步号和 observed_steps。失败、缺失、篡改、歧义、未支持技能均保留分配记录及原因。

独立软件夹具验证 MOVE_ABOVE 的 G=3mm、U=3mm、L=3mm、M=0、C=6mm；真值漂移4mm时命令不变而 C=10mm。APPROACH 使用接触参考，不套用 MOVE_ABOVE 的抬高量。真实解码/几何/绑定路径均执行，没有替换为假返回值。

验证原始证据：RED 为唯一预期缺模块断言失败（2.004秒）；GREEN 59 项 setup/call/teardown 均通过（35新增、24已有），监督器39.536秒，pytest38.44秒。无跳过、输入漂移、超时或遗留子进程，R235前置条件通过。JUnit未请求生成，明确 NOT_PRODUCED；逐阶段 pytest-events.jsonl、stdout、退出记录是执行证据。

静态检查首次发现测试中未使用的 Path 导入，原始 F401 保留。R428 实际 Astra 计划仅删除该导入；文本差异与 AST 等价校验、Ruff和格式检查通过，产品源码SHA不变，mypy已通过。按R428计划不重复执行无行为变化的59项测试。

输出始终 SOFTWARE_ONLY、native_authority=UNAVAILABLE、qualification=UNKNOWN；qualified_completion_metric 固定为 None。实际返回时刻不是完整 nominal H，本轮结果不送入联合校准、不填旧 e/v、不授予在线执行权限。真实采集与正式研究验收均 NOT_STARTED。

下一主线：同次 producer/OC1 事件与原件绑定、完整S时段及默认步长的精确支持、唯一控制器与保持证据，随后补齐其余技能特别是 RELEASE 的实际 PLACE/刚体变换依据，再进入预注册独立组采集。
