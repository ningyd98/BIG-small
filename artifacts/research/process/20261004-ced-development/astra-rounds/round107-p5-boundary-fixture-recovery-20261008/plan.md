# R107：P5 六失败的生产边界与软件夹具恢复

实际 gpt-6-astra；原 GPT-6.1-sol 单写者实施。**PLANNED_PENDING_ROOT_ACTIVATION**。本轮不实施、不产品import、不运行复现/测试/静态/actual/Git。R106以后所有源修改须先由ROOT核对本计划、输入与停止状态。

## 原始事实和五个有限原因

R106 GREEN exit1，2026-10-07T19:35:23.029837→19:36:35.954508Z，32unique=26PASS/6FAIL/0error/skip。原stdout SHA `84281730265a1cfd54af91739c7a5972857367a86edb66f6be375db785bc1500`、JUnit SHA `81e124d39aa23ebf570503ef208d72306e479cd193a29bb5fd1430a8480d29a7`。domain共同启动失败已消失，typed-export节点PASS。不能再把当前六项统称启动失败。

最终freeze `c8443e423606804447cead4e214191d8633d1d9520d06f80543bb0dd0408f39b`、budget `e6a634492da78981978949d8569e2e8cbb960d69f77e15680db1b914d3c8aabd`，十current与snapshot相同，无失败后编辑/在途命令；原五新额度均用1且剩0。完整失败消息、源码读来源与原CPU两DB的只读摘录在diagnosis.json；不复制DB或整批raw。

| 实际失败 | 独立根因与修复性质 |
|---|---|
| UTC-jump及category condition两个FAIL | RobotState.stopped默认False；真实robot_stopped谓词为stopped or estop。两个正例只设置connected=True，FAIL正确。修夹具状态，不改时间门/条件语义。 |
| public from_worker TypeError | 公开WorkerRuntimeSource包含dict，_PENDING membership先触发自动hash，错误类型在明确拒绝前逸出。修错误输入边界，不授予任何公开source权限。 |
| frozen bootstrap MappingProxy TypeError | from_payload虽用_plain构造body，最终canonical(raw)仍编码原MappingProxy。修正规范化比较入口，保留精确比较与legacy字节。 |
| marker registration unavailable | 历史registry绑定旧marker源码f538c6…；当前P5为3fb8c5…；其余五源/asset匹配。拒绝正确，不能更新历史yaml或跳过sources_valid。需要独立且可追溯CPU夹具。 |
| supervision ReplyExpired | 原COMPLETE_PLAN仍以UTC普通TTL≤5s判定，P6尚未迁移。CPU D固定0不代表实际UTC暂停；真实SQL/重建路径耗时已使测试前置失效。保持产品veto，限定该软件节点显式UTC夹具。 |

supervision原DB记录：captured 19:36:11.168823Z；capture commit 12.746208；reserve-plan commit15.157256（年龄3.988433秒），TTL确为5；最终仍PLAN_PENDING、plan_completed_at=null，job21.353796记录BLOCKED_BY_ENV/TTL expired。原栈到complete→_VisualSupervisionCommitRejected→classify→ReplyExpired。失败提交的精确now未落盘，不能补造；结论结合真实阶段、固定D=0的测试源及UTC条件，是有据的源/原件诊断，不仅由18.626秒总耗时推断。

本轮合并该批六项已显露问题，不声称五种原因是同一个产品根因；不趁机处理其他事项。

## 精确范围：三Python文件与三CPU fixture

**A. operational_windows.py，仅from_worker入口。** 在_PENDING membership之前局部导入真实SimulationWorker并判断 `cls is OperationalWindowOwner`、`type(worker) is SimulationWorker`；不符合立即原OperationalTimeError。之后原pending/pop/job/registry/owner流程不变。不能仅把任意TypeError吞为VALID、允许公开描述注册或放松_prepare_startup类型门。原public节点已有不正确source拒绝；同节点可加dict输入同样OperationalTimeError，真实worker/一次消费断言不变。

**B. repositories/event_autonomy/visual_bootstrap.py，仅VisualBootstrapDefinition.from_payload。** 先保存 `normalized = _plain(raw)`，从 `dict(normalized)` 构造会pop/转typed字段的body；最终 `canonical(result.to_payload()) == canonical(normalized)`。normalized必须是解码前未变副本，不能比较已删schema/转datetime的body，不默认补字段/允许extra、不改变_plain规则或canonical全局。现有frozen replay/legacy字节对照/伪新提交拒绝均保留。

**C. tests/test_operational_windows.py。** 两个robot_stopped正例的OnlineEvidenceSnapshot明确使用 `RobotState(connected=True, stopped=True)`，不能全局改默认state或把FAIL也当PASS。保留UTC±1000、本地D+1ns UNKNOWN、原32节点和所有旧断言。

supervision只在原category=supervision节点建立一个局部软件UTC源：实际reserve_supervision_capture成功后取一次当前UTC作为基准（须不早于原claim reserved_at/既有history），在新CPU frame首次构造前建立monkeypatch.context；只替换 `vision.worker_owner.datetime`、`vision.worker_runtime.datetime`、`repositories.event_autonomy.sqlite.datetime` 三个模块的datetime绑定。使用保留标准datetime构造/fromisoformat行为的子类，仅now返回该明确软件时刻；不改全局datetime/系统时钟/其他节点、不patch仓储或verifier返回值。frame首次captured_at取同基准，随后不得重贴旧frame/刷新acquisition；原D来源与所有任务/lease预算不变。临时域涵盖该frame capture→reserve plan→decide5/decide6→complete及原断言，finally恢复。真实SQL、typed decode、current lease/source、UTC≤5门和D门仍执行；明确该节点只测软件逻辑，不能用这种冻结UTC证明wall延迟/实际源资格。既有其他节点继续实UTC路径，不把产品旧UTC veto删掉或扩大TTL。若基准无法满足原顺序即停，不伪造前序时间；采用标准UTC aware datetime值，不能改变isinstance/ISO解析语义。

marker不再调用绑定历史registry的tests.test_marker_association.inputs。新增测试内有限helper，读取下列三个独立夹具，用真实load_marker_registration(expected SHA, root=仓库root)、sources_valid及真实OpenCV associate；沿既有TaskTarget/指令/context构造，同一原marker节点的frozen positive/source-change/legacy digest/过期拒绝全部保留，可明确检查NOT_ADMITTED。只有现有CPU副本的episode/time/frame/id/checksum发生已声明重绑定；原图片/深度/几何不变，不冒称新采集或live实际源。

**新增三个精确路径（本轮计划仅写spec，实施才创建）**：
- `tests/fixtures/p5_marker_source_v1/observation-full.json.gz`
- `tests/fixtures/p5_marker_source_v1/registration.json`
- `tests/fixtures/p5_marker_source_v1/provenance.json`

fixture-spec.json给出完整registry/provenance内容、序列化规则与三输出预计SHA/bytes。gzip展开必须逐字等于原单帧2113847B，SHA `c4067a0cdf272f93afc69d7d33d805ed6290808e3b0ccdc735c8ad60213b12df`；压缩551529B。注册表由原yaml派生，仅独立registration_id与六源的已pin实际hash（其中只有marker源hash不同），DEVELOPMENT_ONLY及asset/layout全部不变；expected_registry SHA来自冻结fixture spec，不在测试中自动刷新接受任意当前源码。JSON可由现有yaml loader读取。manifest清楚旧诊断图像只作CPU软件资产、非新actual/校准/权限。原yaml、原frame和所有批量raw保持。三夹具将进入未来明确路径Git交付，不是完整远端raw包；不能再让新测试依赖未交付大历史目录。

其余七个P5源、OC1实现/测试、真实repo/conditions/marker生产代码、历史配置/asset和所有旧证据字节不变。本轮不改worker_runtime生产逻辑、UTC veto、source binding或条件判定。

## 实施与有限新验证

ROOT重验计划双SHA、有限输入pins、十current+snapshot、原停止预算及无在途命令；新R107 implementation保存before/手工后/导入后/格式后和原命令记录，不覆盖旧round。原27RED、R10592、R10632及所有/tmp/DB原件保留。新green叶与 `/tmp/bigsmall-p5-r107-green` 必须不存在。

实施顺序：三文件有限修订+按spec创建三夹具→一次三Python文件I-only整理→一次仅原NEW windows/tests formatter→一次R107 delta/fixture proof→一次三文件Ruff→一次两NEW format-check→一次32P5 GREEN→最终十源+三夹具freeze/步骤报告→不同作者完整P5独审。

新额度明确为：I-only1、formatter1、delta-proof1、Ruff1、format-check1、GREEN32一轮1。旧额度仍已耗尽；无RED/额外单节点试跑/collect-only/repro/compile/mypy/OC1重跑/actual/model/network/renderer/Git/子代理。

新delta proof只读AST/tokenize/JSON/gzip/hash，不import产品、不重跑旧proof：验证七保护源同字节；产品AST变化仅A/B；测试变化仅两state、局部UTC/marker helpers、原节点相应接入及上述增强，32节点/参数不删减；I整理仅授权import inventory/分组；format前后AST(type_comments=True排除位置)、type-ignore附着、COMMENT文本保持；三个fixture对spec精确SHA，gzip展开原字节、旧yaml/raw/asset不变。新helper不能mock最终verdict/lease/readout或跳消费者，UTC patch严格三模块/一节点且必恢复。任何额外变更/证明失败立即停。

Ruff仅三修改文件，format-check仅原NEW两文件，其他源复用未变SHA对应旧静态。新GREEN全32，因为共享public/codec与common helper皆相关，不能只跑六项把其余默认PASS。60OC1继续复用R105原实际PASS并重新核实OC1实现/测试/config未变，不重跑、不声称新92PASS。每命令保存argv/cwd/真实UTC/有限env/stdout/stderr/exit/hash；任何新失败消耗对应额度并停交Astra，禁止auto retry或删断言。

## 验收边界

公共错误类型明确拒绝、不触发非授权hash路径；frozen codec合法可读且精确round-trip/legacy bytes不变、公有描述不授live；真正condition正例传入满足谓词的状态；marker真实source/asset检查和OpenCV消费者执行但始终DEVELOPMENT_ONLY/NOT_ADMITTED；supervision真实持久提交在明确CPU时钟源下闭合，原5/6与D端点断言保留，UTC实际延迟/系统运行能力不由它背书。新32项须实际全PASS/0error/skip，旧60适用性分开记录。

最终仍需不同作者全P5审查和明确路径Git。P6真实租约/事务/dispatch、R91正常链actual、formal各自未完成；不把软件fixture的成功当真实完整T12。计划冻结后仅追加ROOT激活，不回写计划；新范围或不同失败下一Astra。
