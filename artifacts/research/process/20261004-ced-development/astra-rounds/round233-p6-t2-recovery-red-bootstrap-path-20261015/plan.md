# R233 — 有界只读诊断计划

实际作者：`/root/astra_status_plan`；实际模型：`gpt-6-astra`。本轮只规划，ROOT 完整门控后最多执行一次保留数据库诊断，不授权源码修复或测试。

## 问题与已证事实

R232 恢复 RED3 实际 child/wrapper 均为 1，3 FAIL、0 ERROR/SKIP，accepted=false。Memory 首先出现 broker OC1 startup unavailable；清理时唤醒尚未获得 task 的 writer，随后 KeyError 是次生结果。两个 SQLite 用例已进入 private bootstrap，但未完成 COMPLETE 或 episode；worker 内层异常被捕获，后续 original worker poll ended 不能替代真实原因。现有 JSON 与源码不足以确定修复，不能扩大等待时间、改冻结观察器或猜测权限修复。

原始 402 次资源尝试/399 初始化/402 清理等证据原样保留。它们不使失败成为合法 RED。

## 输入与不变边界

`input-observation.json`（36724 bytes，SHA256 `3a48eb2aa410e451c98f6c422ce6ba4f1878f5833287bc6352cc3e7899fcdfdb`）列出 15 原始 raw、27 current/archive 源对、8 历史角色归档、8 当前角色时间点记录、旧合同与 6 个实际 retained DB 的完整路径/字节/SHA。原始 failure index 为 48943 bytes / `6766d743838a733829c7b4322b551259704ff929c947e9ca5775b567e79452ba`；物理 manifest 为 22354 / `ccefdcf84b4d6b04875296d2b0061a335544e770a724f66193c1b96fae63be1a`。

规划仅做文本/JSON/字节读取，未建立 SQLite 连接。6 个 DB 的 18 个明确 WAL/SHM/journal 路径当前全部不存在。执行前后必须复核；发现任何旁文件或字节漂移立即停止，不能用 immutable 模式忽略 WAL。

## 唯一未来动作

ROOT 新编 `implementation/read-retained-diagnostics.py`，先保存全文/SHA，审核 exact argv、三项有限环境和脚本，再预留独立 `R233-retained-database-diagnostic-once` 槽。解释器固定仓库 `.venv/bin/python`；115 秒 TERM 加 5 秒 KILL 总上限 120 秒。完整 stdout/stderr 独立 noclobber 保存，工具对象先 store，stdout ≤6000 UTF-8 bytes。

只对索引里的六个 DB 使用 `mode=ro&immutable=1`、connection-local query_only、拒写 authorizer。每个 DB 一次限定 schema SELECT，再仅对 JSON 中固定 4 个 runtime/5 个 event 表作 table_info 和 LIMIT 65 SELECT；最多 27 表、66 条含 query_only 的 SQL，保留最多每表 64 行。仅真实存在普通表可读，缺表明确记录，不猜名称、不执行 view/virtual table。

列数 ≤64、单字段 UTF-8 ≤65536、完整诊断 JSON ≤8 MiB；BLOB 仅类型/长度/SHA，未读内容明确标注；越界或异常保存有界证据并停止，不翻页重试。所有连接 finally 关闭，之后核六 DB、18 旁文件、27 源和原 raw 不变。完整细则、精确 argv/env/输出路径以 plan.json 为执行合同。

## 原预算与后续门

R223 原 baseline/RED 与 R232 baseline/RED 均保持 spent；两个失败都不是 legal RED。R223 余下 prepare_green、ruff、GREEN9、ROOT settlement 四槽继续 HELD。旧 settler 与 R232 未执行 continuation 不可运行或改写；后者假设 R232 legal RED 的前提已不成立。

本轮新产品/测试/静态/审查/Git 槽均为 0。原 T2 GREEN7、源/测试/旧 runner、角色、STATE/PHASE 不改。ROOT 只可在 R233 写新 gate、一次诊断和步骤报告。获得诊断后必须 STOP，下一轮 Astra 再决定是否需要修复、如何建立新 baseline/合法 RED 和三代结算；本轮不预授权这些动作。

## 验收

只验收证据获取的完整性和只读性。若数据库没有保存内层异常，应如实报告 unknown，不以普通状态行推定根因。T2/T12/native/formal 均未完成。任何新的实际失败保全后停止，不重试。
