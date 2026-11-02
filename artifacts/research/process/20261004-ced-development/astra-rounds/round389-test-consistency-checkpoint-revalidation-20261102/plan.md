# R389 已交付 checkpoint 后测试一致性计划复核

实际规划模型：gpt-6-astra；代理 /root/astra_r389_revalidate；时间 2026-11-02T08:47:55.185332+00:00。

结论：允许在新适用回执与即时运行前置门通过后恢复 R381，随后严格串行 R377 → R378 → R379。合法起点为 `fdb2e94d3d7bc041e7d958f2514a08406fad4668`。本轮仅重新确认适用性，不扩大既有修复、测试次数或验收范围。

## 证据与根因

旧起点 `28ac315c2af8567b377e6e2cc3ee5acb9cda4677` 经用户授权 checkpoint `13579b8ed9face9e90cd6947073ab2101b558e96`、交付收据 `67d02434663fb9cf72aadbb3b743a49a7370f04a`、状态编码行政修正 `fdb2e94d3d7bc041e7d958f2514a08406fad4668` 线性推进。R381 原先按 unexpected-HEAD 门暂停是正确行为。首 checkpoint 的 1125 路径、86570333 字节、924 唯一 blob 逐项重算 SHA256/bytes 并核对 mode/OID/完整 changed path set 均一致；后两提交仅行政路径。此次提交保存既有源码与测试，不能还原成历史 dirty 状态。

R377 56/56、R378 50/50、R379 27/27 原直接 pins 全同。R381 79/80 全同；唯一 closure 变化是 R380 已批准恢复，精确替换为 `9ba4abc106698997d55420a2ef1cb34df39e33b92f7df67f7f78dfd46df8c97c`（316413 字节）。新 diagnostic 合同为 `2862f11f1a142b199503f3a60a4acbec112bd91e3cf8f7c09ceda04e2f386914`（4336 字节），作为 R381 不可改运行输入。R380 最终 review 为 APPROVED_R380_TEST_SCOPE，JSON SHA256 `c90de74e4e2b3877f048deec33c42ec67d6077a083c7cb1562d388c035df83ba`，Markdown SHA256 `c3d830f8903ec5e8aa24e25d35b34a260240afd7b3799bc2fb732d3ec6554e40`。早期 terminal-handoff 的 review_pending 保留，后发独审满足该门，不修改历史。

R386 58+9=67 的 JUnit/result 原件经只读解析，0 fail/error/skip；回执明确新增真实运行0、正式验收false。本轮未重跑，也不升级成全流程、长T3、browser、性能或真实效果通过。

## 限定实施

仅可保存 R381 当前未提交 applicability 原始字节后，追加 R389 plan/audit pins、合法HEAD、R380精确接收值、实际权限和新互斥/前置检查。旧计划、失败输出、已提交 checkpoint 和两历史 gitlink dirty 均不得撤销或重写。

R381 原四阶段不变：真实线程短 RED 60秒、短GREEN60秒、diagnostic/fixture60秒、原commit_close长节点一次600秒；每阶段清理15秒，总墙钟1200秒。保持真实 COMMIT、同线程独立观察连接、原writer关闭和真正closed-connection异常，保留原完整断言。禁止重新跑已通过长节点或整批67项；R381原计划的 shared_short_green 仍必须执行。

完成 R381 证据、独审、清理与writer移交后，R377 原 default600/research300秒、单worker/无retry/总1200秒；R378 300+180秒、总900秒；R379 60+120秒、总600秒。原commands/env及精确scope以绑定plan.json为准。四轮时钟在各自实施门仅启动一次，不借用/延长R380或历史预算；日历跨日不允许改golden、clock或断言。

## 实际前置与停止门

当前 workspace-write、network restricted、.git read-only，不能套用R386历史full-access。单源writer、前轮已终止清理、运行前即时pins、真实accepted prerequisite、完整结果和owned cleanup全部必需；/proc可见性仅当前namespace。浏览器本地服务、Chromium/EGL依旧按R377原门验证；仅原计划允许的启动前环境拒绝可经获准工具升级，行为已运行不准重试。新产品根因/未授权漂移/计划外失败转新实际Astra轮。

本轮没有新增测试配额。R379尚未使用的一次正常push≤60秒及一次精确分支ls-remote≤60秒继续有效，须实际权限允许且证据审查通过；只交付本次新增已验证路径。严禁重纳已checkpoint源码、冻结原件、受保护路径或完整raw/DB/凭据/权重/SDK。没有原生远端收据不得宣称推送/三SHA相等。

## 验收边界与计划动作

本轮验收仅合法HEAD及旧计划适用性；不将计划批准当测试通过。R376原失败、R367 NONCOMPLETION、R382仅准备均保留。后续软件/模拟验证、真实运行、正式研究验收分开记录。

规划只读Git/文件、stdlib hash/JSON/XML并写本目录三文件。一次只读审计使用不存在的python别名退出127，实际Astra改用已有python3完成；无产品导入/测试/网络/信号/Git写，不计测试尝试。完整原始门、输入SHA256、1125-path核验及四原计划命令/预算绑定见 input-audit.json 与 plan.json。
