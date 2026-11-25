# G1 偏移签发资格入口与原时刻冷读补充计划

计划模型 `gpt-6.2-astra`，基线 `40f9cf2da56e7c8e4f4c5ea33dc28c8a3ae4c5d6`。

## 问题、失败证据及边界

首代 run-01 在独立资格摆放分别用 0/+7 mm 签出八项开发目标，实测零物理步。binding_probe.acquire_controls 实例化底层 Episode，直接调用 check_shield，PRE 审计原拒因为 STEP_TIMEOUT / PHYSICS_STEP_INVALID。直接调用 sample 产生的数据含已拒 Shield；真实 FEEDBACK 回调与控制器样本资格尚未获得，两次 reader 都在 live OpenCVTargetTracker 启动时以 capture_time_not_fresh 退出。read-input、两份 audit、两份 failure.log、两份 frame-index 及真实读者和运行源码逐件 SHA 见 JSON。零步位置预览、真实 PRE、控制器 FEEDBACK、实际八项派发、物理抓放须逐项计数。

## 假设与有限修改

资格工具使用错误入口，并在离线计分时把封存帧送进要求当前时间的 live 跟踪器。分开修正在线资格调用、离线证据时间语义，不改 owner、Shield、控制器、动作时钟、相机/阈值、原计分条件及原始帧字节。在本轮独立目录添加薄资格入口、归档读取适配、测试、步骤报告；构建新的有哈希代与独立 run 目录供原生资格，旧 run-01 只读。在线保持 live tracker 精确类型和原时钟，归档类只在独立 reader 进程导入。实跑前校验所有父 SHA、read-input 各条、frame-index 所有包、已锁源码清单，缺件/不匹配保留原拒因；新根因复报 Astra。

## 第一步　红测与零移动 PRE

先重现/锁定 run-01 原生拒因及冷读堆栈。使用新代资格摆放（原 130 mm 已登记资格姿态，独立于两个新槽和正式名额），每个偏移独立新身份、lease/worker、原任务及原步序和物理步时基。通过原 capture/owner/bootstrap 的有据零步阶段建立 retained stage_source、原始相机身份和登记跟踪；任何启动入口若本身会进步或发运动，改用真实静态原生采集/登记创建 handoff，记录来源及同一步/episode/frame/校验和，禁止写假时钟或假登记。通过真实 BoundAttempt.select、issue_step、GuardedClockEpisode.admission(PRE)→原 SafetyShield，实测 origin/absolute/relative、绑定、条件 PASS/原因、allowed/unmodified、回执与期限。核对正控 0 与 +7 mm 在原 _DOWNWARD 下从原像素→完整 R·δ→签发 target→实际送给 Shield 的参数一致；合成 CLEAR 仅是独立资格刺激，标记源与有效期需真实。零命令基础上只申报可达的真实第一 PRE；后续各阶段可独立重算准备目标/独立条件，禁止虚构前置抓持或确认。

## 第二步　负控、原窗与真实回调边界

同资格接口验证五个负控并记录原错误和命令/步数：未登记候选、跨帧表、同一尝试再次选择不同偏移、运行中替换姿态、替换实测端点。另验错身份/错代/过期时 fail closed，以及原时钟 FEEDBACK-before-dispatch/POST-before-return 拒绝。身份测试必须走原验证入口；各独立阶段如需真实合法状态/实际推进才能正测，明确未到达。仅遇到真实派发、步推进、返回才能记录相应回调；禁止手动 clock.dispatch、模拟 executor 回执、填反馈计数或假装控制回调。零移动资格诊断可在禁止写命令/步进前提下调用原取样、标定、原 IK 纯计算函数一次，记录实测 perf_counter 起止及 capture+sample+IK 合计与 100 ms 原窗，另列端到端原窗口径与实际可观察的组件，其它未实测列缺项。monitor_hold/失败分支可能写 hold，不可从此产生“零移动”的假证。如果原窗真实超时，保留原样本与耗时/拒因，不通过重复或拆小冒充合格；PRE 未获准也不得用随后强取样本作正控。保存进程冷/暖状态、UTC/单调时钟来源、所有真实操作、纳秒/毫秒和步数，并核零物理步与零运动命令。

## 第三步　原时刻冷读

保存同步真实取得的每个初始化、样本读取及登记签发 UTC（如 last_binding_evaluated_at、tracker_evaluated_at、binding_now）与其 event 身份、帧、SHA、角色、lease。先审 run-01 已存戳与操作是否一一对应；若某操作缺精确原戳，仅当实际签发/读取时刻及因果身份有审计支持且满足整个新鲜窗口时才重算该项，否则标缺失并在独立资格代实测补录。禁止以 captured_at 自证读取时间、任选界内时间、当前墙钟替换原时刻，或 mock live 时钟。冷进程验证完整封存链后，用原 collection_bootstrap_evidence 与 _ArchivedTargetTracker(...,evaluated_at=原时刻) 及对应原始事实读取/图像算子复算。当一个算子需要逐次新鲜性检查时用该次经核验原戳；若原 measure_servo_region 对跟踪器有额外类型/时间依赖，保留原像素计算与身份约束，限定归档适配，在线代码冻结。各时间须 aware UTC、有证据归属、capture≤read/issue<expiry；缺失、错帧、超窗/错误时区及 SHA 不符均为反控。复核相同绑定贯穿 SQLite、签发原参数、中央 TCP 与偏移端点、原评分 PRE 以及实际可得的 servo 样本，不制造预期命令、条件或接触。

## 验证、实际前置与验收

核对冻结 runtime-source、EGL/MuJoCo 资格环境、真实资格身份、原生标记和新鲜 RGB-D、完整写入的新代存储、原 lease、100 ms 与技能/任务时限。红绿测试及独立真实资格均列出每个偏移在签发/真实 PRE/SafetyShield、资格刺激、原可用样本与 IK、五负控、实际回调、物理步和命令的分母/拒因。封存后两个独立新进程重读同一代逐项一致，称量/签发目标仅算其见证范围；原拒因和缺失字段回填为解释，绝不改原件。报告软件验证、独立资格和物理抓放分别成立到哪一层。两前瞻槽均无重采、无动作、无新 claim；正式新增零。只有其他任务的真实当前帧可执行 CLEAR、签发/时窗/全门、原监护全通过，才有父轮授权评估实际派发；本轮两正控与冷读自身均不授权动作。按项目规则提交步骤证据及 SHA 交付。

完整输入路径和逐件 SHA256 见同目录 `plan.json`。
