# R303：元数据命令显式 Python 接续

实际规划模型：**gpt-6-astra**。仅计划，未执行修订命令。

## 原失败与根因

Sol 原元数据命令裸 `python` 启动失败：chunk a9e9be，exit127，heredoc 未运行。完整原调用和回执保留在 R302/author-input-pin-actual.json。ROOT 同类只读命令 chunk f3ebb8 也 exit127；这是解释器名称解析问题，不是产品或测试失败。

本席位确认绝对 `.venv/bin/python` 存在，解析到 `/usr/bin/python3.12`；三个原输出及新回归测试目前均不存在。输入/解释器 SHA256 与实物观察见 plan.json、input-observation.json。

## 两处限定更正

1. 仅把原调用开头 `python` 换为工作区绝对 `.venv/bin/python`，保持原 heredoc、工作目录和工具参数。
2. 唯一 `handle.write('\n')` 等价明确写为 `handle.write(chr(10))`。实际解码源片段 hex 为 `68616e646c652e777269746528275c6e2729`，原 Python 语义已是 LF；这是消除多层转义歧义，不将其虚构成已发生的无效 JSON 失败。

plan.json 保存完整精确修订 invocation；其他脚本字节不变。旧失败、R302 plan、源和角色均不改。

## 一次执行与接续

ROOT 核对两处差异；实际 Sol 在执行前再次确认三个输出和新回归测试 absent、非symlink，随后仅执行一次修订元数据命令，0 retry。实际调用/返回存 R303/author-input-pin-actual.json，不覆盖旧失败。

预期 exit0；G0测试原件字节/模式一致，manifest/proof 均可正常解析JSON、原输入全匹配。ROOT 一次独立核对后保存本轮 acceptance，直接继续 R302 Gtest→RED→修复→GREEN→dual→两个wait。无新增通用门禁，不重跑旧gates，不因这个命令新生或消费任何测试/运行额度。

若新失败或部分输出，保留现场并暂停相关操作，不删除后重试。验收仅限元数据前置恢复，不宣称RPC/T2通过。R302既有五key、预算和源码审阅流程原样保持。
