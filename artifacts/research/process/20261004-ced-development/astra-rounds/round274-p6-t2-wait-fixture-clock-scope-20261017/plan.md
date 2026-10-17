# R274 — wait夹具的clock生命周期选择

实际 `/root/astra_status_plan` / `gpt-6-astra`；仅计划。Memory取证child1/wrapper0，真实missingraise在exercise `tb_lineno4309`，post-unwind为4316，发生于D_lease第一operation。它不是GREEN；ROOT独立358项完整性检查接受取证。

已证实静态缺陷：observer只在两domain外创建一次clocks，第二exercise已有两个D_lease条目，而helper4164–4165全列表筛选后要求唯一。holder异常被存入errors并释放锁；主线程missingraise会跳过后续errors断言。实际trace没有holder的异常/历史locals，所以本次究竟触发4165还是更早4秒观察错误仍unknown；不能归因产品TTL/origin。

最小修复仅冻结test尾部两个函数、五处精确文本替换：每domain在exercise分配前记clock_start；显式传helper；按observed.clocks[clock_start:]筛选，仍唯一/未关闭；两个现有holder断言原样移入join后的finally。完整旧列表/所有资源分母保留，不删旧clock；不改observer、产品、时间/权限、两个raises及其regex、七节点、其余断言。精确old/new与派生after SHA在JSON；未生成或写入候选。

完整254018字节before及base64 manifest已独占保存。旧168003前缀66b6c373…必须保持，其他文件和所有范围外字节不变。唯一Sol只能在两个R268诊断全部完成、ROOT完整结算/检查dual新发现后，接受独立source-only release再实施。当前dual运行/准备期间任何27source不得改；计划不将正在变化的角色pin当永久当前身份。

本轮新增runtime/测试/静态/SQL/Git/review槽全0；原GREEN7和memory诊断不退款，不借dual槽验证。后续行为必须由明确新有限验证续接覆盖原memory/sqlite两个wait节点的两domain、真实锁等待、两次拒绝和预算/持久化/资源约束；尚未授权执行。源门不能冒充修复通过。

冻结计划、观察、完整before和原工具回执后STOP。
