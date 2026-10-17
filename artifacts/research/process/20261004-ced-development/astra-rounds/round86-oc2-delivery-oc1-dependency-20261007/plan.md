# Astra Round86：OC2 交付补齐已验证 OC1 前置

规划模型 gpt-6-astra，准备实施 gpt-6.1-sol；ROOT最终commit/push。状态 PLAN_ONLY。本计划仅恢复OC2交付静态闭包，不修改产品语义，不执行测试、Git操作或真实实验。

## 真实问题与根因

原件 `t12-sol-handoff-20261007/delivery-oc2/preparation-failure-1.json` 和 `.tool-output.txt` 保存stdin105的AssertionError：`['src/cloud_edge_robot_arm/research/operational_time_v1.py']`。准备器以9个ROOT签收OC2文件构造虚拟候选，在copy/stage/tests前发现R82真实startup-inputs的依赖闭包缺项。原失败不得覆盖或改写为预期成功。实际stdin完整源码已由原执行者从原工具参数逐字转录为 `delivery-oc2/prepare-initial.executed.py`，15748 bytes、134行、SHA256 `94dd92cc55278776d1b4252e80c811d21e0eca5156a7a771749d35b08e8aeb0b`；本代理已完整读取，第105行为 `assert not missing,missing`。旁边provenance明确它来自原tool-call文本，不冒称与执行前落盘文件比较；该原件禁止执行。

原preflight记录交付branch `codex/research-20261007-p1-delivery` 的HEAD/upstream/live远端均 `3daddcc96c1d23e928fb4c9a3d868750b6cc37ec`，worktree clean；原研发HEAD1007、upstream4d40；4d40是交付祖先，1007不是。本轮未重新执行Git，这些状态归属于原收据，恢复前须再次核验。原收据查询嵌套树使用physics/...简写，不能凭空输出断言实际嵌套树clean；真实保护路径仍是 artifacts/research/process/20261004-t7-parallel-local-models-physics/physics/workspace-baseline 与workspace-h3，继续保留其状态。

本代理独立只读读取R82 `test_reset_primary_survives_fa0/app/prefix-originals/startup-inputs.json`：225项inventory。虚拟替换9个ROOT签收文件，其余只读取交付worktree，结果224项字节匹配、仅OC1 runtime缺失、无既存项hash差异。补入下面精确runtime字节后虚拟225项全部匹配，没有读取或pin当前P2源码。完整观察和路径级结果在readonly-observation.json。另按真实准备器AST算法静态重算“225 inventory + OC2九项 + OC1两项 + 原候选测试依赖”的扩展闭包，得到288个文件、missing=0、pin mismatch=0，结果在extended-closure-observation.json；项目外import只作环境依赖记录。此核对没有导入项目、写候选或运行测试，明确不等于消费46个测试。

OC2 `_SOURCE_ROOTS` 显式包含OC1 runtime；`_source_inventory_v1`从这些root递归静态解析项目imports，而原9文件集只是OC2拥有文件，不是全部尚未远端交付的前置。缺失模块本身只import标准库，没有新增项目模块依赖；配套测试仅依赖该OC1模块、pytest与标准库。根因是选择性Git交付漏带已验证OC1前置，不是OC1或OC2软件缺陷；不得删除_SOURCE_ROOTS项或放宽inventory以跳过它。

## 精确允许增量与来源

两份当前源均与OC1 Round59独审 `source-review.json/source_after` 相同：

- `src/cloud_edge_robot_arm/research/operational_time_v1.py`：20734 bytes，SHA256 `b1fa45a96837072d7bcf8cec57d1a7ae01dceeabec0131503b6aee5ab27dd90b`；R79计划也pin同一版本。
- `tests/test_operational_time_v1.py`：24211 bytes，SHA256 `ff226e9a616462c67d74d29931f8f9a7d21548f4f13f93ced64901b263229c0f`；只交付匹配的测试源码，本轮不运行OC1 full suite。

明确附带8个小历史证据，均来自 `astra-repair-execution/OC1/independent-review-round59/`：source-review.md、source-review.json、full60-command.json、full60.stdout.txt、full60.stderr.txt、pins-before-after.json、real-startup-cpu.json、receipt-copy.json。10项合计87004 bytes，逐项精确SHA/bytes、semantic_role见additional-delivery-paths.json；不是目录复制许可。当前runtime/test按CURRENT_EXECUTABLE严格检查，8证据按R81原样证据规则，必须保留字节。原独审PASS_SCOPED_SOFTWARE_OC1、旧60通过和旧CPU receipt属于历史运行，不算本轮新验证、不累计测试分母、不宣称完整OC1审计附件或完整远端复现包。

input-pins.json列出有限输入及SHA，包括原失败/收据、ROOT OC2签收、R82独审、R79计划、上述单个startup-inputs、10项增量与本轮观察；不pin活动P2总表、当前P2五文件或整仓。原始225清单指向的候选文件按观察核对，恢复时保持同一比较规则；不能改为拿当前primary全部src代替候选。

## 恢复步骤

1. 复核本计划与有限pins、ROOT签收9个OC2精确版本、旧OC1 runtime/test pins。重新核验交付HEAD=3dadd、clean和同名远端/upstream、base/1007祖先关系、原研发分支及真实嵌套树保护状态。任何相关漂移先保留证据并回Astra；P2独立活动本身不构成全仓quiet门槛。
2. 保留完整实际准备器、provenance及失败，本轮创建新恢复脚本，不执行或覆盖prepare-initial.executed.py。使用全新且独占的恢复输出目录，不能重复原O.mkdir(exist_ok=False)后覆盖旧收据。保留ROOT acceptance中的sources及len==9不变；单独构造精确import_sources={原9项+本计划2个OC1源码pins}，只有11项。将selected当前文件集合、virtual()选择、dependencies起点、expected pin选择、非导入项old==actual断言以及closure action标签统一使用import_sources；对原225 inventory按原规则严格核对。尤其原第111行 `if s not in sources: assert old==actual` 必须改成只排除这11个显式导入项，否则补runtime后会把新增前置误当parent已存在而二次失败。不得一般化忽略old缺失。8历史证据单独入selected，不加入可执行import集合。R86计划、观察和恢复执行收据按明确小文档路径单列；不更新历史startup-inputs、ROOT签收或OC1 pin。既有OC2已审路径集不因这10项删减或自动扩大。
3. 用原9文件+本计划2个OC1源码构成虚拟候选，再一次静态检查同一225 inventory，必须225/225匹配、missing=0、changed=0；按原准备器所需测试/配置依赖完成扩展288文件静态闭包，missing/mismatch均0，与本轮extended-closure-observation比较。对应test也须校验旧独审hash；复核原静态import闭包逻辑和_SOURCE_ROOTS保留。这里不是执行项目模块或实际启动，不消耗candidate46预算。其他既存依赖按候选原字节严格比较；若出现另一个模块缺失/hash差异，不借本计划复制全目录或忽略错误，保留并回Astra。
4. 通过后逐路径原字节复制到隔离候选并校验来源/目标SHA和mode；整套allowlist、范围内容审阅、无秘密/无未审大原件边界照R77。P2五路径保留交付parent中的既有版本，不导入其primary活动改动；本轮不扫描、pin或提交P2活动总表。old1007不merge/cherry-pick，原raw/DB/脏嵌套不动。
5. 沿既定执行合同在候选只运行一次OC2 candidate46（原预算尚未消耗）；先冻结其确切命令、46唯一case身份、独占输出/临时目录、环境和最终源码pins，验收分母不变。不得顺便重跑old full63、OC1 full60、历史19probe或actual；不以加入OC1测试文件触发全套自动收集。保存启动、stdout/stderr/exit、JUnit、必要startup原件及before/after pins，报告候选实际结果；计划外失败停止依赖行动并回Astra，不消耗重试掩盖失败。
6. 继续R77/R81/R83：精确staged集合/逐blob pins；whole cached check真实exit原样保存；VERBATIM逐项例外且未分类=0，严格当前源码/新文档子集exit0；新文档解析/引用一致。补OC1不是源码风格容错许可，也不改变Git whitespace设置或原件字节。ROOT独立核对实际候选46证据及上述交付闭包后，按用户“做好git整理和推送”及既有授权对同origin/受众/研发branch执行明确non-force push，核验交付branch本地/upstream/live远端三SHA。保留已成功RW1 commit与其收据，新增OC2为后续增量，不amend或覆盖旧成功记录。
7. 生成新步骤报告并汇入阶段总结：原AssertionError、漏带前置原因、精确新增10项/87004B、225静态闭包结果、candidate46实际运行次数和结果、旧OC1证据引用、Git真实状态分别记录。远端软件交付与完整raw/DB归档、真实实验、正式研究保持分层。

## 前置与验收边界

本轮静态观察不执行产品、不运行Git、不消费candidate46、不新增actual。恢复成功需明确前置已补齐且其余依赖约束不变；后续软件验收只有实际candidate46证据及ROOT核对满足才可声称通过。旧OC1原测试支持复用来源身份，不能声称候选本轮重跑OC1全套。

实际运行仍需既有ROOT唯一串行调度、Gate C/D、确切源/配置/asset/lease/worker/clock与完整原始分母条件；本轮actual=0，formal=NOT_ACCEPTED。新缺项、新根因、范围扩张、相关pin漂移或计划外执行失败保留现场并实际Astra下一轮；当前用户Git授权不等于发布完整1007/raw/DB或改动无关P2的授权。
