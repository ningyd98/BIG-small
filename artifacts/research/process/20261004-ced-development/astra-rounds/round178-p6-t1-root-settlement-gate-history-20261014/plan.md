# R178 — ROOT 结算门与脚本历史 pin 处置

实际规划者：gpt-6-astra（/root/astra_status_plan），2026-10-14。只规划；待 ROOT 激活。

## 判定

确认是预执行元数据时序缺口，并非实际命令或pytest失败。旧307输入同时包含旧script-gate.json（25998B/265e177f…）和旧root-settlement.py（17203B/2cd6f8a4…）。本次合法批准门和限定修正脚本会改变这两项；其余305项仍须对当前文件逐一严格核对。原307、invocation及post原字节不改。

独立595项核查全匹配，包括当前24源、211保护、完整旧307及两角色最新账本。原R175实际7PASS、28次Memory初始化/关闭、零错误的原件保留；结算仍未执行。完整输入SHA与集合在已钉住input-observation.json，JSON计划给出准确引用和边界。

## 最小修正与准确提案

仅ROOT修改其root-settlement.py的门读取、历史双记录比对与最终复核/收据块。Sol脚本、helper、产品和测试不动。

1. 修改前独占保存before-script-gate.json与before-root-settlement.py，字节必须同时等于原finding base64、旧307和invocation的对应记录。原gate及source精确SHA在JSON，不从改后文件反造before。
2. 新script-gate仅增加commands.ROOT_settlement_metadata；原顶层值及原preparation条目的原JSON值字节/解析值均保持。新条目包含真实修后source_pin、精确两项historical_run_metadata映射和当前稳定输入。删除该新增条目后的解析对象必须与旧gate完全相等。
3. 在原draft line136附近捕获当前完整gatebytes并校验新entry。ROOT正常reservation entry保存新gate完整script_gate_pin，脚本在消费author槽前checked该pin；gate本身不存自己的hash，避免循环。新source必须匹配current gate.source_pin。
4. 替换原line217–221的全量current检查：仍要求pre/post307完全相同且路径唯一；仅精确旧gate/旧draft两条改为校验完整archive与旧record及finding原bytes，其余305照旧checked(current)。强制计数2+305，不允许其他路径豁免。
5. 输出前再核当前gatebytes不变、新source pin、双archive与305fixed；原24源/211保护/全部raw/JUnit/资源分母、身份和关闭断言完整保持。结算收据如实包含历史307/305current/2archive与新gate/source pins。

新source和gate尚未生成，afterSHA明确未知，必须ROOT实际全文读diff并取得真实SHA再批准，不能伪造expectedafter hash。完整字段和补丁范围在plan.json。

## 额度与验收

不增加任何执行槽。只继承原R175剩余ROOT settlement一次120s，两角色仍0/1；准备和recovery已用1/0。R174旧ROOT槽仍未用且effective superseded；R1583spent/12HELD不变。

完整门控后采用R176约定noclobber+exec原精确argv捕获真实stdout/stderr和工具返回。任何新失败停止，不重跑、不reset。七项测试不重跑，资源原件不修改。

本计划只恢复准确历史核验，不授予T1/B9/T12、原生/物理、实际或正式验收。ROOT实际结算及fresh独审仍待原门控；未知计数和未直接验证accessor边界保持。

