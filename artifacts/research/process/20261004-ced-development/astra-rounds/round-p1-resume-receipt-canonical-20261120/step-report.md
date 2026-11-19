# 续行前的原始回执逐字节核验

首次续行在第 12 槽 BEGIN 前退出 1。10 份既有 strict 审计与重新核验后的标准 JSON 字节相同。第 1 槽的 `physical.safety_events` 和 `physical.self_collision_checked_pairs` 在内存为 tuple，JSON 读回为 list。Python 对象相等比较因此拒绝了原回执。该次失败、原回执、原固定 launcher v1 及原冻结继续留存。 [完整只读复算](../round-p1-oversized-audit-resume-20261119/first-resume-strict-canonical-readback.json)

v2 外层沿用原代码的标准 JSON 序列化。严格和补充两个读取口分别用原文件实际字节与重算的标准字节比对，并保留严格解析、原终态和同一 owner 锁。7 项通过，覆盖 list/tuple 同值的正例、bool/int、值与成员顺序、遗漏字段、改序列化原字节、重入、原 BEGIN 缺 END 及补充来源错误。首次离线复算前缀 11/11，10 份 strict SHA 和 11 的 v1 补充 `d1758e71…` 均逐字节相符。 [前缀证据](verified-prefix.json) · [v2 恢复入口](resume_v2.py)

实际续行在原锁内复验同一前缀后才发第 12 槽，原 1–11 槽均无再次 BEGIN。该状态与完整批次结果分别记账。
