# R430 Horizon 静态修复 Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans inline；本轮仅语义不变的静态修复，无须另询许可。

**Goal:** 清除 R429 的七项 E501 与一项 B905，保持已通过的 84 项行为验证适用。
**Architecture:** 仅修改 `src/cloud_edge_robot_arm/research/native_completion_horizon_originals.py` 中三组字符串的换行和一个相邻对 zip 的显式默认参数；以冻结源 AST 为独立验证依据。
**Tech Stack:** Python ast/hashlib、现有 .venv Ruff/mypy。
**Spec:** R429 原计划及本轮 intake/observation.json；全部输入 SHA256 见 plan.json。

## 原始失败、根因与前置条件

R429 GREEN 原 result.json 记录 returncode=0、source_drift=[]、remaining_live=[]；原 JUnit 为 84 tests、0 errors、0 failures。原 static/1-stdout.log 含七个 E501（原行 48/49/63/69/70/71/73）及一个 B905（原行 311）。format 与 mypy 已通过。失败原文、旧计划、所有 pre-GREEN 冻结源均保留，不改历史检查结论。

根因：相邻 schema 字符串行超过 Ruff 的 100 字符边界；Ruff formatter 不自动拆分此类字符串。`zip(seqs, seqs[1:])` 有意检查相邻顺序，长度 N/N−1 不同，缺显式 `strict=False` 违反 B905；改为 strict=True 会改变正确语义，禁止。源码该表达式使用内建 zip，没有局部覆盖。

实施前核对 plan.json 的全部 pins、R429 四文件 pre-GREEN snapshot 与 manifest 一致、当前工作区四文件仍为原 GREEN preimage；HEAD 应为 aecf1fd836ff08819edb053a2e87b4b2a83235b0，分支 research/20261004-continuation。不重跑 baseline，不处理既有 dirty gitlinks。执行只用现有 .venv 或 /usr/bin/python3，不安装依赖。

R429 验证选项裁定确认：原正文“既有 59 项”是目标；实际 wrapper 包含 metric10、originals35、calibration10、四个旧负例，合计 59，再加新25=84。原 plan.json 漏列后14项是执行前选项歧义，已有裁定，不修改旧计划。

## Task 1：严格等价修复并验证

- [ ] 在唯一允许的源码文件中，把 `_RECIPE`、`_PREREG`、`_RAW` 七处长字符串拆为相邻字面量；保留每个字符、空格、顺序和 `.split()` 调用。无需改 `_SIDE` 或其他字段。
- [ ] 仅把原 `zip(seqs, seqs[1:])` 改为 `zip(seqs, seqs[1:], strict=False)`，允许围绕该表达式做 formatter 所需换行。不修改后面已有独立 actuator zip、比较条件、错误字符串或结果字段。
- [ ] 新建本轮 `implementation/verify_ast_equivalence.py`。从已固定 SHA 的 R429 `implementation/pre-green-source-originals/<source>` 和当前源码各 ast.parse；必须找到且仅找到这个精确形状的内建 zip：参数 Name(seqs)、Subscript(Name(seqs), Slice(lower=1, upper=None, step=None))，无额外实参。旧调用没有 keyword；新调用仅一个 keyword strict=Constant(False)。记录该唯一允许差异，再仅在新 AST 的此节点去掉该 keyword，比较 ast.dump(include_attributes=False) 完全相同。不得全局移除所有 strict=False，不得归一化字符串、条件、其他常量或类型。新旧 AST 其余字节值等价（相邻 literal 被 parser 合并）必须成立；另三文件 SHA 必须原样。
- [ ] 等价报告保留 old/new 源 SHA、snapshot SHA、目标节点形状、唯一差异计数=1、AST before/after digest 与 equality=true、其余三文件哈希。禁止替换冻结 preimage、忽略任何额外 AST 差异。此证明不依赖导入被测模块，且 built-in zip 默认 strict=False，故无新的 runtime RED/GREEN 循环。
- [ ] 在本轮全新 validation/static 目录分别执行 plan.json 三条原 argv（Ruff check 四文件、Ruff format --check 四文件、mypy --follow-imports=silent 两源文件），各一次、固定 timeout_s=60，保留 argv/cwd/env 摘要、stdout/stderr/返回码与 post-pins。全部必须 0。若需格式化，仅在上述限定区域手动保持 formatter 样式，或对允许源码运行 Ruff format 后用 diff+AST 检查严格限定差异；不得批量自动修复、使用 unsafe-fixes 或改配置。

## Review focus 与验收

逐项关注：字符串边界是否漏空格（AST 捕获）；strict 是否误为 True（精确节点检查）；是否误改第二个 zip（完整 AST 捕获）；是否覆盖旧原件（前置与后置 SHA）；是否借静态通过升级真实资格（报告固定边界）。这些均由上述步骤直接验证。

软件完成条件是精确 AST 等价、其余三文件原 SHA、三项聚焦静态检查全通过；R429 的 84 PASS 记为原 preimage 的运行证据，经此次受限等价检查延续，不声称新运行了 84 项。真实 full-H producer、COMMAND D 支持、原 deadline/hard-stop pre/post 执行、独立校准与正式 native 资格继续 NOT_STARTED/UNKNOWN；不开展模型、网络、硬件或 MuJoCo 实跑。

任何额外 AST 差异、pin 漂移、新 lint/type/format 失败、超时或运行异常都属于计划外失败：停止相关修复、保留原证据，交下一轮 Astra，不自动重试或扩大测试。允许新增本轮 implementation/validation/步骤报告/阶段总结。实施者完成后按已授权明确路径提交并推送研发分支，核对 local/upstream/remote SHA；本 planner 不执行修复、测试或 Git 操作。
