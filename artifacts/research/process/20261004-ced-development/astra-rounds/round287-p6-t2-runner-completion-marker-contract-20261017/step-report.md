# R287 步骤报告

完成标记层级错误已在新路径 runner 修正，保留顶层缺失与 observations 内真实布尔值的区别；收尾评估异常会保留实际错误并尝试持久化失败结果。完整1447行已审读，两处修改之外的字节、原生 Add 参数、candidate/after 均独立核对；新脚本未执行。

ROOT 唯一元数据核对 dc66b8 exit0，2642项通过。原 memory 用例 JUnit 1 PASS；独立核对原始对象分母542、初始化540、清理观察542，四组新数据库原件/归档及12项侧文件缺失。原 wrapper exit1及result缺失保持失败，直接 child exit/进程组清理回执仍null，不能补造正常结果或宣称整体capture/T2通过。

原ROOT memory同key结算为 SPENT_UNEXPECTED_WRAPPER_FINALIZATION_FAILURE1/0；AUTHOR仍SPENT，另外两项保持HELD0/1。完整before/base64/mode、CAS和after已保存，普通完整字节readback通过。R287范围证明966fc6失败保留；R288唯一新证明3d2cec exit0，只修正定位核对，候选未变。

当前阶段STOP；允许ROOT新fullbefore/CAS更新限定事实上下文。后续执行须实际Astra绑定新source/context及明确有界次数；本轮未新增行为/静态/审阅/Git槽，T2/T12、native、正式研究验收均未完成。
