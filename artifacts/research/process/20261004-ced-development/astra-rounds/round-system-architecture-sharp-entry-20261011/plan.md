# 架构图 sharp 入口限定修复计划

请求模型 gpt-6-astra；2026-10-11；仅计划未实施。
父代理说明此代理此前为实际gpt-6-astra计划代理。当前子代理没有可信后端模型查询字段，不能独立核实；须由父代理根据实际spawn调度核实模型，未核实前不将此文件作为已验证Astra身份的证据。

## 问题与原始证据

bundled Node运行build_diagram.mjs时，硬编码sharp/lib/index.js缺失，exit1 ERR_MODULE_NOT_FOUND。
- command：/home/ningyd/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node /tmp/bigsmall-system-architecture-20261011/build_diagram.mjs
- exit_code：1
- raw_transcript：/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round-system-architecture-sharp-entry-20261011/raw-failure.txt
- correction：原转录保留：实际moduleResolve为resolve:865:10，转录为860:10；父代理说明，不影响模块缺失根因。
- plan_generation_failure：chunk f47eb2 exit1：本代理计划写入脚本SyntaxError: [ was never closed，发生于解析阶段，未写计划或改输入。恢复限定为修正计划序列化脚本括号，保留此证据；不涉及图导出实现。

## 输入及 SHA256

- `/tmp/bigsmall-system-architecture-20261011/build_diagram.mjs`：`c533081c0a993da069f2f91183b3553fa8396ad227e16536af7172819e2b6611`
- `/tmp/bigsmall-system-architecture-20261011/artifact.md`：`1d4c5bc0dd9f544fef9809f3d1f4ecbbb34407b64db49acfb3c8105a3b3f9882`
- `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261024-opening-application/开题申请_三项正文_20261024_计划至202704.docx`：`8a7168e908bd4761c42e47cba6ea61cce546713785b5bf9aac7afef30efcaf76`
- `/home/ningyd/文档/ChatGPT/BIGsmall/AGENTS.md`：`8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649`
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round-system-architecture-sharp-entry-20261011/raw-failure.txt`：`6cdd791eab7c7c76fe675f14aeb521511e9b327e1be898a1792ed0118a3242f2`
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round-system-architecture-sharp-entry-20261011/inputs.json`：`94752cc98f9d1f834b679806d33400843adf140c7fcf1b19db5f9e54b98e0ea1`
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round-system-architecture-sharp-entry-20261011/build_diagram.frozen.mjs`：`c533081c0a993da069f2f91183b3553fa8396ad227e16536af7172819e2b6611`
- `/home/ningyd/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp/package.json`：`ad4a2535d72eb638053a38867b1abf43c328cd1c1dbae5cf4172d498365a8b97`

## 根因

错误假定sharp私有lib/index.js布局；应使用包公开入口。现有证据不支持安装或升级依赖。
package.json version=0.35.5 main=./dist/index.cjs。
父代理只读require包根成功，require.resolve返回sharp/dist/index.cjs；本代理读取package.json核实，不重跑导出。

## 限定范围

- 仅替换临时图脚本sharp导入：import { createRequire } from node:module；const require=createRequire(import.meta.url)；const sharp=require(bundled node_modules/sharp绝对包根)。
- 不硬编码新dist/index.cjs私有入口；不安装包，不改runtime/skill/产品/原件。
- 初次入口修复保持图结构、文字、节点、箭头起终点语义和所有绘制参数不变。
- 导出后正常视觉微调限于现有图位置、间距、字号及同端点连线路径；不得改变架构事实。每轮保留脚本和图证据。
- 独立Word工作可继续，导出修复须先完成计划和父代理Astra调度核对。

## 实施与验证

- 校验输入与冻结SHA，不覆盖raw-failure、inputs或冻结脚本。
- 完成最小导入替换，diff确认只有公开包入口修正。
- 用指定bundled Node运行生成脚本，记录命令、退出码、stdout/stderr。
- 确认SVG/PNG非空，SVG解析成功且1400×1510/viewBox完整；PNG可解码、宽高为正、等比。按现有192dpi导出核查metadata，允许像素舍入。
- 逐图打开PNG与SVG预览检查中文、箭头、框线、边缘，无缺字/裁切/重叠；必要按限定位置间距字号范围迭代。
- 核实原文字、节点和箭头语义未变，保存输出SHA及步骤报告，汇入阶段总结。

## 验收边界

- bundled Node exit0，SVG/PNG存在且尺寸比例有效，逐图视觉检查通过。
- 云边端事实、专业名称、边缘选型后置和安全闭环语义不变；不宣称真实硬件或正式研究验收。
- 图导出通过、Word插图逐页通过与研究验收分开记录。
- 正常限定视觉迭代属于本轮；新依赖错误、未知导出异常、需装字体或改变架构事实时停止相关修复并交下一轮Astra。

## 前置条件

- node：`/home/ningyd/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node`
- python：`/home/ningyd/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`
- override：`/home/ningyd/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override`
- sharp_root：`/home/ningyd/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp`
- 校验输入SHA与冻结件一致、工作输出目录可写。
- Word必须用bundled Node/Python，渲染用override/soffice与技能根renderer，不用系统LibreOffice。
- 父代理核实实际模型调度身份；本轮未独立确认后端模型。
