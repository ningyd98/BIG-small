# R366 立项申请：`_sha` 快速校验（SHA256 正则化）

- 提出：外部 agent（用户授权），2026-10-25
- 类型：产品性能修复（新根因、新范围），按 AGENTS.md 需实际 Astra 出计划
- 本文是**立项输入**，不是 Astra 计划，也不释放执行

## 1. 问题与证据

完整诊断见 `../20261025-utc-cost-diagnosis/diagnosis.md`（`ba83e793…`）。关键事实：

| 事实 | 数值 |
| --- | --- |
| 完整 UTC 节点（memory+sqlite，无观测器） | **572.65 s** / 600 s 上限 |
| 还原旧 `_copy` 谓词 | 607.00 s（超限） |
| `_sha` 占 CPU（inclusive） | **30.11%** |
| `_sha` 内部 `<genexpr>` self | 24.41% |
| 只把 `_sha` 换成正则后整节点 | **452.75 s** |
| SQLite self | 0.16% |

热点代码（`src/cloud_edge_robot_arm/vision/local_temporal.py:105`）：

```python
def _sha(value: JSONValue) -> str:
    text = _text(value)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError("SHA256 required")
    return text
```

每校验一个 64 位哈希就启动一个 Python 生成器逐字符扫描，在轮询路径上被调用无数次。

## 2. 提议变更

`r366-candidate.patch`（已用 `git apply --check` 验证可干净应用）：

```python
import re
...
_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")

def _sha(value: JSONValue) -> str:
    text = _text(value)
    if _SHA256_HEX.fullmatch(text) is None:
        raise ValueError("SHA256 required")
    return text
```

改动 3 行 + 1 个模块级常量；不触碰 `_copy`、`_object`、编解码、memo、accessor、所有权或任何调用点。

## 3. 等价性论证

| 输入 | 旧行为 | 新行为 |
| --- | --- | --- |
| 64 位小写十六进制 | 通过 | 通过 |
| 63 / 65 位 | `SHA256 required` | `SHA256 required` |
| 含大写 `A-F` | 拒绝 | 拒绝 |
| 含 `g-z`、空格、`-` | 拒绝 | 拒绝 |
| 非 `str`（int/None/bytes） | `nonempty text required` | `nonempty text required`（`_text` 保留在前） |
| 空串 / 全空白 | `nonempty text required` | 同上 |
| 尾部换行 `\n` | 长度不匹配 → 拒绝 | `\Z` 不允许尾随换行 → 拒绝 |

- Python `re` 的 `[0-9a-f]` 是码点区间，不会匹配全角数字或其他 Unicode；与 `char not in "0123456789abcdef"` 一致。
- `fullmatch` 要求整串匹配，`\Z` 仅匹配串尾（`$` 才会容忍尾随换行），二者叠加杜绝了宽松匹配。
- 错误类型与错误消息顺序完全保持（`_text` 仍先执行）。

## 4. 预期效果

- 实测（同机、串行、空闲）：整节点 **572.65 s → 452.75 s（-20.9%）**。
- 相对 600 s 上限的余量：4.5% → **24.5%**。
- 这是纯校验路径优化，不改变任何语义、状态机、时钟或存储行为。

## 5. 验证计划（三层，逐层验收）

1. **等价性单测**（新增 `tests/test_local_temporal_sha_contract.py`）：覆盖上表全部 7 类输入，断言返回值/异常类型/异常消息；同一套用例在改动前后都要通过。
2. **回归**：现有 26 个 codec 节点 + 触及 `local_temporal` 的其余单测。
3. **端到端**：完整 UTC 节点（memory + sqlite），要求 600 s 内完成、全部断言通过、资源侧车完整。

性能本身不作为断言写进测试（避免脆弱的计时门槛），只作为一次性基准证据留存。

## 6. 预算与门禁建议

- 预算：1 次端到端节点运行（child 600 s / outer 900 s，沿用现有有限预算），不新增诊断、不加重试。
- **门禁收敛**（回应 2026-10-25 流程审阅）：R366 gate 只绑直接输入，建议 ≤ 12 项：
  `local_temporal.py`、`test_local_temporal_sha_contract.py`、3 个 codec 测试文件、UTC 测试文件、runner、helper、plan、diagnosis.md。
  历史材料归档为一次性 manifest，**不再递归继承** 649 项祖先 pin。

## 7. 治理影响（必须由 Astra 明确）

`R365` 的 `utc_memory_01` 槽位**不能**用于验证本次改动：`verify_gate` 要求产品字节等于 baseline 加且仅加那一行 `_copy` 谓词，加入 `_sha` 改动后会直接拒绝。

因此 R366 必须二选一：

- **A**：为 R366 申请自己的端到端预算（推荐，等价范围：同一 UTC 节点、同一断言）；
- **B**：显式声明 R365 的 UTC 槽作废，并在 R366 中把该节点的验收边界写清楚。

不得静默复用旧槽位，也不得在改动后沿用旧 gate。

## 8. 风险与回滚

| 风险 | 评估 |
| --- | --- |
| 语义偏差 | 低：仅替换等价谓词，错误消息不变 |
| 隐藏调用方依赖旧实现 | 低：`_sha` 是模块私有函数，无外部导出 |
| 性能未如预期 | 低：已在真实节点上实测 -20.9% |
| 与 `_copy` 改动叠加 | 已实测叠加后 452.75 s |
| 回滚 | 反向 patch 恢复 3 行，无数据迁移 |

## 9. 输入清单

| 文件 | 字节 | SHA256（前 16） |
| --- | --- | --- |
| `src/cloud_edge_robot_arm/vision/local_temporal.py` | 121,321 | `1695aded2b2e1e5c` |
| `tests/test_local_temporal_copy_dispatch.py` | 8,161 | `51cf42610d1b4c5c` |
| `tests/test_operational_runtime_closure.py` | — | 以 HEAD `dd9df375` 为准 |
| `20261025-utc-cost-diagnosis/diagnosis.md` | 6,198 | `ba83e7933729621f` |
| `20261025-utc-cost-diagnosis/timings.json` | 1,432 | `a1da6c337cafb7ec` |
| `20261025-utc-cost-diagnosis/profile-summary.json` | 1,311 | `0c1f8044468d0258` |
| `r366-candidate.patch` | 761 | `21bdc1d06c1ce9f0` |

HEAD 仍为 `dd9df375e1d372490145327bcbfee5804352fcc4`，本轮未提交任何改动。
