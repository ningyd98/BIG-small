# R250 — 新运行数据库 provenance 修正

实际作者 `/root/astra_status_plan`；实际模型 `gpt-6-astra`。仅计划，等待 ROOT 接受。

ROOT 静态全文审查发现尚未运行的 R248 runner 第 583 行，将未来新数据库标成 R242。物理源码确认该 literal 仅出现一次。这不是运行失败；两个角色的 baseline/Ruff/RED 均为 HELD 0/1。

唯一允许改动：`This genuine new R242 run only; old bytes not recovered` → `This genuine new R248 run only; old bytes not recovered`。仅改变该 future-new-run 字符串的一字节，其他 runner 字节、真实 R242 历史标签、夹具、prepare、产品和断言都不变。

- 原 runner：47902 B，SHA256 `7e6627243f58b2f2479c2bfc067ac85b2e28a675fdc7b82c3bcd6b4f62111d66`。
- 预期修正后：47902 B，SHA256 `80b4c43e7d70f269dbc4024c8df2cffc9879b0c0d5f564459d45f1fbfad55151`。
- 原始 finding：82048 B，SHA256 `7f69b96c7d5191d1dc2e6e56c7df62e4d9d9fb4be87eef5420cd573d321728ec`。
- input-observation：70178 B，SHA256 `741983fc5346fb4a6647528d132469e259d6dbc8f47dfceec96ddc71adbb7074`。

完整 before 已保存在本轮 before/run-command.py；观察文件另含完整 base64。唯一 Sol 在 ROOT 接受后，先保存本轮新持久候选，再 CAS 并作一次精确 native Update，保存新的 native/limited.diff/change-report。原 R248 candidate/native/report 全部不覆盖。ROOT 重建原 AddFile 加本次 Update、全文与精确 bytes 对照后，才能另行预留原 baseline。

旧逻辑 runner 的 7e66 pin 只映射到该完整物理 before（或另经 pin 核验的原不可变候选），不得拿旧 pin 当前比对新源，亦不得按路径笼统豁免。新报告明确 runner_before（物理）、runner_after（逻辑）、candidate、native_receipt 三字段 pins。新 gate 只引用不可变本轮产物和当前源 pin；历史原件保持原代。

本轮新增运行/测试/static/review/Git 槽全部为 0，不启动 runner 或新核验管线、不重置 R248 三槽。仅正常标准库文本/bytes/hash 范围门。原 R248 35 缺失隔离、6 当前 DB、有限 argv/env、资源清理和正向 legacy RED 条件不变。源码通过也不代表合法 RED、T2/T12/native/formal 完成。

初始309f94确认本轮目录不存在；9584d1仅完成原件/观察保全，均为普通元数据 exit0，未修 runner。完整输入和步骤以同目录 plan.json 为准。冻结后 STOP。
