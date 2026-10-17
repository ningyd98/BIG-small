# R273 — 未执行ROOT门的manifest引用修正

实际 `/root/astra_status_plan` / `gpt-6-astra`；仅计划。原草稿9333B/5afc22cb…尚未执行，不存在实际StopIteration或测试失败。

R268观察45inputs中，R258 plan.json恰有1条，R258 input-observation.json为0条。实际父计划 `inputs.complete_manifest` 明确pin该manifest996699B/8213421c…，与当前字节一致；作者runner598–600已使用同一正确链。

仅ROOT按JSON中的精确旧行→两行替换：先从45inputs取父plan并check，再取其complete_manifest并check。不得fallback/递归搜档/新增authority。其余草稿字节及35missing、90oldabsent、两组12+18DB与新10DB检查全部不变。

先保存完整before/mode/base64及物理pin，CAS修正，再ROOT全文/native/精确差分与SHA复核；原finding和所有计划不覆盖。新计划11输入pins及8项真实静态检查全true；派生after SHA仅静态计算，未写修正源码。

复核后仅可运行R268原已授权一次≤120秒stdlib gate，独占写root-final-input-check.json；准确argv/env在JSON。不执行plugin/runner，不创建角色/预约诊断或更改STATE/PHASE。新增产品/诊断/测试/静态/SQL/Git/验证流水线0，两个原诊断槽仍等后续完整门。冻结后STOP。
