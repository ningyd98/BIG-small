# R264：父 GREEN7 bridge 生命周期及案例归属修正计划

实际作者 `/root/astra_status_plan`，模型 `gpt-6-astra`。仅静态计划，待 ROOT 全文/输入门。

已确认两个未执行源码合同缺口：v1 main909 预留 author 后，911 写证据和934–953 构造 invocation 位于 try954 之前，异常可能绕过 finally 的同键 SPENT/结果保全。capture_cases850–870 仅把资源 sidecar 与全局 scenario_files 分别保存；六种文件名齐全不能证明每个节点的文件归属。两者均不是已发生的运行失败。

R264 规划器另一次 a6be9c 元数据断言失败保留原件；R265 已由 ROOT 接受，确认原17622字节 helper 块精确复制，仅更宽切片多一 LF。本计划不重放失败、不改分隔字节来迎合错误断言。

**限定修改**：仅同一 Sol 修改新 bridge 的 main 生命周期、必要 cas_author 状态/原 mode 保持、capture_cases 及有限元数据辅助。四个原 helper 完整17622 B / `0a2601487ad75ccb1ae32872d40f340ab74ba799aa394f76855fea898687ffe4` 保持字节相等。产品27、保护211、测试/observer、旧 runner、原候选/native/report及所有旧 raw 均不动。

生命周期：先构造最小 outcome 与已知预留代际，再进入覆盖预留及全部后续动作的外层 try/finally。预留后的写文件、invocation、handler、子进程及证据解析都不能绕过同键 SPENT 与可用结果保存。os.replace 后回读失败也必须根据实际 ledger bytes 区分 before/reserved/spent，不能因函数未返回就认为未消耗。各证据阶段独立记录错误；可选归档写失败不得阻断 SPENT 尝试。保持 used1/rem0，未知或冲突代际只如实失败、不回补、不重试。原 ledger mode 据实际 before 保持，不声称已发生 mode 漂移。无法捕获的 SIGKILL/宿主丢失不伪称 finally 成功，仍由 ROOT 后续事实处理，不能重复运行。

案例归属已有真实来源，无需新 collector：冻结资源记录的 sqlite_connection 有实际绝对 path、PID、initialized；真实 software_factory 在每个 exercise directory 创建 events.db，Memory 转置前的原 SQLite 也真实创建并关闭。case helper 将 JSON 直接写在同一 directory。按 case 文件父目录，与各真实 sidecar 中 initialized 的 `directory/events.db` 记录做唯一 node/PID 归属；同 sidecar 多连接保留，跨节点/缺失/冲突拒绝。不得猜 pytest 自动目录名，不把稀疏 TRUE_COMMIT scenarios 当所有案例映射，不伪造 Memory 数据库。

冻结正文的成功输出精确为：两 backend wait 各2文件；dual database 的4个 commit-seam 各2文件加 same-live-owner 1文件；两 backend budget 各2文件；两 backend writer 各1文件。共7节点、15真实目录、19 scenario 文件。plan.json 列出逐节点/目录叶名/文件名表。每个 case 记录保存实际 nodeid/PID、sidecar pin、完整文件字节/pin、实际目录和匹配资源 ID/path；严格排除缺失、额外、孤立、歧义和别名。资源分母继续按实际分配，不能拿19作资源数。失败时保全可用证据并显式标缺口，不生成虚构链接。

实施前 ROOT 核 v1 59929 B / `8200a5619c9f9c31f9e565313689f268143cea8b1e02634ccf1d7912de6443ab` 仍适用。Sol 先在 R264/implementation 独占保存完整 before/base64/mode，再持久完整新 candidate，native 有限 Update、actual、diff/report 均用新路径。原 R258 prepared source/native/report/diff 不覆盖。旧 logical runner pin 在修复后只解析到其具体物理 before/原不可变 candidate，不能全路径豁免。新报告给 before/candidate/after/native/diff 精确 pins；ROOT 组合原 AddFile 与新 Update 重建完整新字节，全文复核后再进既有 R258 门。

新增运行、测试、静态、审查、validator、Git 槽均为0。原 t2_green 双角色仍0/1 HELD；本计划不预留、不运行。七节点、原 finite env/prerequisite、600s+15s、预算与角色身份不变。35缺失/null、90旧 sidecars、12+18 retained DB 分组及全部原严格验收不变。只有未来实际 GREEN7+ROOT独立验收后才进入原 fresh12；不宣称 T2/T12/native/formal 完成。冻结后 STOP。
