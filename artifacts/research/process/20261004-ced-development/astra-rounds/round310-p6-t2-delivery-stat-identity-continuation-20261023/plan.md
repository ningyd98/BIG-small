# R310 交付文件身份比较接续计划

**实际模型：gpt-6-astra；状态：仅规划，未执行。**

## 问题与证据

R309 最终清单命令 `416941` exit1 停在 `assert s==p.lstat()`；原失败未记录字段差异，不能声称已捕获当时 atime 变化。独立只读观察 `8e0294` 在新失败回执上发现 atime 改变、mtime/ctime/size/mode 不变，支持读取导致访问时间变化的机制。完整 stat_result 比较将 atime 纳入，属于交付元数据比较错误。输入原件及 SHA256 见 plan.json/input-observation.json。

R309 预检 `9bf87e` 已成功（1127 文件、258656066 字节、6 链接），保持原结果；六项选定运行已由 ROOT 验收结算，本轮不增加运行。

## 唯一修正与固定新增路径

- [ ] ROOT 从冻结失败的 invocation.cmd 取源码，仅将唯一完整 stat 比较替换为 plan.json 的 exact_patch：严格比较 dev、ino、mode、size、mtime_ns、ctime_ns，排除 atime；失败时输出这些字段的真实差异。
- [ ] 原 additional 三路径保留，只追加 R309/final-manifest-failed-actual.json 与 R310/plan.md、plan.json、input-observation.json 四个明确路径。原 D 仍表示 R309；完整目录映射见 JSON。
- [ ] NUL/newline 原表达正确，不修改。保留 O_NOFOLLOW、原始字节及 SHA、六个精确链接的120000原始链接文本、100644普通文件、DB排除、100MiB限制、原聚合本地保留规则。

## 一次接续与验收

- [ ] 前提：ROOT 复核本计划及输入适用，原研发分支/HEAD保持、index空。一次运行修正清单命令，预期 exit0、1134 唯一路径、6链接；命令/实际/manifest/pathspec 全保存在 /tmp，不新增仓库内递归回执。
- [ ] 仅以清单的 NUL 明确路径 stage，逐项核对 stage0、mode、原始 staged blob 字节长度/SHA；链接不跟随目标。任何不符保留实际并停止，不自动再试。
- [ ] 按已有授权提交并推送 research/20261004-continuation，核对本地、上游、远端三个 commit SHA 一致。后续实际回执仍存 /tmp。

本计划不改旧失败、产品、fixture、runner、gate、角色、额度、ignore 或原证据，不重跑成功预检或测试。通过仅表示交付字节一致；历史35DB/90sidecar缺口和研究验收状态不变。本席位只完成文档/source解析核对。
