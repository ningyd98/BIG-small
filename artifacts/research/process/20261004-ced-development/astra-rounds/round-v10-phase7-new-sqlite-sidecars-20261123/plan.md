# Phase 7 新生成 SQLite 旁文件的位置复原计划

gpt-6.2-astra · 2026-11-23 · 基线 `2ec0c98f82a6cab7fb1f9abbec37631226d3d605`。本轮是独立文件操作，只允许将 13:56 查询新建的两个旁文件原样移出正式目录，完整保留在本轮私有证据目录。实施由主线程负责。

Phase 6 的 collection-verification.json 与 validation.public.json 中 collection.sqlite_sha256 只有 runtime.db，SHA256 为 09fab63b235ab3317f27b2528aea724015629863fff287496cb45430d23f4b1a；采证脚本当时在正式输出依次检查 db/wal/shm 后才在私有副本查询。原始帧 inventory 的作用域是 originals/。另有本轮查询前后的顶层文件列表、已关闭的 mode=ro 查询回执和文件指纹。私有 Phase 6 db-snapshot 下可能有自己的旁文件，本轮仅以其主 DB 字节比对。DB 与 publication.lock 均生于 11 月 22 日。新 WAL 与 SHM 生于北京时间 11 月 23 日 13:56:19.514009926，分别为 0、32768 字节，inode 57058354、57058355，device 66309，均为单链接普通文件。SHM 的 mtime 为 13:56:19.514151845。逐文件 SHA、元数据与历史输入见 plan.json。仅持有 mode=ro 连接也可能产生 SQLite 旁文件。

1. 暂停并确认无流程将再次打开正式 DB，源目录、工作树与私有目的父目录均无符号链接。用普通文件 stat/sha256sum 读取校验，严禁在正式目录打开 SQLite。复核两个历史 sqlite_sha256 集合、冷副本、原目录前后列表和原 inventory 范围，核四个现存文件的 inode/device、类型、单链接、birth/mtime、大小、SHA，核正式协议、原件清单/claim 未变。既有 sidecar-open-handles.log 为空、exit 为 1 只是此前时点。
2. 即时在具备主机进程可见性的环境用 lsof 或 fuser 对 db、两旁文件与 publication.lock 检查占用，包括映射；保留命令、stderr、退出码及可见性。确认为零且无无法核实的活跃 DB 使用者、生产作业/worker 时才继续。如工具出错、命名空间不能看到实际进程、权限不足或输入不符，停止对应操作并保留原位置。
3. 在 E 下新建一个仅本轮使用的私有目录，写外置动作日志；确认源与目的在同一文件系统、两个目的名称均不存在。对 WAL 与 SHM 两个确切 basename，逐个再次 lstat/核 inode、大小、SHA、无占用后无覆盖 rename，保留 inode、数据字节及 mtime。不可通配、删除、复制后删除、重建、截断或 checkpoint。两次 rename 不是一个事务；若第二次失败，记明两个实际位置、inode 与哈希，保留全部字节。恢复只允许在以上复核条件再度满足时移动尚留源处的同一文件；任何不符或目的碰撞停止，不以清理/覆盖完成。
4. 复核两个私有文件的 device、inode、字节、mtime 与校验和，记录 rename 导致的 ctime/目录元数据变化。正式顶层名称应与查询前列表完全一致，重核 runtime.db、原 publication.lock 的 SHA、inode、mtime 及正式原件/claim 摘要。将 source/destination、清单、实际时间和占用证据留在 E。后续 DB 核对首选独立私有冷副本，本次已确认无活动 WAL 且原 DB 静止时也可用 URI mode=ro&immutable=1。不得移动或写 DB/历史 lock/正式 raw/协议/claim，预算为零次正式仿真、零新 claim。本步骤不动产品、主计划或 B 补计划，结果可另记阶段总结。
