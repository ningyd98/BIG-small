# R301：Git 状态显示选择器的最小恢复计划

实际规划模型：**gpt-6-astra**。本轮仅生成计划；未实施、未执行 gate、测试、模型、物理或 Git 写入。

## 问题与证据

R300 applicability 首次执行 exit 1（chunk `a4045e`），报两个已知子仓中的 ` M .../workspace-baseline` 未授权。原脚本 SHA256 `4dad0219bdb5d7e0fef3bfae013d8430dc0b3b7999c2eadce48404479a71bba4`，原失败、全文和 review 全部保留。

本席位实测：`git status --porcelain=v1` 与同命令加 `-z` 都是 ` M`；`git status --short` 才是冻结快照中的 ` m`。两个 gitlink 的只读差异均仅为相同 commit 的 `-dirty`。因此问题是显示模式选择错误，**只去掉 -z 无效**；不将所有 M 归一成 m。

输入 SHA256、真实状态输出、原 65 pins 均列于 plan.json 和 input-observation.json。原 R300 snapshot 字段名 status_porcelain 不改写，按实际 short 语义使用。

## 限定实施

ROOT 可以直接准备本 ROOT metadata 检查器，无需新增规划轮。原失败脚本保持原样，在本 R301 目录独占写入 `root-continuation-metadata.py`。plan.json 给出七个精确单次文本替换；先检查原文件 SHA、每段出现恰一次，内存全部替换通过后一次写新文件。

这些替换只做三类事情：

1. 核心修复：状态读取改为 `git status --short` 后 splitlines，保持原两个完整字符串精确匹配。
2. 新世代衔接：新增 R301 目录常量、source-review/执行 argv 和 R301 plan pin；只将这个明确目录加入原未跟踪 metadata 路径允许范围。
3. 留证：新实际回执/失败写 R301；成功 applicability 增加 R301 的 plan、observation、新脚本、review pins。原 failed source/review/回执不覆盖。

不改 65/30/27/211 检查、context、原命令、旧 68 容器边界、角色预算或所有其他判断。不得用旧失败脚本再执行 applicability 或 publish。

## 一次恢复与原链衔接

ROOT 完整检查新源码差异与真实准备回执，创建本目录 `source-review.json`；schema、精确 argv 已在 plan.json。随后新 applicability 仅一次、120 秒、0 retry，actual 放本目录 `applicability-actual.json`。

成功输出仍独占写入原先不存在的 **R300/applicability.json**，保留 `R300_CONTINUATION_APPLICABLE_NO_RUNTIME_RELEASE` schema。这是原下游预留输出槽，不是覆盖旧失败或假称原执行成功。新失败写 R301，原全范围 exit 1 永久保留。

ROOT 依据新实际 exit 0、完整检查及 pins 接受后，继续原 R300 的 R298 metadata 放行，再用同一修订检查器执行原先尚未执行的 publish-gates。publication 仍写原四个路径，源 review/新实际在 R301；不新增一层 gate 框架或 publication 额度。R296 helper、prerequisite SHA、真实 Sol 绑定和原一次诊断均原样沿用。

## 前提、停止与验收边界

HEAD、源字节、绑定、原两个子仓状态和输出不存在条件须仍满足。R300 原三个槽 spent 不恢复，两个 wait 不复跑；R296 仍 used 0 / remaining 1，600 秒 child / 900 秒 outer / 0 retry。35 原 DB / 90 sidecar 缺口保留。

新检查器任何非预期失败，保留证据并停止受影响链，不循环重试。只读源码与 JSON/哈希核对后的一次 applicability 是本轮唯一新增执行授权；后续 R298、publication、roles、diagnostic 仍来自原 R300/旧计划额度。元数据成功不等于 RPC 修复或 T2 验收。
