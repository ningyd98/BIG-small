# R110 P5 两个消费者测试夹具 API 修复计划

实际 gpt-6-astra；PLANNED_PENDING_ROOT_ACTIVATION。原 Sol 实施；只修改 `tests/test_operational_windows.py`，不改任何产品 API、九份产品源或三份 fixture，不扩大 P5 语义。

## 原始失败和独立根因确认

R107 唯一 GREEN，2026-10-07T20:11:19.843610+00:00→20:12:35.644012+00:00 exit 1；原 JUnit 32 unique=30 PASS/2 FAIL/0 ERROR/0 SKIP。stdout 29002 B SHA32771c702c526c4a271178f0c5de20485327f4cd36e913fad8367132e82a8332；JUnit 32354 B SHA28306aeede04d0e321c9263418cfeded90e31442237c8b0c755559f94ba36296。其余五验证 exit 0，六额度已耗尽，active=[]。原 tmp 的 CPU 数据保持，不复制全 raw/DB。

1. marker 参数节点 line695 第一次调用遗漏 keyword-only now。冻结 marker_association.py:632–639 声明 `associate_marker_target(observation, registration, context, *, now: datetime)`；同一节点 source-change 反例 line700 与过期反例 line719 也遗漏同一参数。三处都必须修正，否则首个通过后仍会同因失败。产品 _associate:459–469 用真实 operational 结果；只有无 local authority 时才使用 UTC age，不能改该门或换成 replay API。
2. replay 节点 line770 直接枚举 `__dataclass_fields__`，其中含 `scope: ClassVar[str]`，传给构造器在 line775 TypeError。当前与独立 pre-P5 VisualBootstrapDefinition 均把 scope 定义为 ClassVar，不是 init 参数。这是夹具字段提取错，不是 decoder/legacy 产品错。

本轮已只读匹配十源+三 fixture 的 pre-GREEN pins；完整失败仍保持失败，不称该批32通过。更早共享 startup/domain/public type/canonicalization/supervision 失败已在本次实际节点中通过；本轮不重做这些产品修复。

## 精确编辑

A. 该原 marker 参数分支内三次 `associate_marker_target(...)`，分别正例、changed source_identity 反例、D=5s+1ns 过期反例，各显式加入 `now=datetime.now(UTC)`。这是每次调用当时的真实诊断 UTC，不取 captured_at 假装当前，不 monkeypatch 新时钟、不更改 fresh 原 captured_at，不修改 raw.now 的原 5s→+1ns 顺序。有效 local D、source 校验、frozen MappingProxy/tuple、DEVELOPMENT_ONLY/NOT_ADMITTED、legacy digest 及三次真实消费者断言完整保留；不传 product default、不替换实际 OpenCV consumer。

B. 顶层 `from dataclasses import fields, replace`。只改 replay 节点原 legacy_arguments comprehension：

```python
legacy_arguments = {
    field.name: getattr(original.definition, field.name)
    for field in fields(original.definition)
    if field.init and field.name != "operational_windows"
}
```

标准 fields 排除 ClassVar，field.init 排除非构造字段；新增 operational_windows 仍排除。相同参数继续分别构造当前和独立 pre-P5 class，并逐一比 payload、digest、初始 record JSON；保留后续监督旧 class 对照、immutable roundtrip、historical duplicate、public new transition 拒绝以及退出 scope 后 UNKNOWN。不能删断言/改 expected/捕获 TypeError 当通过。两份 legacy_codec source-before 必须保留并列入未来有限 Git 测试依赖。

除上面三 call kwargs、一个 import、一个 comprehension 和仅本文件格式外，所有共享 helper/其他 test function/decorator/参数列表保持。marker 的其他六类别分支和 shared tail 原逻辑保持；字段反射修正只在 replay 节点执行。原32节点身份及参数分母不变。

## 一次性验证预算与精确顺序

ROOT 复核当前13输入、原 R107 终态及本计划，激活后单写者保存测试 before；R110/implementation、green 和 /tmp/bigsmall-p5-r110-green 必须新叶，存在即停，不覆盖。先直接 apply_patch 精确编辑，保存 semantic-after；不再嵌套 Python 三引号生成修改脚本。

1. formatter 1次，仅原 NEW 测试文件：`.venv/bin/python -m ruff format tests/test_operational_windows.py`。保存 format-after，不格式化产品。
2. delta proof 1次：`.venv/bin/python <R110>/implementation/delta-proof.py`。仅 stdlib AST/type_comments/tokenize/hash/JSON；不 import 产品或重跑 R107 proof。证明 exact 3 kwargs+fields comprehension/import，移去这些已列变化后对应函数 AST 相同；所有其他定义、参数/decorators、assert 数量及内容保持。格式前后 AST/type-comments/ignore 绑定/注释不变。九产品+三fixture+两legacy原件逐项 SHA 同原，旧30通过节点的函数/参数和全部 shared helper AST 不变。原 R107 JUnit 30 PASS 的明确 nodeids 存适用性清单，不能只使用总计。
3. Ruff 1次：`.venv/bin/python -m ruff check tests/test_operational_windows.py`。
4. formatcheck 1次：`.venv/bin/python -m ruff format --check tests/test_operational_windows.py`。
5. GREEN 1次，仅两个失败的精确节点，一条 pytest argv：

```text
.venv/bin/python -m pytest -q -p no:cacheprovider
 tests/test_operational_windows.py::test_all_p5_categories_use_same_original_owner[marker]
 tests/test_operational_windows.py::test_public_replay_descriptor_never_live_authority
 --basetemp=/tmp/bigsmall-p5-r110-green
 --junitxml=artifacts/research/process/20261004-ced-development/astra-rounds/round110-p5-consumer-fixture-api-20261008/implementation/green/junit.xml
```

用 argv 数组保留带方括号 nodeid，不让 shell glob。环境 PYTHONDONTWRITEBYTECODE=1、PYTHONPATH=src:.；各命令独立原 argv/start/end/exit/stdout/stderr，预期全 exit 0。新 GREEN 必须2unique=2PASS/0fail/error/skip。任何非预期失败停并保留原件，不自动重试。无 RED、额外 import-sort、collect-only、compile、mypy、OC1/旧CPU/旧proof重跑、actual/model/network/Git/子代理额度。

最小2节点的依据是仅这两条动态路径改变，产品/fixtures/helpers/其余30节点完全一致，proof须明确证明这一点。若实施需要共享语义变化、proof不能证原30适用或输入漂移，停止重新计划，不悄悄改成全32也不假称旧结果适用。最终覆盖应报告 R110新2 + R107原30 = P5 32 unique 覆盖，另适用复用 R105原60 OC1；绝不称本轮新跑32/92。

## 验收边界

实施后冻结十源+三fixture、test差异、步骤报告和有限pins，原独立审查接续全部 P5需求映射；两节点通过并不自动等于完整审查 PASS。完整P5验收仍需原 startup/七消费者/typed边界/私有权限/cleanup/legacy 范围，无减少；actual=0，P6 lease/事务/dispatch和native完整正链尚独立。保持原27RED、R10592、R10632、R10732失败原件与消耗预算，不覆写原记录。新的较小验证分母不是放宽产品准则。
