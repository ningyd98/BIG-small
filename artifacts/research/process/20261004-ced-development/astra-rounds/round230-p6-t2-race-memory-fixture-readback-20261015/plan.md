# R230 Memory 夹具 publication 读回修正计划

> 实际作者：gpt-6-astra /root/astra_status_plan。仅规划；ROOT 审核后由原唯一 gpt-6.1-sol 作者实施。

已确认新测试在所有 backend 调用仅支持两条 SQLite connection 的冻结 helper；Memory 分支没有 reads['event']，会在竞态目标断言之前出现 setup KeyError。这是静态结论，未运行复现，也不是合法 RED。原始完整证据和三份物理 before 均保留。

仅修改 tests/test_local_public_writer_binding_race.py：新增 _r223_operation_rows(events, reads, operation_id)，并替换 during_episode 中唯一读回调用。SQLite 原样委托冻结 helper；Memory 在真实 events._lock 内调用实际 local_receipt_read_unlocked，释放锁后从真实 job SQLite 连接查询同一 operation_id。返回固定 event/job 两组真实记录；缺失记录保持缺失，不造 COMPLETE、不增加伪 event SQLite，不写 binding 或权限。

现有 COMPLETE、真实 binding、时间顺序、竞态断言、资源分母、清理和全部九节点不变。Memory 对应 event 存储，job 始终为 SQLite；不能将其写成两份 SQLite 持久证据。

- [ ] ROOT 完整审核计划、14 输入 pin 和 before 字节；目标须仍为 15638B/cb827d4e…，方可释放限定编辑。
- [ ] 同一 Sol 只做 helper 插入和唯一调用替换，保存完整 after、diff、report 和真实工具回执。
- [ ] ROOT 以普通标准库文本/bytes/hash 门证明两个精确编辑以外逐字不变，并核真实锁、receipt API、job 查询及原断言均保留。
- [ ] 源门通过后恢复原 R223 准备；原命令仍需独立 gate。父 S2 和新脚本准备可以独立继续，不用旧快照误锁其合法新版本。

本轮新增测试、静态、审查、Git、执行验证槽均为 0，旧槽不重置。原 R223 RED3 必须实际完成 bootstrap 和两端真实 COMPLETE/binding 读回后才验证竞态；setup 错误仍需停止。未来 GREEN9 才能提供行为证据，当前不授予 T2/T12/native/formal 通过。
