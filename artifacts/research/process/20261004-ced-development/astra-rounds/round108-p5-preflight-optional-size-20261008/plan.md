# R108 P5 前置可选尺寸元数据恢复计划

实际 gpt-6-astra；PLANNED_PENDING_ROOT_ACTIVATION。只恢复已批准 R107 的作者前置读取器，不重新规划产品，不授予额外测试额度。

## 原始失败与根因

R107/startup-stop/failed-preflight.py 第 10 行无条件比较 `path.stat().st_size == x['expected_bytes']`。原 ROOT activation 的两份计划记录 expected_bytes 为 JSON null（未声明可选尺寸），SHA 均匹配；作者把 null 当成具体长度，因此第 13 行 assertion 在 mkdir/source-before/产品写入之前失败。原工具 b519e9 exit 1 输出逐字保留于 startup-stop/original-tool-output.json：

```text
Traceback (most recent call last):
  File "<stdin>", line 13, in <module>
CHECKS 75 ALL_MATCH False
AssertionError
```

84bc0f 是原作者只读定位，不是修复重试；没有独立原 UTC 起止，不补造时间。该失败不证明产品错误、SHA 漂移或 R107 授权无效。既有 activation bf389fd200a48c60f71302efdd7233bca83e0a0aa5a5d13d618c611b58777b5f 保持有效且原字节不改。十源冻结、六额度 used=0、active=[] 由 stop-final 收据记录；此轮读取的是 startup-stop，不冒称重新运行了 75 项预检。

## 唯一恢复范围

原 Sol 在 ROOT 激活 R108 后保存一份新前置脚本到 R108/recovery/preflight.py，保留原失败脚本/报告。仅把 activation check 读取改成明确可选尺寸处理：

```python
expected_size = row.get("expected_bytes")
if expected_size is not None:
    if type(expected_size) is not int or expected_size < 0:
        raise ValueError("invalid declared expected_bytes")
size_match = expected_size is None or actual_bytes == expected_size
match = actual_sha256 == row["expected_sha256"] and size_match
```

先检查 activation 为 dict、checks 为 list、各 row 为 dict，path 和 expected_sha256 为非空字符串；SHA 必须为 64 位十六进制。缺失/null 尺寸表示未声明，仅略过尺寸比较；0 是已声明的长度，必须真实比较；bool、负数、字符串、容器均拒绝。不把 null 变 0，不信任旧 match/actual_sha256 字段代替当前读取。每文件一次读取字节，同时计算 SHA 和长度；记录 size_requirement=UNDECLARED 或 DECLARED、实际 bytes、独立 sha_match/size_match。

## 执行顺序与目录前置

1. ROOT 复读本计划及八个有限 pins，保存新的 R108 activation；不修改任何 R107 文件。原 Sol 核对双计划 SHA 与输入。
2. 新 metadata 前置只运行一次，重验固定 R107 双计划/原 activation SHA、原 activation 精确 checks 以及原 new_outputs_absent。这是此前失败前置的必要重新核对，不是重跑产品 proof/static/CPU；不重新执行历史验证命令或扩大递归扫描。按固定 R107 scope 验证十源仍匹配 startup-stop/R106 freeze，六额度全零且没有在途命令。
3. R107/startup-stop 已存在且必须保留；R107/implementation 当前未创建，须在写入前检查。三个 fixture、R107/implementation/green、/tmp/bigsmall-p5-r107-green 仍须缺席。若任一意外存在或固定 SHA 不符，停止，不覆盖/清理/猜测恢复。
4. 所有检查通过后，按原脚本意图新建 R107/implementation，保存本次 input-check.json 与原三份 modified_python source-before。准备脚本及原 argv/UTC/exit/stdout/stderr 记录放 R108/recovery，避免抹掉失败；不得先写产品再完成检查。报告检查数量从实际列表计算，不照抄旧 progress 的 67。原 source-before 仅三份精确源，不复制历史 raw。
5. 恢复原 R107 已批准三 Python + 三 fixture 实施及原验证顺序；严格继承 import_sort、formatter、delta_fixture_proof、ruff、format_check、GREEN32 各剩 1。RED、OC1 rerun、额外 CPU、actual、formal、Git 均 0。R108 不新增产品验证预算，不重跑 R105/R106 或已通过 proof。

本次恢复前置预期 exit 0；其他非零、源漂移或新根因按 AGENTS 停止。成功只证明前置 schema 处理与输入检查通过，不证明 P5 软件/actual/formal 通过。R107 六失败修复、32 节点和最终独审边界全部原样继承；计划及失败原件不得覆写。步骤报告须引用本次元数据恢复和原失败，阶段总结据真实终态补写，不提前写 PASS。
