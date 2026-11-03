# R406 默认模式引用兼容修复

仅_check_reference与_check_observation两处比较加入原合法默认UTC_LEGACY_VETO，执行既有_validate_references。当前产品SHA 1d4a55e578d35f56247439348cef31aca48b2aaf38d04968c1b45766369dda5e；原非这两处的字节/AST完全相同，worker/default/factory/clock/TTL/live owner/source/UTClease未改。

相同冻结新测试：原源码RED2.782秒（原捕获前置失败）；仅第一比较修复intermediateRED3.533秒（真实captured/referenceVALID之后observationFalse）；再修第二比较，新增4+原foreign5PASS13.518秒；原边界9PASS16.176秒；factory6PASS6.548秒。合计20GREEN，无skip；所有R235/源一致/清理均通过。原跨线程已真正到达目标，foreignUNKNOWN+原线程VALID。伪造window/source、错kind/observation、失效真实UTClease、未知mode仍拒绝。保留第三方Starlette/AnyIO弃用warning，未改依赖。

旧R399-R405失败、旧限额未达、旧native来源记录不改；当前全源变化不冒充旧native新运行。下一顺序补writer慢测试诊断/权限验收，再浏览器复测、最终整体独审与精选Git交付。当前未运行真实硬件/模型，非正式研究验收。
