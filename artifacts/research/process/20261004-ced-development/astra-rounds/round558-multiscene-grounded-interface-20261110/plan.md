# R558 Multiscene Interface Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans；父流程内联实施，不增加设计审批。

**Goal:** 固定七案验证真实感知、几何、云端及最终合同接口。

**Architecture:** 独立研究入口复用冻结生产实现；三组独立进程各加载一次模型，逐案新会话。

**Tech Stack:** Python、现有 Molmo/OpenCV/MuJoCo/Sol、pytest。

**Spec:** 本轮 design.md/request.json；实际规划模型 gpt-6-astra。

## 依据与范围

24 项输入大小/SHA256全部核验，完整清单见 plan.json。基线8a8057e7已真实PLANNED，累计4加载/10生成/2付费；本轮是覆盖扩展，不是已发现生产故障。旧CLI固定S01、provider单加载最多8生成，因此只新增研究入口。既有全量docstring失败保留。

新增 scripts/probe_molmo_multiscene.py、tests/test_molmo_multiscene.py、本轮 implementation/launch_multiscene.py；仅可另改指南及本轮预登记/报告。所有既有生产、CLI、模型/SDK/资产/控制器/相机策略/门限冻结。精确接口、预算账本和分类规则见 plan.json 的 contracts。

## 锁定执行

七案参数、顺序及角色逐字沿用design：G1=N01/N02/P01，G2=N03/P02，G3=N04/P03，生成上限8/6/6。静态质量=.08kg、摩擦=1、seed=0；绿RGBA=[.1,.6,.2,1]、N03灰=[.5,.5,.5,1]，其余使用既有palette。禁止随机重采或结果后调参。

每案新session，首次capture前仅一次apply_scene；允许其准备阶段重建/reset，之后只capture，不step/settle/OfflineSceneAdapter。P案supplier使用同session第二capture；N案supplier=None。保留apply_scene原生noise=0，明确区别旧S01的1mm噪声；不叠加深度扰动。场景配置仅用于渲染；在线只传显式任务、RGBD及既有能力元数据，不读实例标签/真值选点。

预登记先固定七行、各案独有request_id和输入SHA。三个worker顺序运行，每组一次独占claim、一次provider；每案一次原pipeline.process，返回其原对象。point代理只计数/存证并返回原BoundPoint，云包装只观察并委托原请求/响应；N案到云入口必须在付费前阻断且判FAIL_CLOUD_GATE_REACHED，绝非PASS。

预算在调用前独占创建并fsync预留记录，失败也占；N每案最多2次point调用，P最多4，付费仅P每案1、每组1。组已claim不可重启，缺失结束记INCOMPLETE。账本写入失败立即停组；安全独立案例可继续，无重试。实际生成数与保守预留数分别报告。

## Task 1：入口及账本 RED→GREEN

- [ ] 按plan.json接口写测试：七行固定分母；未知/重复/遗漏ID；重复组claim、跨案/组超限、预留落盘失败、开始后崩溃；负例云入口拦截不得PASS；原对象返回、同组一provider/逐案新session、初始后禁止reset/step、P同session两帧；无真值入在线参数。
- [ ] 保存预期RED后实现单脚本及薄launcher。launcher先原样调用R545 configure_overlay，再导入研究脚本；不复制/修改运行时。
- [ ] 新测试GREEN及Ruff/diff通过；用无模型的真实MuJoCo setup/capture检查七场景参数可执行，保存检查结果，不据此声称模型成功。

## Task 2：分层验证与一次独立审查

- [ ] 复用现有grounded、revalidation、final_admission、CLI测试覆盖点语法/JSON/云异常/无效深度/绑定漂移/过期/最终合同及缓存；报告为CPU注入，不加入真实七案成功数。新入口测试使用fake依赖，禁止真实网络/GPU。
- [ ] 指南写明noise=0、暂停遮挡、拒绝来源及预算；进行一次新上下文独立实现审查。门通过前实际额度不启动；不新增设计审批轮。

## Task 3：实际执行与交付

- [ ] 重新核对冻结SHA、R545 ABI/原权重/原profile与settings/secret存在性、GPU共享锁及VRAM/RAM/disk。每组主线程加载一次；使用既有资源准入和原始路径，不下载、不打印密钥。
- [ ] 预登记落盘后，依次启动G1/G2/G3三个独立进程。保存每案原始request、RGB/深度/mask、完整native文本/tokenIDs、实际云body/response/usage/model、原pipeline返回与UTC/monotonic计数；不得记录授权headers。进程退出释放模型，下一组重新准入。
- [ ] SHA/大小清单覆盖完整本地raw。汇总严格七行，缺失/错误/未运行均保留，未知或重复记录判汇总无效；P分母3、N分母4。新根因保留证据并交下一轮实际Astra，不当场改生产或阈值。
- [ ] 公开仅代码、预登记元信息和派生报告；raw/DB/凭据/权重仍local ignored。明确路径提交推送并核对本地/上游/远端SHA。

## 前置与验收

CPU用原app .venv及worktree/src的PYTHONPATH；托管工作树写入按需scoped escalation。软件、真实native、真实cloud、实际合同、物理/正式分开报告。P仅原pipeline PLANNED+非空合同+验证及两道门PASS+四定位绑定成立才PASS；N仅原感知/几何真实拒绝且合同空、云入口未到达才PASS，INVALID/异常/预算阻断不算。具体保守分类见JSON。

本计划0实际调用；本轮上限+3加载/+20生成/+3付费，累计7/30/5，0重试/硬件/正式。没有待定接口或额外审批。
