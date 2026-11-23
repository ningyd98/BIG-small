# 毕业答辩归档抓放演示计划

gpt-6.2-astra，2026-11-23，研发基线 bdb8bd415bc94cb431b4229c625eed13e82a1c48

开题第4.3节及毕业计划F要求现场可看的受限抓放演示。现有公开汇总没有逐阶段真实摄像机回放。

## 原始证据与时基

- 按预登记顺序选首例development-01（VISIBLE_POSE，seed 1657582353，episode 8a7766ac134b42d6b9c359110c5694c1，job-db7111f090e84abf），其STRICT审计和独立物理判定均成功。新开发批全体20组，组件5/20、独立物理5/20；演示为单个成功实例，硬件及正式研究认定均未发生。
- 独立审计SHA e400b6dbfa67b61edb5d9487121cdfe36f61ab0c58a1bf3f98fde070f948c80b；archive manifest SHA b1b0eb90c4e96ca6ff51566f35d26ae46bdb865380459c07e76e587d669b117a，begin/end与汇总SHA相符。物理证据7769样本，实测抬升110.276 mm、持稳3.167s、落位稳定9.442s。
- 已在本机读验820对原RGB/观测，320×240、episode和每帧rgb_sha256与manifest一致。790个伺服sample＋7个reference，21处阶段关键帧及before/after两帧；1640个源文件路径/内容哈希对按下列规则聚合为ec1cfdaa37aa44b2917649fbe8e237c7da5d297616aa8802a0037f1b3c24bf4b。物理动作9个，最后先执行step-08-clearance再step-08；目录字典序相反。GRASP和RELEASE的前后关键帧真实保存，其间无这两步自己的servo相机序列。

将component/servo-frames和component/frames递归的全部observation.json与before/after/observation.json合并排序（按路径）；逐观测依次取观测本身和同目录rgb.png。对每个文件将episode根相对路径、TAB、该文件SHA256、LF串接并作UTF8 SHA256。对照manifest字节数/sha及metadata.rgb_sha256；checkpoint取同episode physical-evidence中的独立physics_step/sim_time_s，及audit.actions的start_step/controller_return_step，边界取得RGB的是单独capture，不能假定其时刻等于动作结束。

## 实施与复核

### 只读确认

- [ ] 复核20输入、汇总20组及被选行、freeze/assignment和begin/end/audit/manifest；用manifest校验全部候选图像与元数据，再按计划聚合摘要确认原件。物理步和采集角色都是原始来源，不能用相册路径、模拟回放重绘或墙钟日期代替。原件仅本机读取，零新运行/模型/仿真/设备。

### 选帧并生成

- [ ] 专用可复算脚本，用Pillow导出一个答辩可打开的GIF及轻量JSON来源清单，链接现有论文/答辩演示入口。固定7个有伺服图像的动作按独立审计顺序，每个动作从sample-*按数值序取至多12个等距原索引（包含首尾，不足全取），加入真实before/after及所有21个阶段关键帧。用同episode实测sim_time_s映射到原始逐步物理证据中唯一匹配时间（容许浮点表示误差，要求唯一）；同模拟步各帧retain实际captured_at/采集角色，避免用目录顺序推断执行先后。对应范围逐项对照动作边界，特殊camera-positioned、terminal-stability如实标注。记录并去重同一采集ID/校验和，多视角同一步不同采集单列。

### 观看与校验

- [ ] 画面保留原图全幅/宽高比，可使用最近邻2倍放大，图外加阶段、模拟时间/实际步与批次标签。覆盖移动、下降、抓取前后、抬升、搬运、放置、释放前后、垂直及后续退避和末态；不虚构抓取/释放中间画面。抽选帧按模拟时钟排序，压缩时间仅作浏览，图外明确“真实归档抽帧，非实时录像”；无直接相机覆盖的动作间隔用可读分隔卡标出起止时刻，边界同模拟步不得写成经过时长；禁止插帧/绘制新运动或混入其他期次。清单含每个图像帧及卡片类型、来源相对路径、RGB与metadata SHA、图像ID及采集时间、物理步、动作名、GIF帧时长、导出工具版本与输出SHA。重新打开GIF检查帧数、时长、顺序、尺寸，人工检查首尾/两种退避及抓取和释放缺帧说明；用源图验证渲染图像区域只经历已标明缩放与GIF色表量化。离线冷启动播放、交付链接与哈希核对并记录小结。

## 验收边界

可在本地看到这一成功开发实例的真实相机关键过程，能够按清单逐帧核回来源；同时保留两个无过程相机的间隔和总体5/20分母。若个别原件丢失/错绑/不可唯一定位，记录原始失败后停止该部分并另开Astra，禁止用其它试次替换。输出只含派生动图、清单、复现脚本及必要简报，不分发批量raw，不改变既有论文研究结论。

## 输入指纹

| 文件 | SHA256 |
| --- | --- |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-p1-hard-limit-prefix-resume-20261120/final-batch-summary.json` | `fa9da2498ea14cee38773528db2ae8d4bce52fb0a61c8371a1ebdfd446ebc510` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-p1-hard-limit-prefix-resume-20261120/final-batch-report.md` | `af904b1904bdd1903aee357e025250775230b3f7d9d82228387d39c1c28ac404` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round-graduation-integration-20261123/plan.json` | `d0c577770ea9d464a017ae24d44b913b3d3685f179b6eb3fcebb044c4576d9fc` |
| `docs/开题报告_集成电路工程_20261024.md` | `183c7e64aca750a3f9f4626e29721e4676dd69ebc12c81e02a6d822f915c726c` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-20261118/experiments/results/phase9/p1-live-development-20261119/freeze.json` | `ec0f7b0ab2306c3ff838d5cdbea6ee244a68d0ab6fe42e4780599ae9180b23f4` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-20261118/experiments/results/phase9/p1-live-development-20261119/receipts/development-01.begin.json` | `3fd3e8b2f99e8d8340245aafe680a0b7b594428bfb0ae66959093f610ecf6637` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-20261118/experiments/results/phase9/p1-live-development-20261119/receipts/development-01.end.json` | `ba169431e12e632e00a99b806866071cd425f3eb5afed482a3a0d311fb39dfe8` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-20261118/experiments/results/phase9/p1-live-development-20261119/receipts/development-01.audit.json` | `e400b6dbfa67b61edb5d9487121cdfe36f61ab0c58a1bf3f98fde070f948c80b` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-20261118/experiments/results/phase9/p1-live-development-20261119/receipts/development-01.stdout` | `83b7d6f4ad59e79d9e1e57a7d192edafcc0136a31de29b477ccc51d17d4ec194` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-20261118/experiments/results/phase9/p1-live-development-20261119/verification/development-01-validate.json` | `69f56d105445d6836d13ae4bdd70f8495761b14096e196a78463f1100483703f` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-20261118/experiments/results/phase9/p1-live-development-20261119/native/development-01/evidence-manifest.json` | `b1b0eb90c4e96ca6ff51566f35d26ae46bdb865380459c07e76e587d669b117a` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-20261118/experiments/results/phase9/p1-live-development-20261119/native/development-01/scene-assignment.json` | `9dfc487a0263e24c956a23dd7b40e76cf85ae359d5ae8b97d8984f9c7e1ef8d2` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-20261118/experiments/results/phase9/p1-live-development-20261119/native/development-01/source-hashes.json` | `a0f91d5cd2bdac775d22541522ca9b14f9ab58ba72e02d63a0337ee0c1b4c288` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-20261118/experiments/results/phase9/p1-live-development-20261119/native/development-01/component/episode.json` | `68ec26fb975b81afe40e8d5f456a7bca50eddf25763f3daade6b6c4888b73194` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-20261118/experiments/results/phase9/p1-live-development-20261119/native/development-01/component/physical-evidence.json` | `91ec3e99857e4baf2aed48948cec11117b61dc01454b0413050569b54ab41c89` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-20261118/experiments/results/phase9/p1-live-development-20261119/native/development-01/component/robot-feedback.json` | `d64bb9dab3ab045f8cd2feffe9a3e58346f1c9793b3226cd063ddcc031fdda29` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-20261118/experiments/results/phase9/p1-live-development-20261119/native/development-01/before/observation.json` | `551c6662b4836c713ab10a48db4a54c4cdef960513cb3c6cfa01f071b5b2d408` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-20261118/experiments/results/phase9/p1-live-development-20261119/native/development-01/before/rgb.png` | `1a6c18c0c69ff8f8606688c98ae3eb52c9db87df7b82d26c99dab4162116607a` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-20261118/experiments/results/phase9/p1-live-development-20261119/native/development-01/after/observation.json` | `b82591cb430c1d86c26badcf121016fa35cea3e352feda0ff627bf104e62f6db` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-20261118/experiments/results/phase9/p1-live-development-20261119/native/development-01/after/rgb.png` | `ea6b39bc6bea79b332586df2c65ad4c6406a9c42568f2b05bd140c1e4dbf432d` |
