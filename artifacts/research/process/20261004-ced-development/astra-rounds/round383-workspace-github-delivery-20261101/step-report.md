# R383 当前工作区 GitHub checkpoint 交付

用户授权：整理当前工作区，提交到 GitHub。沿用 `research/20261004-continuation`，不合并 main、不创建 PR。交付起点 HEAD `28ac315c2af8567b377e6e2cc3ee5acb9cda4677`，实时远端起点 `dd9df375e1d372490145327bcbfee5804352fcc4`；两个既有本地提交同时交付。

本轮接收既有三份 src/tests 修改与四份新测试，未进一步改写产品或测试字节。现有最终演示文稿已在 output/pptx 受版本控制；三份 build 候选与已交付终稿逐字节一致，其余中间稿和渲染保持本地。

## 软件验证与原始失败

- R383 temporal 原轮 58 项：33 PASS、25 FAIL，全部失败来自准备脚本遗漏 resources-a 目录。原 stdout、JUnit、回执和错误字段 accepted=null 原样保留，不倒写通过。
- R384 修正前置目录和 accepted_prerequisite 字段的行政计划；执行器中文路径序列化替换失效，被启动前安全门阻止。未创建 verification 目录、未启动测试。原 native stdout/stderr 保留。
- R385 原分类器对 pytest 生成符号链接的无条件拒绝已按实际 Astra 新计划处理：新副本按节点类型分类，原副本冻结。600 个精确链接仅 lstat/readlink 指纹，未读取目标载荷。
- R386 独立新目录/新预算：temporal 58 PASS（16.341 秒外层）、fixture/diagnostic/shared smoke 9 PASS（5.215 秒外层）。两组均0失败/错误/跳过，accepted_prerequisite=true，源不漂移、进程已回收、无剩余进程/异常信号/取消。仅限定 CPU 软件回归；没有重跑全仓、长 T3、UTC、浏览器、模型或真实运行。

## 交付边界

初始 21480 节点=20878 普通文件+600 生成链接+2 历史 gitlink。R385 manifest 对每项记录选择、理由、大小和适用节点指纹：941 个普通文件精选，73217509 字节；其余 19937 个普通文件 2096958545 字节、600 个链接及2个 gitlink 均留本地。新生成的行政计划、原始校验失败、回归回执和交付审计单独纳入新文件清单。

完整批量 raw、运行 DB/WAL/SHM、模型权重、SDK、凭据、重复 runtime/source 快照、临时浏览器输出和可再生渲染不新增入库。既有 .gitignore 范围内的数据及两个嵌套工作区内容未递归盘点。本地原件、链接与历史缺失状态均保留；没有 reset/clean、覆盖原实验字节或修改 tracked .gitignore。经审查的生成物可用精确本地 .git/info/exclude 管理，并保存前后哈希和规则；两个 gitlink dirty 保留可见。

初始完整 inventory/status 以验证解压后字节相等的 gzip 副本交付；分类清单和小报告不等于 raw 载荷，不是完整远端复现包。部分历史证据及测试仍绑定本机绝对路径，迁移云端需另做运行环境和输入适用性复核。

## 研发状态

R367 旧 UTC 双 backend NONCOMPLETION 保留；R376 原五长节点4通过、commit_close FAIL 保留，R381线程归属方案未实施。R380仅其既有诊断恢复范围通过。R377/378/379仍待执行，R382仅浏览器准备证据隔离，不能称 browser PASS。新增真实运行0、正式研究验收无升级。

本轮所有行政异常均先交实际 gpt-6-astra 生成 R384/R385/R386 计划后实施；原失败所在文件/会话工具记录的边界写入各计划，不重造缺失的原生错误文件。完成阶段详见 phase-summary.md、R385/preflight/classification-summary.json 与 R386/verification-summary.json。Git提交、推送原输出和三方完整 SHA 将以独立收据记录，不反复amend记录自身提交号。

## 2026-11-02 对象库恢复与最终审查

后续stage字节读取发现Git空对象；先由实际Astra制定R387，再保全110节点、精确恢复59blob。完整fsck退出0，HEAD/refs/reflogs/index及源码/67项证据均不变；50非可达OID与1临时节点只保全隔离，产生原因UNKNOWN。步骤、原生结果与私有保全边界见R387。

独立最终审查Critical/Important/Minor均0，七项未裁定范围逐项记录于review/rulings.md。完整差异检查的20份冻结日志/补丁空白告警按原hash保留；含告警内容的新原生检查输出同样原样留存，最终审计分别核验新编写文件与冻结输出。完整reachability输出留本地并公布hash，不冒充完整远端运行输入。

## 实际首次交付

1125路径/86570333字节的checkpoint 13579b8ed9face9e90cd6947073ab2101b558e96 已正常推送，HEAD/上游/实时远端三SHA相同。final-precommit-audit、精确index-byte-manifest及提交/推送原始输出保存在delivery/；源码与67项证据保持。后续仅小型交付收据入库，最终自身SHA保存在外部私有回执及用户答复。
