# R105：P5 静态及 CPU 夹具有限恢复

实际计划作者：gpt-6-astra。实施作者仍为原 GPT-6.1-sol 单写者。状态 **PLANNED_PENDING_ROOT_ACTIVATION**；本文只规划，未执行产品、lint、formatter、proof、CPU、actual 或 Git。R103/R104 和原失败一律保留且不修改。

## 证据与根因

R103 原 Ruff command-result 真实 exit1，stdout SHA `fd9e792e897190b75454d0bf19d60aab65502cc1564fcd75d3246dcc217c892e`：bootstrap.py:230 F821 缺 MappingProxyType 导入；operational_windows.py:303 B018 裸 property 求值；I001 共四块（该模块顶层、worker_runtime.py:1172 local、tests marker:550/replay:606）。实际 argv/stdout/stderr/UTC 都引用原收据，不伪造重跑或新输出。R103 scope proof 已 exit0，未运行 format/GREEN。

另有两项已冻结源的只读确定预测，**不是已执行测试失败**：marker 分支先消费 raw.now=5_000_000_001，随后共用尾部倒回5_000_000_000要求 VALID；OC1 _read:277–288 对倒退关闭 owner。cleanup wrapper 只统计“从未关闭变关闭”，但负 counter 节点已使 OC1 关闭，随后 wrapper 真调用 close 也不加计数，和 exercise 的恰一次断言矛盾。两项均为夹具生命周期/时序，不准改 OC1 或产品迎合它。

详细原 provenance、有限读取和源码 pin 在 source-observations.json/plan.json。已只读核对十源与 R103 十份 source-after 同字节；最终 freeze SHA `b71a14db912b575a00f9ae19dc393e6b2114b2e2c9d8130c8307d5d992aa0805`，budget SHA `6cb94f2b99c9d800921e210af2d038699b952351859a287fea9da6e4b77404ea`。32 预定 P5 case 不新增参数或节点；实际 GREEN 尚未发生，不能冒称32通过。

## 精确修改范围

只允许以下四个现有文件，全部都在原十源内；其余六源与 OC1/config/既有原件 byte-identical。

1. `src/cloud_edge_robot_arm/repositories/event_autonomy/visual_bootstrap.py`：顶层新增 `from types import MappingProxyType`，位置由本次有限 I 整理确定。除该导入外所有 AST/注释不变，不重写 freezer/replay/旧 digest。
2. `src/cloud_edge_robot_arm/vision/operational_windows.py`：`self._clock.domain` 改为 `_ = self._clock.domain`，保留一次属性求值和原注释。当前 domain getter 仅返回保存域，不能把这次修订说成新增 _check；原真正 OC1 调用继续原样。仅此语义形态改写、已报告顶层 imports 和下述 formatter。
3. `src/cloud_edge_robot_arm/vision/worker_runtime.py`：只整理已报告 local imports，`from dataclasses import replace` 属于标准库，在 cloud_edge_robot_arm 本地导入之前按项目 Ruff 分组。不挪出原控制流、不运行整个文件 formatter、不改路由。
4. `tests/test_operational_windows.py`：两报告 local import 块；marker 原真消费过期断言移到共用 VALID@5秒 后、raw.now+=1 同阶段，以 `if category == "marker"` 保护并保留原 frozen/source-change/legacy/assertions。不能用新 owner 或 reset counter 绕过因果检查。cleanup 辅助把 `closed_count` 明确改为 `close_call_count`（初始化及既有所有引用一并改），wrapper 每次进入计数一次再调用原 close，不再依赖 was_closed；exercise 独立要求一次调用及最终 `_closed`。负 counter 原节点保留 UNKNOWN，在 raw.now=0 后增加同 owner 仍 UNKNOWN 且 `_closed` 的原节点内断言；重复 revoke 的既有测试继续要求调用数恰1。其他节点/参数/判定强度不变。

新增计数仅是测试观测，不改变运行时清理行为。没有删除任何边界/负例、延长期限、放宽类型、授权 serialized 描述或修改旧 UTC 行为。

## 有限自动整理及新 delta 证明

本轮明确授权原单写者 **一次** `ruff check --select I --fix`，仅上述四文件；不使用 unsafe-fixes，不使用其他规则 auto-fix。这样采用本项目真实分组，不再手猜 tests/包的 third/first-party。pyproject 的 src=[src,tests]、line-length100、target py312 保留。完整原输出/exit/argv留存；该命令是受限导入修改步骤，不冒充最终全规则 Ruff 验证。

随后明确授权 **一次** `ruff format`，仅原 NEW `operational_windows.py` 和 `tests/test_operational_windows.py`。它用于清除尚未运行 format-check 前的手工排版不确定性；不 formatter 另外八源、旧历史快照或全部仓库。两 NEW 文件可整文件版式变化，但必须证明没有额外语义变化。

保留四阶段字节：R103 frozen before、手工有限修订后、import-sort 后、format 后。授权新 **delta proof 一次**（仅 stdlib 读/AST/tokenize，不 import 产品），复用既有 R103 proof 结论，不重跑旧 proof/四负控/CPU。该证明至少：

- 十源 current 对 R103 freeze 建基；六保护源完全同字节。
- before→手工后 AST 差异严格等于本计划四类修改：新增 MappingProxyType、Expr→Assign且 RHS 原样、marker 原块移位、计数语义校准及原负 counter 节点内 no-revival assertions。其余模块/函数/参数化列表 AST 不变；不是泛化忽略整测试函数。
- import-sort 前后只允许已报告四块与新增 bootstrap import 的排序/分组；每块 import inventory（module/name/alias）守恒，除 bootstrap 明确新增1项。不得跨 scope 移动、删除/合并隐藏其他语句。改变 import 执行顺序是明确授权的整理，不虚称 AST 全相等。
- format 前后 `ast.parse(..., type_comments=True)` 的完整 AST（排除位置）相同；type comments/type_ignores保持，COMMENT token 文本及顺序保持，所有注释/字符串/docstring内容不能丢失。若位置型 type_ignore 仅移动，用内容与附着语句验证，不能静默忽略。
- 保持原32 case 的 AST 节点/参数分母，所有既有 assert 保留（仅上文明确替换计数谓词），两 fixture no-revival/expired消费者断言可逐项定位。最终变更四路径且无其他产品写入。

proof 脚本及原 stdout/stderr/exit留存；证明不通过即停，不通过重跑/扩大 normalize 白名单把结果改绿。formatter 不是修改冻结原件的理由。

## 顺序与预算

ROOT 激活前重验计划双 SHA、27项 pins、十 current+snapshot、R103 freeze/budget、R104 replacement activation、无验证在途。R105 implementation 新目录保存此次 source-before/各阶段/命令原件，不覆盖 R103 implementation。R101 implementation 已存在不是错误；只要求 inherited green 子目录与其精确 basetemp 尚未存在。

实施顺序：前置→四文件手工有限改动→I整理1→两文件formatter1→新delta proof1→全十源Ruff1→原两NEW format-check1→原GREEN1→最终十源冻结/步骤报告→不同作者独审。每条非预期非零立即停，保留真实输出和已消费额度，交下一 Astra；不串行继续或自动 retry。导入整理/formatter按成功 exit0处理，不当 RED。

- 原 RED 总1、remaining0：不重跑，无新增 repro、collect-only 或 CPU 节点。
- 原 R103 scope proof1已用且PASS：复用。新增R105 delta proof额度1，仅本轮有限差异。
- 原 Ruff1已用且exit1；R105新增完整 Ruff额度1，累计最多2，不覆盖旧失败。
- 新增 I自动整理1、NEW两文件formatter1（以前formatter0）。
- 原 format-check0used/1remaining、GREEN0used/1remaining：继承各1，不刷新。
- mypy/compile/额外tests/actual/model/network/renderer/Git/subagents：本轮额度0。

JSON 附 exact argv。GREEN 原命令保持 `tests/test_operational_windows.py tests/test_operational_time_v1.py`、`--basetemp=/tmp/bigsmall-p5-r101-green` 和 R101/implementation/green/junit.xml；不得改为重复单节点前探。新元数据目录不改变继承命令/范围。每条记录开始/结束UTC、cwd、有限env、原stdout/stderr、真实exit及hash，不凭旧结果冒充新成功。

## 验收与实际边界

仅当 delta proof/新 Ruff/继承 format-check/GREEN 全部真实通过，原32 P5 case加原OC1分母按实际 JUnit 唯一节点核对且无跳过替代，十源冻结并由不同作者完成原 R100/R101/R103 全部验收，才可称 P5 软件通过。R105 不降低私有启动/原预算/严格typed/frozen codec/真实marker与supervision/replay拒绝授权/legacy字节要求。

P6 真租约、事务与最终执行闭包仍未实施；P4历史真实前缀不提供可借用句柄。actual/formal仍0，本计划不授权真实运行、完整T12验收或Git。新的发现若越出四文件或要求产品语义修订，先停并规划，不能借本轮自动整理吞掉。

本计划发布后冻结；后续激活只追加绑定收据，不事后改计划原字节。
