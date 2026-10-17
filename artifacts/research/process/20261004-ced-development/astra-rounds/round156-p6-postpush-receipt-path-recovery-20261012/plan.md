# R156 已推送回执路径的元数据恢复计划

实际来源：gpt-6-astra，/root/astra_status_plan。计划冻结后由ROOT复核激活；规划者不执行恢复reader。

## 问题、原件与独立根因

R155 deliver工具7d8d52实际exit0，记录commit b8ef6e2708e1a9ea28ae4addbe8aeffa066e55d7、本地/上游/live同SHA且clean，848文件/837变更/26,791,130B；28次Git全部耗用。随后独立metadata reader工具d6a509实际exit1，在第一文件read_bytes因错误路径 implementation/postpush-receipt.json 抛FileNotFoundError，后面的Git结果读取循环未到达；没有修改或新Git。

已阅读全文冻结audit-delivery.py：D是R155轮次根，I才是implementation，真实写入为 save(D / 'postpush-receipt.json', final)。据此发现并读取真实R155根回执，其13612B SHA为74fbdbc7bfc5157fcbe045684d3d9b3f61bacd32e8a6978777b8069e645c4e7f。没有执行/导入helper，根因仅reader猜目录，不是产品或Git失效。

original-failure.json保留精确原shell提交与真实combined返回；独立外层stdout/stderr不存在时不编造。actual-delivery-tool-return.json保留成功deliver/manifest/copy/stage/ROOT门的真实返回。原件SHA、helper和旧plan完整SHA见plan.json.inputs。

## 限定输入与schema

五直接输入与36个真实回执引用全部给出完整路径/bytes/SHA。36引用为8个上层元数据关系+28个Git结果；它们来自已pin实际回执，不冒充规划者已完成整套恢复核验。结果JSON再以真实stdout/stderr pin字段绑定56份原流；只沿实际字段，不猜glob或路径。

真实postpush JSON有identity字典、actual_git_results列表28、整型files848/changed_files837/bytes26791130/Git28/remaining0，以及payload_index、delivery_paths、plan、acceptance、staged_receipt、precommit_receipt、unrelated_before/after八个pin字典。先检查类型再读Path；空stderr仍必须核真实SHA，不能跳过。G7未配置exit1、G14历史空白exit2是原计划观察，不能误要求28次全exit0。

旧G15占位标签里的R153为遗留文字；R155 Task3/whitespace.strict_check与已保存实际argv均要求六源码+全部R155派生+三状态。保留冻结文字和650历史空白原件，不补改计划或原日志。

## ROOT实施门与唯一新额度

- [ ] ROOT核五anchor并全文读新 read-postpush-metadata.py，保存script-gate/fullSHA与root-activation；只允许标准库JSON/text/bytes/hash，无subprocess/Git/产品。
- [ ] 单次执行 plan.json.command 的精确.venv命令。读R155根真实postpush，核身份/计数/边界；验证36引用和28结果的56原流。
- [ ] 核G16/G17真实argv/output、最终G1/G4/G6三SHA及G5空status；只证实当时已保存的推送状态，不称新查询远端。
- [ ] 核payload/staged/precommit路径计数与总字节，837+11=848；核before/after100条路径bytes/SHA/mode相等及引用关系。无需重新渲染或读100文档内容，也不重扫完整fixture。
- [ ] 原staged引用的diff/blob/whitespace只可作现存字节pin核对；不得执行Gitcheck或修原件。
- [ ] 独立保存R156 reader.json、实际invocation/stdout/stderr/exit和工具返回，stdout摘要小于1500字。截断时按计划有界读已保存JSON，不重跑。
- [ ] 仅成功后写本地step-report.md/json，记录推送identity及元数据核验。R155提交内Git pending内容为当时as-of，保持原字节；不写STATE/PHASE/docs、不做第二次提交。

本轮reader1次，Git/产品/静态/测试/作者/独审/重试/复制/提交/推送新增额度全部0。所有新输出只限R156，原失败两文件保持。禁止执行旧helper、原错误命令或任何产品AST/import/compile/collect/SQL/probe。

## 验收和停止

成功边界为“既有Stage A bounded software已推送事实的元数据核对”，上限LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO。B9 OPEN，完整P6/B/C/D/native/actual/physics/formal均不提升；CPU正链仍为受控六flags，selected包不等于完整远端raw/DB复现。任一新缺失/类型/hash/原始结果矛盾或reader失败，保存原件后停止交下一actualAstra，不修旧记录使之通过。

