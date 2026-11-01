# UTC-memory 600 秒完整诊断

- 日期：2026-10-25 22:05 +08:00
- 节点：`tests/test_operational_runtime_closure.py::test_private_startup_to_transaction_grounding[memory|sqlite]`
- 执行：外部 agent（用户授权），诊断运行，**未使用 runner、未消耗 R365 槽位、未改产品与账本**

## 0. 结论

1. **不是死循环，也不是超线性爆炸。** 没有观测器时，完整节点（memory + sqlite 两个参数）**572.65 秒跑完并全部通过**。
2. **600 秒是 harness 上限，实际耗时贴着上限。** 历史两次 600.018 秒被杀，是因为观测器与资源侧车吃掉了那 27 秒余量，不是因为任务无法完成。
3. **CPU 的 92.7% 花在 `from_payload` 解码校验**：其中 `_copy` 占 57.9%、`_sha` 占 30.1%；SQLite 仅 0.16%，pytest 基础设施 0.23%。
4. **R365 那一行确实起作用**：还原旧谓词后 **607.00 秒**（超限），当前产品 **572.65 秒**——34 秒的差，正好决定过不过线。

## 1. 方法

- 采样：py-spy 0.4.2，100 Hz，150 秒，**14,826 个样本**，19 个采样错误（可忽略）。
- 计时：四组端到端运行，每组都跑完整节点（两个 backend），串行、机器空闲（16 核，无其他负载）。
- 所有变体都通过 pytest 插件在**进程内 monkeypatch** 实现，产品文件零改动。

```bash
# 采样
PYTHONPATH=src:.:tests PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
py-spy record -f speedscope -o profile.json --duration 150 -- \
  .venv/bin/python -m pytest -q -p no:cacheprovider \
  "tests/test_operational_runtime_closure.py::test_private_startup_to_transaction_grounding"

# 计时（以 fast-sha 变体为例）
BIGSMALL_R158_COMMAND=R365:probe BIGSMALL_R158_T2_RESOURCE_DIR=/tmp/sink \
PYTHONPATH=/tmp/probe:src:.:tests PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
.venv/bin/python -m pytest -q -p fastsha_plugin -p no:cacheprovider <node>
```

## 2. 采样分布

### 2.1 Self time（前六）

| 占比 | 符号 | 位置 |
| --- | --- | --- |
| 24.41% | `<genexpr>` | `local_temporal.py:107`（`_sha` 的逐字符扫描） |
| 14.61% | `_copy` | `local_temporal.py:50` |
| 10.89% | `_copy` | `local_temporal.py:48` |
| 6.79% | `_copy` | `local_temporal.py:51` |
| 5.34% | `_copy` | `local_temporal.py:65` |
| 2.02% | `__instancecheck__` | `<frozen abc>:119` |

### 2.2 Inclusive time

| 占比 | 函数 |
| --- | --- |
| **92.70%** | `LocalEnvelope.from_payload` |
| 76.00% | `_from_local_payload` |
| 75.41% | `decode_local_payload` |
| 66.20% | `visual_bootstrap.from_payload` |
| 57.95% | `_copy` |
| 57.61% | `_object` |
| **30.11%** | `_sha` |
| 17.34% | `to_payload` |
| 16.62% | `semantic` |

### 2.3 测试侧落点

`test_...` → `_b_t2_exercise`（99.2%）→ `poll_once`（98.5%）→ `_b_t3_ground_and_route`（97.0%）→ `_b_t2_adopt_writer_task`（62.5%）。

也就是说：**时间不在仿真、不在 SQLite、不在等待，而在每次轮询时对 payload 的反复解码与校验。**

## 3. 成本结构

### 3.1 校验即复制

`_object(value, fields)` 的实现是先 `_copy(value)` 做整树深拷贝，再比对字段集合。它被嵌套调用：

- 外层信封一次（`OUTER_FIELDS`）
- `payload` 再一次
- 每个子对象（decision / transaction / lease / conditions …）再一次

于是同一批字节在解码链上被复制多层。实测 `_copy` 递归**最大深度 23，平均 3.7**，自底向上的复制量接近“层级 × 体积”。

### 3.2 decode memo 基本不命中

`from_payload` 的 memo key 是**整条 canonical JSON 文本**。轮询场景里时间戳、序号每次都会变，key 随之改变，128 项/8 MiB 的缓存几乎全部 miss。

### 3.3 `_sha` 逐字符扫描

```python
any(char not in "0123456789abcdef" for char in text)
```

每个 64 位哈希都要跑一个 Python 生成器，单次约几十微秒；在成千上万次校验下成为第二大热点（30.1%）。

## 4. 四组计时

| 变体 | 墙钟 | 相对 baseline | 结果 |
| --- | --- | --- | --- |
| 当前产品（含一行改动） | **572.65 s** | 1.00 | 2 passed |
| 还原旧 `_copy` 谓词 | **607.00 s** | 1.06 | 2 passed（但已超 600 s 上限） |
| `_sha` 换正则 | **452.75 s** | 0.79 | 测试逻辑跑完，仅 sink 文件重名报错 |
| `_sha` + accessor 缓存 | **322.19 s** | 0.56 | 测试逻辑跑完，仅缺 sink 环境变量报错 |

差值：

- 一行 `_copy` 改动：**34.35 s（5.7%）**
- `_sha` 正则化：**119.90 s（20.9%）**
- 再叠加 accessor 单次解析：**130.56 s（22.8%）**

> 两个“失败”变体都只死在收尾写 sink 文件（`open("x")` 撞名 / 缺环境变量），测试主体逻辑已完整执行，计时有效。

## 5. 更正此前判断

| 此前说法 | 实测 | 结论 |
| --- | --- | --- |
| “一行改动对 600 秒的上界约 0.32 s” | **34.35 s** | 错了约 100 倍：ABC 判定不是 100 ns 级的纯 C 路径，含 Python 层 `__instancecheck__` 调用 |
| “600 秒说明测试结构超线性、产品有性能缺陷” | 无观测器 572.65 s 线性跑完 | 不成立：是**贴着上限**，不是炸了 |
| “这行改动不是 600 秒的根因” | 仍成立 | 它不是根因，但它是**刚好让节点过线**的那 34 秒 |

## 6. 建议

1. **R366 先做 `_sha` 正则化**（`re.fullmatch(r"[0-9a-f]{64}\Z", value)`）：语义完全等价、零行为风险、实测 **-20.9%**，把节点压到约 452 s，余量 25%。
2. **可选：accessor 单次解析**（`to_payload`/`semantic` 按 `_json` 缓存），组合后约 322 s；但它让多个调用者共享同一 dict，需要 Astra 定所有权与脱别名边界。
3. **不要在 573 s（4.5% 余量）时赌那一次不可退款的 UTC 运行**；先拿 25% 余量再花。
4. 长期方向：`_object` 改为“只校验不复制”，才能消掉 57.9% 的深拷贝。

## 7. 边界

- 诊断运行**未走 runner**，不构成 R365 的 `utc_memory_01` 证据，不产生任何 behavior credit。
- `/tmp/utc-diag/sink*` 是临时目录，**不是** ROOT 批准的资源侧车。
- `raw/*.py` 三个插件只用于复现诊断，不是产品补丁。
- 计时为单机串行测量，受负载影响；四组均在空闲机器上完成。
