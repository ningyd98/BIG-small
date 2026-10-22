# R308：大体积 case 聚合证据的有限交付计划

实际模型：**gpt-6-astra**。仅交付规划；不执行压缩、测试或Git写入，不阻挡独立wait接续。

## 实物与问题

R307聚合 cases.json **117653675字节**，SHA256 `a5cb9b9c664839eb3fea38fc8a3fb486d51b367f9c2c8cbbb9e1033caa65dfe3`，超过本次普通GitHub100MiB单文件交付边界。九个原始case合计117503638字节，最大17444188字节，各自均低于边界。原文件不存在内容失败；当前行为result是通过候选，ROOT独立验收与wait结算另行记录。

## 限定交付

在所有运行完成/真实结算后，保留原cases.json路径、字节、模式、hash不变，新增同目录 `cases.json.gz` 与 `cases-delivery-manifest.json`。采用stdlib GzipFile：filename为空、mtime=0、level=9，记录真实Python/zlib版本，按固定块流式压缩，不解析重写JSON。

关闭gzip后独立流式解压，与原件逐块逐字节比较并核对长度/SHA；原件及九个case前后hash必须不变，压缩文件实际大小须低于100MiB。这只是交付完整性核对，不是研究验收。

现有 `.gitattributes` 已有 `*.json.gz binary` 与process证据 `-text`。不改属性或Git配置。可在完整归档.gitignore原件后仅新增这一原聚合文件的仓库根锚定精确路径，防止误stage；不得全局忽略JSON或删除原件。

## 明确路径Git与恢复说明

只stage已验证gzip、恢复hash清单、九个原case及本轮计划/报告；原聚合本地保留并排除索引。其他R300–307文件沿ROOT已有明确路径清单交付。DB/batchraw/权重/SDK/凭据继续原边界，不force-add。

验证staged每个blob大小、gzip与九个原case的逐文件hash、清单可读和无未授权文件后commit/push研发分支；记录本地HEAD、upstream、远端分支三个SHA一致。清单写明原件SHA、压缩实测SHA/大小、固定参数和解压恢复方式、逐字节相等验证及九case原件列表。不能称完整远端raw/DB复现包，原35DB/90sidecar缺口不变。

运行仍活动时不做交付变更；source drift、已有输出、压缩/还原失败或size/upload问题保留实物并停止对应交付，不改原件求通过。本轮不新增运行额度、不修改冻结plan/gate或提升任何研发状态。

输入实测pins、精确stage/ignore路径和执行前置见plan.json及input-observation.json。
