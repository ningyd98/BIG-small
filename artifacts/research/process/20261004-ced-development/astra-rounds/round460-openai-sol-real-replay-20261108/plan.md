# R460 — 既有真实RGB-D的Sol实际API回放

实际 gpt-6-astra，2026-11-08。用户已明确要求“利用gpt直接继续测试”。本轮仅制定执行计划及冻结输入；规划者没有读取密钥/DB/环境，也没有调用API、engine或服务。HEAD只读核对为 `2ade467fdcb2999f46df30e7973190ab881fdd42`。

## 最小范围

GPU空闲不足且Qwen常驻服务未获中断授权，R439 full继续NOT_RUN。独立云端验证可直接复用既有真实同步原图，不以此放宽完整采集前置。只允许ROOT在本轮implementation写小型一次性回放脚本和报告，不改产品、不新增通用框架/测试、不运行角色探针CLI或物理采集。

固定四个原正例，严格顺序，各最多一次：positive-01黄块、positive-02红块、positive-03红块、positive-04黄块，均放绿色区域。完整原英文指令与路径在plan.json；不能套当前config里的统一red指令，也不根据前次结果挑选替代样本。

## 已核对的真实输入与限制

输入位于 `artifacts/research/process/20261004-qwen-cloud-comparison/inputs/positive-01` 至04。原source为20261003-t3-small-model-optimization/scene-validation；当前输入六个核心文件逐字节等于原cases/<case>/captures/attempt-01，assignment文件hash也吻合。每帧320×240、原UTC时间2026-10-03、完整episode/scene/calibration、RGB/depth hash正确，RGB/depth/instance三pass同physics hash，原120 settle步且sim_time约0.5。非负instance ID均有标签；-1仍为背景不要求虚构label。

逐文件SHA/字节数与当前源码pins共73项在intake/input-pins.json；输入原二进制仍在既有local originals，不复制为新的公开数据集。intake/input-provenance.json明确原capture路径、日期、identity、pass哈希和配对验证；必要原metadata/code副本冻结在intake/source-originals。没有读取其它模型响应、网络配置/密钥文件或扩大历史审计。

这四帧原资产family hash `182fb2bc068ba44de394622f819ae444eb7fbe51df5c5311591a8abb97bf6a08` 对应现仍显式登记的 `mujoco_upright_box_v1`。回放显式选择该历史匹配profile，不能把旧图标成当前v2新采集。当前用户选定的v2/可见标记/顶相机/控制器配置完全不改。本轮只检验旧图上的定位/当前解析grounding兼容，不证明当前机器人几何或抓取成功。

## 执行入口与CPU预检

ROOT创建本轮 `implementation/replay.py`，只编排现有 `resolve_cloud_role`、`freeze_evidence._read_frame`、`probe_rgbd_roles._attempt` 和纯消息/摘要函数。两次入口命令固定为plan.json所列 `--preflight`、`--execute`；不运行pytest或额外probe。CPU预检一次≤60s、0网络/secret/renderer：

1. 复核当前源码/所选四帧pins、配对原件与输入身份。用原_read_frame读四帧，它会核验RGB-D hash/320×240/instance字节长度/三pass；原captured_at、episode、scene和observation_id全保留，不重签、不刷新、不调用实时tracker。
2. 按已提供的非敏感profile元数据检查exact Sol、官方base/path、enabled/config_version1、low/4096、timeout180、retries0。源码source_fingerprints取当前值，并将本轮runner自身SHA另外绑定进回放manifest。不要把历史role/source hash继续当当前资格。
3. 用纯build_visual_messages/compatible_messages及当前参数helper构造预期请求，不调用adapter._post。每帧两张不同的RGB/depth PNG、320×240、normalized_1000、原指令及JSON格式；请求≤128KiB、纯文本UTF-8≤16KiB，不发instance数组/labels、baseline-scene位置或truth。保存hash/大小预检而不伪造HTTP原件。
4. raw输出固定 `cache/research/r460-openai-sol-real-replay-20261108`，已由cache忽略规则排除；必须新目录且可独占创建、余盘≥256MiB，原始总预算64MiB。不得覆盖输入或旧输出。报告中链接/列hash到本地raw，不把完整图/请求/响应自动stage。

CPU预检完成并写报告后，ROOT才通过已授权hidden getpass/PTY把用户已有key注入执行进程内存。不得把值放argv、环境、文件、日志、agent消息或工具可见输入。若安全隐藏输入不可用就停，不降级为echo/readline。可用一次性内存service view：get_profile返回上述非敏感ModelProviderProfile，secret_store仅在内存为该profile_id返回ROOT注入值；不访问现DB、不复制服务secret、不create/update/activate现profile。此仅满足现resolve_cloud_role接口，无产品功能增加。

## 最多四次实际请求

resolve_cloud_role使用profile-a6a0273a17da4934、expected_model_family=`gpt-6.1-sol`、allow_paid=True、image_size(320,240)、normalized_1000、显式历史v1。核对实际settings为official `https://api.openai.com/v1/chat/completions`、reasoning_effort=low、max_completion_tokens4096；禁止temperature/top_p/logprobs/max_tokens/enable_thinking等不兼容字段。保持原禁止redirect语义。

按固定四case调用原 `_attempt`，index=0..3，各一次，串行、零重试。每次InitialPlanningRequest只含原instruction、原observation及普通无truth请求元数据；若scene字段显式设置，updated_at保留原observation时间。直接adapter.plan生成的只是离线draft，绝不进入实时pipeline/worker/Shield执行/skill/dispatch。

复用_attempt保存原始request.raw/response.raw、派生JSON、attempt、actual cost ledger与原frame副本到local-raw目录。不要包裹或重写_post来制造成功；来源校核与真实wire观察分开。既有_attempt的first/warm字段只保留为原adapter标签，本轮总报告必须声明四个不同历史case，不把它当现场cold/warm probe。输入metadata可能保留source=mujoco_camera，那是历史采集来源，不代表此次渲染。

每次完成后核验actual wire summary与预期、两图/来源hash，actual ledger inference计数恰1，并检查parsed、grounded、target_hit、destination_hit。instance真值只在API返回后离线打分，不能反馈prompt/控制。 原_attempt字节保持不动；派生报告另读parsed_json/VisualDecision及observation_evidence，记录REQUEST_MORE_OBSERVATION/NEED_MORE_OBSERVATION或其他sentinel、_reason、实际几何门禁结果。observed_scene非None或grounded=True都不等于动作可执行；任何补观测sentinel/几何拒绝同样停止后续case。即使两mask命中，也只报告静态定位与门禁事实，不宣称机械臂可执行或成功。response中的usage/prompt/completion/reasoning计数按原返回记录，缺项写UNKNOWN，不估算成实测；延迟是完整非流式往返，不能称纯推理或TTFT。

硬额度：最多4个inference POST、0额外model GET；每次timeout180s、输出含reasoning最多4096 tokens，四次completion总上限16384。输入tokens发送前不可精确保证，明确以双图尺寸/文本与wire字节上限约束并事后记录provider usage，不宣称有不存在的总input+output token硬上限或费用精确值。整轮wall≤900s、外层960s、RSS≤2GiB、raw≤64MiB。ROOT在执行进程/外层监督实现这些限制，无需改现产品重试策略。已报告GET200不需重复，也不证明视觉任务可用。

## 失败停止与原件边界

任何CPU前置/hash/身份不符，0请求停止。任何请求HTTP失败、401/429/5xx、timeout、JSON/解析/grounding失败、离线任一hit为false、原件被secret echo保护抑制、summary不一致或预算耗尽，立即停止后续case。保留失败原件和剩余未执行分母，不换图/改prompt/增token/重试；新的失败交下一轮实际Astra。异常日志只保留安全类名/受控原因，不输出header、secret或任意可能回显secret的异常body。原echo保护优先，若不能安全保存raw则标记suppressed，不能伪称原件完整。

完成后写小型 replay-report/step-report：planned4、attempted/completed/failed/unexecuted、每case输入/源码/请求/响应hash与字节数、safe raw路径、实际usage/延迟、offline定位结论、真实HTTP次数；所有新render/physics/dispatch/GPU服务计数0。既有原120步不是本轮步数。即便4个通过，也仅记 RECORDED_INPUT_API_REPLAY_PASS；失败记PARTIAL/FAILED并停止。

**禁止**调用run_probe、发布roles-frozen.json、把report.source伪装fresh mujoco role probe、让can_accept_role_probe授予资格、重跑R439 prepare/full/read、停止Qwen服务或扩大四次额度。formal research=NOT_ACCEPTED，physical_acceptance=false，native UNKNOWN。

## 已知后续缺口

ROOT已指出 `freeze_evidence.verify_role_probe_evidence` 的expected_body仍硬索引旧temperature/num_predict。本轮只使用该模块的_read_frame，不调用或修改这个role验收reader，不将其记为PASS；未来fresh role冻结前必须另行Astra修复。本轮独立原件核对仅验证bytes/hash/current summarize_role_request与离线定位，没有完整role资格结论。

本规划没有实际API调用。执行者按输入适用性核验后可直接推进已授权的四case有界回放，不另造完整研究协议或模型选择实验。
