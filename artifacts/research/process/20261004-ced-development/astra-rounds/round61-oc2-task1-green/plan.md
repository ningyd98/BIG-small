# Astra round61：OC2 Task1 GREEN 与已知静态修复计划

本轮仅修复 round60 Task1 的测试合同和已确证静态问题。任务数 3；不授权 Task2/3、完整 OC2、任何 source-positive 或 actual。规划者只写本目录 plan.md / plan.json，未跑测试或静态工具。

## 原始失败与判定

首次限定 GREEN 为同 40 unique cases：38 passed、2 failed，42.38s，exit 1。两个失败是 test_worker_authority_is_not_counter_descriptor[worker/repository]：tests/test_operational_prefix_v1.py:118 的 RuntimeError-only 断言调用 catalog_entry(:334)，先进入 _live(:172)，因身份替换触发 ValueError("actual private application/repository/worker identity changed")。实际拒绝是正确 fail-closed；未发现此处权限绕过。修测试的具体拒绝合同，不改变 registry 为了适配旧断言。

健康 application 的 catalog_entry 也统一拒绝，故 Task1 stub 不能冒充 tamper 负例。必须以真实健康 check_worker/check_active 对照，加上 registry/assignment/lease/attempt 的具体拒绝原因，证明真正路径先失败。catalog 的普通 Task1 拒绝仅登记零发布阶段边界。

原始 RED 是 40 failed / 0 passed / 0.50s，缺新 module/CLI/policy，为 round60 批准的预期 RED，保留不重跑。作者随后一次窄静态证据：Ruff 31 errors（2 I001、29 E501），format 5 files，Mypy 1 error（operational_prefix_v1.py:326 nullable origin indexing）。本规划仅读这些原证据，没有重新运行。初次默认 sandbox 读取报 bwrap loopback RTM_NEWADDR Operation not permitted，后续用 require_escalated 只读；这是工具执行环境错误，不是产品 counterexample。

## 输入与硬门

已只读复核 59 个原始 protected 输入、7 个当前 Task1 新文件及7份中断 source archive，全数 SHA256 与 bytes 匹配。完整逐项清单固定在 plan.json/input_pins、protected_original_59、task1_current_7、historical_source_archive_7，包含原始 RED/GREEN/static command/stdout/stderr 及报告。此清单不是完整远端复现包。

round60 plan.md SHA256 为 7cabb71aec1c4d485d6505a060ed227b5a810ae71d325e6b4fbc66da41d160b9（22261 bytes）；plan.json 为 5a5c09f32208815e52c37e43ff63b9fde1e188df1244de4e8e4fcecfac34c402（22171 bytes）。本轮继承其 Task1 合同及所有未完成硬门。

Gate A：已记录 OC1 scoped software PASS，实施前复核 pins。Gate B：root dispatch 时唯一 markerfull actual session88431 正在运行，actual + public readout 终态/renderer释放尚未成立。任何 shared worker/teacher/backend/OC1/public source 字节必须不变；本轮即使之后 Gate B 改变也不授予 Task2 写权限。root 负责运行生命周期，规划者不查询/等待/启动 actual。

修改仅在 7 新路径范围内，其中实需编辑 5 个：operational_prefix_schema_v1.py、operational_prefix_v1.py、scripts/run_operational_prefix_v1.py、tests/test_operational_prefix_v1.py、tests/test_operational_prefix_cli_v1.py。operational_capture_v1.py 的 pending stub 和 configs/research/operational_prefix_v1.json 保持原字节。禁止修改 pyproject、旧测试或共享源。

## Task 1：复核输入并修正真实拒绝测试合同

- 实施前复核本计划全部SHA/bytes、59旧pins、7当前新文件及7份中断source archive。保留原40 RED与首轮38 PASS/2 FAIL及静态RED，不覆盖或删除。
- 在原test_worker_authority_is_not_counter_descriptor的7个参数case内，先以真实临时SQLite及原始exact worker做健康check_worker/check_active对照并核对job/lease/attempt。保留descriptor worker/lease UNAVAILABLE断言和descriptor不可授权负例；为descriptor拒绝匹配current exact configured worker/assignment required。
- worker/repository替换后的check_active和catalog_entry必须明确ValueError且消息actual private application/repository/worker identity changed。其余5个catalog case保留RuntimeError并匹配no live operational source-only publication in Task1；该后者仅证明Task1无发布，不计作tamper来源拒绝。严禁统一扩大raises tuple或Exception。
- 其余5个check_active负例匹配实际assignment/origin/lease/attempt拒绝理由，不能被Task2 stub拒绝冒充。已读合同：origin=original live worker task/assignment changed；assignment=original operational assignment changed；cancel=worker job identity/status/lease source invalid；released按真实release_lease路径核对unique live job lease required或其确切上游守卫；duplicate_attempt=unique open job attempt required。不得为适配错误消息修改共享repository/owner。
- 现有copy/deepcopy/pickle case保留不可复制/序列化拒绝并匹配具体消息；在各case用健康exact app的check_worker/check_active对照，再令复制字段的foreign app以exact startup-owned private application required拒绝。不可只测试catalog/execute pending stub。保留no source-positive/catalog0、原始prereg字节与capture未打开断言。
- 目标保持同40个unique node identities，在现有cases内加强断言；如确需增加具体case，预先登记新旧identity及原因并如实报告总数，不将重复运行相加。无需新产品功能或新的Task2测试。

## Task 2：修正已知静态问题并冻结Task1范围

- 仅在operational_prefix_v1.py::check_active将原origin取为局部值后进行真实if origin is None拒绝，再用此已验证局部值返回task_origin；保留原job/origin/worker/assignment/live lease/fencing守卫与错误语义。不得用assert、cast、ignore或默认元组消除nullable诊断。
- 仅对白名单新文件做31个已知Ruff问题涉及的换行及import排序、5文件格式化。逐项复核无行为漂移，不引入noqa/忽略规则、不改pyproject、不抹异常、不改source inventory范围。capture stub与policy字节不需改变。
- 使用原记录的6文件Ruff check/format --check与4source Mypy范围验证；临时cache置/tmp。先完成本轮已知修复与静态验证，再静止源文件并记录after SHA/archive，最后运行一次限定GREEN。若出现新的静态规则/类型根因或计划外失败，保留证据并再次Astra，不继续临时修。

## Task 3：一次限定GREEN、独立复核与分层报告

- 在fresh /tmp basetemp对tests/test_operational_prefix_v1.py和tests/test_operational_prefix_cli_v1.py运行一次最终完整限定suite，保留command/env/exit/wall/stdout/stderr与unique case identities。原RED40fail、首GREEN38/2和最终GREEN分别记账；不得累加为独立分母。
- 复核全部59旧pins、7旧source archive和原始失败logs与规划时一致；记录新文件before/after，现有共享worker/teacher/backend/OC1/public source字节必须不变。CPU temporary SQLite真实接口、OC1 clock owner及borrowed handles不是实际worker dispatch或native authority；区分default CLI零DB与CPU fixture临时DB。
- 保持默认CLI INPUTS_ONLY/NOT_RUN及output/DB/app/clock-owner/backend/model/network构造0；继续使用现有真实子进程audit/import guard测试，不另跑actual或执行真实backend。限定suite内fixture只允许无source事件的raw backend construction seam。
- 给root/独立reviewer提交静止新文件与报告。Review Gate需检查健康对照、具体拒绝原因、零source publication、origin真实guard、静态与suite结果和59pins，不重复已完成OC1 full60或全仓测试。仅可判PASS_SCOPED_SOFTWARE_OC2_TASK1；没有独审通过不得称完整OC2 PASS。
- 执行者在OC2新子目录保存本轮步骤报告与验证原件；root汇入阶段总结，分别记软件、actual0及正式研究未验收。Git提交推送/三方SHA核对由root按既定交付流程另行执行，本规划者不执行Git。

## 验证与验收边界

执行前逐项核对输入，使用现有 .venv，输出日志采用新路径，不覆盖原始失败。只有无事件 CPU raw backend seam、真实临时 SQLite / lease / attempt 接口及 borrowed capture/executor handle；不能将这些称为实际 worker dispatch 或采集。默认 CLI 必须仍为 INPUTS_ONLY / NOT_RUN，output、DB、clock owner、app、backend、model/network 构造均为 0。原 execute_once/check_recorder/catalog 的 fail-closed Task2 未实现状态保留。

最终 suite 一次：

    PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=/tmp/bigsmall-oc2-round61-task1-green tests/test_operational_prefix_v1.py tests/test_operational_prefix_cli_v1.py

窄 static 沿用 plan.json 中原三条 command 的6文件 Ruff check/format与4source Mypy范围，Mypy fresh cache 为 /tmp/bigsmall-oc2-round61-task1-mypy。现有 mypy 配置 unused section note 不升级为产品故障、不改配置消除。先修已知问题、完成窄静态并静止源，再跑一次最终 suite；不重复 full60、全仓或旧 actual。

Review Gate 必须核对真实健康对照、分支特定拒绝原因、保留全部源/权限断言、origin 真实非空守卫、quiet 新源 pins 与前后59原 pins、原失败不变、无源事件/发布。通过最多为 PASS_SCOPED_SOFTWARE_OC2_TASK1；不能推出 full OC2、Task2/3、source prefix complete、native/UTC、九组/G1、正式研究通过。source-positive/catalog/worker dispatch/actual/model/provider/network/physics/renderer/camera/decoder/hardware 均为0；temporary SQLite 的软件测试事实单列。lease clock migration 仍 NOT_DONE_OC3，independent calibration groups=0，geometry/motion UNKNOWN。

之后真实运行必须另行获得 Task2/3 授权并满足 round60 全部门：marker actual/readout终态且renderer释放、OC2软件独审、source archive冻结、无已有recipe actual、fresh exclusive output、Linux BOOTTIME/proc身份及真实资源、仅root唯一执行。此计划不使这些门自动成立。

新增根因、范围扩大、输入漂移、计划外静态/测试失败：保留原始证据，暂停受影响修复，再次 Astra；不得宽 catch、删除断言、改原件、更新expected pins来取绿。步骤报告与阶段总结区分软件、实际与正式研究；root按明确路径处理提交推送与三方SHA核对，完整raw/DB依既有交付边界保留。

## 本轮新源输入 pins

| Path | SHA256 | Bytes |
| --- | --- | ---: |
| src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py | 1f685317445b9ea33285a8008de95d1523c3c643d649fa97b70deba14391d066 | 7225 |
| src/cloud_edge_robot_arm/research/operational_capture_v1.py | f3196dbf95bea00eb3bafcad610f9ff4ca0219b18050f1b8174263e9c8f0faf5 | 231 |
| src/cloud_edge_robot_arm/research/operational_prefix_v1.py | 1ee7fd2d11d5ff1d82b2104f4ce39ebd78ad81450a3361a9fa8fd20da1f5904d | 21223 |
| scripts/run_operational_prefix_v1.py | 2392106378751d99c61257525b30dc39a4ea70404e24bde4d5c5e632efdfa902 | 1743 |
| tests/test_operational_prefix_v1.py | 1bf16bbd1090e7fa7a065a1013961b15f6b44d45dfe5047f55d90e03a4db1d8d | 10118 |
| tests/test_operational_prefix_cli_v1.py | b886e274aa5b7f19ffd3552cda04c02c48bc12307240bf064cff4afa956ca870 | 5704 |
| configs/research/operational_prefix_v1.json | c1d51bb28376f9a2c7e636efe16a0675d426951b8ed8849ead78d342f4b3ada1 | 394 |

全部原始失败、command、archive和59 protected pins参见同目录 plan.json 的完整逐项表。规划执行：源码改动0、suite0、static工具0、DB0、actual0、network0、renderer0、Git0。
