# R165：四份准备报告的克隆 API 恢复

> 实际 Astra：gpt-6-astra（`/root/astra_status_plan`）。待 ROOT 核对激活，仅恢复元数据。

作者编排在调用 tools.apply_patch 前遇到 ReferenceError: structuredClone is not defined。运行环境未提供该 API；没有嵌套工具、shell 或报告写入。完整可见错误和七行 prefix 已保留，缺失的完整失败 JS/cmd/分流不重构、不重放。

R163 两 helper 修正和 f3c212 continuity 已实际保存：测试现123845字节，原 A 前缀、七节点测试正文、22生产、211保护和 runner 不变。此为 source-only，不是运行通过。mypy baseline 已真实单次 exit1，72 errors/3 files/22 checked，额度1已用/0剩余；其余14条仍HELD。不能沿用旧总0，也不能将 census 说成静态通过。

ROOT 激活后，唯一作者用一次直接 tools.apply_patch 更新四份已有准备报告。使用明确 JSON 字面字段，或只对已知 JSON-compatible 数据用 JSON.parse(JSON.stringify(value))；禁止 structuredClone、嵌套模板或新 helper。更新精确 candidate/helper说明、baseline事实和1/14预算，保留七节点/预期及原 argv。四份 R163 before 原件保持不变。完整17项输入和字段蓝图见 plan.json。

随后只做一次内嵌标准库 bytes/hash/JSON 核对，保存完整实际工具返回。测试、生产、runner、ledger不改；不重跑baseline、不执行RED/GREEN/静态/Git。

报告状态为 FIXTURE_REPAIRED_SOURCE_ONLY_PENDING_ROOT_GATE。恢复后 ROOT 完成原测试/runner/fixture全文及 pin 门，才可释放原 RED 一次；本轮不直接放行，不授予软件/native/实际/formal验收。新失败或漂移立即停，不自行替代重试。
