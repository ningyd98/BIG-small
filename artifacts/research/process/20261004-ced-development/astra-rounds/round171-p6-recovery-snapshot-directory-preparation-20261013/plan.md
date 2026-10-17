# R171：R170 快照目录准备恢复

实际规划者：gpt-6-astra（/root/astra_status_plan）。本计划待 ROOT 复核激活；只恢复元数据准备。

## 问题与证据

ROOT 原工具 41f3f0 实际 exit 1：第一次以 xb 打开 before-local-temporal.py 时，R170 implementation 父目录尚不存在，触发 FileNotFoundError。原精确命令和完整工具 combined 返回保存在 original-failure.json；独立 stdout/stderr 不可得。之前 22 输入、211 保护项和账本检查只可由控制流推断已越过，不能称为完成收据。

本轮独立核对 R170 的 22 项输入全部匹配，并观察两个快照、input-check.json、root-activation.json、r169-disposition.json 均不存在，implementation 目录也不存在。全部 25 项实际输入及完整 SHA256 列于 plan.json。失败原件及旧预算保持原样。

## 唯一恢复动作

ROOT 完整审读本计划及新的动作文本后，仅允许一次 .venv/bin/python 标准库元数据动作（120 秒上限）。先复核 25 项输入、R170 的 22 项输入、原保护清单 211 项，以及两份 R158 账本实际 2 已用 / 13 剩余、t1_green 0/1。不得修改账本。

依 R170 实际 scope/outputs 取路径，要求五个目标和父目录仍不存在。先创建准确的 /home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round170-p6-detached-real-broker-receipt-closure-20261013/implementation，随后独占写入两个 before 快照；快照字节必须与两份已 pin 当前源码一致。再独占写入 R170 三份原定元数据，沿用原 input_check、activation、R169_disposition 结构；详细字段见 plan.json。不得将此次当前快照冒充 R169 失败前快照。

实际输出须读回核对；完整工具返回、结果及步骤报告只保存到本轮列明本地路径，摘要保持简短。新动作失败时保留已产生的部分文件并停止，不重试、不覆盖。旧失败准备已耗用 1/0；本轮只新增一次 ROOT 元数据动作。

## 限定范围与门

只创建一个准确目录、两个快照和三个原 R170 元数据文件；本轮本地激活、输入核查、实际返回、结果、步骤记录路径均在 JSON 明列。不改产品、测试、旧计划、失败原件或状态设计。不执行 R170 作者元数据动作、GREEN、测试、静态检查、AST、产品导入、SQL、probe 或 Git。

R169 patch/metadata 仍 0 已用、未激活，显式 HELD_SUPERSEDED。R170 作者元数据仍 0/1、HELD_PENDING_ROOT_TEXT_GATE；R158 2 已用 / 13 剩余不变，t1_green 0/1 继续等待原门。成功只恢复原 R170 两文件实施授权，不授予 T1/B9 软件通过或 native、actual、formal 验收。

## 验收和停止条件

ROOT 须确认真实输入全部匹配、保护项与账本无变化、两个快照逐字节相同、三份新记录确实由本次成功核查生成。任何新根因、意外存在、漂移或写入失败均保留并停止交回实际 Astra。规划阶段没有实施恢复，也没有执行产品或 Git 命令。
