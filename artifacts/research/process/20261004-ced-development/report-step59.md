# 第59步：首次完整协议冻结、独审与唯一采集启动

## 元数据修正及协议冻结

按[Astra round60元数据计划](astra-rounds/round60-marker-freeze-count/plan.md)执行两项任务。原44/48计数AssertionError、独审缺python和错误摘要类型均保留。新检查用明确 .venv/bin/python，固定44复用源/4owned各自路径与SHA，不交集合及合并48映射全等；不修改产品源码，不重跑root临时closure或作者131。

root通过原CLI首次且仅一次 --prepare，exit0，PREPARED_SOFTWARE_ONLY。生产full-protocol首次创建，48源码及归档、34实际公共来源、29环境pins、65原full输入、exact0..4806/4807范围与状态合同一致，206受保护输入前后字节/SHA相同。生产header SHA为2dec1ca5ac4352a90056f8734d26e8fdef1795da212537f1897c8e1a77542100。见[冻结局部报告](astra-repair-execution/R01/marker-v4-full/implementation/production-freeze/round60/report.md)及[元数据](astra-repair-execution/R01/marker-v4-full/implementation/production-freeze/round60/report.json)。

## 冻结版本独审

[独审报告](astra-repair-execution/R01/marker-v4-full/implementation/independent-review/report.md)为 PASS_SCOPED_SOFTWARE_READY_FOR_ONE_FULL_ATTEMPT，无新产品finding或deferred minor。owned suite一次131通过（pytest9.66秒），四源Ruff/格式/内存编译通过；runner与reader各一个新进程仅source preflight/origins通过。23冻结文件及169项独审保护输入不变。独审actual/model/camera/decoder/旧压缩raw读取均0；两次工具失败保留。169与root206为不同保护集合，不能混为全仓原件复现。作者及独审131重合，不相加为262独立用例。

## 唯一完整采集进行中

root核对静止源/归档/header/env、执行前RAM/disk、无已有attempt及已知同队execute进程后，启动一次完整采集。工具session88431、监督PID2232265，唯一attempt-1；[prelaunch](astra-repair-execution/R01/marker-v4-full/actual/prelaunch.json)及[会话记录](astra-repair-execution/R01/marker-v4-full/actual/tool-session.json)保留精确argv与限制。GNU time分别记录进程wall/RSS；timeout为3600秒，TERM后最多60秒清理，无自动重试。

本报告时process RUNNING，已见新压缩帧文件前缀持续增长（本次文档快照计数由机器状态记录，仅文件存在计数，尚未验真保存成功）。不能预报4807采集成功、完整性、采样间隔或全帧可观测性。source冻结、独审和实际退出是不同门。实际终态及原件inventory后，root只允许一次新full严格读出；不再解码旧201/4807。失败、partial、UNKNOWN和额外数据保留，并先交下一Astra。

资源及研究界保持：capture3600秒/reader1800秒、各RSS4GiB、initial RAM6GiB/disk16GiB、output4GiB及1GiB失败reserve；0.005仅同episode SimulationS采样界。全帧即使OBSERVED也不证明帧间连续运动、角速度、未来误差界、原全部qpos反事实、九组/native/formal。旧full qpos缺失的比较限制仍保留。

## OC2条件实施与阶段边界

[Astra OC2三任务计划](astra-rounds/round60-operational-oc2/plan.md)已定稿，59输入无漂移。OC1独审软件门已满足；marker actual+readout终态仍待完成。root只授权Task1新文件/默认零副作用preflight/private registry和临时SQLite CPU测试；worker、teacher、backend及OC1等现有共享源码保持，Task2/3和真实来源采集未授权执行。本轮新文件实施仍进行中，不能算source-positive；edge模型后置，无模型/provider请求。

恢复wall-Rcap共享教师接口仍等待该窗口，未执行0002。Max当前checked scope无enabled兼容profile，九组、消费者闭合、G1与INITIAL/METHOD/FINAL未验收；主线T12/18、T13并行，硬件NOT_STARTED、S3/S4 LOCKED、formal_accepted=false。边缘型号后置。第58步及更早的RUNNING/0 actual为历史快照，以本次新增唯一actual状态为当前。

Git仍为本地be1c10cd596926d0184d7c13268ae3c3e22109d0，原383文件/20112981字节具体公开载荷等待用户批准；自动审批两次拒绝后无push执行，远端最后核验24ddf13193a1547edeab39165846ff716a0b5f3d。本步与活动新源码/原件未commit或push，没有借新提交扩大待批载荷。批量raw仍本地，派生报告不作完整远端复现包。
