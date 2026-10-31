# R369：SceneSummary 输入合同与有限 runner 修补

实际模型 **gpt-6-astra**；agent `/root/astra_r367_sha_review`；2026-10-26。本轮仅规划，不改产品/测试/旧账证，不运行、commit 或 push。输入大小/SHA、命令与验收见 `plan.json`。**新短命令未授权，长跑额度为零。**

## 四项裁决

1. 唯一测试修复：在 `_b_t3_external_utc` 的 `SceneSummary` 构造中补 **`updated_at=external.captured_at`**。它满足必填带时区字段，与两处生产调用一致；不改schema/default、业务判定或原断言。
2. 先直接辅助函数小合同 **RED → 一行修复 → 同一合同 GREEN**，不先跑约1100秒的单 exercise，不修改完整 UTC 的循环/backend 参数。已有真实RED；新≤30秒RED只确认小合同复现同一缺陷。
3. **拒绝用6.6k外推自动替换双 backend 合计600秒标准。** 原标准仍未通过；短合同不等于完整 UTC。后续完整 memory sizing 的目的、预算与保护条件另议，本轮不复用3600秒额度。
4. runner 仅修显式分段计时、异常收口及有界输出捕获，使用新轮一次短自检槽。`_sha` 保留，copy→sha 分开提交策略沿用；本轮不操作 Git。

## 原始证据及限制

R368 memory 为 **1 test / 1 failure / 0 error / 0 skip**，退出1、非超时；失败是 `SceneSummary.updated_at` 缺失。JUnit suite1113.625秒、case1112.862秒。`result.json` 的 `duration_seconds` **字段不存在**，不是 null。

原origin→reaped独立派生 **1114.078397227秒**（原时刻见JSON），含失败前缀与清理，不是完整exercise通过耗时。侧车1次正常返回poll不能证明exercise通过：callback错误会再抛；`assertions_completed=false`，清理错误为空、observer已恢复。

memory3.3k/双 backend6.6k、六场景等成本及 `_sha` 精确20%收益均未成立。已有 startup profile 不能替代 UTC 归因。

旧 runner 输出自检配置1MiB，实际保存 **41943040B**；只查 reason 与 size>0，不能称硬上限通过。保留原40MiB文件，不截断历史。旧5/5也未证明消费原子性、outer强制执行或完整资源验收；没有当前泄漏证据。不宣称所有旧缺口已解决。

## 最小实施步骤（未执行）

- [ ] 静态扫描 `src/tests` 的 `SceneSummary` 构造，列漏传和无法静态确定的 kwargs；不顺带改其它点，不运行全量 collection。
- [ ] 新建 `tests/test_operational_external_utc_scene_contract.py::test_external_utc_scene_contract`。按JSON的2×2有效RGBD与HOME配方构造经校验的真实 `RGBDObservation`/`TaskContract`。不调用repository fixture、MuJoCo backend、worker/DB/model。
- [ ] 固定 `at=2026-10-26T00:00:00Z`，只固定pipeline时钟，不mock模型或两个业务validator。直接调用原helper，执行其±1000/5000ms四边界及expired-decision原断言；检查返回值与输入未变。
- [ ] 新 runner 经一次短自检后，原代码运行小合同：恰好1failed，Pydantic 报缺 updated_at，退出1；不能用 xfail/raises 把失败伪装成通过。随后只补一个 keyword，再跑相同测试字节，要求1passed/0fail/error/skip、退出0。

## runner 两项修补

在本轮新文件中有限继承现有实现，旧 runner 冻结；不另造框架。

**计时/收口：** 记录launch/spawn/stop/reaped/capture/wrapper单调时刻、分段时长与原因；`duration_seconds`定义为launch-to-reaped，含终止等待，详细算式见JSON。缺阶段写missingness。实际finally持有proc/pipes，异常或缺JUnit仍清理并保存source-after/结果/完成记录，保留主要错误。

**输出：** 子进程两流接 PIPE，nonblocking selectors 公平排空，固定≤64KiB缓冲。每次最多读 remaining+1，文件最多写 remaining；首次越界字节即终止，记录 captured≤cap、observed≥cap+1、capture_complete=false、未读字节未知。退出后也检查管道尾部，不能因快速退出绕过限额；恰好cap且EOF不误报。普通流cap32MiB，自检1MiB；**文件不允许chunk过冲**。不使用无限communicate/队列或仅缩短轮询；受限前缀必须标为不完整raw。

新自检7项见JSON，覆盖缺JUnit、TERM/KILL、两流越界/恰好cap、预检拒绝；检查实际字节、时长、missingness、cleanup及消费。原资源/清理合同不豁免，长跑另核保护条件。

## 预算、验收与回滚

新自检一次60秒/outer90；RED/GREEN各一次child30/outer60。并行1、cleanup15含TERM5、capture10；显式outer保护。新槽不重试，worker/DB/model与长跑预算均0。

授权后须复核输入/新测试/runner hash、静态无副作用路径、独占新输出目录、源/环境与空闲空间；先自检，再RED/GREEN。只有指定缺字段RED是预期失败；其它新失败保留原始字节并交实际Astra，不自动重跑或延时。报告分别记录开发、运行与研究验收。

回滚仅撤销updated_at keyword，保留合同/原始账证，不回滚`_sha/_copy`。沿用明确路径交付与拆commit原则；本轮无长跑或Git执行额度。
