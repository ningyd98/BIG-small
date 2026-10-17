# Astra Round88：只读 JSON 展示器类型判断

规划 gpt-6-astra；状态 PLAN_ONLY。仅处理ROOT激活前展示器失误，不是产品问题；不修改冻结R87及其预算。

## 原失败与输入

ROOT报告tool chunk7e8029、exit1，stdin第5行 `AttributeError: 'list' object has no attribute 'items'`。展示candidate-input-paths.json后，循环处理input-pins.json时无条件调用.items()，但后者是顶层list。完整原stdout/完整shell wrapper未提供；failure-evidence.json忠实保存ROOT提供的确切表达式、traceback和来源，不伪造独立捕获或未提供字节。本代理未重跑失败命令。

独立只读解析确认：input-pins.json为list；candidate-input-paths.json与candidate4-contract.json为dict。三文件精确bytes/SHA见plan.json/input_pins；另pin本轮failure-evidence.json。仅这四项，不pin产品或活动总表。ROOT另报Git三SHA均98b8282138ba61367db526d7d8f52e27085f4f9f且clean，本代理未执行Git核验。

## 限定恢复

1. ROOT复核四项pins，保留原失败。只修正临时只读展示表达式：先isinstance(d, dict)再使用.items()；elif isinstance(d, list)则展示len和有限前两项；其他类型给出明确类型诊断，不假定对象结构。不写回、转换或重序列化原输入文件。
2. 三文件采用分别已确认的schema：input-pins按list逐项访问path/bytes/sha256；candidate-input-paths按dict读取entries；candidate4-contract按dict读取nodeids/次数。显示截断只用于展示，真正pin/载荷核对仍遍历完整列表，不能只验证前两项。显式拒绝意外类型/必需字段缺失，不宽catch后继续。
3. 使用该只读分派重新读取这三个文件并完成激活所需核对，保存新的实际命令/exit和类型结果收据；本展示恢复不消费R87一次candidate4预算，不触发pytest、mypy、产品import或Git写入。若再遇不同schema/输入漂移，保留证据回Astra；不扩大到产品修复。
4. 通过后继续原样R87流程：ROOT实际activation绑定已推送OC2父提交及真实收据，有限P2载荷/闭包、candidate4一次、R81完整真实exit与strict0/逐原件例外、ROOT最终commit/non-force push/三SHA均不变。R88计划、原失败及新恢复收据均local-only，不改变R87的82项载荷+7项明确元数据发布边界。

## 验收边界

验收仅为三种实际输入的正确只读访问、原字节/pins不变、原失败保留、后续完整核对不受展示截断影响。无产品测试/代码更改；actual=0、formal=false。没有新的推送审批拒绝或重复用户确认要求；Git保护边界及GRASP/full future D不支持状态保持。
