# R557 最终准入修复及审查关闭

实际 gpt-6-astra 计划 SHA 5cb54c9f4a9513cd624e1b78bf809ccf5524877b0f9e87380a8f0d6e19961de3，25项输入和原始审查证据已复核。三份原源码逐字节gzip冻结；实际生产修改仅models.py、pipeline.py、grounded_planner.py和新回归文件，随后更新接口说明。

每次成功补帧草稿的PrivateAttr保留独立准入闭包，固定原绑定、独立校验过的新帧副本与checksum。原管线在真正build_task_contract及响应构造完成后检查；私有缓存项保留required和原闭包，缓存PLANNED返回前再检查。调用方、active_planner、原请求、角色与配置绑定不变，仍用5秒/50毫秒。私有引用不进入JSON/schema，不从公开证据授予资格。来源SHA纳入models和pipeline。

拒绝生成独立复制的contract/dispatch均null响应，响应和最后attempt的验证均失败，替换该缓存的成功项；先前交付对象不改写。负缓存不重试规划/采集/生成/付费。局部refresh确实PASSED仍保留，另记final_plan_admission拒绝。只允许固定本地ValueError原因码输出，其他回调异常仅显示类名，防止异常载荷泄漏。

RED32失败/1通过，全部缺少最终门/私有接口/来源清单，没有夹具错误。GREEN33通过；组合253通过；相关回归489通过/1既有anyio warning；观察器5通过；Ruff和diff通过。格式化前后四模块AST完全相同，见format-verification.json。原两份审查脚本原样重跑：最终构造6秒、过期缓存、设置漂移缓存三例均转REQUEST_MORE_OBSERVATION、合同空、无额外调用。旧脚本/失败输出保持不变。所有计数存在重叠，不相加。

R554-REV-1由上述新证据关闭：0未处理Critical/Important，0Minor；依计划不重新派发整体审查。此前全量一次仍94通过/1既有中文文档字符串失败，未完整通过且不修无关问题。

Molmo原运行时新增接口导入/CPU ABI复核通过，CUDA未初始化。迄今本轮实际模型/生成/付费调用为0，既定R554追加上限1/4/1不变，尚须真实运行；开发通过不替代真实合同、物理或正式研究。物理/正式研究NOT_RUN。
