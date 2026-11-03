# ETEAC 修复与验证

已在SQLite仓库修复同线程重复获取普通锁的问题：六类公共getter保留装饰器及原SQL/解码/校验体，持锁内部流程改用私有读取；恢复列表内部链同样处理。普通Lock、BEGIN IMMEDIATE、guard、CAS/commit/rollback和外部list路由未变，protocol/memory/worker/dispatcher/timeout未改。

原代码RED捕获protocol215→sqlite976，8秒有界失败且回收；修后4个新短合同、272个原repository语义、220个visual合同通过（4项原backend不适用skip），4个短worker测试通过。AST精确比较及独审均确认结构保留和持锁图无残留wrapped reader。

原输入语义的新真实MOCK双任务：ETEAC自然SUCCEEDED、task_success=true，1.563512秒；其返回后预排PCSC仍QUEUED attempt0，第二次poll自然成功，1.692480秒。均attempt1终结、lease释放、无heartbeat/run SQLite fd、无强制终止。官方source_tree_hash为`25b44519b8db3187f1376522ed983792de2a2b5e239513c82857d4c82f246912`，另有完整所选源码pinset；parent HEAD ac6351b与修后工作树分开登记。

保留三类历史：原ETEAC失败；180秒combined guard总cap（memory138秒PASS、SQL后来单段139.94秒PASS）；新验收最初把结果run_id与job.run_id误关联的失败。正确关联是result.experiment_id==job.run_id，结果run_id为stable_run_id确定性哈希；R402仅修这一属性，原短RED/GREEN合同函数不变，不冒充全文件同字节。

尚待：foreign-thread guard在创建线程前的初始transition前置失败，四个其它剩余实例已通过；最终guard验收交R403，不以原生成功替代权限验收。全部旧raw/DB/失败冻结不改。独立最终审查及精选Git交付尚未完成。全19浏览器问题、RGBD/MuJoCo、物理和正式研究未因此升级。

## 关闭状态

核心死锁修复与原生双任务链路已验证；整体验收未完成。R403观察启动器误用audit的pins键，实际schema为inputs；在invocation/Popen前失败，未执行任何R403产品/测试子进程。R404仅行政补正计划已保存，但原1800秒余量不满足，未实施或追加运行；总轮含行政关闭实际超时，不宣称预算达标。最后的foreign-thread guard缺口仍BLOCKED，原前置失败未被修复或证明原因。

未提交、未推送；HEAD仍ac6351b，index为空，Git配额未使用。所有产品修改/测试源码和旧失败保留。独立最终审查可接受产品/native部分，但不能批准完整交付。实际硬件/模型调用/全浏览器/正式研究仍未执行。
