# R304：unit basetemp 缺失的限定执行前修正

实际规划模型：**gpt-6-astra**。仅计划；没有运行测试。

## 事实与问题

R302 `observer_red` 已 ROOT RESERVED 1/0，AUTHOR HELD 0/1，实际 dispatch 未开始，输出目录不存在。runner 14464字节，SHA256 `f36559d6cacba23c102684cb04c12c938b66975dec317af1e754c9167c4d251b`。

unit 节点不使用 tmp_path，pytest可能不创建 basetemp；原 runner 无条件 strict_index 要求目录存在。这是 ROOT 实施前发现的潜在工具缺陷，不是已发生的测试失败或新增合法RED。

## 唯一逻辑修正

plan.json提供两处精确单次替换：以 lstat 获取 basetemp 状态，仅当 `unit_only` 且真实 FileNotFoundError 时记录 exists=false、is_symlink=false、index=[]；将这份真实根目录观察同时写入 result 和 persistent index。存在路径一律调用原 strict_index，坏symlink不当absence；权限及其他错误照常失败。behavior 缺目录继续报错。不得为通过检查创建空目录。

## 原件与世代接续

ROOT 先保存 runner、red-source-gate、root-red-source-acceptance、ROOT ledger、AUTHOR ledger 的完整原字节/base64/mode/hash及独占归档。本轮明确允许推进前四个原操作路径，但不损失冻结旧世代。AUTHOR不改，原R302 plan、测试、命令、时限和额度不改。

顺序：修改并审阅runner两处差异 → 新generation-map/source-review → CAS gate的 sources.runner 与 pins[264]（先确认其path）→ CAS acceptance的新gate pin并追加本轮真实审阅 → CAS ROOT observer_red 的 source_gate/acceptance两个指针。保留 RESERVED 1/0、原reservation_id和所有其他key。每次CAS按完整before bytes/mode核对并留after；整个过程中禁止dispatch。

最终独立读回新指针，AUTHOR字节不变、输出仍absent后，保存R304/root-generation-acceptance.json，直接执行原literal RED一次。后续G1 gate沿原R302审阅绑定新runner。无需再建通用gate或增加任何测试/运行槽。

## 验证与停止

本轮只做源码差异、JSON/哈希、精确字段变更和absence核对；实际验证由已预留RED承担。部分CAS、输入漂移或提前dispatch时保留现场并停止，不退款、不重置预算。空unit索引只表示真实目录缺失，不能冒充行为/数据库完整证据或T2通过。
