# R390 浏览器队列与关键目标可达性诊断计划

实际模型 gpt-6-astra；代理 /root/astra_r389_revalidate；2026-11-02T11:12:20.313888+00:00。

结论：新增下游完成性问题成立，具体性能/死锁/服务根因尚未证实。本轮只准封存证据和有界离线诊断，不准源修、增加等待、改变并发或重跑浏览器。R377终态、清理、源完整性与最终独审移交后，允许R378→R379独立继续；不能据此宣称browser通过。

## 原始证据与分类

受限环境首次socket拒绝是launched=false的前行为环境拒绝，原件保留。获工具批准的default替代运行保持原CLI/1worker/0retry及同1200秒时钟，FINISHED exit1，454.781848秒；research首次行为FINISHED exit0，22.440261秒。两组source_drift/errors/remaining_live空、reaped=true；8000/5173/8123/5199已释放。清理中reaped子进程含终止状态，不能把signals空字段解释为所有子进程均自然退出。

Default JUnit共40：20PASS、2failure、17error、1原skip。console37=20PASS/16error/1skip；RGBD3=1error/2failure。E2E07/08属于XML error。research3PASS，原scopeSOFTWARE_ONLY、groups600/assigned4200/blocked4200、formal_accepted=false、actual_research_status=NOT_RUN、model_requests=physical_actions=0保持。

Console仅增加35字节input_mode字段，内存去掉后精确还原原plan SHA。稳定trace显示LEGACY_PIPELINE、实际batch POST202。E2E07先有1success，20秒末1success/1running/1queued；E2E08为3queued。后续多个run始终QUEUED/attempt0/started_at=null。queue_position实现取queued_count，不能称为精确排名。

RGBD1在45秒总case上限内未等到SUCCEEDED，内层等待60000毫秒；RGBD2最后capture状态QUEUED，尚未创建后续visualplanning；RGBD3published_groups=0，尚未发cancel。不能把这些写成已执行目标失败或已证实HTTP超时。采集/规划/取消目标分别登记，暂不与MOCK队列强并根因。

## 根因边界

源码确认dispatcher单线程同步轮询每backend一个固定worker，MOCK走实际ExperimentRunner/RuntimeExperimentHarness。运行deadline在领取后开始，_run前后检查，不能当包括排队的端到端SLA。该路径支持队列阻塞假设，但不能定位内部阻塞点、断言死锁或直接证明timeout应加大。45秒外层/60秒内层上限差异是事实，也尚非完整因果结论。

## 允许动作

仅新R390证据/分析/报告；终态后按hash冻结closed trace、JUnit、日志、源码和调用回执。一次stdlib离线脚本（/usr/bin/python3 -I），最多120秒分析+15秒清理、300秒总墙钟，0重试，查询每条最多10000行；不分配任何行为测试次数。

从trace建立首批run/job/attempt时间线并映射原18case实际结果。可在确认原运行关闭后，原DB及存在的WAL/SHM按字节复制到新私有forensic-copy，前后核原hash；只对副本mode=ro/query_only查询，禁止打开原DB、checkpoint/vacuum/修复，禁止immutable忽略有效WAL。副本不一致则停止DB分支、保留限制。研究实际线程栈未知时只能写UNKNOWN；虚拟时钟和真实UTC不能混算。

独立分析3个RGBDcase捕获/发布目标及后续请求是否到达。任何新行为探针、产品修复、性能优化或等待策略变更都交下一实际Astra计划，本轮不自动实施。禁止产品导入、网络、signals、Git、服务重启或改运行状态制造终态。

## 独立版本工作及验收

已只读复核R37850/50、R37927/27原pins不变。最终R377独审应明确19个default目标未满足、单字段源变更边界和清理移交；其后按原计划串行R378→R379，不要求先修复队列。若独审另发现源/所有权问题则暂停受影响工作。原命令、scope和有限预算全不变，实时权限仍restricted，旧browser escalation不扩散；R379原一次push60秒/一次精确分支ls-remote60秒仍独立受门控。

R390验收是证据与因果边界清晰，不是browser变绿。默认结果不升级，research3只证明软件页面/导出；真实运行和正式研究验收无升级。计划完整原始错误、输入SHA256、终态receipts和离线步骤见plan.json。
