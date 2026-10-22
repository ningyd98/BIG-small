# R329：冻结最后一次 observer 独立审阅 reader

> 实际模型 gpt-6-astra。仅规划与只读 metadata reader 制作；无产品/测试/SQL运行。

## 原始失败与本轮范围

R319/reviews/fresh-observer-review/batch-03-receipt.json 保存 eb7534 exit1：160,039 UTF8字节超过39,000，展示前失败、coverage0。根因是直接序列化完整 invocation/prerequisite/resource 嵌套容器。旧第1定位失败和第3护栏失败均保留 SPENT；仅第2 source325行实际覆盖。

本轮不新增额度：R319.fresh_observer_review 仍4总/3SPENT/1剩余。最后一次合并三run证据、全部15条历史overlay/7raw分母，以及原延后控制流源码。独立seat必须真正读取输出并判断，计划不能替代覆盖或 verdict。

## 已冻结的精确执行物

- `review-reader.py`：完整只读 reader，SHA/bytes见 plan.json。
- `review-command.json`：唯一exec_command调用及reader pin；不得现场另写selector或打印完整容器。
- `input-observation.json`：失败、冻结输入、测量和边界。

ROOT先复核这些pins及全部输入仍适用，再由同一actual fresh seat执行原第4次。完整命令由review-command.json给出，使用绝对 /usr/bin/python3、-B、PYTHONDONTWRITEBYTECODE=1。不要在独立seat中预运行一次再正式运行；每次尝试都计费。

## reader 保留的核对

1. **三次运行完整程序性核验。** 从已冻结R325验收模板只取accept字典前的只读条件，移除save/full/check定义，按各key及已批准可选kind校验派生。逐项检查实际argv/env与命令、initial/中间poll/独立completion、真实native、JUnit、source-before/after/gate、raw/index常规文件及链接、DB/archive/sidecar存在性、资源/case/prerequisite及恢复条件。原RED两测试源码旧pin专门匹配before原件/base64及archive，并核对当前after；其余sourcepins必须当前精确相同，不假称RED所有源码仍current。
2. **展示精确有限字段。** 每run展示原native chunk/exit/短output JSON、actualargs/childargs/env SHA及matched、JUnit、源pin数量、文件/DB数量、cleanup、原unknown/errors。真实两run展示计数、session状态、normal-poll短数组、delegate/callback、异常、restoration与prerequisite必要标量。unit按原0poll/0case/0DB分支处理。完整容器只以去重原件path/bytes/SHA引用，721次程序性pin核对的完整表以确定性SHA和行数锚定；原gate/result/index仍保留完整登记项。
3. **全部15历史行。** 独立重读7raw，重算5708/5693/5708；逐行核对session/worker/normalpoll/ownedthreads原对象逐字结构相等、唯一ID链接、正常return/cleanup，以及source-before/after相等和source_generation原pin归属。展示全部15行命令、PID/IDs、真假/null、原pin引用和无原return trace。overlay仍原PROPOSAL_PENDING_INDEPENDENT_REVIEW；15推断/5708解释值不改旧5693、不能假称原显式constructor-return trace。
4. **源码控制流。** 打印原lease416–460、913–947及worker146–180、235–240，共121行；请求范围内lease948为空行，明确省略展示，完整源码bytes/hash仍核对。原工厂返回后安装session的推断由独立reviewer判定。

## 实测输出与前置

规划席位只读预构造最终payload，未向fresh展示：**121源码行、27,808总UTF8字节、errors=[]、3run、15overlay、65去重引用、721次pin核对**。真实无嵌套大容器。reader在print前对完整header+body强制≤28,000（严于39,000硬限）且≤600行，任何失败仍耗最后一次。各输入SHA冻结，不能以删掉错误行凑大小。原生stdout原件保留。

- [ ] ROOT核对plan/reader/command与输入pins、原桶used3/remaining1和实际独立身份，不重写旧release/失败。
- [ ] fresh仅执行review-command.json一次，原R319 review目录保存batch-04-receipt.json完整args/actual、reader SHA、实际输出计数/覆盖和总used4。
- [ ] fresh对显示的真实值和121源码行作独立Spec/Quality双判断，保存报告。若有reader errors、未覆盖项、输出拒绝或证据仍不足，明确remaining并保持Incomplete；不自动新增额度或通过。

本轮没有新runtime/test/SQL/source修复权限，不覆盖任何原实验字节或ledger，不重跑三run/原七节点。旧35DB/90sidecar与SIGSEGV因果未知保持。整体T2仍以实际独立review和ROOT结果为准，不能由规划预判。
